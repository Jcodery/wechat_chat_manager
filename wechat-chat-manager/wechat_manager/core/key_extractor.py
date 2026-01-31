"""
WeChat Key Extractor Module
Handles extraction of decryption key from WeChat process memory,
key validation, and secure storage via keyring.
"""

import re
from typing import Optional

import keyring
import psutil
import pymem
import pymem.process


# Constants
SERVICE_NAME = "wechat_chat_manager"
KEY_NAME = "db_key"
WECHAT_PROCESS_NAME = "WeChat.exe"
WECHAT_DLL_NAME = "WeChatWin.dll"
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


def is_wechat_running() -> bool:
    """
    Check if WeChat.exe process is running.

    Returns:
        bool: True if WeChat.exe is running, False otherwise.
    """
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] == WECHAT_PROCESS_NAME:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False


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
    pm: pymem.Pymem, module_base: int, module_size: int
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
    try:
        # Read the entire module memory
        module_data = pm.read_bytes(module_base, module_size)

        for pattern in SEARCH_PATTERNS:
            # Search for pattern in module data
            offset = module_data.find(pattern)
            if offset != -1:
                # Calculate actual address
                pattern_addr = module_base + offset

                # Key is typically found at a specific offset from pattern
                # This offset varies by WeChat version, try common offsets
                for key_offset in [
                    0x40,
                    0x44,
                    0x48,
                    0x4C,
                    0x50,
                    0x54,
                    0x58,
                    0x5C,
                    0x60,
                ]:
                    try:
                        # Read pointer to key
                        key_ptr_addr = pattern_addr + key_offset
                        key_ptr = pm.read_int(key_ptr_addr)

                        # Validate pointer is within reasonable range
                        if 0x10000 < key_ptr < 0x7FFFFFFF:
                            # Try to read key bytes
                            potential_key = pm.read_bytes(key_ptr, KEY_LENGTH_BYTES)

                            # Check if it looks like a valid key (all bytes should be non-zero patterns)
                            if len(potential_key) == KEY_LENGTH_BYTES and all(
                                b != 0 for b in potential_key[:8]
                            ):
                                return key_ptr
                    except Exception:
                        continue

        return None

    except Exception:
        return None


def extract_key_from_memory() -> Optional[str]:
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
    if not is_wechat_running():
        raise WeChatNotRunningError("WeChat.exe is not running")

    try:
        # Attach to WeChat process
        pm = pymem.Pymem(WECHAT_PROCESS_NAME)
    except Exception as e:
        raise KeyExtractionError(f"Failed to attach to WeChat process: {e}")

    try:
        # Find WeChatWin.dll module
        module = pymem.process.module_from_name(pm.process_handle, WECHAT_DLL_NAME)

        if module is None:
            raise KeyExtractionError(
                f"Could not find {WECHAT_DLL_NAME} module in WeChat process"
            )

        module_base = module.lpBaseOfDll
        module_size = module.SizeOfImage

        # Search for key pattern
        key_address = _search_key_pattern(pm, module_base, module_size)

        if key_address is None:
            raise KeyExtractionError(
                "Could not find key pattern in WeChat memory. "
                "WeChat version may not be supported."
            )

        # Read the key bytes
        key_bytes = pm.read_bytes(key_address, KEY_LENGTH_BYTES)

        # Convert to hex string
        key_hex = key_bytes.hex()

        return key_hex

    except KeyExtractionError:
        raise
    except Exception as e:
        raise KeyExtractionError(f"Failed to extract key from memory: {e}")
    finally:
        try:
            pm.close_process()
        except Exception:
            pass
