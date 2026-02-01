"""
Mode A routes - Safe read-only extraction.

Provides endpoints for:
- Extract chats to encrypted storage (read-only, source not modified)
- Get extracted messages for a contact
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List

from wechat_manager.core.db_handler import WeChatDBHandler
from wechat_manager.core.storage import EncryptedStorage
from wechat_manager.core.mode_a import ModeA
from wechat_manager.api.routes.dependencies import get_db_handler, get_storage


router = APIRouter()


class ExtractRequest(BaseModel):
    """Request model for extracting chats"""

    contact_ids: List[str]


class MessageResponse(BaseModel):
    """Response model for a message"""

    id: Optional[int] = None
    contact_id: str
    content: str
    create_time: int
    is_sender: bool
    msg_type: int = 1


class ExtractResultItem(BaseModel):
    """Response model for a single extraction result"""

    contact_id: str
    message_count: int
    success: bool
    error: Optional[str] = None


class ExtractResponse(BaseModel):
    """Response model for extraction"""

    results: List[ExtractResultItem]
    total_extracted: int
    success_count: int
    failure_count: int


class MessagesResponse(BaseModel):
    """Response model for messages list"""

    messages: List[MessageResponse]
    count: int
    contact_id: str


class DeleteMessageResponse(BaseModel):
    """Response model for deleting a single message"""

    deleted: bool


class SyncResponse(BaseModel):
    """Response model for sync"""

    contact_id: str
    new_messages: int
    success: bool
    error: Optional[str] = None


def get_mode_a(
    db_handler: WeChatDBHandler = Depends(get_db_handler),
    storage: EncryptedStorage = Depends(get_storage),
) -> ModeA:
    """Get ModeA instance with injected dependencies"""
    return ModeA(db_handler, storage)


@router.post("/extract", response_model=ExtractResponse)
async def extract_chats(
    req: ExtractRequest,
    mode_a: ModeA = Depends(get_mode_a),
):
    """Extract chats to encrypted storage (safe, read-only)"""
    if not req.contact_ids:
        raise HTTPException(status_code=400, detail="No contact_ids provided")

    results = mode_a.extract_multiple(req.contact_ids)

    success_count = sum(1 for r in results if r["success"])
    failure_count = len(results) - success_count
    total_extracted = sum(r["message_count"] for r in results if r["success"])

    return {
        "results": [
            {
                "contact_id": r["contact_id"],
                "message_count": r["message_count"],
                "success": r["success"],
                "error": r.get("error"),
            }
            for r in results
        ],
        "total_extracted": total_extracted,
        "success_count": success_count,
        "failure_count": failure_count,
    }


@router.get("/messages/{contact_id}", response_model=MessagesResponse)
async def get_extracted_messages(
    contact_id: str,
    limit: int = 100,
    mode_a: ModeA = Depends(get_mode_a),
):
    """Get extracted messages for a contact from encrypted storage"""
    messages = mode_a.get_extracted_messages(contact_id, limit)

    return {
        "messages": [
            {
                "id": m.id,
                "contact_id": m.contact_id,
                "content": m.content,
                "create_time": m.create_time,
                "is_sender": m.is_sender,
                "msg_type": m.msg_type,
            }
            for m in messages
        ],
        "count": len(messages),
        "contact_id": contact_id,
    }


@router.delete(
    "/messages/{contact_id}/{message_id}", response_model=DeleteMessageResponse
)
async def delete_extracted_message(
    contact_id: str,
    message_id: int,
    storage: EncryptedStorage = Depends(get_storage),
):
    """Delete a single extracted message from local storage"""
    if message_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid message_id")

    deleted = storage.delete_message(contact_id, message_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Message not found")

    return {"deleted": True}


@router.post("/sync/{contact_id}", response_model=SyncResponse)
async def sync_messages(
    contact_id: str,
    mode_a: ModeA = Depends(get_mode_a),
):
    """Sync new messages for a contact into local storage"""
    result = mode_a.sync_contact(contact_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Sync failed"))
    return result


@router.get("/check/{contact_id}")
async def check_extracted(
    contact_id: str,
    mode_a: ModeA = Depends(get_mode_a),
):
    """Check if a contact has already been extracted"""
    is_extracted = mode_a.is_contact_extracted(contact_id)
    return {
        "contact_id": contact_id,
        "is_extracted": is_extracted,
    }
