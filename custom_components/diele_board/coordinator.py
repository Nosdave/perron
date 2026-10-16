"""Data coordinator: STIB + iRail + disruptions + Waze → composed scene dict.

The ESP is the PRIMARY transit source (standalone); this builds the HA-side
fallback + folds in weather/Waze/presence/mode. Schema: ../../docs/02-architecture.md
STIB/iRail verified against the live API 2026-06-16.
"""
from __future__ import annotations

from collections.abc import Awaitable
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import homeassistant.util.dt as dt_util
from pywaze import route_calculator

from .api import IRailClient, StibClient
from .const import (
    COMMUTE_SLOTS,
    CONF_BUS_LINE,
    CONF_BUS_POINT,
    CONF_PARTNER_KEY,
    CONF_PRESENCE_ENTITIES,
    CONF_TRAIN_PLATFORM,
    CONF_TRAIN_STATION,
    CONF_TRAM_LINE,
    CONF_TRAM_POINT,
    CONF_WEATHER_ENTITY,
    DEFAULT_BUS_LINE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TRAIN_PLATFORM,
    DEFAULT_TRAM_LINE,
    DOMAIN,
    commute_label,
    line_color,
)

_LOGGER = logging.getLogger(__name__)
_UNAVAIL = ("unknown", "unavailable", None, "")
_PRESENT = ("on", "home", "true", "True", "detected")
# Waze allows ~100 requests / 2 h per public IP, shared with HA Core's own
# waze_travel_time entries. One refresh = one routing request (destination
# coords are cached), so 2 slots x 15 min = 16 requests / 2 h.
_WAZE_TTL = 900  # seconds — Waze is recomputed at most this often (on success)
# On failure, back off instead of retrying every scan: 5 / 15 / 30 / 60 min.
_WAZE_FAIL_BACKOFF = (300, 900, 1800, 3600)


def _mins_from_iso(iso: str, now) -> int | None:
    dt = dt_util.parse_datetime(iso)
    if dt is None:
        return None
    return max(0, round((dt - now).total_seconds() / 60))


def _mins_from_unix(unix: Any) -> int | None:
    try:
        dt = dt_util.utc_from_timestamp(int(unix))
    except (ValueError, TypeError):
        return None
    return max(0, round((dt - dt_util.utcnow()).total_seconds() / 60))


