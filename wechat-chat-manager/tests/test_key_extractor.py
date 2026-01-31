"""
WeChat Key Extractor - TDD Tests
Tests for key extraction, validation, storage, and process detection.
"""

import pytest
from unittest.mock import patch, MagicMock
import re

# Import exceptions and functions from the module we're about to create
from wechat_manager.core.key_extractor import (
    is_wechat_running,
    extract_key_from_memory,
    validate_key,
    save_key_to_keyring,
    get_key_from_keyring,
    set_manual_key,
    WeChatNotRunningError,
    KeyExtractionError,
    InvalidKeyError,
)


class TestWeChatProcessDetection:
    """Tests for WeChat process detection."""

    @patch("wechat_manager.core.key_extractor.psutil.process_iter")
    def test_wechat_process_detection_when_running(self, mock_process_iter):
        """Test detecting WeChat.exe when it is running."""
        mock_proc = MagicMock()
        mock_proc.info = {"name": "WeChat.exe"}
        mock_process_iter.return_value = [mock_proc]

        assert is_wechat_running() is True
        mock_process_iter.assert_called_once_with(["name"])

    @patch("wechat_manager.core.key_extractor.psutil.process_iter")
    def test_wechat_process_detection_when_not_running(self, mock_process_iter):
        """Test detecting WeChat.exe when it is NOT running."""
        mock_proc = MagicMock()
        mock_proc.info = {"name": "chrome.exe"}
        mock_process_iter.return_value = [mock_proc]

        assert is_wechat_running() is False

    @patch("wechat_manager.core.key_extractor.psutil.process_iter")
    def test_wechat_process_detection_empty_process_list(self, mock_process_iter):
        """Test when no processes are found."""
        mock_process_iter.return_value = []

        assert is_wechat_running() is False


class TestKeyValidation:
    """Tests for key format validation."""

    def test_validate_key_with_mock_db(self, test_db_key, temp_dir):
        """Validate a key against a mock database (format check only)."""
        # Create a mock db file
        mock_db = temp_dir / "test.db"
        mock_db.touch()

        # Valid key format (64 hex chars)
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
        upper_key = "0123456789ABCDEF" * 4  # 64 uppercase hex chars
        with patch(
            "wechat_manager.core.key_extractor.save_key_to_keyring"
        ) as mock_save:
            result = set_manual_key(upper_key)
            assert result is True
            # Key should be normalized to lowercase
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


class TestMemoryExtraction:
    """Tests for memory extraction from WeChat process."""

    @patch("wechat_manager.core.key_extractor.is_wechat_running")
    def test_extract_key_wechat_not_running(self, mock_is_running):
        """Raise error when WeChat is not running."""
        mock_is_running.return_value = False

        with pytest.raises(WeChatNotRunningError):
            extract_key_from_memory()

    @patch("wechat_manager.core.key_extractor.pymem.Pymem")
    @patch("wechat_manager.core.key_extractor.is_wechat_running")
    def test_extract_key_success(self, mock_is_running, mock_pymem, test_db_key):
        """Successfully extract key from memory (mocked)."""
        mock_is_running.return_value = True

        # Mock pymem behavior
        mock_pm = MagicMock()
        mock_pymem.return_value = mock_pm

        # Mock module
        mock_module = MagicMock()
        mock_module.lpBaseOfDll = 0x10000000
        mock_module.SizeOfImage = 0x1000000

        # Mock process module lookup
        with patch(
            "wechat_manager.core.key_extractor.pymem.process.module_from_name",
            return_value=mock_module,
        ):
            # Mock memory read to return key bytes
            key_bytes = bytes.fromhex(test_db_key)
            mock_pm.read_bytes.return_value = key_bytes

            # Mock pattern search
            with patch(
                "wechat_manager.core.key_extractor._search_key_pattern",
                return_value=0x10001000,
            ):
                result = extract_key_from_memory()
                assert result == test_db_key

    @patch("wechat_manager.core.key_extractor.pymem.Pymem")
    @patch("wechat_manager.core.key_extractor.is_wechat_running")
    def test_extract_key_module_not_found(self, mock_is_running, mock_pymem):
        """Raise error when WeChatWin.dll not found."""
        mock_is_running.return_value = True

        mock_pm = MagicMock()
        mock_pymem.return_value = mock_pm

        with patch(
            "wechat_manager.core.key_extractor.pymem.process.module_from_name",
            return_value=None,
        ):
            with pytest.raises(KeyExtractionError, match="WeChatWin.dll"):
                extract_key_from_memory()

    @patch("wechat_manager.core.key_extractor.pymem.Pymem")
    @patch("wechat_manager.core.key_extractor.is_wechat_running")
    def test_extract_key_pattern_not_found(self, mock_is_running, mock_pymem):
        """Raise error when key pattern not found in memory."""
        mock_is_running.return_value = True

        mock_pm = MagicMock()
        mock_pymem.return_value = mock_pm

        mock_module = MagicMock()
        mock_module.lpBaseOfDll = 0x10000000
        mock_module.SizeOfImage = 0x1000000

        with patch(
            "wechat_manager.core.key_extractor.pymem.process.module_from_name",
            return_value=mock_module,
        ):
            with patch(
                "wechat_manager.core.key_extractor._search_key_pattern",
                return_value=None,
            ):
                with pytest.raises(KeyExtractionError, match="key pattern"):
                    extract_key_from_memory()


class TestErrorHandling:
    """Tests for custom exceptions."""

    def test_wechat_not_running_error(self):
        """WeChatNotRunningError can be raised with message."""
        with pytest.raises(WeChatNotRunningError) as exc_info:
            raise WeChatNotRunningError("WeChat is not running")
        assert "WeChat is not running" in str(exc_info.value)

    def test_key_extraction_error(self):
        """KeyExtractionError can be raised with message."""
        with pytest.raises(KeyExtractionError) as exc_info:
            raise KeyExtractionError("Failed to extract key")
        assert "Failed to extract key" in str(exc_info.value)

    def test_invalid_key_error(self):
        """InvalidKeyError can be raised with message."""
        with pytest.raises(InvalidKeyError) as exc_info:
            raise InvalidKeyError("Invalid key format")
        assert "Invalid key format" in str(exc_info.value)
