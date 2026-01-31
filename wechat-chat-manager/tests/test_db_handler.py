"""
WeChatDBHandler 的测试模块

遵循 TDD 方法，测试 SQLCipher 数据库解密和读取功能
"""

import sqlite3
import pytest
from pathlib import Path

from wechat_manager.core.db_handler import WeChatDBHandler
from wechat_manager.models.chat import Contact, ChatRoom, Message


def create_mock_micromsg(path: Path) -> None:
    """创建模拟的 MicroMsg.db 数据库"""
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
    # 插入测试数据
    conn.execute(
        "INSERT INTO Contact VALUES ('wxid_test1', '张三', 'zhangsan', '同事张三', 1)"
    )
    conn.execute("INSERT INTO Contact VALUES ('wxid_test2', '李四', NULL, NULL, 1)")
    conn.execute(
        "INSERT INTO Contact VALUES ('wxid_test3', '王五', 'wangwu', '同学王五', 1)"
    )
    conn.execute(
        "INSERT INTO Contact VALUES ('12345@chatroom', '测试群', NULL, NULL, 2)"
    )
    conn.execute(
        "INSERT INTO ChatRoom VALUES ('12345@chatroom', 'wxid_test1;wxid_test2;wxid_test3')"
    )
    conn.execute(
        "INSERT INTO ChatRoom VALUES ('67890@chatroom', 'wxid_test1;wxid_test2')"
    )
    conn.commit()
    conn.close()


def create_mock_msg(path: Path, talker_mapping: dict = None) -> None:
    """创建模拟的 MSGn.db 数据库"""
    conn = sqlite3.connect(str(path))
    # MSG 表需要 TalkerId 来关联 Name2Id 表
    conn.execute("""CREATE TABLE MSG (
        localId INTEGER PRIMARY KEY,
        TalkerId INTEGER,
        Type INTEGER,
        SubType INTEGER,
        CreateTime INTEGER,
        IsSender INTEGER,
        StrContent TEXT
    )""")
    # Name2Id 表用于映射 TalkerId 到 UserName
    conn.execute("""CREATE TABLE Name2Id (
        rowId INTEGER PRIMARY KEY,
        UsrName TEXT
    )""")

    # 默认的 talker 映射
    if talker_mapping is None:
        talker_mapping = {1: "wxid_test1", 2: "wxid_test2"}

    # 插入 Name2Id 映射数据
    for talker_id, username in talker_mapping.items():
        conn.execute("INSERT INTO Name2Id VALUES (?, ?)", (talker_id, username))

    # 插入测试消息
    conn.execute("INSERT INTO MSG VALUES (1, 1, 1, 0, 1704067200, 0, '你好')")
    conn.execute("INSERT INTO MSG VALUES (2, 1, 1, 0, 1704067260, 1, '你好啊')")
    conn.execute("INSERT INTO MSG VALUES (3, 1, 1, 0, 1704067320, 0, '今天天气不错')")
    conn.execute("INSERT INTO MSG VALUES (4, 2, 1, 0, 1704067400, 1, '好的，收到')")
    conn.execute("INSERT INTO MSG VALUES (5, 2, 1, 0, 1704067460, 0, '谢谢')")
    conn.commit()
    conn.close()


@pytest.fixture
def mock_db_wechat_dir(temp_dir: Path) -> Path:
    """创建带有完整模拟数据库的微信目录结构"""
    wechat_dir = temp_dir / "WeChat Files" / "wxid_testuser"
    msg_dir = wechat_dir / "Msg"
    msg_dir.mkdir(parents=True)

    # 创建 MicroMsg.db
    create_mock_micromsg(msg_dir / "MicroMsg.db")

    # 创建 MSG0.db 和 MSG1.db
    create_mock_msg(msg_dir / "MSG0.db")
    create_mock_msg(msg_dir / "MSG1.db", {3: "wxid_test3"})

    return wechat_dir


