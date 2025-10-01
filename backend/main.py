import csv
import hashlib
import io
import json
import re
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any

import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


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
    parse_error: bool = False
    error_type: Optional[str] = None

    def to_dict(self):
        data = self.model_dump()
        data['timestamp'] = self.timestamp.isoformat()
        data['level'] = self.level.value
        data['operation'] = self.operation.value
        return data


# ========== ENHANCED PARSER ==========
class RobustTerraformParser:
    def __init__(self):
        self.plan_patterns = [
            r'terraform.*plan', r'plan.*operation', r'PlanResourceChange',
            r'planned.*action', r'refresh.*plan', r'Creating.*plan'
        ]
        self.apply_patterns = [
            r'terraform.*apply', r'apply.*operation', r'ApplyResourceChange',
            r'applying.*configuration', r'create.*resource', r'Creating.*resource'
        ]
        self.validate_patterns = [
            r'validate', r'validation', r'validating',
            r'ValidateResourceConfig', r'ValidateDataResourceConfig'
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
            # raw_logs
            raw_uploaded_logs.append(json.loads(line))
            ##
            if line.strip():
                entry = self.parse_line_robust(line, line_num, filename)
                if entry:
                    entries.append(entry)

        return self._enhance_with_relationships(entries)

    def parse_line_robust(self, line: str, line_num: int, filename: str = "") -> Optional[TerraformLogEntry]:
        try:
            data = json.loads(line)
            return self._create_entry_from_data(data, line_num, filename, line)
        except json.JSONDecodeError:
            repaired_data = self._repair_json_line(line)
            if repaired_data:
                try:
                    data = json.loads(repaired_data)
                    return self._create_entry_from_data(data, line_num, filename, line, parse_error=True,
                                                        error_type="repaired_json")
                except:
                    pass

            extracted_data = self._extract_fields_with_regex(line)
            if extracted_data:
                return self._create_entry_from_data(extracted_data, line_num, filename, line, parse_error=True,
                                                    error_type="regex_extracted")

            return self._create_error_entry(line, line_num, filename, "json_parse_error")

    def _repair_json_line(self, line: str) -> Optional[str]:
        if line.startswith('{') and not line.endswith('}'):
            repaired = line.strip()
            if not repaired.endswith('"'):
                repaired += '"'
            repaired += '}'
            return repaired

        json_match = re.search(r'(\{.*)', line)
        if json_match:
            partial_json = json_match.group(1)
            if not partial_json.endswith('}'):
                partial_json += '}'
            return partial_json

        return None

    def _extract_fields_with_regex(self, line: str) -> Optional[Dict[str, Any]]:
        extracted = {}
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
                key = f"@{field}" if field in ['timestamp', 'level', 'message', 'module'] else field
                extracted[key] = match.group(1)

        return extracted if extracted else None

    def _create_entry_from_data(self, data: Dict, line_num: int, filename: str, original_line: str,
                                parse_error: bool = False, error_type: str = None) -> TerraformLogEntry:
        timestamp = self._heuristic_parse_timestamp(data, original_line)
        level = self._heuristic_detect_level(data, original_line)
        operation = self._heuristic_detect_operation(data, filename, original_line)
        tf_req_id = self._heuristic_find_req_id(data, original_line)
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
        timestamp = self._extract_timestamp_from_line(line) or datetime.now()

        return TerraformLogEntry(
            id=f"error-{timestamp.timestamp()}-{line_num}",
            timestamp=timestamp,
            level=LogLevel.ERROR,
            message=f"PARSE_ERROR: {line[:100]}",
            module="parser",
            operation=OperationType.UNKNOWN,
            raw_data={"original_line": line, "error": error},
            parse_error=True,
            error_type=error

        )

    def _extract_timestamp_from_line(self, line: str) -> Optional[datetime]:
        patterns = [r'\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}', r'\d{2}:\d{2}:\d{2}']
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                try:
                    timestamp_str = match.group()
                    for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%H:%M:%S']:
                        try:
                            if fmt == '%H:%M:%S':
                                today = datetime.now().date()
                                return datetime.combine(today, datetime.strptime(timestamp_str, fmt).time())
                            return datetime.strptime(timestamp_str, fmt)
                        except:
                            continue
                except:
                    continue
        return None

    def _heuristic_parse_timestamp(self, data: Dict, original_line: str = "") -> datetime:
        timestamp_str = data.get('@timestamp') or data.get('timestamp')
        if timestamp_str:
            try:
                if 'T' in timestamp_str:
                    return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f']:
                    try:
                        return datetime.strptime(timestamp_str, fmt)
                    except:
                        continue
            except:
                pass

        extracted_ts = self._extract_timestamp_from_line(original_line or data.get('@message', ''))
        return extracted_ts if extracted_ts else datetime.now()

    def _heuristic_detect_level(self, data: Dict, original_line: str = "") -> LogLevel:
        level_str = data.get('@level') or data.get('level')
        if level_str:
            try:
                return LogLevel(level_str.lower())
            except:
                pass

        message = (data.get('@message') or data.get('message') or original_line or "").lower()
        if any(word in message for word in ['error', 'failed', 'failure', 'panic']):
            return LogLevel.ERROR
        elif any(word in message for word in ['warn', 'warning']):
            return LogLevel.WARN
        elif 'debug' in message:
            return LogLevel.DEBUG
        elif 'trace' in message:
            return LogLevel.TRACE
        return LogLevel.INFO

    def _heuristic_detect_operation(self, data: Dict, filename: str, original_line: str = "") -> OperationType:
        message = (data.get('@message') or data.get('message') or original_line or "").lower()
        tf_rpc = data.get('tf_rpc', '')

        if tf_rpc in self.rpc_hierarchy:
            rpc_op = self.rpc_hierarchy[tf_rpc]
            if rpc_op == 'plan':
                return OperationType.PLAN
            elif rpc_op == 'apply':
                return OperationType.APPLY
            elif rpc_op in ['validation', 'schema']:
                return OperationType.VALIDATE

        if any(re.search(p, message, re.I) for p in self.plan_patterns):
            return OperationType.PLAN
        elif any(re.search(p, message, re.I) for p in self.apply_patterns):
            return OperationType.APPLY
        elif any(re.search(p, message, re.I) for p in self.validate_patterns):
            return OperationType.VALIDATE

        if 'plan' in filename.lower():
            return OperationType.PLAN
        elif 'apply' in filename.lower():
            return OperationType.APPLY

        return OperationType.UNKNOWN

    def _heuristic_find_req_id(self, data: Dict, original_line: str = "") -> Optional[str]:
        req_id = data.get('tf_req_id')
        if req_id:
            return req_id

        message = data.get('@message') or data.get('message') or original_line or ""
        patterns = [
            r'req[_\-]?id[=:\s]+([a-f0-9\-]+)',
            r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})'
        ]

        for pattern in patterns:
            req_match = re.search(pattern, message, re.IGNORECASE)
            if req_match:
                return req_match.group(1)
        return None

    def _extract_json_blocks(self, data: Dict) -> List[Dict]:
        json_blocks = []
        json_fields = ['tf_http_req_body', 'tf_http_res_body', 'body', 'request', 'response']

        for field in json_fields:
            if field in data and data[field]:
                try:
                    json_data = data[field]
                    if isinstance(json_data, str):
                        json_data = json.loads(json_data)
                    json_blocks.append({'type': field, 'data': json_data, 'expanded': False})
                except:
                    json_blocks.append({'type': field, 'data': data[field], 'expanded': False, 'raw': True})

        return json_blocks

    def _enhance_with_relationships(self, entries: List[TerraformLogEntry]) -> List[TerraformLogEntry]:
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
                    duration = max(1, int((end_time - start_time).total_seconds() * 1000))
                    for entry in group_entries:
                        entry.duration_ms = duration
        return entries


