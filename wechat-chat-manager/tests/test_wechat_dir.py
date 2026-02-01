"""
Tests for WeChat Directory Detection Module

Tests cover:
- Auto-detection of WeChat directory
- Manual path input and validation
- Invalid path rejection
- Directory structure validation
- Finding wxid folders
"""

import pytest
import os
from pathlib import Path
from wechat_manager.core.wechat_dir import (
    auto_detect_wechat_dir,
    set_wechat_dir,
    validate_wechat_dir,
    get_wxid_folders,
    get_msg_dir,
    get_current_wechat_dir,
)


class TestAutoDetect:
    """Tests for auto_detect_wechat_dir function"""

    def test_auto_detect_with_valid_dir(self, temp_dir):
        """Test auto-detection when valid WeChat directory exists"""
        # Create a valid WeChat structure in temp_dir
        wechat_files = temp_dir / "WeChat Files"
        wxid_folder = wechat_files / "wxid_abc123"
        msg_dir = wxid_folder / "Msg"
        msg_dir.mkdir(parents=True)
        (msg_dir / "MicroMsg.db").write_bytes(b"x")

        # Temporarily patch DEFAULT_PATHS to use our temp directory
        from wechat_manager.core import wechat_dir as wechat_dir_module

        original_paths = wechat_dir_module.DEFAULT_PATHS
        try:
            wechat_dir_module.DEFAULT_PATHS = [str(wechat_files)]
            result = wechat_dir_module.auto_detect_wechat_dir()
            assert result is not None
            assert Path(result).exists()
        finally:
            wechat_dir_module.DEFAULT_PATHS = original_paths

    def test_auto_detect_no_valid_dir(self):
        """Test auto-detection returns None when no valid directory exists"""
        from wechat_manager.core import wechat_dir as wechat_dir_module

        original_paths = wechat_dir_module.DEFAULT_PATHS
        try:
            # Set paths to non-existent directories
            wechat_dir_module.DEFAULT_PATHS = [
                "/nonexistent/path1",
                "/nonexistent/path2",
            ]
            result = wechat_dir_module.auto_detect_wechat_dir()
            assert result is None
        finally:
            wechat_dir_module.DEFAULT_PATHS = original_paths


class TestManualPath:
    """Tests for set_wechat_dir function"""

    def test_manual_path_valid(self, temp_dir):
        """Test manually setting valid WeChat directory"""
        # Create valid structure
        wechat_files = temp_dir / "WeChat Files"
        wxid_folder = wechat_files / "wxid_def456"
        msg_dir = wxid_folder / "Msg"
        msg_dir.mkdir(parents=True)
        (msg_dir / "MicroMsg.db").write_bytes(b"x")

        result = set_wechat_dir(str(wechat_files))
        assert result is True
        assert get_current_wechat_dir() == str(wechat_files)

    def test_manual_path_invalid(self, temp_dir):
        """Test manually setting invalid WeChat directory"""
        # Create directory without proper structure
        invalid_dir = temp_dir / "InvalidWeChat"
        invalid_dir.mkdir()

        result = set_wechat_dir(str(invalid_dir))
        assert result is False
        # Current directory should not be changed if validation failed
        # (depends on previous state, but validation should have failed)


class TestInvalidPath:
    """Tests for validate_wechat_dir function with invalid paths"""

    def test_validate_nonexistent_path(self):
        """Test validation rejects non-existent path"""
        result = validate_wechat_dir("/nonexistent/wechat/path")
        assert result is False

    def test_validate_empty_directory(self, temp_dir):
        """Test validation rejects empty directory (no wxid folders)"""
        result = validate_wechat_dir(str(temp_dir))
        assert result is False

    def test_validate_no_msg_directory(self, temp_dir):
        """Test validation rejects wxid folder without Msg directory"""
        wxid_folder = temp_dir / "wxid_nomsdir"
        wxid_folder.mkdir()

        result = validate_wechat_dir(str(temp_dir))
        assert result is False

    def test_validate_directory_without_wxid_prefix(self, temp_dir):
        """Test validation rejects directory with wrong prefix"""
        # Create directory that doesn't start with wxid_
        invalid_folder = temp_dir / "wrongprefix_123"
        msg_dir = invalid_folder / "Msg"
        msg_dir.mkdir(parents=True)
        (msg_dir / "MicroMsg.db").write_bytes(b"x")

        result = validate_wechat_dir(str(temp_dir))
        assert result is False


