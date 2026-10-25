"""Talking to the board: ESPHome actions (encrypted API) and the token-protected HTTP endpoints."""
from __future__ import annotations

import io
import json
import logging
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class Board:
    """One Perron board."""

    def __init__(self, hass: HomeAssistant, device: str, host: str, token: str) -> None:
        self.hass = hass
        self.device = device
        self.host = host
        self.token = token

    # ------------------------------------------------------------- ESPHome actions
    def _service(self, action: str) -> str:
        return f"{self.device}_{action}"

    def has_action(self, action: str) -> bool:
        return self.hass.services.has_service("esphome", self._service(action))

    async def call(self, action: str, **data: Any) -> bool:
        if not self.has_action(action):
            _LOGGER.debug("esphome.%s not available (board offline or old firmware)", self._service(action))
            return False
        await self.hass.services.async_call("esphome", self._service(action), data, blocking=True)
        return True

    async def push_card(self, card: dict) -> bool:
        # ASCII-safe JSON: umlauts travel as \\u escapes
        return await self.call("push_json", card=json.dumps(card, ensure_ascii=True, separators=(",", ":")))

    async def delete_card(self, card_id: str) -> bool:
        return await self.push_card({"id": card_id, "del": 1})

    async def set_token(self) -> bool:
        return await self.call("set_studio_token", token=self.token)

    async def push_image_url(self, key: str, url: str) -> bool:
        return await self.call("push_image_url", key=key, url=url)

    async def show_commute(self, slot: int, seconds: int) -> bool:
        return await self.call("show_commute", slot=slot, seconds=seconds)

    # ------------------------------------------------------------- HTTP (token protected)
    async def _get(self, method: str, path: str, data: dict | None = None) -> bytes:
        session = async_get_clientsession(self.hass)
        url = f"http://{self.host}{path}"
        headers = {"X-Perron-Token": self.token}
        async with session.request(method, url, data=data, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=8)) as resp:
            body = await resp.read()
            if resp.status != 200:
                raise BoardError(resp.status, body.decode("utf-8", "replace"))
            return body

    async def screen_bmp(self) -> bytes:
        return await self._get("GET", "/perron/screen.bmp")

    async def preview_bmp(self, card: dict, zone: str) -> bytes:
        return await self._get("POST", "/perron/preview", data={
            "card": json.dumps(card, ensure_ascii=True, separators=(",", ":")), "zone": zone})


class BoardError(Exception):
    """HTTP error from the board."""

    def __init__(self, status: int, text: str) -> None:
        super().__init__(f"{status}: {text}")
        self.status = status
        self.text = text


def bmp_to_png(bmp: bytes, scale: int = 4, led: bool = True) -> bytes:
    """192x64 BMP -> scaled PNG; led=True draws round LED dots like the real panel."""
    from PIL import Image, ImageDraw  # Pillow ships with Home Assistant

    src = Image.open(io.BytesIO(bmp)).convert("RGB")
    w, h = src.size
    if not led:
        out = src.resize((w * scale, h * scale), Image.NEAREST)
    else:
        out = Image.new("RGB", (w * scale, h * scale), (10, 10, 12))
        draw = ImageDraw.Draw(out)
        px = src.load()
        r = max(1, scale // 2 - (0 if scale < 4 else 1))
        for y in range(h):
            for x in range(w):
                c = px[x, y]
                if c == (0, 0, 0):
                    c = (26, 26, 29)
                cx, cy = x * scale + scale // 2, y * scale + scale // 2
                draw.ellipse([cx - r, cy - r, cx + r - 1, cy + r - 1], fill=c)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=False)
    return buf.getvalue()
