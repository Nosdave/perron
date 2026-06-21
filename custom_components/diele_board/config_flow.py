"""Config + options flow for Diele Departure Board."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import StibClient, StibError
from .const import (
    CONF_BUS_LINE,
    CONF_BUS_POINT,
    CONF_COMMUTE_LABEL_1,
    CONF_COMMUTE_LABEL_2,
    CONF_PARTNER_KEY,
    CONF_PRESENCE_ENTITIES,
    CONF_TRAIN_PLATFORM,
    CONF_TRAIN_STATION,
    CONF_TRAM_LINE,
    CONF_TRAM_POINT,
    CONF_WEATHER_ENTITY,
    DEFAULT_BUS_LINE,
    DEFAULT_BUS_POINT,
    DEFAULT_COMMUTE_LABEL_1,
    DEFAULT_COMMUTE_LABEL_2,
    DEFAULT_TRAIN_PLATFORM,
    DEFAULT_TRAIN_STATION,
    DEFAULT_TRAM_LINE,
    DEFAULT_TRAM_POINT,
    DOMAIN,
)


def _schema(d: dict[str, Any]) -> vol.Schema:
    """Build the config/options schema, pre-filled from ``d``.

    Optional entity selectors use ``suggested_value`` (not ``default``) so they can
    be left empty — a default of "" is an invalid entity and would force a pick.
    """
    fields: dict[Any, Any] = {
        vol.Required(CONF_PARTNER_KEY, default=d.get(CONF_PARTNER_KEY, "")): str,
        vol.Required(CONF_TRAM_POINT, default=d.get(CONF_TRAM_POINT, DEFAULT_TRAM_POINT)): str,
        vol.Required(CONF_TRAM_LINE, default=d.get(CONF_TRAM_LINE, DEFAULT_TRAM_LINE)): str,
        vol.Required(CONF_BUS_POINT, default=d.get(CONF_BUS_POINT, DEFAULT_BUS_POINT)): str,
        vol.Required(CONF_BUS_LINE, default=d.get(CONF_BUS_LINE, DEFAULT_BUS_LINE)): str,
        vol.Required(CONF_TRAIN_STATION, default=d.get(CONF_TRAIN_STATION, DEFAULT_TRAIN_STATION)): str,
        vol.Optional(CONF_TRAIN_PLATFORM, default=d.get(CONF_TRAIN_PLATFORM, DEFAULT_TRAIN_PLATFORM)): str,
        vol.Optional(
            CONF_WEATHER_ENTITY, description={"suggested_value": d.get(CONF_WEATHER_ENTITY)}
        ): selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
        vol.Optional(
            CONF_PRESENCE_ENTITIES, description={"suggested_value": d.get(CONF_PRESENCE_ENTITIES)}
        ): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["binary_sensor", "input_boolean", "person"], multiple=True
            )
        ),
        vol.Optional(CONF_COMMUTE_LABEL_1, default=d.get(CONF_COMMUTE_LABEL_1, DEFAULT_COMMUTE_LABEL_1)): str,
        vol.Optional(CONF_COMMUTE_LABEL_2, default=d.get(CONF_COMMUTE_LABEL_2, DEFAULT_COMMUTE_LABEL_2)): str,
    }
    return vol.Schema(fields)


async def _validate(hass, user_input: dict[str, Any]) -> dict[str, str]:
    """Return {} if the STIB key + tram point work, else an errors dict."""
    session = async_get_clientsession(hass)
    try:
        await StibClient(session, user_input[CONF_PARTNER_KEY]).waiting_times(
            user_input[CONF_TRAM_POINT]
        )
    except StibError:
        return {"base": "cannot_connect"}
    except Exception:  # noqa: BLE001
        return {"base": "unknown"}
    return {}


class DieleBoardConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate(self.hass, user_input)
            if not errors:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Diele Departure Board", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(user_input or {}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DieleBoardOptionsFlow(config_entry)


class DieleBoardOptionsFlow(OptionsFlow):
    """Allow editing the settings after setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(title="", data=user_input)
        current = {**self._entry.data, **self._entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_schema(current), errors=errors
        )
