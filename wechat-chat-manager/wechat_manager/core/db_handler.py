"""
微信数据库处理模块

提供 SQLCipher 加密数据库的解密和读取功能
支持读取联系人、群聊和消息数据
"""

import os
import re
import sqlite3
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional

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

    def _guess_self_username_v4(self) -> str:
        """Best-effort derive the current account username for Weixin 4.x.

        Weixin 4.x folder names are often like: wxid_<base>_<random>.
        The message DB Name2Id usually stores the base username (without the last suffix).
        """

        name = self.wechat_dir.name
        if not name.startswith("wxid_"):
            return name
        parts = name.split("_")
        if len(parts) <= 2:
            return name
        return "_".join(parts[:-1])

    @staticmethod
    def _normalize_epoch_seconds(v: Any) -> int:
        if v is None:
            return 0
        if isinstance(v, bool):
            n = int(v)
        elif isinstance(v, int):
            n = v
        elif isinstance(v, float):
            n = int(v)
        elif isinstance(v, str):
            try:
                n = int(v)
            except Exception:
                return 0
        elif isinstance(v, (bytes, bytearray, memoryview)):
            try:
                n = int(bytes(v).decode("utf-8", errors="ignore") or "0")
            except Exception:
                return 0
        else:
            return 0
        # Heuristic: values >= 1e12 are milliseconds.
        if n >= 1_000_000_000_000:
            return int(n // 1000)
        return n

    @staticmethod
    def _to_text(v: object) -> str:
        if v is None:
            return ""
        if isinstance(v, (bytes, bytearray, memoryview)):
            try:
                return bytes(v).decode("utf-8")
            except Exception:
                return bytes(v).decode("utf-8", errors="replace")
        return str(v)

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

            cols = conn.execute(f"PRAGMA table_info({contact_table})").fetchall()
            col_map = {str(r[1]).lower(): str(r[1]) for r in cols}

            def _pick(*names: str) -> Optional[str]:
                for n in names:
                    hit = col_map.get(n.lower())
                    if hit:
                        return hit
                return None

            col_user = _pick(
                "UserName",
                "username",
                "UsrName",
                "usrname",
                "user_name",
                "userName",
            )
            col_nick = _pick("NickName", "nick_name", "nickname")
            col_alias = _pick("Alias", "alias")
            col_remark = _pick("Remark", "remark", "remark_name", "remarkname")
            col_type = _pick("Type", "type", "local_type", "localtype")

            if not col_user:
                raise DecryptionError(
                    "Unsupported contact schema: missing username column"
                )

            select_parts = [
                f"{col_user} AS username",
                f"{col_nick} AS nickname" if col_nick else "'' AS nickname",
                f"{col_alias} AS alias" if col_alias else "NULL AS alias",
                f"{col_remark} AS remark" if col_remark else "NULL AS remark",
                f"{col_type} AS contact_type" if col_type else "0 AS contact_type",
            ]

            sql = f"SELECT {', '.join(select_parts)} FROM {contact_table}"
            if col_type:
                sql += f" WHERE {col_type} IN (1, 2, 3)"

            cursor = conn.execute(sql)

            contacts = []
            for row in cursor.fetchall():
                user_name = row[0]
                contact = Contact(
                    id=user_name,
                    username=user_name,
                    nickname=row[1] or "",
                    alias=row[2],
                    remark=row[3],
                    contact_type=int(row[4] or 0),
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
            chatroom_table = self._find_table(
                conn, ["ChatRoom", "chatroom", "chat_room", "chatroom"]
            )
            if not chatroom_table:
                return []

            cols = conn.execute(f"PRAGMA table_info({chatroom_table})").fetchall()
            col_map = {str(r[1]).lower(): str(r[1]) for r in cols}

            def _pick(*names: str) -> Optional[str]:
                for n in names:
                    hit = col_map.get(n.lower())
                    if hit:
                        return hit
                return None

            # Legacy ChatRoom table: ChatRoomName + UserNameList
            col_room_name = _pick("ChatRoomName", "chatroomname", "username", "name")
            col_user_list = _pick(
                "UserNameList", "usernamelist", "member_list", "members"
            )
            if col_room_name and col_user_list:
                cursor = conn.execute(
                    f"SELECT {col_room_name}, {col_user_list} FROM {chatroom_table}"
                )

                chatrooms = []
                for row in cursor.fetchall():
                    members = str(row[1] or "").split(";") if row[1] else []
                    members = [m for m in members if m]
                    chatrooms.append(ChatRoom(name=str(row[0]), members=members))
                return chatrooms

            # Weixin 4.x contact.db: chat_room(id, username, ...) + chatroom_member(room_id, member_id)
            col_id = _pick("id", "room_id")
            if not col_id or not col_room_name:
                return []

            member_table = self._find_table(
                conn, ["chatroom_member", "ChatRoomMember", "chatroommember"]
            )
            member_cols = (
                conn.execute(f"PRAGMA table_info({member_table})").fetchall()
                if member_table
                else []
            )
            member_map = {str(r[1]).lower(): str(r[1]) for r in member_cols}
            col_member_room = member_map.get("room_id")
            col_member_id = member_map.get("member_id")

            rooms = conn.execute(
                f"SELECT {col_id}, {col_room_name} FROM {chatroom_table}"
            ).fetchall()

            chatrooms: List[ChatRoom] = []
            for r in rooms:
                room_id = r[0]
                room_name = str(r[1])
                members: List[str] = []
                if member_table and col_member_room and col_member_id:
                    m_rows = conn.execute(
                        f"SELECT {col_member_id} FROM {member_table} WHERE {col_member_room} = ?",
                        (room_id,),
                    ).fetchall()
                    members = [str(m[0]) for m in m_rows if m and m[0]]
                chatrooms.append(ChatRoom(name=room_name, members=members))

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
            if self._version_hint != 4 and len(all_messages) >= limit:
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
            # Weixin 4.x: per-contact tables Msg_{md5(username)}
            md5 = hashlib.md5(str(contact_id).encode("utf-8")).hexdigest()
            v4_table = self._find_table(conn, [f"Msg_{md5}", f"msg_{md5}"])
            if v4_table:
                cols = conn.execute(f"PRAGMA table_info({v4_table})").fetchall()
                col_map = {str(r[1]).lower(): str(r[1]) for r in cols}

                def _pick(*names: str) -> Optional[str]:
                    for n in names:
                        hit = col_map.get(n.lower())
                        if hit:
                            return hit
                    return None

                col_local_id = _pick("local_id", "localid")
                col_type = _pick("local_type", "type")
                col_create = _pick("create_time", "createtime")
                col_sender_flag = _pick("is_sender", "issender")
                col_real_sender = _pick("real_sender_id", "realsenderid", "sender_id")
                col_content = _pick("message_content", "strcontent", "content")
                col_compress = _pick("compress_content", "compresscontent")
                col_sort = _pick("sort_seq", "sortseq")

                if not (col_local_id and col_type and col_create and col_content):
                    return []

                # Resolve self rowid for sender inference if possible
                self_rowid: Optional[int] = None
                if col_real_sender and not col_sender_flag:
                    name2id_table = self._find_table(
                        conn, ["Name2Id", "Name2ID", "name2id"]
                    )
                    if name2id_table:
                        ncols = conn.execute(
                            f"PRAGMA table_info({name2id_table})"
                        ).fetchall()
                        nmap = {str(r[1]).lower(): str(r[1]) for r in ncols}
                        n_user = (
                            nmap.get("user_name")
                            or nmap.get("usrname")
                            or nmap.get("username")
                            or nmap.get("user")
                        )
                        if n_user:
                            self_user = self._guess_self_username_v4()
                            row = conn.execute(
                                f"SELECT rowid FROM {name2id_table} WHERE {n_user} = ? LIMIT 1",
                                (self_user,),
                            ).fetchone()
                            if row is not None:
                                try:
                                    self_rowid = int(row[0])
                                except Exception:
                                    self_rowid = None

                order_col = col_sort or col_create
                select_cols = [
                    col_local_id,
                    col_type,
                    col_create,
                    col_sender_flag or "NULL",
                    col_real_sender or "NULL",
                    col_content,
                    col_compress or "NULL",
                ]
                sql = (
                    f"SELECT {', '.join(select_cols)} FROM {v4_table} "
                    f"ORDER BY {order_col} DESC LIMIT ?"
                )

                cursor = conn.execute(sql, (int(limit),))
                messages: List[Message] = []
                for row in cursor.fetchall():
                    local_id = row[0]
                    msg_type = int(row[1] or 0)
                    create_time = self._normalize_epoch_seconds(row[2])
                    sender_flag = row[3]
                    real_sender_id = row[4]
                    content = self._to_text(row[5])
                    if not content:
                        content = self._to_text(row[6])

                    is_sender = False
                    if sender_flag is not None:
                        is_sender = bool(int(sender_flag))
                    elif self_rowid is not None and real_sender_id is not None:
                        try:
                            is_sender = int(real_sender_id) == int(self_rowid)
                        except Exception:
                            is_sender = False

                    messages.append(
                        Message(
                            id=local_id,
                            contact_id=contact_id,
                            content=content,
                            create_time=create_time,
                            is_sender=is_sender,
                            msg_type=msg_type,
                        )
                    )

                return messages

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

            params: list[int | str] = []
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
