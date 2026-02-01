"""
共享的 pytest fixtures 和配置
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_app_config():
    """Isolate on-disk config from developer machine.

    Tests should not read/write user home config.json.
    """

    tmp_cfg_dir = Path(tempfile.mkdtemp())
    os.environ["WECHAT_MANAGER_CONFIG_DIR"] = str(tmp_cfg_dir)
    try:
        yield
    finally:
        try:
            shutil.rmtree(tmp_cfg_dir, ignore_errors=True)
        finally:
            os.environ.pop("WECHAT_MANAGER_CONFIG_DIR", None)


# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Mock 数据目录
MOCK_DATA_DIR = Path(__file__).parent / "mock_data"

# 已知的测试密钥 (32字节 = 64个十六进制字符)
# 这是一个测试用的密钥，不是真实的微信密钥
TEST_DB_KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
TEST_PASSWORD = "test_password_123"


@pytest.fixture
def mock_data_dir() -> Path:
    """返回 mock 数据目录路径"""
    return MOCK_DATA_DIR


@pytest.fixture
def test_db_key() -> str:
    """返回测试用的数据库密钥"""
    return TEST_DB_KEY


@pytest.fixture
def test_password() -> str:
    """返回测试用的应用密码"""
    return TEST_PASSWORD


@pytest.fixture
def temp_dir():
    """创建临时目录，测试后自动清理"""
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def mock_wechat_dir(temp_dir: Path) -> Path:
    """创建模拟的微信数据目录结构"""
    wechat_dir = temp_dir / "WeChat Files" / "wxid_test123456"
    msg_dir = wechat_dir / "Msg"
    msg_dir.mkdir(parents=True)

    # 创建非空占位文件（新版本验证要求非空）
    (msg_dir / "MicroMsg.db").write_bytes(b"x")
    (msg_dir / "MSG0.db").touch()

    return wechat_dir


@pytest.fixture
def mock_storage_dir(temp_dir: Path) -> Path:
    """创建模拟的程序存储目录"""
    storage_dir = temp_dir / "data"
    storage_dir.mkdir(parents=True)
    return storage_dir


@pytest.fixture
def storage_dir(temp_dir: Path) -> Path:
    """Create a temporary storage directory for encrypted storage tests"""
    storage = temp_dir / "data"
    storage.mkdir(parents=True, exist_ok=True)
    return storage


@pytest.fixture
def mock_backup_dir(temp_dir: Path) -> Path:
    """创建模拟的备份目录"""
    backup_dir = temp_dir / "backups"
    backup_dir.mkdir(parents=True)
    return backup_dir
