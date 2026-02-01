"""WeChat directory detection.

This module detects and validates the WeChat data root directory.

Supported layouts:
- Legacy (WeChat 3.x): wxid_*/Msg/MicroMsg.db (non-empty)
- New (Weixin 4.x): wxid_*/db_storage/contact/contact.db (non-empty)
"""

import os
from pathlib import Path
from typing import Optional, List

# Default search paths for WeChat data directory (Windows)
DEFAULT_PATHS = [
    # Weixin 4.x
    os.path.expanduser("~/Documents/xwechat_files"),
    os.path.expandvars(r"%USERPROFILE%\Documents\xwechat_files"),
    # WeChat 3.x
    os.path.expanduser("~/Documents/WeChat Files"),
    os.path.expandvars(r"%USERPROFILE%\Documents\WeChat Files"),
    os.path.expanduser("~/Documents/Tencent Files/WeChat Files"),
    os.path.expandvars(r"%USERPROFILE%\Documents\Tencent Files\WeChat Files"),
]

# Global variable to store the currently configured WeChat directory
_current_wechat_dir: Optional[str] = None


def auto_detect_wechat_dir() -> Optional[str]:
    """
    Automatically detect WeChat Files directory.

    Searches through DEFAULT_PATHS and returns the first valid directory found.

    Returns:
        Optional[str]: Path to WeChat Files directory if found, None otherwise
    """
    for path in DEFAULT_PATHS:
        expanded = os.path.expandvars(os.path.expanduser(path))
        if validate_wechat_dir(expanded):
            return expanded
    return None


def _is_nonempty_file(p: Path) -> bool:
    try:
        return p.is_file() and p.stat().st_size > 0
    except OSError:
        return False


def is_v3_wxid_dir(wxid_dir: Path) -> bool:
    """Legacy layout: wxid_*/Msg/MicroMsg.db"""
    return _is_nonempty_file(wxid_dir / "Msg" / "MicroMsg.db")


def is_v4_wxid_dir(wxid_dir: Path) -> bool:
    """Weixin 4.x layout: wxid_*/db_storage/contact/contact.db"""
    return _is_nonempty_file(wxid_dir / "db_storage" / "contact" / "contact.db")


def detect_wxid_version(wxid_path: str) -> Optional[int]:
    """Detect wxid folder layout version.

    Returns:
        4: Weixin 4.x (db_storage)
        3: WeChat 3.x (Msg)
        None: unknown
    """
    p = Path(wxid_path)
    if is_v4_wxid_dir(p):
        return 4
    if is_v3_wxid_dir(p):
        return 3
    return None


def validate_wechat_dir(path: str) -> bool:
    """
    Validate if a path is a valid WeChat Files directory.

    Checks:
    - Path exists
    - Path is a valid WeChat Files directory (contains wxid_* with Msg)
      OR a valid wxid_* account directory (contains Msg)

    Args:
        path (str): Path to validate

    Returns:
        bool: True if valid WeChat directory, False otherwise
    """
    p = Path(path)

    # Check if path exists
    if not p.exists():
        return False

    # Direct wxid folder
    if p.is_dir() and p.name.startswith("wxid_"):
        return is_v3_wxid_dir(p) or is_v4_wxid_dir(p)

    # Root folder containing wxid_* subfolders
    for wxid_dir in p.glob("wxid_*"):
        if wxid_dir.is_dir() and (is_v3_wxid_dir(wxid_dir) or is_v4_wxid_dir(wxid_dir)):
            return True

    return False


def set_wechat_dir(path: str) -> bool:
    """
    Manually set and validate WeChat Files directory.

    Args:
        path (str): Path to set as WeChat directory

    Returns:
        bool: True if path is valid and set successfully, False otherwise
    """
    global _current_wechat_dir

    p = Path(path)
    if not validate_wechat_dir(path):
        return False

    # If user points to wxid_*, store its parent (root directory)
    if p.is_dir() and p.name.startswith("wxid_"):
        _current_wechat_dir = str(p.parent)
    else:
        _current_wechat_dir = str(p)
    return True


def get_current_wechat_dir() -> Optional[str]:
    """
    Get the currently configured WeChat Files directory.

    Returns:
        Optional[str]: Current WeChat directory path if set, None otherwise
    """
    if _current_wechat_dir:
        return _current_wechat_dir

    # Fall back to persisted config (so a server restart doesn't lose state).
    try:
        from wechat_manager.core.config import load_config

        cfg = load_config()
        return cfg.root_path
    except Exception:
        return None


def get_wxid_folders(wechat_dir: str) -> List[str]:
    """
    Get list of all wxid_xxx account folders in WeChat directory.

    Args:
        wechat_dir (str): Path to WeChat Files directory

    Returns:
        List[str]: List of full paths to wxid folders, sorted alphabetically
    """
    p = Path(wechat_dir)

    if not p.exists():
        return []

    wxid_folders: List[str] = []
    for folder in p.glob("wxid_*"):
        if not folder.is_dir():
            continue
        if is_v3_wxid_dir(folder) or is_v4_wxid_dir(folder):
            wxid_folders.append(str(folder))

    wxid_folders.sort()
    return wxid_folders


def get_msg_dir(wxid_path: str) -> str:
    """
    Get the Msg subdirectory path for a given wxid folder.

    Args:
        wxid_path (str): Path to wxid_xxx folder

    Returns:
        str: Path to Msg subdirectory
    """
    return str(Path(wxid_path) / "Msg")
