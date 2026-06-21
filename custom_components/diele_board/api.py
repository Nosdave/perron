"""Minimal async clients for STIB (Belgian Mobility) and iRail (SNCB).

Endpoints/shapes verified 2026-06-16 against the live API (see docs/05-stib-irail.md).
"""
from __future__ import annotations

import json
import re
from typing import Any

import aiohttp

try:  # package import (inside Home Assistant)
    from .const import (
        IRAIL_BASE,
        IRAIL_USER_AGENT,
        STIB_BASE,
        STIB_PARTNER_KEY_HEADER,
        STIB_TRAVELLERS_INFO,
        STIB_WAITING_TIMES,
    )
except ImportError:  # standalone import (scripts/smoke_test.py)
    from const import (  # type: ignore[no-redef]
        IRAIL_BASE,
        IRAIL_USER_AGENT,
        STIB_BASE,
        STIB_PARTNER_KEY_HEADER,
        STIB_TRAVELLERS_INFO,
        STIB_WAITING_TIMES,
    )

_TIMEOUT = aiohttp.ClientTimeout(total=15)
_VEHICLE_RE = re.compile(r"^([A-Z]+\d{0,2})\d{4}$")


class StibError(Exception):
    """STIB API error."""


class StibClient:
    """STIB real-time waiting times + traveller information (disruptions)."""

    def __init__(self, session: aiohttp.ClientSession, partner_key: str) -> None:
        self._session = session
        self._headers = {STIB_PARTNER_KEY_HEADER: partner_key, "Cache-Control": "no-cache"}

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            async with self._session.get(
                STIB_BASE + path, params=params, headers=self._headers, timeout=_TIMEOUT
            ) as resp:
                if resp.status != 200:
                    raise StibError(f"HTTP {resp.status} for {path}")
                return await resp.json()
        except aiohttp.ClientError as err:
            raise StibError(str(err)) from err

    async def waiting_times(self, pointid: str) -> list[dict[str, Any]]:
        """Return [{line, dest, eta(iso)}] for one stop point."""
        data = await self._get(STIB_WAITING_TIMES, {"where": f'pointid="{pointid}"', "limit": 20})
        out: list[dict[str, Any]] = []
        for rec in data.get("results", []):
            line = str(rec.get("lineid", ""))
            try:
                times = json.loads(rec.get("passingtimes") or "[]")
            except (ValueError, TypeError):
                continue
            for ti in times:
                eta = ti.get("expectedArrivalTime")
                dest = (ti.get("destination") or {})
                if eta:
                    out.append({"line": line, "dest": dest.get("fr") or dest.get("nl") or "?", "eta": eta})
        return out

    async def disruptions(self) -> list[dict[str, Any]]:
        """Return [{lines, points, priority, text{en,fr,nl}}] traveller-info messages."""
        data = await self._get(STIB_TRAVELLERS_INFO, {"limit": 100})
        out: list[dict[str, Any]] = []
        for rec in data.get("results", []):
            try:
                content = json.loads(rec.get("content") or "[]")
                lines = [str(x.get("id")) for x in json.loads(rec.get("lines") or "[]")]
                points = [str(x.get("id")) for x in json.loads(rec.get("points") or "[]")]
            except (ValueError, TypeError):
                continue
            text: dict[str, str] = {}
            for block in content:
                texts = block.get("text") or []
                if texts:
                    text = texts[0]
                    break
            out.append({"lines": lines, "points": points, "priority": rec.get("priority", 9), "text": text})
        return out


class IRailClient:
    """SNCB departures via the free iRail liveboard."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def liveboard(self, station: str, lang: str = "en", results: int = 6) -> list[dict[str, Any]]:
        """Return [{line, dest, eta_unix, delay(min), platform, canceled}]."""
        params: dict[str, Any] = {"format": "json", "lang": lang, "arrdep": "departures", "results": results}
        if station.startswith("BE."):
            params["id"] = station
        else:
            params["station"] = station
        try:
            async with self._session.get(
                f"{IRAIL_BASE}/liveboard/", params=params,
                headers={"User-Agent": IRAIL_USER_AGENT}, timeout=_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except aiohttp.ClientError:
            return []
        out: list[dict[str, Any]] = []
        for d in (data.get("departures") or {}).get("departure", []):
            veh = (d.get("vehicle") or "").replace("BE.NMBS.", "")
            match = _VEHICLE_RE.match(veh)
            if match:
                line = match.group(1)
            else:
                lead = re.match(r"^([A-Z]+)", veh)
                line = lead.group(1) if lead else "SNCB"
            try:
                delay_min = round(int(d.get("delay") or 0) / 60)
            except (ValueError, TypeError):
                delay_min = 0
            out.append({
                "line": line or "SNCB",
                "dest": d.get("station"),
                "eta_unix": d.get("time"),
                "delay": delay_min,
                "platform": d.get("platform"),
                "canceled": str(d.get("canceled")) in ("1", "True", "true"),
            })
        return out
