"""REST API for the Perron Studio panel (admin only, HA authentication)."""
from __future__ import annotations

import asyncio
from http import HTTPStatus

from aiohttp import web

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

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
        return self.json([{**t, "_status": eng.status(t)} for t in eng.tiles])

    async def post(self, request: web.Request) -> web.Response:
        _admin(request)
        _, d = _ctx(request)
        body = await request.json()
        if body.get("new"):  # a draft: becomes an automation with the first "Speichern"
            return self.json(await d["engine"].async_upsert(new_tile(body.get("name") or "Neue Kachel"), write=False))
        else:
            tile = body.get("tile") or {}
            if not tile.get("id"):
                return self.json_message("id fehlt", HTTPStatus.BAD_REQUEST)
            tile = {k: v for k, v in tile.items() if not k.startswith("_")}
        try:
            saved = await d["engine"].async_upsert(tile)
        except HomeAssistantError as err:
            return self.json_message(str(err), HTTPStatus.BAD_REQUEST)
        return self.json({**saved, "_status": d["engine"].status(saved)})

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
        tile = {**new_tile(), **tile}
        card = eng.build_card(tile, "preview")
        if not card:  # Karten-JSON whose template gives nothing right now
            return self.json_message("Vorlage liefert gerade keine Karte (z. B. Gerät aus)", HTTPStatus.CONFLICT)
        if card.get("img"):  # the picture has to be on the board first (it downloads it from HA)
            await eng._image_for(tile, max_age=20)
        try:
            for _ in range(16):  # board answers "Bild lädt" until the download is decoded
                try:
                    bmp = await d["board"].preview_bmp(card, zone)
                    break
                except BoardError as err:
                    if "Bild" not in err.text and err.status != 429:
                        raise
                    await asyncio.sleep(0.5)
            else:
                return self.json_message("Tafel: Bild kam nicht an", HTTPStatus.BAD_GATEWAY)
        except BoardError as err:
            return self.json_message(f"Tafel: {err.text}", HTTPStatus.BAD_GATEWAY)
        except Exception as err:  # noqa: BLE001 - board offline etc.
            return self.json_message(f"Tafel nicht erreichbar ({err})", HTTPStatus.BAD_GATEWAY)
        png = await hass.async_add_executor_job(bmp_to_png, bmp, 4, True)
        return web.Response(body=png, content_type="image/png", headers={
            "Cache-Control": "no-store", "X-Perron-Card": str(len(str(card))),
            "X-Perron-Night": "1" if d["board"].night else "0"})


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


class ExternalView(HomeAssistantView):
    """Cards that automations send to the board: list, show now, take over as a tile."""

    url = "/api/perron_studio/external"
    name = "api:perron_studio:external"

    async def get(self, request: web.Request) -> web.Response:
        _admin(request)
        _, d = _ctx(request)
        eng = d["engine"]
        cards = []
        for cid, rec in sorted(eng.external.items(), key=lambda kv: kv[1].get("at", ""), reverse=True):
            cards.append({**rec, "tile": eng.tile_from_external(cid),
                          "taken": any(t.get("from_automation") == cid for t in eng.tiles)})
        return self.json({"cards": cards, "automations": eng.automations_overview()})

    async def post(self, request: web.Request) -> web.Response:
        _admin(request)
        _, d = _ctx(request)
        eng = d["engine"]
        body = await request.json()
        cid = str(body.get("id") or "")
        if body.get("action") == "show":
            ok = await eng.async_show_external(cid, body.get("zone"), body.get("duration"))
            return self.json({"ok": ok})
        if body.get("action") == "import":
            tile = eng.tile_from_external(cid)
            if tile is None:
                return self.json_message("Karte unbekannt", HTTPStatus.NOT_FOUND)
            return self.json(await eng.async_upsert(tile))
        if body.get("action") == "forget":
            eng.external.pop(cid, None)
            await eng.async_save()
            return self.json({"ok": True})
        return self.json_message("action?", HTTPStatus.BAD_REQUEST)


class ImageView(HomeAssistantView):
    """Small JPEGs for the board. The board has no HA login: it gets a signed URL (5 min)."""

    url = "/api/perron_studio/img/{key}.jpg"
    name = "api:perron_studio:img"

    async def get(self, request: web.Request, key: str) -> web.Response:
        _, d = _ctx(request)
        jpg = d["engine"].images.get(key)
        if jpg is None:
            raise web.HTTPNotFound()
        return web.Response(body=jpg, content_type="image/jpeg", headers={"Cache-Control": "no-store"})


@callback
def async_register_views(hass: HomeAssistant) -> None:
    for view in (MetaView, TilesView, PreviewView, LiveView, ShowView, ImageView, ExternalView):
        hass.http.register_view(view())
