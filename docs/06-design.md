# 06 — Design, Gehäuse & Montage

## Kontext (Penthouse-Ästhetik)
Weiße Wände · Eiche-Massivholz-Mobiliar · Ceppo-Grey-Marmorboden (schwarz meliert). Anspruch: **edel & schön**,
„fügt sich ein" — aber **Haltestellen-Charakter ausdrücklich erwünscht** (der Gag).

## Konzept „Eiche-gerahmte Abfahrtstafel"
- **Eiche-Massivrahmen** (bindet visuell an das Mobiliar).
- **Dunkel getönte Glas-/Acrylfront** (~25–40 % Transmission) vor den Panels:
  - **Aus:** ruhige schwarze Fläche im Eichenrahmen = Designobjekt.
  - **An:** RGB-Dots glühen durch → Abfahrtstafel.
  - Tönung = tiefe Schwarzwerte (Off-Pixel bleiben schwarz) → genau das „edel".
- Schwarz greift die dunkle Maserung des Ceppo-Grey-Marmors auf; weiße Wand stellt das Objekt frei.
- **Alternative Blende:** schwarz eloxiertes Alu (puristischer „Station"-Look).

## Maße & Aufbau
- Sichtfläche ~**76,8 × 25,6 cm** (192×64 @ P4); zentriert über der 88-cm-Tür, schwebend.
- Aufbau (vorne→hinten): getönte Front · schmaler Abstandshalter (Panel-Tiefe/Belüftung) · 3 Panels auf
  Trägerplatte · MatrixPortal + Verkabelung · Rückwand · Wandhalterung.
- **Front-Abstand**: ein paar mm Luft vor den LEDs verbessert Diffusion/Look; im Smoke-Test testen.

## Montage
- **French-Cleat** oder versteckte VESA-artige Halterung über der Tür (tragfähig in Massivwand).
- **Kabel unsichtbar**: Kanal in/hinter die Wand zur nächsten Steckdose; **PSU gekapselt** im Deckenhohlraum
  oder Schrank (nicht im Display-Gehäuse, falls Wärme/Platz kritisch — im Smoke-Test entscheiden).
- Belüftung: Panels + PSU erzeugen Wärme; Rückwand mit dezenten Lüftungsschlitzen.

## Fertigung
- **Front/Blende:** Lasercut (snijlab.nl o. lokaler Laser in BXL) auf exakte Sichtfläche + Schraubdome.
- **Eiche-Rahmen:** Tischler oder CNC-Service; Gehrung, Falz für Front + Panelträger.
- **Trägerplatte/Rückwand:** Aluminium- oder Multiplexplatte; 3D-Druck für Halter/Abstandshalter.
- CAD-/Laser-Dateien später unter [../hardware/enclosure/](../hardware/enclosure/).

## Adaptive Anzeige (Design-relevant)
- **VEML7700-Lichtsensor** → Helligkeit folgt Raumlicht (tags hell, nachts gedimmt).
- **Präsenz Diele** (HA) → bei Abwesenheit dimmen/blank (Stromsparen, dezenter nachts).
- **Tageszeit-Modi** → morgens Pendel-Fokus, abends/nachts ruhiger. Siehe [02-architecture.md](02-architecture.md).
