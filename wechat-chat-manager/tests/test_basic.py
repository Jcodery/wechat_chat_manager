"""
基础测试 - 验证测试框架正常工作
"""

import pytest
from pathlib import Path


def test_fixtures_available(mock_data_dir, test_db_key, test_password):
    """测试 fixtures 是否正确加载"""
    assert mock_data_dir is not None
    assert isinstance(mock_data_dir, Path)
    assert test_db_key is not None
    assert len(test_db_key) == 64  # 32字节 = 64个十六进制字符
    assert test_password is not None


def test_temp_dir_fixture(temp_dir):
    """测试临时目录 fixture"""
    assert temp_dir.exists()
    assert temp_dir.is_dir()


def test_mock_wechat_dir_fixture(mock_wechat_dir):
    """测试模拟微信目录 fixture"""
    assert mock_wechat_dir.exists()
    assert (mock_wechat_dir / "Msg").exists()
    assert (mock_wechat_dir / "Msg" / "MicroMsg.db").exists()
    assert (mock_wechat_dir / "Msg" / "MSG0.db").exists()


def test_project_structure():
    """测试项目结构是否正确"""
    from pathlib import Path

    project_root = Path(__file__).parent.parent

    assert (project_root / "wechat_manager").exists()
    assert (project_root / "wechat_manager" / "__init__.py").exists()
    assert (project_root / "wechat_manager" / "core").exists()
    assert (project_root / "wechat_manager" / "api").exists()
    assert (project_root / "requirements.txt").exists()
