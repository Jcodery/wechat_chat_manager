"""
Contacts routes for the WeChat Chat Manager API.

Provides endpoints for:
- List contacts from WeChat database
- List chatrooms from WeChat database
- List extracted (hidden) contacts from encrypted storage
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List

from wechat_manager.core import wechat_dir, key_extractor
from wechat_manager.core.db_handler import WeChatDBHandler
from wechat_manager.core.decrypt import DecryptionError, InvalidKeyError
from wechat_manager.core.storage import EncryptedStorage
from wechat_manager.api.routes.dependencies import get_db_handler, get_storage


router = APIRouter()


class ContactResponse(BaseModel):
    """Response model for a contact"""

    id: str
    username: str
    nickname: Optional[str] = None
    alias: Optional[str] = None
    remark: Optional[str] = None
    contact_type: int = 0
    hidden_at: Optional[int] = None


class ChatRoomResponse(BaseModel):
    """Response model for a chatroom"""

    name: str
    members: List[str]
    nickname: Optional[str] = None


class ContactListResponse(BaseModel):
    """Response model for contact list"""

    contacts: List[ContactResponse]
    count: int


class ChatRoomListResponse(BaseModel):
    """Response model for chatroom list"""

    chatrooms: List[ChatRoomResponse]
    count: int


@router.get("/", response_model=ContactListResponse)
async def list_contacts(db_handler: WeChatDBHandler = Depends(get_db_handler)):
    """Get contacts from WeChat database"""
    try:
        contacts = db_handler.get_contacts()
        return {
            "contacts": [
                {
                    "id": c.id,
                    "username": c.username,
                    "nickname": c.nickname,
                    "alias": c.alias,
                    "remark": c.remark,
                    "contact_type": c.contact_type,
                }
                for c in contacts
            ],
            "count": len(contacts),
        }
    except (InvalidKeyError, DecryptionError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Failed to get contacts: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get contacts: {str(e)}")


@router.get("/chatrooms", response_model=ChatRoomListResponse)
async def list_chatrooms(db_handler: WeChatDBHandler = Depends(get_db_handler)):
    """Get chatrooms from WeChat database"""
    try:
        chatrooms = db_handler.get_chatrooms()
        return {
            "chatrooms": [
                {
                    "name": c.name,
                    "members": c.members,
                    "nickname": c.nickname,
                }
                for c in chatrooms
            ],
            "count": len(chatrooms),
        }
    except (InvalidKeyError, DecryptionError, ValueError) as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to get chatrooms: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get chatrooms: {str(e)}"
        )


@router.get("/extracted", response_model=ContactListResponse)
async def list_extracted(storage: EncryptedStorage = Depends(get_storage)):
    """List extracted (hidden) contacts from encrypted storage"""
    try:
        contacts = storage.list_contacts()
        return {
            "contacts": [
                {
                    "id": c.id,
                    "username": c.username,
                    "nickname": c.nickname,
                    "remark": c.remark,
                    "contact_type": c.contact_type,
                    "hidden_at": c.hidden_at,
                }
                for c in contacts
            ],
            "count": len(contacts),
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get extracted contacts: {str(e)}"
        )
