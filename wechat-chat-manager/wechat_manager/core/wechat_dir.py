"""
WeChat Directory Detection Module

Handles detection, validation, and management of WeChat Files directory.
Supports auto-detection and manual path configuration.
"""

import os
from pathlib import Path
from typing import Optional, List

# Default search paths for WeChat Files directory (Windows)
DEFAULT_PATHS = [
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
    if p.is_dir() and p.name.startswith("wxid_") and (p / "Msg").exists():
        return True

    # WeChat Files folder containing wxid_* subfolders
    for wxid_dir in p.glob("wxid_*"):
        if wxid_dir.is_dir() and (wxid_dir / "Msg").exists():
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

    # If user points to wxid_*, store its parent (WeChat Files)
    if p.is_dir() and p.name.startswith("wxid_") and (p / "Msg").exists():
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
    return _current_wechat_dir


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

    wxid_folders = sorted(
        [str(folder) for folder in p.glob("wxid_*") if (folder / "Msg").exists()]
    )
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
