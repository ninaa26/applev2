// The hub's radio: an ESP32 with an SX1262 (Waveshare Core1262-HF or Ebyte E22-900M22S) on the hub Pi's USB.
// A plain modem: every frame it hears goes to the Pi (sentinel-radio, sentinel_device/radio_link.py), and every
// frame the Pi gives it goes out on the air. All the protocol is on the Pi. See README.md.
#include <Arduino.h>
#include <RadioLib.h>
#include <SPI.h>
#include "sentinel_radio.h"
#include "sentinel_radio_phy.h"

// Pins: an ESP32 DevKit's VSPI by default; set others with -D in platformio.ini (env:esp32s3 does).
#ifndef RADIO_SCK
#define RADIO_SCK 18
#endif
#ifndef RADIO_MISO
#define RADIO_MISO 19
#endif
#ifndef RADIO_MOSI
#define RADIO_MOSI 23
#endif
#ifndef RADIO_NSS
#define RADIO_NSS 5
#endif
#ifndef RADIO_RESET
#define RADIO_RESET 27
#endif
#ifndef RADIO_BUSY
#define RADIO_BUSY 26
#endif
#ifndef RADIO_DIO1
#define RADIO_DIO1 25
#endif
#ifndef RADIO_RXEN
#define RADIO_RXEN -1  // -1: the module's DIO2 drives its RF switch
#endif
#ifndef RADIO_TXEN
#define RADIO_TXEN -1
#endif

#define BRIDGE_VERSION "0.1.0"
static const uint32_t TX_GAP_US = 2500;    // between frames sent back to back: the camera re-arms its receiver
static const uint32_t HELLO_EVERY_MS = 60000;
static const size_t TX_QUEUE = 40;         // frames: a whole window of reply chunks, and then some

#if CONFIG_IDF_TARGET_ESP32
SPIClass spi(VSPI);
#else
SPIClass spi(FSPI);
#endif
SX1262 radio = new Module(RADIO_NSS, RADIO_DIO1, RADIO_RESET, RADIO_BUSY, spi);
static volatile bool dio1 = false;
static void IRAM_ATTR onDio1() { dio1 = true; }

static uint8_t txq[TX_QUEUE][MAX_FRAME];
static uint8_t txlen[TX_QUEUE];
static size_t tx_head = 0, tx_count = 0;
static uint32_t heard = 0, sent = 0, dropped = 0;
static float tcxo = 0;

// ------------------------------------------------------------------ serial to the Pi

static void sendMessage(uint8_t kind, const uint8_t *p, size_t n, const uint8_t *p2 = nullptr, size_t n2 = 0) {
  uint8_t buf[2 + MAX_FRAME + 2];
  size_t len = 0;
  buf[len++] = kind;
  if (n) { memcpy(buf + len, p, n); len += n; }
  if (n2) { memcpy(buf + len, p2, n2); len += n2; }
  uint16_t crc = radioCrc16(buf, len);
  buf[len++] = crc; buf[len++] = crc >> 8;
  uint8_t out[2 * sizeof(buf) + 2];
  size_t o = 0;
  out[o++] = SLIP_END;
  for (size_t i = 0; i < len; i++) {
    if (buf[i] == SLIP_END) { out[o++] = SLIP_ESC; out[o++] = SLIP_ESC_END; }
    else if (buf[i] == SLIP_ESC) { out[o++] = SLIP_ESC; out[o++] = SLIP_ESC_ESC; }
    else out[o++] = buf[i];
  }
  out[o++] = SLIP_END;
  Serial.write(out, o);
}

static void logf(const char *fmt, ...) {
  char text[160];
  va_list ap;
  va_start(ap, fmt);
  int n = vsnprintf(text, sizeof(text), fmt, ap);
  va_end(ap);
  sendMessage(SER_LOG, (const uint8_t *)text, n < 0 ? 0 : std::min((size_t)n, sizeof(text) - 1));
}

