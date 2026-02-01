"""
Mode A - Safe Read-Only Extraction

Provides safe extraction of WeChat chat data to encrypted local storage.
Source databases are NEVER modified - this mode is purely read-only.
"""

from typing import List, Optional
import time

from wechat_manager.core.db_handler import WeChatDBHandler
from wechat_manager.core.storage import EncryptedStorage
from wechat_manager.models.chat import Contact, Message


class ModeA:
    """Safe mode - read-only extraction to encrypted storage

    This mode extracts chat data from WeChat databases and stores
    them in local encrypted storage. The original WeChat databases
    are never modified.

    Extraction flow:
        WeChat DB (read-only) --> Mode A --> Encrypted Storage

        1. Read contact from MicroMsg.db
        2. Read messages from MSGn.db
        3. Store to hidden_chats.db (encrypted)
        4. Original DB untouched
    """

    def __init__(self, db_handler: WeChatDBHandler, storage: EncryptedStorage):
        """Initialize Mode A

        Args:
            db_handler: WeChat database handler for reading source data
            storage: Encrypted storage for storing extracted data
        """
        self.db_handler = db_handler
        self.storage = storage

    def extract_contact(self, contact_id: str) -> dict:
        """Extract all messages for a contact to encrypted storage.

        Args:
            contact_id: The contact's unique identifier (wxid/username)

        Returns:
            dict with keys:
                - contact_id: str - The extracted contact's ID
                - message_count: int - Number of messages extracted
                - success: bool - Whether extraction succeeded
                - error: str (optional) - Error message if failed
        """
        try:
            # 1. Get contact info from WeChat DB
            contacts = self.db_handler.get_contacts()
            contact = None
            for c in contacts:
                if c.id == contact_id:
                    contact = c
                    break

            if contact is None:
                return {
                    "contact_id": contact_id,
                    "message_count": 0,
                    "success": False,
                    "error": f"Contact {contact_id} not found in WeChat database",
                }

            # 2. Get all messages for contact (use high limit to get all)
            messages = self.db_handler.get_messages(contact_id, limit=100000)

            # 3. Store contact in encrypted storage
            # Set hidden_at to current timestamp
            contact.hidden_at = int(time.time())
            store_result = self.storage.store_contact(contact)

            if not store_result:
                return {
                    "contact_id": contact_id,
                    "message_count": 0,
                    "success": False,
                    "error": "Failed to store contact",
                }

            # 4. Store messages in encrypted storage
            # Set original_id for each message to preserve original ID
            for msg in messages:
                msg.original_id = msg.id

            stored_count = self.storage.store_messages(contact_id, messages)

            # 5. Return result summary
            return {
                "contact_id": contact_id,
                "message_count": stored_count,
                "success": True,
            }

        except Exception as e:
            return {
                "contact_id": contact_id,
                "message_count": 0,
                "success": False,
                "error": str(e),
            }

    def extract_multiple(self, contact_ids: List[str]) -> List[dict]:
        """Extract messages for multiple contacts.

        Args:
            contact_ids: List of contact IDs to extract

        Returns:
            List of result dicts, one for each contact
        """
        results = []
        for contact_id in contact_ids:
            result = self.extract_contact(contact_id)
            results.append(result)
        return results

    def sync_contact(self, contact_id: str) -> dict:
        """Incrementally extract new messages for a contact.

        Returns:
            dict with keys: contact_id, new_messages, success, error(optional)
        """
        try:
            if not self.is_contact_extracted(contact_id):
                result = self.extract_contact(contact_id)
                return {
                    "contact_id": contact_id,
                    "new_messages": result.get("message_count", 0),
                    "success": result.get("success", False),
                    "error": result.get("error"),
                }

            last_time = self.storage.get_latest_message_time(contact_id)
            messages = self.db_handler.get_messages(
                contact_id, limit=10000, since_time=last_time
            )

            for msg in messages:
                msg.original_id = msg.id

            stored_count = self.storage.store_messages(contact_id, messages)
            return {
                "contact_id": contact_id,
                "new_messages": stored_count,
                "success": True,
            }
        except Exception as e:
            return {
                "contact_id": contact_id,
                "new_messages": 0,
                "success": False,
                "error": str(e),
            }

    def get_extracted_contacts(self) -> List[Contact]:
        """List all contacts that have been extracted.

        Returns:
            List of Contact objects from encrypted storage
        """
        return self.storage.list_contacts()

    def get_extracted_messages(
        self, contact_id: str, limit: int = 100
    ) -> List[Message]:
        """Get messages from encrypted storage for a contact.

        Args:
            contact_id: The contact's unique identifier
            limit: Maximum number of messages to return

        Returns:
            List of Message objects from encrypted storage
        """
        return self.storage.get_messages(contact_id, limit)

    def is_contact_extracted(self, contact_id: str) -> bool:
        """Check if a contact has already been extracted.

        Args:
            contact_id: The contact's unique identifier

        Returns:
            True if contact exists in encrypted storage, False otherwise
        """
        contact = self.storage.get_contact(contact_id)
        return contact is not None
