"""QQBot Notify 配置条目的运行期数据。"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .api import QQBotClient


@dataclass
class QQBotData:
    """保存在 ConfigEntry.runtime_data 中的数据。"""

    appid: str
    secret: str
    default_target: str
    client: QQBotClient


# 配置条目类型别名，便于平台与动作模块复用。
QQBotConfigEntry = ConfigEntry[QQBotData]
