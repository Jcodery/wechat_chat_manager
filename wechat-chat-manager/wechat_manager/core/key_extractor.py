"""WeChat Key Utilities (manual only).

Provides:
- Key format validation
- Keyring storage and retrieval
- Manual key setting
"""

import re
from typing import Optional

import keyring

# Constants
SERVICE_NAME = "wechat_chat_manager"
KEY_NAME = "db_key"
KEY_LENGTH_HEX = 64  # 32 bytes = 64 hex characters


class InvalidKeyError(Exception):
    """Raised when key format is invalid."""

    pass


def _is_valid_hex_key(key: Optional[str]) -> bool:
    if key is None:
        return False
    if len(key) != KEY_LENGTH_HEX:
        return False
    return bool(re.fullmatch(r"[0-9a-fA-F]+", key))


def validate_key(key: Optional[str], db_path: str) -> bool:
    """Validate key format (64 hexadecimal characters).

    Args:
        key: The key to validate.
        db_path: Unused (kept for compatibility).

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
    """Save key to system keyring securely."""

    keyring.set_password(SERVICE_NAME, KEY_NAME, key)


def get_key_from_keyring() -> Optional[str]:
    """Retrieve key from system keyring."""

    return keyring.get_password(SERVICE_NAME, KEY_NAME)


def set_manual_key(key: str) -> bool:
    """Manually set a key after validating its format."""

    if not _is_valid_hex_key(key):
        raise InvalidKeyError(f"Key must be {KEY_LENGTH_HEX} hexadecimal characters")

    normalized_key = key.lower()
    save_key_to_keyring(normalized_key)
    return True
