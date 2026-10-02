# Cameras

The camera looks down from the top middle of the trap, lens about 110 mm above the
174 × 198 mm card ([TRAP.md](TRAP.md)).

## On hand

| Camera | Specs (webcam test site) | In this trap |
|---|---|---|
| icspring USB camera | 640 × 480 (0.31 MP, VGA, 4:3), 28 fps, UVC, no mic | ~2.6 px/mm across the card if it sees all of it; an oriental fruit moth ≈ 16 px |

Use it to build and test the software (capture, upload, detection, counting, the camera bench) and
to check lighting and framing. It can't tell the moths apart: 640 × 480 spread over the whole card
shows a moth as a small blob, with no wing pattern. Its lens field of view isn't recorded; find it
with `sentinel-camera-bench` (the `FOV mm` column).

## What a trap camera needs

| | Need |
|---|---|
| Field of view | ≥ 80° on the sensor's short side, ≥ 87° on the long side (lens at 110 mm) |
| Detail | ≥ 15 px/mm on the card, corners included (OFM ≈ 90 px); ≥ 20 px/mm for look-alikes |
| Sensor | ≥ 12 MP, 4:3, normal IR-cut (not NoIR), Pi 5 CSI/libcamera support |
| Lens and focus | Low distortion, rated for the sensor; sharp at 10–11 cm and locked |

## Choice: Raspberry Pi HQ Camera (M12) + Arducam LN069 lens

- Camera: Raspberry Pi HQ Camera, **M12-mount** version (SC0870, IMX477, 12.3 MP, 4:3), ~$50 at
  [PiShop.us](https://www.pishop.us/product/raspberry-pi-hq-camera-m12/) or
  [CanaKit](https://www.canakit.com/raspberry-pi-hq-camera-m12.html). No lens included.
- Lens: [Arducam LN069](https://www.arducam.com/arducam-100-degree-low-distortion-1-2-3-inch-m12-lens-with-lens-adapter-for-raspberry-pi-high-quality-camera-ln069.html)
  (M23270H10): 2.7 mm f/2.8, 100° × 83°, distortion < 1.5 %. From 110 mm it sees ~262 × 195 mm,
  the whole card, at ~15.5 px/mm (OFM ≈ 93 px). Rated minimum focus is 0.3 m: check it focuses at
  11 cm (screw the lens out further, or add a spacer) as soon as it arrives.
- Also: a Pi 5 camera cable (22-pin to 15-pin) long enough to reach from the peak to the Pi.
- Software: `camera.py` needs an HQ Camera config (it assumes `imx708_wide` today); manual focus,
  so set it once and lock the lens.

## Ruled out

| Camera | Why not |
|---|---|
| Camera Module 3 Wide | Works, with autofocus and existing code, but needs the lens 131–150 mm up (a housing above the peak) for ~13–15 px/mm. The fallback |
| Raspberry Pi AI Camera (IMX500) | Fixed 66° × 52° lens: needs the lens ~177 mm up. Its on-sensor models see a downscaled frame (~3–4 px/mm over the card), too coarse for species; detection runs on the server anyway |
| Arducam 64 MP Hawkeye | Needs ~160 mm; big photos and battery cost for detail the counting problems don't need |
| Ordinary USB webcams | Fixed focus far from 11 cm, exposure/white balance that can't be locked, heavy compression, narrow lenses, USB drop-outs |
| [Arducam 12 MP IMX477P USB 3.0](https://www.arducam.com/arducam-12mp-imx477p-usb-3-0-camera-with-m12-manual-focus-lens-without-enclosure.html) | Not ruled out: same sensor, takes the same lens, works on a Mac with the existing USB backend. Costs more, ~1.3 W, compressed frames, less control. The pick if we want USB |
| Two cameras (Pi 5 has two ports) | Trapview covers its card with 4 × 5 MP cameras. Only if the HQ Camera's corners are too soft |

## From the literature

Suto 2022, *Codling moth monitoring with camera-equipped automated traps: a review*
(Agriculture 12:1721): traps used 2–10 MP cameras (Trapview 4 × 5 MP, iSCOUT 10 MP, Pi Camera v2
8 MP). Counting codling moth worked at 640 × 480 (93.1 AP, Ding & Taylor 2016), so resolution
wasn't the limit; touching insects, look-alike moths, torn wings and too little training data were.
Those papers only separated codling moth from background, not three species, so our 15 px/mm target
stands. One photo a day is enough, and ~20 % count error is tolerable for forecasting.
