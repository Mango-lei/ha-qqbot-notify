"""QQ Bot 开放平台 API 封装：access_token 获取与消息发送。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_BASE,
    DEFAULT_TOKEN_LIFETIME,
    REQUEST_TIMEOUT,
    TOKEN_REFRESH_MARGIN,
    TOKEN_URL,
)

_LOGGER = logging.getLogger(__name__)

# 鉴权头格式：QQ 官方文档与官方 SDK（botpy）均为 "QQBot <access_token>"。
# 旧版频道接口用的 "Bot <token>" 会被判为 Token错误（401 / code 11242）。
AUTH_SCHEME = "QQBot"

# access_token 被判无效的错误码：丢弃缓存后重试一次
TOKEN_ERROR_CODES = frozenset({"11242", "11253", "40012002"})
# AppID / AppSecret 凭证错误的错误码（换取 token 时返回）
AUTH_ERROR_CODES = frozenset({"100007", "100016", "10004"})

# 常见错误码 → 排查建议
_ERROR_HINTS: dict[str, str] = {
    "11242": "鉴权头必须是 'QQBot <access_token>'，并确认 AppID/AppSecret 与机器人一致",
    "11244": "机器人未上线，或没有该接口的权限",
    "11253": "token 已失效，等待自动刷新后重试",
    "22009": "openid 无效，或该用户尚未与机器人建立会话",
    "40054": "openid 或请求参数不正确",
    "304103": "msg_id 已过期，不能回复",
    "40034005": "回复的 msg_id 已过期（单聊 60 分钟、群聊 5 分钟）",
    "40034100": "触发主动消息频控，请降低发送频率",
    "40034105": "无主动消息权限，用户可能关闭了“允许主动发送”",
    "40054004": "无好友关系，需要用户先添加机器人或先发一条消息",
    "40054013": "用户已拒收机器人消息",
    "100007": "AppID 无效，或机器人状态异常（被封禁/已删除）",
    "100016": "AppID 或 AppSecret 不正确",
}


class QQBotApiError(HomeAssistantError):
    """调用 QQ Bot API 失败。"""


class QQBotConnectionError(QQBotApiError):
    """网络不通或请求超时。"""


class QQBotAuthError(QQBotApiError):
    """AppID / AppSecret 等凭证不正确。"""


class QQBotTokenError(QQBotApiError):
    """access_token 被判无效，可丢弃缓存后重试。"""


def _parse(text: str) -> dict[str, Any]:
    """尽量把响应体解析成 dict。"""
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _error_code(data: dict[str, Any]) -> str | None:
    """取出响应体里的错误码（成功时为 None）。"""
    for key in ("code", "err_code"):
        value = data.get(key)
        if value not in (None, 0, "0"):
            return str(value)
    return None


def _error_hint(data: dict[str, Any]) -> str:
    """根据错误码附加一句排查建议。"""
    if (code := _error_code(data)) and (hint := _ERROR_HINTS.get(code)):
        return f"（建议：{hint}）"
    return ""


class QQBotClient:
    """QQ Bot 单聊（C2C）/ 群聊发送客户端，内部缓存 access_token。"""

    def __init__(self, hass: HomeAssistant, appid: str, secret: str) -> None:
        """初始化客户端。"""
        self._hass = hass
        self._appid = appid
        self._secret = secret
        self._token: str | None = None
        self._token_expire: float = 0.0
        self._token_lock = asyncio.Lock()

    @property
    def appid(self) -> str:
        """返回 AppID。"""
        return self._appid

    @property
    def _timeout(self) -> aiohttp.ClientTimeout:
        """返回统一的请求超时设置。"""
        return aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    def _invalidate_token(self) -> None:
        """丢弃缓存的 access_token。"""
        self._token = None
        self._token_expire = 0.0

    async def async_validate_credentials(self) -> None:
        """校验 AppID/AppSecret 能否换取 access_token（供配置流程使用）。"""
        await self._async_get_token()

    async def _async_request(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, str]:
        """发一次请求，网络问题统一转成 QQBotConnectionError。"""
        session = async_get_clientsession(self._hass)
        try:
            async with session.request(
                method, url, json=payload, headers=headers, timeout=self._timeout
            ) as resp:
                return resp.status, await resp.text()
        except TimeoutError as err:
            raise QQBotConnectionError("请求 QQ 开放平台超时") from err
        except aiohttp.ClientError as err:
            raise QQBotConnectionError(f"请求 QQ 开放平台失败：{err}") from err

    async def _async_get_token(self) -> str:
        """获取 access_token（提前 5 分钟刷新，并发调用只请求一次）。"""
        async with self._token_lock:
            now = time.monotonic()
            if self._token and self._token_expire > now + TOKEN_REFRESH_MARGIN:
                return self._token

            status, text = await self._async_request(
                "POST",
                TOKEN_URL,
                payload={"appId": self._appid, "clientSecret": self._secret},
            )
            data = _parse(text)
            _LOGGER.debug("QQBot token resp: status=%s body=%s", status, text[:300])

            if status != 200:
                raise QQBotApiError(
                    f"获取 QQBot access_token 失败（HTTP {status}）：{text[:300]}"
                    + _error_hint(data)
                )

            token = data.get("access_token")
            if not token:
                # 该接口出错时 HTTP 仍为 200，只能靠响应体里的 code 判断
                message = (
                    f"QQBot access_token 响应缺少 access_token 字段：{text[:300]}"
                    + _error_hint(data)
                )
                if _error_code(data) in AUTH_ERROR_CODES:
                    raise QQBotAuthError(message)
                raise QQBotApiError(message)

            try:
                expires_in = int(data.get("expires_in") or DEFAULT_TOKEN_LIFETIME)
            except (TypeError, ValueError):
                expires_in = DEFAULT_TOKEN_LIFETIME

            self._token = token
            self._token_expire = now + expires_in
            _LOGGER.debug("QQBot access_token 已更新，%s 秒后过期", expires_in)
            return token

    async def async_send_message(
        self,
        target: str,
        message: str,
        *,
        is_group: bool = False,
        msg_id: str | None = None,
        msg_seq: int = 1,
    ) -> None:
        """发送消息；token 被判无效时丢弃缓存重试一次。"""
        target = str(target or "").strip()
        if not target:
            raise QQBotApiError("未指定接收者（user_openid 或 group_openid）")
        if not message:
            raise QQBotApiError("消息内容为空，已取消发送")

        if is_group:
            url = f"{API_BASE}/v2/groups/{target}/messages"
        else:
            url = f"{API_BASE}/v2/users/{target}/messages"

        # 主动消息只需 content + msg_type；被动回复（带 msg_id）必须带 msg_seq。
        payload: dict[str, Any] = {"content": message, "msg_type": 0}
        if msg_id:
            payload["msg_id"] = msg_id
            payload["msg_seq"] = int(msg_seq or 1)

        for attempt in (1, 2):
            try:
                await self._async_post_message(url, payload)
            except QQBotTokenError:
                if attempt == 2:
                    raise
                _LOGGER.debug("QQBot access_token 被判无效，丢弃缓存后重试一次")
                self._invalidate_token()
            else:
                _LOGGER.debug(
                    "QQBot 消息已发出：target=%s is_group=%s", target, is_group
                )
                return

    async def _async_post_message(self, url: str, payload: dict[str, Any]) -> None:
        """带鉴权头发送一条消息，失败时抛出分类后的异常。"""
        token = await self._async_get_token()
        headers = {
            "Authorization": f"{AUTH_SCHEME} {token}",
            "X-Union-Appid": self._appid,
            "Content-Type": "application/json",
        }
        _LOGGER.debug("QQBot send: url=%s payload=%s", url, payload)

        status, text = await self._async_request(
            "POST", url, payload=payload, headers=headers
        )
        _LOGGER.debug("QQBot send resp: status=%s body=%s", status, text[:300])

        data = _parse(text)
        code = _error_code(data)

        if status != 200:
            message = (
                f"发送 QQ 消息失败（HTTP {status}）：{text[:300]}" + _error_hint(data)
            )
            if code in TOKEN_ERROR_CODES or status in (401, 403):
                raise QQBotTokenError(message)
            if code in AUTH_ERROR_CODES:
                raise QQBotAuthError(message)
            raise QQBotApiError(message)

        # 少数错误会以 HTTP 200 + body 里的 code 返回
        if code:
            message = f"发送 QQ 消息失败（code {code}）：{text[:300]}" + _error_hint(data)
            if code in TOKEN_ERROR_CODES:
                raise QQBotTokenError(message)
            if code in AUTH_ERROR_CODES:
                raise QQBotAuthError(message)
            raise QQBotApiError(message)
