"""
WeChat Key Extractor Module
Handles extraction of decryption key from WeChat process memory,
key validation, and secure storage via keyring.
"""

import os
import re
import time
from pathlib import Path
from typing import Callable, Optional

import ctypes

import keyring
import psutil
import pymem
import pymem.process


# Constants
SERVICE_NAME = "wechat_chat_manager"
KEY_NAME = "db_key"

# WeChat/Weixin process names (Windows)
_WECHAT_PROCESS_STEMS_ORDERED = (
    "wechat",
    "weixin",
    # Some multi-instance launchers use this helper process name
    "wechatappex",
)
_WECHAT_PROCESS_STEMS = set(_WECHAT_PROCESS_STEMS_ORDERED)

# WeChat module names (Windows)
_WECHAT_DLL_NAMES = (
    # Common on many PC builds
    "WeChatWin.dll",
    # Observed on some Weixin builds
    "Weixin.dll",
    # Some builds may use different names
    "WeChat.dll",
    "WeixinWin.dll",
)

KEY_LENGTH_HEX = 64  # 32 bytes = 64 hex characters
KEY_LENGTH_BYTES = 32

# Patterns used to locate key in memory (PyWxDump style)
# These are common patterns found near the key in WeChat's memory
SEARCH_PATTERNS = [
    b"-----BEGIN PUBLIC KEY-----",
    b"iphone\x00",
    b"android\x00",
    b"iPad\x00",
]


# Custom Exceptions
class WeChatNotRunningError(Exception):
    """Raised when WeChat.exe process is not running."""

    pass


class KeyExtractionError(Exception):
    """Raised when key extraction from memory fails."""

    pass


class InvalidKeyError(Exception):
    """Raised when key format is invalid."""

    pass


def _find_wx_key_dll() -> Optional[str]:
    """Locate wx_key.dll if present.

    Users can drop the DLL next to the project or set WX_KEY_DLL_PATH.
    """
    env = os.environ.get("WX_KEY_DLL_PATH")
    if env:
        p = Path(env)
        if p.exists() and p.is_file():
            return str(p)

    # Look in common local locations
    candidates = [
        Path.cwd() / "wx_key.dll",
        Path(__file__).resolve().parents[2] / "bin" / "wx_key.dll",
        Path(__file__).resolve().parents[3] / "wx_key.dll",
    ]
    for c in candidates:
        try:
            if c.exists() and c.is_file():
                return str(c)
        except OSError:
            continue
    return None


def _extract_key_with_wx_key(pid: int, timeout_sec: float = 15.0) -> str:
    """Extract database key via wx_key.dll (Weixin 4.x).

    Requires user-provided wx_key.dll.
    """
    dll_path = _find_wx_key_dll()
    if not dll_path:
        raise KeyExtractionError(
            "wx_key.dll not found. Set WX_KEY_DLL_PATH or place wx_key.dll next to the program."
        )

    try:
        lib = ctypes.CDLL(dll_path)
    except Exception as e:
        raise KeyExtractionError(f"Failed to load wx_key.dll: {e}")

    # bool InitializeHook(DWORD targetPid)
    lib.InitializeHook.argtypes = [ctypes.c_uint32]
    lib.InitializeHook.restype = ctypes.c_bool

    # bool PollKeyData(char* keyBuffer, int bufferSize)
    lib.PollKeyData.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.PollKeyData.restype = ctypes.c_bool

    # bool GetStatusMessage(char* statusBuffer, int bufferSize, int* outLevel)
    lib.GetStatusMessage.argtypes = [
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
    ]
    lib.GetStatusMessage.restype = ctypes.c_bool

    # bool CleanupHook()
    lib.CleanupHook.argtypes = []
    lib.CleanupHook.restype = ctypes.c_bool

    # const char* GetLastErrorMsg();
    lib.GetLastErrorMsg.argtypes = []
    lib.GetLastErrorMsg.restype = ctypes.c_char_p

    if not lib.InitializeHook(int(pid)):
        msg = lib.GetLastErrorMsg()
        err = msg.decode("utf-8", errors="replace") if msg else "unknown"
        raise KeyExtractionError(f"wx_key InitializeHook failed: {err}")

    key_buf = ctypes.create_string_buffer(128)
    status_buf = ctypes.create_string_buffer(512)
    level = ctypes.c_int(0)
    last_status: list[str] = []

    deadline = time.time() + float(timeout_sec)
    try:
        while time.time() < deadline:
            # Drain status messages for diagnostics
            while lib.GetStatusMessage(
                status_buf, len(status_buf), ctypes.byref(level)
            ):
                try:
                    s = status_buf.value.decode("utf-8", errors="replace").strip()
                    if s:
                        last_status.append(s)
                        last_status = last_status[-10:]
                except Exception:
                    break

            if lib.PollKeyData(key_buf, len(key_buf)):
                key = key_buf.value.decode("ascii", errors="ignore").strip()
                if _is_valid_hex_key(key):
                    return key.lower()
                raise KeyExtractionError("wx_key returned an invalid key format")

            time.sleep(0.1)

        extra = (" | ".join(last_status)) if last_status else "(no status)"
        raise KeyExtractionError(
            f"Timed out waiting for key from wx_key.dll. Status: {extra}"
        )
    finally:
        try:
            lib.CleanupHook()
        except Exception:
            pass