class TestValidateStructure:
    """Tests for validate_wechat_dir function with valid structures"""

    def test_validate_structure_basic(self, temp_dir):
        """Test validation passes for correct directory structure"""
        wechat_files = temp_dir / "WeChat Files"
        wxid_folder = wechat_files / "wxid_ghi789"
        msg_dir = wxid_folder / "Msg"
        msg_dir.mkdir(parents=True)
        (msg_dir / "MicroMsg.db").write_bytes(b"x")
        (msg_dir / "MSG0.db").touch()

        result = validate_wechat_dir(str(wechat_files))
        assert result is True

    def test_validate_structure_multiple_wxid(self, temp_dir):
        """Test validation with multiple wxid folders"""
        wechat_files = temp_dir / "WeChat Files"

        # Create first wxid folder
        wxid_folder1 = wechat_files / "wxid_first"
        msg_dir1 = wxid_folder1 / "Msg"
        msg_dir1.mkdir(parents=True)
        (msg_dir1 / "MicroMsg.db").write_bytes(b"x")

        # Create second wxid folder
        wxid_folder2 = wechat_files / "wxid_second"
        msg_dir2 = wxid_folder2 / "Msg"
        msg_dir2.mkdir(parents=True)
        (msg_dir2 / "MicroMsg.db").write_bytes(b"x")

        result = validate_wechat_dir(str(wechat_files))
        assert result is True

    def test_validate_structure_with_config_dir(self, temp_dir):
        """Test validation with config directory"""
        wechat_files = temp_dir / "WeChat Files"
        wxid_folder = wechat_files / "wxid_jkl012"
        msg_dir = wxid_folder / "Msg"
        config_dir = wxid_folder / "config"

        msg_dir.mkdir(parents=True)
        config_dir.mkdir(parents=True)

        (msg_dir / "MicroMsg.db").write_bytes(b"x")
        (msg_dir / "MSG0.db").touch()

        result = validate_wechat_dir(str(wechat_files))
        assert result is True


class TestFindWxidFolders:
    """Tests for get_wxid_folders function"""

    def test_find_single_wxid_folder(self, temp_dir):
        """Test finding single wxid folder"""
        wechat_files = temp_dir / "WeChat Files"
        wxid_folder = wechat_files / "wxid_mno345"
        msg_dir = wxid_folder / "Msg"
        msg_dir.mkdir(parents=True)
        (msg_dir / "MicroMsg.db").write_bytes(b"x")

        folders = get_wxid_folders(str(wechat_files))
        assert len(folders) == 1
        assert str(wxid_folder) in folders

    def test_find_multiple_wxid_folders(self, temp_dir):
        """Test finding multiple wxid folders"""
        wechat_files = temp_dir / "WeChat Files"

        wxid_names = ["wxid_alpha", "wxid_beta", "wxid_gamma"]
        for wxid_name in wxid_names:
            wxid_folder = wechat_files / wxid_name
            msg_dir = wxid_folder / "Msg"
            msg_dir.mkdir(parents=True)
            (msg_dir / "MicroMsg.db").write_bytes(b"x")

        folders = get_wxid_folders(str(wechat_files))
        assert len(folders) == 3
        # Verify all wxid folders are found
        for wxid_name in wxid_names:
            assert any(wxid_name in folder for folder in folders)

    def test_find_wxid_folders_sorted(self, temp_dir):
        """Test that wxid folders are returned sorted"""
        wechat_files = temp_dir / "WeChat Files"

        wxid_names = ["wxid_zzz", "wxid_aaa", "wxid_mmm"]
        for wxid_name in wxid_names:
            wxid_folder = wechat_files / wxid_name
            msg_dir = wxid_folder / "Msg"
            msg_dir.mkdir(parents=True)
            (msg_dir / "MicroMsg.db").write_bytes(b"x")

        folders = get_wxid_folders(str(wechat_files))
        # Convert to comparable paths
        folder_names = [Path(f).name for f in folders]
        expected_order = sorted(wxid_names)
        assert folder_names == expected_order

    def test_find_wxid_folders_empty_dir(self, temp_dir):
        """Test finding wxid folders in empty directory"""
        folders = get_wxid_folders(str(temp_dir))
        assert folders == []

    def test_find_wxid_folders_nonexistent_dir(self):
        """Test finding wxid folders in non-existent directory"""
        folders = get_wxid_folders("/nonexistent/directory")
        assert folders == []


