"""number.diele_board_brightness — brightness target the ESP blends with its lux reading."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import board_device


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([DieleBrightnessNumber(entry)])


class DieleBrightnessNumber(NumberEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_name = "Brightness"
    _attr_native_min_value = 0
    _attr_native_max_value = 255
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:brightness-6"

    def __init__(self, entry: ConfigEntry) -> None:
        self._attr_unique_id = f"{entry.entry_id}_brightness"
        self._attr_device_info = board_device(entry)
        self._attr_native_value = 180

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in (None, "unknown", "unavailable"):
            try:
                self._attr_native_value = min(255.0, max(0.0, float(last.state)))
            except ValueError:
                pass

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()
