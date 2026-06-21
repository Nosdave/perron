"""Shared device info so all entities group under one HA device."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN


def board_device(entry: ConfigEntry) -> DeviceInfo:
    """Return the shared DeviceInfo for the Diele Departure Board."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Diele Departure Board",
        manufacturer="ha-diele-board",
        model="Departure board",
    )
