"""QQBot Notify 集成的常量定义。"""

from typing import Final

DOMAIN: Final = "qqbot_notify"
PLATFORMS: Final[list[str]] = ["notify"]

# 配置条目字段
CONF_APPID: Final = "appid"
CONF_SECRET: Final = "secret"
CONF_DEFAULT_TARGET: Final = "default_target"

# 动作字段
ATTR_MESSAGE: Final = "message"
ATTR_TITLE: Final = "title"
ATTR_TARGET: Final = "target"
ATTR_IS_GROUP: Final = "is_group"
ATTR_MSG_ID: Final = "msg_id"
ATTR_MSG_SEQ: Final = "msg_seq"
ATTR_ENTRY_ID: Final = "entry_id"

SERVICE_SEND: Final = "send"

# QQ Bot 开放平台接口
TOKEN_URL: Final = "https://bots.qq.com/app/getAppAccessToken"
API_BASE: Final = "https://api.sgroup.qq.com"

# 单次 HTTP 请求超时（秒）
REQUEST_TIMEOUT: Final = 15
# access_token 提前刷新的余量（秒）
TOKEN_REFRESH_MARGIN: Final = 300
# QQ 未返回 expires_in 时的默认有效期（秒）
DEFAULT_TOKEN_LIFETIME: Final = 7200
