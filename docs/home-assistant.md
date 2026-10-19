# Home Assistant

Perron works without Home Assistant. With it, you get remote configuration, sensors and extra
information cards.

## Adding the board

The ESPHome integration discovers the board automatically. During adoption Home Assistant
provisions an API encryption key; the firmware itself contains no secret.

## Entities

- **Configuration:** every setting from the web wizard (stops, filters, layout, brightness, …).
- **Abfahrten** (text sensor): JSON with the rows currently shown, e.g.
  `[{"l":"81","d":"Montgomery","m":[9,21]},{"l":"71","d":"Delta","m":[],"t":"05:42"}]`
  - `m`: minutes until departure at the stop (catchable departures within the preview)
  - `t`: time of the next departure when it is beyond the preview
- **Nächste Abfahrt** (text sensor): the soonest departure, e.g. `81 Montgomery 9 min`.
- **Datenstatus**, heap, PSRAM, Wi-Fi signal (diagnostics).

Use these sensors instead of polling the STIB API a second time — the API key is rate limited.

## Information cards: `push_card`

```yaml
action: esphome.perron_push_card
data:
  key: "car:office"        # same key replaces the card; empty message removes it
  message: "Office: 23 min"
  tag: 1                    # 0 calendar, 1 commute, 2 weather, 3 disruption, 4 alert, 5 news, 6 other
  prio: 2                   # 0 = full-screen alert, 1 high … 3 low
  ttl: 900                  # seconds; 0 = until removed
```

`esphome.perron_clear_alert` removes a full-screen alert sent with `prio: 0`.

## Rich cards and images

`esphome.perron_push_json` shows template cards (progress, numbers, lists, messages, doorbell,
images, free canvas) on the full screen, on panel 3 or in the pager; `push_image` and
`push_image_url` send PNG/BMP or raw RGB565 images. See [cards.md](cards.md).

## Blueprint

[`blueprints/automation/perron_info_cards.yaml`](../blueprints/automation/perron_info_cards.yaml)
sends car travel times (e.g. Waze Travel Time sensors), the next calendar events (recurring
events expanded by Home Assistant) and an optional free-text entity to the board every 5 minutes.

- Set **ESPHome action of the board** to your device's action (`esphome.<device_name>_push_card`).
- Only select travel-time sensors that are actually polled; disabled polling sends frozen values.
- Use either the blueprint or the legacy integration's board push for commute times, not both.

## Legacy integration

`custom_components/diele_board` is the earlier Home Assistant integration. It is no longer needed
— the firmware fetches all transit data itself, and the blueprint covers the extras — and will be
removed. If you still run it, disable its STIB polling to avoid using the API quota twice.
