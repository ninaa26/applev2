# Cameras

The camera looks down from the top middle of the trap, lens about 110 mm above the
174 × 198 mm card ([TRAP.md](TRAP.md)).

## Current trap camera: Arducam UC-572 (IMX219, wide-angle)

8 MP (3280 × 2464, 4:3), Raspberry Pi camera port (`imx219` driver), fisheye M12 lens, no focus
motor. From the peak of the trap it sees the whole card. Read off a preview of the card's 25 mm
grid: roughly 15 px/mm in the centre and 10–11 px/mm at the edges (not yet bench-tested).

- Focus by turning the lens by hand; `lens_position` is ignored.
- `lens_shading = false` and a white-card calibration (`sentinel-flatfield`) remove the green
  centre and pink edges the Pi's stock IMX219 colour correction gives with this lens.
- Light the card with the white LEDs and block daylight: through the red roof the photo is all red.
- Calibrated on the bench on 2026-10-06 (red trap, bench LED): `exposure_us = 40000`,
  `analogue_gain = 2.0`, `colour_gains = [0.89, 1.76]`; after `sentinel-flatfield` the card is
  an even neutral grey edge to edge. The LED leaves a blown-out glare patch on the card; diffuse
  it or aim it off the card. The saved correction (`flatfield.npz`) stays on the Pi it was made on.
- With seven pinned specimens on the liner (same day, `ml/data/trap_camera/capture_bugs_2026-10-06/`):
  wing patterns are visible even on a moth in the corner; the detector finds every specimen and
  ignores their shadows, but splits the large ones into several boxes, still boxes the trap walls
  outside the card, and estimates a different lens k (−0.10) than on the empty liner. The single
  LED casts long red shadows; diffuse light from two sides would shorten them. The trap had been
  moved since the white-card calibration and the correction no longer lined up (faint green and
  pink patches): recalibrate whenever the camera or trap is moved.
- Steps: [docs/bring-up.md](../docs/bring-up.md), section 5.

## Also on hand

| Camera | What it is | In this trap |
|---|---|---|
| icspring USB camera | 640 × 480 UVC webcam | ~2.6 px/mm over the whole card (OFM ≈ 16 px). Software development only |
| Arducam UC-261 Rev D | 5 MP OV5647, Pi camera port, swappable M12 lens | Backup: ~10 px/mm with a ~1.7 mm lens for a 1/4" sensor |
| Pi camera in a clear acrylic holder | Normal-angle lens; sensor not identified yet (`rpicam-hello --list-cameras`) | Too narrow at the peak; worth identifying in case it is a 16 MP Arducam |
| Arducam UC-626 Rev B | 8 MP IMX219 USB, two microphones, fixed ~62° × 49° lens (looks scratched) | Too narrow at the peak |
| ArduCAM Mini UC-474 | 2 or 5 MP, SPI | No: not a camera-port device |
| OV7670/OV7725 board; OmniVision module on a UC-260 adapter | Parallel-pin microcontroller cameras | No |

## What a trap camera needs

| | Need |
|---|---|
| Field of view | ≥ 80° on the sensor's short side, ≥ 87° on the long side (lens at 110 mm) |
| Detail | ≥ 15 px/mm on the card, corners included (OFM ≈ 90 px); ≥ 20 px/mm for look-alikes |
| Sensor | ≥ 12 MP, 4:3, normal IR-cut (not NoIR), Pi 5 CSI/libcamera support |
| Lens and focus | Low distortion, rated for the sensor; sharp at 10–11 cm and locked |

## Upgrade if the edges or look-alikes need more: Raspberry Pi HQ Camera (M12) + Arducam LN069 lens

- Camera: Raspberry Pi HQ Camera, **M12-mount** version (SC0870, IMX477, 12.3 MP, 4:3), ~$50 at
  [PiShop.us](https://www.pishop.us/product/raspberry-pi-hq-camera-m12/) or
  [CanaKit](https://www.canakit.com/raspberry-pi-hq-camera-m12.html). No lens included.
- Lens: [Arducam LN069](https://www.arducam.com/arducam-100-degree-low-distortion-1-2-3-inch-m12-lens-with-lens-adapter-for-raspberry-pi-high-quality-camera-ln069.html)
  (M23270H10): 2.7 mm f/2.8, 100° × 83°, distortion < 1.5 %. From 110 mm it sees ~262 × 195 mm,
  the whole card, at ~15.5 px/mm (OFM ≈ 93 px). Rated minimum focus is 0.3 m: check it focuses at
  11 cm (screw the lens out further, or add a spacer) as soon as it arrives.
- Also: a Pi 5 camera cable (22-pin to 15-pin) long enough to reach from the peak to the Pi.
- Software: nothing to add; `camera.py` handles fixed-focus cameras. Manual focus, so set it once
  and lock the lens, then redo `sentinel-flatfield`.

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
