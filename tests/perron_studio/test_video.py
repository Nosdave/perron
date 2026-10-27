"""Video filter: real ffmpeg (imageio-ffmpeg's static build) -> JPEG frames -> UDP, received here
like the board would (perron_video.h packet format)."""
from __future__ import annotations

import asyncio
import io
import shutil
import socket
import subprocess

import pytest
from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component

from custom_components.perron_studio import video as V

DOMAIN = "perron_studio"


def _ffmpeg() -> str | None:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return shutil.which("ffmpeg")


FFMPEG = _ffmpeg()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def test_split_jpegs_and_packets():
    buf = bytearray(b"junk\xff\xd8AAA\xff\xd9\xff\xd8BB")
    assert V.split_jpegs(buf) == [b"\xff\xd8AAA\xff\xd9"]
    assert bytes(buf) == b"\xff\xd8BB"  # incomplete frame waits for more data
    buf += b"\xff\xd9"
    assert V.split_jpegs(buf) == [b"\xff\xd8BB\xff\xd9"] and not buf
    import hashlib
    import hmac
    s, key = bytes(range(8)), bytes(range(16))
    pk = V.frame_packets(s, key, 70000, b"x" * 3000)
    assert len(pk) == 3 and all(p[:4] == b"PV\x02\x00" and p[4:12] == s for p in pk)
    assert pk[0][12:14] == (70000 & 0xFFFF).to_bytes(2, "little") and pk[2][14:16] == bytes([2, 3])
    assert len(pk[0]) == 16 + 1400 + 8 and len(pk[2]) == 16 + 200 + 8
    for p in pk:  # what the board checks: HMAC-SHA256(key, header + data)[:8]
        assert p[-8:] == hmac.new(key, p[:-8], hashlib.sha256).digest()[:8]
    buf = bytearray(b"abc\xff")  # an SOI split across two reads must survive
    assert V.split_jpegs(buf) == [] and bytes(buf) == b"\xff"


def test_ffmpeg_args_layouts_and_hardening():
    a = V.ffmpeg_args("ffmpeg", V.Source("/media/x.mp4", "file", False), "s", 12, 30, True)
    vf = a[a.index("-vf") + 1]
    assert "scale=96:64" in vf and "crop=96:64" in vf and "-stream_loop" in a and "-re" in a
    assert a[a.index("-protocol_whitelist") + 1] == "file" and "-format_whitelist" in a
    assert a.index("-protocol_whitelist") < a.index("-i") and "-max_pixels" in a
    live = V.ffmpeg_args("ffmpeg", V.Source("rtsp://cam/1", "rtsp", True), "p", 12, 30, False)
    assert "-re" not in live and "-rtsp_transport" in live and "crop=62:44" in live[live.index("-vf") + 1]
    assert "file" not in live[live.index("-protocol_whitelist") + 1].split(",")
    web = V.ffmpeg_args("ffmpeg", V.Source("https://x/y.mp4", "http", False), "f", 12, 30, False)
    assert web[web.index("-protocol_whitelist") + 1] == "http,https,tls,tcp,crypto"


def test_redact():
    assert "abc" not in V.redact("http://h/api/x?authSig=abc&b=1")
    assert "pw" not in V.redact("rtsp://user:pw@cam/1")


@pytest.mark.skipif(FFMPEG is None, reason="no ffmpeg")
async def test_play_video_end_to_end(hass: HomeAssistant, tmp_path, monkeypatch, socket_enabled):
    # a short test clip
    clip = tmp_path / "clip.mp4"
    subprocess.run([FFMPEG, "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=24",
                    "-t", "2", "-pix_fmt", "yuv420p", str(clip)], check=True)
    hass.config.allowlist_external_dirs = {str(tmp_path)}

    # the "board": a UDP socket on localhost
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx.bind(("127.0.0.1", 0))
    rx.setblocking(False)
    monkeypatch.setattr(V, "PORT", rx.getsockname()[1])

    calls: list[tuple[str, dict]] = []

    async def rec(call: ServiceCall) -> None:
        calls.append((call.service, dict(call.data)))

    for action in ("perron_push_json", "perron_set_studio_token", "perron_video_start", "perron_video_stop"):
        hass.services.async_register("esphome", action, rec)
    MockConfigEntry(domain="esphome", title="Perron", data={"host": "127.0.0.1", "device_name": "perron"}).add_to_hass(hass)
    await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "ffmpeg", {"ffmpeg": {"ffmpeg_bin": FFMPEG}})
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"esphome_entry_id": hass.config_entries.async_entries("esphome")[0].entry_id})
    await hass.async_block_till_done()

    await hass.services.async_call(DOMAIN, "play_video", {"source": str(clip), "layout": "seitlich",
                                                          "title": "Test", "duration": 1}, blocking=True)
    start = next(d for s, d in calls if s == "perron_video_start")
    assert start["layout"] == "s" and start["seconds"] == 1 and len(start["session"]) == 16

    frames: dict[int, dict[int, bytes]] = {}
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 10
    while loop.time() < deadline and not any(s == "perron_video_stop" for s, _ in calls):
        try:
            pkt = rx.recv(2048)
        except BlockingIOError:
            await asyncio.sleep(0.02)
            continue
        assert pkt[:4] == b"PV\x02\x00" and pkt[4:12].hex() == start["session"] and len(start["key"]) == 32
        f = int.from_bytes(pkt[12:14], "little")
        frames.setdefault(f, {})[pkt[14]] = pkt[16:-8]
        if len(frames[f]) == pkt[15]:
            frames[f]["n"] = pkt[15]
    rx.close()
    done = [f for f in frames.values() if "n" in f]
    assert len(done) >= 3, len(done)  # ~12 fps for 1 s (slow CI: at least a few)
    jpg = b"".join(done[0][i] for i in range(done[0]["n"]))
    im = Image.open(io.BytesIO(jpg))
    assert im.format == "JPEG" and im.size == (96, 64)
    assert any(s == "perron_video_stop" for s, _ in calls)  # ended by itself -> board freed


