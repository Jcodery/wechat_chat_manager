"""
Tests for wechat_manager.core.mode_b - Mode B (Convenient Mode with Backup/Delete/Restore)

Tests cover:
- Backup creation and verification
- Pre-flight checks (WeChat closed, backup writable, DB accessible)
- Message hiding (extract + delete)
- Message restoration
- Dry-run mode
- Safety constraints (WeChat must be closed, backup required before delete)
"""

import sqlite3
import pytest
from pathlib import Path
import time

from wechat_manager.core.mode_b import ModeB, PreFlightError, BackupError
from wechat_manager.core.db_handler import WeChatDBHandler
from wechat_manager.core.storage import EncryptedStorage
from wechat_manager.models.chat import Contact, Message


# ============================================================================
# Fixtures
# ============================================================================


def create_mock_micromsg(path: Path) -> None:
    """Create mock MicroMsg.db database"""
    conn = sqlite3.connect(str(path))
    conn.execute("""CREATE TABLE Contact (
        UserName TEXT PRIMARY KEY,
        NickName TEXT,
        Alias TEXT,
        Remark TEXT,
        Type INTEGER
    )""")
    conn.execute("""CREATE TABLE ChatRoom (
        ChatRoomName TEXT PRIMARY KEY,
        UserNameList TEXT
    )""")
    # Insert test data
    conn.execute(
        "INSERT INTO Contact VALUES ('wxid_test1', '张三', 'zhangsan', '同事张三', 1)"
    )
    conn.execute("INSERT INTO Contact VALUES ('wxid_test2', '李四', NULL, NULL, 1)")
    conn.commit()
    conn.close()


def create_mock_msg(path: Path, talker_mapping: dict = None) -> None:
    """Create mock MSGn.db database"""
    conn = sqlite3.connect(str(path))
    conn.execute("""CREATE TABLE MSG (
        localId INTEGER PRIMARY KEY,
        TalkerId INTEGER,
        Type INTEGER,
        SubType INTEGER,
        CreateTime INTEGER,
        IsSender INTEGER,
        StrContent TEXT
    )""")
    conn.execute("""CREATE TABLE Name2Id (
        rowId INTEGER PRIMARY KEY,
        UsrName TEXT
    )""")

    if talker_mapping is None:
        talker_mapping = {1: "wxid_test1", 2: "wxid_test2"}

    for talker_id, username in talker_mapping.items():
        conn.execute("INSERT INTO Name2Id VALUES (?, ?)", (talker_id, username))

    # Insert test messages
    conn.execute("INSERT INTO MSG VALUES (1, 1, 1, 0, 1704067200, 0, '你好')")
    conn.execute("INSERT INTO MSG VALUES (2, 1, 1, 0, 1704067260, 1, '你好啊')")
    conn.execute("INSERT INTO MSG VALUES (3, 1, 1, 0, 1704067320, 0, '今天天气不错')")
    conn.execute("INSERT INTO MSG VALUES (4, 2, 1, 0, 1704067400, 1, '好的，收到')")
    conn.execute("INSERT INTO MSG VALUES (5, 2, 1, 0, 1704067460, 0, '谢谢')")
    conn.commit()
    conn.close()


@pytest.fixture
def mock_db_wechat_dir(temp_dir: Path) -> Path:
    """Create mock WeChat directory with complete database structure"""
    wechat_dir = temp_dir / "WeChat Files" / "wxid_testuser"
    msg_dir = wechat_dir / "Msg"
    msg_dir.mkdir(parents=True)

    create_mock_micromsg(msg_dir / "MicroMsg.db")
    create_mock_msg(msg_dir / "MSG0.db")

    return wechat_dir


@pytest.fixture
def backup_dir(temp_dir: Path) -> Path:
    """Create backup directory for tests"""
    backup = temp_dir / "backups"
    backup.mkdir(parents=True, exist_ok=True)
    return backup


@pytest.fixture
def storage_dir(temp_dir: Path) -> Path:
    """Create storage directory for encrypted storage"""
    storage = temp_dir / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    return storage


