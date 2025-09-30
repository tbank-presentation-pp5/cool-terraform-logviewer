import grpc
from concurrent import futures
import logging
import json
from datetime import datetime

# Генерируемые файлы из .proto
import plugin_pb2
import plugin_pb2_grpc

class WorkingLogProcessorServicer(plugin_pb2_grpc.LogProcessorServicer):
    """Работающий gRPC плагин для фильтрации ошибок"""
    
    def ProcessLogs(self, request, context):
        processed_entries = []
        error_count = 0
        
        for entry in request.entries:
            # Простая логика фильтрации: помечаем ошибки и предупреждения
            processed_entry = plugin_pb2.LogEntry()
            processed_entry.CopyFrom(entry)
            
            # Добавляем метаданные
            processed_entry.metadata['processed_by'] = 'error_filter_plugin'
            processed_entry.metadata['processed_at'] = datetime.now().isoformat()
            
            # Логика фильтрации
            if 'error' in entry.message.lower():
                processed_entry.metadata['priority'] = 'high'
                processed_entry.message = f"🚨 ERROR: {entry.message}"
                error_count += 1
            elif 'warn' in entry.message.lower():
                processed_entry.metadata['priority'] = 'medium' 
                processed_entry.message = f"⚠️ WARN: {entry.message}"
            else:
                processed_entry.metadata['priority'] = 'low'
                
            processed_entries.append(processed_entry)
        
        return plugin_pb2.ProcessLogsResponse(
            entries=processed_entries,
            statistics={
                'total_processed': str(len(processed_entries)),
                'errors_found': str(error_count),
                'plugin_version': '1.0.0'
            }
        )

    def GetCapabilities(self, request, context):
        return plugin_pb2.GetCapabilitiesResponse(
            capabilities=['error_filtering', 'priority_tagging', 'metadata_enrichment'],
            version='1.0.0'
        )

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    plugin_pb2_grpc.add_LogProcessorServicer_to_server(WorkingLogProcessorServicer(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("✅ Working gRPC plugin running on port 50051")
    server.wait_for_termination()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    serve()