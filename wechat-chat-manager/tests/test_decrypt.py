"""解密模块单元测试"""

import hashlib
import os
import struct
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from Crypto.Cipher import AES

from wechat_manager.core.decrypt import (
    HMAC_SIZE,
    IV_SIZE,
    KDF_ITER,
    KEY_SIZE,
    PAGE_SIZE,
    RESERVED_SIZE,
    SQLITE_FILE_HEADER,
    DecryptionError,
    InvalidKeyError,
    decrypt_database,
    decrypt_page,
    derive_keys,
    is_encrypted_database,
    verify_hmac,
    verify_key,
)


# 测试用的密钥
TEST_KEY_HEX = "0" * 64  # 64 个零


class TestDeriveKeys:
    """测试密钥派生"""

    def test_derive_keys_returns_correct_length(self):
        """派生密钥长度应该正确"""
        salt = os.urandom(16)
        decrypt_key, mac_key = derive_keys(TEST_KEY_HEX, salt)

        assert len(decrypt_key) == KEY_SIZE
        assert len(mac_key) == KEY_SIZE

    def test_derive_keys_deterministic(self):
        """相同输入应该产生相同输出"""
        salt = b"0123456789abcdef"
        key1 = derive_keys(TEST_KEY_HEX, salt)
        key2 = derive_keys(TEST_KEY_HEX, salt)

        assert key1 == key2

    def test_derive_keys_different_salts(self):
        """不同盐值应该产生不同密钥"""
        salt1 = b"0123456789abcdef"
        salt2 = b"fedcba9876543210"

        key1 = derive_keys(TEST_KEY_HEX, salt1)
        key2 = derive_keys(TEST_KEY_HEX, salt2)

        assert key1 != key2

    def test_derive_keys_mac_key_uses_xor_salt(self):
        """HMAC 密钥应该使用 XOR 0x3a 后的盐值"""
        salt = b"\x00" * 16
        _, mac_key = derive_keys(TEST_KEY_HEX, salt)

        # 手动计算预期的 mac_key
        key_bytes = bytes.fromhex(TEST_KEY_HEX)
        decrypt_key = hashlib.pbkdf2_hmac("sha1", key_bytes, salt, KDF_ITER, KEY_SIZE)
        expected_mac_salt = bytes([0x3A] * 16)  # 0x00 XOR 0x3a = 0x3a
        expected_mac_key = hashlib.pbkdf2_hmac(
            "sha1", decrypt_key, expected_mac_salt, 2, KEY_SIZE
        )

        assert mac_key == expected_mac_key


class TestVerifyHmac:
    """测试 HMAC 验证"""

    def create_page_with_hmac(self, mac_key: bytes, page_number: int) -> bytes:
        """创建带有效 HMAC 的测试页面"""
        import hmac

        # 数据部分 (PAGE_SIZE - 32)
        data = os.urandom(PAGE_SIZE - 32)

        # 计算 HMAC
        h = hmac.new(mac_key, digestmod="sha1")
        h.update(data)
        h.update(struct.pack("<I", page_number))
        hmac_value = h.digest()

        # 填充
        padding = b"\x00" * 12

        return data + hmac_value + padding

    def test_verify_hmac_valid(self):
        """有效 HMAC 应该通过验证"""
        salt = os.urandom(16)
        _, mac_key = derive_keys(TEST_KEY_HEX, salt)

        page = self.create_page_with_hmac(mac_key, 1)
        assert verify_hmac(mac_key, page, 1) is True

    def test_verify_hmac_invalid_page_number(self):
        """错误的页面编号应该验证失败"""
        salt = os.urandom(16)
        _, mac_key = derive_keys(TEST_KEY_HEX, salt)

        page = self.create_page_with_hmac(mac_key, 1)
        assert verify_hmac(mac_key, page, 2) is False

    def test_verify_hmac_corrupted_data(self):
        """损坏的数据应该验证失败"""
        salt = os.urandom(16)
        _, mac_key = derive_keys(TEST_KEY_HEX, salt)

        page = self.create_page_with_hmac(mac_key, 1)
        # 修改数据
        corrupted = b"\xff" + page[1:]
        assert verify_hmac(mac_key, corrupted, 1) is False