static void hello() {
  char text[96];
  int n = snprintf(text, sizeof(text), "bridge %s, %.1f MHz %.0f kbps, TCXO %.1f V, heard %lu sent %lu dropped %lu",
                   BRIDGE_VERSION, RADIO_FREQ_MHZ, RADIO_BITRATE_KBPS, tcxo, (unsigned long)heard,
                   (unsigned long)sent, (unsigned long)dropped);
  uint8_t v = RADIO_VERSION;
  sendMessage(SER_HELLO, &v, 1, (const uint8_t *)text, n);
}

// SLIP decoder for what the Pi sends: TX messages go on the queue.
static uint8_t in[2 * (2 + MAX_FRAME + 2)];
static size_t in_len = 0;
static bool in_esc = false;

static void takeMessage() {
  if (in_len < 3 || radioCrc16(in, in_len - 2) != (uint16_t)(in[in_len - 2] | in[in_len - 1] << 8)) return;
  size_t n = in_len - 3;
  if (in[0] != SER_TX || n < RADIO_HEADER || n > MAX_FRAME) return;
  if (tx_count == TX_QUEUE) { dropped++; return; }
  size_t slot = (tx_head + tx_count++) % TX_QUEUE;
  memcpy(txq[slot], in + 1, n);
  txlen[slot] = n;
}

static void readSerial() {
  while (Serial.available()) {
    uint8_t b = Serial.read();
    if (b == SLIP_END) {
      if (in_len) takeMessage();
      in_len = 0; in_esc = false;
    } else if (in_len >= sizeof(in)) {
      in_len = 0;  // too long to be ours: drop it and wait for the next frame
    } else if (in_esc) {
      in[in_len++] = b == SLIP_ESC_END ? SLIP_END : b == SLIP_ESC_ESC ? SLIP_ESC : b;
      in_esc = false;
    } else if (b == SLIP_ESC) {
      in_esc = true;
    } else {
      in[in_len++] = b;
    }
  }
}

// ------------------------------------------------------------------ radio

static void listen() {
  dio1 = false;
  radio.startReceive();
}

static void receive() {
  dio1 = false;
  uint8_t frame[MAX_FRAME];
  size_t len = radio.getPacketLength();
  int16_t st = len <= MAX_FRAME ? radio.readData(frame, len) : RADIOLIB_ERR_PACKET_TOO_LONG;
  float rssi = radio.getRSSI();
  radio.startReceive();  // straight back to listening: more frames of the window are on their way
  if (st != RADIOLIB_ERR_NONE || len < RADIO_HEADER) return;
  heard++;
  int8_t r = (int8_t)std::max(-128.0f, std::min(127.0f, rssi));
  sendMessage(SER_RX, (const uint8_t *)&r, 1, frame, len);
}

static void transmitQueue() {
  while (tx_count) {
    int16_t st = radio.transmit(txq[tx_head], txlen[tx_head]);
    tx_head = (tx_head + 1) % TX_QUEUE;
    tx_count--;
    if (st == RADIOLIB_ERR_NONE) sent++;
    else logf("transmit failed: %d", st);
    dio1 = false;  // that was the end of the transmission, not a frame heard
    delayMicroseconds(TX_GAP_US);
    readSerial();  // the rest of a window of chunks may still be arriving from the Pi
  }
  listen();
}

void setup() {
  Serial.setRxBufferSize(16384);  // a whole window of reply chunks from the Pi at once
  Serial.setTxBufferSize(8192);
  Serial.begin(BRIDGE_BAUD);
  spi.begin(RADIO_SCK, RADIO_MISO, RADIO_MOSI, RADIO_NSS);
  int16_t st = radioSetup(radio, onDio1, RADIO_RXEN, RADIO_TXEN, &tcxo);
  if (st != RADIOLIB_ERR_NONE) {
    for (;;) {  // nothing works without the radio: say so until someone looks
      logf("radio did not start (RadioLib %d): check the wiring and RADIO_* pins", st);
      delay(5000);
    }
  }
  listen();
  hello();
}

void loop() {
  static uint32_t last_hello = millis();
  if (dio1) receive();
  readSerial();
  if (tx_count) transmitQueue();
  if (millis() - last_hello > HELLO_EVERY_MS) { hello(); last_hello = millis(); }
}
