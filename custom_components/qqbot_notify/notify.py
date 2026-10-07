"""QQBot 通知平台：基于 notify 实体（NotifyEntity）。"""

from __future__ import annotations

import logging

from homeassistant.components.notify import (
    NotifyEntity,
    NotifyEntityDescription,
    NotifyEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN
from .data import QQBotConfigEntry

_LOGGER = logging.getLogger(__name__)

# 通知实体自身不轮询
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: QQBotConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """通过配置条目建立通知实体。"""
    async_add_entities([QQBotNotifyEntity(config_entry)])


class QQBotNotifyEntity(NotifyEntity):
    """把消息推送到该机器人默认接收者的通知实体。"""

    entity_description = NotifyEntityDescription(key=DOMAIN)
    _attr_has_entity_name = False
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, config_entry: QQBotConfigEntry) -> None:
        """初始化实体。"""
        self._config_entry = config_entry
        self._attr_name = config_entry.title
        self._attr_unique_id = f"{config_entry.entry_id}_notify"

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """供 notify.send_message 动作调用。"""
        data = self._config_entry.runtime_data
        if not data.default_target:
            raise ServiceValidationError(
                "该 QQBot 条目没有设置默认接收者（Default Target）；"
                "请重新添加集成并填写，或改用 qqbot_notify.send 动作并通过 target 指定接收者"
            )

        content = f"{title}\n{message}" if title else message
        await data.client.async_send_message(data.default_target, content)
