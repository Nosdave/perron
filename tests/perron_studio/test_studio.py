"""Tests for Perron Studio (pytest-homeassistant-custom-component).

Run:  pytest tests/perron_studio
The ESPHome actions of the board are replaced by recording services; the board's HTTP endpoints
by aioclient_mock. Tiles are saved as real automations in a temporary automations.yaml, and it is
those automations (not the Studio) that send the cards.
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


@pytest.fixture(autouse=True)
async def config_dir(hass: HomeAssistant, tmp_path):
    """A config dir of our own: configuration.yaml includes automations.yaml like a normal install."""
    hass.config.config_dir = str(tmp_path)
    (tmp_path / "configuration.yaml").write_text("automation: !include automations.yaml\n", encoding="utf-8")
    (tmp_path / "automations.yaml").write_text("[]\n", encoding="utf-8")
    yield tmp_path


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
    assert await async_setup_component(hass, "automation", {})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"esphome_entry_id": esphome_entry.entry_id})
    assert result["type"] == "create_entry", result
    await hass.async_block_till_done()
    return result["result"]


def _engine(hass):
    return next(v for k, v in hass.data[DOMAIN].items() if not k.startswith("_"))["engine"]


def _pushes(board_calls):
    # HA hands over the rendered JSON wrapped; str() is what ESPHome's string field receives
    return [json.loads(str(d["card"])) for s, d in board_calls if s == "perron_push_json"]


async def test_setup_sends_token(hass, esphome_entry, board_calls):
    entry = await _setup(hass, esphome_entry)
    tok = [d for s, d in board_calls if s == "perron_set_studio_token"]
    assert tok and tok[0]["token"] == entry.data["token"] and len(entry.data["token"]) >= 24
    assert hass.states.get("camera.perron_studio_live") is not None


async def test_tile_is_saved_as_automation_that_sends_the_card(hass, esphome_entry, board_calls, config_dir):
    await _setup(hass, esphome_entry)
    hass.states.async_set("sensor.pv", "3412")
    engine = _engine(hass)
    await engine.async_upsert({
        "id": "tpv", "name": "Energie", "template": "kpi", "title": "Energie", "accent": "y",
        "cells": [{"label": "PV", "value": "{{ (states('sensor.pv')|float/1000)|round(1) }}", "unit": "kW", "icon": "sun"}],
        "when": {"mode": "always", "min_interval": 0}, "where": {"zone": "p"},
    })
    await hass.async_block_till_done()
    text = (config_dir / "automations.yaml").read_text(encoding="utf-8")
    assert "perron_studio_tpv" in text and "esphome.perron_push_json" in text
    st = engine.status(engine.get("tpv"))
    assert st["saved"] and st["on"] and not st["modified"] and st["automation"] == "automation.perron_studio_energie"

    # the AUTOMATION reacts to the sensor and sends the card
    board_calls.clear()
    hass.states.async_set("sensor.pv", "5000")
    await hass.async_block_till_done()
    card = _pushes(board_calls)[-1]
    assert card["id"] == "st_tpv" and card["t"] == "kpi" and card["z"] == "p" and card["p"] == 2
    assert card["kpi"][0][:3] == ["PV", "5.0", "kW"] and card["kpi"][0][6] == "sun" and card["ac"] == "y"

    # Studio unloaded: the automation keeps working on its own
    await hass.config_entries.async_unload(hass.config_entries.async_entries(DOMAIN)[0].entry_id)
    board_calls.clear()
    hass.states.async_set("sensor.pv", "1200")
    await hass.async_block_till_done()
    assert _pushes(board_calls)[-1]["kpi"][0][1] == "1.2"


async def test_show_service_goes_through_the_automation(hass, esphome_entry, board_calls):
    await _setup(hass, esphome_entry)
    engine = _engine(hass)
    await engine.async_upsert({"id": "tmsg", "name": "Müll", "template": "msg", "title": "Müll morgen", "text": "Gelber Sack"})
    await hass.async_block_till_done()
    board_calls.clear()
    await hass.services.async_call(DOMAIN, "show", {"tile": "müll", "zone": "vollbild", "duration": 15}, blocking=True)
    await hass.async_block_till_done()
    card = _pushes(board_calls)[-1]
    assert card["id"] == "st_tmsg_abruf" and card["p"] == 1 and card["z"] == "f"
    assert card["hold"] == 15 and card["ttl"] == 15 and card["force"] == 1
    assert card["ti"] == "Müll morgen" and card["sub"] == "Gelber Sack"
    # "Ausführen" in HA's automation list = show on demand as well
    board_calls.clear()
    await hass.services.async_call("automation", "trigger", {"entity_id": "automation.perron_studio_mull"}, blocking=True)
    await hass.async_block_till_done()
    assert _pushes(board_calls)[-1]["id"] == "st_tmsg_abruf"


async def test_disabled_tile_automation_is_off(hass, esphome_entry, board_calls):
    await _setup(hass, esphome_entry)
    engine = _engine(hass)
    await engine.async_upsert({"id": "toff", "name": "Aus", "enabled": False, "template": "msg", "text": "x",
                               "when": {"mode": "always"}})
    await hass.async_block_till_done()
    assert hass.states.get("automation.perron_studio_aus").state == "off"


async def test_schedule_window(hass, esphome_entry, board_calls):
    from custom_components.perron_studio.autogen import _days
    from custom_components.perron_studio.engine import _in_window
    from datetime import datetime
    mon = datetime(2026, 10, 26, 7, 45)
    assert _in_window({"days": "Mo-Fr", "from": "06:30", "to": "09:00"}, mon)
    assert not _in_window({"days": "Sa,So", "from": "06:30", "to": "09:00"}, mon)
    assert _in_window({"days": "Fr-Mo", "from": "", "to": ""}, mon)
    assert _days("Mo-Fr") == ["mon", "tue", "wed", "thu", "fri"] and _days("Fr-Mo") == ["fri", "sat", "sun", "mon"]


async def test_preview_and_live_views(hass, esphome_entry, board_calls, aioclient_mock, hass_client, config_dir):
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
    assert "perron_studio_" not in (config_dir / "automations.yaml").read_text(encoding="utf-8")  # a draft
    r = await client.get("/api/perron_studio/tiles")
    tiles = await r.json()
    assert len(tiles) == 1 and tiles[0]["_status"]["saved"] is False


async def test_external_cards_registry_show_import(hass, esphome_entry, board_calls):
    await _setup(hass, esphome_entry)
    engine = _engine(hass)
    await hass.services.async_call("esphome", "perron_push_json", {"card": json.dumps(
        {"id": "pv", "t": "kpi", "ti": "Energie", "p": 2, "z": "f", "every": 900, "show": 10, "ttl": 3600,
         "kpi": [["PV", "3.1", "kW", "y", -1, "", "sun"]]})}, blocking=True)
    await hass.async_block_till_done()
    assert engine.external["pv"]["card"]["ti"] == "Energie" and not engine.external["pv"]["deleted"]
    await hass.services.async_call(DOMAIN, "show", {"tile": "pv", "zone": "f", "duration": 12}, blocking=True)
    card = _pushes(board_calls)[-1]
    assert card["id"] == "x_pv_abruf" and card["force"] == 1 and card["z"] == "f" and "every" not in card
    assert "x_pv_abruf" not in engine.external
    tile = engine.tile_from_external("pv")
    assert tile["template"] == "json" and json.loads(tile["card"])["ti"] == "Energie"
    await hass.services.async_call("esphome", "perron_push_json", {"card": '{"id":"pv","del":1}'}, blocking=True)
    assert engine.external["pv"]["deleted"] and engine.external["pv"]["card"]["ti"] == "Energie"


async def test_json_tile_template_and_empty(hass, esphome_entry, board_calls):
    await _setup(hass, esphome_entry)
    engine = _engine(hass)
    hass.states.async_set("sensor.wm", "off")
    tpl = ("{% if is_state('sensor.wm','in_use') %}"
           '{"t":"prog","ti":"Waschen","val":"42\'","pct":60}'
           "{% endif %}")
    await engine.async_upsert({"id": "twm", "name": "Wäsche", "template": "json", "card": tpl,
                               "when": {"mode": "always", "min_interval": 0}, "where": {"zone": "p"}})
    await hass.async_block_till_done()
    board_calls.clear()
    hass.states.async_set("sensor.wm", "in_use")
    await hass.async_block_till_done()
    card = _pushes(board_calls)[-1]
    assert card["id"] == "st_twm" and card["t"] == "prog" and card["z"] == "p" and card["pct"] == 60
    assert card["ttl"] >= 1800 and card["val"] == "42'"
    hass.states.async_set("sensor.wm", "off")
    await hass.async_block_till_done()
    assert _pushes(board_calls)[-1] == {"id": "st_twm", "del": 1}


async def test_alarm_json_tile_keeps_p0(hass, esphome_entry, board_calls):
    await _setup(hass, esphome_entry)
    engine = _engine(hass)
    hass.states.async_set("binary_sensor.smoke", "off")
    await engine.async_upsert({"id": "tal", "name": "Rauch", "template": "json", "when": {"mode": "always", "min_interval": 0},
                               "card": "{% if is_state('binary_sensor.smoke','on') %}{'t':'msg','p':0,'s':'x','ti':'Rauch'}{% endif %}"})
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.smoke", "on")
    await hass.async_block_till_done()
    card = _pushes(board_calls)[-1]
    assert card["p"] == 0 and card["s"] == "x" and card["id"] == "st_tal"


async def test_hand_edit_is_detected(hass, esphome_entry, board_calls, config_dir):
    await _setup(hass, esphome_entry)
    engine = _engine(hass)
    await engine.async_upsert({"id": "th", "name": "Hand", "template": "msg", "text": "a"})
    await hass.async_block_till_done()
    p = config_dir / "automations.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("Perron Studio: Hand", "Perron Studio: Hand geändert"), encoding="utf-8")
    await hass.services.async_call("automation", "reload", blocking=True)
    await hass.async_block_till_done()
    assert engine.status(engine.get("th"))["modified"] is True
    await engine.async_delete("th")
    await hass.async_block_till_done()
    assert "perron_studio_th" not in p.read_text(encoding="utf-8")
    assert (config_dir / "automations.yaml.perron_studio.bak").exists()


async def test_image_signed_url_and_view(hass, esphome_entry, board_calls, hass_client_no_auth):
    await _setup(hass, esphome_entry)
    await hass.config.async_update(internal_url="http://192.0.2.1:8123")
    engine = _engine(hass)

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


async def test_image_tile_automation_uses_entity_picture(hass, esphome_entry, board_calls):
    await _setup(hass, esphome_entry)
    await hass.config.async_update(internal_url="http://192.0.2.1:8123")
    hass.states.async_set("camera.door", "idle", {"entity_picture": "/api/camera_proxy/camera.door?token=abc"})
    engine = _engine(hass)
    await engine.async_upsert({"id": "tim", "name": "Tür", "template": "img", "image": "camera.door", "sub1": "Tür"})
    await hass.async_block_till_done()
    board_calls.clear()
    await hass.services.async_call(DOMAIN, "show", {"tile": "tim"}, blocking=True)
    await hass.async_block_till_done()
    img = [d for s, d in board_calls if s == "perron_push_image_url"][-1]
    assert img["key"] == "st_tim"
    assert img["url"] == "http://192.0.2.1:8123/api/camera_proxy/camera.door?token=abc&width=192"
    assert _pushes(board_calls)[-1]["img"] == "st_tim"


async def test_automations_overview_skips_studio_tiles(hass, esphome_entry, board_calls):
    await _setup(hass, esphome_entry)
    engine = _engine(hass)
    await engine.async_upsert({"id": "tx", "name": "Studio-Kachel", "template": "msg", "text": "x"})
    await hass.async_block_till_done()
    ov = engine.automations_overview()
    assert all(not str(a["config_id"]).startswith("perron_studio_") for a in ov)


async def test_min_interval_throttles_fast_sensors(hass, esphome_entry, board_calls):
    await _setup(hass, esphome_entry)
    engine = _engine(hass)
    hass.states.async_set("sensor.fast", "1")
    await engine.async_upsert({"id": "tf", "name": "Schnell", "template": "hero", "value": "sensor.fast",
                               "when": {"mode": "always", "min_interval": 60}})
    await hass.async_block_till_done()
    board_calls.clear()
    for v in ("2", "3", "4"):
        hass.states.async_set("sensor.fast", v)
        await hass.async_block_till_done()
    vals = [c["val"] for c in _pushes(board_calls)]
    assert len(vals) == 1, vals  # one update, the next ones wait for min_interval / the refresh
    # on demand is never throttled
    await hass.services.async_call(DOMAIN, "show", {"tile": "tf"}, blocking=True)
    await hass.async_block_till_done()
    assert _pushes(board_calls)[-1]["id"] == "st_tf_abruf" and _pushes(board_calls)[-1]["val"] == "4"


async def test_saving_reloads_only_its_own_automation(hass, esphome_entry, board_calls, config_dir):
    await _setup(hass, esphome_entry)
    # another automation that is running (like the doorbell waiting for its snapshot)
    p = config_dir / "automations.yaml"
    p.write_text("- id: waiter\n  alias: Waiter\n  triggers: [{trigger: event, event_type: go}]\n"
                 "  actions: [{delay: 30}, {event: waited}]\n", encoding="utf-8")
    await hass.services.async_call("automation", "reload", blocking=True)
    await hass.async_block_till_done()
    import asyncio
    hass.bus.async_fire("go")
    for _ in range(20):  # no block_till_done: it would wait for the 30 s delay
        await asyncio.sleep(0)
    assert hass.states.get("automation.waiter").attributes["current"] == 1
    await _engine(hass).async_upsert({"id": "tr", "name": "Neu", "template": "msg", "text": "x"})
    for _ in range(20):
        await asyncio.sleep(0)
    assert hass.states.get("automation.waiter").attributes["current"] == 1  # still running
    assert "waiter" in p.read_text(encoding="utf-8") and "perron_studio_tr" in p.read_text(encoding="utf-8")


async def test_concurrent_write_is_not_lost(config_dir):
    import os
    from custom_components.perron_studio.autogen import _update
    p = config_dir / "automations.yaml"
    p.write_text("- id: a\n  alias: A\n", encoding="utf-8")
    tries = []

    def change(data):
        tries.append(1)
        if len(tries) == 1:  # someone else saves while we are working
            p.write_text("- id: a\n  alias: A\n- id: b\n  alias: B (HA-Editor)\n", encoding="utf-8")
            os.utime(p, ns=(1, 1))
        return data + [{"id": "perron_studio_x", "alias": "X"}]

    assert _update(str(p), change)
    text = p.read_text(encoding="utf-8")
    assert len(tries) == 2 and "B (HA-Editor)" in text and "perron_studio_x" in text
