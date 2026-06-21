# Roadmap & Ideen (nicht MVP)

Die scene-JSON-Schicht (siehe [02-architecture.md](02-architecture.md)) ist so gebaut, dass neue Inhalte
**rein HA-seitig** ergänzt werden können — meist ohne Firmware-Neu-Flash.

## Naheliegend
- **Kalender-gesteuerte Reisen:** nächster Kalender-Eintrag mit Ort → passendes Verkehrsmittel + Ziel:
  - Flug → **Brussels Airport (Zaventem)**, Zug → **Bruxelles-Midi**.
  - Wegzeit via **Waze-Templatesensor mit dynamischem Ziel** → `trip`-Widget + **Leave-Timer**.
- **Leave-Timer zum nächsten Termin** (Abfahrtsempfehlung „in 12 min losgehen").
- **Generischer Alert-/Message-Slot:** HA wirft beliebige Meldung auf die Tafel (`alert` im scene-JSON).
- **Tageszeit-/Kontext-Layouts** verfeinern (Wochenende, Feiertag, Schulferien).

## Später / optional
- **Leave-Timer nach Alarm-Aktivierung** (Weck-/Routine-Alarm → Countdown bis Losgehen).
- **Ethernet/PoE** statt WLAN für maximale Stabilität (Board-Wechsel nötig, siehe [01-hardware.md](01-hardware.md)).
- Mehr Linien/Haltestellen, Störungs-/Verspätungs-Hinweise (STIB/SNCB).
- Animationen/Übergänge, Nacht-Clock-Face, Feiertags-Themes.

## Separates Projekt (NICHT Teil von ha-diele-board)
- Das alte **„transit"-HTML-Dashboard → ordentliche HA-Integration** überführen. Dieses Projekt nutzt das
  Dashboard nur als **Lernquelle** (Key/IDs), nicht als Abhängigkeit.
