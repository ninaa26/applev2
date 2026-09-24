# Bring-up: from a blank Pi 5 to photos on the dashboard

Do the server steps in [server-on-mac.md](server-on-mac.md) first, so there is somewhere to upload to.

## 1. Flash and first boot

1. Raspberry Pi Imager → **Raspberry Pi OS Lite (64-bit)**. In the settings: hostname `sentinel-t1`, your SSH public key, and the Wi-Fi network.
2. Boot, then `ssh pi@sentinel-t1.local` (or whatever user you set).
3. `sudo apt update && sudo apt full-upgrade -y && sudo reboot`
4. Camera check: `rpicam-still -o test.jpg --width 2304 --height 1296`. Copy `test.jpg` back and look at it.

## 2. Tailscale (lets the Pi reach the Mac from any network)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Log in with the team's Tailscale account. `tailscale status` should list the Mac.

## 3. Install the trap software

```bash
git clone <your repo URL> sentinel && cd sentinel/device
sudo ./install.sh
```

On the Mac, create the trap and copy the key it prints:

```bash
sentinel-server add-trap T1 --lure CM --name "Bench mockup"
```

Edit `/etc/sentinel/config.toml` on the Pi: `trap_id`, `api_key`, and `server_url = "http://<mac's tailscale name>:8000"`.
For bench work, set `halt_after_cycle = false` and `manual_wake_is_new_card = false`.

## 4. Bench cycle

```bash
sudo -u sentinel /opt/sentinel/venv/bin/sentinel-cycle --config /etc/sentinel/config.toml --no-halt -v
```

The photo should appear on the dashboard within a few seconds. If the Mac is off, the photo waits in `/var/lib/sentinel/queue/` and goes up on the next run.

## 5. Tune the camera once, in the (mockup) trap

1. Put a liner with a few specimens (or the printed checkerboard) in the tray.
2. Focus: `sudo -u sentinel /opt/sentinel/venv/bin/sentinel-focus-sweep --config /etc/sentinel/config.toml --out /tmp/focus`. Set `lens_position` to the best value it prints.
3. Exposure: with the LEDs on, adjust `exposure_us` until the liner is bright but not blown out (grid lines still visible), and keep `analogue_gain` at 1.0 if possible.
4. White balance: adjust `colour_gains` until a white liner looks neutral. These values stay fixed for good; the model relies on every photo looking the same.
5. Lens calibration: photograph `hardware/print/checkerboard.png` flat on the tray at ~10 positions/angles and keep the photos for the calibration script.

**USB webcam instead:** webcams have no manual exposure, and their auto-exposure clips the red
channel under an orange trap roof. Set `usb_controls` in `[camera]` (names from
`v4l2-ctl -d /dev/video0 --list-ctrls`); the Alcor Micro webcam in the orange Pherocon VI works with
`{ brightness = -40, saturation = 30, backlight_compensation = 0 }`. The capture also lowers
`brightness` by itself while more than `usb_max_clip_frac` of any channel is saturated, and reports
`brightness`/`clipped_frac` in the photo's metadata.

**Check detection on the bench** (on the Mac): copy a few photos over and run
`.venv/bin/sentinel-server detect photo1.jpg photo2.jpg --out overlays/`. It prints how many insects
it found and the grid it measured (spacing in px, angle, px/mm), and saves copies with boxes drawn.
Measure your liner's grid spacing once with a ruler and set `SENTINEL_GRID_MM` in `.env`: the
detector uses it to turn pixels into millimetres (it ignores anything under 3 mm or over 30 mm).
If the lure isn't in the photo, clear the default lure mask: `sentinel-server set-mask T1 --none`.
With a wide or fisheye lens the grid lines bend; the detector straightens the photo first (it tries
lens corrections until the grid lines are straightest, once per liner) and prints the `lens k` it used:
0 for a normal lens, around −0.2 for the wide lens we tried. If it guesses wrong on a nearly empty
or very crowded liner, fix it with `SENTINEL_LENS_K=-0.2` in `.env` (or try values with `detect --lens`).

## 6. Field mode

```bash
sudo rpi-eeprom-config --edit     # POWER_OFF_ON_HALT=1, WAKE_ON_GPIO=0, PSU_MAX_CURRENT=5000
sudo systemctl enable sentinel-cycle
```

In the config: `halt_after_cycle = true`, `manual_wake_is_new_card = true`. From then on, every boot runs one cycle and powers off until the next scheduled time. **After swapping a liner, press the Pi's power button**: the trap wakes, takes a baseline photo, and the server starts a new liner. The dashboard's "New liner installed" button does the same thing.

To stop the cycle and work on the Pi, SSH in during a wake and run `sudo systemctl disable sentinel-cycle`, or set `halt_after_cycle = false` from the server (next section).

## Changing settings remotely

The server sends `device_config` for the trap in every upload reply (schedule, camera, LED). For now, edit it in the database or a Python shell. A settings page on the dashboard is a later task.
