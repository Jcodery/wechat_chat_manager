"""API 路由模块"""

from wechat_manager.api.routes import (
    auth,
    wechat,
    contacts,
    mode_a,
    mode_b,
    search,
    export,
)

__all__ = ["auth", "wechat", "contacts", "mode_a", "mode_b", "search", "export"]
