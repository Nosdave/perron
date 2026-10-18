"""Build the static data for the GPS setup helper (site/setup/).

  python tools/gen_site_data.py

Writes site/data/stops.json and site/data/stations.json from keyless official sources:
  STIB  official GTFS (stops, trips, stop_times, translations) -> lines + directions per platform
  SNCB  iRail /v1/stations
Line colours come from esphome/perron/perron_lines.h (generated from GTFS by gen_assets.py).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "site", "data")
GTFS_STIB = "https://api-management-discovery-production.azure-api.net/api/gtfs/feed/stibmivb/static"
UA = {"User-Agent": "ha-perron site generator (+https://github.com/Nosdave/perron)"}


def get_json(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                time.sleep(40)
                continue
            raise


def gtfs_files(src):
    """src: directory with extracted GTFS or None -> download official STIB GTFS (keyless)."""
    import csv
    import io
    import zipfile
    if src:
        op = lambda n: open(os.path.join(src, n), encoding="utf-8-sig", newline="")
    else:
        req = urllib.request.Request(GTFS_STIB, headers=UA)
        with urllib.request.urlopen(req, timeout=300) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        op = lambda n: io.TextIOWrapper(z.open(n), "utf-8-sig", newline="")
    return lambda n: csv.DictReader(op(n))


def line_colors():
    p = os.path.join(ROOT, "esphome", "perron", "perron_lines.h")
    out = {}
    for m in re.finditer(r'\{"([^"]+)", 0x([0-9A-F]{6}), (true|false), (\d)\}', open(p, encoding="utf-8").read()):
        out[m.group(1)] = {"c": "#" + m.group(2), "dark": m.group(3) == "true", "k": int(m.group(4))}
    return out


def title(s: str) -> str:
    """'GARE DU MIDI' -> 'Gare Du Midi', 'PORTE DE HAL' -> 'Porte De Hal'."""
    return re.sub(r"(^|[ \-/(])(\w)", lambda m: m.group(1) + m.group(2).upper(), s.lower())


def main():
    import sys
    os.makedirs(OUT, exist_ok=True)
    src = sys.argv[sys.argv.index("--gtfs-dir") + 1] if "--gtfs-dir" in sys.argv else None
    rd = gtfs_files(src)
    routes = {r["route_id"]: r["route_short_name"] for r in rd("routes.txt")}
    trips = {t["trip_id"]: (routes.get(t["route_id"], "?"), title(t.get("trip_headsign", "")))
             for t in rd("trips.txt")}
    serve: dict[str, set] = {}
    for st in rd("stop_times.txt"):
        tr = trips.get(st["trip_id"])
        if tr:
            serve.setdefault(st["stop_id"], set()).add(tr)
    nl = {}
    for t in rd("translations.txt"):
        if t.get("table_name") == "stops" and t.get("field_name") == "stop_name" and t.get("language") == "nl":
            nl[t.get("field_value", "")] = t.get("translation", "")
    fr_names = {}
    for t in rd("translations.txt"):
        if t.get("table_name") == "stops" and t.get("field_name") == "stop_name" and t.get("language") == "fr":
            fr_names[t.get("field_value", "")] = t.get("translation", "")
    stops = []
    for s in rd("stops.txt"):
        sid = s["stop_id"]
        if sid not in serve or not s.get("stop_lat"):
            continue
        raw = s["stop_name"]
        lines = sorted(serve[sid], key=lambda x: (len(x[0]), x[0], x[1]))
        stops.append({
            "id": sid,
            "fr": fr_names.get(raw) or title(raw), "nl": nl.get(raw) or title(raw),
            "lat": round(float(s["stop_lat"]), 5), "lon": round(float(s["stop_lon"]), 5),
            "l": [[ln, dest] for ln, dest in lines],  # line + direction (headsign) at this platform
        })
    colors = line_colors()
    with open(os.path.join(OUT, "stops.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": time.strftime("%Y-%m-%d"), "colors": colors, "stops": stops}, f,
                  ensure_ascii=False, separators=(",", ":"))
    st = get_json("https://api.irail.be/v1/stations/?format=json&lang=en")
    # "name" is bilingual in Brussels ("Sint-Job / Saint-Job") -> searchable in FR and NL
    stations = [{"id": x["id"], "name": x.get("name") or x.get("standardname"),
                 "lat": round(float(x["locationY"]), 5), "lon": round(float(x["locationX"]), 5)}
                for x in st["station"] if x["id"].startswith("BE.NMBS.0088")]
    with open(os.path.join(OUT, "stations.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": time.strftime("%Y-%m-%d"), "stations": stations}, f, ensure_ascii=False,
                  separators=(",", ":"))
    print(f"stops: {len(stops)}  stations: {len(stations)}")


if __name__ == "__main__":
    main()
