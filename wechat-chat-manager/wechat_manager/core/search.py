"""
Search service for extracted chat messages

Provides functionality to search through encrypted storage.
"""

from typing import List, Optional
import sqlite3

from wechat_manager.core.storage import EncryptedStorage
from wechat_manager.models.chat import Message


class SearchService:
    """Search extracted messages from encrypted storage"""

    def __init__(self, storage: EncryptedStorage):
        """
        Initialize search service.

        Args:
            storage: EncryptedStorage instance for database access
        """
        self.storage = storage

    def search(
        self, query: str, contact_id: Optional[str] = None, limit: int = 100
    ) -> List[Message]:
        """
        Search messages by keyword.

        Args:
            query: Search keyword (case-insensitive)
            contact_id: Optional filter by contact ID
            limit: Maximum number of results (default: 100)

        Returns:
            List of matching Message objects, ordered by create_time ASC
        """
        conn = self.storage._get_connection()
        try:
            cursor = conn.cursor()

            if contact_id:
                # Search within specific contact
                cursor.execute(
                    """
                    SELECT id, contact_id, original_id, content, create_time, is_sender, msg_type
                    FROM messages
                    WHERE content LIKE ? AND contact_id = ?
                    ORDER BY create_time ASC
                    LIMIT ?
                    """,
                    (f"%{query}%", contact_id, limit),
                )
            else:
                # Global search across all messages
                cursor.execute(
                    """
                    SELECT id, contact_id, original_id, content, create_time, is_sender, msg_type
                    FROM messages
                    WHERE content LIKE ?
                    ORDER BY create_time ASC
                    LIMIT ?
                    """,
                    (f"%{query}%", limit),
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

    def search_with_context(
        self, query: str, context_lines: int = 2, contact_id: Optional[str] = None
    ) -> List[dict]:
        """
        Search and return results with surrounding messages as context.

        Args:
            query: Search keyword
            context_lines: Number of messages before/after to include
            contact_id: Optional filter by contact ID

        Returns:
            List of dicts with keys:
            - "match": The matching Message object
            - "before": List of Message objects before the match
            - "after": List of Message objects after the match
        """
        # First find all matching messages
        matches = self.search(query, contact_id=contact_id)

        if not matches:
            return []

        results = []

        for match in matches:
            conn = self.storage._get_connection()
            try:
                cursor = conn.cursor()

                # Get messages before
                cursor.execute(
                    """
                    SELECT id, contact_id, original_id, content, create_time, is_sender, msg_type
                    FROM messages
                    WHERE contact_id = ? AND create_time < ?
                    ORDER BY create_time DESC
                    LIMIT ?
                    """,
                    (match.contact_id, match.create_time, context_lines),
                )
                before_rows = list(reversed(cursor.fetchall()))
                before_messages = [
                    Message(
                        id=row[0],
                        contact_id=row[1],
                        original_id=row[2],
                        content=row[3],
                        create_time=row[4],
                        is_sender=bool(row[5]),
                        msg_type=row[6],
                    )
                    for row in before_rows
                ]

                # Get messages after
                cursor.execute(
                    """
                    SELECT id, contact_id, original_id, content, create_time, is_sender, msg_type
                    FROM messages
                    WHERE contact_id = ? AND create_time > ?
                    ORDER BY create_time ASC
                    LIMIT ?
                    """,
                    (match.contact_id, match.create_time, context_lines),
                )
                after_rows = cursor.fetchall()
                after_messages = [
                    Message(
                        id=row[0],
                        contact_id=row[1],
                        original_id=row[2],
                        content=row[3],
                        create_time=row[4],
                        is_sender=bool(row[5]),
                        msg_type=row[6],
                    )
                    for row in after_rows
                ]

                results.append(
                    {
                        "match": match,
                        "before": before_messages,
                        "after": after_messages,
                    }
                )
            finally:
                conn.close()

        return results
