"""QQBot Notify 集成入口。"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from .api import QQBotClient
from .const import CONF_APPID, CONF_DEFAULT_TARGET, CONF_SECRET, DOMAIN, PLATFORMS
from .data import QQBotConfigEntry, QQBotData
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: QQBotConfigEntry) -> bool:
    """设置配置条目。"""
    appid = str(entry.data.get(CONF_APPID, "")).strip()
    secret = str(entry.data.get(CONF_SECRET, "")).strip()
    # 选项优先于初始配置（允许通过选项把默认接收者改回空）
    if CONF_DEFAULT_TARGET in entry.options:
        default_target = str(entry.options[CONF_DEFAULT_TARGET] or "").strip()
    else:
        default_target = str(entry.data.get(CONF_DEFAULT_TARGET) or "").strip()

    entry.runtime_data = QQBotData(
        appid=appid,
        secret=secret,
        default_target=default_target,
        client=QQBotClient(hass, appid, secret),
    )

    # 转发到 notify 平台建立通知实体；平台设置失败时 HA 会记录错误并使条目设置失败
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 注册支持 target / is_group / msg_id 的扩展动作
    async_register_services(hass)

    # 选项变更后重载条目，让新的默认接收者立即生效
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    _LOGGER.debug(
        "QQBot Notify 已加载：appid=%s，默认接收者=%s",
        appid,
        "已设置" if default_target else "未设置",
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: QQBotConfigEntry) -> bool:
    """卸载配置条目。"""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    # 只剩当前条目仍在（卸载中的）列表里时，说明没有别的机器人了
    remaining = [
        other
        for other in hass.config_entries.async_loaded_entries(DOMAIN)
        if other.entry_id != entry.entry_id
    ]
    if not remaining:
        async_unregister_services(hass)

    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: QQBotConfigEntry
) -> None:
    """选项变化后重新加载条目。"""
    await hass.config_entries.async_reload(entry.entry_id)
