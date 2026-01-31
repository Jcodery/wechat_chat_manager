"""
微信聊天相关的数据模型

定义了联系人、聊天室和消息的数据结构
"""

from dataclasses import dataclass, field
from typing import Optional, List
import time


@dataclass
class Contact:
    """联系人数据模型"""

    id: str  # wxid 或唯一标识符 (主键)
    username: str  # 微信号
    nickname: Optional[str] = None
    alias: Optional[str] = None
    remark: Optional[str] = None
    contact_type: int = 0  # 0=好友, 1=群组, 2=公众号
    hidden_at: int = field(default_factory=lambda: int(time.time()))  # 隐藏时间戳


@dataclass
class ChatRoom:
    """聊天室/群组数据模型"""

    name: str  # 聊天室名称/ID
    members: List[str] = field(default_factory=list)  # 成员用户名列表
    nickname: Optional[str] = None


@dataclass
class Message:
    """消息数据模型"""

    id: Optional[int] = None
    contact_id: str = ""
    original_id: Optional[int] = None
    content: str = ""
    create_time: int = 0
    is_sender: bool = False
    msg_type: int = 1
