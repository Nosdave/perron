# 03 — ESPHome Firmware

> Code wird in **Phase 2** (Smoke-Test mit Hardware) real ausgearbeitet/validiert. Dieses Dokument hält
> Struktur, Konfig-Schlüssel und Build-Weg fest.

## Struktur (`esphome/`)
Aufgeteilt in wiederverwendbare **packages** (sauber, flippbar):

| Datei | Inhalt |
|---|---|
| `diele-board.yaml` | Node-Hauptdatei: `substitutions`, `esp32` (board), `wifi`, `api` (encryption), `ota`, `time` (SNTP), `logger`, `i2c`, bindet packages, Diagnose-Sensoren |
| `packages/display.yaml` | `platform: hub75` + Fonts/Icons + Render-Lambda (Widget-Zonen) |
| `packages/transit.yaml` | `http_request` Fetch STIB (`bmc-partner-key`) + iRail, JSON-Parse, `transit_stale` |
| `packages/ha_inputs.yaml` | `homeassistant` text_sensor (scene), binary_sensor (Präsenz), number, switch |
| `packages/brightness.yaml` | VEML7700 + adaptive Helligkeit (`hub75.set_brightness`) |
| `secrets.yaml.example` | Vorlage für WLAN, API-Key, STIB-Basic-Header, OTA-Passwort |

## HUB75-Display (verifizierte Schlüssel)
Offizielle ESPHome-Plattform `hub75` (DMA-basiert). Beispiel-Skelett:

```yaml
display:
  - platform: hub75
    id: matrix
    board: adafruit-matrix-portal-s3   # Board-Preset → Pinmapping automatisch
    panel_width: 64
    panel_height: 64
    layout_cols: 3          # 3 Panels nebeneinander → 192 breit
    layout_rows: 1          # → 64 hoch
    layout: HORIZONTAL
    brightness: 128         # 0-255 (Start; zur Laufzeit via hub75.set_brightness)
    bit_depth: 6            # 4-12 (Default 8); 6 = guter Kompromiss Speicher/Farbe
    # update_interval / min_refresh_rate (40-200 Hz) im Smoke-Test tunen
    lambda: |-
      // Widget-Zonen rendern (siehe docs/02-architecture.md)
```
Helligkeit zur Laufzeit: Action `hub75.set_brightness` (0–255).
Unterstützte Chips: ESP32, S2, **S3**, C6, P4 — **nicht** C3/C2/H2. PSRAM (S3) hilft bei 192×64.

## Build & Flash
- **Lokal (CLI):** `pip install esphome`, dann `esphome run esphome/diele-board.yaml` (erstes Mal per USB-C,
  danach OTA).
- **Oder** über das ESPHome-Dashboard / HA-Add-on (Datei importieren).
- Fonts: `gfonts://...` oder lokale TTFs in `esphome/fonts/`. Transit-Icons als kleine PNGs in `esphome/icons/`.

## Phase-2-Checkliste (Smoke-Test)
1. MatrixPortal S3 + **1 Panel** → Testbild, dann Uhr.
2. **3er-Kette** (192×64) → `bit_depth`/`min_refresh_rate`/`brightness` justieren, Flimmern/Heat prüfen.
3. `http_request` **iRail** (frei) → JSON-Parse → Werte ins Display.
4. `http_request` **STIB** (Header `bmc-partner-key`, KEIN OAuth2) → WaitingTimes + Störungen → Display.
   Siehe [05-stib-irail.md](05-stib-irail.md).
5. `homeassistant`-Inputs anbinden (Phase 3) + `transit_stale`-Fallback.

## Quellen
- https://esphome.io/components/display/hub75/
- https://esphome.io/components/http_request
- https://esphome.io/components/text_sensor/homeassistant
