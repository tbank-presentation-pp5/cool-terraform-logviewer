from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
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
    operation: OperationType = OperationType.UNKNOWN
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    parent_req_id: Optional[str] = None
    duration_ms: Optional[int] = None

    class Config:
        use_enum_values = True

class LogGroup(BaseModel):
    tf_req_id: str
    entries: List[TerraformLogEntry]
    operation: OperationType
    start_time: datetime
    end_time: Optional[datetime] = None
    resource_types: List[str] = []
    status: str = "unknown"

class UploadResponse(BaseModel):
    filename: str
    entries_count: int
    operations: List[str]
    resource_types: List[str] = []
    data_source_types: List[str] = []
    sample_entries: List[Dict[str, Any]]
