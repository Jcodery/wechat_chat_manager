"""
Password authentication module for app protection
Uses scrypt hashing with keyring for secure credential storage
"""

import os
import keyring
from Crypto.Protocol.KDF import scrypt
from typing import Optional

SERVICE_NAME = "wechat_chat_manager"
HASH_KEY = "app_password_hash"
SALT_KEY = "app_password_salt"


class AuthManager:
    """Manages app password authentication with secure hashing"""

    def __init__(self):
        """Initialize auth manager"""
        pass

    def is_password_set(self) -> bool:
        """Check if app password has been configured"""
        return keyring.get_password(SERVICE_NAME, HASH_KEY) is not None

    def set_password(self, password: str) -> bool:
        """
        Set initial app password (only if not already set)

        Args:
            password: The password to set

        Returns:
            True if password was set, False if already set
        """
        if self.is_password_set():
            return False

        salt = os.urandom(16)
        hashed = self._hash_password(password, salt)
        keyring.set_password(SERVICE_NAME, HASH_KEY, hashed.hex())
        keyring.set_password(SERVICE_NAME, SALT_KEY, salt.hex())
        return True

    def verify_password(self, password: str) -> bool:
        """
        Verify password matches stored hash

        Args:
            password: The password to verify

        Returns:
            True if password matches, False otherwise
        """
        stored_hash = keyring.get_password(SERVICE_NAME, HASH_KEY)
        stored_salt = keyring.get_password(SERVICE_NAME, SALT_KEY)

        if not stored_hash or not stored_salt:
            return False

        salt = bytes.fromhex(stored_salt)
        hashed = self._hash_password(password, salt)
        return hashed.hex() == stored_hash

    def change_password(self, old_password: str, new_password: str) -> bool:
        """
        Change password (requires old password verification)

        Args:
            old_password: The current password
            new_password: The new password to set

        Returns:
            True if password was changed, False if old password incorrect
        """
        if not self.verify_password(old_password):
            return False

        # Delete old and set new
        self._clear_password()
        return self._force_set_password(new_password)

    def _hash_password(self, password: str, salt: bytes) -> bytes:
        """
        Hash password using scrypt KDF

        Args:
            password: The password to hash
            salt: The salt bytes (16 bytes recommended)

        Returns:
            Hashed password bytes
        """
        return scrypt(password.encode(), salt, key_len=32, N=2**14, r=8, p=1)

    def _clear_password(self):
        """Clear stored password (internal use)"""
        try:
            keyring.delete_password(SERVICE_NAME, HASH_KEY)
            keyring.delete_password(SERVICE_NAME, SALT_KEY)
        except keyring.errors.PasswordDeleteError:
            pass

    def _force_set_password(self, password: str) -> bool:
        """
        Force set password (internal use for change_password)

        Args:
            password: The password to set

        Returns:
            True if password was set
        """
        salt = os.urandom(16)
        hashed = self._hash_password(password, salt)
        keyring.set_password(SERVICE_NAME, HASH_KEY, hashed.hex())
        keyring.set_password(SERVICE_NAME, SALT_KEY, salt.hex())
        return True