class TestDecryptPage:
    """测试页面解密"""

    def create_encrypted_page(self, decrypt_key: bytes) -> bytes:
        """创建加密的测试页面"""
        # 原始数据
        plaintext = b"Hello WeChat!" + b"\x00" * (PAGE_SIZE - RESERVED_SIZE - 13)

        # 随机 IV
        iv = os.urandom(IV_SIZE)

        # 加密
        cipher = AES.new(decrypt_key, AES.MODE_CBC, iv)
        encrypted = cipher.encrypt(plaintext)

        # HMAC 和填充 (测试用，不需要真实值)
        hmac_padding = os.urandom(HMAC_SIZE + 12)

        return encrypted + iv + hmac_padding

    def test_decrypt_page_success(self):
        """应该能正确解密页面"""
        salt = os.urandom(16)
        decrypt_key, _ = derive_keys(TEST_KEY_HEX, salt)

        page = self.create_encrypted_page(decrypt_key)
        decrypted = decrypt_page(decrypt_key, page, is_first_page=False)

        assert decrypted.startswith(b"Hello WeChat!")


class TestIsEncryptedDatabase:
    """测试加密检测"""

    def test_encrypted_database(self, tmp_path):
        """加密数据库应该被识别"""
        db_file = tmp_path / "encrypted.db"
        db_file.write_bytes(os.urandom(100))  # 随机数据，不是 SQLite 头

        assert is_encrypted_database(str(db_file)) is True

    def test_unencrypted_database(self, tmp_path):
        """未加密数据库应该被识别"""
        db_file = tmp_path / "plain.db"
        db_file.write_bytes(SQLITE_FILE_HEADER + b"\x00" * 84)

        assert is_encrypted_database(str(db_file)) is False

    def test_nonexistent_file(self, tmp_path):
        """不存在的文件应该返回 False"""
        assert is_encrypted_database(str(tmp_path / "nonexistent.db")) is False


class TestDecryptDatabase:
    """测试完整数据库解密"""

    def test_file_not_found(self, tmp_path):
        """不存在的文件应该抛出异常"""
        with pytest.raises(FileNotFoundError):
            decrypt_database(TEST_KEY_HEX, str(tmp_path / "nonexistent.db"))

    def test_file_too_small(self, tmp_path):
        """文件太小应该抛出异常"""
        small_file = tmp_path / "small.db"
        small_file.write_bytes(b"too small")

        with pytest.raises(DecryptionError, match="文件太小"):
            decrypt_database(TEST_KEY_HEX, str(small_file))

    def test_invalid_key(self, tmp_path):
        """无效密钥应该抛出异常"""
        # 创建一个看起来像加密数据库的文件
        db_file = tmp_path / "fake.db"
        # 随机盐值 + 随机页面数据
        fake_data = os.urandom(PAGE_SIZE)
        db_file.write_bytes(fake_data)

        with pytest.raises(InvalidKeyError):
            decrypt_database(TEST_KEY_HEX, str(db_file))


class TestVerifyKey:
    """测试密钥验证"""

    def test_invalid_key_returns_false(self, tmp_path):
        """无效密钥应该返回 False"""
        db_file = tmp_path / "test.db"
        db_file.write_bytes(os.urandom(PAGE_SIZE))

        assert verify_key(TEST_KEY_HEX, str(db_file)) is False

    def test_file_too_small_returns_false(self, tmp_path):
        """文件太小应该返回 False"""
        db_file = tmp_path / "small.db"
        db_file.write_bytes(b"small")

        assert verify_key(TEST_KEY_HEX, str(db_file)) is False

    def test_nonexistent_file_returns_false(self, tmp_path):
        """不存在的文件应该返回 False"""
        assert verify_key(TEST_KEY_HEX, str(tmp_path / "nonexistent.db")) is False
