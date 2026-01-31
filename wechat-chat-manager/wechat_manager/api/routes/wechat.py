"""
WeChat directory and key management routes.

Provides endpoints for:
- Auto-detect WeChat directory
- Manually set WeChat directory
- Check WeChat running status
- Key extraction and management
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from wechat_manager.core import wechat_dir
from wechat_manager.core import key_extractor


router = APIRouter()


class SetDirRequest(BaseModel):
    """Request model for setting WeChat directory"""

    path: str


class ManualKeyRequest(BaseModel):
    """Request model for setting key manually"""

    key: str


class WeChatDirResponse(BaseModel):
    """Response model for WeChat directory operations"""

    success: bool
    path: Optional[str] = None
    message: str
    wxid_folders: Optional[List[str]] = None


class WeChatStatusResponse(BaseModel):
    """Response model for WeChat status"""

    running: bool


class KeyStatusResponse(BaseModel):
    """Response model for key status"""

    is_saved: bool


class KeyResponse(BaseModel):
    """Response model for key operations"""

    success: bool
    message: str


@router.get("/detect", response_model=WeChatDirResponse)
async def detect_wechat_dir():
    """Auto-detect WeChat directory"""
    detected_path = wechat_dir.auto_detect_wechat_dir()

    if detected_path:
        # Also set it as current
        wechat_dir.set_wechat_dir(detected_path)
        wxid_folders = wechat_dir.get_wxid_folders(detected_path)
        return {
            "success": True,
            "path": detected_path,
            "message": "WeChat directory detected successfully",
            "wxid_folders": wxid_folders,
        }
    else:
        return {
            "success": False,
            "path": None,
            "message": "Could not auto-detect WeChat directory. Please set it manually.",
            "wxid_folders": None,
        }


@router.post("/set-dir", response_model=WeChatDirResponse)
async def set_wechat_directory(req: SetDirRequest):
    """Manually set WeChat directory"""
    if not req.path:
        raise HTTPException(status_code=400, detail="Path is required")

    if wechat_dir.set_wechat_dir(req.path):
        wxid_folders = wechat_dir.get_wxid_folders(req.path)
        return {
            "success": True,
            "path": req.path,
            "message": "WeChat directory set successfully",
            "wxid_folders": wxid_folders,
        }
    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid WeChat directory. Make sure it contains wxid_* folders with Msg subdirectory.",
        )


@router.get("/current-dir", response_model=WeChatDirResponse)
async def get_current_wechat_dir():
    """Get currently configured WeChat directory"""
    current = wechat_dir.get_current_wechat_dir()

    if current:
        wxid_folders = wechat_dir.get_wxid_folders(current)
        return {
            "success": True,
            "path": current,
            "message": "Current WeChat directory",
            "wxid_folders": wxid_folders,
        }
    else:
        return {
            "success": False,
            "path": None,
            "message": "WeChat directory not set",
            "wxid_folders": None,
        }


@router.get("/status", response_model=WeChatStatusResponse)
async def wechat_status():
    """Check if WeChat is running"""
    return {"running": key_extractor.is_wechat_running()}


@router.get("/key/status", response_model=KeyStatusResponse)
async def key_status():
    """Check if key is saved in keyring"""
    key = key_extractor.get_key_from_keyring()
    return {"is_saved": key is not None}


@router.post("/key/extract", response_model=KeyResponse)
async def extract_key():
    """Extract key from WeChat process memory"""
    try:
        key = key_extractor.extract_key_from_memory()

        if key:
            # Save to keyring
            key_extractor.save_key_to_keyring(key)
            return {
                "success": True,
                "message": "Key extracted and saved successfully",
            }
        else:
            return {
                "success": False,
                "message": "Could not extract key from memory",
            }
    except key_extractor.WeChatNotRunningError:
        raise HTTPException(
            status_code=400, detail="WeChat is not running. Please start WeChat first."
        )
    except key_extractor.KeyExtractionError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/key/manual", response_model=KeyResponse)
async def set_manual_key(req: ManualKeyRequest):
    """Set key manually"""
    try:
        key_extractor.set_manual_key(req.key)
        return {
            "success": True,
            "message": "Key set successfully",
        }
    except key_extractor.InvalidKeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