async def test_bad_sources_are_refused(hass: HomeAssistant, tmp_path):
    from homeassistant.exceptions import HomeAssistantError
    p = V.VideoPlayer(hass, None)
    with pytest.raises(HomeAssistantError):
        await p.async_resolve("/etc/passwd")  # not in allowlist_external_dirs
    with pytest.raises(HomeAssistantError):
        await p.async_resolve("file:///etc/passwd")
    with pytest.raises(HomeAssistantError):
        await p.async_resolve("")
    with pytest.raises(HomeAssistantError):
        await p.async_resolve("udp://@:5000")  # would open a listener on the HA host
    with pytest.raises(HomeAssistantError):
        await p.async_resolve("-filter_complex")
    with pytest.raises(HomeAssistantError):
        await p.async_resolve("camera.perron_studio_live")
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    (tmp_path / "x.m3u8").write_text("#EXTM3U\nfile:///etc/passwd\n")
    with pytest.raises(HomeAssistantError):
        await p.async_resolve(str(tmp_path / "x.m3u8"))


@pytest.mark.skipif(FFMPEG is None, reason="no ffmpeg")
async def test_replace_stop_unload_and_errors(hass: HomeAssistant, tmp_path, monkeypatch, socket_enabled):
    from homeassistant.exceptions import HomeAssistantError
    clip = tmp_path / "clip.mp4"
    subprocess.run([FFMPEG, "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=12",
                    "-t", "3", "-pix_fmt", "yuv420p", str(clip)], check=True)
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    monkeypatch.setattr(V, "MIN_PLAY_INTERVAL", 0)
    calls: list[tuple[str, dict]] = []

    async def rec(call: ServiceCall) -> None:
        calls.append((call.service, dict(call.data)))

    for action in ("perron_push_json", "perron_set_studio_token", "perron_video_start", "perron_video_stop"):
        hass.services.async_register("esphome", action, rec)
    MockConfigEntry(domain="esphome", title="Perron", data={"host": "127.0.0.1", "device_name": "perron"}).add_to_hass(hass)
    await async_setup_component(hass, "http", {})
    assert await async_setup_component(hass, "ffmpeg", {"ffmpeg": {"ffmpeg_bin": FFMPEG}})
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"esphome_entry_id": hass.config_entries.async_entries("esphome")[0].entry_id})
    await hass.async_block_till_done()
    player = next(v for k, v in hass.data[DOMAIN].items() if not k.startswith("_"))["video"]

    await hass.services.async_call(DOMAIN, "play_video", {"source": str(clip), "duration": 20}, blocking=True)
    first = player._cur
    await hass.services.async_call(DOMAIN, "play_video", {"source": str(clip), "duration": 20}, blocking=True)
    assert player._cur is not first and first.proc.returncode is not None   # old ffmpeg ended
    assert not [d for s, d in calls if s == "perron_video_stop"]           # replacing sends no stop
    second = player._cur
    await hass.services.async_call(DOMAIN, "stop_video", {}, blocking=True)
    stops = [d for s, d in calls if s == "perron_video_stop"]
    assert len(stops) == 1 and stops[0]["session"] == second.session.hex() and player._cur is None

    await hass.services.async_call(DOMAIN, "play_video", {"source": str(clip), "duration": 20}, blocking=True)
    proc = player._cur.proc
    await hass.config_entries.async_unload(hass.config_entries.async_entries(DOMAIN)[0].entry_id)
    assert proc.returncode is not None  # unload ends ffmpeg

    # board without video firmware: clear error, nothing left running
    hass.services.async_remove("esphome", "perron_video_start")
    await hass.config_entries.async_setup(hass.config_entries.async_entries(DOMAIN)[0].entry_id)
    await hass.async_block_till_done()
    player = next(v for k, v in hass.data[DOMAIN].items() if not k.startswith("_"))["video"]
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, "play_video", {"source": str(clip)}, blocking=True)
    assert player._cur is None


async def test_play_video_is_admin_only(hass: HomeAssistant, hass_read_only_user):
    from homeassistant.core import Context
    from homeassistant.exceptions import Unauthorized
    MockConfigEntry(domain="esphome", title="Perron", data={"host": "127.0.0.1", "device_name": "perron"}).add_to_hass(hass)
    await async_setup_component(hass, "http", {})
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"esphome_entry_id": hass.config_entries.async_entries("esphome")[0].entry_id})
    await hass.async_block_till_done()
    with pytest.raises(Unauthorized):
        await hass.services.async_call(DOMAIN, "play_video", {"source": "https://x/y.mp4"}, blocking=True,
                                       context=Context(user_id=hass_read_only_user.id))
