# Hardware files

| File | What it is | Status |
|---|---|---|
| `mockup_template.py` → `mockup_template.svg` | 1:1 cut-and-fold template for a mockup delta trap (roof panels, floor, cable slot, LED holes, liner + lure outline), plus a check that the camera sees the whole liner at your dimensions | Works; defaults are **stand-ins**: measure a real Pherocon VI and liner |
| `scad/camera_mount.scad` | Wedge that sits in the roof apex and holds the Camera Module 3 Wide facing down | Not yet rendered or printed; check the board's hole pattern against the official drawing |
| `scad/liner_tray.scad` | Slide-in tray so every liner lands in the same spot, with pockets for the ArUco markers and a lure seat | Not yet rendered or printed |
| `make_markers.py` → `print/checkerboard.png`, `print/tray_markers.png` | Lens-calibration checkerboard and the four tray-corner ArUco markers (300 dpi) | Works; detection verified with OpenCV |

## Build the mockup

```bash
python mockup_template.py --floor-width <mm> --length <mm> --apex <mm> --liner <W>x<L> -o mockup_template.svg
```

1. Print at **100 %** and check the 50 mm scale bar with a ruler.
2. Cut from corrugated plastic (the same material as a real delta trap) or foam board. Score the green dashed lines and fold.
3. Open the `.scad` files in OpenSCAD (free), set `floor_w`/`apex` (mount) and `liner_w`/`liner_l` (tray) to your numbers, press F6, and export STL.
4. Print the markers at 100 %, cut them out, and glue them into the tray pockets: id 0 top-left, 1 top-right, 2 bottom-right, 3 bottom-left, with the camera cable end at the top.
5. After changing the camera height, re-run `mockup_template.py` with the new `--cam-drop` to confirm the liner is still fully in view.

Wiring for the whole unit is in [../docs/wiring.md](../docs/wiring.md).
