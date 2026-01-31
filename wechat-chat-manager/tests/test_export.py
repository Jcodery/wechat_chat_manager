"""
Tests for export module.

Tests TXT export functionality including format, file handling, and edge cases.
"""

import pytest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from wechat_manager.core.storage import EncryptedStorage
from wechat_manager.core.export import ExportService
from wechat_manager.models.chat import Contact, Message


@pytest.fixture
def temp_dir():
    """Create temporary directory for testing"""
    with TemporaryDirectory() as tmp_dir:
        yield tmp_dir


@pytest.fixture
def storage(temp_dir):
    """Create encrypted storage instance for testing"""
    storage_path = Path(temp_dir) / "storage"
    return EncryptedStorage(str(storage_path), "test_password")


@pytest.fixture
def export_service(temp_dir, storage):
    """Create export service instance for testing"""
    export_dir = Path(temp_dir) / "exports"
    return ExportService(storage, str(export_dir))


def test_export_txt(storage, export_service):
    """Test basic TXT export functionality"""
    # Setup: Create contact and messages
    contact = Contact(id="test_contact_1", username="user123", nickname="张三")
    storage.store_contact(contact)

    # Create test messages
    now = int(datetime.now().timestamp())
    messages = [
        Message(
            contact_id="test_contact_1",
            content="你好",
            create_time=now,
            is_sender=False,
        ),
        Message(
            contact_id="test_contact_1",
            content="你好啊",
            create_time=now + 5,
            is_sender=True,
        ),
    ]
    storage.store_messages("test_contact_1", messages)

    # Export
    filepath = export_service.export_to_txt("test_contact_1")

    # Verify file exists
    assert Path(filepath).exists()
    assert filepath.endswith(".txt")

    # Verify content
    content = Path(filepath).read_text(encoding="utf-8")
    assert "聊天记录导出 - 张三" in content
    assert "你好" in content
    assert "你好啊" in content


def test_txt_format(storage, export_service):
    """Test that TXT format is correct"""
    contact = Contact(id="format_test", username="user456", nickname="李四")
    storage.store_contact(contact)

    now = int(datetime.now().timestamp())
    messages = [
        Message(
            contact_id="format_test",
            content="测试消息",
            create_time=now,
            is_sender=False,
        ),
    ]
    storage.store_messages("format_test", messages)

    filepath = export_service.export_to_txt("format_test")
    content = Path(filepath).read_text(encoding="utf-8")

    # Check header format
    lines = content.split("\n")
    assert "聊天记录导出 - 李四" in lines[0]
    assert "导出时间:" in lines[1]
    assert "=" * 50 in lines[2]

    # Check message format: [timestamp] sender: content
    message_lines = [l for l in lines if l.startswith("[")]
    assert len(message_lines) > 0
    assert "李四: 测试消息" in message_lines[0]
    assert "[" in message_lines[0] and "]" in message_lines[0]


def test_export_multiple_contacts(storage, export_service):
    """Test exporting multiple contacts at once"""
    # Create multiple contacts
    for i in range(3):
        contact = Contact(id=f"contact_{i}", username=f"user_{i}", nickname=f"用户{i}")
        storage.store_contact(contact)

        now = int(datetime.now().timestamp())
        messages = [
            Message(
                contact_id=f"contact_{i}",
                content=f"消息{i}",
                create_time=now,
                is_sender=False,
            ),
        ]
        storage.store_messages(f"contact_{i}", messages)

    # Export all
    filepaths = export_service.export_multiple([f"contact_{i}" for i in range(3)])

    # Verify all files were created
    assert len(filepaths) == 3
    for filepath in filepaths:
        assert Path(filepath).exists()
        content = Path(filepath).read_text(encoding="utf-8")
        assert "聊天记录导出" in content


def test_export_empty_contact(storage, export_service):
    """Test handling contact with no messages"""
    contact = Contact(id="empty_contact", username="empty_user", nickname="空联系人")
    storage.store_contact(contact)

    # Export without adding any messages
    filepath = export_service.export_to_txt("empty_contact")

    # Verify file exists but has no message content
    assert Path(filepath).exists()
    content = Path(filepath).read_text(encoding="utf-8")
    assert "聊天记录导出 - 空联系人" in content
    # Should only have header, no message lines starting with [
    message_lines = [l for l in content.split("\n") if l.startswith("[")]
    assert len(message_lines) == 0


def test_export_filename(storage, export_service):
    """Test that generated filename is correct and safe"""
    contact = Contact(
        id="filename_test", username="test_user", nickname='特殊<>字符:"名|字*?'
    )
    storage.store_contact(contact)

    now = int(datetime.now().timestamp())
    messages = [
        Message(
            contact_id="filename_test", content="测试", create_time=now, is_sender=False
        ),
    ]
    storage.store_messages("filename_test", messages)

    filepath = export_service.export_to_txt("filename_test")
    filename = Path(filepath).name

    # Verify filename is safe (no invalid characters)
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        assert char not in filename, f"Invalid character {char} found in filename"

    # Verify filename has .txt extension
    assert filename.endswith(".txt")

    # Verify filename contains safe version of nickname and timestamp
    assert "特殊" in filename or "_" in filename  # Special chars replaced with _
    # Filename should be: {safe_name}_{YYYYMMDD_HHMMSS}.txt
    assert "_" in filename  # Should have underscore before timestamp


def test_safe_filename_sanitization(export_service):
    """Test filename sanitization utility"""
    test_cases = [
        ("正常名字", "正常名字"),
        ("包含<尖括号>", "包含_尖括号_"),
        ("包含:冒号", "包含_冒号"),
        ('包含"引号', "包含_引号"),
        ("包含|管道", "包含_管道"),
        ("包含*星号", "包含_星号"),
        ("包含?问号", "包含_问号"),
        ("包含\\反斜杠", "包含_反斜杠"),
        ("包含/正斜杠", "包含_正斜杠"),
    ]

    for input_name, expected in test_cases:
        result = export_service._safe_filename(input_name)
        assert result == expected, (
            f"Failed for {input_name}: got {result}, expected {expected}"
        )


def test_export_nonexistent_contact(export_service):
    """Test exporting a contact that doesn't exist"""
    with pytest.raises(ValueError, match="Contact .* not found"):
        export_service.export_to_txt("nonexistent_contact")


def test_message_sender_display(storage, export_service):
    """Test that sender/receiver display is correct"""
    contact = Contact(id="sender_test", username="user789", nickname="王五")
    storage.store_contact(contact)

    now = int(datetime.now().timestamp())
    messages = [
        Message(
            contact_id="sender_test",
            content="来自对方",
            create_time=now,
            is_sender=False,
        ),
        Message(
            contact_id="sender_test",
            content="我的消息",
            create_time=now + 1,
            is_sender=True,
        ),
    ]
    storage.store_messages("sender_test", messages)

    filepath = export_service.export_to_txt("sender_test")
    content = Path(filepath).read_text(encoding="utf-8")

    # Verify sender/receiver display
    lines = content.split("\n")
    message_lines = [l for l in lines if l.startswith("[")]

    # First message should show contact nickname as sender
    assert "王五:" in message_lines[0]
    assert "来自对方" in message_lines[0]

    # Second message should show "我" as sender
    assert "我:" in message_lines[1]
    assert "我的消息" in message_lines[1]
