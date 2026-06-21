"""The Diele Departure Board integration (HACS-compatible).

HA-side producer of the entity contract consumed by the ESPHome node.
See ../../docs/02-architecture.md and ../../docs/04-homeassistant.md.
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS
from .coordinator import DieleBoardCoordinator

_ALERT_SCHEMA = vol.Schema(
    {
        vol.Required("text"): cv.string,
        vol.Optional("level", default="info"): vol.In(["info", "warn", "crit"]),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Diele Departure Board from a config entry."""
    coordinator = DieleBoardCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    async def _show_alert(call: ServiceCall) -> None:
        coordinator.set_manual_alert(call.data["text"], call.data.get("level", "info"))
        await coordinator.async_request_refresh()

    if not hass.services.has_service(DOMAIN, "show_alert"):
        hass.services.async_register(DOMAIN, "show_alert", _show_alert, schema=_ALERT_SCHEMA)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, "show_alert")
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
