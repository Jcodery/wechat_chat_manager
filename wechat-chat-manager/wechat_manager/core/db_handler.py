"""
微信数据库处理模块

提供 SQLCipher 加密数据库的解密和读取功能
支持读取联系人、群聊和消息数据
"""

import os
import re
import sqlite3
import tempfile
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
        # 缓存解密后的数据库文件路径
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
            decrypted_path = decrypt_database(self.key, db_path)
            self._decrypted_cache[db_path] = decrypted_path
            return sqlite3.connect(decrypted_path)
        else:
            # 未加密的数据库（测试用），直接连接
            return sqlite3.connect(db_path)

    def get_contacts(self) -> List[Contact]:
        """读取联系人列表

        从 MicroMsg.db 的 Contact 表中读取联系人信息

        Returns:
            联系人对象列表
        """
        db_path = self._msg_dir / "MicroMsg.db"
        conn = self.connect(str(db_path))

        try:
            cursor = conn.execute("""
                SELECT UserName, NickName, Alias, Remark, Type 
                FROM Contact 
                WHERE Type IN (1, 2, 3)
            """)

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
        db_path = self._msg_dir / "MicroMsg.db"
        conn = self.connect(str(db_path))

        try:
            cursor = conn.execute("""
                SELECT ChatRoomName, UserNameList 
                FROM ChatRoom
            """)

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
            # 首先查询 Name2Id 表获取 TalkerId
            cursor = conn.execute(
                """
                SELECT rowId FROM Name2Id WHERE UsrName = ?
            """,
                (contact_id,),
            )

            row = cursor.fetchone()
            if row is None:
                return []

            talker_id = row[0]

            # 然后查询消息
            cursor = conn.execute(
                """
                SELECT localId, TalkerId, Type, SubType, CreateTime, IsSender, StrContent
                FROM MSG
                WHERE TalkerId = ? AND Type = 1
                ORDER BY CreateTime DESC
                LIMIT ?
            """,
                (talker_id, limit),
            )

            messages = []
            for row in cursor.fetchall():
                message = Message(
                    id=row[0],
                    contact_id=contact_id,
                    content=row[6] or "",
                    create_time=row[4],
                    is_sender=bool(row[5]),
                    msg_type=row[2],
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
        msg_files = []

        if not self._msg_dir.exists():
            return msg_files

        # 查找所有 MSG*.db 文件
        for file_path in self._msg_dir.glob("MSG*.db"):
            if file_path.is_file():
                msg_files.append(str(file_path))

        # 按文件名排序，确保 MSG0.db, MSG1.db... 的顺序
        msg_files.sort(key=lambda p: Path(p).name)

        return msg_files
