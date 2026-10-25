# Perron Studio (Home Assistant)

Design the board's cards in Home Assistant instead of writing JSON: pick a template, fill the
fields with entities or templates, choose when and where the tile appears, and see a preview
rendered by the board itself.

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
| `perron_studio.show` | show a tile now: `tile` (name or id), optional `zone` (`f`/`p`/`l`) and `duration` |
| `perron_studio.hide` | remove a tile from the board |
| `perron_studio.show_commute` | route commute 1 or 2 now and show it full screen |

## Tiles

* **Content** – template (number, key figures, list, progress, text, agenda, doorbell, image,
  free canvas), title, values, icon, accent colour. Every field accepts plain text, an entity id
  (its state is used) or a Jinja template.
* **When** – *on demand only*, *always*, *while a condition is true* or *in a time window*;
  optionally only now and then (every *n* seconds for *m* seconds); event triggers (an entity
  changes, e.g. the doorbell) show the tile immediately.
* **Where & how long** – full screen, right panel or info line; duration for on-demand/events;
  importance.

Voice commands, dashboard buttons and automations call `perron_studio.show`:

```yaml
action: perron_studio.show
data:
  tile: Energie
  zone: f
  duration: 20
```

## Security

The board's preview and live endpoints only answer with an access token. The integration
creates it during setup and hands it to the board over the encrypted ESPHome API; it is stored
in the config entry and on the board, never shown in the web interface. The board serves one
request at a time (at least 250 ms apart, at most 1 KB).
