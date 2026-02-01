"""
WeChat directory and key management routes.

Provides endpoints for:
- Auto-detect WeChat directory
- Manually set WeChat directory
- Check WeChat running status
- Key extraction and management
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from wechat_manager.core.config import load_config, set_active_wxid, set_root_path
from wechat_manager.core import wechat_dir
from wechat_manager.core import key_extractor
from wechat_manager.core.decrypt import verify_key


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


class AccountInfo(BaseModel):
    wxid: str
    path: str
    version: Optional[int] = None
    is_active: bool = False


class AccountListResponse(BaseModel):
    accounts: List[AccountInfo]
    active_account: Optional[str] = None


class SetActiveAccountRequest(BaseModel):
    wxid: str


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
    cfg = load_config()

    # Prefer persisted custom path
    if cfg.root_path and wechat_dir.validate_wechat_dir(cfg.root_path):
        wechat_dir.set_wechat_dir(cfg.root_path)
        wxid_folders = wechat_dir.get_wxid_folders(cfg.root_path)
        return {
            "success": True,
            "path": cfg.root_path,
            "message": "Using saved WeChat directory",
            "wxid_folders": wxid_folders,
        }

    detected_path = wechat_dir.auto_detect_wechat_dir()

    if detected_path:
        # Also set it as current
        wechat_dir.set_wechat_dir(detected_path)
        set_root_path(detected_path)
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

    input_path = Path(req.path)
    wxid_dir: Optional[Path] = None
    for p in [input_path, *input_path.parents]:
        if p.name.startswith("wxid_"):
            wxid_dir = p
            break

    root_path = str(wxid_dir.parent) if wxid_dir is not None else str(input_path)
    requested_wxid = wxid_dir.name if wxid_dir is not None else None

    if not wechat_dir.set_wechat_dir(root_path):
        raise HTTPException(
            status_code=400,
            detail="Invalid WeChat directory. It must contain wxid_* folders with Msg (V3) or db_storage (V4).",
        )

    # Persist root path
    set_root_path(root_path)

    wxid_folders = wechat_dir.get_wxid_folders(root_path)
    wxid_names = [Path(p).name for p in wxid_folders]

    # Set active account if user provided a wxid path
    if requested_wxid and requested_wxid in wxid_names:
        set_active_wxid(requested_wxid)
    elif len(wxid_folders) == 1:
        set_active_wxid(Path(wxid_folders[0]).name)
    else:
        # Keep previous active if still valid; otherwise clear it
        cfg = load_config()
        if cfg.active_wxid and cfg.active_wxid not in wxid_names:
            set_active_wxid(None)

    return {
        "success": True,
        "path": root_path,
        "message": "WeChat directory set successfully",
        "wxid_folders": wxid_folders,
    }


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


@router.get("/accounts", response_model=AccountListResponse)
async def list_accounts():
    cfg = load_config()
    root = wechat_dir.get_current_wechat_dir() or cfg.root_path
    if not root:
        return {"accounts": [], "active_account": cfg.active_wxid}

    wxid_folders = wechat_dir.get_wxid_folders(root)
    accounts: List[dict] = []
    for folder_path in wxid_folders:
        wxid = Path(folder_path).name
        version = wechat_dir.detect_wxid_version(folder_path)
        accounts.append(
            {
                "wxid": wxid,
                "path": folder_path,
                "version": version,
                "is_active": wxid == cfg.active_wxid,
            }
        )

    return {"accounts": accounts, "active_account": cfg.active_wxid}


@router.post("/accounts/active", response_model=KeyResponse)
async def set_active_account(req: SetActiveAccountRequest):
    cfg = load_config()
    root = wechat_dir.get_current_wechat_dir() or cfg.root_path
    if not root:
        raise HTTPException(status_code=400, detail="WeChat directory not set")

    wxid_folders = wechat_dir.get_wxid_folders(root)
    valid = {Path(p).name for p in wxid_folders}
    if req.wxid not in valid:
        raise HTTPException(status_code=400, detail=f"Account not found: {req.wxid}")

    set_active_wxid(req.wxid)
    return {"success": True, "message": f"Active account set to {req.wxid}"}


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
        # Prefer validating against the active account DB if configured.
        cfg = load_config()
        root = wechat_dir.get_current_wechat_dir() or cfg.root_path
        wxid_path: Optional[Path] = None
        if root:
            wxid_folders = wechat_dir.get_wxid_folders(root)
            if cfg.active_wxid:
                for p in wxid_folders:
                    if Path(p).name == cfg.active_wxid:
                        wxid_path = Path(p)
                        break
            elif len(wxid_folders) == 1:
                wxid_path = Path(wxid_folders[0])

        db_path = None
        if wxid_path is not None:
            # V4: db_storage/contact/contact.db, V3: Msg/MicroMsg.db
            v4_contact = wxid_path / "db_storage" / "contact" / "contact.db"
            v3_micromsg = wxid_path / "Msg" / "MicroMsg.db"
            if v4_contact.exists() and v4_contact.stat().st_size > 0:
                db_path = str(v4_contact)
            elif v3_micromsg.exists() and v3_micromsg.stat().st_size > 0:
                db_path = str(v3_micromsg)

        if not db_path:
            raise HTTPException(
                status_code=400,
                detail=(
                    "WeChat directory/account not configured for validation. "
                    "Please set directory and select an account first."
                ),
            )

        key = key_extractor.extract_key_from_memory(db_path=db_path)

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
    except key_extractor.WeChatNotRunningError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except key_extractor.KeyExtractionError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/key/manual", response_model=KeyResponse)
async def set_manual_key(req: ManualKeyRequest):
    """Set key manually"""
    try:
        cfg = load_config()
        root = wechat_dir.get_current_wechat_dir() or cfg.root_path
        if not root:
            raise HTTPException(status_code=400, detail="WeChat directory not set")

        wxid_folders = wechat_dir.get_wxid_folders(root)
        wxid_path: Optional[Path] = None
        if cfg.active_wxid:
            for p in wxid_folders:
                if Path(p).name == cfg.active_wxid:
                    wxid_path = Path(p)
                    break
        elif len(wxid_folders) == 1:
            wxid_path = Path(wxid_folders[0])
        else:
            raise HTTPException(
                status_code=400,
                detail="Multiple accounts found. Please select an account first.",
            )

        if wxid_path is None:
            raise HTTPException(status_code=400, detail="Active account not found")

        v4_contact = wxid_path / "db_storage" / "contact" / "contact.db"
        v3_micromsg = wxid_path / "Msg" / "MicroMsg.db"
        db_path = None
        if v4_contact.exists() and v4_contact.stat().st_size > 0:
            db_path = str(v4_contact)
        elif v3_micromsg.exists() and v3_micromsg.stat().st_size > 0:
            db_path = str(v3_micromsg)

        if not db_path:
            raise HTTPException(
                status_code=400,
                detail="No valid database file found for validation under selected account.",
            )

        key_norm = (req.key or "").strip().lower()
        if not verify_key(key_norm, db_path, version_hint=None):
            raise HTTPException(
                status_code=400,
                detail="Key does not match the selected account database (HMAC verify failed).",
            )

        key_extractor.set_manual_key(key_norm)
        return {
            "success": True,
            "message": "Key set successfully",
        }
    except key_extractor.InvalidKeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
