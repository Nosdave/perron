# Perron Studio (Home Assistant)

Design the board's cards in Home Assistant instead of writing JSON: pick a template, fill the
fields with entities or templates, choose when and where the tile appears, and see a preview
rendered by the board itself.

**Perron Studio is only the editor.** Saving a tile writes an ordinary Home Assistant automation
(*Perron Studio: <name>*, id `perron_studio_<tile id>`) to `automations.yaml`, the same way
Home Assistant's own automation editor does (validated, previous file kept as
`automations.yaml.perron_studio.bak`, automations reloaded). That automation renders the card and
sends it to the board; nothing of the Studio is needed while it runs. You find it under
*Settings → Automations*; edit it in the Studio (there is the preview) – the Studio notices hand
edits and asks before overwriting them.

## Install

1. Install via HACS (custom repository `Nosdave/perron`, category *Integration*) or copy
   `custom_components/perron_studio` to `/config/custom_components/`, then restart Home Assistant.
2. *Settings → Devices & services → Add integration → Perron Studio*, pick the board (it must be
   set up in the ESPHome integration already).
3. A **Perron Studio** entry appears in the sidebar (administrators only).

The board firmware needs version 0.5 or later (endpoints `/perron/screen.bmp`, `/perron/preview`).

## What it adds

| | |
|---|---|
| Side panel *Perron Studio* | live view, list of tiles, editor with preview |
| `camera.perron_studio_live` | the board as an image (LED look), usable in any dashboard |
| `perron_studio.show` | show a tile now (fires `perron_studio_show` for its automation): `tile` (name or id), optional `zone` (`f`/`p`/`l`) and `duration` |
| `perron_studio.hide` | remove a tile from the board |
| `perron_studio.show_commute` | route commute 1 or 2 now and show it full screen |

## Tiles

A new tile is a draft until it is saved; then its automation exists. The automation carries the
complete tile (variable `perron_studio_kachel`, compressed), and the Studio reads its saved tiles
from there: every saved tile can always be loaded back for editing, even after reinstalling the
Studio or restoring a backup. Only unsaved drafts live in the Studio's own storage. Switching a tile off switches
its automation off. Deleting a tile removes its automation.

* **Content** – template (number, key figures, list, progress, text, agenda, doorbell, image,
  free canvas), title, values, icon, accent colour. Every field accepts plain text, an entity id
  (its state is used) or a Jinja template.
* **When** – *on demand only*, *always*, *while a condition is true* or *in a time window*;
  optionally only now and then (every *n* seconds for *m* seconds); event triggers (an entity
  changes, e.g. the doorbell) show the tile immediately.
* **Where & how long** – full screen, right panel or info line; duration for on-demand/events;
  importance.

How the automation works: state tiles listen to the entities they use, re-send every 10 minutes
and on start (cards live 30 minutes on the board) and send a delete when their condition ends;
*at most every n seconds* keeps fast sensors from flooding the board. On demand the automation
answers the event `perron_studio_show` (`tile: <id>`, optional `zone`, `duration`), its event
triggers, and *Run* in Home Assistant's automation list.

Voice commands, dashboard buttons and automations call `perron_studio.show` (it fires that event):

```yaml
action: perron_studio.show
data:
  tile: Energie
  zone: f
  duration: 20
```

### Card JSON (advanced)

The template *Karten-JSON* takes the whole card as JSON (fields as in [cards.md](cards.md)) and
may be a Jinja template. An empty result, `none` or `{"del": 1}` means "no card right now": the
tile is inactive and its card is removed. The JSON decides `p`, `z`, `s`, `every`/`show`; the tile
settings only fill what is missing. `p: 0` makes an alarm (full screen until the template is empty
again).

```jinja
{% if is_state('sensor.washer', 'in_use') %}
{"t": "prog", "ti": "Waschen", "ic": "washer", "ac": "v",
 "val": "{{ states('sensor.washer_remaining') }}'", "pct": {{ states('sensor.washer_progress') | int(0) }}}
{% endif %}
```

### Pictures and cameras

The automation of an *image* or *doorbell* tile hands the board the picture's `entity_picture`
URL (cameras with `&width=192`); it carries its own access token, so the board needs no Home
Assistant login. For the preview the Studio fetches the picture itself, shrinks it to a JPEG and
lets the board download it from a signed URL (5 minutes). Home Assistant's *internal URL* must be
set (Settings → System → Network).

## Video

`perron_studio.play_video` plays any video live on the board – a camera, a freshly generated AI
clip, a video from the web, a GIF:

```yaml
action: perron_studio.play_video
data:
  source: camera.front_door        # camera entity, media-source://…, http(s)/rtsp URL, allowed path
  layout: s                        # f full bleed · b status bar + info line · s video left, text right · p panel tile
  title: Volt · Wetter
  text: Morgen 14°, ab 12 Uhr leichter Regen
  duration: 30                     # seconds (max 900)
  loop: false                      # repeat short clips / GIFs for the whole duration
```

Home Assistant does the work: its ffmpeg scales and crops the source live to the layout's video
area (192×64, 192×44, 96×64 or 62×44), boosts colour a little for LEDs and sends about 12 small JPEG
frames per second to the board (UDP port 4049). The board is told about the stream first over the
encrypted ESPHome API and only accepts frames of that stream; it ends the card by itself after the
duration or when frames stop. Alarms and a ringing doorbell take precedence. `perron_studio.stop_video`
ends it earlier. The panel has a *Video* section to try sources and layouts.

Local files must be in `allowlist_external_dirs`. Board firmware 0.6 or later. On the board,
*Helligkeit Video (mindestens)* lifts the panel while a video runs (also at night) and
*Video-Bildhelligkeit* sets how bright frames may be on average.

Security: only administrators (and automations/scripts) may call `play_video`; ffmpeg only gets
the protocols a source type needs (no local files through playlists), input size is capped, and
every UDP packet carries an HMAC with a per-stream key the board got over the encrypted API.

## Cards from automations

Studio watches every card that other automations send with `esphome.<board>_push_json` and lists
it in the panel with its last version. It does not change them. *Show* brings the last version to
the board now (also `perron_studio.show` with the card id as `tile`); *in HA öffnen* opens the
automation in Home Assistant's editor. *Take over* creates a *Karten-JSON* tile from it as a
starting point (optional).

Cards that need actions (calendar events, polling a sensor, waiting for a camera snapshot) stay
automations; Studio still shows them and can call them up.

## Night

In the board's night window only the doorbell, alarms and cards asked for on demand appear (full
screen for their duration). The preview always shows the day layout; the panel says when the board
is in its night window.

## Security

The board's preview and live endpoints only answer with an access token. The integration
creates it during setup and hands it to the board over the encrypted ESPHome API; it is stored
in the config entry and on the board, never shown in the web interface. The board serves one
request at a time (at least 250 ms apart, at most 1 KB); the integration queues its requests.
