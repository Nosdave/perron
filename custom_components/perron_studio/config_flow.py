"""Config flow: pick the Perron board among the ESPHome devices, create the access token."""
from __future__ import annotations

import secrets
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_DEVICE, CONF_ESPHOME_ENTRY, CONF_HOST, CONF_TOKEN, DOMAIN


def _perron_like(entry) -> bool:
    name = (entry.data.get("device_name") or entry.title or "").lower()
    return "perron" in name or "diele" in name or "departure" in name


class PerronStudioConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up Perron Studio for one board."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        boards = {
            e.entry_id: f"{e.title} ({e.data.get('host', '?')})"
            for e in self.hass.config_entries.async_entries("esphome")
        }
        if not boards:
            return self.async_abort(reason="no_esphome")
        if user_input is not None:
            entry = self.hass.config_entries.async_get_entry(user_input[CONF_ESPHOME_ENTRY])
            device = (entry.data.get("device_name") or entry.title).replace("-", "_").lower()
            await self.async_set_unique_id(f"perron_studio_{device}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"Perron Studio – {entry.title}",
                data={
                    CONF_ESPHOME_ENTRY: entry.entry_id,
                    CONF_DEVICE: device,
                    CONF_HOST: entry.data.get("host"),
                    # secret for the board's /perron/* endpoints; transferred over the encrypted API
                    CONF_TOKEN: secrets.token_urlsafe(24),
                },
            )
        default = next((k for k in boards if _perron_like(self.hass.config_entries.async_get_entry(k))), None)
        schema = vol.Schema(
            {vol.Required(CONF_ESPHOME_ENTRY, default=default or vol.UNDEFINED): vol.In(boards)}
        )
        return self.async_show_form(step_id="user", data_schema=schema)
