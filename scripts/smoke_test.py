"""Offline smoke test — run the STIB/iRail clients against the LIVE API (no HA).

Proves api.py parsing works end-to-end before installing the integration in HA.

Usage:
    python scripts/smoke_test.py
Reads your private config from esphome/secrets.yaml (gitignored): stib_partner_key,
stib_point_tram, stib_point_bus, irail_train_station. $STIB_PARTNER_KEY overrides the key.
Requires: aiohttp  (pip install aiohttp)
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
# import the integration's clients standalone (api.py falls back to `from const`)
sys.path.insert(0, str(ROOT / "custom_components" / "diele_board"))

import aiohttp  # noqa: E402
import api  # noqa: E402

_KEYS = ("stib_partner_key", "stib_point_tram", "stib_point_bus", "irail_train_station")


def _read_secrets() -> dict[str, str]:
    cfg: dict[str, str] = {}
    secrets = ROOT / "esphome" / "secrets.yaml"
    if secrets.exists():
        for raw in secrets.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            for k in _KEYS:
                if line.startswith(k + ":"):
                    v = line.split(":", 1)[1].strip()
                    if v[:1] in ('"', "'"):  # quoted → take up to closing quote
                        q = v[0]
                        v = v[1:v.index(q, 1)] if v.find(q, 1) != -1 else v[1:]
                    else:  # bare value → drop trailing inline comment
                        v = v.split("#", 1)[0].strip()
                    cfg[k] = v
    if env := os.environ.get("STIB_PARTNER_KEY"):
        cfg["stib_partner_key"] = env
    return cfg


async def main() -> None:
    cfg = _read_secrets()
    if not cfg.get("stib_partner_key"):
        sys.exit("No STIB key: set $STIB_PARTNER_KEY or esphome/secrets.yaml (stib_partner_key)")

    async with aiohttp.ClientSession() as session:
        stib = api.StibClient(session, cfg["stib_partner_key"])
        irail = api.IRailClient(session)

        if tram := cfg.get("stib_point_tram"):
            print(f"== Tram @ {tram} ==")
            for d in (await stib.waiting_times(tram))[:5]:
                print(f"   {d['line']:>3}  {d['dest']:<20} {d['eta']}")

        if bus := cfg.get("stib_point_bus"):
            print(f"== Bus @ {bus} ==")
            for d in (await stib.waiting_times(bus))[:6]:
                print(f"   {d['line']:>3}  {d['dest']:<20} {d['eta']}")

        if station := cfg.get("irail_train_station"):
            print(f"== Train @ {station} ==")
            for d in (await irail.liveboard(station))[:8]:
                print(f"   {d['line']:>4}  plat {d.get('platform')}  {d['dest']:<24} +{d['delay']}m")

        print("== Disruptions (first few) ==")
        for m in (await stib.disruptions())[:5]:
            txt = (m["text"].get("en") or m["text"].get("fr") or "")[:88]
            print(f"   prio {m['priority']} lines {m['lines']}: {txt}")


if __name__ == "__main__":
    asyncio.run(main())
