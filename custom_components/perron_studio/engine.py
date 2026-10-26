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

import aiohttp

from homeassistant.components.http.auth import async_sign_path
from homeassistant.const import EVENT_CALL_SERVICE
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_util

from .board import Board
from .const import REFRESH_ACTIVE, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)

ENTITY_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
CARD_ID_RE = re.compile(r"[\"']id[\"']\s*:\s*[\"']([a-z0-9_]{2,32})[\"']")
ENTITY_IN_TEXT_RE = re.compile(r"\b([a-z_]+\.[a-z0-9_]+)\b")
DAYS = ["mo", "di", "mi", "do", "fr", "sa", "so"]


def _to_board_jpeg(raw: bytes) -> bytes:
    """Any picture -> RGB JPEG that fits 192x192 (the board decodes it fully in PSRAM)."""
    import io

    from PIL import Image

    im = Image.open(io.BytesIO(raw))
    im.thumbnail((192, 192))
    out = io.BytesIO()
    im.convert("RGB").save(out, "JPEG", quality=85)
    return out.getvalue()


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
        "card": "",
        "elements": "",
        "cells": [],
        "rows": [],
        "when": {"mode": "manual", "condition": "", "days": "Mo-Fr", "from": "", "to": "",
                 "every": 0, "show": 10, "events": [], "voice": "", "min_interval": 10},
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
        self._later: dict[str, asyncio.TimerHandle] = {}
        self.listeners: list[Callable[[], None]] = []
        self.images: dict[str, bytes] = {}           # key -> small JPEG served to the board
        self._img_sent: dict[str, tuple[str, float]] = {}
        # cards other automations send to the board (esphome.<device>_push_json), id -> record
        self.external: dict[str, dict] = {}
        self._ext_unsub: CALLBACK_TYPE | None = None
        self._ext_save: asyncio.TimerHandle | None = None

    # ------------------------------------------------------------- persistence
    async def async_load(self) -> None:
        data = await self.store.async_load()
        self.tiles = (data or {}).get("tiles", [])
        self.external = (data or {}).get("external", {})
        self._ext_unsub = self.hass.bus.async_listen(EVENT_CALL_SERVICE, self._on_service_call)
        self._setup_listeners()
        await self.async_evaluate_all()

    async def async_save(self) -> None:
        await self.store.async_save({"tiles": self.tiles, "external": self.external})
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
        if self._ext_unsub:
            self._ext_unsub()
        if self._ext_save:
            self._ext_save.cancel()
        for u in self._unsubs:
            u()
        self._unsubs.clear()
        for h in [*self._debounce.values(), *self._later.values()]:
            h.cancel()

    # ------------------------------------------------------------- cards from automations
    @callback
    def _on_service_call(self, event: Event) -> None:
        d = event.data
        if d.get("domain") != "esphome" or d.get("service") != self.board._service("push_json"):
            return
        raw = (d.get("service_data") or {}).get("card")
        try:
            card = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        except (TypeError, ValueError):
            return
        cid = str(card.get("id") or "")
        if not cid or cid.startswith(("st_", "x_", "__")):  # Studio's own cards
            return
        rec = self.external.setdefault(cid, {"id": cid, "count": 0})
        rec["count"] = rec.get("count", 0) + 1
        rec["at"] = dt_util.now().isoformat(timespec="seconds")
        rec["deleted"] = bool(card.get("del"))
        auto = self._automation_of(event)
        if auto:
            rec["automation"] = auto
        if not rec["deleted"]:
            rec["card"] = card
        if self._ext_save:
            self._ext_save.cancel()
        self._ext_save = self.hass.loop.call_later(
            30, lambda: self.hass.async_create_task(
                self.store.async_save({"tiles": self.tiles, "external": self.external})))
        for cb in self.listeners:
            cb()

    def automations_overview(self) -> list[dict]:
        """All automations that send cards to this board (from their configuration), with the
        card ids they mention, so the panel lists them before they have sent anything."""
        comp = self.hass.data.get("automation")
        prefix = f"esphome.{self.board.device}_"
        out = []
        for st in self.hass.states.async_all("automation"):
            ent = comp.get_entity(st.entity_id) if comp and hasattr(comp, "get_entity") else None
            raw = getattr(ent, "raw_config", None)
            if not raw:
                continue
            txt = json.dumps(raw, ensure_ascii=False, default=str)
            if prefix not in txt:
                continue
            not_cards = {str(raw.get("id") or "")}  # the automation's own id and its trigger ids
            for trg in raw.get("triggers") or raw.get("trigger") or []:
                if isinstance(trg, dict) and trg.get("id"):
                    not_cards.add(str(trg["id"]))
            ids = []
            for m in CARD_ID_RE.findall(txt):
                if m not in ids and m not in not_cards:
                    ids.append(m)
            for cid, rec in self.external.items():  # ids seen at runtime (templated ids)
                if rec.get("automation") == st.entity_id and cid not in ids:
                    ids.append(cid)
            out.append({
                "entity_id": st.entity_id,
                "name": st.attributes.get("friendly_name") or st.entity_id,
                "on": st.state == "on",
                "last_triggered": str(st.attributes.get("last_triggered") or "")[:16].replace("T", " "),
                "ids": ids,
            })
        return sorted(out, key=lambda a: a["name"].lower())

    def _automation_of(self, event: Event) -> str | None:
        """The automation whose run made this service call (context parent chain)."""
        comp = self.hass.data.get("automation")
        if not comp or not hasattr(comp, "entities"):
            return None
        ctx = event.context
        ids = {ctx.id, ctx.parent_id}
        for ent in comp.entities:
            run_ctx = getattr(ent, "_context", None) or getattr(ent, "context", None)
            if run_ctx is not None and getattr(run_ctx, "id", None) in ids:
                return ent.entity_id
        return None

    async def async_show_external(self, cid: str, zone: str | None = None, duration: int | None = None) -> bool:
        """Show the last card an automation sent, now (a copy with its own id)."""
        rec = self.external.get(cid)
        if not rec or not rec.get("card"):
            return False
        card = {k: v for k, v in rec["card"].items() if k not in ("every", "show", "hold", "ttl", "force")}
        if card.get("p") == 0:  # an alarm is never asked for: show it as a normal card
            card.pop("s", None)
        card["id"] = f"x_{cid}"[:26] + "_abruf"
        z = zone or (card.get("z") if card.get("z") in ("f", "p", "l") else "f")
        await self.board.push_card(self.place(card, {"where": {}}, True, z, duration))
        return True

    def tile_from_external(self, cid: str) -> dict | None:
        """Starting point for a migration: a JSON tile with the automation's last card."""
        rec = self.external.get(cid)
        if not rec or not rec.get("card"):
            return None
        card = {k: v for k, v in rec["card"].items() if k != "id"}
        tile = new_tile(str(card.get("ti") or cid))
        tile["template"] = "json"
        tile["card"] = json.dumps(card, ensure_ascii=False, indent=1)
        tile["where"]["zone"] = card.get("z") if card.get("z") in ("f", "p", "l") else "p"
        tile["from_automation"] = cid
        return tile

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
        if t == "json":  # Profi: the whole card as JSON / template (see docs/cards.md)
            return self._json_card(tile, card_id or f"st_{tile['id']}")
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

    def _json_card(self, tile: dict, card_id: str) -> dict:
        """Template -> card dict. Empty, 'none' or a del -> {} (= no card now, tile inactive)."""
        txt = self.render(tile.get("card"))
        if not txt or txt.lower() in ("none", "null", "{}", "false", "[]"):
            return {}
        try:
            card = json.loads(txt)
        except ValueError:
            try:  # HA templates often render Python-style dicts
                import ast
                card = ast.literal_eval(txt)
            except (ValueError, SyntaxError):
                return {"id": card_id, "t": "msg", "ti": "JSON-Fehler", "sub": txt[:60]}
        if not isinstance(card, dict) or card.get("del"):
            return {}
        card = {k: v for k, v in card.items() if k != "id"}
        card["id"] = card_id
        card.setdefault("t", "msg")
        return card

    def place(self, card: dict, tile: dict, on_demand: bool = False, zone: str | None = None,
              duration: int | None = None) -> dict:
        where = tile.get("where", {})
        when = tile.get("when", {})
        z = zone or where.get("zone", "p")
        dur = int(duration or where.get("duration") or 20)
        if on_demand:
            for k in ("every", "show", "hold"):
                card.pop(k, None)
            if card.get("p") == 0:
                card.pop("s", None)
            if z == "f":
                card.update({"p": 1, "z": "f", "hold": max(3, min(30, dur)), "ttl": dur, "force": 1})
            else:
                # force: at night the board shows on-demand cards full screen for their time
                card.update({"p": 2 if z == "p" else 3, "z": z, "ttl": dur, "force": 1})
            return card
        if tile.get("template") == "json":  # the JSON decides; the tile settings only fill gaps
            card.setdefault("p", int(where.get("prio") or 2))
            if card["p"] != 0:
                card.setdefault("z", z)
            card["ttl"] = max(int(card.get("ttl") or 0), REFRESH_ACTIVE * 2)
            if int(when.get("every") or 0) > 0 and "every" not in card:
                card["every"] = int(when["every"])
                card["show"] = int(when.get("show") or 10)
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
    async def _image_for(self, tile: dict, max_age: float = 0) -> bool:
        """Fetch the tile's picture (camera, image entity, any entity_picture or URL), shrink it to a
        small JPEG and let the board download it from a short-lived signed URL. False if no picture."""
        src = (tile.get("image") or "").strip()
        if not src:
            return False
        key = f"st_{tile['id']}"[:24]
        now = asyncio.get_running_loop().time()
        cached = self._img_sent.get(key)
        if max_age and cached and cached[0] == src and now - cached[1] < max_age:
            return True
        raw = await self._fetch_picture(src)
        if not raw:
            return False
        try:
            jpg = await self.hass.async_add_executor_job(_to_board_jpeg, raw)
        except Exception as err:  # noqa: BLE001 - broken or unsupported picture
            _LOGGER.warning("Perron Studio: Bild von %s nicht lesbar (%s)", src, err)
            return False
        self.images[key] = jpg
        try:
            base = get_url(self.hass, allow_external=False, prefer_external=False)
        except NoURLAvailableError:
            _LOGGER.warning("Perron Studio: keine interne HA-URL konfiguriert, Bilder gehen nicht")
            return False
        path = async_sign_path(self.hass, f"/api/perron_studio/img/{key}.jpg", timedelta(minutes=5))
        ok = await self.board.push_image_url(key, base + path)
        if ok:
            self._img_sent[key] = (src, now)
        return ok

    async def _fetch_picture(self, src: str) -> bytes | None:
        if ENTITY_RE.match(src):
            if src.startswith("camera."):
                from homeassistant.components.camera import async_get_image
                try:
                    return (await async_get_image(self.hass, src, timeout=10)).content
                except Exception as err:  # noqa: BLE001 - camera offline
                    _LOGGER.debug("Perron Studio: Kamera %s: %s", src, err)
                    return None
            st = self.hass.states.get(src)
            pic = st.attributes.get("entity_picture") if st else None
            if not pic:
                return None
            if pic.startswith("/"):
                try:
                    pic = get_url(self.hass, allow_external=False, prefer_external=False) + pic
                except NoURLAvailableError:
                    return None
            src = pic
        if not src.startswith(("http://", "https://")):
            return None
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(src, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return await resp.read() if resp.status == 200 else None
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Perron Studio: Bild %s: %s", src, err)
            return None

    async def async_push_state(self, tile: dict, force: bool = False) -> None:
        card = self.place(self.build_card(tile), tile)
        h = hashlib.sha1(json.dumps(card, sort_keys=True).encode()).hexdigest()
        now = asyncio.get_running_loop().time()
        since = now - self._last_push.get(tile["id"], 0)
        if not force and self._last_hash.get(tile["id"]) == h and since < REFRESH_ACTIVE:
            return
        # at most one push per min_interval (fast sensors such as PV power): catch up later
        min_iv = max(2, int(tile.get("when", {}).get("min_interval") or 10))
        if not force and since < min_iv:
            if tile["id"] not in self._later:
                def _again(tid: str = tile["id"]) -> None:
                    self._later.pop(tid, None)
                    t = next((x for x in self.tiles if x["id"] == tid), None)
                    if t:
                        self.hass.async_create_task(self.async_evaluate(t))
                self._later[tile["id"]] = self.hass.loop.call_later(min_iv - since, _again)
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
        card = self.build_card(tile, f"st_{tile['id']}_abruf")
        if not card:
            return
        await self.board.push_card(self.place(card, tile, True, zone, duration))

    async def async_hide(self, tile: dict) -> None:
        await self.board.delete_card(f"st_{tile['id']}_abruf")
        await self.board.delete_card(f"st_{tile['id']}")
        self._active[tile["id"]] = False

    async def async_evaluate(self, tile: dict, force: bool = False) -> None:
        active = self.is_active(tile)
        if active and tile.get("template") == "json" and not self._json_card(tile, "x"):
            active = False  # the template says: nothing to show right now
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
