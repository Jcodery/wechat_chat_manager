"""
Encrypted local storage for hidden chat records.

Uses PBKDF2 key derivation and SQLite for storage.
For MVP, uses standard sqlite3 - production should use sqlcipher3.
"""

from pathlib import Path
from typing import List, Optional
import sqlite3
import os

from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256

from wechat_manager.models.chat import Contact, Message


class EncryptedStorage:
    PBKDF2_ITERATIONS = 100000
    KEY_LENGTH = 32

    def __init__(self, storage_path: str, password: str):
        self.storage_path = Path(storage_path)
        self.db_path = self.storage_path / "hidden_chats.db"
        self._key = self._derive_key(password)
        self._ensure_storage_exists()

    def _derive_key(self, password: str) -> bytes:
        salt_path = self.storage_path / ".salt"
        if salt_path.exists():
            salt = salt_path.read_bytes()
        else:
            salt = os.urandom(16)
            self.storage_path.mkdir(parents=True, exist_ok=True)
            salt_path.write_bytes(salt)
        return PBKDF2(
            password,
            salt,
            dkLen=self.KEY_LENGTH,
            count=self.PBKDF2_ITERATIONS,
            hmac_hash_module=SHA256,
        )

    def _ensure_storage_exists(self):
        self.storage_path.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    nickname TEXT,
                    remark TEXT,
                    contact_type INTEGER DEFAULT 0,
                    hidden_at INTEGER NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contact_id TEXT NOT NULL,
                    original_id INTEGER,
                    content TEXT NOT NULL,
                    create_time INTEGER NOT NULL,
                    is_sender INTEGER NOT NULL,
                    msg_type INTEGER DEFAULT 1,
                    FOREIGN KEY (contact_id) REFERENCES contacts(id)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_contact ON messages(contact_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_time ON messages(create_time)
            """)
            conn.commit()
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def store_contact(self, contact: Contact) -> bool:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO contacts (id, username, nickname, remark, contact_type, hidden_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    contact.id,
                    contact.username,
                    contact.nickname,
                    contact.remark,
                    contact.contact_type,
                    contact.hidden_at,
                ),
            )
            conn.commit()
            return True
        except sqlite3.Error:
            return False
        finally:
            conn.close()

    def store_messages(self, contact_id: str, messages: List[Message]) -> int:
        if not messages:
            return 0
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            count = 0
            for msg in messages:
                cursor.execute(
                    """
                    INSERT INTO messages (contact_id, original_id, content, create_time, is_sender, msg_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        contact_id,
                        msg.original_id,
                        msg.content,
                        msg.create_time,
                        1 if msg.is_sender else 0,
                        msg.msg_type,
                    ),
                )
                count += 1
            conn.commit()
            return count
        except sqlite3.Error:
            return 0
        finally:
            conn.close()

    def get_contact(self, contact_id: str) -> Optional[Contact]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, username, nickname, remark, contact_type, hidden_at
                FROM contacts WHERE id = ?
            """,
                (contact_id,),
            )
            row = cursor.fetchone()
            if row:
                return Contact(
                    id=row[0],
                    username=row[1],
                    nickname=row[2],
                    remark=row[3],
                    contact_type=row[4],
                    hidden_at=row[5],
                )
            return None
        finally:
            conn.close()

    def get_messages(self, contact_id: str, limit: int = 100) -> List[Message]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, contact_id, original_id, content, create_time, is_sender, msg_type
                FROM messages
                WHERE contact_id = ?
                ORDER BY create_time ASC
                LIMIT ?
            """,
                (contact_id, limit),
            )
            rows = cursor.fetchall()
            return [
                Message(
                    id=row[0],
                    contact_id=row[1],
                    original_id=row[2],
                    content=row[3],
                    create_time=row[4],
                    is_sender=bool(row[5]),
                    msg_type=row[6],
                )
                for row in rows
            ]
        finally:
            conn.close()

    def list_contacts(self) -> List[Contact]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, username, nickname, remark, contact_type, hidden_at
                FROM contacts
                ORDER BY hidden_at DESC
            """)
            rows = cursor.fetchall()
            return [
                Contact(
                    id=row[0],
                    username=row[1],
                    nickname=row[2],
                    remark=row[3],
                    contact_type=row[4],
                    hidden_at=row[5],
                )
                for row in rows
            ]
        finally:
            conn.close()

    def delete_contact(self, contact_id: str) -> bool:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE contact_id = ?", (contact_id,))
            cursor.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
            conn.commit()
            return cursor.rowcount > 0 or True
        except sqlite3.Error:
            return False
        finally:
            conn.close()

    def search_messages(self, query: str) -> List[Message]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, contact_id, original_id, content, create_time, is_sender, msg_type
                FROM messages
                WHERE content LIKE ?
                ORDER BY create_time ASC
            """,
                (f"%{query}%",),
            )
            rows = cursor.fetchall()
            return [
                Message(
                    id=row[0],
                    contact_id=row[1],
                    original_id=row[2],
                    content=row[3],
                    create_time=row[4],
                    is_sender=bool(row[5]),
                    msg_type=row[6],
                )
                for row in rows
            ]
        finally:
            conn.close()