class TestGetMsgDir:
    """Tests for get_msg_dir function"""

    def test_get_msg_dir_basic(self, temp_dir):
        """Test getting Msg directory path"""
        wxid_path = temp_dir / "wxid_pqr678"
        msg_path = get_msg_dir(str(wxid_path))

        expected = str(wxid_path / "Msg")
        assert msg_path == expected

    def test_get_msg_dir_with_existing_structure(self, temp_dir):
        """Test getting Msg directory for existing structure"""
        wxid_path = temp_dir / "wxid_stu901"
        msg_dir = wxid_path / "Msg"
        msg_dir.mkdir(parents=True)
        (msg_dir / "MicroMsg.db").write_bytes(b"x")

        msg_path = get_msg_dir(str(wxid_path))

        assert msg_path == str(msg_dir)
        assert Path(msg_path).exists()


class TestGetCurrentDir:
    """Tests for get_current_wechat_dir function"""

    def test_get_current_dir_not_set(self):
        """Test getting current directory when none is set"""
        # Reset global state
        from wechat_manager.core import wechat_dir as wechat_dir_module

        wechat_dir_module._current_wechat_dir = None

        result = get_current_wechat_dir()
        assert result is None

    def test_get_current_dir_after_set(self, temp_dir):
        """Test getting current directory after setting it"""
        wechat_files = temp_dir / "WeChat Files"
        wxid_folder = wechat_files / "wxid_vwx234"
        msg_dir = wxid_folder / "Msg"
        msg_dir.mkdir(parents=True)
        (msg_dir / "MicroMsg.db").write_bytes(b"x")

        set_wechat_dir(str(wechat_files))
        result = get_current_wechat_dir()

        assert result == str(wechat_files)


class TestMockWechatDirFixture:
    """Tests using the mock_wechat_dir fixture"""

    def test_mock_fixture_structure(self, mock_wechat_dir):
        """Test that mock_wechat_dir fixture has correct structure"""
        assert mock_wechat_dir.exists()
        assert (mock_wechat_dir / "Msg").exists()
        assert (mock_wechat_dir / "Msg" / "MicroMsg.db").exists()
        assert (mock_wechat_dir / "Msg" / "MSG0.db").exists()

    def test_validate_mock_wechat_dir(self, mock_wechat_dir):
        """Test validation of mock_wechat_dir fixture parent"""
        parent = mock_wechat_dir.parent  # WeChat Files directory
        result = validate_wechat_dir(str(parent))
        assert result is True

    def test_find_wxid_in_mock_fixture(self, mock_wechat_dir):
        """Test finding wxid folders in mock fixture"""
        parent = mock_wechat_dir.parent  # WeChat Files directory
        folders = get_wxid_folders(str(parent))

        assert len(folders) == 1
        assert str(mock_wechat_dir) in folders