class TestWeChatDBHandler:
    """WeChatDBHandler 测试类"""

    def test_decrypt_mock_db(self, mock_db_wechat_dir: Path, test_db_key: str):
        """测试连接模拟数据库（使用普通 sqlite3 模拟解密场景）"""
        handler = WeChatDBHandler(str(mock_db_wechat_dir), test_db_key)

        # 测试连接 MicroMsg.db
        db_path = mock_db_wechat_dir / "Msg" / "MicroMsg.db"
        conn = handler.connect(str(db_path))

        assert conn is not None

        # 验证能够查询数据
        cursor = conn.execute("SELECT COUNT(*) FROM Contact")
        count = cursor.fetchone()[0]
        assert count > 0

        conn.close()

    def test_read_contacts(self, mock_db_wechat_dir: Path, test_db_key: str):
        """测试从 MicroMsg.db 读取联系人"""
        handler = WeChatDBHandler(str(mock_db_wechat_dir), test_db_key)
        contacts = handler.get_contacts()

        # 验证返回的是 Contact 对象列表
        assert isinstance(contacts, list)
        assert len(contacts) > 0
        assert all(isinstance(c, Contact) for c in contacts)

        # 验证联系人数据
        usernames = [c.username for c in contacts]
        assert "wxid_test1" in usernames
        assert "wxid_test2" in usernames

        # 验证具体联系人信息
        zhangsan = next(c for c in contacts if c.username == "wxid_test1")
        assert zhangsan.nickname == "张三"
        assert zhangsan.alias == "zhangsan"
        assert zhangsan.remark == "同事张三"
        assert zhangsan.contact_type == 1

    def test_read_chatrooms(self, mock_db_wechat_dir: Path, test_db_key: str):
        """测试从 MicroMsg.db 读取群聊"""
        handler = WeChatDBHandler(str(mock_db_wechat_dir), test_db_key)
        chatrooms = handler.get_chatrooms()

        # 验证返回的是 ChatRoom 对象列表
        assert isinstance(chatrooms, list)
        assert len(chatrooms) > 0
        assert all(isinstance(cr, ChatRoom) for cr in chatrooms)

        # 验证群聊数据
        room_names = [cr.name for cr in chatrooms]
        assert "12345@chatroom" in room_names

        # 验证群成员
        room = next(cr for cr in chatrooms if cr.name == "12345@chatroom")
        assert "wxid_test1" in room.members
        assert "wxid_test2" in room.members
        assert "wxid_test3" in room.members

    def test_read_messages(self, mock_db_wechat_dir: Path, test_db_key: str):
        """测试从 MSGn.db 读取消息"""
        handler = WeChatDBHandler(str(mock_db_wechat_dir), test_db_key)
        messages = handler.get_messages("wxid_test1", limit=100)

        # 验证返回的是 Message 对象列表
        assert isinstance(messages, list)
        assert len(messages) > 0
        assert all(isinstance(m, Message) for m in messages)

        # 验证消息数据
        assert any(m.content == "你好" for m in messages)
        assert any(m.content == "你好啊" for m in messages)

        # 验证消息属性
        msg = next(m for m in messages if m.content == "你好")
        assert msg.contact_id == "wxid_test1"
        assert msg.is_sender is False
        assert msg.msg_type == 1
        assert msg.create_time == 1704067200

    def test_invalid_key_rejected(self, mock_db_wechat_dir: Path):
        """测试使用无效密钥被拒绝（仅验证密钥格式）"""
        # 密钥格式验证 - 密钥必须是 64 个十六进制字符
        with pytest.raises(ValueError, match="密钥必须是64个十六进制字符"):
            WeChatDBHandler(str(mock_db_wechat_dir), "invalid_key")

        with pytest.raises(ValueError, match="密钥必须是64个十六进制字符"):
            WeChatDBHandler(str(mock_db_wechat_dir), "1234")

        # 非十六进制字符
        with pytest.raises(ValueError, match="密钥必须是64个十六进制字符"):
            WeChatDBHandler(str(mock_db_wechat_dir), "zzzz" * 16)

    def test_message_contact_association(
        self, mock_db_wechat_dir: Path, test_db_key: str
    ):
        """测试消息与联系人的关联"""
        handler = WeChatDBHandler(str(mock_db_wechat_dir), test_db_key)

        # 获取联系人
        contacts = handler.get_contacts()
        contact_usernames = {c.username for c in contacts}

        # 获取不同联系人的消息
        messages_1 = handler.get_messages("wxid_test1")
        messages_2 = handler.get_messages("wxid_test2")

        # 验证消息与联系人关联正确
        assert all(m.contact_id == "wxid_test1" for m in messages_1)
        assert all(m.contact_id == "wxid_test2" for m in messages_2)

        # 验证消息内容不混淆
        contents_1 = {m.content for m in messages_1}
        contents_2 = {m.content for m in messages_2}

        assert "你好" in contents_1
        assert "好的，收到" in contents_2

    def test_get_all_msg_databases(self, mock_db_wechat_dir: Path, test_db_key: str):
        """测试获取所有 MSG 数据库文件"""
        handler = WeChatDBHandler(str(mock_db_wechat_dir), test_db_key)
        msg_dbs = handler.get_all_msg_databases()

        # 验证返回的是文件路径列表
        assert isinstance(msg_dbs, list)
        assert len(msg_dbs) >= 2  # 至少有 MSG0.db 和 MSG1.db

        # 验证文件名格式
        filenames = [Path(db).name for db in msg_dbs]
        assert "MSG0.db" in filenames
        assert "MSG1.db" in filenames

    def test_message_limit(self, mock_db_wechat_dir: Path, test_db_key: str):
        """测试消息数量限制"""
        handler = WeChatDBHandler(str(mock_db_wechat_dir), test_db_key)

        # 限制为 1 条消息
        messages = handler.get_messages("wxid_test1", limit=1)
        assert len(messages) == 1

        # 限制为 2 条消息
        messages = handler.get_messages("wxid_test1", limit=2)
        assert len(messages) == 2

    def test_nonexistent_contact_returns_empty(
        self, mock_db_wechat_dir: Path, test_db_key: str
    ):
        """测试查询不存在的联系人返回空列表"""
        handler = WeChatDBHandler(str(mock_db_wechat_dir), test_db_key)
        messages = handler.get_messages("wxid_nonexistent")

        assert isinstance(messages, list)
        assert len(messages) == 0
