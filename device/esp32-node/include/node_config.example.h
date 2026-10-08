// Copy to node_config.h (gitignored) and fill in for this trap.
#pragma once

// From `sentinel-server add-trap T2 ...`; the same id and key go in the hub's [hub.nodes.T2].
#define TRAP_ID "T2"
#define API_KEY "paste-the-key-printed-by-add-trap"

// The hub Pi's access point and gateway (NetworkManager's shared mode gives the hub 10.42.0.1).
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
#define BUTTON_PIN 0