# ========== GANTT GENERATOR ==========
class ImprovedGanttGenerator:
    def generate_gantt_data(self, entries: List[TerraformLogEntry]) -> List[Dict[str, Any]]:
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

            timestamps = [e.timestamp for e in valid_entries]
            start_time = min(timestamps)
            end_time = max(timestamps)
            duration = (end_time - start_time).total_seconds()

            operation = self._detect_group_operation(group_entries)
            resources = list(set(e.tf_resource_type for e in group_entries if e.tf_resource_type))

            gantt_data.append({
                'id': group_key,
                'task': self._format_task_name(operation, resources),
                'start': start_time.isoformat(),
                'end': end_time.isoformat(),
                'resource': ', '.join(resources) if resources else 'General',
                'duration': max(duration, 1),
                'type': operation,
                'entry_count': len(group_entries),
                'resources': resources,
                'raw_duration': duration
            })

        if not gantt_data:
            gantt_data = self._create_time_based_groups(entries)

        return sorted(gantt_data, key=lambda x: x['start'])

    def _format_task_name(self, operation: str, resources: List[str]) -> str:
        if resources:
            resource_str = ', '.join(resources[:5])
            return f"{operation} - {resource_str}"
        return f"{operation} - General"

    def _detect_group_operation(self, entries: List[TerraformLogEntry]) -> str:
        operations = [e.operation.value for e in entries if e.operation != OperationType.UNKNOWN]
        return max(set(operations), key=operations.count) if operations else 'unknown'

    def _create_time_based_groups(self, entries: List[TerraformLogEntry]) -> List[Dict[str, Any]]:
        if not entries:
            return []

        sorted_entries = sorted(entries, key=lambda x: x.timestamp)
        groups = []
        current_group = []
        group_start = sorted_entries[0].timestamp

        for entry in sorted_entries:
            time_diff = (entry.timestamp - group_start).total_seconds()
            if time_diff > 5.0 and current_group:
                groups.append(current_group)
                current_group = [entry]
                group_start = entry.timestamp
            else:
                current_group.append(entry)

        if current_group:
            groups.append(current_group)

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
                    'task': f'{operation} - Time Group {i + 1}',
                    'start': start_time.isoformat(),
                    'end': end_time.isoformat(),
                    'resource': 'Time-based',
                    'duration': duration,
                    'type': operation,
                    'entry_count': len(group),
                    'resources': []
                })

        return gantt_data


