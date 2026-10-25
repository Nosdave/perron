"""Tests for Perron Studio (pytest-homeassistant-custom-component).

Run:  pytest tests/perron_studio
The ESPHome actions of the board are replaced by recording services; the board's HTTP endpoints
by aioclient_mock.
"""
from __future__ import annotations

import io
import json

import pytest
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component

DOMAIN = "perron_studio"
HOST = "192.0.2.10"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _bmp() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (192, 64), (255, 160, 0)).save(buf, "BMP")
    return buf.getvalue()


@pytest.fixture
async def board_calls(hass: HomeAssistant):
    calls: list[tuple[str, dict]] = []

    async def rec(call: ServiceCall) -> None:
        calls.append((call.service, dict(call.data)))

    for action in ("perron_push_json", "perron_set_studio_token", "perron_push_image_url", "perron_show_commute"):
        hass.services.async_register("esphome", action, rec)
    return calls


@pytest.fixture
async def esphome_entry(hass: HomeAssistant):
    e = MockConfigEntry(domain="esphome", title="Perron", data={"host": HOST, "device_name": "perron"})
    e.add_to_hass(hass)
    return e


async def _setup(hass, esphome_entry):
    await async_setup_component(hass, "http", {})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"esphome_entry_id": esphome_entry.entry_id})
    assert result["type"] == "create_entry", result
    await hass.async_block_till_done()
    return result["result"]


async def test_setup_sends_token(hass, esphome_entry, board_calls):
    entry = await _setup(hass, esphome_entry)
    tok = [d for s, d in board_calls if s == "perron_set_studio_token"]
    assert tok and tok[0]["token"] == entry.data["token"] and len(entry.data["token"]) >= 24
    assert hass.states.get("camera.perron_studio_live") is not None


async def test_tile_always_pushes_card(hass, esphome_entry, board_calls, hass_admin_user):
    await _setup(hass, esphome_entry)
    hass.states.async_set("sensor.pv", "3412")
    engine = next(v for k, v in hass.data[DOMAIN].items() if not k.startswith("_"))["engine"]
    tile = await engine.async_upsert({
        "id": "tpv", "name": "Energie", "template": "kpi", "title": "Energie", "accent": "y",
        "cells": [{"label": "PV", "value": "{{ (states('sensor.pv')|float/1000)|round(1) }}", "unit": "kW", "icon": "sun"}],
        "when": {"mode": "always"}, "where": {"zone": "p"},
    })
    await hass.async_block_till_done()
    pushes = [json.loads(d["card"]) for s, d in board_calls if s == "perron_push_json"]
    card = pushes[-1]
    assert card["id"] == "st_tpv" and card["t"] == "kpi" and card["z"] == "p"
    assert card["kpi"][0][:3] == ["PV", "3.4", "kW"] and card["kpi"][0][6] == "sun"

    # content change -> re-push (throttled to min_interval, force skips the wait)
    hass.states.async_set("sensor.pv", "5000")
    await engine.async_evaluate(tile)
    pushes = [json.loads(d["card"]) for s, d in board_calls if s == "perron_push_json"]
    assert pushes[-1]["kpi"][0][1] == "3.4"  # too soon
    await engine.async_evaluate(tile, force=True)
    pushes = [json.loads(d["card"]) for s, d in board_calls if s == "perron_push_json"]
    assert pushes[-1]["kpi"][0][1] == "5.0"


async def test_show_service_full_screen(hass, esphome_entry, board_calls):
    await _setup(hass, esphome_entry)
    engine = next(v for k, v in hass.data[DOMAIN].items() if not k.startswith("_"))["engine"]
    await engine.async_upsert({"id": "tmsg", "name": "Müll", "template": "msg", "title": "Müll morgen", "text": "Gelber Sack"})
    await hass.services.async_call(DOMAIN, "show", {"tile": "müll", "zone": "vollbild", "duration": 15}, blocking=True)
    card = json.loads([d for s, d in board_calls if s == "perron_push_json"][-1]["card"])
    assert card == {**card, "id": "st_tmsg_abruf", "p": 1, "z": "f", "hold": 15, "ttl": 15, "force": 1}
    assert card["ti"] == "Müll morgen"


async def test_schedule_window(hass, esphome_entry, board_calls):
    from custom_components.perron_studio.engine import _in_window
    from datetime import datetime
    mon = datetime(2026, 10, 26, 7, 45)
    assert _in_window({"days": "Mo-Fr", "from": "06:30", "to": "09:00"}, mon)
    assert not _in_window({"days": "Sa,So", "from": "06:30", "to": "09:00"}, mon)
    assert _in_window({"days": "Fr-Mo", "from": "", "to": ""}, mon)


async def test_preview_and_live_views(hass, esphome_entry, board_calls, aioclient_mock, hass_client):
    entry = await _setup(hass, esphome_entry)
    aioclient_mock.post(f"http://{HOST}/perron/preview", content=_bmp())
    aioclient_mock.get(f"http://{HOST}/perron/screen.bmp", content=_bmp())
    client = await hass_client()
    r = await client.post("/api/perron_studio/preview", json={"tile": {"template": "hero", "title": "Büro", "value": "23"}, "zone": "p"})
    assert r.status == 200 and r.headers["Content-Type"] == "image/png"
    sent = aioclient_mock.mock_calls[-1]
    assert sent[3]["X-Perron-Token"] == entry.data["token"]
    r = await client.get("/api/perron_studio/live")
    assert r.status == 200
    r = await client.post("/api/perron_studio/tiles", json={"new": True, "name": "X"})
    t = await r.json()
    assert t["name"] == "X" and t["id"].startswith("t")
    r = await client.get("/api/perron_studio/tiles")
    assert len(await r.json()) == 1