def is_wechat_running() -> bool:
    """
    Check if WeChat.exe process is running.

    Returns:
        bool: True if WeChat.exe is running, False otherwise.
    """
    return len(_get_wechat_process_candidates()) > 0


def _normalize_process_name(name: str) -> str:
    # psutil returns names like "WeChat.exe"; PowerShell sometimes shows no extension.
    n = (name or "").strip().lower()
    return n.removesuffix(".exe")


def _get_wechat_process_candidates() -> list[tuple[int, str]]:
    candidates: list[tuple[int, str]] = []

    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = proc.info.get("name")
            if not name:
                continue

            stem = _normalize_process_name(name)
            if stem in _WECHAT_PROCESS_STEMS:
                candidates.append((int(proc.info["pid"]), name))
        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
            psutil.ZombieProcess,
            KeyError,
            TypeError,
        ):
            continue

    def _sort_key(item: tuple[int, str]) -> int:
        stem = _normalize_process_name(item[1])
        try:
            return _WECHAT_PROCESS_STEMS_ORDERED.index(stem)
        except ValueError:
            return 999

    candidates.sort(key=_sort_key)
    return candidates


def _is_valid_hex_key(key: str) -> bool:
    """
    Check if a string is a valid 64-character hexadecimal key.

    Args:
        key: The key string to validate.

    Returns:
        bool: True if valid, False otherwise.
    """
    if key is None:
        return False
    if len(key) != KEY_LENGTH_HEX:
        return False
    return bool(re.fullmatch(r"[0-9a-fA-F]+", key))


def validate_key(key: str, db_path: str) -> bool:
    """
    Validate key format (64 hexadecimal characters).

    Args:
        key: The key to validate.
        db_path: Path to the database (for future validation against actual DB).

    Returns:
        bool: True if key format is valid.

    Raises:
        InvalidKeyError: If key format is invalid.
    """
    if not _is_valid_hex_key(key):
        raise InvalidKeyError(
            f"Key must be {KEY_LENGTH_HEX} hexadecimal characters, "
            f"got {len(key) if key else 0} characters"
        )
    return True


def save_key_to_keyring(key: str) -> None:
    """
    Save key to system keyring securely.

    Args:
        key: The hexadecimal key to save.
    """
    keyring.set_password(SERVICE_NAME, KEY_NAME, key)


def get_key_from_keyring() -> Optional[str]:
    """
    Retrieve key from system keyring.

    Returns:
        Optional[str]: The stored key, or None if not found.
    """
    return keyring.get_password(SERVICE_NAME, KEY_NAME)


def set_manual_key(key: str) -> bool:
    """
    Manually set a key after validating its format.

    Args:
        key: The hexadecimal key to set (64 characters).

    Returns:
        bool: True if key was set successfully.

    Raises:
        InvalidKeyError: If key format is invalid.
    """
    if not _is_valid_hex_key(key):
        raise InvalidKeyError(f"Key must be {KEY_LENGTH_HEX} hexadecimal characters")

    # Normalize to lowercase
    normalized_key = key.lower()
    save_key_to_keyring(normalized_key)
    return True