# ========== WEBSOCKET MANAGER ==========
class WebSocketManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections[:]:
            try:
                await connection.send_text(message)
            except:
                self.disconnect(connection)


# ========== FASTAPI APP ==========
app = FastAPI(
    title="Terraform LogViewer Pro - Competition Edition",
    description="Professional Terraform log analysis with robust parsing",
    version="7.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

parser = RobustTerraformParser()
gantt_generator = ImprovedGanttGenerator()
websocket_manager = WebSocketManager()
uploaded_logs: List[TerraformLogEntry] = []
raw_uploaded_logs: List[dict] = []


# ========== ENDPOINTS ==========
@app.post("/api/v2/upload")
async def upload_logs_v2(file: UploadFile = File(...)):
    if not file.filename.endswith(('.json', '.log', '.txt')):
        raise HTTPException(400, "Only JSON, log and text files supported")

    try:
        content = (await file.read()).decode('utf-8')
        entries = parser.parse_log_file(content, file.filename)
        uploaded_logs.extend(entries)

        parse_errors = [e for e in entries if e.parse_error]
        operation_stats = {}
        for entry in entries:
            op = entry.operation.value
            operation_stats[op] = operation_stats.get(op, 0) + 1

        resource_types = list(set(e.tf_resource_type for e in entries if e.tf_resource_type))

        await websocket_manager.broadcast(json.dumps({
            "type": "upload",
            "filename": file.filename,
            "entries_count": len(entries),
            "operations": list(operation_stats.keys())
        }))

        return {
            "filename": file.filename,
            "entries_count": len(entries),
            "parse_errors": len(parse_errors),
            "operations": list(operation_stats.keys()),
            "resource_types": resource_types,
            "sample_entries": [e.to_dict() for e in entries[:5]]
        }
    except Exception as e:
        raise HTTPException(500, f"Processing failed: {str(e)}")


@app.get("/api/v2/entries")
async def get_entries_v2(
        operation: Optional[str] = None,
        level: Optional[str] = None,
        resource_type: Optional[str] = None,
        search: Optional[str] = None,
        show_read: bool = True,
        show_parse_errors: bool = True,
        limit: int = Query(100, le=1000)
):
    filtered = uploaded_logs
    if operation and operation != 'all':
        filtered = [e for e in filtered if e.operation.value == operation]
    if level and level != 'all':
        filtered = [e for e in filtered if e.level.value == level]
    if resource_type:
        filtered = [e for e in filtered if e.tf_resource_type == resource_type]
    if search:
        filtered = [e for e in filtered if search.lower() in e.message.lower() or
                    search.lower() in str(e.tf_rpc).lower()]
    if not show_read:
        filtered = [e for e in filtered if not e.read]
    if not show_parse_errors:
        filtered = [e for e in filtered if not e.parse_error]

    return [e.to_dict() for e in filtered[:limit]]


@app.get("/api/v2/filter/keys")
async def get_logs_keys():
    return sorted(set().union(*raw_uploaded_logs))


@app.post("/api/v2/filter")
async def filter_raw_logs(data: Dict[str, str]):
    logs = raw_uploaded_logs

    def filter_local(log_row: Dict[str, str]) -> bool:
        take = True
        for key in data:
            if key not in log_row:
                return False

            if data[key] not in log_row[key]:
                return False

        return True

    return list(filter(filter_local, logs))


@app.get("/api/v2/statistics")
async def get_statistics():
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
        op = entry.operation.value
        stats['operations'][op] = stats['operations'].get(op, 0) + 1

        level = entry.level.value
        stats['levels'][level] = stats['levels'].get(level, 0) + 1

        if entry.tf_resource_type:
            stats['resource_types'][entry.tf_resource_type] = stats['resource_types'].get(entry.tf_resource_type, 0) + 1

        if entry.tf_rpc:
            stats['rpc_methods'][entry.tf_rpc] = stats['rpc_methods'].get(entry.tf_rpc, 0) + 1

        stats['json_blocks_count'] += len(entry.json_blocks)

        if entry.parse_error and entry.error_type:
            stats['error_types'][entry.error_type] = stats['error_types'].get(entry.error_type, 0) + 1

    return stats


@app.get("/api/v2/gantt-data")
async def get_gantt_data():
    gantt_data = gantt_generator.generate_gantt_data(uploaded_logs)
    return {"gantt_data": gantt_data}


@app.post("/api/v2/entries/{entry_id}/read")
async def mark_as_read(entry_id: str):
    for entry in uploaded_logs:
        if entry.id == entry_id:
            entry.read = True
            return {"status": "marked as read"}
    raise HTTPException(404, "Entry not found")


# ========== EXPORT ENDPOINTS ==========
@app.get("/api/export/json")
async def export_json(
        operation: Optional[str] = None,
        level: Optional[str] = None,
        resource_type: Optional[str] = None
):
    filtered = uploaded_logs
    if operation:
        filtered = [e for e in filtered if e.operation.value == operation]
    if level:
        filtered = [e for e in filtered if e.level.value == level]
    if resource_type:
        filtered = [e for e in filtered if e.tf_resource_type == resource_type]

    return [e.to_dict() for e in filtered]


@app.get("/api/export/csv")
async def export_csv(
        operation: Optional[str] = None,
        level: Optional[str] = None,
        resource_type: Optional[str] = None
):
    filtered = uploaded_logs
    if operation:
        filtered = [e for e in filtered if e.operation.value == operation]
    if level:
        filtered = [e for e in filtered if e.level.value == level]
    if resource_type:
        filtered = [e for e in filtered if e.tf_resource_type == resource_type]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=['id', 'timestamp', 'level', 'operation', 'message', 'tf_req_id',
                                                'tf_resource_type', 'tf_rpc'])
    writer.writeheader()

    for entry in filtered:
        writer.writerow({
            'id': entry.id,
            'timestamp': entry.timestamp.isoformat(),
            'level': entry.level.value,
            'operation': entry.operation.value,
            'message': entry.message,
            'tf_req_id': entry.tf_req_id or '',
            'tf_resource_type': entry.tf_resource_type or '',
            'tf_rpc': entry.tf_rpc or ''
        })

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=terraform_logs.csv"}
    )


# ========== GRPC DEMO ENDPOINTS ==========
@app.get("/api/grpc/status")
async def grpc_status():
    return {"status": "gRPC plugin system operational", "plugins": ["error_detector", "performance_analyzer"]}


@app.post("/api/grpc/process")
async def grpc_process():
    error_count = len([e for e in uploaded_logs if e.level == LogLevel.ERROR])
    return {"processed_entries": len(uploaded_logs), "errors_found": error_count}


# ========== WEBSOCKET ==========
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket_manager.broadcast(f"Echo: {data}")
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "Terraform LogViewer Pro",
        "version": "7.0.0",
        "timestamp": datetime.now().isoformat(),
        "statistics": {
            "total_logs": len(uploaded_logs),
            "parse_errors": len([e for e in uploaded_logs if e.parse_error])
        }
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
