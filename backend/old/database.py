import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any
from contextlib import contextmanager
from .models import TerraformLogEntry, OperationType, LogLevel

class LogDatabase:
    def __init__(self, db_path: str = "terraform_logs.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS log_entries (
                    id TEXT PRIMARY KEY,
                    timestamp DATETIME,
                    level TEXT,
                    message TEXT,
                    module TEXT,
                    tf_req_id TEXT,
                    tf_resource_type TEXT,
                    tf_data_source_type TEXT,
                    tf_rpc TEXT,
                    tf_provider_addr TEXT,
                    operation TEXT,
                    parent_req_id TEXT,
                    duration_ms INTEGER,
                    raw_data TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS request_groups (
                    tf_req_id TEXT PRIMARY KEY,
                    operation TEXT,
                    start_time DATETIME,
                    end_time DATETIME,
                    resource_types TEXT,
                    status TEXT
                )
            ''')
            
            # Создаем индексы для производительности
            conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON log_entries(timestamp)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_tf_req_id ON log_entries(tf_req_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_operation ON log_entries(operation)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_level ON log_entries(level)')

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def save_entries(self, entries: List[TerraformLogEntry]):
        with self._get_connection() as conn:
            for entry in entries:
                conn.execute('''
                    INSERT OR REPLACE INTO log_entries 
                    (id, timestamp, level, message, module, tf_req_id, tf_resource_type, 
                     tf_data_source_type, tf_rpc, tf_provider_addr, operation, parent_req_id, 
                     duration_ms, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    entry.id,
                    entry.timestamp.isoformat(),
                    entry.level.value,
                    entry.message,
                    entry.module,
                    entry.tf_req_id,
                    entry.tf_resource_type,
                    entry.tf_data_source_type,
                    entry.tf_rpc,
                    entry.tf_provider_addr,
                    entry.operation.value,
                    entry.parent_req_id,
                    entry.duration_ms,
                    json.dumps(entry.raw_data)
                ))

    def get_entries(self, filters: Dict[str, Any] = None, limit: int = 1000) -> List[Dict]:
        with self._get_connection() as conn:
            query = "SELECT * FROM log_entries WHERE 1=1"
            params = []
            
            if filters:
                if filters.get('operation'):
                    query += " AND operation = ?"
                    params.append(filters['operation'])
                if filters.get('level'):
                    query += " AND level = ?"
                    params.append(filters['level'])
                if filters.get('resource_type'):
                    query += " AND tf_resource_type = ?"
                    params.append(filters['resource_type'])
                if filters.get('search'):
                    query += " AND (message LIKE ? OR tf_rpc LIKE ?)"
                    params.extend([f"%{filters['search']}%", f"%{filters['search']}%"])
            
            query += " ORDER BY timestamp LIMIT ?"
            params.append(limit)
            
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_gantt_data(self) -> List[Dict]:
        """Данные для диаграммы Ганта"""
        with self._get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    tf_req_id,
                    operation,
                    MIN(timestamp) as start_time,
                    MAX(timestamp) as end_time,
                    GROUP_CONCAT(DISTINCT tf_resource_type) as resources,
                    COUNT(*) as entry_count
                FROM log_entries 
                WHERE tf_req_id IS NOT NULL 
                GROUP BY tf_req_id, operation
                ORDER BY start_time
            ''')
            
            return [dict(row) for row in cursor.fetchall()]

    def _test_connection(self) -> bool:
        """Тестирование соединения с БД"""
        try:
            with self._get_connection() as conn:
                conn.execute("SELECT 1")
            return True
        except:
            return False
