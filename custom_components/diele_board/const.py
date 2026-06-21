"""Constants for the Diele Departure Board integration."""
from __future__ import annotations

DOMAIN = "diele_board"

# ─── STIB (Belgian Mobility / Azure API Management) ───────────────────────────
# Auth = simple partner-key header (NOT OAuth2).
STIB_BASE = "https://api-management-opendata-production.azure-api.net"
STIB_WAITING_TIMES = "/api/datasets/stibmivb/rt/WaitingTimes/"
STIB_TRAVELLERS_INFO = "/api/datasets/stibmivb/rt/TravellersInformation/"  # disruptions
STIB_PARTNER_KEY_HEADER = "bmc-partner-key"

# ─── iRail (SNCB / NMBS) ──────────────────────────────────────────────────────
IRAIL_BASE = "https://api.irail.be"
IRAIL_USER_AGENT = "ha-diele-board/0.1 (github.com/Nosdave/ha-diele-board)"

# ─── Official STIB / SNCB line colors (bg, fg) ────────────────────────────────
LINE_COLORS: dict[str, tuple[str, str]] = {
    "92": ("#E2231A", "#ffffff"),
    "93": ("#E2231A", "#ffffff"),
    "37": ("#7B5EA7", "#ffffff"),
    "60": ("#F9A825", "#000000"),
    "54": ("#00ACC1", "#ffffff"),
    "8": ("#388E3C", "#ffffff"),
    "81": ("#795548", "#ffffff"),
    "21": ("#D81B60", "#ffffff"),
    "56": ("#1565C0", "#ffffff"),
    "63": ("#00897B", "#ffffff"),
    "64": ("#EF6C00", "#ffffff"),
    "12": ("#6A1B9A", "#ffffff"),
    "79": ("#2E7D32", "#ffffff"),
    "1": ("#1A237E", "#ffffff"),
    "5": ("#B71C1C", "#ffffff"),
    "SNCB": ("#003082", "#FFD700"),
    "IC": ("#0055A4", "#ffffff"),
    "P": ("#6B2D8B", "#ffffff"),
    "L": ("#009B48", "#ffffff"),
    "default": ("#555555", "#ffffff"),
}
# SNCB S-lines all share the SNCB colors
for _s in range(1, 20):
    LINE_COLORS.setdefault(f"S{_s}", ("#003082", "#FFD700"))


def line_color(line_id: str) -> tuple[str, str]:
    """Return (bg, fg) for a line id."""
    return LINE_COLORS.get(str(line_id), LINE_COLORS["default"])


# ─── Config-flow keys ─────────────────────────────────────────────────────────
CONF_PARTNER_KEY = "stib_partner_key"
CONF_TRAM_POINT = "tram_pointid"
CONF_TRAM_LINE = "tram_line"
CONF_BUS_POINT = "bus_pointid"
CONF_BUS_LINE = "bus_line"
CONF_TRAIN_STATION = "train_station"
CONF_TRAIN_PLATFORM = "train_platform"  # inbound filter; "" = no filter
CONF_WEATHER_ENTITY = "weather_entity"
CONF_PRESENCE_ENTITIES = "presence_entities"
CONF_COMMUTE_LABEL_1 = "commute_label_1"
CONF_COMMUTE_LABEL_2 = "commute_label_2"

# ─── Waze commute slots ───────────────────────────────────────────────────────
# Two destination helpers (text.* entities). Labels are user-configurable so no
# personal names ship in the repo; the user enters them at runtime (stored in HA).
COMMUTE_SLOTS = ("1", "2")
DEFAULT_COMMUTE_LABEL_1 = "Commute 1"
DEFAULT_COMMUTE_LABEL_2 = "Commute 2"
_LABEL_CONF = {"1": CONF_COMMUTE_LABEL_1, "2": CONF_COMMUTE_LABEL_2}
_LABEL_DEFAULT = {"1": DEFAULT_COMMUTE_LABEL_1, "2": DEFAULT_COMMUTE_LABEL_2}


def commute_label(cfg: dict, slot: str) -> str:
    """Resolve the user-facing label for a commute slot from config."""
    return cfg.get(_LABEL_CONF[slot]) or _LABEL_DEFAULT[slot]


# ─── Defaults ─────────────────────────────────────────────────────────────────
# Personal stops/station/entities/labels are NOT hardcoded — entered at setup
# (config flow) or, for the firmware, in the gitignored esphome/secrets.yaml.
DEFAULT_TRAM_POINT = ""
DEFAULT_TRAM_LINE = ""
DEFAULT_BUS_POINT = ""
DEFAULT_BUS_LINE = ""
DEFAULT_TRAIN_STATION = ""
DEFAULT_TRAIN_PLATFORM = ""  # e.g. "2" for inbound at a given station; "" = no filter
DEFAULT_WEATHER_ENTITY = ""
DEFAULT_PRESENCE_ENTITIES: list[str] = []

DEFAULT_SCAN_INTERVAL = 30  # seconds
PLATFORMS = ["sensor", "number", "switch", "text"]
