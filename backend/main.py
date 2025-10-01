from fastapi import FastAPI, UploadFile, File, HTTPException, Query, WebSocket, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn
import json
import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
import csv
import io
import hashlib

# ========== MODELS ==========
class LogLevel(str, Enum):
    TRACE = "trace"
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"

class OperationType(str, Enum):
    PLAN = "plan"
    APPLY = "apply"
    VALIDATE = "validate"
    UNKNOWN = "unknown"

class TerraformLogEntry(BaseModel):
    id: Optional[str] = None
    timestamp: datetime
    level: LogLevel
    message: str
    module: Optional[str] = None
    tf_req_id: Optional[str] = None
    tf_resource_type: Optional[str] = None
    tf_data_source_type: Optional[str] = None
    tf_rpc: Optional[str] = None
    tf_provider_addr: Optional[str] = None
    operation: OperationType = OperationType.UNKNOWN
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    parent_req_id: Optional[str] = None
    duration_ms: Optional[int] = None
    json_blocks: List[Dict] = Field(default_factory=list)
    read: bool = False
    parse_error: bool = False  # Новое поле для пометки ошибок парсинга
    error_type: Optional[str] = None  # Тип ошибки парсинга

    def to_dict(self):
        data = self.model_dump()
        data['level'] = self.level.value
        data['operation'] = self.operation.value
        return data

