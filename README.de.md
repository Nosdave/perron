# Perron (Deutsch)

**Echtzeit-Abfahrtstafel für Brüssel auf einer 192×64-RGB-LED-Matrix.** Tram, Bus und Metro
(STIB/MIVB), Züge (SNCB/NMBS), Wetter (KMI/IRM), BE-Alert und eigene Infos aus Home Assistant –
im Stil der Verkehrsbetriebe, komplett eigenständig.

- **Eigenständig:** Der ESP32-S3 holt alle Daten selbst; Home Assistant ist optional.
- **Abfahrten nach Gehzeit eingefärbt:** Amber = schaffbar, Rot = jetzt los, ↓↓ = fährt ein.
- **Originale Linienfarben** aus den offiziellen GTFS-Daten von STIB und SNCB.
- **Feste Zeilen:** jede Linie/Richtung hat ihren Platz; fährt gerade nichts, steht die nächste Uhrzeit da.
- **Wetter & Warnungen:** KMI-Wetter mit Regenradar (10-Minuten-Raster), Unwetterwarnungen,
  STIB-Störungen, BE-Alert für den eigenen Standort.
- **Einrichtung wie bei einem Kaufprodukt:** WLAN per QR-Code, Einrichtungsassistent auf dem
  Gerät, Haltestellen-Vorschlag per Handy-GPS.
- **Details:** drei Layouts, Nachtmodus, automatische Helligkeit, nächtliche automatische Updates.

Ausführliche Dokumentation (Englisch): [README.md](README.md) · [Aufbau](docs/hardware.md) ·
[Einrichtung](docs/setup.md) · [Home Assistant](docs/home-assistant.md)