def _search_key_pattern(
    pm: pymem.Pymem,
    module_base: int,
    module_size: int,
    validate_key_bytes: Optional[Callable[[bytes], bool]] = None,
) -> Optional[int]:
    """
    Search for key pattern in WeChat module memory.

    This function searches for known patterns in WeChat's memory that are
    typically located near the encryption key.

    Args:
        pm: Pymem instance attached to WeChat process.
        module_base: Base address of WeChatWin.dll.
        module_size: Size of WeChatWin.dll module.

    Returns:
        Optional[int]: Address of the key if found, None otherwise.
    """
    chunk_size = 4 * 1024 * 1024
    back_window = 0x2000
    forward_window = 0x2000

    def looks_like_key(key_bytes: bytes) -> bool:
        if len(key_bytes) != KEY_LENGTH_BYTES:
            return False
        if all(b == 0 for b in key_bytes):
            return False

        zero_count = sum(1 for b in key_bytes if b == 0)
        zero_limit = 4 if validate_key_bytes is not None else 8
        if zero_count > zero_limit:
            return False

        # Heuristic: keys are high-entropy; avoid low-variance buffers.
        if len(set(key_bytes)) < 16:
            return False

        if validate_key_bytes is not None:
            return validate_key_bytes(key_bytes)

        return True

    for pattern in SEARCH_PATTERNS:
        overlap = max(len(pattern) - 1, 0)
        tail = b""
        offset = 0

        while offset < module_size:
            to_read = min(chunk_size, module_size - offset)

            try:
                chunk = pm.read_bytes(module_base + offset, to_read)
            except Exception:
                # Some regions may fail to read in large chunks; retry smaller.
                try:
                    to_read = min(256 * 1024, to_read)
                    chunk = pm.read_bytes(module_base + offset, to_read)
                except Exception:
                    offset += to_read
                    tail = b""
                    continue

            hay = tail + chunk
            start = 0
            while True:
                idx = hay.find(pattern, start)
                if idx == -1:
                    break

                pattern_addr = module_base + offset - len(tail) + idx
                search_start = max(module_base, pattern_addr - back_window)
                search_end = min(
                    module_base + module_size, pattern_addr + forward_window
                )

                for step in (8, 4):
                    addr = search_start
                    rem = addr % step
                    if rem:
                        addr += step - rem

                    while addr + step <= search_end:
                        try:
                            if step == 8:
                                key_ptr = pm.read_ulonglong(addr)
                            else:
                                key_ptr = pm.read_int(addr)

                            key_ptr_int = int(key_ptr)
                            if not (0x10000 < key_ptr_int < 0x7FFFFFFFFFFF):
                                addr += step
                                continue

                            potential_key = pm.read_bytes(key_ptr_int, KEY_LENGTH_BYTES)
                            if looks_like_key(potential_key):
                                return key_ptr_int
                        except Exception:
                            pass

                        addr += step

                start = idx + 1

            tail = hay[-overlap:] if overlap else b""
            offset += to_read

    return None