# ========== ENHANCED PARSER WITH ROBUST JSON HANDLING ==========
class RobustTerraformParser:
    def __init__(self):
        self.plan_patterns = [
            r'terraform.*plan',
            r'plan.*operation',
            r'PlanResourceChange',
            r'planned.*action',
            r'refresh.*plan',
            r'Creating.*plan'
        ]
        
        self.apply_patterns = [
            r'terraform.*apply', 
            r'apply.*operation',
            r'ApplyResourceChange',
            r'applying.*configuration',
            r'create.*resource',
            r'Creating.*resource'
        ]
        
        self.validate_patterns = [
            r'validate',
            r'validation',
            r'validating',
            r'ValidateResourceConfig',
            r'ValidateDataResourceConfig'
        ]

        self.rpc_hierarchy = {
            'GetProviderSchema': 'schema',
            'ValidateProviderConfig': 'validation',
            'ValidateDataResourceConfig': 'validation', 
            'ValidateResourceConfig': 'validation',
            'PlanResourceChange': 'plan',
            'ApplyResourceChange': 'apply'
        }

    def parse_log_file(self, file_content: str, filename: str = "") -> List[TerraformLogEntry]:
        entries = []
        lines = file_content.strip().split('\n')
        
        for line_num, line in enumerate(lines, 1):
            if line.strip():
                entry = self.parse_line_robust(line, line_num, filename)
                if entry:
                    entries.append(entry)
        
        return self._enhance_with_relationships(entries)

    def parse_line_robust(self, line: str, line_num: int, filename: str = "") -> Optional[TerraformLogEntry]:
        """Улучшенный парсер с обработкой сломанных JSON"""
        original_line = line
        
        # Попытка 1: Стандартный JSON парсинг
        try:
            data = json.loads(line)
            return self._create_entry_from_data(data, line_num, filename, line)
        except json.JSONDecodeError as e:
            # Попытка 2: Восстановление неполного JSON
            repaired_data = self._repair_json_line(line)
            if repaired_data:
                try:
                    data = json.loads(repaired_data)
                    return self._create_entry_from_data(data, line_num, filename, line, parse_error=True, error_type="repaired_json")
                except:
                    pass
            
            # Попытка 3: Извлечение полей через регулярные выражения
            extracted_data = self._extract_fields_with_regex(line)
            if extracted_data:
                return self._create_entry_from_data(extracted_data, line_num, filename, line, parse_error=True, error_type="regex_extracted")
            
            # Попытка 4: Создание записи об ошибке
            return self._create_error_entry(line, line_num, filename, str(e))
        
        except Exception as e:
            # Любая другая ошибка
            return self._create_error_entry(line, line_num, filename, f"unexpected_error: {str(e)}")

    def _repair_json_line(self, line: str) -> Optional[str]:
        """Пытается восстановить сломанный JSON"""
        # Случай 1: Не закрытая фигурная скобка
        if line.startswith('{') and not line.endswith('}'):
            # Добавляем закрывающую скобку и возможные кавычки
            repaired = line.strip()
            if not repaired.endswith('"'):
                repaired += '"'
            repaired += '}'
            return repaired
        
        # Случай 2: Не хватает кавычек
        if ': {' in line and not line.endswith('}'):
            return line + '}'
        
        # Случай 3: Частичный JSON в начале строки
        json_match = re.search(r'(\{.*)', line)
        if json_match:
            partial_json = json_match.group(1)
            if not partial_json.endswith('}'):
                partial_json += '}'
            return partial_json
        
        return None

    def _extract_fields_with_regex(self, line: str) -> Dict[str, Any]:
        """Извлекает поля лога через регулярные выражения"""
        extracted = {}
        
        # Паттерны для извлечения common полей
        patterns = {
            'timestamp': r'"@timestamp"\s*:\s*"([^"]+)"',
            'level': r'"@level"\s*:\s*"([^"]+)"',
            'message': r'"@message"\s*:\s*"([^"]*)"',
            'module': r'"@module"\s*:\s*"([^"]*)"',
            'tf_req_id': r'"tf_req_id"\s*:\s*"([^"]*)"',
            'tf_resource_type': r'"tf_resource_type"\s*:\s*"([^"]*)"',
            'tf_rpc': r'"tf_rpc"\s*:\s*"([^"]*)"'
        }
        
        for field, pattern in patterns.items():
            match = re.search(pattern, line)
            if match:
                extracted[f"@{field}" if field in ['timestamp', 'level', 'message', 'module'] else field] = match.group(1)
        
        # Если нашли хоть что-то, возвращаем
        return extracted if extracted else None

    def _create_entry_from_data(self, data: Dict, line_num: int, filename: str, original_line: str, 
                              parse_error: bool = False, error_type: str = None) -> TerraformLogEntry:
        """Создает запись из данных с эвристиками"""
        # Эвристики для временных меток и уровней
        timestamp = self._heuristic_parse_timestamp(data, original_line)
        level = self._heuristic_detect_level(data, original_line)
        
        # Эвристики для определения операции
        operation = self._heuristic_detect_operation(data, filename, original_line)
        
        # Эвристики для tf_req_id
        tf_req_id = self._heuristic_find_req_id(data, original_line)
        
        # Извлечение JSON блоков
        json_blocks = self._extract_json_blocks(data)

        return TerraformLogEntry(
            id=f"{timestamp.timestamp()}-{line_num}-{hashlib.md5(original_line.encode()).hexdigest()[:8]}",
            timestamp=timestamp,
            level=level,
            message=data.get('@message', data.get('message', original_line[:200])),
            module=data.get('@module', data.get('module')),
            tf_req_id=tf_req_id,
            tf_resource_type=data.get('tf_resource_type'),
            tf_data_source_type=data.get('tf_data_source_type'),
            tf_rpc=data.get('tf_rpc'),
            tf_provider_addr=data.get('tf_provider_addr'),
            operation=operation,
            raw_data=data,
            json_blocks=json_blocks,
            parse_error=parse_error,
            error_type=error_type
        )

    def _create_error_entry(self, line: str, line_num: int, filename: str, error: str) -> TerraformLogEntry:
        """Создает запись об ошибке парсинга"""
        timestamp = self._extract_timestamp_from_line(line) or datetime.now()
        
        return TerraformLogEntry(
            id=f"error-{timestamp.timestamp()}-{line_num}-{hashlib.md5(line.encode()).hexdigest()[:8]}",
            timestamp=timestamp,
            level=LogLevel.ERROR,
            message=f"JSON_PARSE_ERROR: {error} - {line[:100]}...",
            module="parser",
            operation=OperationType.UNKNOWN,
            raw_data={"original_line": line, "error": error},
            parse_error=True,
            error_type="json_parse_error"
        )

    def _extract_timestamp_from_line(self, line: str) -> Optional[datetime]:
        """Извлекает timestamp из строки через регулярки"""
        # Паттерны для timestamp
        patterns = [
            r'\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}',
            r'\d{2}:\d{2}:\d{2}',
            r'\d{4}-\d{2}-\d{2}'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                try:
                    timestamp_str = match.group()
                    # Пытаемся разобрать разные форматы
                    for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%H:%M:%S']:
                        try:
                            if fmt == '%H:%M:%S':
                                # Для времени без даты используем сегодняшнюю дату
                                today = datetime.now().date()
                                time_str = timestamp_str
                                return datetime.combine(today, datetime.strptime(time_str, fmt).time())
                            return datetime.strptime(timestamp_str, fmt)
                        except:
                            continue
                except:
                    continue
        return None

    def _heuristic_parse_timestamp(self, data: Dict, original_line: str = "") -> datetime:
        """Улучшенные эвристики для парсинга временных меток"""
        timestamp_str = data.get('@timestamp') or data.get('timestamp')
        
        if timestamp_str:
            try:
                # Обработка различных форматов timestamp
                if 'T' in timestamp_str:
                    return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                else:
                    # Пробуем разные форматы
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                        try:
                            return datetime.strptime(timestamp_str, fmt)
                        except:
                            continue
            except:
                pass
        
        # Эвристика из сообщения
        extracted_ts = self._extract_timestamp_from_line(original_line or data.get('@message', ''))
        if extracted_ts:
            return extracted_ts
                
        return datetime.now()

    def _heuristic_detect_level(self, data: Dict, original_line: str = "") -> LogLevel:
        """Улучшенные эвристики для определения уровня логирования"""
        level_str = data.get('@level') or data.get('level')
        if level_str:
            try:
                return LogLevel(level_str.lower())
            except:
                pass
        
        # Эвристики по тексту
        message = (data.get('@message') or data.get('message') or original_line or "").lower()
        if any(word in message for word in ['error', 'failed', 'failure', 'panic', 'crash']):
            return LogLevel.ERROR
        elif any(word in message for word in ['warn', 'warning']):
            return LogLevel.WARN
        elif any(word in message for word in ['info', 'information']):
            return LogLevel.INFO
        elif any(word in message for word in ['debug']):
            return LogLevel.DEBUG
        elif any(word in message for word in ['trace']):
            return LogLevel.TRACE
            
        return LogLevel.INFO

    def _heuristic_detect_operation(self, data: Dict, filename: str, original_line: str = "") -> OperationType:
        """Улучшенные эвристики для определения операции"""
        message = (data.get('@message') or data.get('message') or original_line or "").lower()
        tf_rpc = data.get('tf_rpc', '')
        
        # Проверяем RPC методы
        if tf_rpc in self.rpc_hierarchy:
            rpc_op = self.rpc_hierarchy[tf_rpc]
            if rpc_op == 'plan':
                return OperationType.PLAN
            elif rpc_op == 'apply':
                return OperationType.APPLY
            elif rpc_op in ['validation', 'schema']:
                return OperationType.VALIDATE
        
        # Эвристики по тексту сообщения
        if any(re.search(pattern, message, re.IGNORECASE) for pattern in self.plan_patterns):
            return OperationType.PLAN
        elif any(re.search(pattern, message, re.IGNORECASE) for pattern in self.apply_patterns):
            return OperationType.APPLY
        elif any(re.search(pattern, message, re.IGNORECASE) for pattern in self.validate_patterns):
            return OperationType.VALIDATE
            
        # Эвристика по имени файла
        filename_lower = filename.lower()
        if 'plan' in filename_lower:
            return OperationType.PLAN
        elif 'apply' in filename_lower:
            return OperationType.APPLY
            
        return OperationType.UNKNOWN

    def _heuristic_find_req_id(self, data: Dict, original_line: str = "") -> Optional[str]:
        """Улучшенные эвристики для поиска tf_req_id"""
        req_id = data.get('tf_req_id')
        if req_id:
            return req_id
            
        # Эвристика: ищем в сообщении
        message = data.get('@message') or data.get('message') or original_line or ""
        patterns = [
            r'req[_\-]?id[=:\s]+([a-f0-9\-]+)',
            r'request[_-]id[=:\s]+([a-f0-9\-]+)',
            r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})'  # UUID
        ]
        
        for pattern in patterns:
            req_match = re.search(pattern, message, re.IGNORECASE)
            if req_match:
                return req_match.group(1)
            
        return None

    def _extract_json_blocks(self, data: Dict) -> List[Dict]:
        """Извлекает JSON блоки"""
        json_blocks = []
        
        json_fields = ['tf_http_req_body', 'tf_http_res_body', 'body', 'request', 'response']
        
        for field in json_fields:
            if field in data and data[field]:
                try:
                    json_data = data[field]
                    if isinstance(json_data, str):
                        json_data = json.loads(json_data)
                    
                    json_blocks.append({
                        'type': field,
                        'data': json_data,
                        'expanded': False
                    })
                except (json.JSONDecodeError, TypeError):
                    json_blocks.append({
                        'type': field,
                        'data': data[field],
                        'expanded': False,
                        'raw': True
                    })
        
        return json_blocks

    def _enhance_with_relationships(self, entries: List[TerraformLogEntry]) -> List[TerraformLogEntry]:
        """Добавляем информацию о зависимостях и длительности"""
        req_groups = {}
        
        for entry in entries:
            if entry.tf_req_id:
                if entry.tf_req_id not in req_groups:
                    req_groups[entry.tf_req_id] = []
                req_groups[entry.tf_req_id].append(entry)

        for req_id, group_entries in req_groups.items():
            if len(group_entries) > 1:
                valid_entries = [e for e in group_entries if e.timestamp]
                if valid_entries:
                    start_time = min(e.timestamp for e in valid_entries)
                    end_time = max(e.timestamp for e in valid_entries)
                    duration = max(1, int((end_time - start_time).total_seconds() * 1000))  # Минимум 1 мс
                    
                    for entry in group_entries:
                        entry.duration_ms = duration

        return entries

