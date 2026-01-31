"""
Export chat records to files.

Supports exporting messages to TXT format with proper formatting and encoding.
"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from wechat_manager.core.storage import EncryptedStorage
from wechat_manager.models.chat import Contact, Message


class ExportService:
    """Export chat records to files"""

    def __init__(self, storage: EncryptedStorage, export_dir: str):
        self.storage = storage
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export_to_txt(self, contact_id: str, filename: Optional[str] = None) -> str:
        """
        Export messages for a contact to TXT file.

        Args:
            contact_id: Contact to export
            filename: Optional custom filename

        Returns: Path to exported file
        """
        contact = self.storage.get_contact(contact_id)
        if not contact:
            raise ValueError(f"Contact {contact_id} not found")

        messages = self.storage.get_messages(contact_id, limit=10000)

        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = self._safe_filename(contact.nickname or contact_id)
            filename = f"{safe_name}_{timestamp}.txt"

        filepath = self.export_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            self._write_txt_content(f, contact, messages)

        return str(filepath)

    def export_multiple(self, contact_ids: List[str]) -> List[str]:
        """Export multiple contacts, returns list of file paths"""
        return [self.export_to_txt(cid) for cid in contact_ids]

    def _write_txt_content(self, f, contact: Contact, messages: List[Message]):
        """Write formatted TXT content"""
        # Header
        f.write(f"聊天记录导出 - {contact.nickname or contact.username}\n")
        f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 50 + "\n\n")

        # Messages
        for msg in sorted(messages, key=lambda m: m.create_time):
            time_str = datetime.fromtimestamp(msg.create_time).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            sender = "我" if msg.is_sender else (contact.nickname or contact.username)
            f.write(f"[{time_str}] {sender}: {msg.content}\n")

    def _safe_filename(self, name: str) -> str:
        """Convert name to safe filename"""
        # Remove invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, "_")
        return name[:50]  # Limit length
