"""Constants for Perron Studio."""
from __future__ import annotations

DOMAIN = "perron_studio"

CONF_ESPHOME_ENTRY = "esphome_entry_id"
CONF_DEVICE = "device_name"   # ESPHome device name, e.g. "perron" -> services esphome.perron_*
CONF_HOST = "host"
CONF_TOKEN = "token"          # secret for the board's /perron/* HTTP endpoints

STORAGE_KEY = f"{DOMAIN}.tiles"
STORAGE_VERSION = 1

PANEL_URL = "perron-studio"
PANEL_JS = "/perron_studio_static/perron-studio-panel.js"

LIVE_INTERVAL = 2.0           # seconds between live mirror refreshes
REFRESH_ACTIVE = 600          # re-push active state tiles every 10 min (their ttl is longer)

TEMPLATES = ["hero", "prog", "list", "msg", "kpi", "ring", "img", "agenda", "cv", "json"]
ZONES = {"f": "Vollbild", "p": "Kachel rechts", "l": "Infozeile"}
ACCENTS = ["y", "g", "b", "v", "w"]
ICONS = [
    "sun", "battery", "bolt", "plug", "car", "washer", "bell", "door", "window", "fridge", "snow",
    "home", "cal", "clock", "cake", "school", "pin", "tram", "bus", "train", "euro", "info", "warn",
    "person", "smoke", "walk", "plane",
]
