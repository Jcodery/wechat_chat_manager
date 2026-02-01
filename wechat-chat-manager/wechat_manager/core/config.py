"""Configuration persistence for WeChat Chat Manager.

This module stores user configuration on disk so the backend can survive restarts.

Stored fields:
- root_path: The directory that contains one or more wxid_* folders.
- active_wxid: The selected wxid_* folder name when multiple accounts exist.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_LOCK = threading.Lock()


def _config_file_path() -> Path:
    """Resolve config file path.

    Test harnesses can override via:
    - WECHAT_MANAGER_CONFIG_FILE: full path to config.json
    - WECHAT_MANAGER_CONFIG_DIR: directory containing config.json
    """

    file_env = os.environ.get("WECHAT_MANAGER_CONFIG_FILE")
    if file_env:
        return Path(file_env)

    dir_env = os.environ.get("WECHAT_MANAGER_CONFIG_DIR")
    if dir_env:
        return Path(dir_env) / "config.json"

    return Path.home() / ".wechat_manager" / "config.json"


@dataclass
class AppConfig:
    root_path: Optional[str] = None
    active_wxid: Optional[str] = None


def load_config() -> AppConfig:
    with _LOCK:
        try:
            cfg_file = _config_file_path()
            if not cfg_file.exists():
                return AppConfig()
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            return AppConfig(
                root_path=data.get("root_path"),
                active_wxid=data.get("active_wxid"),
            )
        except Exception:
            return AppConfig()


def save_config(cfg: AppConfig) -> None:
    with _LOCK:
        cfg_file = _config_file_path()
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "root_path": cfg.root_path,
            "active_wxid": cfg.active_wxid,
        }
        cfg_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def set_root_path(path: Optional[str]) -> AppConfig:
    cfg = load_config()
    cfg.root_path = path
    save_config(cfg)
    return cfg


def set_active_wxid(wxid: Optional[str]) -> AppConfig:
    cfg = load_config()
    cfg.active_wxid = wxid
    save_config(cfg)
    return cfg
