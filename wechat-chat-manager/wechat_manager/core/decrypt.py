"""WeChat/Weixin database decryption.

This module implements SQLCipher-like page decryption in pure Python.

Supported profiles:
- V3 (legacy): PBKDF2-HMAC-SHA1 (64000), HMAC-SHA1, reserve=48
- V4 (Weixin 4.x): PBKDF2-HMAC-SHA512 (256000), HMAC-SHA512, reserve=80
"""

import hashlib
import hmac
import struct
import tempfile
from pathlib import Path
from dataclasses import dataclass, replace
from typing import Optional, Tuple, Literal

from Crypto.Cipher import AES

# SQLite 文件头
SQLITE_FILE_HEADER = b"SQLite format 3\x00"

# Common parameters
KEY_SIZE = 32  # AES-256
PAGE_SIZE = 4096
KDF_ITER = 64000
HMAC_SIZE = 20  # SHA1
IV_SIZE = 16
RESERVED_SIZE = 48  # IV(16) + HMAC(20) + padding(12)

# Weixin 4.x (SQLCipher 4 defaults)
V4_KDF_ITER = 256000
V4_HMAC_SIZE = 64  # SHA512
V4_RESERVED_SIZE = 80  # IV(16) + HMAC(64)


@dataclass(frozen=True)
class CipherProfile:
    version: int
    kdf_hash: str
    kdf_iter: int
    hmac_hash: str
    hmac_size: int
    reserved_size: int
    mac_key_mode: Literal["passphrase", "enc_key_iter2"]
    page_num_endian: Literal["be", "le"]
    kdf_mode: Literal["pbkdf2", "raw"]


_PROFILE_V3 = CipherProfile(
    version=3,
    kdf_hash="sha1",
    kdf_iter=KDF_ITER,
    hmac_hash="sha1",
    hmac_size=HMAC_SIZE,
    reserved_size=RESERVED_SIZE,
    mac_key_mode="enc_key_iter2",
    page_num_endian="le",
    kdf_mode="pbkdf2",
)

_PROFILE_V4_DEFAULT = CipherProfile(
    version=4,
    kdf_hash="sha512",
    kdf_iter=V4_KDF_ITER,
    hmac_hash="sha512",
    hmac_size=V4_HMAC_SIZE,
    reserved_size=V4_RESERVED_SIZE,
    mac_key_mode="passphrase",
    page_num_endian="be",
    kdf_mode="pbkdf2",
)


class DecryptionError(Exception):
    """解密错误"""

    pass


class InvalidKeyError(DecryptionError):
    """密钥无效"""

    pass


def _mask_salt(salt: bytes) -> bytes:
    return bytes([b ^ 0x3A for b in salt])


def _derive_keys_for_profile(
    key_hex: str, salt: bytes, profile: CipherProfile
) -> Tuple[bytes, bytes]:
    key_bytes = bytes.fromhex(key_hex)

    if profile.kdf_mode == "pbkdf2":
        decrypt_key = hashlib.pbkdf2_hmac(
            profile.kdf_hash, key_bytes, salt, profile.kdf_iter, dklen=KEY_SIZE
        )
    else:
        # Raw mode: treat key bytes as already-derived encryption key
        decrypt_key = key_bytes

    mac_salt = _mask_salt(salt)
    if profile.mac_key_mode == "passphrase":
        mac_key = hashlib.pbkdf2_hmac(
            profile.kdf_hash, key_bytes, mac_salt, profile.kdf_iter, dklen=KEY_SIZE
        )
    else:
        mac_key = hashlib.pbkdf2_hmac(
            profile.kdf_hash, decrypt_key, mac_salt, 2, dklen=KEY_SIZE
        )

    return decrypt_key, mac_key


def _page_num_bytes(page_number: int, endian: Literal["be", "le"]) -> bytes:
    return struct.pack(">I" if endian == "be" else "<I", int(page_number))


def _hmac_slices(
    page_data: bytes, profile: CipherProfile
) -> Optional[Tuple[bytes, bytes, bytes]]:
    """Return (data_to_hash, expected_hmac, iv) for a page buffer.

    page_data is either:
    - first page without salt (PAGE_SIZE - 16 bytes)
    - a full page (PAGE_SIZE bytes)
    """
    page_len = len(page_data)
    if page_len < profile.reserved_size:
        return None
    if profile.reserved_size <= IV_SIZE:
        return None

    cipher_end = page_len - profile.reserved_size
    trail_size = profile.reserved_size - IV_SIZE
    data_end = page_len - trail_size

    iv = page_data[cipher_end : cipher_end + IV_SIZE]
    expected_hmac = page_data[data_end : data_end + profile.hmac_size]

    if len(iv) != IV_SIZE:
        return None
    if len(expected_hmac) != profile.hmac_size:
        return None

    data_to_hash = page_data[:data_end]
    return data_to_hash, expected_hmac, iv


def _verify_hmac_for_profile(
    mac_key: bytes, page_data: bytes, page_number: int, profile: CipherProfile
) -> bool:
    slices = _hmac_slices(page_data, profile)
    if slices is None:
        return False
    data_to_hash, expected_hmac, _iv = slices

    hm = hmac.new(mac_key, digestmod=profile.hmac_hash)
    hm.update(data_to_hash)
    hm.update(_page_num_bytes(page_number, profile.page_num_endian))
    digest = hm.digest()
    if len(digest) != profile.hmac_size:
        digest = digest[: profile.hmac_size]
    return hmac.compare_digest(digest, expected_hmac)


