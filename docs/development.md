# Development

## Layout

```
esphome/
  perron.yaml            main configuration (no secrets; Wi-Fi/keys are entered on the device)
  packages/              settings, display, light sensor, transit
  perron/
    perron_core.h        data layer: background fetch task, streaming JSON, model
    perron_render.h      renderer (layouts, badges, pager, alerts, night mode)
    perron_icons.h       generated pixel icons
    perron_lines.h       generated line colours (GTFS)
  web/                   on-device setup wizard (served instead of the default ESPHome page)
  fonts/                 X11 misc-fixed bitmap fonts
site/                    GPS setup helper + generated stop/station data (GitHub Pages)
tools/
  mockup/                pixel-exact mockup renderer (same fonts and icons as the firmware)
  gen_assets.py          icons + line colours -> C++ headers
  gen_site_data.py       stops/stations for the setup helper
```

## Build and flash

```bash
pip install esphome==2026.5.3
esphome run esphome/perron.yaml            # USB first time, OTA afterwards
```

GitHub Actions (`.github/workflows/pages.yml`) builds the firmware and publishes it with the
setup helper to GitHub Pages; devices pick up new versions from the manifest at night.

## Design workflow

Layouts are designed in `tools/mockup` first and reviewed as LED renderings, then ported to
`perron_render.h` with identical coordinates (text `y` = top of capitals). Regenerate assets after
changing icons or when the operators publish new GTFS data:

```bash
python tools/gen_assets.py --gtfs
python tools/gen_site_data.py
python tools/mockup/readme_images.py
```

## Architecture notes

- All network access runs in one FreeRTOS task; the display loop only reads a snapshot of the
  model when its generation changes, and rebuilds rows at most once per second.
- JSON is parsed streaming from the HTTP connection with ArduinoJson filters into PSRAM, so large
  feeds do not need full-body buffers. mbedTLS allocates in PSRAM (the HUB75 DMA buffers occupy
  most of the internal RAM).
- Panel refresh (100 Hz, DMA) is decoupled from redrawing (20 fps, double buffered).