def extract_key_from_memory(db_path: Optional[str] = None) -> Optional[str]:
    """
    Extract the decryption key from WeChat process memory.

    This function attaches to the WeChat.exe process, finds the WeChatWin.dll
    module, searches for known patterns, and extracts the 32-byte key.

    Returns:
        Optional[str]: The extracted key as a 64-character hex string.

    Raises:
        WeChatNotRunningError: If WeChat.exe is not running.
        KeyExtractionError: If key extraction fails.
    """
    # Keep a fast/patchable guard for tests and better UX.
    if not is_wechat_running():
        raise WeChatNotRunningError(
            "WeChat/Weixin is not running. Expected process name: WeChat.exe or Weixin.exe"
        )

    candidates = _get_wechat_process_candidates()

    validate_cb: Optional[Callable[[bytes], bool]] = None
    if db_path and os.path.exists(db_path):
        try:
            from wechat_manager.core.decrypt import verify_key as _verify_db_key
        except Exception:
            _verify_db_key = None

        if _verify_db_key is not None:

            def validate_cb(key_bytes: bytes) -> bool:
                try:
                    return _verify_db_key(key_bytes.hex(), db_path)
                except Exception:
                    return False

    last_error: Optional[Exception] = None
    saw_supported_module = False

    # If psutil could not enumerate candidates (or tests patched is_wechat_running),
    # fall back to trying process names directly.
    if not candidates:
        name_fallbacks = (
            "WeChat.exe",
            "Weixin.exe",
            "WeChatAppEx.exe",
            "WeChatAppEx",
        )
        candidates = [(0, n) for n in name_fallbacks]

    for pid, name in candidates:
        pm: Optional[pymem.Pymem] = None
        try:
            pm = pymem.Pymem(pid if pid else name)

            modules_to_scan = []
            seen_bases = set()

            try:
                handle = getattr(pm, "process_handle", None)
                if isinstance(handle, int):
                    base = pymem.process.base_module(handle)
                    if base is not None:
                        modules_to_scan.append(base)
                        seen_bases.add(int(base.lpBaseOfDll))
            except Exception:
                pass

            found_named_module = False
            for dll in _WECHAT_DLL_NAMES:
                try:
                    module = pymem.process.module_from_name(pm.process_handle, dll)
                    if module is None:
                        continue
                    found_named_module = True
                    base_addr = int(module.lpBaseOfDll)
                    if base_addr in seen_bases:
                        continue
                    modules_to_scan.append(module)
                    seen_bases.add(base_addr)
                except Exception:
                    continue

            if found_named_module:
                saw_supported_module = True

            if not modules_to_scan:
                continue

            modules_to_scan.sort(key=lambda m: int(getattr(m, "SizeOfImage", 0)))

            for module in modules_to_scan:
                module_base = int(module.lpBaseOfDll)
                module_size = int(module.SizeOfImage)

                key_address = _search_key_pattern(
                    pm,
                    module_base,
                    module_size,
                    validate_key_bytes=validate_cb,
                )
                if key_address is None:
                    continue

                key_bytes = pm.read_bytes(int(key_address), KEY_LENGTH_BYTES)
                if validate_cb is not None and not validate_cb(key_bytes):
                    continue
                return key_bytes.hex()

            last_error = KeyExtractionError(
                "Could not find key pattern in WeChat memory. WeChat version may not be supported."
            )
            continue

        except Exception as e:
            last_error = e
            continue
        finally:
            if pm is not None:
                try:
                    pm.close_process()
                except Exception:
                    pass

    # If pattern-based scan couldn't find a valid key (common on Weixin 4.x),
    # fall back to wx_key.dll if available.
    if validate_cb is not None:
        # Prefer Weixin.exe pid
        weixin_pid = None
        for p, n in candidates:
            if _normalize_process_name(n) == "weixin":
                weixin_pid = p
                break
        if weixin_pid is None and candidates:
            weixin_pid = candidates[0][0]

        if weixin_pid:
            key_hex = _extract_key_with_wx_key(weixin_pid)
            key_bytes = bytes.fromhex(key_hex)
            if not validate_cb(key_bytes):
                raise KeyExtractionError(
                    "Extracted key does not validate against the selected database."
                )
            return key_hex

    if not saw_supported_module:
        found = ", ".join(sorted({n for _, n in candidates}))
        dlls = ", ".join(_WECHAT_DLL_NAMES)
        raise KeyExtractionError(
            f"Found WeChat-related processes ({found}) but could not locate any known WeChat module ({dlls}). "
            "If you are using Microsoft Store/UWP WeChat, it is not supported; install the classic desktop client."
        )

    if last_error is not None:
        msg = str(last_error)
        if "access" in msg.lower() and "denied" in msg.lower():
            raise KeyExtractionError(
                "Access denied when reading WeChat process memory. Run this program as Administrator."
            )
        if isinstance(last_error, KeyExtractionError):
            raise last_error
        raise KeyExtractionError(f"Failed to extract key from memory: {msg}")

    raise KeyExtractionError("Failed to extract key from memory")
