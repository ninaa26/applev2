# ESP32 camera trap firmware

An ESP32-S3 camera board in a delta trap that sends its photos through the hub Pi. How it fits
together, the Wi-Fi setup and adding cameras on the dashboard: [docs/esp32-traps.md](../../docs/esp32-traps.md).

Each wake it photographs the liner and saves the photo to flash. It joins the hub's Wi-Fi, uploads
everything queued (`POST /node/v1/captures`), and asks when to wake next (`GET /node/v1/schedule`).
Then it deep-sleeps. Pressing the button wired to `BUTTON_PIN` (the BOOT button by default) wakes it
and marks the photo as a fresh liner.

## Build and flash

PlatformIO (`pip install platformio`, or the VS Code extension):

```bash
cd device/esp32-node
cp include/node_config.example.h include/node_config.h   # then fill it in; it is gitignored
pio run -t upload
pio device monitor                                        # 115200 baud
```

The board this was written for: a Freenove-style ESP32-S3 CAM (N8R8: 8 MB flash, 8 MB octal PSRAM,
CH343 USB serial, ESP32-S3-EYE camera pins) with an OV3660. On a Mac the CH343 garbles uploads above
115200 baud, which is why `upload_speed` is 115200 (about 20 s per flash). Other boards need their
camera pins in `node_config.h` and maybe `board_build.arduino.memory_type` in `platformio.ini`.

`partitions.csv` keeps one 2 MB app slot and gives the rest of the flash (5.9 MB) to the photo queue.

## Serial output

What a normal wake looks like (format, not a recorded run):

```
sentinel node T2 fw 0.1.0 wake=scheduled boots=14 synced=1
captured /q/00000014-3f9a0c2e71b4d580 1600x1200 142311 bytes
upload /q/00000014-3f9a0c2e71b4d580 -> 201
sleeping 12480 s
```

`ERROR camera not found`: the ribbon cable is loose or upside down, or the camera's pins differ from
`node_config.h`. `ERROR hub not reachable`: out of range, the wrong Wi-Fi password, or the hub was not
awake (it is awake for a few minutes after each scheduled time). `ERROR hub does not know this trap's
key`: the camera was removed on the dashboard, given a new key, or not added yet.
