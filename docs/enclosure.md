# Enclosure

A slim wooden frame (~45 mm deep) with a smoked acrylic front, slotted side grilles for the
speaker and the sensors, a removable back and a separate box for the mains supply.

## Dimensions

| | Value |
|---|---|
| Panel field / front opening | 770 × 258 mm (768 × 256 + 1 mm tolerance per side) |
| Frame | solid wood 18 mm, 45 mm deep, mitred with splines, 18 mm visible rim |
| Outer size | **W** × 294 × 45 mm, default W = 875 mm |
| Side grille width | (W − 806) / 2 per side, 34.5 mm at W = 875 |
| Acrylic | 780 × 268 × 3 mm, in a 3.5 × 5.5 mm groove 3 mm behind the front face |
| Back panel | 851 × 270 × 3 mm (black HDF or aluminium composite) in a 6 × 4 mm rebate |

Measure W on site; everything else stays fixed.

## Cut list (one board 1000 × 300 × 18 mm)

Rip three 45 mm strips and one 75 mm strip.

| Part | Qty | Size (mm) | Notes |
|---|---|---|---|
| Top / bottom rail | 2 | W × 45 × 18 | mitred; groove for acrylic; vent slots in the grille zones |
| End piece | 2 | 294 × 45 × 18 | mitred; flush keyhole hanger in the back edge; cable hole Ø 12 in one |
| Side grille | 2 | 258 × grille width × 10 | planed from 18 mm; three 3 × 220 mm slots; acrylic groove on the inner edge |

## Inside

```
front ─ acrylic (3–6 mm) ─ panels (≈6.5–21.5 mm) ─ MatrixPortal on panel 1 (≈ up to 37 mm) ─ back (41–45 mm)
```

- **Panel carrier:** two aluminium flat bars 20 × 3 mm, W − 36 mm long, screwed to the panels'
  M3 inserts and to small blocks glued inside the end pieces. The panels press the acrylic into
  its groove; the back panel carries no load.
- **Side compartments** (behind the grilles, ~31 mm deep): speaker (≤ 30 mm, front-firing,
  sealed back) on one side; light sensor behind a Ø 3 mm hole, temperature sensor and a 30 mm
  fan on the other side.
- **Airflow:** four 3 × 25 mm slots in the bottom rail (intake) and in the top rail (exhaust),
  only in the grille zones so they are invisible from the front.
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
