"""Tile engine: stores tiles, renders their fields (entities / templates), decides when and where
they appear, and pushes them to the board as card JSON (see docs/cards.md)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Any, Callable

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from .board import Board
from .const import REFRESH_ACTIVE, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

ENTITY_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
ENTITY_IN_TEXT_RE = re.compile(r"\b([a-z_]+\.[a-z0-9_]+)\b")
DAYS = ["mo", "di", "mi", "do", "fr", "sa", "so"]


def new_tile(name: str = "Neue Kachel") -> dict:
    return {
        "id": "t" + secrets.token_hex(4),
        "name": name,
        "enabled": True,
        "template": "hero",
        "title": name,
        "icon": "",
        "accent": "b",
        "value": "",
        "unit": "",
        "sub1": "",
        "sub2": "",
        "pct": "",
        "text": "",
        "image": "",
        "elements": "",
        "cells": [],
        "rows": [],
        "when": {"mode": "manual", "condition": "", "days": "Mo-Fr", "from": "", "to": "",
                 "every": 0, "show": 10, "events": [], "voice": ""},
        "where": {"zone": "p", "duration": 20, "prio": 2},
    }


class TileEngine:
    """Keeps all tiles live."""

    def __init__(self, hass: HomeAssistant, board: Board, entry_id: str) -> None:
        self.hass = hass
        self.board = board
        self.store: Store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry_id}")
        self.tiles: list[dict] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        self._active: dict[str, bool] = {}
        self._last_hash: dict[str, str] = {}
        self._last_push: dict[str, float] = {}
        self._debounce: dict[str, asyncio.TimerHandle] = {}
        self.listeners: list[Callable[[], None]] = []

    # ------------------------------------------------------------- persistence
    async def async_load(self) -> None:
        data = await self.store.async_load()
        self.tiles = (data or {}).get("tiles", [])
        self._setup_listeners()
        await self.async_evaluate_all()

    async def async_save(self) -> None:
        await self.store.async_save({"tiles": self.tiles})
        self._setup_listeners()
        await self.async_evaluate_all()
        for cb in self.listeners:
            cb()

    def get(self, tile_id_or_name: str) -> dict | None:
        key = (tile_id_or_name or "").strip().lower()
        for t in self.tiles:
            if t["id"].lower() == key or t.get("name", "").strip().lower() == key:
                return t
        return None

    async def async_upsert(self, tile: dict) -> dict:
        base = new_tile()
        base.update(tile)
        base["when"] = {**new_tile()["when"], **(tile.get("when") or {})}
        base["where"] = {**new_tile()["where"], **(tile.get("where") or {})}
        for i, t in enumerate(self.tiles):
            if t["id"] == base["id"]:
                self.tiles[i] = base
                break
        else:
            self.tiles.append(base)
        self._last_hash.pop(base["id"], None)
        await self.async_save()
        return base

    async def async_delete(self, tile_id: str) -> None:
        self.tiles = [t for t in self.tiles if t["id"] != tile_id]
        if self._active.pop(tile_id, False):
            await self.board.delete_card(f"st_{tile_id}")
        await self.async_save()

    async def async_unload(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()
        for h in self._debounce.values():
            h.cancel()

    # ------------------------------------------------------------- field rendering
    def render(self, text: Any) -> str:
        s = "" if text is None else str(text).strip()
        if not s:
            return ""
        if "{{" in s or "{%" in s:
            try:
                return str(Template(s, self.hass).async_render(parse_result=False)).strip()
            except TemplateError as err:
                return f"⚠ {err}"[:40]
        if ENTITY_RE.match(s):
            st = self.hass.states.get(s)
            if st is not None:
                return st.state
        return s

    def _num(self, text: Any) -> int | None:
        v = self.render(text)
        try:
            return max(0, min(100, int(round(float(v)))))
        except (TypeError, ValueError):
            return None

    def entities_of(self, tile: dict) -> set[str]:
        """Entities a tile depends on (plain entity ids and ids inside templates)."""
        found: set[str] = set()

        def scan(v: Any) -> None:
            if isinstance(v, str):
                for m in ENTITY_IN_TEXT_RE.findall(v):
                    if self.hass.states.get(m) is not None:
                        found.add(m)
            elif isinstance(v, dict):
                for x in v.values():
                    scan(x)
            elif isinstance(v, list):
                for x in v:
                    scan(x)

        scan({k: v for k, v in tile.items() if k not in ("when", "where")})
        scan(tile.get("when", {}).get("condition", ""))
        return found

    # ------------------------------------------------------------- card JSON
    def build_card(self, tile: dict, card_id: str | None = None) -> dict:
        t = tile.get("template", "hero")
        card: dict[str, Any] = {"id": card_id or f"st_{tile['id']}", "t": t}
        title = self.render(tile.get("title"))
        if title:
            card["ti"] = title
        if tile.get("icon"):
            card["ic"] = tile["icon"]
        if tile.get("accent") and tile["accent"] != "w":
            card["ac"] = tile["accent"]
        sub = "|".join(x for x in (self.render(tile.get("sub1")), self.render(tile.get("sub2"))) if x) \
            if tile.get("sub2") else self.render(tile.get("sub1"))
        if t in ("hero", "prog", "ring"):
            val = self.render(tile.get("value"))
            if val:
                card["val"] = val
            if tile.get("unit"):
                card["u"] = self.render(tile.get("unit"))
            if sub:
                card["sub"] = sub
            pct = self._num(tile.get("pct"))
            if pct is not None and t == "prog":
                card["pct"] = pct
        elif t == "msg":
            card["sub"] = self.render(tile.get("text")) or sub
        elif t == "kpi":
            cells = []
            for c in (tile.get("cells") or [])[:3]:
                pct = self._num(c.get("pct")) if c.get("pct") else None
                cells.append([self.render(c.get("label")), self.render(c.get("value")), self.render(c.get("unit")),
                              c.get("color") or "w", -1 if pct is None else pct, self.render(c.get("sub")),
                              c.get("icon") or ""])
            card["kpi"] = cells
        elif t in ("list", "agenda"):
            rows = []
            for r in (tile.get("rows") or [])[: (8 if t == "agenda" else 4)]:
                rows.append([r.get("icon") or "", self.render(r.get("label")), self.render(r.get("value")),
                             r.get("color") or "w"])
            card["rows"] = rows
        elif t == "img":
            card["img"] = f"st_{tile['id']}"[:24]
            if sub:
                card["ft"] = sub
        elif t == "cv":
            try:
                card["el"] = json.loads(self.render(tile.get("elements")) or "[]")
            except ValueError:
                card["el"] = []
        if t == "ring" and tile.get("image"):
            card["img"] = f"st_{tile['id']}"[:24]
        return card

    def place(self, card: dict, tile: dict, on_demand: bool = False, zone: str | None = None,
              duration: int | None = None) -> dict:
        where = tile.get("where", {})
        when = tile.get("when", {})
        z = zone or where.get("zone", "p")
        dur = int(duration or where.get("duration") or 20)
        if on_demand:
            if z == "f":
                card.update({"p": 1, "z": "f", "hold": max(3, min(30, dur)), "ttl": dur, "force": 1})
            else:
                card.update({"p": 2 if z == "p" else 3, "z": z, "ttl": dur})
            return card
        prio = int(where.get("prio") or 2)
        card.update({"p": max(1, min(3, prio)), "z": z, "ttl": REFRESH_ACTIVE * 2})
        if int(when.get("every") or 0) > 0:
            card["every"] = int(when["every"])
            card["show"] = int(when.get("show") or 10)
        return card

    # ------------------------------------------------------------- when is a tile active?
    def is_active(self, tile: dict, now: datetime | None = None) -> bool:
        if not tile.get("enabled", True):
            return False
        when = tile.get("when", {})
        mode = when.get("mode", "manual")
        if mode == "manual":
            return False
        if mode == "always":
            return True
        if mode == "condition":
            v = self.render(when.get("condition")).lower()
            return v in ("true", "on", "1", "yes", "ja")
        if mode == "schedule":
            return _in_window(when, now or dt_util.now())
        return False

    # ------------------------------------------------------------- pushing
    async def _image_for(self, tile: dict) -> None:
        src = (tile.get("image") or "").strip()
        if not src:
            return
        url = src
        if ENTITY_RE.match(src):
            st = self.hass.states.get(src)
            pic = st.attributes.get("entity_picture") if st else None
            if not pic:
                return
            try:
                base = get_url(self.hass, allow_external=False, prefer_external=False)
            except NoURLAvailableError:
                return
            url = base + pic
        await self.board.push_image_url(f"st_{tile['id']}"[:24], url)

    async def async_push_state(self, tile: dict, force: bool = False) -> None:
        card = self.place(self.build_card(tile), tile)
        h = hashlib.sha1(json.dumps(card, sort_keys=True).encode()).hexdigest()
        now = asyncio.get_running_loop().time()
        if not force and self._last_hash.get(tile["id"]) == h and now - self._last_push.get(tile["id"], 0) < REFRESH_ACTIVE:
            return
        if tile.get("template") in ("img", "ring"):
            await self._image_for(tile)
        if await self.board.push_card(card):
            self._last_hash[tile["id"]] = h
            self._last_push[tile["id"]] = now

    async def async_show(self, tile: dict, zone: str | None = None, duration: int | None = None) -> None:
        """On demand (voice, button, automation, event trigger)."""
        if tile.get("template") in ("img", "ring"):
            await self._image_for(tile)
        card = self.place(self.build_card(tile, f"st_{tile['id']}_abruf"), tile, True, zone, duration)
        await self.board.push_card(card)

    async def async_hide(self, tile: dict) -> None:
        await self.board.delete_card(f"st_{tile['id']}_abruf")
        await self.board.delete_card(f"st_{tile['id']}")
        self._active[tile["id"]] = False

    async def async_evaluate(self, tile: dict, force: bool = False) -> None:
        active = self.is_active(tile)
        was = self._active.get(tile["id"], False)
        if active:
            await self.async_push_state(tile, force=force or not was)
        elif was:
            await self.board.delete_card(f"st_{tile['id']}")
            self._last_hash.pop(tile["id"], None)
        self._active[tile["id"]] = active

    async def async_evaluate_all(self, *_: Any) -> None:
        for tile in list(self.tiles):
            try:
                await self.async_evaluate(tile)
            except Exception:  # noqa: BLE001 - one bad tile must not stop the others
                _LOGGER.exception("Kachel %s", tile.get("name"))

    # ------------------------------------------------------------- listeners
    def _setup_listeners(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs = [async_track_time_interval(self.hass, self.async_evaluate_all, timedelta(seconds=30))]
        for tile in self.tiles:
            if not tile.get("enabled", True):
                continue
            ents = self.entities_of(tile)
            if ents:
                self._unsubs.append(async_track_state_change_event(
                    self.hass, list(ents), self._content_changed(tile["id"])))
            for ev in (tile.get("when", {}).get("events") or []):
                ent = (ev.get("entity") or "").strip()
                if ent:
                    self._unsubs.append(async_track_state_change_event(
                        self.hass, [ent], self._event_trigger(tile["id"], (ev.get("to") or "").strip())))

    def _content_changed(self, tile_id: str) -> Callable[[Event], None]:
        @callback
        def _cb(_event: Event) -> None:  # debounce bursts of state changes (2 s)
            old = self._debounce.pop(tile_id, None)
            if old:
                old.cancel()

            def _fire() -> None:
                tile = next((t for t in self.tiles if t["id"] == tile_id), None)
                if tile:
                    self.hass.async_create_task(self.async_evaluate(tile))

            self._debounce[tile_id] = self.hass.loop.call_later(2.0, _fire)

        return _cb

    def _event_trigger(self, tile_id: str, to: str) -> Callable[[Event], None]:
        @callback
        def _cb(event: Event) -> None:
            new = event.data.get("new_state")
            old = event.data.get("old_state")
            if new is None or (old is not None and old.state == new.state):
                return
            if to and new.state != to:
                return
            tile = next((t for t in self.tiles if t["id"] == tile_id), None)
            if tile and tile.get("enabled", True):
                self.hass.async_create_task(self.async_show(tile))

        return _cb


def _hm(v: str) -> int | None:
    try:
        h, m = v.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def _in_window(when: dict, now: datetime) -> bool:
    days = (when.get("days") or "").strip().lower()
    if days and days not in ("täglich", "taeglich", "alle"):
        ok = False
        for tok in days.replace(" ", "").split(","):
            a, _, b = tok.partition("-")
            if a[:2] in DAYS:
                i0 = DAYS.index(a[:2])
                i1 = DAYS.index(b[:2]) if b[:2] in DAYS else i0
                k = i0
                while True:
                    if k == now.weekday():
                        ok = True
                    if k == i1:
                        break
                    k = (k + 1) % 7
        if not ok:
            return False
    f, t = _hm(when.get("from") or ""), _hm(when.get("to") or "")
    if f is None or t is None:
        return True
    m = now.hour * 60 + now.minute
    return f <= m < t if f <= t else (m >= f or m < t)
