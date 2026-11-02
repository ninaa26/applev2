// Copy to node_config.h (gitignored) and fill in for this trap.
#pragma once

// From the dashboard's Set up traps page; flash-camera.sh T2 <key> fills in these two.
#define TRAP_ID "T2"
#define API_KEY "paste-the-key-printed-by-add-trap"

// The hub Pi's access point and gateway (NetworkManager's shared mode gives the hub 10.42.0.1). With the radio
// below, Wi-Fi is only for the setup preview, near the hub.
#define WIFI_SSID "sentinel-hub"
#define WIFI_PASSWORD "change-me"
#define HUB_URL "http://10.42.0.1:8080"

// Camera. Pins: ESP32-S3-EYE / Freenove layout (found by the camera check, Oct 8 2026).
#define CAM_PIN_XCLK 15
#define CAM_PIN_SIOD 4
#define CAM_PIN_SIOC 5
#define CAM_PIN_D7 16
#define CAM_PIN_D6 17
#define CAM_PIN_D5 18
#define CAM_PIN_D4 12
#define CAM_PIN_D3 10
#define CAM_PIN_D2 8
#define CAM_PIN_D1 9
#define CAM_PIN_D0 11
#define CAM_PIN_VSYNC 6
#define CAM_PIN_HREF 7
#define CAM_PIN_PCLK 13
#define CAM_FRAMESIZE FRAMESIZE_UXGA  // 1600x1200; FRAMESIZE_QXGA (2048x1536) on an OV3660 / OV5640
#define CAM_JPEG_QUALITY 8            // 0-63, lower is better
#define CAM_AEC_VALUE -1              // fixed exposure 0-1200, or -1 for auto
#define CAM_AGC_GAIN -1               // fixed gain 0-30, or -1 for auto
#define CAM_SETTLE_FRAMES 8           // frames thrown away while exposure settles

// Liner light: GPIO driving the LED MOSFET, or -1 for none.
#define LED_PIN -1
#define LED_SETTLE_MS 300

// Button that wakes the trap to mean "fresh liner installed" (GPIO0 is the BOOT button), or -1.
// Held for SETUP_HOLD_MS it also starts setup mode: a live preview before the photo.
#define BUTTON_PIN 0

// Setup mode (after power-on, or the button held): a live preview on the hub's Wi-Fi, for aiming the camera.
#define SETUP_PREVIEW_S 120               // how long the preview runs before the camera takes its photo
#define PREVIEW_FRAMESIZE FRAMESIZE_VGA   // preview size (640x480); the page's full-size photo uses CAM_FRAMESIZE
#define SETUP_HOLD_MS 3000

// The 900 MHz radio link instead of Wi-Fi, for a camera beyond the hub's Wi-Fi (docs/radio-range.md): uncomment
// HUB_LINK_RADIO and wire an SX1262 module (Waveshare Core1262-HF or Ebyte E22-900M22S) to these pins, 3.3 V and
// GND, with 100 uF across its supply. The pins avoid the camera (4-13, 15-18), the button (0) and PSRAM (35-37):
// check them against your board's pinout. The hub needs the radio bridge (device/esp32-radio-bridge).
// #define HUB_LINK_RADIO
#define RADIO_SCK 47
#define RADIO_MOSI 21
#define RADIO_MISO 14
#define RADIO_NSS 41
#define RADIO_BUSY 42
#define RADIO_DIO1 1
#define RADIO_RESET 3
#define RADIO_RXEN -1   // -1: the module's DIO2 drives its RF switch; else the GPIOs wired to its RXEN and TXEN
#define RADIO_TXEN -1
#define SETUP_WIFI_S 20  // with the radio, setup mode gives up on Wi-Fi sooner (the preview needs it)
