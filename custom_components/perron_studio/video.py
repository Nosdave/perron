"""Video filter: any video live onto the board.

Source (camera entity, media-source id, allowed local file, http(s)/rtsp/rtmp URL, GIF) -> ffmpeg
(scale + crop to the layout's video area, LED-friendly colour) -> JPEG frames -> UDP to the board.

The board is told about the stream first over the encrypted ESPHome API (action video_start with
a random session id and a random key); it only accepts frames carrying that session and a valid
HMAC-SHA256 (truncated) made with that key. One stream at a time per board.

Hardening: ffmpeg only gets the protocols the source type needs (no file:/data:/concat: through
playlists), input size and probing are capped, playlists as local files are refused, ffmpeg's
stderr is drained continuously, and a stream without frames is ended.
"""
from __future__ import annotations

import asyncio
import collections
import contextlib
import hashlib
import hmac
import logging
import os
import re
import secrets
import struct
from dataclasses import dataclass, field
from urllib.parse import urlparse

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .board import Board

_LOGGER = logging.getLogger(__name__)

PORT = 4049
CHUNK = 1400
MAX_CHUNKS = 32
MAX_FRAME = CHUNK * MAX_CHUNKS
MAC_LEN = 8
# video area per layout (must match perron_video.h)
AREAS = {"f": (192, 64), "b": (192, 44), "s": (96, 64), "p": (62, 44)}
NO_FRAME_TIMEOUT = 15     # s without a frame -> stream ends (startup of slow cameras included)
MIN_PLAY_INTERVAL = 2.0   # s between play_video calls

PROTOCOLS = {
    "http": "http,https,tls,tcp,crypto",
    "rtsp": "rtsp,rtsps,rtp,udp,tcp,tls,srtp",
    "rtmp": "rtmp,rtmps,tcp,tls",
    "file": "file",
}
LIVE_SCHEMES = {"rtsp": "rtsp", "rtsps": "rtsp", "rtmp": "rtmp", "rtmps": "rtmp"}
LOCAL_FORMATS = "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,gif,avi,mpegts,image2,png_pipe,jpeg_pipe,webp_pipe"
PLAYLIST_SUFFIXES = (".m3u8", ".m3u", ".ffconcat", ".concat", ".sdp", ".txt", ".pls", ".xspf")
_SECRET_RE = re.compile(r"(authSig=|token=)[^&\s'\"]+|//[^/@\s]+:[^/@\s]+@")


def redact(text: str) -> str:
    """Keep signed tokens and camera passwords out of the log."""
    return _SECRET_RE.sub(lambda m: (m.group(1) + "…") if m.group(1) else "//…@", text)


@dataclass
class Source:
    url: str           # what ffmpeg opens
    kind: str          # http | rtsp | rtmp | file
    live: bool
    fmt: str | None = None   # forced input format (e.g. mpjpeg for HA's camera proxy)


@dataclass
class _Stream:
    session: bytes
    key: bytes
    proc: asyncio.subprocess.Process | None = None
    task: asyncio.Task | None = None
    transport: asyncio.DatagramTransport | None = None
    frames: int = 0
    skipped: int = 0
    stderr: collections.deque = field(default_factory=lambda: collections.deque(maxlen=20))
    info: dict = field(default_factory=dict)


def frame_packets(session: bytes, key: bytes, frame_no: int, jpeg: bytes) -> list[bytes]:
    """One JPEG -> board packets:
    "PV" 2 0 | session(8) | frame(u16 LE) | chunk | chunks | data | HMAC-SHA256(key, all before)[:8]."""
    chunks = [jpeg[i:i + CHUNK] for i in range(0, len(jpeg), CHUNK)] or [b""]
    n = len(chunks)
    out = []
    for i, c in enumerate(chunks):
        body = b"PV\x02\x00" + session + struct.pack("<HBB", frame_no & 0xFFFF, i, n) + c
        out.append(body + hmac.new(key, body, hashlib.sha256).digest()[:MAC_LEN])
    return out


def split_jpegs(buf: bytearray) -> list[bytes]:
    """Take complete JPEGs (SOI ... EOI) out of an MJPEG byte stream; the rest stays in buf."""
    out = []
    while True:
        start = buf.find(b"\xff\xd8")
        if start < 0:
            keep_ff = bool(buf) and buf[-1] == 0xFF  # an SOI may be split across two reads
            buf.clear()
            if keep_ff:
                buf += b"\xff"
            return out
        end = buf.find(b"\xff\xd9", start + 2)
        if end < 0:
            if start:
                del buf[:start]
            return out
        out.append(bytes(buf[start:end + 2]))
        del buf[:end + 2]


