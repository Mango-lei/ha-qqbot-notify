"""QQBot Notify 自定义动作（支持 target / is_group / msg_id）。"""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_ENTRY_ID,
    ATTR_IS_GROUP,
    ATTR_MESSAGE,
    ATTR_MSG_ID,
    ATTR_MSG_SEQ,
    ATTR_TARGET,
    ATTR_TITLE,
    DOMAIN,
    SERVICE_SEND,
)
from .data import QQBotConfigEntry

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_TITLE): cv.string,
        vol.Optional(ATTR_TARGET): cv.string,
        vol.Optional(ATTR_IS_GROUP, default=False): cv.boolean,
        vol.Optional(ATTR_MSG_ID): cv.string,
        vol.Optional(ATTR_MSG_SEQ, default=1): vol.Coerce(int),
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """注册 qqbot_notify.send 动作（整个 HA 运行期只注册一次）。"""
    if hass.services.has_service(DOMAIN, SERVICE_SEND):
        return

    async def _async_handle_send(call: ServiceCall) -> None:
        """处理 qqbot_notify.send 动作。"""
        entry = _async_get_entry(hass, call.data.get(ATTR_ENTRY_ID))
        data = entry.runtime_data

        target = str(call.data.get(ATTR_TARGET) or data.default_target or "").strip()
        if not target:
            raise ServiceValidationError(
                "未指定 target，且该 QQBot 条目没有设置默认接收者（Default Target）"
            )

        message = call.data[ATTR_MESSAGE]
        if title := call.data.get(ATTR_TITLE):
            message = f"{title}\n{message}"

        await data.client.async_send_message(
            target,
            message,
            is_group=call.data.get(ATTR_IS_GROUP, False),
            msg_id=call.data.get(ATTR_MSG_ID),
            msg_seq=call.data.get(ATTR_MSG_SEQ, 1),
        )

    hass.services.async_register(
        DOMAIN, SERVICE_SEND, _async_handle_send, schema=SERVICE_SEND_SCHEMA
    )
    _LOGGER.debug("已注册动作 %s.%s", DOMAIN, SERVICE_SEND)


@callback
def async_unregister_services(hass: HomeAssistant) -> None:
    """注销 qqbot_notify.send 动作。"""
    if hass.services.has_service(DOMAIN, SERVICE_SEND):
        hass.services.async_remove(DOMAIN, SERVICE_SEND)


@callback
def _async_get_entry(
    hass: HomeAssistant, entry_id: str | None
) -> QQBotConfigEntry:
    """取出目标配置条目：优先按 entry_id，否则在只有一条时自动选择。"""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)

    if entry_id:
        for entry in entries:
            if entry.entry_id == entry_id:
                return entry
        raise ServiceValidationError(f"找不到已加载的 QQBot 配置条目：{entry_id}")

    if not entries:
        raise ServiceValidationError("QQBot Notify 没有已加载的配置条目")
    if len(entries) > 1:
        raise ServiceValidationError(
            "配置了多个 QQBot，请通过 entry_id 指定使用哪一个条目"
        )

    return entries[0]
