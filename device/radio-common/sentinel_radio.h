// The 900 MHz radio link between an ESP32 camera and its hub: radio settings and frame layout, shared by the
// camera firmware (esp32-node) and the hub's radio bridge (esp32-radio-bridge). The Pi side is
// sentinel_device/radio_link.py, which must match (RADIO_VERSION, the frame types and CHUNK).
//
// The camera's hub requests (POST /node/v1/captures, GET /node/v1/schedule, POST /node/v1/pair,
// GET /node/v1/firmware) go over the radio unchanged: the camera sends the request in numbered chunks, the
// Pi replays it to the gateway on localhost, and the camera pulls the reply back in chunks. The camera
// always speaks first; the hub only answers.
//
// Every frame starts with a 6-byte header: [version << 4 | type] [node: 4 bytes] [xfer: 1 byte].
// node is the camera's radio address (the last 4 bytes of its MAC), xfer counts its requests. Multi-byte
// fields are little-endian. Chunks hold CHUNK bytes; windows are 32 chunks (one bit each in a u32).
//
//   1 REQ_DATA   camera -> hub  seq u16, total u32, flags u8 (bit 0: last of a window, answer with REQ_ACK), data
//   2 REQ_ACK    hub -> camera  base u16, have u32 (bit i: chunk base+i is here), flags u8 (bit 0: all here), rssi i8
//   3 POLL       camera -> hub  (nothing): is the reply ready?
//   4 RESP_INFO  hub -> camera  state u8 (0 working, 1 ready, 2 no such request), status u16, total u32, rssi i8
//   5 PULL       camera -> hub  base u16, want u32: send these chunks of the reply
//   6 RESP_DATA  hub -> camera  seq u16, data
//   7 DONE       camera -> hub  (nothing): reply received, forget the request
//
// The request is [head length u16][head: JSON {"m": method, "p": path, "a": API key, "x": X-Sentinel-Meta,
// "t": Content-Type}][body]. The reply is the gateway's body; its HTTP status comes in RESP_INFO.
#pragma once
#include <stdint.h>
#include <stddef.h>

#define RADIO_VERSION 1

// Radio settings: both ends must match. 250 kbps 2-GFSK with 125 kHz deviation in the 467 kHz receive
// filter, the SX1262's -104 dBm setting (docs/radio-range.md). Override any of them with -D in platformio.ini.
#ifndef RADIO_FREQ_MHZ
#define RADIO_FREQ_MHZ 915.0
#endif
#ifndef RADIO_BITRATE_KBPS
#define RADIO_BITRATE_KBPS 250.0
#endif
#ifndef RADIO_DEVIATION_KHZ
#define RADIO_DEVIATION_KHZ 125.0
#endif
#ifndef RADIO_RX_BW_KHZ
#define RADIO_RX_BW_KHZ 467.0
#endif
#ifndef RADIO_POWER_DBM
#define RADIO_POWER_DBM 22  // the SX1262's most; the Core1262 and E22-900M22S take it
#endif
#ifndef RADIO_PREAMBLE_BITS
#define RADIO_PREAMBLE_BITS 32
#endif
#ifndef RADIO_TCXO_V
#define RADIO_TCXO_V 1.8  // the Core1262's TCXO on DIO3; 0 for a module with a plain crystal
#endif
#ifndef RADIO_NET
#define RADIO_NET 0x01  // the last sync-word byte: give hubs within reach of each other different ones
#endif

// The sync word marks our frames, so other 915 MHz traffic is never even received.
static const uint8_t RADIO_SYNC[4] = {0x53, 0x4E, 0x54, RADIO_NET};  // "SNT" + network

enum RadioType : uint8_t {
  REQ_DATA = 1, REQ_ACK = 2, POLL = 3, RESP_INFO = 4, PULL = 5, RESP_DATA = 6, DONE = 7,
};

static const size_t RADIO_HEADER = 6;
static const size_t CHUNK = 240;       // data bytes per chunk: a REQ_DATA frame is 6 + 7 + 240 = 253 bytes
static const size_t WINDOW = 32;       // chunks per window
static const size_t MAX_FRAME = 255;   // the SX1262's FSK packet limit

static const uint8_t FLAG_ACK_PLEASE = 1;  // REQ_DATA: last frame of a window
static const uint8_t FLAG_ALL_HERE = 1;    // REQ_ACK: the whole request has arrived

static const uint8_t STATE_WORKING = 0, STATE_READY = 1, STATE_UNKNOWN = 2;

static inline void radioPut16(uint8_t *p, uint16_t v) { p[0] = v; p[1] = v >> 8; }
static inline void radioPut32(uint8_t *p, uint32_t v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }
static inline uint16_t radioGet16(const uint8_t *p) { return p[0] | (uint16_t)p[1] << 8; }
static inline uint32_t radioGet32(const uint8_t *p) {
  return p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

// Fills the header; returns its length.
static inline size_t radioHeader(uint8_t *f, uint8_t type, uint32_t node, uint8_t xfer) {
  f[0] = (RADIO_VERSION << 4) | type;
  radioPut32(f + 1, node);
  f[5] = xfer;
  return RADIO_HEADER;
}

// The bridge's USB serial to the Pi: SLIP-framed messages, each [kind][payload][CRC-16/CCITT-FALSE of both].
//   bridge -> Pi: 0x01 RX [rssi i8][radio frame], 0x02 LOG [text], 0x03 HELLO [RADIO_VERSION][text]
//   Pi -> bridge: 0x10 TX [radio frame]  (sent in order, a few ms apart, then back to listening)
enum SerialKind : uint8_t { SER_RX = 0x01, SER_LOG = 0x02, SER_HELLO = 0x03, SER_TX = 0x10 };
#ifndef BRIDGE_BAUD
#define BRIDGE_BAUD 460800
#endif
static const uint8_t SLIP_END = 0xC0, SLIP_ESC = 0xDB, SLIP_ESC_END = 0xDC, SLIP_ESC_ESC = 0xDD;

static inline uint16_t radioCrc16(const uint8_t *p, size_t n) {
  uint16_t crc = 0xFFFF;
  while (n--) {
    crc ^= (uint16_t)*p++ << 8;
    for (int i = 0; i < 8; i++) crc = crc & 0x8000 ? (crc << 1) ^ 0x1021 : crc << 1;
  }
  return crc;
}
