import grpc
from concurrent import futures
import logging
import re

# Импорты для gRPC (в реальном проекте сгенерированы из .proto)
# from backend.grpc import plugin_pb2
# from backend.grpc import plugin_pb2_grpc

# Заглушки для демонстрации
class plugin_pb2:
    class LogEntry:
        pass
    class ProcessLogsRequest:
        pass
    class ProcessLogsResponse:
        pass
    class GetCapabilitiesRequest:
        pass
    class GetCapabilitiesResponse:
        pass

class plugin_pb2_grpc:
    class LogProcessorServicer:
        pass

class ErrorDetectorServicer(plugin_pb2_grpc.LogProcessorServicer):
    def __init__(self):
        self.error_patterns = [
            r'error|failed|failure',
            r'panic',
            r'timeout',
            r'denied',
            r'unauthorized',
            r'not found',
            r'invalid',
            r'cannot'
        ]

    def ProcessLogs(self, request, context):
        print("Error Detector: Processing logs...")
        
        # В реальной реализации здесь была бы обработка через gRPC
        # Для демо просто возвращаем успех
        return plugin_pb2.ProcessLogsResponse(
            entries=[],
            statistics={'processed': 'true', 'plugin': 'error_detector'}
        )

    def GetCapabilities(self, request, context):
        return plugin_pb2.GetCapabilitiesResponse(
            capabilities=['error_detection', 'severity_analysis'],
            version='1.0.0'
        )

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    plugin_pb2_grpc.add_LogProcessorServicer_to_server(ErrorDetectorServicer(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("Error Detector plugin running on port 50051")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()