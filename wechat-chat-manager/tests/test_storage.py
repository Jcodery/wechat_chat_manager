"""
Tests for wechat_manager.core.storage - Encrypted Local Storage System
"""

import pytest
from pathlib import Path
import time

from wechat_manager.core.storage import EncryptedStorage
from wechat_manager.models.chat import Contact, Message


class TestEncryptedStorageCreation:
    def test_create_encrypted_storage(self, storage_dir: Path, test_password: str):
        """Test creating a new encrypted storage database"""
        storage = EncryptedStorage(str(storage_dir), test_password)

        assert storage.db_path.exists()
        assert (storage_dir / ".salt").exists()

    def test_salt_persists_across_sessions(self, storage_dir: Path, test_password: str):
        """Test that salt file is reused on subsequent opens"""
        storage1 = EncryptedStorage(str(storage_dir), test_password)
        salt1 = (storage_dir / ".salt").read_bytes()

        storage2 = EncryptedStorage(str(storage_dir), test_password)
        salt2 = (storage_dir / ".salt").read_bytes()

        assert salt1 == salt2


class TestMessageStorage:
    def test_store_messages(self, storage_dir: Path, test_password: str):
        """Test storing messages to encrypted storage"""
        storage = EncryptedStorage(str(storage_dir), test_password)

        contact = Contact(
            id="wxid_test123",
            username="testuser",
            nickname="Test User",
        )
        storage.store_contact(contact)

        messages = [
            Message(
                contact_id="wxid_test123",
                original_id=1001,
                content="Hello!",
                create_time=int(time.time()) - 100,
                is_sender=False,
            ),
            Message(
                contact_id="wxid_test123",
                original_id=1002,
                content="Hi there!",
                create_time=int(time.time()),
                is_sender=True,
            ),
        ]

        count = storage.store_messages("wxid_test123", messages)
        assert count == 2

    def test_read_stored_messages(self, storage_dir: Path, test_password: str):
        """Test reading messages from encrypted storage"""
        storage = EncryptedStorage(str(storage_dir), test_password)

        contact = Contact(
            id="wxid_reader",
            username="reader_user",
            nickname="Reader",
        )
        storage.store_contact(contact)

        now = int(time.time())
        messages = [
            Message(
                contact_id="wxid_reader",
                original_id=2001,
                content="First message",
                create_time=now - 200,
                is_sender=False,
            ),
            Message(
                contact_id="wxid_reader",
                original_id=2002,
                content="Second message",
                create_time=now - 100,
                is_sender=True,
            ),
            Message(
                contact_id="wxid_reader",
                original_id=2003,
                content="Third message",
                create_time=now,
                is_sender=False,
            ),
        ]
        storage.store_messages("wxid_reader", messages)

        retrieved = storage.get_messages("wxid_reader")
        assert len(retrieved) == 3
        assert retrieved[0].content == "First message"
        assert retrieved[2].content == "Third message"


class TestPasswordValidation:
    def test_wrong_password_rejected(self, storage_dir: Path, test_password: str):
        """Test that wrong password produces different derived key"""
        storage1 = EncryptedStorage(str(storage_dir), test_password)

        contact = Contact(
            id="wxid_secret",
            username="secret_user",
            nickname="Secret",
        )
        storage1.store_contact(contact)

        storage2 = EncryptedStorage(str(storage_dir), "wrong_password")

        assert storage1._key != storage2._key


class TestContactStorage:
    def test_store_contact(self, storage_dir: Path, test_password: str):
        """Test storing contact info"""
        storage = EncryptedStorage(str(storage_dir), test_password)

        contact = Contact(
            id="wxid_contact1",
            username="contact_one",
            nickname="Contact One",
            remark="My Friend",
            contact_type=0,
        )

        result = storage.store_contact(contact)
        assert result is True

        retrieved = storage.get_contact("wxid_contact1")
        assert retrieved is not None
        assert retrieved.id == "wxid_contact1"
        assert retrieved.nickname == "Contact One"
        assert retrieved.remark == "My Friend"

    def test_list_hidden_contacts(self, storage_dir: Path, test_password: str):
        """Test listing all hidden contacts"""
        storage = EncryptedStorage(str(storage_dir), test_password)

        contacts = [
            Contact(id="wxid_a", username="user_a", nickname="User A"),
            Contact(id="wxid_b", username="user_b", nickname="User B"),
            Contact(id="wxid_c", username="user_c", nickname="User C"),
        ]

        for c in contacts:
            storage.store_contact(c)

        all_contacts = storage.list_contacts()
        assert len(all_contacts) == 3

        ids = {c.id for c in all_contacts}
        assert ids == {"wxid_a", "wxid_b", "wxid_c"}


class TestDeletion:
    def test_delete_contact_messages(self, storage_dir: Path, test_password: str):
        """Test deleting a contact and all their messages"""
        storage = EncryptedStorage(str(storage_dir), test_password)

        contact = Contact(
            id="wxid_delete",
            username="delete_user",
            nickname="To Delete",
        )
        storage.store_contact(contact)

        messages = [
            Message(
                contact_id="wxid_delete",
                content="Message 1",
                create_time=int(time.time()),
                is_sender=False,
            ),
            Message(
                contact_id="wxid_delete",
                content="Message 2",
                create_time=int(time.time()),
                is_sender=True,
            ),
        ]
        storage.store_messages("wxid_delete", messages)

        assert len(storage.get_messages("wxid_delete")) == 2

        result = storage.delete_contact("wxid_delete")
        assert result is True

        assert storage.get_contact("wxid_delete") is None
        assert len(storage.get_messages("wxid_delete")) == 0


class TestSearch:
    def test_search_messages(self, storage_dir: Path, test_password: str):
        """Test searching messages by content"""
        storage = EncryptedStorage(str(storage_dir), test_password)

        contact = Contact(
            id="wxid_search",
            username="search_user",
            nickname="Searcher",
        )
        storage.store_contact(contact)

        now = int(time.time())
        messages = [
            Message(
                contact_id="wxid_search",
                content="Let's meet at the coffee shop",
                create_time=now - 300,
                is_sender=False,
            ),
            Message(
                contact_id="wxid_search",
                content="Sounds good, I love coffee!",
                create_time=now - 200,
                is_sender=True,
            ),
            Message(
                contact_id="wxid_search",
                content="See you tomorrow",
                create_time=now - 100,
                is_sender=False,
            ),
        ]
        storage.store_messages("wxid_search", messages)

        results = storage.search_messages("coffee")
        assert len(results) == 2

        results = storage.search_messages("tomorrow")
        assert len(results) == 1
        assert "tomorrow" in results[0].content