async def test_external_cards_registry_show_import(hass, esphome_entry, board_calls):
    await _setup(hass, esphome_entry)
    engine = next(v for k, v in hass.data[DOMAIN].items() if not k.startswith("_"))["engine"]
    # an automation sends a card
    await hass.services.async_call("esphome", "perron_push_json", {"card": json.dumps(
        {"id": "pv", "t": "kpi", "ti": "Energie", "p": 2, "z": "f", "every": 900, "show": 10, "ttl": 3600,
         "kpi": [["PV", "3.1", "kW", "y", -1, "", "sun"]]})}, blocking=True)
    await hass.async_block_till_done()
    assert engine.external["pv"]["card"]["ti"] == "Energie" and not engine.external["pv"]["deleted"]
    # show it on demand by its id through the normal service
    await hass.services.async_call(DOMAIN, "show", {"tile": "pv", "zone": "f", "duration": 12}, blocking=True)
    card = json.loads([d for s, d in board_calls if s == "perron_push_json"][-1]["card"])
    assert card["id"] == "x_pv_abruf" and card["force"] == 1 and card["z"] == "f" and "every" not in card
    assert "x_pv_abruf" not in engine.external  # Studio's own push is not recorded
    # take over as a JSON tile
    tile = engine.tile_from_external("pv")
    assert tile["template"] == "json" and json.loads(tile["card"])["ti"] == "Energie"
    # the automation deletes it
    await hass.services.async_call("esphome", "perron_push_json", {"card": '{"id":"pv","del":1}'}, blocking=True)
    assert engine.external["pv"]["deleted"] and engine.external["pv"]["card"]["ti"] == "Energie"


async def test_json_tile_template_and_empty(hass, esphome_entry, board_calls):
    await _setup(hass, esphome_entry)
    engine = next(v for k, v in hass.data[DOMAIN].items() if not k.startswith("_"))["engine"]
    hass.states.async_set("sensor.wm", "in_use")
    tpl = ("{% if is_state('sensor.wm','in_use') %}"
           '{"t":"prog","ti":"Waschen","val":"42\'","pct":60,"p":2}'
           "{% endif %}")
    tile = await engine.async_upsert({"id": "twm", "name": "Wäsche", "template": "json", "card": tpl,
                                      "when": {"mode": "always"}, "where": {"zone": "p"}})
    await hass.async_block_till_done()
    card = json.loads([d for s, d in board_calls if s == "perron_push_json"][-1]["card"])
    assert card["id"] == "st_twm" and card["t"] == "prog" and card["z"] == "p" and card["pct"] == 60
    hass.states.async_set("sensor.wm", "off")
    await engine.async_evaluate(tile)
    card = json.loads([d for s, d in board_calls if s == "perron_push_json"][-1]["card"])
    assert card == {"id": "st_twm", "del": 1}


async def test_alarm_json_tile_keeps_p0(hass, esphome_entry, board_calls):
    await _setup(hass, esphome_entry)
    engine = next(v for k, v in hass.data[DOMAIN].items() if not k.startswith("_"))["engine"]
    hass.states.async_set("binary_sensor.smoke", "on")
    await engine.async_upsert({"id": "tal", "name": "Rauch", "template": "json", "when": {"mode": "always"},
                               "card": "{% if is_state('binary_sensor.smoke','on') %}{'t':'msg','p':0,'s':'x','ti':'Rauch'}{% endif %}"})
    await hass.async_block_till_done()
    card = json.loads([d for s, d in board_calls if s == "perron_push_json"][-1]["card"])
    assert card["p"] == 0 and card["s"] == "x" and "z" not in card


async def test_image_signed_url_and_view(hass, esphome_entry, board_calls, hass_client_no_auth):
    await _setup(hass, esphome_entry)
    await hass.config.async_update(internal_url="http://192.0.2.1:8123")
    engine = next(v for k, v in hass.data[DOMAIN].items() if not k.startswith("_"))["engine"]

    async def fake_fetch(src):
        buf = io.BytesIO()
        Image.new("RGB", (640, 480), (10, 200, 30)).save(buf, "PNG")
        return buf.getvalue()

    engine._fetch_picture = fake_fetch
    ok = await engine._image_for({"id": "tcam", "image": "camera.door"})
    assert ok
    url = [d for s, d in board_calls if s == "perron_push_image_url"][-1]["url"]
    assert url.startswith("http://192.0.2.1:8123/api/perron_studio/img/st_tcam.jpg?authSig=")
    jpg = Image.open(io.BytesIO(engine.images["st_tcam"]))
    assert jpg.format == "JPEG" and max(jpg.size) == 192
    client = await hass_client_no_auth()  # the board has no HA login: only the signature
    r = await client.get(url.split("8123", 1)[1])
    assert r.status == 200 and r.headers["Content-Type"] == "image/jpeg"
    r = await client.get("/api/perron_studio/img/st_tcam.jpg")
    assert r.status == 401
