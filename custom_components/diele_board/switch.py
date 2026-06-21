"""switch.diele_board_power — hard on/off (blank) for the panel."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import board_device


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([DielePowerSwitch(entry)])


class DielePowerSwitch(SwitchEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_name = "Power"
    _attr_icon = "mdi:power"

    def __init__(self, entry: ConfigEntry) -> None:
        self._attr_unique_id = f"{entry.entry_id}_power"
        self._attr_device_info = board_device(entry)
        self._attr_is_on = True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self._attr_is_on = last.state == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()