# ========== IMPROVED GANTT CHART GENERATOR ==========
class ImprovedGanttGenerator:
    def generate_gantt_data(self, entries: List[TerraformLogEntry]) -> List[Dict[str, Any]]:
        """Улучшенный генератор данных для диаграммы Ганта"""
        
        # Группируем по tf_req_id и операциям
        groups = {}
        for entry in entries:
            if entry.tf_req_id:
                group_key = f"{entry.tf_req_id}-{entry.operation.value}"
                if group_key not in groups:
                    groups[group_key] = []
                groups[group_key].append(entry)
        
        gantt_data = []
        
        for group_key, group_entries in groups.items():
            valid_entries = [e for e in group_entries if e.timestamp]
            if len(valid_entries) < 1:
                continue
                
            # Находим временной диапазон группы
            timestamps = [e.timestamp for e in valid_entries]
            start_time = min(timestamps)
            end_time = max(timestamps)
            duration = (end_time - start_time).total_seconds()
            
            # Минимальная длительность для отображения на timeline
            min_duration = 1  # 1 секунда минимум
            
            # Определяем операцию и ресурсы
            operation = self._detect_group_operation(group_entries)
            resources = list(set(e.tf_resource_type for e in group_entries if e.tf_resource_type))
            
            gantt_data.append({
                'id': group_key,
                'task': self._format_task_name(operation, resources),
                'start': start_time.isoformat(),
                'end': end_time.isoformat(),
                'resource': ', '.join(resources) if resources else 'General',
                'duration': max(duration, min_duration),  # Гарантируем минимальную длительность
                'type': operation,
                'entry_count': len(group_entries),
                'resources': resources,
                'raw_duration': duration  # Оригинальная длительность для отладки
            })
        
        # Если нет сгруппированных данных, создаем общие группы по времени
        if not gantt_data:
            gantt_data = self._create_time_based_groups(entries)
        
        return sorted(gantt_data, key=lambda x: x['start'])

    def _format_task_name(self, operation: str, resources: List[str]) -> str:
        """Форматирует имя задачи для отображения"""
        if resources:
            # Ограничиваем количество отображаемых ресурсов
            display_resources = resources  # Максимум 5 ресурсов
            resource_str = ', '.join(display_resources)
            # if len(resources) > 5:
            #     resource_str += f" (+{len(resources) - 5} more)"
            return f"{operation} - {resource_str}"
        else:
            return f"{operation} - General"

    def _detect_group_operation(self, entries: List[TerraformLogEntry]) -> str:
        """Определяет операцию для группы записей"""
        operations = [e.operation.value for e in entries if e.operation != OperationType.UNKNOWN]
        if operations:
            return max(set(operations), key=operations.count)
        return 'unknown'

    def _create_time_based_groups(self, entries: List[TerraformLogEntry]) -> List[Dict[str, Any]]:
        """Создает группы на основе временных интервалов когда нет tf_req_id"""
        if not entries:
            return []
        
        # Сортируем по времени
        sorted_entries = sorted(entries, key=lambda x: x.timestamp)
        
        # Группируем по 5-секундным интервалам
        groups = []
        current_group = []
        group_start = sorted_entries[0].timestamp
        
        for entry in sorted_entries:
            time_diff = (entry.timestamp - group_start).total_seconds()
            if time_diff > 5.0 and current_group:  # 5 секунд - новый интервал
                groups.append(current_group)
                current_group = [entry]
                group_start = entry.timestamp
            else:
                current_group.append(entry)
        
        if current_group:
            groups.append(current_group)
        
        # Создаем gantt данные из временных групп
        gantt_data = []
        for i, group in enumerate(groups):
            if group:
                start_time = min(e.timestamp for e in group)
                end_time = max(e.timestamp for e in group)
                duration = max(1.0, (end_time - start_time).total_seconds())
                
                operations = list(set(e.operation.value for e in group))
                operation = operations[0] if operations else 'unknown'
                
                gantt_data.append({
                    'id': f'time-group-{i}',
                    'task': f'{operation} - Time Group {i+1}',
                    'start': start_time.isoformat(),
                    'end': end_time.isoformat(),
                    'resource': 'Time-based',
                    'duration': duration,
                    'type': operation,
                    'entry_count': len(group),
                    'resources': []
                })
        
        return gantt_data

