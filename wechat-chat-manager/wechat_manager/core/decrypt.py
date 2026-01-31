"""
微信数据库解密模块

使用纯 Python (pycryptodome) 实现 SQLCipher 解密
支持 PC 微信数据库格式 (SQLCipher 4.x 风格)

加密参数:
- cipher_page_size: 4096 bytes
- kdf_iter: 64000
- cipher_hmac_algorithm: HMAC-SHA1
- cipher_kdf_algorithm: PBKDF2-HMAC-SHA1
"""

import hashlib
import hmac
import struct
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from Crypto.Cipher import AES

# SQLite 文件头
SQLITE_FILE_HEADER = b"SQLite format 3\x00"

# PC 微信加密参数 (SQLCipher 4.x 风格)
KEY_SIZE = 32  # AES-256
PAGE_SIZE = 4096
KDF_ITER = 64000
HMAC_SIZE = 20  # SHA1
IV_SIZE = 16
RESERVED_SIZE = 48  # IV(16) + HMAC(20) + padding(12)


class DecryptionError(Exception):
    """解密错误"""

    pass


class InvalidKeyError(DecryptionError):
    """密钥无效"""

    pass


def derive_keys(key_hex: str, salt: bytes) -> Tuple[bytes, bytes]:
    """从密钥和盐值派生解密密钥和 HMAC 密钥

    Args:
        key_hex: 64 字符的十六进制密钥
        salt: 16 字节的盐值

    Returns:
        (decrypt_key, mac_key) 元组
    """
    # 将十六进制密钥转换为字节
    key_bytes = bytes.fromhex(key_hex)

    # 使用 PBKDF2-HMAC-SHA1 派生解密密钥
    decrypt_key = hashlib.pbkdf2_hmac("sha1", key_bytes, salt, KDF_ITER, dklen=KEY_SIZE)

    # 派生 HMAC 密钥: 使用 salt XOR 0x3a 作为盐值
    mac_salt = bytes([x ^ 0x3A for x in salt])
    mac_key = hashlib.pbkdf2_hmac("sha1", decrypt_key, mac_salt, 2, KEY_SIZE)

    return decrypt_key, mac_key


def verify_hmac(mac_key: bytes, page_data: bytes, page_number: int) -> bool:
    """验证页面的 HMAC

    Args:
        mac_key: HMAC 密钥
        page_data: 页面数据
        page_number: 页面编号 (从 1 开始)

    Returns:
        HMAC 是否有效
    """
    # HMAC 计算范围: 页面数据除去最后 32 字节 (HMAC + padding)
    data_to_hash = page_data[:-32]

    # 创建 HMAC
    hash_mac = hmac.new(mac_key, digestmod="sha1")
    hash_mac.update(data_to_hash)
    # 添加页面编号 (little-endian 32-bit integer)
    hash_mac.update(struct.pack("<I", page_number))

    # 比较 HMAC (在 -32:-12 位置)
    expected_hmac = page_data[-32:-12]
    return hmac.compare_digest(hash_mac.digest(), expected_hmac)


def decrypt_page(decrypt_key: bytes, page_data: bytes, is_first_page: bool) -> bytes:
    """解密单个页面

    Args:
        decrypt_key: 解密密钥
        page_data: 加密的页面数据
        is_first_page: 是否为第一页 (第一页包含盐值)

    Returns:
        解密后的页面数据
    """
    # 提取 IV (在 -48:-32 位置)
    iv = page_data[-RESERVED_SIZE : -RESERVED_SIZE + IV_SIZE]

    # 提取加密数据
    encrypted_data = page_data[:-RESERVED_SIZE]

    # AES-256-CBC 解密
    cipher = AES.new(decrypt_key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(encrypted_data)

    return decrypted


def decrypt_database(
    key_hex: str, encrypted_path: str, output_path: Optional[str] = None
) -> str:
    """解密微信数据库文件

    Args:
        key_hex: 64 字符的十六进制密钥
        encrypted_path: 加密数据库文件路径
        output_path: 解密后文件保存路径 (可选, 默认创建临时文件)

    Returns:
        解密后的数据库文件路径

    Raises:
        InvalidKeyError: 密钥无效
        DecryptionError: 解密失败
        FileNotFoundError: 加密文件不存在
    """
    encrypted_path = Path(encrypted_path)
    if not encrypted_path.exists():
        raise FileNotFoundError(f"加密文件不存在: {encrypted_path}")

    # 读取加密数据库
    with open(encrypted_path, "rb") as f:
        encrypted_data = f.read()

    # 检查文件大小
    if len(encrypted_data) < PAGE_SIZE:
        raise DecryptionError(
            f"文件太小，不是有效的加密数据库: {len(encrypted_data)} bytes"
        )

    # 提取盐值 (前 16 字节)
    salt = encrypted_data[:16]

    # 派生密钥
    decrypt_key, mac_key = derive_keys(key_hex, salt)

    # 验证第一页的 HMAC
    first_page = encrypted_data[16:PAGE_SIZE]
    if not verify_hmac(mac_key, first_page, 1):
        raise InvalidKeyError("HMAC 验证失败 - 密钥可能不正确")

    # 创建输出文件
    if output_path is None:
        # 创建临时文件
        fd, output_path = tempfile.mkstemp(suffix=".db")
        import os

        os.close(fd)

    # 解密并写入输出文件
    with open(output_path, "wb") as f:
        # 解密第一页
        decrypted_first = decrypt_page(decrypt_key, first_page, is_first_page=True)

        # 写入 SQLite 文件头
        f.write(SQLITE_FILE_HEADER)
        # 写入解密数据 (跳过原来的文件头位置)
        f.write(decrypted_first[16:])
        # 写入保留区域 (IV + HMAC + padding)
        f.write(first_page[-RESERVED_SIZE:])

        # 处理剩余页面
        page_number = 2
        for offset in range(PAGE_SIZE, len(encrypted_data), PAGE_SIZE):
            page = encrypted_data[offset : offset + PAGE_SIZE]
            if len(page) < PAGE_SIZE:
                # 不完整的页面，跳过
                break

            # 解密页面
            decrypted = decrypt_page(decrypt_key, page, is_first_page=False)
            f.write(decrypted)
            f.write(page[-RESERVED_SIZE:])

            page_number += 1

    return output_path


def is_encrypted_database(db_path: str) -> bool:
    """检查数据库文件是否是加密的

    Args:
        db_path: 数据库文件路径

    Returns:
        True 如果文件是加密的 (不以 SQLite 文件头开始)
    """
    try:
        with open(db_path, "rb") as f:
            header = f.read(16)
        return not header.startswith(SQLITE_FILE_HEADER)
    except (OSError, IOError):
        return False


def verify_key(key_hex: str, db_path: str) -> bool:
    """验证密钥是否能解密指定的数据库

    Args:
        key_hex: 64 字符的十六进制密钥
        db_path: 加密数据库文件路径

    Returns:
        True 如果密钥有效
    """
    try:
        with open(db_path, "rb") as f:
            # 读取盐值和第一页
            salt = f.read(16)
            first_page = f.read(PAGE_SIZE - 16)

        if len(first_page) < PAGE_SIZE - 16:
            return False

        # 派生密钥
        decrypt_key, mac_key = derive_keys(key_hex, salt)

        # 验证 HMAC
        return verify_hmac(mac_key, first_page, 1)
    except Exception:
        return False
