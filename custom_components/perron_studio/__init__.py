"""Perron Studio – design and schedule cards for the Perron LED departure board from Home Assistant.

* Tiles (stored in HA) are rendered from entities / templates and pushed to the board.
* A side panel shows the board live and edits tiles with a pixel-exact preview rendered by the board.
* Services perron_studio.show / hide for voice commands, buttons and automations.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

import voluptuous as vol

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_interval

from .board import Board
from .const import CONF_DEVICE, CONF_HOST, CONF_TOKEN, DOMAIN, PANEL_JS, PANEL_URL
from .engine import TileEngine
from .http import async_register_views

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.CAMERA]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    board = Board(hass, entry.data[CONF_DEVICE], entry.data[CONF_HOST], entry.data[CONF_TOKEN])
    engine = TileEngine(hass, board, entry.entry_id)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"board": board, "engine": engine}

    # hand the access token to the board (encrypted ESPHome API); retry until the board is online
    async def _ensure_token(*_):
        if await board.set_token():
            data["token_ok"] = True

    data = hass.data[DOMAIN][entry.entry_id]
    data["token_ok"] = False
    await _ensure_token()
    entry.async_on_unload(async_track_time_interval(hass, _ensure_token, timedelta(minutes=5)))

    await engine.async_load()

    if not hass.data[DOMAIN].get("_ui"):
        await hass.http.async_register_static_paths([
            StaticPathConfig("/perron_studio_static", str(Path(__file__).parent / "frontend"), cache_headers=False)
        ])
        async_register_views(hass)
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL,
            webcomponent_name="perron-studio-panel",
            module_url=f"{PANEL_JS}?v=0.3.0",
            sidebar_title="Perron Studio",
            sidebar_icon="mdi:view-dashboard-variant",
            require_admin=True,
            config={"entry_id": entry.entry_id},
        )
        _register_services(hass)
        hass.data[DOMAIN]["_ui"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    data = hass.data[DOMAIN].pop(entry.entry_id, None)
    if data:
        await data["engine"].async_unload()
    if not [k for k in hass.data[DOMAIN] if not k.startswith("_")]:
        from homeassistant.components import frontend
        frontend.async_remove_panel(hass, PANEL_URL)
        hass.data[DOMAIN].pop("_ui", None)
    return ok


def first_engine(hass: HomeAssistant) -> TileEngine:
    for k, v in hass.data.get(DOMAIN, {}).items():
        if not k.startswith("_"):
            return v["engine"]
    raise ServiceValidationError("Perron Studio ist nicht eingerichtet")


@callback
def _register_services(hass: HomeAssistant) -> None:
    zone = vol.In(["f", "p", "l", "vollbild", "kachel", "infozeile"])
    zmap = {"vollbild": "f", "kachel": "p", "infozeile": "l"}

    async def show(call: ServiceCall) -> None:
        eng = first_engine(hass)
        tile = eng.get(call.data["tile"])
        z = call.data.get("zone")
        z = zmap.get(z, z)
        if tile is None:  # also the id of a card an automation sends (e.g. "pv")
            if await eng.async_show_external(call.data["tile"].strip(), z, call.data.get("duration")):
                return
            raise ServiceValidationError(f"Kachel „{call.data['tile']}“ nicht gefunden")
        await eng.async_show(tile, z, call.data.get("duration"))

    async def hide(call: ServiceCall) -> None:
        eng = first_engine(hass)
        tile = eng.get(call.data["tile"])
        if tile is None:
            raise ServiceValidationError(f"Kachel „{call.data['tile']}“ nicht gefunden")
        await eng.async_hide(tile)

    async def commute(call: ServiceCall) -> None:
        await first_engine(hass).board.show_commute(call.data["slot"], call.data.get("duration", 30))

    hass.services.async_register(DOMAIN, "show", show, schema=vol.Schema({
        vol.Required("tile"): cv.string, vol.Optional("zone"): zone,
        vol.Optional("duration"): vol.All(vol.Coerce(int), vol.Range(min=3, max=3600))}))
    hass.services.async_register(DOMAIN, "hide", hide, schema=vol.Schema({vol.Required("tile"): cv.string}))
    hass.services.async_register(DOMAIN, "show_commute", commute, schema=vol.Schema({
        vol.Required("slot"): vol.In([1, 2]),
        vol.Optional("duration", default=30): vol.All(vol.Coerce(int), vol.Range(min=5, max=120))}))
