"""Live mirror of the board as a camera entity (usable in any dashboard)."""
from __future__ import annotations

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .board import bmp_to_png
from .const import DOMAIN, LIVE_INTERVAL


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    add([PerronLiveCamera(hass.data[DOMAIN][entry.entry_id]["board"], entry)])


class PerronLiveCamera(Camera):
    """What the board shows right now (LED look)."""

    _attr_has_entity_name = True
    _attr_name = "Live"
    _attr_icon = "mdi:view-dashboard-variant"
    _attr_frame_interval = LIVE_INTERVAL

    def __init__(self, board, entry: ConfigEntry) -> None:
        super().__init__()
        self._board = board
        self._attr_unique_id = f"{entry.entry_id}_live"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}, "name": "Perron Studio",
                                  "manufacturer": "Perron", "model": "Studio"}

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        try:
            bmp = await self._board.screen_bmp()
        except Exception:  # noqa: BLE001 - board offline
            return None
        scale = 4 if not width else max(1, min(8, width // 192))
        return await self.hass.async_add_executor_job(bmp_to_png, bmp, scale, True)