@pytest.fixture
def mock_wechat_closed(monkeypatch):
    """Mock WeChat as not running"""
    monkeypatch.setattr("wechat_manager.core.mode_b.is_wechat_running", lambda: False)


@pytest.fixture
def mock_wechat_running(monkeypatch):
    """Mock WeChat as running"""
    monkeypatch.setattr("wechat_manager.core.mode_b.is_wechat_running", lambda: True)


@pytest.fixture
def mode_b_instance(
    mock_db_wechat_dir: Path,
    storage_dir: Path,
    backup_dir: Path,
    test_db_key: str,
    test_password: str,
    mock_wechat_closed,
):
    """Create ModeB instance with all dependencies"""
    db_handler = WeChatDBHandler(str(mock_db_wechat_dir), test_db_key)
    storage = EncryptedStorage(str(storage_dir), test_password)
    return ModeB(db_handler, storage, str(backup_dir))


# ============================================================================
# Test: Create Backup
# ============================================================================


class TestCreateBackup:
    """Tests for backup creation"""

    def test_create_backup(self, mode_b_instance: ModeB, backup_dir: Path):
        """Test creating database backup"""
        backup_path = mode_b_instance.create_backup()

        # Verify backup was created
        assert backup_path is not None
        assert Path(backup_path).exists()

        # Verify backup contains Msg directory
        backup_msg_dir = Path(backup_path) / "Msg"
        assert backup_msg_dir.exists()

        # Verify databases were copied
        assert (backup_msg_dir / "MicroMsg.db").exists()
        assert (backup_msg_dir / "MSG0.db").exists()

    def test_backup_path_contains_timestamp(self, mode_b_instance: ModeB):
        """Test that backup path contains timestamp"""
        backup_path = mode_b_instance.create_backup()

        # Should match pattern: backup_YYYYMMDD_HHMMSS
        backup_name = Path(backup_path).name
        assert backup_name.startswith("backup_")
        assert len(backup_name) == 22  # backup_ + 8 date + _ + 6 time

    def test_backup_stores_last_path(self, mode_b_instance: ModeB):
        """Test that backup stores last backup path"""
        backup_path = mode_b_instance.create_backup()
        assert mode_b_instance._last_backup_path == backup_path


# ============================================================================
# Test: Verify Backup
# ============================================================================


class TestVerifyBackup:
    """Tests for backup verification"""

    def test_verify_backup(self, mode_b_instance: ModeB):
        """Test verifying backup is readable"""
        # Create a backup first
        backup_path = mode_b_instance.create_backup()

        # Verify it
        result = mode_b_instance.verify_backup(backup_path)
        assert result is True

    def test_verify_backup_nonexistent(self, mode_b_instance: ModeB, temp_dir: Path):
        """Test verifying non-existent backup returns False"""
        result = mode_b_instance.verify_backup(str(temp_dir / "nonexistent"))
        assert result is False

    def test_verify_backup_sets_verified_flag(self, mode_b_instance: ModeB):
        """Test that verification sets the verified flag"""
        backup_path = mode_b_instance.create_backup()
        assert mode_b_instance._backup_verified is False

        mode_b_instance.verify_backup(backup_path)
        assert mode_b_instance._backup_verified is True


# ============================================================================
# Test: Pre-flight Check
# ============================================================================


class TestPreFlightCheck:
    """Tests for pre-flight checks"""

    def test_pre_flight_check(self, mode_b_instance: ModeB):
        """Test pre-flight check passes when conditions are met"""
        all_passed, checks = mode_b_instance.pre_flight_check()

        assert all_passed is True
        assert checks["wechat_closed"] is True
        assert checks["backup_dir_writable"] is True
        assert checks["db_accessible"] is True

    def test_pre_flight_check_wechat_running(
        self,
        mock_db_wechat_dir: Path,
        storage_dir: Path,
        backup_dir: Path,
        test_db_key: str,
        test_password: str,
        mock_wechat_running,
    ):
        """Test pre-flight check fails when WeChat is running"""
        db_handler = WeChatDBHandler(str(mock_db_wechat_dir), test_db_key)
        storage = EncryptedStorage(str(storage_dir), test_password)
        mode_b = ModeB(db_handler, storage, str(backup_dir))

        all_passed, checks = mode_b.pre_flight_check()

        assert all_passed is False
        assert checks["wechat_closed"] is False


