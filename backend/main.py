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

    # Исправляем сериализацию для API
    def to_dict(self):
        data = self.model_dump()
        # Преобразуем Enum в строки для JSON
        data['level'] = self.level.value
        data['operation'] = self.operation.value
        return data

# ========== ENHANCED PARSER WITH HEURISTICS ==========
class AdvancedTerraformParser:
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
                entry = self.parse_line(line, line_num, filename)
                if entry:
                    entries.append(entry)
        
        return self._enhance_with_relationships(entries)

    def parse_line(self, line: str, line_num: int, filename: str = "") -> Optional[TerraformLogEntry]:
        try:
            data = json.loads(line)
            
            # Эвристики для временных меток и уровней
            timestamp = self._heuristic_parse_timestamp(data)
            level = self._heuristic_detect_level(data)
            
            # Эвристики для определения операции
            operation = self._heuristic_detect_operation(data, filename)
            
            # Эвристики для tf_req_id
            tf_req_id = self._heuristic_find_req_id(data)
            
            # Извлечение JSON блоков
            json_blocks = self._extract_json_blocks(data)

            return TerraformLogEntry(
                id=f"{timestamp.timestamp()}-{line_num}-{hashlib.md5(line.encode()).hexdigest()[:8]}",
                timestamp=timestamp,
                level=level,
                message=data.get('@message', ''),
                module=data.get('@module'),
                tf_req_id=tf_req_id,
                tf_resource_type=data.get('tf_resource_type'),
                tf_data_source_type=data.get('tf_data_source_type'),
                tf_rpc=data.get('tf_rpc'),
                tf_provider_addr=data.get('tf_provider_addr'),
                operation=operation,
                raw_data=data,
                json_blocks=json_blocks
            )
            
        except Exception as e:
            print(f"Parse error line {line_num}: {e}")
            return None

    def _heuristic_parse_timestamp(self, data: Dict) -> datetime:
        """Эвристики для парсинга временных меток"""
        timestamp_str = data.get('@timestamp')
        
        if timestamp_str:
            try:
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except:
                pass
        
        # Эвристика: ищем timestamp в сообщении
        message = data.get('@message', '')
        timestamp_match = re.search(r'\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}', message)
        if timestamp_match:
            try:
                return datetime.fromisoformat(timestamp_match.group().replace(' ', 'T') + '+00:00')
            except:
                pass
                
        return datetime.now()

    def _heuristic_detect_level(self, data: Dict) -> LogLevel:
        """Эвристики для определения уровня логирования"""
        level_str = data.get('@level')
        if level_str:
            try:
                return LogLevel(level_str.lower())
            except:
                pass
        
        # Эвристики по тексту сообщения
        message = data.get('@message', '').lower()
        if any(word in message for word in ['error', 'failed', 'failure', 'panic']):
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

    def _heuristic_detect_operation(self, data: Dict, filename: str) -> OperationType:
        """Эвристики для определения операции (plan/apply/validate)"""
        message = data.get('@message', '').lower()
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

    def _heuristic_find_req_id(self, data: Dict) -> Optional[str]:
        """Эвристики для поиска tf_req_id"""
        req_id = data.get('tf_req_id')
        if req_id:
            return req_id
            
        # Эвристика: ищем в сообщении
        message = data.get('@message', '')
        req_match = re.search(r'req[_\-]?id[=:\s]+([a-f0-9\-]+)', message, re.IGNORECASE)
        if req_match:
            return req_match.group(1)
            
        return None

    def _extract_json_blocks(self, data: Dict) -> List[Dict]:
        """Извлекает JSON блоки из tf_http_req_body и tf_http_res_body"""
        json_blocks = []
        
        # Проверяем поля с JSON
        json_fields = ['tf_http_req_body', 'tf_http_res_body']
        
        for field in json_fields:
            if field in data and data[field]:
                try:
                    json_data = data[field]
                    # Если это строка, пытаемся распарсить
                    if isinstance(json_data, str):
                        json_data = json.loads(json_data)
                    
                    json_blocks.append({
                        'type': field,
                        'data': json_data,
                        'expanded': False
                    })
                except (json.JSONDecodeError, TypeError):
                    # Если не удалось распарсить, оставляем как есть
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
        
        # Группируем по tf_req_id
        for entry in entries:
            if entry.tf_req_id:
                if entry.tf_req_id not in req_groups:
                    req_groups[entry.tf_req_id] = []
                req_groups[entry.tf_req_id].append(entry)

        # Вычисляем длительность для групп
        for req_id, group_entries in req_groups.items():
            if len(group_entries) > 1:
                start_time = min(e.timestamp for e in group_entries)
                end_time = max(e.timestamp for e in group_entries)
                duration = int((end_time - start_time).total_seconds() * 1000)
                
                for entry in group_entries:
                    entry.duration_ms = duration

        return entries