def ffmpeg_args(binary: str, src: Source, layout: str, fps: int, seconds: int, loop: bool) -> list[str]:
    w, h = AREAS[layout]
    vf = (f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase:flags=area,crop={w}:{h},"
          "eq=saturation=1.3:contrast=1.1:gamma=1.15,format=yuvj420p")  # LEDs: dark tones vanish
    args = [binary, "-hide_banner", "-loglevel", "error", "-nostdin",
            "-protocol_whitelist", PROTOCOLS[src.kind],
            "-probesize", "5000000", "-analyzeduration", "5000000", "-max_pixels", "8294400",
            "-threads", "2"]
    if src.kind == "file":
        args += ["-format_whitelist", LOCAL_FORMATS]
    if src.kind == "http":
        args += ["-rw_timeout", "10000000"]
    if src.kind == "rtsp":
        args += ["-rtsp_transport", "tcp", "-timeout", "10000000"]
    if src.live:
        args += ["-fflags", "nobuffer", "-flags", "low_delay"]
    else:
        args += ["-re"]  # files and clips: real time, not as fast as possible
        if loop:
            args += ["-stream_loop", "-1"]
    if src.fmt:
        args += ["-f", src.fmt]
    args += ["-i", src.url, "-t", str(seconds), "-an", "-vf", vf,
             "-c:v", "mjpeg", "-q:v", "4", "-flush_packets", "1", "-f", "image2pipe", "pipe:1"]
    return args


class _Sender(asyncio.DatagramProtocol):
    pass