class DieleBoardCoordinator(DataUpdateCoordinator):
    """Fetch all sources and build the scene payload."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.entry = entry
        self._cfg = {**entry.data, **entry.options}
        # Waze destinations are owned by the text.* helper entities (set at runtime).
        self.destinations: dict[str, str] = {slot: "" for slot in COMMUTE_SLOTS}
        self._waze_cache: dict[str, tuple[Any, str, int | None]] = {}
        # slot -> (last_fail_ts, consecutive_failures) for negative caching / backoff.
        self._waze_fail: dict[str, tuple[Any, int]] = {}
        # slot -> (destination text, "lat,lon") so geocoding runs once per destination.
        self._waze_coords: dict[str, tuple[str, str]] = {}
        self._manual_alert: dict[str, str] | None = None

    def set_destination(self, slot: str, value: str) -> None:
        """Called by the text.* helper entities when their value changes."""
        if self.destinations.get(slot) != value:
            # New target: drop any failure backoff so it is tried again at once.
            self._waze_fail.pop(slot, None)
        self.destinations[slot] = value

    def label_for(self, slot: str) -> str:
        return commute_label(self._cfg, slot)

    def set_manual_alert(self, text: str, level: str = "info") -> None:
        """Service-driven alert; empty text clears it."""
        self._manual_alert = {"text": text, "level": level} if text else None

    async def _safe(self, coro: Awaitable, label: str):
        try:
            return await coro
        except Exception as err:  # noqa: BLE001 - one bad source must not kill the board
            _LOGGER.warning("diele_board: %s fetch failed: %s", label, err)
            return None

    async def _async_update_data(self) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        stib = StibClient(session, self._cfg[CONF_PARTNER_KEY])
        irail = IRailClient(session)
        now = dt_util.now()

        tram = await self._safe(stib.waiting_times(self._cfg[CONF_TRAM_POINT]), "tram")
        bus = await self._safe(stib.waiting_times(self._cfg[CONF_BUS_POINT]), "bus")
        train = await self._safe(irail.liveboard(self._cfg[CONF_TRAIN_STATION]), "train")
        disruptions = await self._safe(stib.disruptions(), "disruptions") or []

        tram_line = self._cfg.get(CONF_TRAM_LINE, DEFAULT_TRAM_LINE)
        bus_line = self._cfg.get(CONF_BUS_LINE, DEFAULT_BUS_LINE)

        return {
            "mode": self._mode(now),
            "present": self._presence(),
            "commute": await self._commutes(now),
            "weather": await self._weather(),
            "alert": self._manual_alert or self._pick_alert(disruptions, {tram_line, bus_line}),
            "transit_fallback": {
                "tram": self._format_stib(tram, tram_line, now),
                "bus": self._format_stib(bus, bus_line, now),
                "train": self._format_train(train),  # inbound-only (platform filter)
            },
        }

    # ── formatting (defensive: a shape drift degrades only its zone) ───────────
    def _format_stib(self, recs, line, now) -> list[dict[str, Any]]:
        out = []
        for r in recs or []:
            eta = r.get("eta")
            rline = str(r.get("line", ""))
            if not eta or (line and rline != str(line)):
                continue
            mins = _mins_from_iso(eta, now)
            if mins is None:
                continue
            bg, fg = line_color(rline)
            out.append({"line": rline, "dest": r.get("dest", "?"), "min": mins, "bg": bg, "fg": fg})
        out.sort(key=lambda d: d["min"])
        return out[:3]

    def _format_train(self, recs) -> list[dict[str, Any]]:
        platform = str(self._cfg.get(CONF_TRAIN_PLATFORM, DEFAULT_TRAIN_PLATFORM) or "")
        out = []
        for d in recs or []:
            if platform and str(d.get("platform") or "") != platform:
                continue  # keep only inbound (stadteinwärts) departures
            mins = _mins_from_unix(d.get("eta_unix"))
            if mins is None:
                continue
            bg, fg = line_color(d.get("line", ""))
            out.append({
                "line": d.get("line", "SNCB"), "dest": d.get("dest", "?"), "min": mins,
                "delay": d.get("delay", 0), "platform": d.get("platform"), "bg": bg, "fg": fg,
            })
        out.sort(key=lambda d: d["min"])
        return out[:3]

    def _pick_alert(self, disruptions, my_lines) -> dict[str, Any]:
        wanted = {str(x) for x in my_lines}
        cand = [d for d in disruptions if set(d.get("lines", [])) & wanted]
        if not cand:
            return {"text": "", "level": "info"}
        cand.sort(key=lambda d: d.get("priority", 9))
        top = cand[0]
        text = top["text"].get("en") or top["text"].get("fr") or top["text"].get("nl") or ""
        prio = top.get("priority", 9)
        level = "crit" if prio <= 1 else "warn" if prio <= 3 else "info"
        return {"text": text, "level": level, "lines": top.get("lines", [])}

    # ── HA state folding ──────────────────────────────────────────────────────
    def _mode(self, now) -> str:
        h = now.hour
        return "morning" if 6 <= h < 10 else "day" if 10 <= h < 17 else "evening" if 17 <= h < 22 else "night"

    def _presence(self) -> bool:
        ents = self._cfg.get(CONF_PRESENCE_ENTITIES) or []
        if not ents:
            return True
        return any(
            (st := self.hass.states.get(e)) and st.state in _PRESENT for e in ents
        )

    async def _weather(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        we = self._cfg.get(CONF_WEATHER_ENTITY)
        if not we:
            return out
        if st := self.hass.states.get(we):
            out["icon"] = st.state
            if (t := st.attributes.get("temperature")) is not None:
                out["now"] = t
        # today's min/max from the weather entity's own daily forecast
        try:
            resp = await self.hass.services.async_call(
                "weather", "get_forecasts",
                {"entity_id": we, "type": "daily"},
                blocking=True, return_response=True,
            )
            forecast = ((resp or {}).get(we) or {}).get("forecast") or []
            if forecast:
                today = forecast[0]
                if (lo := today.get("templow")) is not None:
                    out["min"] = lo
                if (hi := today.get("temperature")) is not None:
                    out["max"] = hi
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("diele_board: forecast unavailable: %s", err)
        return out

    async def _commutes(self, now) -> list[dict[str, Any]]:
        """Travel time per destination helper, via pywaze (cached ~15 min)."""
        origin = f"{self.hass.config.latitude},{self.hass.config.longitude}"
        out = []
        for slot, dest in self.destinations.items():
            if not dest:
                continue
            mins = await self._waze_minutes(origin, dest, slot, now)
            if mins is not None:
                out.append({"label": self.label_for(slot), "min": mins})
        return out

    async def _waze_minutes(self, origin: str, dest: str, slot: str, now) -> int | None:
        ts, cached_dest, cached = self._waze_cache.get(slot, (None, None, None))
        if cached is not None and cached_dest == dest and ts and (now - ts).total_seconds() < _WAZE_TTL:
            return cached
        # Only fall back to a cached value if it belongs to the SAME destination.
        fallback = cached if cached_dest == dest else None
        # Negative caching: after a failure, don't hammer Waze every scan.
        fail_ts, fails = self._waze_fail.get(slot, (None, 0))
        if fail_ts is not None and (now - fail_ts).total_seconds() < _WAZE_FAIL_BACKOFF[
            min(fails, len(_WAZE_FAIL_BACKOFF)) - 1
        ]:
            return fallback
        try:
            # HA's shared httpx client: no per-call client (blocking cert load) and
            # never closed by us, hence no ``async with``.
            client = route_calculator.WazeRouteCalculator(client=get_async_client(self.hass))
            target = await self._waze_target(client, origin, dest, slot)
            routes = await client.calc_routes(origin, target)
            if routes:
                mins = round(routes[0].duration)
                self._waze_cache[slot] = (now, dest, mins)
                if fails:
                    _LOGGER.info(
                        "diele_board: waze %s recovered after %d failure(s)", slot, fails
                    )
                self._waze_fail.pop(slot, None)
                return mins
        except Exception as err:  # noqa: BLE001
            # Log only the first failure at WARNING; the rest at DEBUG to avoid log spam.
            log = _LOGGER.warning if fails == 0 else _LOGGER.debug
            log("diele_board: waze %s failed (attempt %d): %s", slot, fails + 1, err)
            if "429" in str(err) or "too many" in str(err).lower():
                # Rate-limited: jump straight to the longest backoff.
                fails = max(fails, len(_WAZE_FAIL_BACKOFF) - 1)
        self._waze_fail[slot] = (now, fails + 1)
        return fallback

    async def _waze_target(self, client, origin: str, dest: str, slot: str) -> str:
        """Resolve a destination to "lat,lon" once and reuse it (saves a Waze call)."""
        cached = self._waze_coords.get(slot)
        if cached and cached[0] == dest:
            return cached[1]
        if client.already_coords(dest):
            return dest
        lat, lon = (float(v) for v in origin.split(","))
        coords = await client.address_to_coords(dest, base_coords={"lat": lat, "lon": lon})
        target = f"{coords['lat']},{coords['lon']}"
        self._waze_coords[slot] = (dest, target)
        return target
