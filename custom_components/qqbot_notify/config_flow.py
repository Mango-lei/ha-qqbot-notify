"""QQBot Notify 配置流程（配置 + 选项）。"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import QQBotApiError, QQBotAuthError, QQBotClient, QQBotConnectionError
from .const import CONF_APPID, CONF_DEFAULT_TARGET, CONF_SECRET, DOMAIN

_LOGGER = logging.getLogger(__name__)

OPTIONS_SCHEMA = vol.Schema({vol.Optional(CONF_DEFAULT_TARGET): str})


class QQBotConfigFlow(ConfigFlow, domain=DOMAIN):
    """处理配置流程。"""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """处理用户步骤。"""
        errors: dict[str, str] = {}

        if user_input is not None:
            appid = str(user_input.get(CONF_APPID, "")).strip()
            secret = str(user_input.get(CONF_SECRET, "")).strip()
            target = str(user_input.get(CONF_DEFAULT_TARGET) or "").strip()

            if not appid.isdigit():
                errors[CONF_APPID] = "invalid_appid"
            if not secret:
                errors[CONF_SECRET] = "secret_required"

            if not errors:
                await self.async_set_unique_id(appid)
                self._abort_if_unique_id_configured()
                try:
                    # 添加时就校验凭证，避免填错直到发送时才暴露
                    client = QQBotClient(self.hass, appid, secret)
                    await client.async_validate_credentials()
                except QQBotAuthError:
                    errors["base"] = "invalid_auth"
                except QQBotConnectionError:
                    errors["base"] = "cannot_connect"
                except QQBotApiError:
                    _LOGGER.exception("QQBot 凭证校验失败")
                    errors["base"] = "unknown"
                else:
                    return self.async_create_entry(
                        title=f"QQBot {appid}",
                        data={
                            CONF_APPID: appid,
                            CONF_SECRET: secret,
                            CONF_DEFAULT_TARGET: target,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_APPID): str,
                    vol.Required(CONF_SECRET): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(CONF_DEFAULT_TARGET, default=""): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> QQBotOptionsFlow:
        """创建选项流程。"""
        return QQBotOptionsFlow()


class QQBotOptionsFlow(OptionsFlow):
    """调整默认接收者（保存后自动重载条目）。"""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """处理选项步骤。"""
        if user_input is not None:
            target = str(user_input.get(CONF_DEFAULT_TARGET) or "").strip()
            return self.async_create_entry(data={CONF_DEFAULT_TARGET: target})

        suggested = dict(self.config_entry.data)
        suggested.update(self.config_entry.options)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(OPTIONS_SCHEMA, suggested),
        )
