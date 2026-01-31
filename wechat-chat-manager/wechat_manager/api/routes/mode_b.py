"""
Mode B routes - Convenient mode with backup/delete/restore.

Provides endpoints for:
- Run pre-flight checks
- Create backup
- Hide messages (extract + delete from source)
- Restore messages
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict

from wechat_manager.core.db_handler import WeChatDBHandler
from wechat_manager.core.storage import EncryptedStorage
from wechat_manager.core.mode_b import ModeB, PreFlightError, BackupError
from wechat_manager.api.routes.dependencies import (
    get_db_handler,
    get_storage,
    get_backup_path,
)


router = APIRouter()


class HideRequest(BaseModel):
    """Request model for hiding messages"""

    contact_id: str
    dry_run: bool = False


class RestoreRequest(BaseModel):
    """Request model for restoring messages"""

    contact_id: str
    dry_run: bool = False


class PreFlightResponse(BaseModel):
    """Response model for pre-flight check"""

    all_passed: bool
    checks: Dict[str, bool]
    message: str


class BackupResponse(BaseModel):
    """Response model for backup operation"""

    success: bool
    backup_path: Optional[str] = None
    message: str


class HideResponse(BaseModel):
    """Response model for hide operation"""

    extracted: int
    deleted: int
    dry_run: bool
    message: str


class RestoreResponse(BaseModel):
    """Response model for restore operation"""

    restored: int
    dry_run: bool
    message: str


def get_mode_b(
    db_handler: WeChatDBHandler = Depends(get_db_handler),
    storage: EncryptedStorage = Depends(get_storage),
) -> ModeB:
    """Get ModeB instance with injected dependencies"""
    backup_path = get_backup_path()
    return ModeB(db_handler, storage, backup_path)


@router.get("/preflight", response_model=PreFlightResponse)
async def preflight_check(mode_b: ModeB = Depends(get_mode_b)):
    """Run pre-flight checks for Mode B operations"""
    all_passed, checks = mode_b.pre_flight_check()

    if all_passed:
        message = "All pre-flight checks passed. Safe to proceed."
    else:
        failed = [k for k, v in checks.items() if not v]
        message = f"Pre-flight checks failed: {', '.join(failed)}"

    return {
        "all_passed": all_passed,
        "checks": checks,
        "message": message,
    }


@router.post("/backup", response_model=BackupResponse)
async def create_backup(mode_b: ModeB = Depends(get_mode_b)):
    """Create backup of WeChat Msg directory"""
    try:
        backup_path = mode_b.create_backup()

        # Verify the backup
        if mode_b.verify_backup(backup_path):
            return {
                "success": True,
                "backup_path": backup_path,
                "message": "Backup created and verified successfully",
            }
        else:
            return {
                "success": False,
                "backup_path": backup_path,
                "message": "Backup created but verification failed",
            }
    except BackupError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hide", response_model=HideResponse)
async def hide_messages(
    req: HideRequest,
    mode_b: ModeB = Depends(get_mode_b),
):
    """Hide messages: extract to encrypted storage, then delete from source"""
    try:
        result = mode_b.hide_messages(req.contact_id, dry_run=req.dry_run)

        if req.dry_run:
            message = f"Dry run: Would extract {result['extracted']} messages"
        else:
            message = f"Extracted {result['extracted']} messages, deleted {result['deleted']} from source"

        return {
            "extracted": result["extracted"],
            "deleted": result["deleted"],
            "dry_run": result["dry_run"],
            "message": message,
        }
    except PreFlightError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except BackupError as e:
        raise HTTPException(status_code=500, detail=f"Backup error: {str(e)}")


@router.post("/restore", response_model=RestoreResponse)
async def restore_messages(
    req: RestoreRequest,
    mode_b: ModeB = Depends(get_mode_b),
):
    """Restore messages from encrypted storage back to WeChat database"""
    try:
        result = mode_b.restore_messages(req.contact_id, dry_run=req.dry_run)

        if req.dry_run:
            message = f"Dry run: Would restore {result['restored']} messages"
        else:
            message = f"Restored {result['restored']} messages to WeChat database"

        return {
            "restored": result["restored"],
            "dry_run": result["dry_run"],
            "message": message,
        }
    except PreFlightError as e:
        raise HTTPException(status_code=400, detail=str(e))
