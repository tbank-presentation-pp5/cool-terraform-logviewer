from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Optional
import csv
import io
import json
from .models import TerraformLogEntry

router = APIRouter()

@router.get("/api/export/csv")
async def export_logs_csv(
    operation: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None)
):
    """Экспорт логов в CSV"""
    # Фильтруем логи (используем существующую логику фильтрации)
    filtered_entries = await get_filtered_entries(operation, level, resource_type)
    
    # Создаем CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Заголовки
    writer.writerow([
        'Timestamp', 'Level', 'Operation', 'Resource Type', 
        'RPC Method', 'Message', 'Request ID', 'Provider'
    ])
    
    # Данные
    for entry in filtered_entries:
        writer.writerow([
            entry.timestamp.isoformat(),
            entry.level,
            entry.operation,
            entry.tf_resource_type or '',
            entry.tf_rpc or '',
            entry.message[:200],  # Обрезаем длинные сообщения
            entry.tf_req_id or '',
            entry.tf_provider_addr or ''
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=terraform_logs_export.csv"}
    )

@router.get("/api/export/json")
async def export_logs_json(
    operation: Optional[str] = Query(None),
    level: Optional[str] = Query(None), 
    resource_type: Optional[str] = Query(None)
):
    """Экспорт логов в JSON"""
    filtered_entries = await get_filtered_entries(operation, level, resource_type)
    
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
        "entries": [entry.dict() for entry in filtered_entries]
    }
    
    return export_data