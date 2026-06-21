# Bill of Materials — Diele Departure Board

Variante **A** (empfohlen): 3× 64×64 P4 → 192×64 (~76,8 × 25,6 cm), wenige Nähte.
Preise = Richtwerte (EUR), **am Bestelltag prüfen**; alle Händler liefern nach BE.
Maschinenlesbar: [bom.csv](bom.csv).

| # | Teil | Empfehlung | Händler | Menge | ~€/Stk | ~€ ges. |
|---|---|---|---|---|---|---|
| 1 | LED-Panel | 64×64 **P4** HUB75, 256×256 mm (Waveshare „RGB-Matrix-P4-64x64" o. gleichw.) | kiwi-electronics.com · tinytronics.nl · waveshare.com · Amazon.de | 3 | 45–70 | 135–210 |
| 2 | Controller | **Adafruit MatrixPortal S3** (#5778) | eckstein-shop.de (~27 ✔) · kiwi-electronics.com · Adafruit | 1 | 27–35 | 27–35 |
| 3 | Netzteil | **Meanwell LRS-150-5** (5V/30A); Reserve LRS-200-5 (40A) | reichelt.de · conrad.be · tme.eu | 1 | 30–55 | 30–55 |
| 4 | Lichtsensor | **Adafruit VEML7700** (#4162, STEMMA QT) | kiwi-electronics.com · Adafruit | 1 | 6–10 | 6–10 |
| 5 | Strom-Kabel | AWG14–16 rot/schwarz + Aderendhülsen (Power-Injection je Panel) | lokal · Amazon.de | 1 Set | 10 | 10 |
| 6 | Sicherung | 5×20 mm Halter + 25 A Sicherung | Amazon.de · Conrad | 1 | 5 | 5 |
| 7 | HUB75-Flachband | 2×8 IDC (meist beigelegt), Ersatz | AliExpress · Amazon.de | 2 | 3 | 6 |
| 8 | Front | dunkel getöntes Acryl ~25–40 % (lasergeschnitten auf Maß) | snijlab.nl · lokaler Laser BXL | 1 | 25–45 | 25–45 |
| 9 | Rahmen | Eiche-Massivrahmen + schwarze Alu-Innenblende (CNC/Tischler) | lokal | 1 | 60–180 | 60–180 |
| 10 | Montage | French-Cleat/versteckte Halterung, Kabelkanal | Baumarkt | 1 Set | 20 | 20 |

**Summe (grob):** ~**330–580 €** (Showpiece-Ausführung; Rahmen/Front dominieren die Spanne).

## Hinweise
- Strombudget/Sicherheit & Power-Injection: [../docs/01-hardware.md](../docs/01-hardware.md).
- Konnektivität MVP = WLAN; Ethernet/PoE optional ([../docs/roadmap.md](../docs/roadmap.md)).
- Verkabelungs-Skizze später: `wiring-diagram.*`; Gehäuse-/Laserdateien: `enclosure/`.
