# Enclosure

A slim wooden frame (~45 mm deep) with a smoked acrylic front across the full inner width, a
removable back and a separate box for the mains supply. Nothing but wood and glass is visible
from the front: the speaker fires downwards and the fan breathes through slots in the top and
bottom rail.

## Dimensions

| | Value |
|---|---|
| Panel field | 770 × 258 mm (768 × 256 + 1 mm tolerance per side), centred |
| Frame | solid wood 18 mm, 45 mm deep, mitred with splines, 18 mm visible rim |
| Outer size | **W** × 294 × 45 mm, default W = 875 mm |
| Side zones | (W − 806) / 2 per side behind the glass, 34.5 mm at W = 875, blacked out |
| Acrylic | (W − 26) × 268 × 3 mm, in a 3.5 × 5.5 mm groove 3 mm behind the front face, all round |
| Back panel | (W − 24) × 270 × 3 mm (black HDF or aluminium composite) in a 6 × 4 mm rebate |

Measure W on site; everything else stays fixed.

## Cut list (one board 1000 × 300 × 18 mm)

Rip three 45 mm strips and one narrow strip for the blocks.

| Part | Qty | Size (mm) | Notes |
|---|---|---|---|
| Top rail | 1 | W × 45 × 18 | mitred; groove; 4 exhaust slots 3 × 25 in the fan-side zone |
| Bottom rail | 1 | W × 45 × 18 | mitred; groove; 6 speaker slots 3 × 25 on one side, 4 intake slots on the other |
| End piece | 2 | 294 × 45 × 18 | mitred; groove; flush keyhole hanger in the back edge; cable hole Ø 12 in one |
| Carrier block | 4 | ~30 × 20 × 18 | glued inside the end pieces, carry the panel bars |
| Side mask | 2 | 256 × 34 × 3 | black HDF right behind the glass; cut-out for the speaker, Ø 8 hole for the light sensor |

The acrylic is captive in the groove once the frame is glued; panels and electronics stay
serviceable from the back.

## Inside

```
front ─ acrylic (3–6 mm) ─ panels (≈6.5–21.5 mm) ─ MatrixPortal on panel 1 (≈ up to 37 mm) ─ back (41–45 mm)
```

- **Panel carrier:** two aluminium flat bars 20 × 3 mm, W − 36 mm long, screwed to the panels'
  M3 inserts and to the carrier blocks. The panels press the acrylic into its groove; the back
  panel carries no load.
- **Side zones** (~34 × 35 mm, behind the black masks): speaker (≤ 30 mm, sealed back) lying
  flat and firing down through the bottom-rail slots on one side; light sensor pressed against
  the glass, temperature sensor and a 30 mm fan on the other side. Set **Front panel light
  transmission** to the acrylic's value so the sensor reading is corrected.
- **Power:** the 2 × 4 mm² trunk enters through one end piece to a distribution block; diode
  branch to the controller as described in [`hardware.md`](hardware.md#powering-the-controller).
- **Back panel:** held by magnets or turn buttons; cut out a 40 × 25 mm window over the
  controller's USB-C socket for service access.

Check the panel and controller height before cutting: if the controller sticks out more than
37 mm from the acrylic face, make the frame 50 mm deep.

## Mounting

Two flush-routed keyhole hangers in the back edges of the end pieces keep the board tight to
the wall without adding depth. Any adjacent door or cabinet front needs ≥ 55 mm clearance from
the wall (board depth plus margin) or an opening limiter.

## Supply box

The LRS-150-5 has open mains terminals. Mount it in a closed plastic junction box
(≈ 220 × 170 × 80 mm, M20 cable glands, earth connected) together with an optional Wi-Fi relay
for a remote hard power cycle. Have the 230 V side installed by an electrician.
