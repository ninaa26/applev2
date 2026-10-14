# Hardware files

The trap is the **Alpha Scents red plastic delta trap** with its 174 × 198 mm insert card (25 mm grid).
Measured dimensions, the schematic and what they mean for the camera: [TRAP.md](TRAP.md).

| File | What it is | Status |
|---|---|---|
| `TRAP.md`, `trap_schematic.svg` | Measured trap and card dimensions, end/side/top schematic | Measured |
| `CAMERAS.md` | The trap camera now in use (Arducam UC-572, wide-angle IMX219), its calibrated settings and bench results, and the ESP32 camera boards | IMX219 calibrated on the bench Pi (Oct 6 2026) |
| `mockup_template.py` → `mockup_template.svg` | 1:1 cut-and-fold template for a mockup delta trap (roof panels, floor, end flaps, cable slot, LED holes, liner + lure outline), plus a check that the camera sees the whole liner at your dimensions | Works; defaults are the measured Alpha Scents trap |
| `HOUSING.md`, `scad/trap_housing.scad`, `housing_*.svg` | Weatherproof camera head that retrofits onto the stock trap: sealed box (Pi 5, 1S4P 21700 battery cartridge), saddle + light bar clamped through one slot in the roof peak, LED strips, glass window, sun shade. `scad/export_housing.sh` exports the STLs; `housing_drawings.py` makes the dimensioned drawings | Designed Oct 14 2026; not yet printed |
| `scad/camera_mount.scad` | Wedge that sits in the roof apex and holds the Camera Module 3 Wide facing down | Not yet rendered or printed. Sized for the Camera Module 3, not the IMX219 board now in use ([CAMERAS.md](CAMERAS.md)). **Too low for this trap** (sees ~113 of the card's 174 mm across). Superseded by `trap_housing.scad` |
| `scad/liner_tray.scad` | Slide-in tray so every liner lands in the same spot, with pockets for the ArUco markers and a lure seat | Not yet rendered or printed. At the card's size it's wider than the 195 mm floor; shrink the rim/markers first |
| `make_markers.py` → `print/checkerboard.png`, `print/tray_markers.png` | Lens-calibration checkerboard and the four tray-corner ArUco markers (300 dpi) | Works; detection verified with OpenCV |

## Build the mockup

```bash
python mockup_template.py -o mockup_template.svg     # Alpha Scents defaults; --floor-width/--length/--flap/--apex/--liner for another trap
```

1. Print at **100 %** and check the 50 mm scale bar with a ruler.
2. Cut from corrugated plastic (the same material as a real delta trap) or foam board. Score the green dashed lines and fold.
3. Open the `.scad` files in OpenSCAD (free), set `floor_w`/`apex` (mount) and `liner_w`/`liner_l` (tray) to your numbers, press F6, and export STL.
4. Print the markers at 100 %, cut them out, and glue them into the tray pockets: id 0 top-left, 1 top-right, 2 bottom-right, 3 bottom-left, with the camera cable end at the top.
5. After changing the camera height, re-run `mockup_template.py` with the new `--cam-drop` to confirm the liner is still fully in view.

Wiring for the whole unit is in [../docs/wiring.md](../docs/wiring.md).
