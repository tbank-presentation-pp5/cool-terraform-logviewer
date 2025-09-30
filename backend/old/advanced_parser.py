import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from .models import TerraformLogEntry, OperationType, LogLevel

class AdvancedTerraformParser:
    def __init__(self):
        self.plan_patterns = [
            r'terraform.*plan',
            r'plan.*operation',
            r'PlanResourceChange',
            r'planned.*action',
            r'refresh.*plan'
        ]
        
        self.apply_patterns = [
            r'terraform.*apply', 
            r'apply.*operation',
            r'ApplyResourceChange',
            r'applying.*configuration',
            r'create.*resource'
        ]
        
        self.json_pattern = r'(\{.*?\})'  # Базовый паттерн для JSON

    def parse_line(self, line: str, line_num: int) -> Optional[TerraformLogEntry]:
        try:
            data = json.loads(line)
            
            # Эвристики для определения операции
            operation = self._heuristic_detect_operation(data)
            
            # Извлечение JSON блоков из сообщений
            json_blocks = self._extract_json_blocks(data.get('@message', ''))
            
            # Эвристики для временных меток и уровней
            timestamp = self._heuristic_parse_timestamp(data)
            level = self._heuristic_detect_level(data)
            
            # Извлечение tf_req_id через эвристики
            tf_req_id = self._heuristic_find_req_id(data)
            
            entry = TerraformLogEntry(
                id=f"{timestamp.timestamp()}-{line_num}",
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
                json_blocks=json_blocks  # Новое поле для JSON блоков
            )
            
            return entry
            
        except Exception as e:
            print(f"Advanced parse error line {line_num}: {e}")
            return None

    def _heuristic_detect_operation(self, data: Dict) -> OperationType:
        message = data.get('@message', '').lower()
        tf_rpc = data.get('tf_rpc', '')
        
        # Проверяем RPC методы
        if 'PlanResourceChange' in tf_rpc:
            return OperationType.PLAN
        elif 'ApplyResourceChange' in tf_rpc:
            return OperationType.APPLY
        elif any(keyword in tf_rpc for keyword in ['Validate', 'GetProvider']):
            return OperationType.VALIDATE
        
        # Эвристики по тексту сообщения
        if any(re.search(pattern, message, re.IGNORECASE) for pattern in self.plan_patterns):
            return OperationType.PLAN
        elif any(re.search(pattern, message, re.IGNORECASE) for pattern in self.apply_patterns):
            return OperationType.APPLY
            
        return OperationType.UNKNOWN

    def _heuristic_parse_timestamp(self, data: Dict) -> datetime:
        # Пытаемся найти timestamp в разных местах
        timestamp_str = data.get('@timestamp') or data.get('timestamp') or data.get('time')
        
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
                return datetime.fromisoformat(timestamp_match.group().replace(' ', 'T'))
            except:
                pass
                
        return datetime.now()

    def _heuristic_detect_level(self, data: Dict) -> LogLevel:
        level_str = data.get('@level')
        if level_str:
            try:
                return LogLevel(level_str.lower())
            except:
                pass
        
        # Эвристики по тексту сообщения
        message = data.get('@message', '').lower()
        if any(word in message for word in ['error', 'failed', 'failure']):
            return LogLevel.ERROR
        elif any(word in message for word in ['warn', 'warning']):
            return LogLevel.WARN
        elif any(word in message for word in ['info', 'information']):
            return LogLevel.INFO
        elif any(word in message for word in ['debug']):
            return LogLevel.DEBUG
            
        return LogLevel.INFO

    def _heuristic_find_req_id(self, data: Dict) -> Optional[str]:
        # Ищем tf_req_id в разных местах
        req_id = data.get('tf_req_id')
        if req_id:
            return req_id
            
        # Эвристика: ищем в сообщении
        message = data.get('@message', '')
        req_match = re.search(r'req[_\-]?id[=:\s]+([a-f0-9\-]+)', message, re.IGNORECASE)
        if req_match:
            return req_match.group(1)
            
        return None

    def _extract_json_blocks(self, message: str) -> List[Dict]:
        """Извлекает JSON блоки из сообщения"""
        json_blocks = []
        
        try:
            # Пытаемся найти JSON в полях tf_http_req_body и tf_http_res_body
            req_body_match = re.search(r'tf_http_req_body[=:\s]+(\{.*?\})', message)
            res_body_match = re.search(r'tf_http_res_body[=:\s]+(\{.*?\})', message)
            
            if req_body_match:
                json_blocks.append({
                    'type': 'request_body',
                    'data': json.loads(req_body_match.group(1)),
                    'expanded': False
                })
                
            if res_body_match:
                json_blocks.append({
                    'type': 'response_body', 
                    'data': json.loads(res_body_match.group(1)),
                    'expanded': False
                })
                
        except json.JSONDecodeError:
            # Если не удалось распарсить, оставляем как текст
            pass
            
        return json_blocks