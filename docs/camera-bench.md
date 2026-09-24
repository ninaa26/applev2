# Picking a camera: the bench test

Every candidate camera photographs the same printed checkerboard from the same height, and
`sentinel-camera-bench` turns each photo into numbers we can compare side by side.

## Setup (once)

1. Print `hardware/print/checkerboard.png` at **100 %**. Check one square: it must be 12.0 mm.
   Tape it flat to something stiff.
2. Mark the trap height: lens **150 mm** above the card (the planned apex mount). Use a stack
   of books, a clamp or the mockup trap. Keep that height the same for every camera.
3. Lighting: use the same light for every camera, ideally the trap LEDs, and otherwise one
   lamp. Avoid glare on the paper.

## Shots per camera

| Tag | What | Why |
|---|---|---|
| `centre` | Board in the middle of the frame | Detail, focus, noise |
| `corner` | Board pushed into one corner (entirely in frame) | Lens softness at the edges, where half the liner is |
| `dim` | Lamp off / LEDs at the lowest setting | Dusk shot quality |

Also take one photo of a real moth or a staged liner with each camera, for a look by eye.

## Commands

Webcam on a Mac (the first run asks for Camera permission for your terminal app; allow it
and run again. Index 0 or 1 selects the camera; `system_profiler SPCameraDataType` lists them):

```bash
cd device
uv run --with-editable '.[bench]' sentinel-camera-bench shoot --camera brio101 --backend usb --device 1 --out ../camera_bench
```

On the Pi (webcam on `/dev/video0`, or a Pi camera module):

```bash
sentinel-camera-bench shoot --camera cm3wide --backend picamera2 --out ~/camera_bench
```

Any other camera (phone, a camera with its own app): take the photo there, then score it:

```bash
uv run --with-editable '.[bench]' sentinel-camera-bench score --camera phone --tag centre --image ~/Downloads/IMG_0412.jpg --out ../camera_bench
```

Collect all the `camera_bench/<camera>/` folders on one machine and print the table:

```bash
uv run --with-editable '.[bench]' sentinel-camera-bench compare --out ../camera_bench
```

## Reading the table

| Column | Good | Meaning |
|---|---|---|
| px/mm | ≥ 8 | Nominal detail on the card |
| OFM px | ≥ 50 | Pixels along a 6 mm oriental fruit moth, the smallest target. Below ~30 the classifier is guessing from a blob |
| edge blur mm | ≤ 0.25 | Real sharpness after focus, lens and compression. Much bigger than 1/(px/mm) means the camera is out of focus at 150 mm (common for fixed-focus webcams) or over-compressed |
| contrast/noise | ≥ 30 | Image quality; compare `dim` shots for dusk performance |
| FOV mm / liner fits | fits | Whether the whole liner is in view at this height (`--liner WxL` to change the size) |
| fps | — | Webcams only; not important for stills |

Choose on edge blur and OFM px from the `centre` and `corner` shots first, then on the `dim`
contrast/noise. Resolution on the box counts only if the edge blur says the camera uses it.
