"""
Mode B - Convenient Mode with Backup/Delete/Restore

This mode provides convenient hiding by:
1. Creating a backup of the WeChat Msg directory
2. Extracting messages to encrypted storage
3. Deleting messages from the source WeChat DB
4. Supporting restoration from encrypted storage back to WeChat DB

CRITICAL SAFETY:
- NEVER operate while WeChat is running
- ALWAYS create and verify backup before deletion
- Support dry_run for testing without actual changes
"""

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from wechat_manager.core.db_handler import WeChatDBHandler
from wechat_manager.core.key_extractor import is_wechat_running
from wechat_manager.core.storage import EncryptedStorage
from wechat_manager.models.chat import Contact, Message


class PreFlightError(Exception):
    """Raised when pre-flight checks fail"""

    pass


class BackupError(Exception):
    """Raised when backup operations fail"""

    pass


class ModeB:
    """Convenient mode - backup, delete from source, restore

    This mode provides more convenient hiding by actually removing messages
    from the WeChat database. This requires:
    1. WeChat must NOT be running (database is locked otherwise)
    2. A verified backup must exist before any deletion
    3. Messages are first extracted to encrypted storage
    """

    def __init__(
        self, db_handler: WeChatDBHandler, storage: EncryptedStorage, backup_dir: str
    ):
        """Initialize Mode B

        Args:
            db_handler: Handler for WeChat database operations
            storage: Encrypted storage for hidden messages
            backup_dir: Directory to store backups
        """
        self.db_handler = db_handler
        self.storage = storage
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._last_backup_path: Optional[str] = None
        self._backup_verified: bool = False

    def pre_flight_check(self) -> Tuple[bool, Dict[str, bool]]:
        """Check if conditions are safe for Mode B operations.

        Returns:
            Tuple of (all_passed, check_results_dict)
            check_results_dict contains:
                - wechat_closed: True if WeChat.exe is not running
                - backup_dir_writable: True if backup directory is writable
                - db_accessible: True if WeChat databases can be accessed
        """
        # Mode B mutates the source databases. Weixin 4.x schema differs significantly
        # and is not supported by the current backup/delete/restore implementation.
        supported_mode_b = getattr(self.db_handler, "_version_hint", None) != 4

        checks = {
            "mode_b_supported": supported_mode_b,
            "wechat_closed": not is_wechat_running(),
            "backup_dir_writable": self._check_backup_writable(),
            "db_accessible": self._check_db_accessible(),
        }
        return all(checks.values()), checks

    def create_backup(self) -> str:
        """Create full backup of WeChat Msg directory.

        Returns:
            str: Path to the created backup

        Raises:
            BackupError: If backup creation fails
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"backup_{timestamp}"

        try:
            # Get source Msg directory
            source_msg_dir = self.db_handler.wechat_dir / "Msg"
            if not source_msg_dir.exists():
                raise BackupError(f"Source Msg directory not found: {source_msg_dir}")

            # Create backup directory and copy
            backup_msg_dir = backup_path / "Msg"
            shutil.copytree(str(source_msg_dir), str(backup_msg_dir))

            # Store backup path
            self._last_backup_path = str(backup_path)
            self._backup_verified = False

            return str(backup_path)

        except PermissionError as e:
            raise BackupError(f"Permission denied during backup: {e}")
        except Exception as e:
            raise BackupError(f"Backup failed: {e}")

    def verify_backup(self, backup_path: str) -> bool:
        """Verify backup is complete and databases are readable.

        Args:
            backup_path: Path to the backup directory

        Returns:
            bool: True if backup is valid and readable
        """
        backup_dir = Path(backup_path)
        backup_msg_dir = backup_dir / "Msg"

        # Check backup directory exists
        if not backup_msg_dir.exists():
            return False

        # Check MicroMsg.db exists and is readable
        micromsg_path = backup_msg_dir / "MicroMsg.db"
        if not micromsg_path.exists():
            return False

        try:
            conn = sqlite3.connect(str(micromsg_path))
            cursor = conn.execute("SELECT COUNT(*) FROM sqlite_master")
            cursor.fetchone()
            conn.close()
        except Exception:
            return False

        # Check at least one MSG database exists
        msg_files = list(backup_msg_dir.glob("MSG*.db"))
        if not msg_files:
            return False

        # Try to read one MSG database
        try:
            conn = sqlite3.connect(str(msg_files[0]))
            cursor = conn.execute("SELECT COUNT(*) FROM sqlite_master")
            cursor.fetchone()
            conn.close()
        except Exception:
            return False

        # Mark as verified if this is the last backup
        if self._last_backup_path == str(backup_dir):
            self._backup_verified = True

        return True

    def hide_messages(self, contact_id: str, dry_run: bool = False) -> dict:
        """Hide messages: extract to storage, then delete from source.

        Args:
            contact_id: Contact ID to hide messages for
            dry_run: If True, only simulate (no actual deletion)

        Returns:
            dict with keys: extracted, deleted, dry_run

        Raises:
            PreFlightError: If pre-flight checks fail
            BackupError: If backup is required but not available
        """
        # 1. Run pre-flight checks
        all_passed, checks = self.pre_flight_check()
        if not all_passed:
            failed_checks = [k for k, v in checks.items() if not v]
            raise PreFlightError(
                f"Pre-flight checks failed: {', '.join(failed_checks)}"
            )

        # 2. Create backup (if not dry_run)
        if not dry_run:
            if self._last_backup_path is None or not self._backup_verified:
                backup_path = self.create_backup()
                if not self.verify_backup(backup_path):
                    raise BackupError("Backup verification failed")

        # 3. Extract messages from WeChat DB
        messages = self.db_handler.get_messages(contact_id, limit=10000)

        # Store contact info
        contacts = self.db_handler.get_contacts()
        contact = next((c for c in contacts if c.id == contact_id), None)
        if contact:
            self.storage.store_contact(contact)

        # Store messages to encrypted storage
        extracted_count = 0
        if messages:
            # Convert to storage format (set original_id)
            storage_messages = []
            for msg in messages:
                storage_msg = Message(
                    id=msg.id,
                    contact_id=msg.contact_id,
                    original_id=msg.id,
                    content=msg.content,
                    create_time=msg.create_time,
                    is_sender=msg.is_sender,
                    msg_type=msg.msg_type,
                )
                storage_messages.append(storage_msg)
            extracted_count = self.storage.store_messages(contact_id, storage_messages)

        # 4. Delete from WeChat DB (if not dry_run)
        deleted_count = 0
        if not dry_run and messages:
            deleted_count = self._delete_messages_from_db(contact_id, messages)

        return {
            "extracted": extracted_count,
            "deleted": deleted_count,
            "dry_run": dry_run,
        }

    def restore_messages(self, contact_id: str, dry_run: bool = False) -> dict:
        """Restore messages from encrypted storage back to WeChat DB.

        Args:
            contact_id: Contact ID to restore messages for
            dry_run: If True, only simulate (no actual restoration)

        Returns:
            dict with keys: restored, dry_run

        Raises:
            PreFlightError: If pre-flight checks fail
        """
        # 1. Run pre-flight checks
        all_passed, checks = self.pre_flight_check()
        if not all_passed:
            failed_checks = [k for k, v in checks.items() if not v]
            raise PreFlightError(
                f"Pre-flight checks failed: {', '.join(failed_checks)}"
            )

        # 2. Read from encrypted storage
        messages = self.storage.get_messages(contact_id, limit=10000)

        if not messages:
            return {"restored": 0, "dry_run": dry_run}

        # 3. Insert into WeChat DB (if not dry_run)
        restored_count = 0
        if not dry_run:
            restored_count = self._insert_messages_to_db(contact_id, messages)

            # 4. Remove from encrypted storage (if not dry_run)
            if restored_count > 0:
                self.storage.delete_contact(contact_id)

        else:
            restored_count = len(messages)

        return {"restored": restored_count, "dry_run": dry_run}

    def _check_backup_writable(self) -> bool:
        """Check if backup directory is writable."""
        try:
            test_file = self.backup_dir / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            return True
        except Exception:
            return False

    def _check_db_accessible(self) -> bool:
        """Check if WeChat databases can be accessed (not locked)."""
        try:
            # Try to get databases list
            db_paths = self.db_handler.get_all_msg_databases()
            if not db_paths:
                return False

            # Try to open the first database
            conn = self.db_handler.connect(db_paths[0])
            conn.close()
            return True
        except Exception:
            return False

    def _delete_messages_from_db(self, contact_id: str, messages: List[Message]) -> int:
        """Delete messages from WeChat database.

        Args:
            contact_id: Contact ID whose messages to delete
            messages: List of messages to delete

        Returns:
            Number of messages deleted
        """
        deleted_count = 0
        msg_databases = self.db_handler.get_all_msg_databases()

        for db_path in msg_databases:
            try:
                conn = self.db_handler.connect(db_path)
                cursor = conn.cursor()

                # Get TalkerId for this contact
                cursor.execute(
                    "SELECT rowId FROM Name2Id WHERE UsrName = ?", (contact_id,)
                )
                row = cursor.fetchone()
                if row is None:
                    conn.close()
                    continue

                talker_id = row[0]

                # Delete messages for this contact
                cursor.execute("DELETE FROM MSG WHERE TalkerId = ?", (talker_id,))
                deleted_count += cursor.rowcount
                conn.commit()
                conn.close()

            except Exception:
                continue

        return deleted_count

    def _insert_messages_to_db(self, contact_id: str, messages: List[Message]) -> int:
        """Insert messages back into WeChat database.

        Args:
            contact_id: Contact ID for the messages
            messages: Messages to insert

        Returns:
            Number of messages inserted
        """
        if not messages:
            return 0

        msg_databases = self.db_handler.get_all_msg_databases()
        if not msg_databases:
            return 0

        # Use the first MSG database for insertion
        db_path = msg_databases[0]
        inserted_count = 0

        try:
            conn = self.db_handler.connect(db_path)
            cursor = conn.cursor()

            # Get or create TalkerId for this contact
            cursor.execute("SELECT rowId FROM Name2Id WHERE UsrName = ?", (contact_id,))
            row = cursor.fetchone()

            if row is None:
                # Insert into Name2Id first
                cursor.execute(
                    "INSERT INTO Name2Id (UsrName) VALUES (?)", (contact_id,)
                )
                talker_id = cursor.lastrowid
            else:
                talker_id = row[0]

            # Insert messages
            for msg in messages:
                cursor.execute(
                    """
                    INSERT INTO MSG (TalkerId, Type, SubType, CreateTime, IsSender, StrContent)
                    VALUES (?, ?, 0, ?, ?, ?)
                    """,
                    (
                        talker_id,
                        msg.msg_type,
                        msg.create_time,
                        1 if msg.is_sender else 0,
                        msg.content,
                    ),
                )
                inserted_count += 1

            conn.commit()
            conn.close()

        except Exception:
            pass

        return inserted_count