class VideoPlayer:
    """Plays one stream at a time on one board."""

    def __init__(self, hass: HomeAssistant, board: Board) -> None:
        self.hass = hass
        self.board = board
        self._cur: _Stream | None = None
        self._lock = asyncio.Lock()
        self._last_play = 0.0

    @property
    def status(self) -> dict:
        s = self._cur
        if not s:
            return {"playing": False}
        return {"playing": True, "frames": s.frames, "skipped": s.skipped, **s.info}

    # ------------------------------------------------------------- sources
    async def async_resolve(self, source: str, seconds: int = 60) -> Source:
        source = (source or "").strip()
        if not source:
            raise HomeAssistantError("Keine Videoquelle angegeben")
        if source.startswith("camera."):
            if source.startswith("camera.perron_studio"):
                raise HomeAssistantError("Die Tafel selbst ist keine Videoquelle")
            from homeassistant.components.camera import async_get_stream_source
            url = await async_get_stream_source(self.hass, source)
            if url:
                return self._from_url(url, live=True)
            # no stream: HA's MJPEG proxy of the camera (signed, internal URL)
            return Source(self._signed(f"/api/camera_proxy_stream/{source}", seconds), "http", True, "mpjpeg")
        if source.startswith("media-source://"):
            from homeassistant.components.media_player import async_process_play_media_url
            from homeassistant.components.media_source import async_resolve_media
            media = await async_resolve_media(self.hass, source, None)
            return self._from_url(async_process_play_media_url(self.hass, media.url), live=False)
        if source.startswith("/"):
            allowed = await self.hass.async_add_executor_job(self.hass.config.is_allowed_path, source)
            if not allowed:
                raise HomeAssistantError(f"Pfad nicht freigegeben (allowlist_external_dirs): {source}")
            if source.lower().endswith(PLAYLIST_SUFFIXES):
                raise HomeAssistantError("Wiedergabelisten als Datei sind nicht erlaubt")
            real = await self.hass.async_add_executor_job(os.path.realpath, source)
            return Source(real, "file", False)
        return self._from_url(source, live=False)

    @staticmethod
    def _from_url(url: str, live: bool) -> Source:
        p = urlparse(url)
        scheme = p.scheme.lower()
        if scheme in ("http", "https"):
            path = p.path.lower()
            is_live = live or path.endswith((".m3u8", ".mjpg", ".mjpeg")) or "mjpeg" in path or "stream" in path
            return Source(url, "http", is_live)
        if scheme in LIVE_SCHEMES:
            return Source(url, LIVE_SCHEMES[scheme], True)
        raise HomeAssistantError(f"Unbekannte oder nicht erlaubte Videoquelle: {redact(url)}")

    def _signed(self, path: str, seconds: int) -> str:
        from datetime import timedelta

        from homeassistant.components.http.auth import async_sign_path
        from homeassistant.helpers.network import NoURLAvailableError, get_url
        try:
            base = get_url(self.hass, allow_external=False, prefer_external=False)
        except NoURLAvailableError as err:
            raise HomeAssistantError("Keine interne HA-URL gesetzt") from err
        return base + async_sign_path(self.hass, path, timedelta(seconds=seconds + 60))

    # ------------------------------------------------------------- play / stop
    async def async_play(self, source: str, layout: str = "f", title: str = "", sub: str = "",
                         seconds: int = 30, fps: int = 12, loop: bool = False) -> None:
        loop_ = asyncio.get_running_loop()
        if loop_.time() - self._last_play < MIN_PLAY_INTERVAL:
            raise HomeAssistantError("Bitte kurz warten – Video wird gerade gestartet")
        self._last_play = loop_.time()
        layout = layout if layout in AREAS else "f"
        seconds = max(1, min(900, int(seconds)))
        fps = max(1, min(20, int(fps)))
        src = await self.async_resolve(source, seconds)
        from homeassistant.components.ffmpeg import get_ffmpeg_manager
        binary = get_ffmpeg_manager(self.hass).binary
        async with self._lock:
            await self._stop_locked(tell_board=False)
            stream = _Stream(session=secrets.token_bytes(8), key=secrets.token_bytes(16),
                             info={"source": source, "layout": layout, "seconds": seconds})
            try:
                stream.transport, _ = await loop_.create_datagram_endpoint(
                    _Sender, remote_addr=(self.board.host, PORT))
                stream.proc = await asyncio.create_subprocess_exec(
                    *ffmpeg_args(binary, src, layout, fps, seconds, loop),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.DEVNULL)
            except OSError as err:
                await self._cleanup(stream)
                raise HomeAssistantError(f"Video konnte nicht starten: {err}") from err
            ok = await self._board_call("video_start", session=stream.session.hex(), key=stream.key.hex(),
                                        layout=layout, title=title or "", sub=sub or "", seconds=seconds)
            if not ok:
                await self._cleanup(stream)
                raise HomeAssistantError("Tafel nicht erreichbar oder Firmware ohne Video (ab 0.6)")
            self._cur = stream
            stream.task = self.hass.async_create_background_task(self._pump(stream), "perron_studio_video")

    async def _board_call(self, action: str, **data) -> bool:
        try:
            async with asyncio.timeout(10):
                return await self.board.call(action, **data)
        except (TimeoutError, HomeAssistantError) as err:
            _LOGGER.warning("Perron Studio Video: %s fehlgeschlagen (%s)", action, err)
            return False

    async def _drain_stderr(self, stream: _Stream) -> None:
        assert stream.proc and stream.proc.stderr
        while line := await stream.proc.stderr.readline():
            stream.stderr.append(redact(line.decode(errors="replace").rstrip()))

    async def _pump(self, stream: _Stream) -> None:
        assert stream.proc and stream.proc.stdout and stream.transport
        drain = self.hass.async_create_background_task(self._drain_stderr(stream), "perron_studio_video_err")
        buf = bytearray()
        try:
            async with asyncio.timeout(stream.info["seconds"] + 30):
                while True:
                    try:
                        async with asyncio.timeout(NO_FRAME_TIMEOUT):
                            data = await stream.proc.stdout.read(65536)
                    except TimeoutError:
                        _LOGGER.warning("Perron Studio Video: keine Bilder von %s", redact(stream.info["source"]))
                        break
                    if not data:
                        break
                    buf += data
                    if len(buf) > 4 * MAX_FRAME:  # garbage without JPEG markers
                        buf.clear()
                    for jpg in split_jpegs(buf):
                        if len(jpg) > MAX_FRAME:
                            stream.skipped += 1
                            continue
                        for pkt in frame_packets(stream.session, stream.key, stream.frames, jpg):
                            stream.transport.sendto(pkt)
                        stream.frames += 1
        except TimeoutError:
            pass
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Perron Studio Video")
        finally:
            await self._cleanup(stream)
            drain.cancel()
            if not stream.frames and stream.stderr:
                _LOGGER.warning("Perron Studio Video: ffmpeg: %s", " | ".join(stream.stderr)[-500:])
            if self._cur is stream:  # ended by itself (end of clip / time): free the board now
                self._cur = None
                await self._board_call("video_stop", session=stream.session.hex())

    @staticmethod
    async def _cleanup(stream: _Stream) -> None:
        if stream.transport:
            stream.transport.close()
        p = stream.proc
        if p and p.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                p.kill()
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(5):
                    await p.wait()

    async def _stop_locked(self, tell_board: bool = True) -> None:
        s, self._cur = self._cur, None
        if not s:
            return
        if s.task:
            s.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await s.task
        await self._cleanup(s)
        if tell_board:
            await self._board_call("video_stop", session=s.session.hex())

    async def async_stop(self) -> None:
        async with self._lock:
            await self._stop_locked()
