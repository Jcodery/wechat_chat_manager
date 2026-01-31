"""
Tests for SearchService module
"""

import pytest
import tempfile
import shutil
from pathlib import Path

from wechat_manager.models.chat import Contact, Message
from wechat_manager.core.storage import EncryptedStorage
from wechat_manager.core.search import SearchService


@pytest.fixture
def temp_storage():
    """Create temporary storage for testing"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def storage(temp_storage):
    """Initialize storage with test data"""
    storage = EncryptedStorage(temp_storage, "test_password")

    # Create test contacts
    contact1 = Contact(id="wxid_001", username="testuser1", nickname="Test User 1")
    contact2 = Contact(id="wxid_002", username="testuser2", nickname="Test User 2")

    storage.store_contact(contact1)
    storage.store_contact(contact2)

    # Create test messages
    messages1 = [
        Message(
            contact_id="wxid_001",
            original_id=1,
            content="Hello world",
            create_time=1000000,
            is_sender=True,
            msg_type=1,
        ),
        Message(
            contact_id="wxid_001",
            original_id=2,
            content="How are you?",
            create_time=1000001,
            is_sender=False,
            msg_type=1,
        ),
        Message(
            contact_id="wxid_001",
            original_id=3,
            content="I am fine, thank you",
            create_time=1000002,
            is_sender=True,
            msg_type=1,
        ),
    ]

    messages2 = [
        Message(
            contact_id="wxid_002",
            original_id=4,
            content="你好",
            create_time=2000000,
            is_sender=True,
            msg_type=1,
        ),
        Message(
            contact_id="wxid_002",
            original_id=5,
            content="你好呀",
            create_time=2000001,
            is_sender=False,
            msg_type=1,
        ),
        Message(
            contact_id="wxid_002",
            original_id=6,
            content="今天天气很好",
            create_time=2000002,
            is_sender=True,
            msg_type=1,
        ),
    ]

    storage.store_messages("wxid_001", messages1)
    storage.store_messages("wxid_002", messages2)

    return storage


@pytest.fixture
def search_service(storage):
    """Initialize search service"""
    return SearchService(storage)


def test_search_messages(search_service):
    """Test searching messages by keyword"""
    results = search_service.search("Hello")
    assert len(results) == 1
    assert results[0].content == "Hello world"


def test_search_no_results(search_service):
    """Test search with no matching results"""
    results = search_service.search("nonexistent")
    assert len(results) == 0
    assert isinstance(results, list)


def test_search_case_insensitive(search_service):
    """Test case-insensitive search"""
    results = search_service.search("hello")
    assert len(results) == 1
    assert "hello" in results[0].content.lower()


def test_search_chinese(search_service):
    """Test searching Chinese characters"""
    results = search_service.search("你好")
    assert len(results) == 2
    assert all("你好" in msg.content for msg in results)


def test_search_with_contact_filter(search_service):
    """Test search within specific contact"""
    results = search_service.search("hello", contact_id="wxid_001")
    assert len(results) == 1
    assert results[0].contact_id == "wxid_001"

    # Search Chinese in specific contact should return nothing
    results = search_service.search("你好", contact_id="wxid_001")
    assert len(results) == 0


def test_search_with_limit(search_service):
    """Test search with result limit"""
    results = search_service.search("你好", limit=1)
    assert len(results) == 1


def test_search_returns_message_objects(search_service):
    """Test that search returns proper Message objects"""
    results = search_service.search("fine")
    assert len(results) == 1
    msg = results[0]
    assert isinstance(msg, Message)
    assert msg.content == "I am fine, thank you"
    assert msg.is_sender is True
    assert msg.msg_type == 1


def test_search_with_context(search_service):
    """Test search with surrounding context"""
    results = search_service.search_with_context("fine", context_lines=2)
    assert len(results) == 1

    result = results[0]
    assert "match" in result
    assert "before" in result
    assert "after" in result

    assert result["match"].content == "I am fine, thank you"
    assert isinstance(result["before"], list)
    assert isinstance(result["after"], list)


def test_search_with_context_boundaries(search_service):
    """Test search with context at message boundaries"""
    # Search first message - should have no 'before' context
    results = search_service.search_with_context("Hello", context_lines=2)
    assert len(results) == 1
    result = results[0]
    assert len(result["before"]) == 0
    assert len(result["after"]) >= 1
