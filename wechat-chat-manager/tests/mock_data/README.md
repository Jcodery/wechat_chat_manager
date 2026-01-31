# Mock Data 目录

此目录用于存放测试用的模拟数据库文件。

注意：这些文件仅用于测试，不是真实的微信数据。

## 文件说明

- `mock_micromsg.db` - 模拟的 MicroMsg.db (联系人数据库)
- `mock_msg.db` - 模拟的 MSGn.db (消息数据库)

这些文件使用已知的测试密钥加密，密钥定义在 `conftest.py` 中。
