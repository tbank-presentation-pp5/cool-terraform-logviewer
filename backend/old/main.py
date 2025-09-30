from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
import uvicorn
import json
from datetime import datetime
from pydantic import BaseModel
from enum import Enum

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
    operation: OperationType
    raw_data: dict

app = FastAPI(
    title="Terraform LogViewer Pro",
    description="Advanced Terraform log analysis",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Улучшенный парсер в backend/main.py
class TerraformLogParser:
    def __init__(self):
        self.operation_keywords = {
            'plan': ['plan', 'plan operation', 'terraform plan'],
            'apply': ['apply', 'apply operation', 'terraform apply'], 
            'validate': ['validate', 'validation', 'validating']
        }
        
        self.rpc_operations = {
            'PlanResourceChange': 'plan',
            'ApplyResourceChange': 'apply', 
            'ValidateResourceConfig': 'validate',
            'ValidateDataResourceConfig': 'validate',
            'GetProviderSchema': 'validate'
        }

    def parse_line(self, line: str):
        try:
            data = json.loads(line)
            
            # Определяем операцию
            operation = self._detect_operation(data)
            
            entry = TerraformLogEntry(
                id=data.get('@timestamp', '') + str(hash(line)),
                timestamp=datetime.fromisoformat(data.get('@timestamp', '').replace('Z', '+00:00')),
                level=LogLevel(data.get('@level', 'info')),
                message=data.get('@message', ''),
                module=data.get('@module'),
                tf_req_id=data.get('tf_req_id'),
                tf_resource_type=data.get('tf_resource_type'),
                tf_data_source_type=data.get('tf_data_source_type'),
                tf_rpc=data.get('tf_rpc'),
                tf_provider_addr=data.get('tf_provider_addr'),
                operation=operation,
                raw_data=data
            )
            return entry
        except Exception as e:
            print(f"Parse error: {e}")
            return None

    def _detect_operation(self, data: dict) -> OperationType:
        message = data.get('@message', '').lower()
        tf_rpc = data.get('tf_rpc', '')
        
        # Сначала проверяем RPC методы
        if tf_rpc in self.rpc_operations:
            op = self.rpc_operations[tf_rpc]
            if op == 'plan':
                return OperationType.PLAN
            elif op == 'apply':
                return OperationType.APPLY
            elif op == 'validate':
                return OperationType.VALIDATE
        
        # Затем проверяем ключевые слова в сообщении
        for op_type, keywords in self.operation_keywords.items():
            if any(keyword in message for keyword in keywords):
                if op_type == 'plan':
                    return OperationType.PLAN
                elif op_type == 'apply':
                    return OperationType.APPLY
                elif op_type == 'validate':
                    return OperationType.VALIDATE
        
        # Если не определили, смотрим на имя файла (передается через raw_data)
        filename = data.get('_filename', '').lower()
        if 'plan' in filename:
            return OperationType.PLAN
        elif 'apply' in filename:
            return OperationType.APPLY
            
        return OperationType.UNKNOWN

    def parse_log_file(self, file_content: str) -> List[TerraformLogEntry]:
        entries = []
        lines = file_content.strip().split('\n')
        
        for line_num, line in enumerate(lines, 1):
            if line.strip():
                entry = self.parse_line(line)
                if entry:
                    entries.append(entry)
        return entries

parser = TerraformLogParser()

# Простая "база данных" в памяти
uploaded_logs = []

@app.post("/api/v2/upload")
async def upload_logs_v2(file: UploadFile = File(...)):
    if not file.filename.endswith(('.json', '.log')):
        raise HTTPException(400, "Only JSON and log files are supported")
    
    try:
        content = (await file.read()).decode('utf-8')
        entries = parser.parse_log_file(content)
        
        # Сохраняем в память
        uploaded_logs.extend(entries)
        
        # Анализ загруженных логов
        operations = list(set(e.operation.value for e in entries))
        resource_types = list(set(e.tf_resource_type for e in entries if e.tf_resource_type))
        data_source_types = list(set(e.tf_data_source_type for e in entries if e.tf_data_source_type))
        
        return {
            "filename": file.filename,
            "entries_count": len(entries),
            "operations": operations,
            "resource_types": resource_types,
            "data_source_types": data_source_types,
            "sample_entries": [e.dict() for e in entries[:5]]
        }
    except Exception as e:
        raise HTTPException(500, f"Processing failed: {str(e)}")

@app.get("/api/v2/entries")
async def get_entries_v2(
    operation: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, le=1000)
):
    filtered_entries = uploaded_logs
    
    if operation:
        filtered_entries = [e for e in filtered_entries if e.operation.value == operation]
    if level:
        filtered_entries = [e for e in filtered_entries if e.level.value == level]
    if resource_type:
        filtered_entries = [e for e in filtered_entries if e.tf_resource_type == resource_type]
    if search:
        filtered_entries = [
            e for e in filtered_entries 
            if search.lower() in e.message.lower() or 
               search.lower() in str(e.tf_rpc).lower()
        ]
    
    return [e.dict() for e in filtered_entries[:limit]]

@app.get("/api/v2/statistics")
async def get_statistics():
    """Статистика по логам"""
    stats = {
        'total_entries': len(uploaded_logs),
        'operations': {},
        'levels': {},
        'resource_types': {},
        'rpc_methods': {}
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
    
    return stats

@app.get("/api/v2/gantt-data")
async def get_gantt_data():
    """Данные для диаграммы Ганта (демо)"""
    if not uploaded_logs:
        return []
    
    # Простая демо-реализация
    gantt_data = []
    for i, entry in enumerate(uploaded_logs[:10]):
        gantt_data.append({
            'id': f"task-{i}",
            'task': f"{entry.operation.value} - {entry.tf_resource_type or 'general'}",
            'start': entry.timestamp.isoformat(),
            'end': (entry.timestamp.timestamp() + 300).isoformat(),  # +5 минут
            'resource': entry.tf_resource_type or 'general',
            'duration': 300,
            'type': entry.operation.value
        })
    
    return gantt_data

@app.get("/api/health")
def health_check():
    return {"status": "ready", "service": "Terraform LogViewer", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)