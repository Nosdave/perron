# 05 — Daten: STIB & iRail (validiert 2026-06-16)

Endpoints & Datenformen live gegen die API verifiziert. **Keine** personenbezogenen IDs/Adressen in diesem
Repo — die eigenen Haltepunkte/Station/Arbeitsadressen werden im **Config-Flow** bzw. in der gitignorierten
`esphome/secrets.yaml` hinterlegt.

## STIB/MIVB — Belgian Mobility (Azure API Management) 🔑
**Kein OAuth2!** Auth = ein einziger Header `bmc-partner-key: <KEY>`.
- Base: `https://api-management-opendata-production.azure-api.net`
- Key: in `secrets.yaml` (`stib_partner_key`) bzw. Config-Flow. **Nicht im Repo.**

### Wartezeiten (Tram/Bus)
```
GET /api/datasets/stibmivb/rt/WaitingTimes/?where=pointid="<POINTID>"&limit=20
Header: bmc-partner-key: <KEY>
```
Antwort: `results[]` mit `pointid`, `lineid`, **`passingtimes`** (JSON-**String**!). Nach `JSON.parse`:
`[{destination:{fr,nl}, expectedArrivalTime:"…+02:00", lineId}]`. → Minuten = (expectedArrivalTime − now).

### Störungen / Traveller-Info
```
GET /api/datasets/stibmivb/rt/TravellersInformation/?limit=100
```
Antwort: `results[]` mit `content` (JSON-String `[{text:[{en,fr,nl}],type}]`), `lines` (JSON-String
`[{id}]`), `points` (JSON-String), `priority` (int). → Filter auf die eigenen Linien/Haltepunkte; niedrigste
`priority` = wichtigste Meldung. (Live getestet: liefert echte Werke/EU-Gipfel-Meldungen je Linie.)

### Fahrzeugpositionen (nur Karte, irrelevant)
`GET /api/datasets/stibmivb/rt/VehiclePositions/`

## iRail (SNCB/NMBS) — frei, kein Login ✅
- Base: `https://api.irail.be` · Header `User-Agent` Pflicht.
```
GET /liveboard/?id=<BE.NMBS.xxxxxxxxx>&format=json&lang=de&arrdep=departures
```
(`id=` für NMBS-IDs, sonst `station=<name>`; `/liveboard/` → 302 auf `/v1/liveboard`, `aiohttp` folgt selbst.)
Antwort: `departures.departure[]` mit `time` (Unix), `delay` (s), `station` (Ziel), `platform`, `vehicle`,
`canceled`. Linien-Parse aus `vehicle`: `BE.NMBS.S194015 → S19` (Regex `^([A-Z]+\d{0,2})\d{4}$`).
**Richtungsfilter** „stadteinwärts" am robustesten über das **Gleis** (`platform`) — Config `train_platform`.

## Eigene Haltepunkte ermitteln (kommt NICHT ins Repo)
1. **STIB pointId** je Linie/Haltestelle: aus den STIB-GTFS-/Stops-Daten bzw. einem vorhandenen
   STIB-Dashboard. Pro Richtung eigener pointId.
2. **iRail Station-ID**: https://github.com/iRail/stations (Format `BE.NMBS.xxxxxxxxx`) oder
   `GET /liveboard/?station=<Name>` → `stationinfo.id`.
3. Werte in den **Config-Flow** eintragen (Integration) bzw. `esphome/secrets.yaml` (Firmware).

## Offizielle Linienfarben (`LINE_COLORS`, in `const.py`)
92/93 = `#E2231A` · 60 = `#F9A825` · 37 = `#7B5EA7` · 8 = `#388E3C` · SNCB/S-Linien = `#003082`/`#FFD700` ·
IC = `#0055A4`. (Vollständig in `const.py`.)

## Doku-Portal
Heute `data.belgianmobility.io` (Rebrand von `opendata.stib-mivb.be`), eine JS-SPA. Maßgeblich sind die oben
verifizierten Endpoints. iRail-Doku: https://docs.irail.be/ · Stations: https://github.com/iRail/stations
