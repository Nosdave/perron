# 02 — Architektur

## Prinzip
**Max. standalone + HA-Fallback + HA-„Injection".**
- Der **ESP holt Transit selbst** (STIB + iRail) → läuft auch bei HA-Ausfall weiter.
- **HA liefert**: Fallback-Transit, Wetter, Waze, Präsenz, Modi, Helligkeit, Power — und eine flexible
  **Szenen-JSON**-Schicht, über die beliebige Inhalte „injiziert" werden können (Zukunft: Kalender-Reisen,
  Leave-Timer, Alerts …), **ohne Neu-Flash**.
- **Basics nativ** am ESP: SNTP-Uhr/Datum, adaptive Helligkeit, Render-Engine.

## Datenfluss

```
                 INTERNET
        ┌───────────┴────────────┐
   STIB OpenData (OAuth2)     iRail (frei)
   STIB Tram / Bus            SNCB-Zug
        │ ▲ primär                │ ▲ primär
        ▼ │                       ▼ │
   ┌─────────────────────────────────┐     Native ESPHome-API (verschlüsselt)
   │  ESP32-S3 (MatrixPortal S3)      │◄───────────────────────────────────────┐
   │  • SNTP-Uhr/Datum                │   HA → ESP:                              │
   │  • http_request Fetch STIB+iRail │   • text_sensor scene-JSON              │
   │  • Render-Engine (Widget-Zonen)  │   • binary_sensor Präsenz Diele         │
   │  • adaptive Helligkeit (Lux+HA)  │   • number Brightness · switch Power    │
   │  • Fallback: HA-Werte wenn stale │                                         │
   │  • VEML7700 (Lux, I2C)           │   ESP → HA: stale, lux, brightness, …   ┘
   └───────────────┬─────────────────┘
                   │ HUB75
                   ▼
        3× 64×64 P4 (192×64) + 5V-PSU (Power-Injection)
```

## Entity-Vertrag (HA ⇄ ESP) — MVP

| Richtung | Entity (Vorschlag) | Zweck |
|---|---|---|
| HA→ESP | `sensor.diele_board_scene` (JSON-String) | Wetter min/max+Symbol, Waze, Trip, Alert, Mode, Fallback-Transit |
| HA→ESP | `binary_sensor.diele_presence` | Präsenz Diele → wecken/dimmen/blank |
| HA→ESP | `number.diele_board_brightness` | Helligkeits-Ziel/Override (0–255) — ESP mischt mit Lux |
| HA→ESP | `switch.diele_board_power` | Hart an/aus/blank |
| ESP→HA | `binary_sensor.diele_transit_stale` | eigener Fetch veraltet → HA-Fallback aktiv |
| ESP→HA | `sensor.diele_lux` / `…_brightness` / `…_uptime` / `…_wifi_signal` | Telemetrie/Diagnose |

## Szenen-JSON-Schema
HA baut diesen String per Template (das ist die „Injection"-Stelle). Firmware parst tolerant — **unbekannte
Felder werden ignoriert** (vorwärtskompatibel für Roadmap-Ideen).

```json
{
  "mode": "morning",            // morning | day | evening | night | away
  "brightness": 180,            // optionaler Vorschlag 0-255
  "present": true,
  "weather": { "icon": "cloudy", "min": 15, "max": 23, "now": 17 },
  "commute": [ { "label": "Commute 1", "min": 22 }, { "label": "Commute 2", "min": 18 } ],
  "trip":    { "active": false, "label": "", "leave_in": null, "mode": "", "dest": "" },
  "alert":   { "text": "", "level": "info" },          // info | warn | crit
  "transit_fallback": { "tram": [], "bus": [], "train": [] }
}
```

> ⚠️ **255-Zeichen-Limit:** Ein HA-*State* ist auf 255 Zeichen begrenzt. Das volle scene-JSON wird daher
> **als Attribut** `payload` (JSON-String) am `sensor.diele_board_scene` geführt (Attribute sind nicht
> begrenzt). Der ESP liest es via `homeassistant` text_sensor mit `attribute: payload`. **Phase 2:**
> ESPHome-Text-Sensor-Maximallänge verifizieren; falls zu lang → scene **pro Zone** in mehrere text_sensors
> splitten.

## Render-Logik (Firmware)
1. **Transit primär** aus eigenem Fetch. Ist er `stale` (> X min) → `scene.transit_fallback` + dezenter
   Stale-Indikator.
2. **Wetter / Waze / Trip / Alert / Mode** aus `scene`.
3. **Helligkeit** = f(Lux) geclamped/überschrieben durch `number.diele_board_brightness`, gegated durch
   Präsenz (Abwesenheit→dimmen/blank nach Timeout) und `mode` (night = sehr dunkel).
4. **Power**: `switch.diele_board_power` aus → Panel blank (Strom sparen).

## Widget-Zonen (192×64, Vorschlag)
```
┌──────────────────────────────────────┐  Zeile 0–13:  Uhr  ·  Wetter (Icon min/max)
│ 14:32                   wolkig 15/23°  │
│ ────────────────────────────────────  │  Zeile 14–39: Tram + Bus (Countdown)
│ T00 > Endstation       3'   11'   19'  │
│ B00 > Terminus         6'   16'        │
│ ────────────────────────────────────  │  Zeile 40–63: Zug · Waze · (Trip/Alert)
│ Zug Bahnhof > Zentrum      14:41  +2'  │
│ Arbeit (Waze)              22 min      │
└──────────────────────────────────────┘
```
(Trip/Alert überschreiben bei Bedarf die untere Zone.)

## Resilienz
- `homeassistant`-Plattform behält **letzten Wert** bei HA-Neustart.
- Eigener Transit-Fetch läuft unabhängig weiter → **Standalone-Nachweis**: HA neustarten, Tafel zeigt weiter
  aktuelle Tram/Zug-Zeiten.
