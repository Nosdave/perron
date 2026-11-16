# Hardware

## Overview

| Component | Specification |
|---|---|
| Display | 3 × 64×64 RGB HUB75 panels, 4 mm pitch (P4), 1/32 scan → 192×64 px, 768 × 256 mm |
| Controller | Adafruit MatrixPortal S3 (ESP32-S3, 8 MB flash, 2 MB PSRAM) |
| Power | 5 V supply (e.g. Mean Well LRS-150-5, 22 A) with a 20 A inline fuse |
| Optional | VEML7700 ambient light sensor, smoked acrylic front panel |

Bill of materials: [`hardware/bom.csv`](../hardware/bom.csv)

## Panels and data chain

- Chain the panels with the supplied ribbon cables: controller → panel 1 **IN**, panel 1 **OUT** →
  panel 2 **IN**, and so on. Panel 1 is the left-most panel seen from the front.
- 64×64 panels need address line E. On the MatrixPortal S3 the solder jumper must connect the
  centre pad to **8** (factory default on recent boards). Most panels use pin 8; a few use 16.
- Wrong chain direction or a missing E line is harmless: the image is blank, mirrored or doubled.

## Power

- Adjust the supply to **5.1–5.2 V** without load before connecting panels (compensates the drop
  on the feed cable).
- Run a **2 × 4 mm² trunk** with a **20 A inline fuse** right after the supply to a distribution
  block inside the case, then **one red/black pair per panel** from there (star wiring).
- Keep the mains terminals inside a closed box and connect protective earth. A Wi-Fi relay in
  that box (e.g. Shelly) gives Home Assistant a hard power cycle.
- Full white would draw ~24 A, more than the LRS-150-5 delivers. Real content at normal
  brightness draws 3–8 A; keep the configured maximum brightness reasonable.

### Powering the controller

The MatrixPortal's **+5V screw terminal is wired directly to USB VBUS** (no diode, no switch).
Feed it from the supply **through a Schottky diode and a 2 A fuse**:

```
PSU +5V ─┬──────────────────────────────► panels (star wiring)
         ├──────────────────────────────► amplifier Vin
         └──[2 A fuse]──►|── MatrixPortal +5V terminal
                     1N5822 / SS34 (ring towards the MatrixPortal)
PSU GND ───── panels, amplifier, MatrixPortal GND terminal (common ground)
```

- The diode blocks USB VBUS: a computer plugged in for service powers only the controller and
  can never feed the panels or push current into the supply.
- 3 A rating, ~0.4 V drop: the controller gets ~4.7–4.8 V, plenty for its 3.3 V regulator.
  Typical draw is 0.3 A, up to ~1 A with case fans on the A0 socket.
- **Never connect the panels to the MatrixPortal terminals.** Power them from the supply only.
- With USB plugged in, the computer supplies the controller and its fans (5 V beats the 4.7 V
  behind the diode). USB ports deliver 0.5–0.9 A and shut down safely on overload.

Enclosure, wall mount and supply box: [`enclosure.md`](enclosure.md)

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
