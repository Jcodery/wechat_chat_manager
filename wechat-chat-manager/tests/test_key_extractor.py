"""WeChat Key Utilities - Tests (manual-only)."""

from unittest.mock import patch

import pytest

from wechat_manager.core.key_extractor import (
    validate_key,
    save_key_to_keyring,
    get_key_from_keyring,
    set_manual_key,
    InvalidKeyError,
)


class TestKeyValidation:
    """Tests for key format validation."""

    def test_validate_key_with_mock_db(self, test_db_key, temp_dir):
        """Validate a key against a mock database (format check only)."""
        mock_db = temp_dir / "test.db"
        mock_db.touch()
        assert validate_key(test_db_key, str(mock_db)) is True

    def test_validate_key_correct_format(self, test_db_key):
        """Test key validation with correct 64 hex char format."""
        assert validate_key(test_db_key, "any_path.db") is True

    def test_invalid_key_rejected_too_short(self):
        """Reject key that is too short."""
        short_key = "0123456789abcdef"  # Only 16 chars
        with pytest.raises(InvalidKeyError, match="must be 64 hexadecimal characters"):
            validate_key(short_key, "any_path.db")

    def test_invalid_key_rejected_too_long(self):
        """Reject key that is too long."""
        long_key = "0" * 128  # 128 chars
        with pytest.raises(InvalidKeyError, match="must be 64 hexadecimal characters"):
            validate_key(long_key, "any_path.db")

    def test_invalid_key_rejected_non_hex(self):
        """Reject key with non-hexadecimal characters."""
        invalid_key = "ghijklmnopqrstuv" * 4  # 64 chars but not hex
        with pytest.raises(InvalidKeyError, match="must be 64 hexadecimal characters"):
            validate_key(invalid_key, "any_path.db")

    def test_invalid_key_rejected_empty(self):
        """Reject empty key."""
        with pytest.raises(InvalidKeyError, match="must be 64 hexadecimal characters"):
            validate_key("", "any_path.db")

    def test_invalid_key_rejected_none(self):
        """Reject None key."""
        with pytest.raises(InvalidKeyError):
            validate_key(None, "any_path.db")


class TestManualKeyInput:
    """Tests for manual key input."""

    def test_manual_key_input_valid(self, test_db_key):
        """Accept valid manual key input (64 hex chars)."""
        with patch(
            "wechat_manager.core.key_extractor.save_key_to_keyring"
        ) as mock_save:
            result = set_manual_key(test_db_key)
            assert result is True
            mock_save.assert_called_once_with(test_db_key)

    def test_manual_key_input_invalid_format(self):
        """Reject invalid manual key input."""
        invalid_key = "not_a_valid_key"
        with pytest.raises(InvalidKeyError):
            set_manual_key(invalid_key)

    def test_manual_key_input_accepts_uppercase(self):
        """Accept uppercase hex characters."""
        upper_key = "0123456789ABCDEF" * 4
        with patch(
            "wechat_manager.core.key_extractor.save_key_to_keyring"
        ) as mock_save:
            result = set_manual_key(upper_key)
            assert result is True
            mock_save.assert_called_once()

    def test_manual_key_input_mixed_case(self):
        """Accept mixed case hex characters."""
        mixed_key = "0123456789AbCdEf" * 4
        with patch(
            "wechat_manager.core.key_extractor.save_key_to_keyring"
        ) as mock_save:
            result = set_manual_key(mixed_key)
            assert result is True


class TestKeyringStorage:
    """Tests for keyring storage and retrieval."""

    @patch("wechat_manager.core.key_extractor.keyring.set_password")
    def test_keyring_storage_save(self, mock_set_password, test_db_key):
        """Store key to keyring."""
        save_key_to_keyring(test_db_key)
        mock_set_password.assert_called_once_with(
            "wechat_chat_manager", "db_key", test_db_key
        )

    @patch("wechat_manager.core.key_extractor.keyring.get_password")
    def test_keyring_storage_retrieve(self, mock_get_password, test_db_key):
        """Retrieve key from keyring."""
        mock_get_password.return_value = test_db_key
        result = get_key_from_keyring()
        assert result == test_db_key
        mock_get_password.assert_called_once_with("wechat_chat_manager", "db_key")

    @patch("wechat_manager.core.key_extractor.keyring.get_password")
    def test_keyring_storage_retrieve_not_found(self, mock_get_password):
        """Return None when key not in keyring."""
        mock_get_password.return_value = None
        result = get_key_from_keyring()
        assert result is None
