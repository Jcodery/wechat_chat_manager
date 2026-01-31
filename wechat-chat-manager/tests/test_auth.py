"""
Tests for app password authentication module
"""

import pytest
from unittest.mock import patch, MagicMock
import keyring
from wechat_manager.core.auth import AuthManager, SERVICE_NAME, HASH_KEY, SALT_KEY


@pytest.fixture
def mock_keyring():
    """Mock keyring for testing without accessing system keyring"""
    storage = {}

    def mock_get(service, key):
        return storage.get(f"{service}:{key}")

    def mock_set(service, key, value):
        storage[f"{service}:{key}"] = value

    def mock_delete(service, key):
        k = f"{service}:{key}"
        if k in storage:
            del storage[k]
        else:
            raise keyring.errors.PasswordDeleteError()

    with (
        patch("keyring.get_password", side_effect=mock_get),
        patch("keyring.set_password", side_effect=mock_set),
        patch("keyring.delete_password", side_effect=mock_delete),
    ):
        yield storage


def test_is_password_set_when_not_set(mock_keyring):
    """Test checking if password is set when none exists"""
    auth = AuthManager()
    assert auth.is_password_set() is False


def test_set_password_success(mock_keyring):
    """Test setting initial password"""
    auth = AuthManager()
    result = auth.set_password("test_password_123")

    assert result is True
    assert auth.is_password_set() is True
    # Verify both hash and salt are stored
    assert mock_keyring.get(f"{SERVICE_NAME}:{HASH_KEY}") is not None
    assert mock_keyring.get(f"{SERVICE_NAME}:{SALT_KEY}") is not None


def test_set_password_twice_fails(mock_keyring):
    """Test that setting password twice is not allowed"""
    auth = AuthManager()

    # First set should succeed
    assert auth.set_password("first_password") is True

    # Second set should fail
    assert auth.set_password("second_password") is False


def test_verify_password_correct(mock_keyring):
    """Test verifying correct password"""
    auth = AuthManager()
    auth.set_password("test_password_123")

    assert auth.verify_password("test_password_123") is True


def test_verify_password_incorrect(mock_keyring):
    """Test verifying incorrect password"""
    auth = AuthManager()
    auth.set_password("test_password_123")

    assert auth.verify_password("wrong_password") is False


def test_verify_password_not_set(mock_keyring):
    """Test verifying password when none is set"""
    auth = AuthManager()

    assert auth.verify_password("any_password") is False


def test_change_password_success(mock_keyring):
    """Test changing password with correct old password"""
    auth = AuthManager()
    auth.set_password("old_password_123")

    # Change password
    result = auth.change_password("old_password_123", "new_password_456")
    assert result is True

    # Old password should not work
    assert auth.verify_password("old_password_123") is False

    # New password should work
    assert auth.verify_password("new_password_456") is True


def test_change_password_wrong_old_password(mock_keyring):
    """Test changing password with wrong old password"""
    auth = AuthManager()
    auth.set_password("old_password_123")

    # Change password with wrong old password
    result = auth.change_password("wrong_password", "new_password_456")
    assert result is False

    # Old password should still work
    assert auth.verify_password("old_password_123") is True


def test_password_hash_not_plaintext(mock_keyring):
    """Test that stored password is not plaintext"""
    auth = AuthManager()
    password = "test_password_123"
    auth.set_password(password)

    stored_hash = mock_keyring.get(f"{SERVICE_NAME}:{HASH_KEY}")

    # Hash should not contain plaintext password
    assert stored_hash != password
    assert password not in stored_hash


def test_different_passwords_different_hashes(mock_keyring):
    """Test that different passwords produce different hashes"""
    storage1 = {}
    storage2 = {}

    def mock_get1(service, key):
        return storage1.get(f"{service}:{key}")

    def mock_set1(service, key, value):
        storage1[f"{service}:{key}"] = value

    def mock_delete1(service, key):
        k = f"{service}:{key}"
        if k in storage1:
            del storage1[k]

    def mock_get2(service, key):
        return storage2.get(f"{service}:{key}")

    def mock_set2(service, key, value):
        storage2[f"{service}:{key}"] = value

    def mock_delete2(service, key):
        k = f"{service}:{key}"
        if k in storage2:
            del storage2[k]

    with (
        patch("keyring.get_password", side_effect=mock_get1),
        patch("keyring.set_password", side_effect=mock_set1),
        patch("keyring.delete_password", side_effect=mock_delete1),
    ):
        auth1 = AuthManager()
        auth1.set_password("password_one")
        hash1 = storage1.get(f"{SERVICE_NAME}:{HASH_KEY}")

    with (
        patch("keyring.get_password", side_effect=mock_get2),
        patch("keyring.set_password", side_effect=mock_set2),
        patch("keyring.delete_password", side_effect=mock_delete2),
    ):
        auth2 = AuthManager()
        auth2.set_password("password_two")
        hash2 = storage2.get(f"{SERVICE_NAME}:{HASH_KEY}")

    # Different passwords should produce different hashes
    assert hash1 != hash2