# ============================================================================
# Test: Delete Messages
# ============================================================================


class TestDeleteMessages:
    """Tests for message deletion"""

    def test_delete_messages(self, mode_b_instance: ModeB, mock_db_wechat_dir: Path):
        """Test deleting messages from WeChat DB"""
        # Hide messages (which includes deletion)
        result = mode_b_instance.hide_messages("wxid_test1", dry_run=False)

        # Verify extraction happened
        assert result["extracted"] > 0
        assert result["deleted"] > 0
        assert result["dry_run"] is False

        # Verify messages were deleted from source
        db_path = mock_db_wechat_dir / "Msg" / "MSG0.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM MSG WHERE TalkerId = 1")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0  # Messages should be deleted

    def test_delete_messages_extracts_to_storage(
        self, mode_b_instance: ModeB, storage_dir: Path
    ):
        """Test that messages are extracted to storage before deletion"""
        mode_b_instance.hide_messages("wxid_test1", dry_run=False)

        # Verify messages are in encrypted storage
        messages = mode_b_instance.storage.get_messages("wxid_test1")
        assert len(messages) > 0


# ============================================================================
# Test: Restore Messages
# ============================================================================


class TestRestoreMessages:
    """Tests for message restoration"""

    def test_restore_messages(self, mode_b_instance: ModeB, mock_db_wechat_dir: Path):
        """Test restoring messages to WeChat DB"""
        # First hide messages
        mode_b_instance.hide_messages("wxid_test1", dry_run=False)

        # Then restore them
        result = mode_b_instance.restore_messages("wxid_test1", dry_run=False)

        assert result["restored"] > 0
        assert result["dry_run"] is False

    def test_restore_removes_from_storage(self, mode_b_instance: ModeB):
        """Test that restoration removes messages from encrypted storage"""
        # First hide messages
        mode_b_instance.hide_messages("wxid_test1", dry_run=False)

        # Verify messages are in storage
        messages_before = mode_b_instance.storage.get_messages("wxid_test1")
        assert len(messages_before) > 0

        # Restore messages
        mode_b_instance.restore_messages("wxid_test1", dry_run=False)

        # Verify messages are removed from storage
        messages_after = mode_b_instance.storage.get_messages("wxid_test1")
        assert len(messages_after) == 0


# ============================================================================
# Test: Dry Run
# ============================================================================


class TestDryRun:
    """Tests for dry-run mode"""

    def test_dry_run(self, mode_b_instance: ModeB, mock_db_wechat_dir: Path):
        """Test dry-run mode (no actual changes)"""
        # Count messages before
        db_path = mock_db_wechat_dir / "Msg" / "MSG0.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM MSG WHERE TalkerId = 1")
        count_before = cursor.fetchone()[0]
        conn.close()

        # Run in dry_run mode
        result = mode_b_instance.hide_messages("wxid_test1", dry_run=True)

        assert result["dry_run"] is True
        assert result["extracted"] > 0
        assert result["deleted"] == 0  # No actual deletion

        # Verify messages still exist in source
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT COUNT(*) FROM MSG WHERE TalkerId = 1")
        count_after = cursor.fetchone()[0]
        conn.close()

        assert count_after == count_before  # No change

    def test_dry_run_restore(self, mode_b_instance: ModeB):
        """Test dry-run mode for restoration"""
        # First hide messages (not dry run)
        mode_b_instance.hide_messages("wxid_test1", dry_run=False)

        # Get messages count in storage
        messages_before = mode_b_instance.storage.get_messages("wxid_test1")

        # Restore in dry_run mode
        result = mode_b_instance.restore_messages("wxid_test1", dry_run=True)

        assert result["dry_run"] is True
        assert result["restored"] > 0

        # Verify messages still in storage (not removed)
        messages_after = mode_b_instance.storage.get_messages("wxid_test1")
        assert len(messages_after) == len(messages_before)


