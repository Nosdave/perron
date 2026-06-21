# 01 — Hardware

## Maßentscheidung
- Tür: **88 cm** breit. Über der Tür ~**50 cm** bis zur Decke; genutzt werden sollen **≤30 cm** (Höhe).
- Gewählt: **192×64 px @ P4** → **76,8 × 25,6 cm**. ~87 % der Türbreite, klar unter 30 cm hoch.
- Pixelpitch **P4 (4 mm)** bewusst gewählt: deutlicher **Dot-Matrix-/Haltestellen-Look** und gut lesbar quer
  durch den Flur (Faustregel Betrachtungsabstand ≈ Pitch[mm] × ~1; P4 ⇒ ab ~1,2 m gut).

## Panel-Konfiguration
- **3× 64×64 P4 HUB75-Panels** (je 256×256 mm), horizontal verkettet → 192×64 (Variante A, wenige Nähte).
- Alternative B: **6× 64×32 P4** als 3×2-Raster (gleiche 192×64, 1/16-Scan = robuster/billiger, aber
  zusätzliche horizontale Naht). In ESPHome via `layout_cols: 3`, `layout_rows: 2`.
- 64×64-Panels nutzen **1/32-Scan** — von der offiziellen ESPHome-`hub75`-Plattform unterstützt; im
  Smoke-Test (Phase 2) verifizieren.

## Stückliste (BE-lieferbar; Links/Preise am Bestelltag prüfen)

| # | Teil | Empfehlung | Händler | ~€ |
|---|---|---|---|---|
| 1 | LED-Panel ×3 | 64×64 **P4** HUB75, 256×256 mm (Waveshare „RGB-Matrix-P4-64x64" o. gleichw.) | kiwi-electronics.com · tinytronics.nl · waveshare.com · Amazon.de | 3× 45–70 |
| 2 | Controller | **Adafruit MatrixPortal S3** (#5778) | eckstein-shop.de (~27 ✔) · kiwi-electronics.com · Adafruit | 27–35 |
| 3 | Netzteil | **Meanwell LRS-150-5** (5V/30A/150W); Reserve: LRS-200-5 (40A) | reichelt.de · conrad.be · tme.eu | 30–55 |
| 4 | Lichtsensor | **Adafruit VEML7700** (#4162, I2C/STEMMA QT) | kiwi-electronics.com · Adafruit | 6–10 |
| 5 | Strom-Kabel | AWG14–16 rot/schwarz (Power-Injection an **jedes** Panel) + Aderendhülsen | lokal · Amazon.de | ~10 |
| 6 | Sicherung | 5×20 mm Halter + **25 A** Sicherung (PSU→Panels) | Amazon.de · Conrad | ~5 |
| 7 | HUB75-Flachband | 2×8 IDC (meist beigelegt), ggf. Ersatz | AliExpress · Amazon.de | ~5 |
| 8 | Front | **dunkel getöntes Acryl** ~25–40 % Transmission, lasergeschnitten auf Maß | snijlab.nl · lokaler Laser BXL | 25–45 |
| 9 | Rahmen | **Eiche-Massivrahmen** + schwarze Alu-Innenblende (CNC/Tischler) | lokal | 60–180 |
| 10 | Montage | French-Cleat / versteckte Halterung, Kabelkanal, PSU-Versteck | Baumarkt | ~20 |

> Maschinenlesbar: [../hardware/bom.csv](../hardware/bom.csv)

## Strombudget & Sicherheit
- 3× 64×64 ≈ bis **~24 A** worst-case (Vollweiß @ 100 %). Real mit Helligkeits-Cap (adaptiv) ~**8–14 A**.
- **150 W (30 A)** reicht komfortabel und läuft kühl; 200 W = maximale Reserve.
- **Power-Injection** an alle 3 Panels (5V/GND je Panel) gegen Spannungsabfall → gleichmäßige Helligkeit/Farbe.
- **Gemeinsame Masse** PSU ↔ MatrixPortal. Inline-**Sicherung** PSU→Panels. **Mains/PSU gekapselt** verstauen
  (Deckenhohlraum/Schrank), nicht offen.

## Konnektivität
- **MVP: WLAN** (MatrixPortal S3). Foyer-WLAN-Abdeckung vorab prüfen.
- Upgrade-Pfad **Ethernet/PoE** (z. B. Olimex ESP32-POE-ISO + HUB75-Adapter) — verliert das MatrixPortal-
  Board-Preset, daher nicht MVP. Siehe [roadmap.md](roadmap.md).

## Quellen
- ESPHome HUB75: https://esphome.io/components/display/hub75/
- esp-hub75 Lib: https://components.espressif.com/components/esphome/esp-hub75
- MatrixPortal S3: https://www.adafruit.com/product/5778
