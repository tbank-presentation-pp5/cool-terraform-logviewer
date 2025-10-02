import csv
import hashlib
import io
import json
import re
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any, Union

import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

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


def normalize(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [s.strip() for s in value.split(',') if s.strip()]
    if isinstance(value, list):
        return [str(s).strip() for s in value if s is not None]
    raise TypeError('Invalid type')


class TerraformLogEntry(BaseModel):
    id: Optional[str] = None
    timestamp: datetime
    level: LogLevel
    message: str
    module: Optional[str] = None
    
    # Все требуемые поля
    caller: Optional[str] = None
    Accept: Optional[str] = None
    Accept_Encoding: Optional[str] = None
    Access_Control_Expose_Headers: Optional[str] = None
    Cache_Control: Union[str, List[str]] = None
    Connection: Optional[str] = None
    Content_Length: Optional[str] = None
    Content_Security_Policy: Optional[str] = None
    Content_Type: Optional[str] = None
    Date: Optional[str] = None
    EXTRA_VALUE_AT_END: Optional[str] = None
    Etag: Optional[str] = None
    Expires: Optional[str] = None
    Host: Optional[str] = None
    Keep_Alive: Optional[str] = None
    Permissions_Policy: Optional[str] = None
    Pragma: Optional[str] = None
    Referrer_Policy: Optional[str] = None
    Server: Optional[str] = None
    Set_Cookie: Optional[str] = None
    Strict_Transport_Security: Optional[str] = None
    User_Agent: Optional[str] = None
    Vary: Union[str, List[str]] = None
    Via: Optional[str] = None
    X_Content_Type_Options: Optional[str] = None
    X_Frame_Options: Optional[str] = None
    X_Kong_Proxy_Latency: Optional[str] = None
    X_Kong_Upstream_Latency: Optional[str] = None
    X_Request_Id: Optional[str] = None
    X_Runtime: Optional[str] = None
    address: Optional[str] = None
    args: List[str] = None
    channel: Optional[str] = None
    description: Optional[str] = None
    diagnostic_attribute: Optional[str] = None
    diagnostic_detail: Optional[str] = None
    diagnostic_error_count: int = None
    diagnostic_severity: Optional[str] = None
    diagnostic_summary: Optional[str] = None
    diagnostic_warning_count: int = None
    err: Optional[str] = None
    len: int = None
    network: Optional[str] = None
    path: Optional[str] = None
    pid: int = None
    plugin: Optional[str] = None
    tf_registry_stdout: Optional[str] = None
    tf_attribute_path: Optional[str] = None
    tf_client_capability_deferral_allowed: bool = None
    tf_client_capability_write_only_attributes_allowed: bool = None
    tf_data_source_type: Optional[str] = None
    tf_http_op_type: Optional[str] = None
    tf_http_req_body: Optional[str] = None
    tf_http_req_method: Optional[str] = None
    tf_http_req_uri: Optional[str] = None
    tf_http_req_version: Optional[str] = None
    tf_http_res_body: Optional[str] = None
    tf_http_res_status_code: int = None
    tf_http_res_status_reason: Optional[str] = None
    tf_http_res_version: Optional[str] = None
    tf_http_trans_id: Optional[str] = None
    tf_proto_version: Optional[str] = None
    tf_provider_addr: Optional[str] = None
    tf_req_duration_ms: int = None
    tf_req_id: Optional[str] = None
    tf_resource_type: Optional[str] = None
    tf_rpc: Optional[str] = None
    tf_server_capability_get_provider_schema_optional: bool = None
    tf_server_capability_move_resource_state: bool = None
    tf_server_capability_plan_destroy: bool = None
    version: int = None
    
    # Существующие технические поля
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

    @field_validator('Cache_Control', mode='before')
    def _norm_cache(cls, v):
        return normalize(v)

    @field_validator('Vary', mode='before')
    def _norm_vary(cls, v):
        return normalize(v)

    # Опционально: гарантировать конечный тип — список строк
    @field_validator('Cache_Control', mode='after')
    def _ensure_cache_list(cls, v):
        return list(v) if isinstance(v, (list, tuple)) else [v]

    @field_validator('Vary', mode='after')
    def _ensure_vary_list(cls, v):
        return list(v) if isinstance(v, (list, tuple)) else [v]


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
        self.last_valid_timestamp = None  # Для обработки записей без timestamp

    def parse_log_file(self, file_content: str, filename: str = "") -> List[TerraformLogEntry]:
        entries = []
        lines = file_content.strip().split('\n')

        for line_num, line in enumerate(lines, 1):
            if line.strip():
                entry = self.parse_line_robust(line, line_num, filename)
                if entry:
                    entries.append(entry)
                    if hasattr(entry, 'raw_data') and isinstance(entry.raw_data, dict):
                        raw_uploaded_logs.append(entry.raw_data)

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
        if timestamp:
            self.last_valid_timestamp = timestamp
        else:
            timestamp = self.last_valid_timestamp or datetime.now()

        level = self._heuristic_detect_level(data, original_line)
        operation = self._heuristic_detect_operation(data, filename, original_line)
        tf_req_id = self._heuristic_find_req_id(data, original_line)
        json_blocks = self._extract_json_blocks(data)

        entry_data = {
            'id': f"{timestamp.timestamp()}-{line_num}-{hashlib.md5(original_line.encode()).hexdigest()[:8]}",
            'timestamp': timestamp,
            'level': level,
            'message': data.get('@message', data.get('message', original_line[:200])),
            'module': data.get('@module', data.get('module')),
            'tf_req_id': tf_req_id,
            'tf_resource_type': data.get('tf_resource_type'),
            'tf_data_source_type': data.get('tf_data_source_type'),
            'tf_rpc': data.get('tf_rpc'),
            'tf_provider_addr': data.get('tf_provider_addr'),
            'operation': operation,
            'raw_data': data,
            'json_blocks': json_blocks,
            'parse_error': parse_error,
            'error_type': error_type
        }

        entry_data2 = entry_data.copy()

        field_mappings = {
            'caller': ['caller', '@caller'],
            'Accept': ['Accept'],
            'Accept_Encoding': ['Accept-Encoding', 'Accept_Encoding'],
            'Access_Control_Expose_Headers': ['Access-Control-Expose-Headers', 'Access_Control_Expose_Headers'],
            'Cache_Control': ['Cache-Control', 'Cache_Control'],
            'Connection': ['Connection'],
            'Content_Length': ['Content-Length', 'Content_Length'],
            'Content_Security_Policy': ['Content-Security-Policy', 'Content_Security_Policy'],
            'Content_Type': ['Content-Type', 'Content_Type'],
            'Date': ['Date'],
            'EXTRA_VALUE_AT_END': ['EXTRA_VALUE_AT_END'],
            'Etag': ['Etag'],
            'Expires': ['Expires'],
            'Host': ['Host'],
            'Keep_Alive': ['Keep-Alive', 'Keep_Alive'],
            'Permissions_Policy': ['Permissions-Policy', 'Permissions_Policy'],
            'Pragma': ['Pragma'],
            'Referrer_Policy': ['Referrer-Policy', 'Referrer_Policy'],
            'Server': ['Server'],
            'Set_Cookie': ['Set-Cookie', 'Set_Cookie'],
            'Strict_Transport_Security': ['Strict-Transport-Security', 'Strict_Transport_Security'],
            'User_Agent': ['User-Agent', 'User_Agent'],
            'Vary': ['Vary'],
            'Via': ['Via'],
            'X_Content_Type_Options': ['X-Content-Type-Options', 'X_Content_Type_Options'],
            'X_Frame_Options': ['X-Frame-Options', 'X_Frame_Options'],
            'X_Kong_Proxy_Latency': ['X-Kong-Proxy-Latency', 'X_Kong_Proxy_Latency'],
            'X_Kong_Upstream_Latency': ['X-Kong-Upstream-Latency', 'X_Kong_Upstream_Latency'],
            'X_Request_Id': ['X-Request-Id', 'X_Request_Id'],
            'X_Runtime': ['X-Runtime', 'X_Runtime'],
            'address': ['address'],
            'args': ['args'],
            'channel': ['channel'],
            'description': ['description'],
            'diagnostic_attribute': ['diagnostic_attribute'],
            'diagnostic_detail': ['diagnostic_detail'],
            'diagnostic_error_count': ['diagnostic_error_count'],
            'diagnostic_severity': ['diagnostic_severity'],
            'diagnostic_summary': ['diagnostic_summary'],
            'diagnostic_warning_count': ['diagnostic_warning_count'],
            'err': ['err'],
            'len': ['len'],
            'network': ['network'],
            'path': ['path'],
            'pid': ['pid'],
            'plugin': ['plugin'],
            'tf_registry_stdout': ['tf-registry.t1.cloud/t1cloud/t1cloud:stdout', 'tf_registry_stdout'],
            'tf_attribute_path': ['tf_attribute_path'],
            'tf_client_capability_deferral_allowed': ['tf_client_capability_deferral_allowed'],
            'tf_client_capability_write_only_attributes_allowed': ['tf_client_capability_write_only_attributes_allowed'],
            'tf_data_source_type': ['tf_data_source_type'],
            'tf_http_op_type': ['tf_http_op_type'],
            'tf_http_req_body': ['tf_http_req_body'],
            'tf_http_req_method': ['tf_http_req_method'],
            'tf_http_req_uri': ['tf_http_req_uri'],
            'tf_http_req_version': ['tf_http_req_version'],
            'tf_http_res_body': ['tf_http_res_body'],
            'tf_http_res_status_code': ['tf_http_res_status_code'],
            'tf_http_res_status_reason': ['tf_http_res_status_reason'],
            'tf_http_res_version': ['tf_http_res_version'],
            'tf_http_trans_id': ['tf_http_trans_id'],
            'tf_proto_version': ['tf_proto_version'],
            'tf_provider_addr': ['tf_provider_addr'],
            'tf_req_duration_ms': ['tf_req_duration_ms'],
            'tf_req_id': ['tf_req_id'],
            'tf_resource_type': ['tf_resource_type'],
            'tf_rpc': ['tf_rpc'],
            'tf_server_capability_get_provider_schema_optional': ['tf_server_capability_get_provider_schema_optional'],
            'tf_server_capability_move_resource_state': ['tf_server_capability_move_resource_state'],
            'tf_server_capability_plan_destroy': ['tf_server_capability_plan_destroy'],
            'version': ['version']
        }

        for model_field, source_fields in field_mappings.items():
            for source_field in source_fields:
                if source_field in data:
                    entry_data[model_field] = data[source_field]
                    break

        try:
            return TerraformLogEntry(**entry_data)
        except Exception as e:
            print(f"Error creating entry: {e}")
            print(f"Entry data keys: {entry_data.keys()}")
            for key, value in entry_data.items():
                print(f"  {key}: {value} (type: {type(value)})")
            return TerraformLogEntry(**entry_data2)

    def _create_error_entry(self, line: str, line_num: int, filename: str, error: str) -> TerraformLogEntry:
        timestamp = self._extract_timestamp_from_line(line)
        if timestamp:
            self.last_valid_timestamp = timestamp
        else:
            timestamp = self.last_valid_timestamp or datetime.now()

        return TerraformLogEntry(
            id=f"error-{timestamp.timestamp()}-{line_num}",
            timestamp=timestamp,
            level=LogLevel.ERROR,
            message=f"PARSE_ERROR: {line}",
            module="LogViewer-parser",
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

    def _heuristic_parse_timestamp(self, data: Dict, original_line: str = "") -> Optional[datetime]:
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
        return extracted_ts

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
    description="""Professional Terraform log analysis with robust parsing.
    
## Features
- Upload and parse Terraform JSON logs
- Filter and search through log entries
- Generate Gantt charts for request flows
- Real-time WebSocket updates
- Export data in JSON and CSV formats
- Full Swagger documentation
    
## API Endpoints
All endpoints are prefixed with `/api/v2/` for versioning.
    
## WebSocket
Connect to `/ws` for real-time updates.""",
    version="7.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "API Support",
        "url": "http://localhost:8000/docs",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    }
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
@app.post(
    "/api/v2/upload",
    summary="Upload Terraform logs",
    description="Upload and parse Terraform JSON log files",
    tags=["Upload"]
)
async def upload_logs_v2(file: UploadFile = File(...)):
    """
    Upload a Terraform log file for analysis.
    
    Supports:
    - JSON log files (.json)
    - Text log files (.log, .txt)
    
    Returns parsing statistics and sample entries.
    """
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


@app.get(
    "/api/v2/entries",
    summary="Get log entries",
    description="Retrieve filtered log entries with various query parameters",
    tags=["Entries"]
)
async def get_entries_v2(
        operation: Optional[str] = Query(None, description="Filter by operation type"),
        level: Optional[str] = Query(None, description="Filter by log level"),
        resource_type: Optional[str] = Query(None, description="Filter by resource type"),
        search: Optional[str] = Query(None, description="Search in message and RPC fields"),
        show_read: bool = Query(True, description="Include read entries"),
        show_parse_errors: bool = Query(True, description="Include parse errors")
):
    """
    Get log entries with advanced filtering.
    
    Parameters:
    - operation: Filter by operation type (plan, apply, validate, unknown)
    - level: Filter by log level (trace, debug, info, warn, error)
    - resource_type: Filter by specific resource type
    - search: Search term in message and RPC fields
    - show_read: Include/exclude read entries
    - show_parse_errors: Include/exclude parse errors
    """
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

    return [e.to_dict() for e in filtered]


@app.get(
    "/api/v2/filter/keys",
    summary="Get filter keys",
    description="Get all unique field keys available for filtering",
    tags=["Filter"]
)
async def get_logs_keys():
    """Return all unique field keys from raw uploaded logs."""
    return sorted(set().union(*raw_uploaded_logs))


@app.get(
    "/api/v2/filter_enh/keys",
    summary="Get enhanced filter keys",
    description="Get all unique non-null fields from both raw and parsed logs",
    tags=["Filter"]
)
async def get_logs_keys_enh():
    """Return all unique non-null fields from both raw and parsed logs."""
    all_non_null_fields = set()
    
    for log in raw_uploaded_logs:
        if isinstance(log, dict):
            for key, value in log.items():
                if value is not None:
                    all_non_null_fields.add(key)
    
    for entry in uploaded_logs:
        entry_dict = entry.model_dump()
        for key, value in entry_dict.items():
            if value is not None:
                all_non_null_fields.add(key)
    
    return sorted(all_non_null_fields)


@app.post(
    "/api/v2/filter",
    summary="Filter raw logs",
    description="Filter raw logs using field-value pairs",
    tags=["Filter"]
)
async def filter_raw_logs(data: Dict[str, str]):
    """
    Filter raw logs with exact field matching.
    
    Request body should be a JSON object with field-value pairs to match.
    Only logs containing all specified field-value pairs will be returned.
    """
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


@app.post(
    "/api/v2/filter_enh",
    summary="Enhanced filter",
    description="Filter logs with enhanced matching using both raw and parsed data",
    tags=["Filter"]
)
async def filter_raw_logs_enh(data: Dict[str, str]):
    """
    Enhanced filtering that searches both raw logs and parsed model fields.
    
    Supports:
    - Field matching in raw log data
    - Special fields: level, operation, message, module
    - Case-insensitive substring matching
    """
    if not data:
        return [entry.to_dict() for entry in uploaded_logs]
    
    matching_indices = []
    
    for idx, raw_log in enumerate(raw_uploaded_logs):
        matches_all_filters = True
        
        for field, filter_value in data.items():
            if field in raw_log:
                field_value = str(raw_log[field])
                if filter_value.lower() not in field_value.lower():
                    matches_all_filters = False
                    break
            elif idx < len(uploaded_logs):
                entry = uploaded_logs[idx]
                if field == 'level' and entry.level.value.lower() != filter_value.lower():
                    matches_all_filters = False
                    break
                elif field == 'operation' and entry.operation.value.lower() != filter_value.lower():
                    matches_all_filters = False
                    break
                elif field == 'message' and filter_value.lower() not in entry.message.lower():
                    matches_all_filters = False
                    break
                elif field == 'module' and entry.module and filter_value.lower() not in entry.module.lower():
                    matches_all_filters = False
                    break
                elif hasattr(entry, field):
                    field_value = str(getattr(entry, field) or '')
                    if filter_value.lower() not in field_value.lower():
                        matches_all_filters = False
                        break
                else:
                    matches_all_filters = False
                    break
            else:
                matches_all_filters = False
                break
        
        if matches_all_filters:
            matching_indices.append(idx)
    
    filtered_entries = []
    for idx in matching_indices:
        if idx < len(uploaded_logs):
            filtered_entries.append(uploaded_logs[idx].to_dict())
    
    return filtered_entries


@app.get(
    "/api/v2/statistics",
    summary="Get statistics",
    description="Get comprehensive statistics about parsed logs",
    tags=["Statistics"]
)
async def get_statistics():
    """
    Return detailed statistics about the uploaded logs.
    
    Includes:
    - Total entries and parse errors
    - Operation type distribution
    - Log level distribution
    - Resource type statistics
    - RPC method usage
    - JSON blocks count
    - Error type breakdown
    """
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


@app.get(
    "/api/v2/gantt-data",
    summary="Get Gantt chart data",
    description="Generate Gantt chart data for request flow visualization",
    tags=["Visualization"]
)
async def get_gantt_data():
    """Generate Gantt chart data showing request flows and durations."""
    gantt_data = gantt_generator.generate_gantt_data(uploaded_logs)
    return {"gantt_data": gantt_data}


@app.post(
    "/api/v2/entries/{entry_id}/read",
    summary="Mark entry as read",
    description="Mark a specific log entry as read",
    tags=["Entries"]
)
async def mark_as_read(entry_id: str):
    """Mark a log entry as read by its ID."""
    for entry in uploaded_logs:
        if entry.id == entry_id:
            entry.read = True
            return {"status": "marked as read"}
    raise HTTPException(404, "Entry not found")


# ========== EXPORT ENDPOINTS ==========
@app.get(
    "/api/export/json",
    summary="Export as JSON",
    description="Export filtered logs as JSON",
    tags=["Export"]
)
async def export_json(
        operation: Optional[str] = Query(None, description="Filter by operation type"),
        level: Optional[str] = Query(None, description="Filter by log level"),
        resource_type: Optional[str] = Query(None, description="Filter by resource type")
):
    """Export filtered log entries in JSON format."""
    filtered = uploaded_logs
    if operation:
        filtered = [e for e in filtered if e.operation.value == operation]
    if level:
        filtered = [e for e in filtered if e.level.value == level]
    if resource_type:
        filtered = [e for e in filtered if e.tf_resource_type == resource_type]

    return [e.to_dict() for e in filtered]


@app.get(
    "/api/export/csv",
    summary="Export as CSV",
    description="Export filtered logs as CSV file",
    tags=["Export"]
)
async def export_csv(
        operation: Optional[str] = Query(None, description="Filter by operation type"),
        level: Optional[str] = Query(None, description="Filter by log level"),
        resource_type: Optional[str] = Query(None, description="Filter by resource type")
):
    """Export filtered log entries as CSV download."""
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
@app.get(
    "/api/grpc/status",
    summary="gRPC status",
    description="Check gRPC plugin system status",
    tags=["gRPC"]
)
async def grpc_status():
    """Check the status of the gRPC plugin system."""
    return {"status": "gRPC plugin system operational", "plugins": ["error_detector", "performance_analyzer"]}


@app.post(
    "/api/grpc/process",
    summary="Process with gRPC",
    description="Process logs using gRPC plugins",
    tags=["gRPC"]
)
async def grpc_process():
    """Process logs through gRPC plugins and return results."""
    error_count = len([e for e in uploaded_logs if e.level == LogLevel.ERROR])
    return {"processed_entries": len(uploaded_logs), "errors_found": error_count}


# ========== WEBSOCKET ==========
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates.
    
    Connect to receive real-time notifications about:
    - New log uploads
    - Processing status
    - System events
    """
    await websocket_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            await websocket_manager.broadcast(f"Echo: {data}")
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket)


@app.get(
    "/api/health",
    summary="Health check",
    description="Check API health status",
    tags=["System"]
)
async def health_check():
    """Check the health status of the API service."""
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


@app.get(
    "/",
    summary="Root endpoint",
    description="API root with basic information",
    tags=["System"]
)
async def root():
    """API root endpoint with basic information and links to documentation."""
    return {
        "message": "Terraform LogViewer Pro API",
        "version": "7.0.0",
        "docs": "/docs",
        "health": "/api/health"
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)