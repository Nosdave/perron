"""REST API for the Perron Studio panel (admin only, HA authentication)."""
from __future__ import annotations

from http import HTTPStatus

from aiohttp import web

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant, callback

from .board import BoardError, bmp_to_png
from .const import ACCENTS, DOMAIN, ICONS, TEMPLATES, ZONES
from .engine import new_tile


def _ctx(request: web.Request):
    hass: HomeAssistant = request.app[KEY_HASS]
    for k, v in hass.data.get(DOMAIN, {}).items():
        if not k.startswith("_"):
            return hass, v
    raise web.HTTPServiceUnavailable(text="Perron Studio ist nicht eingerichtet")


def _admin(request: web.Request) -> None:
    user = request.get("hass_user")
    if user is None or not user.is_admin:
        raise web.HTTPForbidden()


class MetaView(HomeAssistantView):
    url = "/api/perron_studio/meta"
    name = "api:perron_studio:meta"

    async def get(self, request: web.Request) -> web.Response:
        _admin(request)
        hass, d = _ctx(request)
        board = d["board"]
        return self.json({
            "templates": TEMPLATES, "zones": ZONES, "accents": ACCENTS, "icons": ICONS,
            "board": {"device": board.device, "host": board.host, "online": board.has_action("push_json"),
                      "token_ok": d.get("token_ok", False)},
        })


class TilesView(HomeAssistantView):
    url = "/api/perron_studio/tiles"
    name = "api:perron_studio:tiles"

    async def get(self, request: web.Request) -> web.Response:
        _admin(request)
        _, d = _ctx(request)
        eng = d["engine"]
        return self.json([{**t, "_active": eng._active.get(t["id"], False)} for t in eng.tiles])

    async def post(self, request: web.Request) -> web.Response:
        _admin(request)
        _, d = _ctx(request)
        body = await request.json()
        if body.get("new"):
            tile = new_tile(body.get("name") or "Neue Kachel")
        else:
            tile = body.get("tile") or {}
            if not tile.get("id"):
                return self.json_message("id fehlt", HTTPStatus.BAD_REQUEST)
            tile = {k: v for k, v in tile.items() if not k.startswith("_")}
        return self.json(await d["engine"].async_upsert(tile))

    async def delete(self, request: web.Request) -> web.Response:
        _admin(request)
        _, d = _ctx(request)
        await d["engine"].async_delete(request.query.get("id", ""))
        return self.json({"ok": True})


class PreviewView(HomeAssistantView):
    """Pixel-exact preview: the tile is rendered by the board itself (off screen)."""

    url = "/api/perron_studio/preview"
    name = "api:perron_studio:preview"

    async def post(self, request: web.Request) -> web.Response:
        _admin(request)
        hass, d = _ctx(request)
        body = await request.json()
        eng = d["engine"]
        tile = body.get("tile") or {}
        zone = body.get("zone") if body.get("zone") in ZONES else "f"
        card = eng.build_card({**new_tile(), **tile}, "preview")
        try:
            bmp = await d["board"].preview_bmp(card, zone)
        except BoardError as err:
            return self.json_message(f"Tafel: {err.text}", HTTPStatus.BAD_GATEWAY)
        except Exception as err:  # noqa: BLE001 - board offline etc.
            return self.json_message(f"Tafel nicht erreichbar ({err})", HTTPStatus.BAD_GATEWAY)
        png = await hass.async_add_executor_job(bmp_to_png, bmp, 4, True)
        return web.Response(body=png, content_type="image/png", headers={"Cache-Control": "no-store",
                                                                         "X-Perron-Card": str(len(str(card)))})


class LiveView(HomeAssistantView):
    url = "/api/perron_studio/live"
    name = "api:perron_studio:live"

    async def get(self, request: web.Request) -> web.Response:
        _admin(request)
        hass, d = _ctx(request)
        try:
            bmp = await d["board"].screen_bmp()
        except Exception as err:  # noqa: BLE001
            return self.json_message(f"Tafel nicht erreichbar ({err})", HTTPStatus.BAD_GATEWAY)
        png = await hass.async_add_executor_job(bmp_to_png, bmp, 4, True)
        return web.Response(body=png, content_type="image/png", headers={"Cache-Control": "no-store"})


class ShowView(HomeAssistantView):
    """'Jetzt auf der Tafel zeigen' from the editor."""

    url = "/api/perron_studio/show"
    name = "api:perron_studio:show"

    async def post(self, request: web.Request) -> web.Response:
        _admin(request)
        _, d = _ctx(request)
        body = await request.json()
        eng = d["engine"]
        tile = {**new_tile(), **(body.get("tile") or {})}
        await eng.async_show(tile, body.get("zone"), body.get("duration"))
        return self.json({"ok": True})


@callback
def async_register_views(hass: HomeAssistant) -> None:
    for view in (MetaView, TilesView, PreviewView, LiveView, ShowView):
        hass.http.register_view(view())
