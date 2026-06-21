# 04 — Home Assistant: HACS-Integration `diele_board`

Die HA-Seite ist eine **HACS-kompatible Custom-Integration** (`custom_components/diele_board/`) — kein
YAML-Package. Sie ist über **HACS** installierbar (Custom-Repo jetzt, Default-Store später möglich), per
**Config-Flow** in der UI konfigurierbar und liefert sauber alle HA-Entities des Entity-Vertrags.

> Wird in **Phase 3** real ausgearbeitet. Hier: Struktur, Felder, Installationsweg, HACS-Anforderungen.
> **Wichtig:** Entity-Vertrag & scene-JSON ([02-architecture.md](02-architecture.md)) bleiben unverändert —
> die Integration ist nur der *Produzent* dieser Entities (statt YAML-Templates).

## Warum Integration statt YAML
UI-Konfiguration (config_flow), HACS-Updates, saubere Trennung, reproduzierbar/„flippbar", später in den
HACS-Default-Store einreichbar.

## Struktur der Integration
```
custom_components/diele_board/
├─ __init__.py          Setup/Unload des Config-Entry, Coordinator-Wiring
├─ manifest.json        domain, name, version, config_flow:true, requirements, codeowners …
├─ const.py             DOMAIN="diele_board", Defaults, Keys
├─ config_flow.py       UI-Setup + Options
├─ coordinator.py       DataUpdateCoordinator: STIB (OAuth2) + iRail Fallback-Fetch
├─ sensor.py            sensor.diele_board_scene (JSON) + Diagnose
├─ number.py            number.diele_board_brightness
├─ switch.py            switch.diele_board_power
├─ text.py             text.* Waze-Ziel-Helfer (editierbar) + pywaze-Berechnung
├─ services.yaml        z. B. diele_board.show_alert (Alert injizieren)
├─ strings.json         Config-Flow-Texte
└─ translations/de.json / en.json
hacs.json               (Repo-Root) HACS-Metadaten
```

## Kernfelder
`manifest.json` (Auszug, HACS braucht `version` für Custom-Integrationen):
```json
{
  "domain": "diele_board",
  "name": "Diele Departure Board",
  "version": "0.1.0",
  "config_flow": true,
  "iot_class": "local_polling",
  "integration_type": "service",
  "documentation": "https://github.com/Nosdave/ha-diele-board",
  "issue_tracker": "https://github.com/Nosdave/ha-diele-board/issues",
  "codeowners": ["@Nosdave"],
  "requirements": []
}
```
`hacs.json` (Repo-Root):
```json
{ "name": "Diele Departure Board", "content_in_root": false, "render_readme": true, "homeassistant": "2024.12.0" }
```

## Was die Integration erzeugt / liest
- **Erzeugt** (ESP abonniert via `homeassistant`-Plattform):
  `sensor.diele_board_scene` (JSON), `number.diele_board_brightness`, `switch.diele_board_power`,
  Diagnose-Sensoren.
- **Liest/foldet ein** (per Config-Flow gewählt): `weather.zuhause` + Min/Max-Sensoren, Waze-Sensor,
  Diele-Präsenz-Sensoren, optional ESP-Status (`binary_sensor.diele_transit_stale`, Lux) für die Logik.

## Config-Flow (geplante Felder)
- STIB **Key/Secret** (→ daraus vorab `Basic`-Header; sicher in HA gespeichert).
- STIB **pointId**s (Tram, Bus) + Liniennummern.
- iRail **Station** (`BE.NMBS.xxxxxxxxx`) + **Richtungsfilter** (Gleis/`train_platform`).
- **Wetter**-Entity + Min/Max-Sensoren; **Waze**-Sensor; **Präsenz**-Sensoren (Diele).
- Update-Intervalle; Helligkeits-/Modus-Defaults.

## Coordinator
`DataUpdateCoordinator` holt **als Fallback** STIB (Token cachen ~50 min) + iRail (kein Auth, `User-Agent`)
und füllt `transit_fallback` im scene-JSON. (Primärquelle bleibt der ESP selbst.) Siehe
[05-stib-irail.md](05-stib-irail.md).

## Installation via HACS (Phase 3)
1. HACS → ⋮ → **Custom repositories** → Repo-URL eintragen, Kategorie **Integration**.
2. „Diele Departure Board" installieren → HA neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen → „Diele Departure Board"** → Config-Flow
   ausfüllen (STIB-Key, IDs, Entities …).
4. Entities prüfen (Developer Tools → States): `sensor.diele_board_scene` = valides JSON.

## HACS-Anforderungs-Checkliste
- [ ] `custom_components/diele_board/manifest.json` mit `version` + `config_flow: true`
- [ ] `hacs.json` im Repo-Root
- [ ] README vorhanden (✔)
- [ ] GitHub-Repo öffentlich, Beschreibung + Topics, mind. ein **Release/Tag** (für saubere HACS-Version)
- [ ] (Optional, später) Eintrag in `home-assistant/brands` + PR an HACS für Default-Store

## Verifikation
- Integration lädt fehlerfrei (Logs); Config-Flow durchläuft.
- `sensor.diele_board_scene` enthält valides JSON; Waze-Minuten & Präsenz korrekt eingefoldet.
- ESP empfängt Änderungen < paar Sekunden (native API).

## Pendel (Waze) & Präsenz
**Waze – von der Integration selbst verwaltet:** Die Integration legt pro Ziel eine **editierbare
`text`-Entity** an (Label je Pendel im Config-/Options-Flow konfigurierbar, Default „Commute 1/2"; keine
Namen im Code). Die Adresse trägst du in der HA-UI ein (oder
per Automation, z. B. Kalender-Trip) — sie bleibt als Entity-State **privat in HA**, nie im Repo. Die
Fahrzeit berechnet die Integration **intern via `pywaze`** (Origin = HA-Standort `zone.home`) →
`commute`-Liste. **Kein** separates Waze-Travel-Time-Setup nötig.

**Präsenz:** Eigene Präsenz-Entity(s) im Config-Flow wählen (mehrere = ODER-verknüpft). Tipp: eine
aggregierte Raum-Präsenz (Template/Bayesian/Bereichs-Belegung) bauen und dort eintragen.

**Zug-Richtung:** stadteinwärts über `train_platform` (Gleisnummer) filtern; leer = kein Filter.
