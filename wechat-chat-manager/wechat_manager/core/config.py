"""Configuration persistence for WeChat Chat Manager.

This module stores user configuration on disk so the backend can survive restarts.

Stored fields:
- root_path: The directory that contains one or more wxid_* folders.
- active_wxid: The selected wxid_* folder name when multiple accounts exist.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


_LOCK = threading.Lock()

_CONFIG_DIR = Path.home() / ".wechat_manager"
_CONFIG_FILE = _CONFIG_DIR / "config.json"


@dataclass
class AppConfig:
    root_path: Optional[str] = None
    active_wxid: Optional[str] = None


def load_config() -> AppConfig:
    with _LOCK:
        try:
            if not _CONFIG_FILE.exists():
                return AppConfig()
            data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            return AppConfig(
                root_path=data.get("root_path"),
                active_wxid=data.get("active_wxid"),
            )
        except Exception:
            return AppConfig()


def save_config(cfg: AppConfig) -> None:
    with _LOCK:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "root_path": cfg.root_path,
            "active_wxid": cfg.active_wxid,
        }
        _CONFIG_FILE.write_text(
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