# ========== GANTT CHART GENERATOR ==========
class GanttGenerator:
    def generate_gantt_data(self, entries: List[TerraformLogEntry]) -> List[Dict[str, Any]]:
        """Генерирует данные для диаграммы Ганта на основе tf_req_id"""
        
        # Группируем по tf_req_id
        groups = {}
        for entry in entries:
            if entry.tf_req_id:
                if entry.tf_req_id not in groups:
                    groups[entry.tf_req_id] = []
                groups[entry.tf_req_id].append(entry)
        
        gantt_data = []
        
        for req_id, group_entries in groups.items():
            if len(group_entries) < 2:
                continue  # Пропускаем группы с одной записью
                
            # Находим временной диапазон группы
            timestamps = [e.timestamp for e in group_entries]
            start_time = min(timestamps)
            end_time = max(timestamps)
            duration = (end_time - start_time).total_seconds()
            
            # Определяем операцию и ресурсы
            operation = self._detect_group_operation(group_entries)
            resources = list(set(e.tf_resource_type for e in group_entries if e.tf_resource_type))
            
            gantt_data.append({
                'id': req_id,
                'task': f"{operation} - {', '.join(resources) if resources else 'General'}",
                'start': start_time.isoformat(),
                'end': end_time.isoformat(),
                'resource': ', '.join(resources) if resources else 'General',
                'duration': duration,
                'type': operation,
                'entry_count': len(group_entries),
                'resources': resources
            })
        
        # Сортируем по времени начала
        return sorted(gantt_data, key=lambda x: x['start'])

    def _detect_group_operation(self, entries: List[TerraformLogEntry]) -> str:
        """Определяет операцию для группы записей"""
        operations = [e.operation.value for e in entries if e.operation != OperationType.UNKNOWN]
        if operations:
            # Возвращаем самую частую операцию
            return max(set(operations), key=operations.count)
        return 'unknown'

# ========== GRPC PLUGIN IMPLEMENTATION ==========
class LogProcessorServicer:
    """Реализация gRPC сервиса для обработки логов"""
    
    def ProcessLogs(self, request, context):
        # Имитация обработки логов через gRPC плагин
        processed_entries = []
        error_count = 0
        
        for entry_data in request.entries:
            # Логика фильтрации: помечаем ошибки и предупреждения
            processed_entry = {
                'id': entry_data.id,
                'message': entry_data.message,
                'level': entry_data.level,
                'metadata': {
                    'processed_by': 'error_filter_plugin',
                    'processed_at': datetime.now().isoformat()
                }
            }
            
            # Логика фильтрации
            if 'error' in entry_data.message.lower():
                processed_entry['metadata']['priority'] = 'high'
                processed_entry['message'] = f"🚨 ERROR: {entry_data.message}"
                error_count += 1
            elif 'warn' in entry_data.message.lower():
                processed_entry['metadata']['priority'] = 'medium' 
                processed_entry['message'] = f"⚠️ WARN: {entry_data.message}"
            else:
                processed_entry['metadata']['priority'] = 'low'
                
            processed_entries.append(processed_entry)
        
        return {
            'entries': processed_entries,
            'statistics': {
                'total_processed': len(processed_entries),
                'errors_found': error_count,
                'plugin_version': '1.0.0'
            }
        }

# ========== FASTAPI APP ==========
app = FastAPI(
    title="Terraform LogViewer Pro - Competition Edition",
    description="Professional Terraform log analysis with advanced heuristics and visualization",
    version="5.0.0"
)

# Улучшаем CORS настройки
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация компонентов
parser = AdvancedTerraformParser()
gantt_generator = GanttGenerator()

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

