"""Tile -> ordinary Home Assistant automation.

Perron Studio is only the editor: every tile is saved as an automation in automations.yaml
(id ``perron_studio_<tile id>``), written the same way as Home Assistant's own automation editor
does it. The automation renders the card and sends it with ``esphome.<board>_push_json``; nothing
of Perron Studio is needed while it runs.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.util.file import write_utf8_file_atomic
from homeassistant.util.yaml import dump, load_yaml

_LOGGER = logging.getLogger(__name__)

ID_PREFIX = "perron_studio_"
SHOW_EVENT = "perron_studio_show"
REFRESH = "/10"          # time_pattern minutes: re-send state cards (board drops them after ttl)
STATE_TTL = 1800         # s: survives two missed refreshes
ENTITY_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
ENTITY_IN_TEXT_RE = re.compile(r"\b([a-z_]+\.[a-z0-9_]+)\b")
DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_DE = ["mo", "di", "mi", "do", "fr", "sa", "so"]
_LOCK = asyncio.Lock()  # Studio-internal; against other writers see _update()


def automation_id(tile: dict) -> str:
    return f"{ID_PREFIX}{tile['id']}"


def config_hash(cfg: dict) -> str:
    return hashlib.sha1(json.dumps(cfg, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ------------------------------------------------------------------ field -> template
def _field(v: Any) -> str:
    """A tile field as automation variable: entity id -> its state, template stays, text stays."""
    s = "" if v is None else str(v).strip()
    if ENTITY_RE.match(s) and "{" not in s:
        return "{{ states('%s') }}" % s
    return s


def _q(s: str) -> str:
    """Python/Jinja string literal."""
    return json.dumps(s, ensure_ascii=False)


def _days(spec: str) -> list[str]:
    spec = (spec or "").strip().lower()
    if not spec or spec in ("täglich", "taeglich", "alle"):
        return []
    out: list[str] = []
    for tok in spec.replace(" ", "").split(","):
        a, _, b = tok.partition("-")
        if a[:2] not in DAY_DE:
            continue
        i0 = DAY_DE.index(a[:2])
        i1 = DAY_DE.index(b[:2]) if b[:2] in DAY_DE else i0
        k = i0
        while True:
            if DAY_KEYS[k] not in out:
                out.append(DAY_KEYS[k])
            if k == i1:
                break
            k = (k + 1) % 7
    return out


def entities_in(tile: dict, hass: HomeAssistant | None = None) -> list[str]:
    found: list[str] = []

    def scan(v: Any) -> None:
        if isinstance(v, str):
            for m in ENTITY_IN_TEXT_RE.findall(v):
                if m.split(".")[0] in ("states", "state_attr", "is_state", "trigger", "this", "now"):
                    continue
                if hass is not None and hass.states.get(m) is None:
                    continue
                if m not in found:
                    found.append(m)
        elif isinstance(v, dict):
            for x in v.values():
                scan(x)
        elif isinstance(v, list):
            for x in v:
                scan(x)

    scan({k: v for k, v in tile.items() if k not in ("when", "where", "id", "name", "template", "icon",
                                                     "accent", "enabled")})
    scan((tile.get("when") or {}).get("condition", ""))
    return found


# ------------------------------------------------------------------ card expression
def _card_parts(tile: dict) -> tuple[dict[str, str], str]:
    """(variables, Jinja dict expression of the card body without placement)."""
    t = tile.get("template", "hero")
    v: dict[str, str] = {}
    keys: list[str] = [f"'t': {_q(t)}"]

    def sv(name: str, value: Any) -> str:
        v[f"v_{name}"] = _field(value)
        return f"(v_{name} | string)"

    keys.append(f"'ti': {sv('ti', tile.get('title'))}")
    if tile.get("icon"):
        keys.append(f"'ic': {_q(tile['icon'])}")
    if tile.get("accent") and tile["accent"] != "w":
        keys.append(f"'ac': {_q(tile['accent'])}")
    sub = f"([{sv('sub1', tile.get('sub1'))}, {sv('sub2', tile.get('sub2'))}] | select | join('|'))"
    if t in ("hero", "prog", "ring"):
        if t != "ring":
            keys.append(f"'val': {sv('val', tile.get('value'))}")
            keys.append(f"'u': {sv('u', tile.get('unit'))}")
        keys.append(f"'sub': {sub}")
        if t == "prog":
            v["v_pct"] = _field(tile.get("pct"))
            keys.append("'pct': ([[(v_pct | float(0)) | round(0) | int, 0] | max, 100] | min)")
    elif t == "msg":
        keys.append(f"'sub': {sv('text', tile.get('text'))}")
    elif t == "kpi":
        cells = []
        for i, c in enumerate((tile.get("cells") or [])[:3]):
            pct = "-1"
            if c.get("pct"):
                v[f"v_c{i}pct"] = _field(c.get("pct"))
                pct = f"((v_c{i}pct | float(-1)) | round(0) | int)"
            cells.append("[%s, %s, %s, %s, %s, %s, %s]" % (
                sv(f"c{i}label", c.get("label")), sv(f"c{i}value", c.get("value")), sv(f"c{i}unit", c.get("unit")),
                _q(c.get("color") or "w"), pct, sv(f"c{i}sub", c.get("sub")), _q(c.get("icon") or "")))
        keys.append(f"'kpi': [{', '.join(cells)}]")
    elif t in ("list", "agenda"):
        rows = []
        for i, r in enumerate((tile.get("rows") or [])[: (8 if t == "agenda" else 4)]):
            rows.append("[%s, %s, %s, %s]" % (_q(r.get("icon") or ""), sv(f"r{i}label", r.get("label")),
                                              sv(f"r{i}value", r.get("value")), _q(r.get("color") or "w")))
        keys.append(f"'rows': [{', '.join(rows)}]")
    elif t == "img":
        keys.append(f"'img': {_q(image_key(tile))}")
        keys.append(f"'ft': {sub}")
    elif t == "cv":
        v["v_el"] = _field(tile.get("elements") or "[]")
        keys.append("'el': (v_el if v_el is list else (v_el | from_json if v_el else []))")
    if t == "ring" and tile.get("image"):
        keys.append(f"'img': {_q(image_key(tile))}")
    return v, "{" + ", ".join(keys) + "}"


def image_key(tile: dict) -> str:
    return f"st_{tile['id']}"[:24]


def _image_url(hass: HomeAssistant, src: str) -> str | None:
    """URL the board downloads (needs no login: entity_picture carries its own token)."""
    src = (src or "").strip()
    if not src:
        return None
    if ENTITY_RE.match(src):
        try:
            base = get_url(hass, allow_external=False, prefer_external=False)
        except NoURLAvailableError:
            return None
        width = "&width=192" if src.startswith("camera.") else ""
        return "%s{{ state_attr('%s', 'entity_picture') }}%s" % (base, src, width)
    return src if src.startswith(("http://", "https://")) else None


# ------------------------------------------------------------------ the automation
def build_automation(hass: HomeAssistant, tile: dict, device: str) -> dict:
    when = tile.get("when") or {}
    where = tile.get("where") or {}
    mode = when.get("mode", "manual")
    tid = tile["id"]
    card_id = f"st_{tid}"
    zone = where.get("zone") if where.get("zone") in ("f", "p", "l") else "p"
    prio = max(1, min(3, int(where.get("prio") or 2)))
    dur = max(3, int(where.get("duration") or 20))
    every = int(when.get("every") or 0)
    show = int(when.get("show") or 10)
    mi = when.get("min_interval")
    min_iv = max(0, int(10 if mi in (None, "") else mi))
    push = f"esphome.{device}_push_json"
    is_json = tile.get("template") == "json"

    triggers: list[dict] = [{"trigger": "event", "event_type": SHOW_EVENT, "event_data": {"tile": tid}, "id": "show"}]
    for ev in when.get("events") or []:
        ent = (ev.get("entity") or "").strip()
        if ent:
            t = {"trigger": "state", "entity_id": ent, "id": "show"}
            if (ev.get("to") or "").strip():
                t["to"] = ev["to"].strip()
            triggers.append(t)
    if mode != "manual":
        ents = entities_in(tile, hass)
        if ents:
            triggers.append({"trigger": "state", "entity_id": ents, "id": "state"})
        triggers.append({"trigger": "time_pattern", "minutes": REFRESH, "id": "state"})
        triggers.append({"trigger": "homeassistant", "event": "start", "id": "state"})
        if mode == "schedule":
            for k in ("from", "to"):
                if when.get(k):
                    triggers.append({"trigger": "time", "at": f"{when[k]}:00"[:8], "id": "state"})

    # variables: tile fields, the card body, placement for state and on-demand
    if is_json:
        variables: dict[str, Any] = {"body": tile.get("card") or ""}
        body = "(body if body is mapping else {})"
    else:
        variables, expr = _card_parts(tile)
        variables["body"] = "{{ %s }}" % expr
        body = "body"
    variables["od_zone"] = ("{{ trigger.event.data.get('zone') if trigger.get('id') == 'show' and trigger.get('platform') == 'event' "
                            "and trigger.event.data.get('zone') in ['f', 'p', 'l'] else %s }}" % _q(zone))
    variables["od_dur"] = ("{{ (trigger.event.data.get('duration') | int(%d)) if trigger.get('id') == 'show' "
                           "and trigger.get('platform') == 'event' else %d }}" % (dur, dur))

    if mode == "condition":
        cond = "{{ %s }}" % _strip_braces(when.get("condition") or "false")
    elif mode == "schedule":
        days = _days(when.get("days"))
        f, t = when.get("from") or "", when.get("to") or ""
        parts = []
        if days:
            parts.append("now().strftime('%a') | lower in " + _q(days).replace('"', "'"))
        if f and t:
            fm, tm = _q(f), _q(t)
            parts.append(f"((now().strftime('%H:%M') >= {fm} and now().strftime('%H:%M') < {tm}) if {fm} <= {tm} "
                         f"else (now().strftime('%H:%M') >= {fm} or now().strftime('%H:%M') < {tm}))")
        cond = "{{ %s }}" % (" and ".join(parts) or "true")
    elif mode == "always":
        cond = "{{ true }}"
    else:
        cond = "{{ false }}"
    if is_json:
        cond = "{{ (%s) and (body is mapping) and not body.get('del') }}" % _strip_braces(cond)

    # placement
    state_extra = {"z": zone, "p": prio, "ttl": STATE_TTL}
    if every > 0:
        state_extra.update({"every": every, "show": show})
    if is_json:  # the JSON decides, the tile only fills gaps
        state_card = ("{{ dict(dict(%s, **%s), id=%s, ttl=[(%s.get('ttl') or 0) | int, %d] | max) | to_json }}"
                      % (_pyd({k: v for k, v in state_extra.items() if k != "ttl"}), body, _q(card_id), body, STATE_TTL))
    else:
        state_card = "{{ dict(%s, id=%s, **%s) | to_json }}" % (body, _q(card_id), _pyd(state_extra))
    od_card = ("{%% set c = dict(%s, id=%s) %%}"
               "{%% set c = dict(c, p=1, z='f', hold=[[od_dur, 3] | max, 30] | min, ttl=od_dur, force=1) "
               "if od_zone == 'f' else dict(c, p=(2 if od_zone == 'p' else 3), z=od_zone, ttl=od_dur, force=1) %%}"
               "{{ dict(c, every=0, show=0, s=('i' if %s.get('p') == 0 else c.get('s', 'i'))) | to_json }}"
               % (body, _q(card_id + "_abruf"), body))

    image_steps: list[dict] = []
    if tile.get("template") in ("img", "ring"):
        url = _image_url(hass, tile.get("image"))
        if url:
            image_steps = [{"action": f"esphome.{device}_push_image_url", "continue_on_error": True,
                            "data": {"key": image_key(tile), "url": url}}]

    send_state = image_steps + [{"action": push, "continue_on_error": True, "data": {"card": state_card}}]
    remove = [{"action": push, "continue_on_error": True, "data": {"card": json.dumps({"id": card_id, "del": 1})}}]
    on_demand_ok = "{{ (body is mapping) and (body | length > 0) and not body.get('del') }}" if is_json else "{{ true }}"

    actions = [
        {"variables": variables},
        {"choose": [
            # "show" event / entity trigger, or "Ausführen" in HA (no trigger id) = on demand
            {"conditions": [{"condition": "template", "value_template": "{{ trigger.get('id', 'show') == 'show' }}"},
                            {"condition": "template", "value_template": on_demand_ok}],
             "sequence": image_steps + [{"action": push, "continue_on_error": True, "data": {"card": od_card}}]},
            {"conditions": [{"condition": "template", "value_template": cond}], "sequence": send_state},
        ], "default": remove if mode != "manual" else []},
    ]
    if mode == "manual":  # manual tiles only answer "show": no removal needed
        actions[1]["default"] = []

    conditions = []
    if min_iv > 0 and mode != "manual":  # fast sensors: at most one state update per min_interval
        conditions.append({"condition": "template", "value_template": (
            "{{ trigger.get('id', 'show') == 'show' or trigger.get('platform') in ['time_pattern', 'time', 'homeassistant'] or "
            "this.attributes.last_triggered is none or "
            "(now() - this.attributes.last_triggered).total_seconds() >= %d }}" % min_iv)})

    return {
        "id": automation_id(tile),
        "alias": f"Perron Studio: {tile.get('name') or tid}",
        "description": "Erstellt mit Perron Studio. Bitte im Studio bearbeiten – dort gibt es die "
                       "Vorschau; Änderungen hier überschreibt das Studio beim nächsten Speichern.",
        "mode": "queued",
        "max": 5,
        "triggers": triggers,
        "conditions": conditions,
        "actions": actions,
    }


def _strip_braces(t: str) -> str:
    t = (t or "").strip()
    m = re.fullmatch(r"\{\{(.*)\}\}", t, re.S)
    return m.group(1).strip() if m else (t if t else "false")


def _pyd(d: dict) -> str:
    return "{" + ", ".join(f"{_q(k)}: {json.dumps(v)}" for k, v in d.items()) + "}"


# ------------------------------------------------------------------ automations.yaml
def _path(hass: HomeAssistant) -> str:
    return hass.config.path("automations.yaml")


def _read(path: str) -> list:
    if not os.path.isfile(path):
        return []
    data = load_yaml(path)
    return list(data or [])


def _fingerprint(path: str) -> tuple[float, int] | None:
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except FileNotFoundError:
        return None


def _update(path: str, change) -> bool:
    """Read-modify-write of automations.yaml in one go, compare-and-swap style.

    Home Assistant's automation editor keeps its write lock private (an attribute of its view), so
    it cannot be shared. Instead the file is read, changed and - only if nobody wrote it in the
    meantime (mtime/size unchanged) - written atomically; otherwise it is read again (3 tries).
    Returns False if nothing had to change.
    """
    for _ in range(3):
        before = _fingerprint(path)
        data = list(load_yaml(path) or []) if before else []
        new = change(data)
        if new is None:
            return False
        contents = dump(new)  # before touching the file: a dump error leaves it intact
        if _fingerprint(path) != before:
            continue  # someone (HA editor, API) wrote meanwhile: start over with their version
        if before:
            shutil.copy2(path, path + ".perron_studio.bak")  # previous version, one step back
        write_utf8_file_atomic(path, contents)
        return True
    raise HomeAssistantError("automations.yaml wird gerade anderweitig geändert – bitte nochmal speichern")


async def async_read(hass: HomeAssistant, auto_id: str) -> dict | None:
    data = await hass.async_add_executor_job(_read, _path(hass))
    return next((a for a in data if isinstance(a, dict) and a.get("id") == auto_id), None)


async def async_save(hass: HomeAssistant, cfg: dict, enabled: bool) -> None:
    """Validate, write (like HA's automation editor), reload, then switch on/off."""
    from homeassistant.components.automation.config import async_validate_config_item

    try:
        await async_validate_config_item(hass, cfg["id"], cfg)
    except Exception as err:  # noqa: BLE001 - vol.Invalid / HomeAssistantError
        raise HomeAssistantError(f"Automation ungültig: {err}") from err

    def change(data: list) -> list:
        for i, a in enumerate(data):
            if isinstance(a, dict) and a.get("id") == cfg["id"]:
                data[i] = cfg
                break
        else:
            data.append(cfg)
        return data

    async with _LOCK:
        await hass.async_add_executor_job(_update, _path(hass), change)
    # only this automation (like HA's editor): running ones (doorbell waits etc.) are not interrupted
    await hass.services.async_call("automation", "reload", {"id": cfg["id"]}, blocking=True)
    ent = er.async_get(hass).async_get_entity_id("automation", "automation", cfg["id"])
    if ent:
        await hass.services.async_call("automation", "turn_on" if enabled else "turn_off",
                                       {"entity_id": ent}, blocking=True)


async def async_remove(hass: HomeAssistant, auto_id: str) -> None:
    """Delete like HA's editor: drop it from the file, then remove its entity (no reload)."""

    def change(data: list) -> list | None:
        new = [a for a in data if not (isinstance(a, dict) and a.get("id") == auto_id)]
        return new if len(new) != len(data) else None

    async with _LOCK:
        await hass.async_add_executor_job(_update, _path(hass), change)
    reg = er.async_get(hass)
    ent = reg.async_get_entity_id("automation", "automation", auto_id)
    if ent:
        reg.async_remove(ent)