# ============================================================================
# Test: WeChat Must Be Closed
# ============================================================================


class TestWeChatMustBeClosed:
    """Tests that operations reject when WeChat is running"""

    def test_wechat_must_be_closed(
        self,
        mock_db_wechat_dir: Path,
        storage_dir: Path,
        backup_dir: Path,
        test_db_key: str,
        test_password: str,
        mock_wechat_running,
    ):
        """Test that operations reject if WeChat is running"""
        db_handler = WeChatDBHandler(str(mock_db_wechat_dir), test_db_key)
        storage = EncryptedStorage(str(storage_dir), test_password)
        mode_b = ModeB(db_handler, storage, str(backup_dir))

        # Should raise PreFlightError
        with pytest.raises(PreFlightError) as exc_info:
            mode_b.hide_messages("wxid_test1")

        assert "wechat_closed" in str(exc_info.value)

    def test_restore_rejects_when_wechat_running(
        self,
        mock_db_wechat_dir: Path,
        storage_dir: Path,
        backup_dir: Path,
        test_db_key: str,
        test_password: str,
        mock_wechat_running,
    ):
        """Test that restore rejects if WeChat is running"""
        db_handler = WeChatDBHandler(str(mock_db_wechat_dir), test_db_key)
        storage = EncryptedStorage(str(storage_dir), test_password)
        mode_b = ModeB(db_handler, storage, str(backup_dir))

        with pytest.raises(PreFlightError):
            mode_b.restore_messages("wxid_test1")


# ============================================================================
# Test: Backup Required
# ============================================================================


class TestBackupRequired:
    """Tests that backup is required before deletion"""

    def test_backup_required(self, mode_b_instance: ModeB):
        """Test that cannot delete without backup"""
        # The hide_messages method should automatically create and verify backup
        # before deletion, so this test verifies the backup was created

        result = mode_b_instance.hide_messages("wxid_test1", dry_run=False)

        # Backup should have been created
        assert mode_b_instance._last_backup_path is not None
        assert mode_b_instance._backup_verified is True

    def test_backup_created_automatically(self, mode_b_instance: ModeB):
        """Test that backup is created automatically during hide operation"""
        # Ensure no backup exists initially
        assert mode_b_instance._last_backup_path is None

        # Hide messages should create backup
        mode_b_instance.hide_messages("wxid_test1", dry_run=False)

        # Verify backup was created
        assert mode_b_instance._last_backup_path is not None
        assert Path(mode_b_instance._last_backup_path).exists()

    def test_dry_run_skips_backup(self, mode_b_instance: ModeB):
        """Test that dry_run mode skips backup creation"""
        mode_b_instance.hide_messages("wxid_test1", dry_run=True)

        # Backup should not be created in dry_run mode
        assert mode_b_instance._last_backup_path is None


# ============================================================================
# Test: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases"""

    def test_hide_nonexistent_contact(self, mode_b_instance: ModeB):
        """Test hiding messages for non-existent contact"""
        result = mode_b_instance.hide_messages("wxid_nonexistent", dry_run=False)

        assert result["extracted"] == 0
        assert result["deleted"] == 0

    def test_restore_nonexistent_contact(self, mode_b_instance: ModeB):
        """Test restoring messages for non-existent contact in storage"""
        result = mode_b_instance.restore_messages("wxid_nonexistent", dry_run=False)

        assert result["restored"] == 0

    def test_multiple_backups(self, mode_b_instance: ModeB):
        """Test creating multiple backups"""
        backup1 = mode_b_instance.create_backup()

        import time

        time.sleep(1)  # Ensure different timestamp

        backup2 = mode_b_instance.create_backup()

        assert backup1 != backup2
        assert Path(backup1).exists()
        assert Path(backup2).exists()
