"""
微信数据库处理模块

提供 SQLCipher 加密数据库的解密和读取功能
支持读取联系人、群聊和消息数据
"""

import os
import re
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

from wechat_manager.core.decrypt import (
    DecryptionError,
    InvalidKeyError,
    decrypt_database,
    is_encrypted_database,
)
from wechat_manager.models.chat import ChatRoom, Contact, Message


class WeChatDBHandler:
    """微信数据库处理器

    处理微信加密数据库的连接、解密和数据读取
    """

    def __init__(self, wechat_dir: str, key: str):
        """初始化数据库处理器

        Args:
            wechat_dir: 微信数据目录路径
            key: 数据库解密密钥（64个十六进制字符）

        Raises:
            ValueError: 密钥格式无效
        """
        self._validate_key(key)
        self.wechat_dir = Path(wechat_dir)
        self.key = key
        self._msg_dir = self.wechat_dir / "Msg"
        self._db_storage_dir = self.wechat_dir / "db_storage"

        # Layout/version hint
        self._version_hint: Optional[int] = None
        if (self._db_storage_dir / "contact" / "contact.db").exists():
            # Weixin 4.x db_storage layout
            self._version_hint = 4
        elif (self._msg_dir / "MicroMsg.db").exists():
            # Legacy Msg layout
            self._version_hint = 3

        # Cache decrypted DB file paths
        self._decrypted_cache: Dict[str, str] = {}

    def __del__(self):
        """清理临时解密文件"""
        self._cleanup_cache()

    def _cleanup_cache(self):
        """清理所有缓存的解密文件"""
        if not hasattr(self, "_decrypted_cache"):
            return
        for decrypted_path in self._decrypted_cache.values():
            try:
                if os.path.exists(decrypted_path):
                    os.remove(decrypted_path)
            except OSError:
                pass
        self._decrypted_cache.clear()

    @staticmethod
    def _validate_key(key: str) -> None:
        """验证密钥格式

        Args:
            key: 待验证的密钥

        Raises:
            ValueError: 密钥不是64个十六进制字符
        """
        if not key or len(key) != 64:
            raise ValueError("密钥必须是64个十六进制字符")

        # 检查是否都是十六进制字符
        if not re.match(r"^[0-9a-fA-F]{64}$", key):
            raise ValueError("密钥必须是64个十六进制字符")

    def connect(self, db_path: str) -> sqlite3.Connection:
        """连接到数据库（自动处理加密）

        对于加密的数据库，先解密到临时文件再连接
        对于未加密的数据库（测试用），直接连接

        Args:
            db_path: 数据库文件路径

        Returns:
            数据库连接对象

        Raises:
            DecryptionError: 解密失败
            InvalidKeyError: 密钥无效
        """
        # 检查是否已经解密过
        if db_path in self._decrypted_cache:
            return sqlite3.connect(self._decrypted_cache[db_path])

        # 检查是否是加密数据库
        if is_encrypted_database(db_path):
            # 解密到临时文件
            decrypted_path = decrypt_database(
                self.key, db_path, version_hint=self._version_hint
            )
            self._decrypted_cache[db_path] = decrypted_path
            return sqlite3.connect(decrypted_path)
        else:
            # 未加密的数据库（测试用），直接连接
            return sqlite3.connect(db_path)

    def _get_contacts_db_path(self) -> Path:
        # Prefer V4 db_storage layout if present and non-empty
        v4 = self._db_storage_dir / "contact" / "contact.db"
        if v4.exists() and v4.stat().st_size > 0:
            return v4
        return self._msg_dir / "MicroMsg.db"

    def _get_message_db_paths(self) -> List[str]:
        # V4: db_storage/message/message_*.db
        msg_dir = self._db_storage_dir / "message"
        if msg_dir.exists():
            dbs = []
            for p in msg_dir.glob("message_*.db"):
                # Keep only shards like message_0.db, exclude message_fts.db, message_resource.db
                name = p.name
                if not name.startswith("message_"):
                    continue
                suffix = name[len("message_") : -len(".db")]
                if suffix.isdigit():
                    dbs.append(p)
            dbs.sort(key=lambda p: int(p.stem.split("_")[-1]))
            return [str(p) for p in dbs]

        # V3: Msg/MSG*.db
        msg_files = []
        if self._msg_dir.exists():
            for file_path in self._msg_dir.glob("MSG*.db"):
                if file_path.is_file():
                    msg_files.append(str(file_path))
        msg_files.sort(key=lambda p: Path(p).name)
        return msg_files

    @staticmethod
    def _find_table(conn: sqlite3.Connection, candidates: List[str]) -> Optional[str]:
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        except Exception:
            return None

        table_map = {str(r[0]).lower(): str(r[0]) for r in rows}
        for c in candidates:
            hit = table_map.get(c.lower())
            if hit:
                return hit
        return None

    def get_contacts(self) -> List[Contact]:
        """读取联系人列表

        从 MicroMsg.db 的 Contact 表中读取联系人信息

        Returns:
            联系人对象列表
        """
        db_path = self._get_contacts_db_path()
        if not db_path.exists() or db_path.stat().st_size == 0:
            raise DecryptionError(f"Contacts database is missing or empty: {db_path}")

        conn = self.connect(str(db_path))

        try:
            contact_table = self._find_table(conn, ["Contact", "contact"])
            if not contact_table:
                raise DecryptionError("Contact table not found")

            cursor = conn.execute(
                f"""
                SELECT UserName, NickName, Alias, Remark, Type
                FROM {contact_table}
                WHERE Type IN (1, 2, 3)
            """
            )

            contacts = []
            for row in cursor.fetchall():
                user_name = row[0]
                contact = Contact(
                    id=user_name,
                    username=user_name,
                    nickname=row[1] or "",
                    alias=row[2],
                    remark=row[3],
                    contact_type=row[4],
                )
                contacts.append(contact)

            return contacts
        finally:
            conn.close()

    def get_chatrooms(self) -> List[ChatRoom]:
        """读取群聊列表

        从 MicroMsg.db 的 ChatRoom 表中读取群聊信息

        Returns:
            群聊对象列表
        """
        db_path = self._get_contacts_db_path()
        if not db_path.exists() or db_path.stat().st_size == 0:
            raise DecryptionError(f"Contacts database is missing or empty: {db_path}")

        conn = self.connect(str(db_path))

        try:
            chatroom_table = self._find_table(conn, ["ChatRoom", "chatroom"])
            if not chatroom_table:
                return []

            cursor = conn.execute(
                f"""
                SELECT ChatRoomName, UserNameList
                FROM {chatroom_table}
            """
            )

            chatrooms = []
            for row in cursor.fetchall():
                # UserNameList 是以分号分隔的成员列表
                members = row[1].split(";") if row[1] else []
                # 过滤空字符串
                members = [m for m in members if m]

                chatroom = ChatRoom(name=row[0], members=members)
                chatrooms.append(chatroom)

            return chatrooms
        finally:
            conn.close()

    def get_messages(self, contact_id: str, limit: int = 100) -> List[Message]:
        """读取指定联系人的消息

        从所有 MSGn.db 文件中读取指定联系人的消息

        Args:
            contact_id: 联系人用户名（wxid）
            limit: 返回消息数量限制

        Returns:
            消息对象列表
        """
        all_messages = []
        msg_databases = self.get_all_msg_databases()

        for db_path in msg_databases:
            messages = self._get_messages_from_db(db_path, contact_id, limit)
            all_messages.extend(messages)

            # 如果已经达到限制，提前退出
            if len(all_messages) >= limit:
                break

        # 按时间排序并限制数量
        all_messages.sort(key=lambda m: m.create_time)
        return all_messages[:limit]

    def _get_messages_from_db(
        self, db_path: str, contact_id: str, limit: int
    ) -> List[Message]:
        """从单个数据库文件读取消息

        Args:
            db_path: 数据库文件路径
            contact_id: 联系人用户名
            limit: 消息数量限制

        Returns:
            消息对象列表
        """
        conn = self.connect(db_path)

        try:
            msg_table = self._find_table(conn, ["MSG", "msg"])
            if not msg_table:
                return []

            cols = conn.execute(f"PRAGMA table_info({msg_table})").fetchall()
            col_map = {str(r[1]).lower(): str(r[1]) for r in cols}

            col_local_id = col_map.get("localid")
            col_type = col_map.get("type")
            col_create = col_map.get("createtime")
            col_sender = col_map.get("issender")
            col_content = col_map.get("strcontent") or col_map.get("content")

            if not (
                col_local_id and col_type and col_create and col_sender and col_content
            ):
                return []

            col_talkerid = col_map.get("talkerid")
            col_talker = col_map.get("talker")

            params = []
            where_clause = ""
            if col_talkerid:
                name2id_table = self._find_table(
                    conn, ["Name2Id", "Name2ID", "name2id"]
                )
                if not name2id_table:
                    return []

                # Prefer SQLite rowid for robustness
                talker_id = None
                for usr_col in ("UsrName", "usrName", "username", "UserName"):
                    try:
                        row = conn.execute(
                            f"SELECT rowid FROM {name2id_table} WHERE {usr_col} = ?",
                            (contact_id,),
                        ).fetchone()
                        if row is not None:
                            talker_id = row[0]
                            break
                    except sqlite3.OperationalError:
                        continue

                if talker_id is None:
                    return []

                where_clause = f"WHERE {col_talkerid} = ?"
                params = [talker_id]
            elif col_talker:
                where_clause = f"WHERE {col_talker} = ?"
                params = [contact_id]
            else:
                return []

            # Only text messages (Type=1) when available
            where_clause += f" AND {col_type} = 1"

            sql = (
                f"SELECT {col_local_id}, {col_type}, {col_create}, {col_sender}, {col_content} "
                f"FROM {msg_table} {where_clause} "
                f"ORDER BY {col_create} DESC LIMIT ?"
            )
            params.append(int(limit))
            cursor = conn.execute(sql, tuple(params))

            messages = []
            for row in cursor.fetchall():
                message = Message(
                    id=row[0],
                    contact_id=contact_id,
                    content=row[4] or "",
                    create_time=row[2],
                    is_sender=bool(row[3]),
                    msg_type=row[1],
                )
                messages.append(message)

            return messages
        finally:
            conn.close()

    def get_all_msg_databases(self) -> List[str]:
        """获取所有 MSG 数据库文件路径

        查找 Msg 目录下所有符合 MSG*.db 命名格式的文件

        Returns:
            数据库文件路径列表
        """
        return self._get_message_db_paths()