# ========== FASTAPI APP ==========
app = FastAPI(
    title="Terraform LogViewer Pro - Enhanced Edition",
    description="Professional Terraform log analysis with robust parsing and improved visualization",
    version="6.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация улучшенных компонентов
parser = RobustTerraformParser()
gantt_generator = ImprovedGanttGenerator()

# "База данных" в памяти
uploaded_logs: List[TerraformLogEntry] = []

# ========== WEB SOCKET MANAGER ==========
class WebSocketManager:
    def __init__(self):
        self.active_connections = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                self.active_connections.remove(connection)

websocket_manager = WebSocketManager()

# ========== ENHANCED API ENDPOINTS ==========
@app.post("/api/v2/upload")
async def upload_logs_v2(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """Улучшенная загрузка логов с обработкой ошибок"""
    if not file.filename.endswith(('.json', '.log', '.txt')):
        raise HTTPException(400, "Only JSON, log and text files are supported")
    
    try:
        content = (await file.read()).decode('utf-8')
        entries = parser.parse_log_file(content, file.filename)
        
        # Сохраняем в память
        uploaded_logs.extend(entries)
        
        # Статистика парсинга
        parse_errors = [e for e in entries if e.parse_error]
        operation_stats = {}
        for entry in entries:
            op = entry.operation.value
            operation_stats[op] = operation_stats.get(op, 0) + 1
        
        resource_types = list(set(e.tf_resource_type for e in entries if e.tf_resource_type))
        
        print(f"DEBUG: Processed {len(entries)} entries")
        print(f"DEBUG: Parse errors: {len(parse_errors)}")
        print(f"DEBUG: Operations detected: {operation_stats}")
        
        # Real-time уведомление
        await websocket_manager.broadcast(json.dumps({
            "type": "upload",
            "filename": file.filename,
            "entries_count": len(entries),
            "parse_errors": len(parse_errors),
            "operations": list(operation_stats.keys())
        }))
        
        return {
            "filename": file.filename,
            "entries_count": len(entries),
            "parse_errors": len(parse_errors),
            "operations": list(operation_stats.keys()),
            "resource_types": resource_types,
            "sample_entries": [e.to_dict() for e in entries[:5]],
            "debug_info": {
                "operation_stats": operation_stats,
                "parse_error_types": list(set(e.error_type for e in parse_errors if e.error_type)),
                "json_blocks_found": sum(len(e.json_blocks) for e in entries)
            }
        }
        
    except Exception as e:
        print(f"Upload error: {str(e)}")
        raise HTTPException(500, f"Processing failed: {str(e)}")

@app.get("/api/v2/entries")
async def get_entries_v2(
    operation: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    show_read: bool = Query(True),
    show_parse_errors: bool = Query(True),
    limit: int = Query(100, le=1000)
):
    """Получение записей с улучшенной фильтрацией"""
    filtered_entries = uploaded_logs
    
    if operation and operation != 'all':
        filtered_entries = [e for e in filtered_entries if e.operation.value == operation]
    if level and level != 'all':
        filtered_entries = [e for e in filtered_entries if e.level.value == level]
    if resource_type:
        filtered_entries = [e for e in filtered_entries if e.tf_resource_type == resource_type]
    if search:
        filtered_entries = [
            e for e in filtered_entries 
            if search.lower() in e.message.lower() or 
               search.lower() in str(e.tf_rpc).lower() or
               search.lower() in str(e.tf_resource_type).lower()
        ]
    if not show_read:
        filtered_entries = [e for e in filtered_entries if not e.read]
    if not show_parse_errors:
        filtered_entries = [e for e in filtered_entries if not e.parse_error]
    
    return [e.to_dict() for e in filtered_entries[:limit]]

@app.get("/api/v2/statistics")
async def get_statistics():
    """Расширенная статистика по логам"""
    stats = {
        'total_entries': len(uploaded_logs),
        'parse_errors': len([e for e in uploaded_logs if e.parse_error]),
        'operations': {},
        'levels': {},
        'resource_types': {},
        'rpc_methods': {},
        'json_blocks_count': 0,
        'error_types': {}
    }
    
    for entry in uploaded_logs:
        # Операции
        op = entry.operation.value
        stats['operations'][op] = stats['operations'].get(op, 0) + 1
        
        # Уровни
        level = entry.level.value
        stats['levels'][level] = stats['levels'].get(level, 0) + 1
        
        # Типы ресурсов
        resource_type = entry.tf_resource_type
        if resource_type:
            stats['resource_types'][resource_type] = stats['resource_types'].get(resource_type, 0) + 1
            
        # RPC методы
        rpc_method = entry.tf_rpc
        if rpc_method:
            stats['rpc_methods'][rpc_method] = stats['rpc_methods'].get(rpc_method, 0) + 1
            
        # JSON блоки
        stats['json_blocks_count'] += len(entry.json_blocks)
        
        # Типы ошибок парсинга
        if entry.parse_error and entry.error_type:
            stats['error_types'][entry.error_type] = stats['error_types'].get(entry.error_type, 0) + 1
    
    return stats

@app.get("/api/v2/gantt-data")
async def get_gantt_data():
    """Улучшенные данные для диаграммы Ганта"""
    gantt_data = gantt_generator.generate_gantt_data(uploaded_logs)
    
    # Добавляем отладочную информацию
    debug_info = {
        "total_groups": len(gantt_data),
        "groups_with_duration": len([g for g in gantt_data if g['duration'] > 0]),
        "min_duration": min([g['duration'] for g in gantt_data]) if gantt_data else 0,
        "max_duration": max([g['duration'] for g in gantt_data]) if gantt_data else 0
    }
    
    return {
        "gantt_data": gantt_data,
        "debug_info": debug_info
    }

@app.post("/api/v2/entries/{entry_id}/read")
async def mark_as_read(entry_id: str):
    """Пометить запись как прочитанную"""
    for entry in uploaded_logs:
        if entry.id == entry_id:
            entry.read = True
            return {"status": "marked as read", "entry_id": entry_id}
    
    raise HTTPException(404, "Entry not found")

# ========== HEALTH AND INFO ==========
@app.get("/api/health")
async def health_check():
    parse_errors = len([e for e in uploaded_logs if e.parse_error])
    
    return {
        "status": "healthy",
        "service": "Terraform LogViewer Pro - Enhanced",
        "version": "6.0.0",
        "timestamp": datetime.now().isoformat(),
        "statistics": {
            "total_logs": len(uploaded_logs),
            "parse_errors": parse_errors,
            "operations_found": list(set(e.operation.value for e in uploaded_logs)),
            "resource_types": list(set(e.tf_resource_type for e in uploaded_logs if e.tf_resource_type))
        }
    }

@app.get("/api/debug/parser-info")
async def debug_parser_info():
    """Отладочная информация о парсере"""
    error_entries = [e for e in uploaded_logs if e.parse_error]
    
    return {
        "total_entries": len(uploaded_logs),
        "parse_errors": len(error_entries),
        "error_types": list(set(e.error_type for e in error_entries if e.error_type)),
        "sample_errors": [e.to_dict() for e in error_entries[:3]]
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)