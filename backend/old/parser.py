import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from .models import TerraformLogEntry, OperationType, LogLevel

class EnhancedTerraformParser:
    def __init__(self):
        self.operation_patterns = {
            OperationType.PLAN: [
                'starting Plan operation',
                'backend/local: starting Plan operation',
                'terraform plan'
            ],
            OperationType.APPLY: [
                'starting Apply operation', 
                'backend/local: starting Apply operation',
                'terraform apply'
            ],
            OperationType.VALIDATE: [
                'running validation operation',
                'ValidateDataResourceConfig',
                'ValidateResourceConfig'
            ]
        }
        
        self.rpc_hierarchy = {
            'GetProviderSchema': 'schema',
            'ValidateProviderConfig': 'validation',
            'ValidateDataResourceConfig': 'validation', 
            'ValidateResourceConfig': 'validation',
            'PlanResourceChange': 'plan',
            'ApplyResourceChange': 'apply'
        }

    def parse_log_file(self, file_content: str) -> List[TerraformLogEntry]:
        entries = []
        lines = file_content.strip().split('\n')
        
        for line_num, line in enumerate(lines, 1):
            if line.strip():
                entry = self.parse_line(line, line_num)
                if entry:
                    entries.append(entry)
        
        return self._enhance_with_relationships(entries)

    def parse_line(self, line: str, line_num: int) -> Optional[TerraformLogEntry]:
        try:
            data = json.loads(line)
            
            # Парсинг временной метки
            timestamp = self._parse_timestamp(data.get('@timestamp'))
            if not timestamp:
                return None

            # Определение операции
            operation = self._detect_operation(data)
            
            # Извлечение tf_req_id из разных мест
            tf_req_id = (data.get('tf_req_id') or 
                        data.get('@message', '').split('tf_req_id=')[-1].split()[0] 
                        if 'tf_req_id=' in data.get('@message', '') else None)

            return TerraformLogEntry(
                id=f"{timestamp.timestamp()}-{line_num}",
                timestamp=timestamp,
                level=LogLevel(data.get('@level', 'info')),
                message=data.get('@message', ''),
                module=data.get('@module'),
                tf_req_id=tf_req_id,
                tf_resource_type=data.get('tf_resource_type'),
                tf_data_source_type=data.get('tf_data_source_type'),
                tf_rpc=data.get('tf_rpc'),
                tf_provider_addr=data.get('tf_provider_addr'),
                operation=operation,
                raw_data=data
            )
            
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error parsing line {line_num}: {e}")
            return None

    def _parse_timestamp(self, timestamp_str: str) -> Optional[datetime]:
        if not timestamp_str:
            return None
            
        formats = [
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S%z"
        ]
        
        for fmt in formats:
            try:
                cleaned = timestamp_str.strip().replace(' ', 'T')
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
        
        return None

    def _detect_operation(self, data: Dict[str, Any]) -> OperationType:
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

        # Проверяем паттерны в сообщениях
        for op_type, patterns in self.operation_patterns.items():
            if any(pattern.lower() in message for pattern in patterns):
                return op_type

        return OperationType.UNKNOWN

    def _enhance_with_relationships(self, entries: List[TerraformLogEntry]) -> List[TerraformLogEntry]:
        """Добавляем информацию о родительских запросах и длительности"""
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
