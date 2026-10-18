# Hardware

## Overview

| Component | Specification |
|---|---|
| Display | 3 × 64×64 RGB HUB75 panels, 4 mm pitch (P4), 1/32 scan → 192×64 px, 768 × 256 mm |
| Controller | Adafruit MatrixPortal S3 (ESP32-S3, 8 MB flash, 2 MB PSRAM) |
| Power | 5 V / 30 A supply (e.g. Mean Well LRS-150-5) with a 25 A inline fuse |
| Optional | VEML7700 ambient light sensor, smoked acrylic front panel |

Bill of materials: [`hardware/bom.csv`](../hardware/bom.csv)

## Panels and data chain

- Chain the panels with the supplied ribbon cables: controller → panel 1 **IN**, panel 1 **OUT** →
  panel 2 **IN**, and so on. Panel 1 is the left-most panel seen from the front.
- 64×64 panels need address line E. On the MatrixPortal S3 the solder jumper must connect the
  centre pad to **8** (factory default on recent boards). Most panels use pin 8; a few use 16.
- Wrong chain direction or a missing E line is harmless: the image is blank, mirrored or doubled.

## Power

- Adjust the supply to **5.0–5.1 V** without load before connecting panels.
- Wire **one red/black pair per panel** directly from the supply (star wiring, 14–12 AWG).
- Put the **inline fuse** (25 A with 12 AWG, 20 A with 14 AWG) on the +5 V line right after the supply.
- Connect protective earth and keep the mains terminals covered.
- Worst case (full white) is ~24 A; at typical brightness the board draws 3–8 A.

### Powering the controller

Power the MatrixPortal **through USB-C** (phone charger or a USB-C pigtail from the 5 V supply).
Do **not** feed 5 V into its screw terminals: they are wired directly to USB VBUS and are meant
as an output. Feeding them and plugging in a computer at the same time can damage the board or
the computer (Adafruit documentation). Ground is shared through the HUB75 ribbon.

## Ambient light sensor (optional)

Plug a VEML7700 into the **STEMMA QT / I²C** socket next to the USB-C connector (SDA GPIO16,
SCL GPIO17). Mount it at the edge, facing the room and away from the LEDs, otherwise it measures
its own light. Behind a tinted front set **Front panel light transmission** (e.g. 21 %) in the
settings so brightness is computed from the real room light.

## Front panel (optional)

Glossy smoked grey cast acrylic, 3 mm, ~20–25 % transmission (e.g. PLEXIGLAS GS 7C83) gives deep
blacks and hides the PCB while keeping pixels crisp. Avoid frosted/diffusing grades for a 4 mm
pitch — they blur the dot-matrix look.

## Bring-up test

`esphome/perron-smoketest.yaml` draws a frame, a large panel number and RGB blocks on each panel.
Flash it with one panel first, then two, then three (`layout_cols`) to verify the chain order,
colour channels and the E line before installing the full firmware.
