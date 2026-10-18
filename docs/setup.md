# Setup and configuration

## First start

1. **Flash once over USB:** `esphome run esphome/perron.yaml` (or ESPHome Web). Later updates are
   installed over the air.
2. **Wi-Fi:** with no saved network the board opens the hotspot **Perron** and shows a QR code.
   Scan it with the phone camera (from ~2 m works best), choose your network and enter the
   password. If the sign-in page does not open by itself, browse to `http://192.168.4.1`.
3. **Setup wizard:** once connected, the board shows a second QR code with its own address.
   Open it (or `http://perron.local`) and follow the five steps.

## Setup wizard

| Step | What you configure |
|---|---|
| 1. Stops | Tap **Use my phone's location**: a secure helper page lists the nearest stops with their lines and directions; tap the ones to show. Walking time per stop is estimated from your position. Manual entry is possible too. |
| 2. Train & commute | SNCB station, train filter (platform / lines / destinations), walking time to the station, public-transport commute (iRail stations). |
| 3. Data | STIB API key (optional, write-only), weather, BE-Alert, disruptions, headlines, free text. |
| 4. Appearance | Layout, language, brightness, night mode, walking times, second departure, info line, destination short names. |
| 5. Status | Live state of every data source, automatic updates. |

The phone location never leaves the phone; only the selected stop IDs and a rounded position
(~100 m, for weather and alerts) are sent to the board.

## Settings reference

All settings are stored on the device and are also available as entities in Home Assistant.

| Setting | Format / range | Notes |
|---|---|---|
| Stops | `pointid[:min],…` e.g. `1234:1,2345:5` | STIB platform IDs; optional walking minutes per stop |
| Line filter | `81,71` | empty = all lines |
| Destination filter | `71=Delta;81=Montgomery` | a listed line is only shown towards matching destinations |
| Station | iRail ID `BE.NMBS.008813003` | |
| Train filter | `p2` · `S5,S19` · destination text | platform, lines or destinations |
| Commute from / to | iRail IDs | public-transport travel time in the info line |
| Location | `lat,lon` | default: Brussels centre |
| Layout | Premium · 4 rows · 2 large rows | |
| Walking time (default / station) | 0–15 / 0–30 min | colour threshold and catchability |
| Preview | 15–95 min | later departures show as `HH:MM` |
| Night time / mode | `23:00-06:00`; off · dimmed · clock · dark | |
| Brightness (max / night) | 5–255 / 2–120 | with the light sensor the board regulates between both |
| Front panel light transmission | 5–100 % | light-sensor correction behind a tinted front |
| Automatic updates | on/off | checked every 6 h, installed between 03:00 and 05:00 |

## Reading the board

- **Large number:** minutes until departure at the stop (real-time forecast incl. delays).
  **Amber** = catchable, **red** = leave now (minutes ≤ walking time), **↓↓** = arriving.
- **Small grey number:** the following departure. Grey large numbers: data older than 3 minutes.
- **`HH:MM` in grey:** next departure is beyond the preview window. **`-`:** no data.
- **Pedestrian + number:** walking time to that stop.
- **Info line:** the coloured tag shows the topic — purple weather, blue calendar, teal commute,
  orange disruption, red alert, grey headline, light blue Home Assistant text.
- **Full screen red banner:** BE-Alert for your location, a severe RMI warning or a critical
  message from Home Assistant (20 s, then repeated every 10 minutes).
