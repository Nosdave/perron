"""Editable Waze destination helpers, owned by the integration.

One ``text.*`` entity per commute slot. The address is entered/edited at runtime
in the HA UI (or by an automation, e.g. a calendar trip) and is stored as the
entity state — it never lives in the repo. The coordinator reads these values and
computes travel time via pywaze. The display label per slot is user-configurable
in the config/options flow (no personal names ship in the code).
"""
from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import COMMUTE_SLOTS, DOMAIN
from .entity import board_device


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        DieleDestinationText(coordinator, entry, slot) for slot in COMMUTE_SLOTS
    )


class DieleDestinationText(TextEntity, RestoreEntity):
    """A runtime-editable Waze destination address for one commute slot."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:map-marker"
    _attr_native_max = 200

    def __init__(self, coordinator, entry: ConfigEntry, slot: str) -> None:
        self._coordinator = coordinator
        self._slot = slot
        self._attr_name = f"Destination {coordinator.label_for(slot)}"
        self._attr_unique_id = f"{entry.entry_id}_dest_{slot}"
        self._attr_device_info = board_device(entry)
        self._attr_native_value = ""

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in (None, "unknown", "unavailable"):
            self._attr_native_value = last.state
        self._coordinator.set_destination(self._slot, self._attr_native_value)

    async def async_set_value(self, value: str) -> None:
        self._attr_native_value = value
        self._coordinator.set_destination(self._slot, value)
        self.async_write_ha_state()
        await self._coordinator.async_request_refresh()