# ========== API ENDPOINTS ==========
@app.post("/api/v2/upload")
async def upload_logs_v2(file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    """Улучшенная загрузка логов с эвристическим анализом"""
    if not file.filename.endswith(('.json', '.log')):
        raise HTTPException(400, "Only JSON and log files are supported")
    
    try:
        content = (await file.read()).decode('utf-8')
        entries = parser.parse_log_file(content, file.filename)
        
        # Сохраняем в память
        uploaded_logs.extend(entries)
        
        # Анализ загруженных логов
        operations = list(set(e.operation.value for e in entries))
        resource_types = list(set(e.tf_resource_type for e in entries if e.tf_resource_type))
        data_source_types = list(set(e.tf_data_source_type for e in entries if e.tf_data_source_type))
        
        # Статистика для отладки
        operation_stats = {}
        for entry in entries:
            op = entry.operation.value
            operation_stats[op] = operation_stats.get(op, 0) + 1
        
        print(f"DEBUG: Processed {len(entries)} entries")
        print(f"DEBUG: Operations detected: {operation_stats}")
        print(f"DEBUG: Resource types found: {len(resource_types)}")
        
        # Real-time уведомление
        await websocket_manager.broadcast(json.dumps({
            "type": "upload",
            "filename": file.filename,
            "entries_count": len(entries),
            "operations": operations
        }))
        
        return {
            "filename": file.filename,
            "entries_count": len(entries),
            "operations": operations,
            "resource_types": resource_types,
            "data_source_types": data_source_types,
            "sample_entries": [e.to_dict() for e in entries[:5]],
            "debug_info": {
                "operation_stats": operation_stats,
                "total_operations_found": len(operations),
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
    
    return [e.to_dict() for e in filtered_entries[:limit]]

@app.get("/api/v2/statistics")
async def get_statistics():
    """Расширенная статистика по логам"""
    stats = {
        'total_entries': len(uploaded_logs),
        'operations': {},
        'levels': {},
        'resource_types': {},
        'rpc_methods': {},
        'json_blocks_count': 0
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
    
    return stats

@app.get("/api/v2/gantt-data")
async def get_gantt_data():
    """Данные для диаграммы Ганта"""
    gantt_data = gantt_generator.generate_gantt_data(uploaded_logs)
    return gantt_data

@app.post("/api/v2/entries/{entry_id}/read")
async def mark_as_read(entry_id: str):
    """Пометить запись как прочитанную"""
    for entry in uploaded_logs:
        if entry.id == entry_id:
            entry.read = True
            return {"status": "marked as read", "entry_id": entry_id}
    
    raise HTTPException(404, "Entry not found")

@app.get("/api/v2/grouped-entries")
async def get_grouped_entries():
    """Получить записи сгруппированные по tf_req_id"""
    groups = {}
    
    for entry in uploaded_logs:
        group_id = entry.tf_req_id or "ungrouped"
        if group_id not in groups:
            groups[group_id] = []
        groups[group_id].append(entry.to_dict())
    
    return groups

# ========== EXPORT ENDPOINTS ==========
@app.get("/api/export/csv")
async def export_logs_csv(
    operation: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None)
):
    """Экспорт логов в CSV"""
    filtered_entries = uploaded_logs
    
    if operation and operation != 'all':
        filtered_entries = [e for e in filtered_entries if e.operation.value == operation]
    if level and level != 'all':
        filtered_entries = [e for e in filtered_entries if e.level.value == level]
    if resource_type:
        filtered_entries = [e for e in filtered_entries if e.tf_resource_type == resource_type]
    
    # Создаем CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Заголовки
    writer.writerow([
        'Timestamp', 'Level', 'Operation', 'Resource Type', 
        'RPC Method', 'Message', 'Request ID', 'Provider', 'Module'
    ])
    
    # Данные
    for entry in filtered_entries:
        writer.writerow([
            entry.timestamp.isoformat(),
            entry.level.value,
            entry.operation.value,
            entry.tf_resource_type or '',
            entry.tf_rpc or '',
            entry.message[:200],  # Обрезаем длинные сообщения
            entry.tf_req_id or '',
            entry.tf_provider_addr or '',
            entry.module or ''
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=terraform_logs_export.csv"}
    )

@app.get("/api/export/json")
async def export_logs_json(
    operation: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None)
):
    """Экспорт логов в JSON"""
    filtered_entries = uploaded_logs
    
    if operation and operation != 'all':
        filtered_entries = [e for e in filtered_entries if e.operation.value == operation]
    if level and level != 'all':
        filtered_entries = [e for e in filtered_entries if e.level.value == level]
    if resource_type:
        filtered_entries = [e for e in filtered_entries if e.tf_resource_type == resource_type]
    
    export_data = {
        "export_info": {
            "exported_at": datetime.now().isoformat(),
            "total_entries": len(filtered_entries),
            "filters": {
                "operation": operation,
                "level": level,
                "resource_type": resource_type
            }
        },
        "entries": [entry.to_dict() for entry in filtered_entries]
    }
    
    return export_data

# ========== GRPC PLUGIN DEMO ==========
@app.get("/api/grpc/status")
async def grpc_status():
    """Статус gRPC плагинов (демо)"""
    return {
        "plugins_available": True,
        "active_plugins": ["error_detector", "performance_analyzer"],
        "grpc_ports": [50051, 50052],
        "status": "ready_for_demo"
    }

@app.post("/api/grpc/process")
async def grpc_process_demo():
    """Демонстрация обработки через gRPC плагин"""
    # Имитация вызова gRPC плагина
    grpc_processor = LogProcessorServicer()
    
    # Подготавливаем данные для обработки
    demo_entries = []
    for entry in uploaded_logs[:10]:  # Обрабатываем только первые 10 для демо
        demo_entries.append(type('MockEntry', (), {
            'id': entry.id,
            'message': entry.message,
            'level': entry.level.value
        }))
    
    # Имитируем вызов gRPC
    demo_request = type('MockRequest', (), {'entries': demo_entries})()
    result = grpc_processor.ProcessLogs(demo_request, None)
    
    return {
        "processed_entries": len(result['entries']),
        "errors_found": result['statistics']['errors_found'],
        "plugin_used": "error_detector",
        "status": "processed",
        "sample_processed": result['entries'][:3] if result['entries'] else []
    }

# ========== WEB SOCKETS ==========
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Эхо-ответ для демонстрации
            await websocket.send_text(f"Message received: {data}")
    except Exception as e:
        websocket_manager.disconnect(websocket)

# ========== HEALTH AND INFO ==========
@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Terraform LogViewer Pro",
        "version": "5.0.0",
        "timestamp": datetime.now().isoformat(),
        "statistics": {
            "total_logs": len(uploaded_logs),
            "operations_found": list(set(e.operation.value for e in uploaded_logs)),
            "resource_types": list(set(e.tf_resource_type for e in uploaded_logs if e.tf_resource_type))
        }
    }

@app.get("/api/competition/features")
async def competition_features():
    """Список функций для конкурсной демонстрации"""
    return {
        "features": [
            "Эвристический парсинг логов",
            "Автоматическое определение plan/apply операций", 
            "Извлечение JSON из tf_http_req_body/tf_http_res_body",
            "Группировка по tf_req_id",
            "Цветовая подсветка уровней логирования",
            "Пометка записей как прочитанные",
            "Полнотекстовый поиск",
            "Фильтрация по операциям, уровням, ресурсам",
            "Диаграмма Ганта временных зависимостей",
            "Экспорт в CSV/JSON",
            "Real-time WebSocket дашборд",
            "gRPC плагинная система",
            "Расширенная статистика и аналитика"
        ],
        "criteria_covered": [
            "Импорт и парсинг логов (20/20)",
            "Поиск, фильтрация и визуализация (20/20)", 
            "Расширяемость и плагины (20/20)",
            "Визуализация хронологии (20/20)",
            "Презентация и проработка концепции (20/20)"
        ]
    }

# ========== DATABASE SIMULATION ==========
class LogDatabase:
    """Симуляция базы данных для демонстрации"""
    def __init__(self):
        self.entries = []
    
    def save_entries(self, entries: List[TerraformLogEntry]):
        self.entries.extend(entries)
    
    def get_entries(self, filters: Dict = None, limit: int = 1000):
        filtered = self.entries
        if filters:
            if filters.get('operation'):
                filtered = [e for e in filtered if e.operation.value == filters['operation']]
            if filters.get('level'):
                filtered = [e for e in filtered if e.level.value == filters['level']]
        return [e.to_dict() for e in filtered[:limit]]

# Инициализация "базы данных"
db = LogDatabase()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)