"""
Export routes for the WeChat Chat Manager API.

Provides endpoints for:
- Export chat to TXT file
- Export multiple chats
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List
from pathlib import Path

from wechat_manager.core.storage import EncryptedStorage
from wechat_manager.core.export import ExportService
from wechat_manager.api.routes.dependencies import get_storage, get_export_path


router = APIRouter()


class ExportMultipleRequest(BaseModel):
    """Request model for exporting multiple contacts"""

    contact_ids: List[str]


class ExportResponse(BaseModel):
    """Response model for export"""

    success: bool
    file_path: str
    message: str


class ExportMultipleResponse(BaseModel):
    """Response model for multiple exports"""

    success: bool
    file_paths: List[str]
    count: int
    message: str


def get_export_service(
    storage: EncryptedStorage = Depends(get_storage),
) -> ExportService:
    """Get ExportService instance"""
    export_path = get_export_path()
    return ExportService(storage, export_path)


@router.get("/{contact_id}", response_model=ExportResponse)
async def export_chat(
    contact_id: str,
    format: str = "txt",
    export_service: ExportService = Depends(get_export_service),
):
    """Export chat to file"""
    if format != "txt":
        raise HTTPException(
            status_code=400, detail="Currently only TXT format is supported"
        )

    try:
        file_path = export_service.export_to_txt(contact_id)
        return {
            "success": True,
            "file_path": file_path,
            "message": f"Chat exported successfully to {file_path}",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/{contact_id}/download")
async def download_export(
    contact_id: str,
    format: str = "txt",
    export_service: ExportService = Depends(get_export_service),
):
    """Export chat and download the file"""
    if format != "txt":
        raise HTTPException(
            status_code=400, detail="Currently only TXT format is supported"
        )

    try:
        file_path = export_service.export_to_txt(contact_id)
        filename = Path(file_path).name
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="text/plain; charset=utf-8",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.post("/multiple", response_model=ExportMultipleResponse)
async def export_multiple(
    req: ExportMultipleRequest,
    export_service: ExportService = Depends(get_export_service),
):
    """Export multiple contacts to files"""
    if not req.contact_ids:
        raise HTTPException(status_code=400, detail="No contact_ids provided")

    try:
        file_paths = export_service.export_multiple(req.contact_ids)
        return {
            "success": True,
            "file_paths": file_paths,
            "count": len(file_paths),
            "message": f"Successfully exported {len(file_paths)} chats",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
