"""
Shared dependencies for API routes.

Provides FastAPI dependency injection for:
- WeChatDBHandler
- EncryptedStorage
- ModeA/ModeB instances
"""

from pathlib import Path
from fastapi import HTTPException

from wechat_manager.core.config import load_config
from wechat_manager.core import wechat_dir, key_extractor
from wechat_manager.core.db_handler import WeChatDBHandler
from wechat_manager.core.storage import EncryptedStorage


# Default paths for storage and exports
DEFAULT_STORAGE_PATH = Path.home() / ".wechat_manager" / "storage"
DEFAULT_EXPORT_PATH = Path.home() / ".wechat_manager" / "exports"
DEFAULT_BACKUP_PATH = Path.home() / ".wechat_manager" / "backups"

# Default password for storage (in production, use user's auth password)
DEFAULT_STORAGE_PASSWORD = "wechat_manager_default_key"


def get_db_handler() -> WeChatDBHandler:
    """Get WeChatDBHandler instance.

    Requires:
    - WeChat directory to be set
    - Key to be available in keyring

    Raises:
        HTTPException: If WeChat directory or key is not configured
    """
    cfg = load_config()
    root_dir = wechat_dir.get_current_wechat_dir() or cfg.root_path
    if not root_dir:
        raise HTTPException(
            status_code=400,
            detail="WeChat directory not set. Please use /api/wechat/detect or /api/wechat/set-dir first.",
        )

    key = key_extractor.get_key_from_keyring()
    if not key:
        raise HTTPException(
            status_code=400,
            detail="Database key not available. Please use /api/wechat/key/extract or /api/wechat/key/manual first.",
        )

    wxid_folders = wechat_dir.get_wxid_folders(root_dir)
    if not wxid_folders:
        raise HTTPException(
            status_code=400, detail="No wxid folders found in WeChat directory."
        )

    # Explicit account selection when multiple wxid folders exist.
    if len(wxid_folders) == 1:
        selected = wxid_folders[0]
    else:
        if not cfg.active_wxid:
            names = [Path(p).name for p in wxid_folders]
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Multiple accounts found: {names}. "
                    "Please select an account via /api/wechat/accounts/active"
                ),
            )

        selected = None
        for p in wxid_folders:
            if Path(p).name == cfg.active_wxid:
                selected = p
                break

        if not selected:
            names = [Path(p).name for p in wxid_folders]
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Active account '{cfg.active_wxid}' not found. Available: {names}. "
                    "Please re-select via /api/wechat/accounts/active"
                ),
            )

    return WeChatDBHandler(selected, key)


def get_storage() -> EncryptedStorage:
    """Get EncryptedStorage instance.

    Creates storage directory if it doesn't exist.
    Uses default password for MVP (should use user's password in production).
    """
    DEFAULT_STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    return EncryptedStorage(str(DEFAULT_STORAGE_PATH), DEFAULT_STORAGE_PASSWORD)


def get_export_path() -> str:
    """Get export directory path."""
    DEFAULT_EXPORT_PATH.mkdir(parents=True, exist_ok=True)
    return str(DEFAULT_EXPORT_PATH)


def get_backup_path() -> str:
    """Get backup directory path."""
    DEFAULT_BACKUP_PATH.mkdir(parents=True, exist_ok=True)
    return str(DEFAULT_BACKUP_PATH)