def _decrypt_page_for_profile(
    decrypt_key: bytes, page_data: bytes, profile: CipherProfile
) -> bytes:
    slices = _hmac_slices(page_data, profile)
    if slices is None:
        raise DecryptionError("Invalid page layout")
    _data_to_hash, _expected_hmac, iv = slices

    cipher_end = len(page_data) - profile.reserved_size
    ciphertext = page_data[:cipher_end]
    if len(ciphertext) % 16 != 0:
        raise DecryptionError("Ciphertext length is not a multiple of 16")

    cipher = AES.new(decrypt_key, AES.MODE_CBC, iv)
    return cipher.decrypt(ciphertext)


def _candidate_profiles(version_hint: Optional[int]) -> list[CipherProfile]:
    if version_hint == 3:
        # Keep legacy behavior by default.
        return [_PROFILE_V3]

    if version_hint == 4:
        base = _PROFILE_V4_DEFAULT
        # Weixin 4.x may keep legacy SQLCipher3 parameters, so try V3 first.
        return [
            _PROFILE_V3,
            base,
            replace(base, page_num_endian="le"),
            replace(base, mac_key_mode="enc_key_iter2"),
            replace(base, mac_key_mode="enc_key_iter2", page_num_endian="le"),
            replace(base, kdf_mode="raw"),
            replace(base, kdf_mode="raw", page_num_endian="le"),
            replace(base, kdf_mode="raw", mac_key_mode="enc_key_iter2"),
            replace(
                base,
                kdf_mode="raw",
                mac_key_mode="enc_key_iter2",
                page_num_endian="le",
            ),
        ]

    # Auto-detect: try V3 (fast) then V4.
    return _candidate_profiles(3) + _candidate_profiles(4)


def _select_profile(
    key_hex: str, encrypted_data: bytes, version_hint: Optional[int]
) -> Optional[CipherProfile]:
    if len(encrypted_data) < PAGE_SIZE:
        return None

    salt = encrypted_data[:16]
    page1 = encrypted_data[16:PAGE_SIZE]
    page2 = (
        encrypted_data[PAGE_SIZE : PAGE_SIZE * 2]
        if len(encrypted_data) >= PAGE_SIZE * 2
        else None
    )

    for profile in _candidate_profiles(version_hint):
        try:
            _dec_key, mac_key = _derive_keys_for_profile(key_hex, salt, profile)
            if not _verify_hmac_for_profile(mac_key, page1, 1, profile):
                continue
            if page2 is not None and len(page2) == PAGE_SIZE:
                if not _verify_hmac_for_profile(mac_key, page2, 2, profile):
                    continue
            return profile
        except Exception:
            continue

    return None


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
    key_hex: str,
    encrypted_path: str,
    output_path: Optional[str] = None,
    version_hint: Optional[int] = None,
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

    salt = encrypted_data[:16]
    first_page = encrypted_data[16:PAGE_SIZE]

    profile = _select_profile(key_hex, encrypted_data[: PAGE_SIZE * 2], version_hint)
    if profile is None:
        raise InvalidKeyError("HMAC 验证失败 - 密钥或解密参数不正确")

    decrypt_key, mac_key = _derive_keys_for_profile(key_hex, salt, profile)
    if not _verify_hmac_for_profile(mac_key, first_page, 1, profile):
        raise InvalidKeyError("HMAC 验证失败 - 密钥或解密参数不正确")

    # 创建输出文件
    if output_path is None:
        # 创建临时文件
        fd, output_path = tempfile.mkstemp(suffix=".db")
        import os

        os.close(fd)

    # 解密并写入输出文件
    with open(output_path, "wb") as f:
        # 解密第一页 (ciphertext only)
        decrypted_first = _decrypt_page_for_profile(decrypt_key, first_page, profile)

        # 写入 SQLite 文件头 + 第一页 payload + reserved 区
        f.write(SQLITE_FILE_HEADER)
        f.write(decrypted_first)
        f.write(first_page[-profile.reserved_size :])

        # 处理剩余页面
        page_number = 2
        for offset in range(PAGE_SIZE, len(encrypted_data), PAGE_SIZE):
            page = encrypted_data[offset : offset + PAGE_SIZE]
            if len(page) < PAGE_SIZE:
                # 不完整的页面，跳过
                break

            # 可选：验证每页 HMAC（开销较大），这里跳过以提升速度
            decrypted = _decrypt_page_for_profile(decrypt_key, page, profile)
            f.write(decrypted)
            f.write(page[-profile.reserved_size :])

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


def verify_key(key_hex: str, db_path: str, version_hint: Optional[int] = None) -> bool:
    """验证密钥是否能解密指定的数据库

    Args:
        key_hex: 64 字符的十六进制密钥
        db_path: 加密数据库文件路径

    Returns:
        True 如果密钥有效
    """
    try:
        p = Path(db_path)
        if not p.exists():
            return False

        with open(p, "rb") as f:
            head = f.read(PAGE_SIZE * 2)

        if len(head) < PAGE_SIZE:
            return False

        profile = _select_profile(key_hex, head, version_hint)
        return profile is not None
    except Exception:
        return False
