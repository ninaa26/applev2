// The camera's end of the 900 MHz radio link: sends a request to the hub in chunks and pulls the reply back.
// The protocol is in ../radio-common/sentinel_radio.h; the hub's end is sentinel_device/radio_link.py, whose
// tests (device/tests/test_radio_link.py) run a Python copy of this file's logic over a lossy channel.
#include "node_config.h"
#ifdef HUB_LINK_RADIO
#include <RadioLib.h>
#include <SPI.h>
#include "esp_mac.h"
#include "radio_link.h"
#include "sentinel_radio.h"
#include "sentinel_radio_phy.h"

#if !defined(RADIO_SCK) || !defined(RADIO_MISO) || !defined(RADIO_MOSI) || !defined(RADIO_NSS) || \
    !defined(RADIO_RESET) || !defined(RADIO_BUSY) || !defined(RADIO_DIO1)
#error "HUB_LINK_RADIO needs the radio's pins in node_config.h (RADIO_SCK ... RADIO_DIO1): see node_config.example.h"
#endif
#ifndef RADIO_RXEN
#define RADIO_RXEN -1
#endif
#ifndef RADIO_TXEN
#define RADIO_TXEN -1
#endif

static const uint32_t ACK_WAIT_MS = 300;    // for the hub's answer: the Pi relays it, so allow for its round trip
static const uint32_t CHUNK_GAP_MS = 40;    // between reply chunks in a burst (the bridge sends one every ~11 ms)
static const int MAX_MISSES = 12;           // answers missed in a row before the hub counts as gone
static const uint32_t WORKING_WAIT_MS = 200;  // between polls while the hub is busy with the request

static SPIClass spi(FSPI);
static SX1262 radio = new Module(RADIO_NSS, RADIO_DIO1, RADIO_RESET, RADIO_BUSY, spi);
static volatile bool dio1 = false;
static void IRAM_ATTR onDio1() { dio1 = true; }
static bool up = false;
static int last_rssi = 0;
static uint32_t node = 0;
RTC_DATA_ATTR static uint8_t xfer = 0;      // request number: survives deep sleep, random after power-on
static uint8_t frame[MAX_FRAME];
static uint8_t window[WINDOW * CHUNK];       // a window of reply chunks, written to the sink in order

bool radioLinkBegin() {
  if (up) return true;
  spi.begin(RADIO_SCK, RADIO_MISO, RADIO_MOSI, RADIO_NSS);
  float tcxo = 0;
  int16_t st = radioSetup(radio, onDio1, RADIO_RXEN, RADIO_TXEN, &tcxo);
  if (st != RADIOLIB_ERR_NONE) {
    Serial.printf("radio did not start (RadioLib %d): check its wiring and RADIO_* pins\n", st);
    return false;
  }
  uint8_t mac[6];
  esp_read_mac(mac, ESP_MAC_WIFI_STA);
  node = (uint32_t)mac[2] << 24 | mac[3] << 16 | mac[4] << 8 | mac[5];
  if (xfer == 0) xfer = esp_random() | 1;
  Serial.printf("radio %.1f MHz %.0f kbps, TCXO %.1f V, address %08lx\n", RADIO_FREQ_MHZ, RADIO_BITRATE_KBPS, tcxo,
                (unsigned long)node);
  up = true;
  return true;
}

void radioLinkSleep() {
  if (!up) return;
  radio.sleep();
  spi.end();
  up = false;
}

int radioLinkRssi() { return last_rssi; }

static bool send(size_t len) {
  int16_t st = radio.transmit(frame, len);
  dio1 = false;  // that was the end of the transmission
  return st == RADIOLIB_ERR_NONE;
}

// Wait up to ms for a frame of this request (any type); returns its length, or 0. Leaves the radio listening.
static size_t hear(uint8_t *buf, uint8_t x, uint32_t ms, bool start = true) {
  if (start) { dio1 = false; radio.startReceive(); }
  uint32_t until = millis() + ms;
  while ((int32_t)(until - millis()) > 0) {
    if (!dio1) { delayMicroseconds(100); continue; }
    dio1 = false;
    size_t len = radio.getPacketLength();
    int16_t st = len <= MAX_FRAME ? radio.readData(buf, len) : RADIOLIB_ERR_PACKET_TOO_LONG;
    float rssi = radio.getRSSI();
    radio.startReceive();
    if (st == RADIOLIB_ERR_NONE && len >= RADIO_HEADER && buf[0] >> 4 == RADIO_VERSION &&
        radioGet32(buf + 1) == node && buf[5] == x) {
      last_rssi = (int)rssi;
      return len;
    }
  }
  return 0;
}

// Listen before talking: another camera may be mid-request with the hub. Gives way a few times, then goes ahead.
static void waitForQuiet() {
  for (int i = 0; i < 5; i++) {
    dio1 = false;
    radio.startReceive();
    delay(2);
    if (radio.getRSSI(false) < -95 && !dio1) break;
    delay(20 + esp_random() % 80);
  }
  radio.standby();
}

// The request blob is [head length u16][head][body]: read len bytes of it from offset off.
struct Blob {
  String head;
  File *body;
  size_t total() const { return 2 + head.length() + (body ? body->size() : 0); }
  void read(size_t off, uint8_t *dst, size_t len) {
    while (len) {
      if (off < 2) {
        *dst++ = off == 0 ? head.length() & 0xFF : head.length() >> 8;
        off++; len--;
      } else if (off < 2 + head.length()) {
        size_t n = std::min(len, 2 + head.length() - off);
        memcpy(dst, head.c_str() + off - 2, n);
        dst += n; off += n; len -= n;
      } else {
        body->seek(off - 2 - head.length());
        size_t n = body->read(dst, len);
        if (!n) { memset(dst, 0, len); return; }  // the file shrank: the hub will refuse the photo
        dst += n; off += n; len -= n;
      }
    }
  }
};

static size_t dataFrame(Blob &blob, uint8_t x, uint16_t seq, uint32_t total, uint8_t flags) {
  size_t h = radioHeader(frame, REQ_DATA, node, x);
  radioPut16(frame + h, seq);
  radioPut32(frame + h + 2, total);
  frame[h + 6] = flags;
  size_t n = std::min(CHUNK, (size_t)total - seq * CHUNK);
  blob.read(seq * CHUNK, frame + h + 7, n);
  return h + 7 + n;
}

// Send the whole request; returns 0 once the hub has all of it, or -1.
static int upload(Blob &blob, uint8_t x, uint32_t deadline) {
  uint32_t total = blob.total();
  uint16_t n = (total + CHUNK - 1) / CHUNK;
  uint8_t ack[MAX_FRAME];
  for (uint16_t base = 0; base < n; base += WINDOW) {
    uint16_t count = std::min((uint16_t)WINDOW, (uint16_t)(n - base));
    uint32_t missing = count == 32 ? 0xFFFFFFFF : (1UL << count) - 1;
    uint32_t resend = missing;
    int misses = 0;
    while (missing) {
      if ((int32_t)(deadline - millis()) < 0) return -1;
      waitForQuiet();
      int last = 31 - __builtin_clz(resend);
      for (int i = 0; i <= last; i++) {
        if (!(resend >> i & 1)) continue;
        if (!send(dataFrame(blob, x, base + i, total, i == last ? FLAG_ACK_PLEASE : 0))) return -1;
      }
      size_t len = 0;
      for (uint32_t until = millis() + ACK_WAIT_MS; !len && (int32_t)(until - millis()) > 0;) {
        len = hear(ack, x, until - millis());
        if (len && (ack[0] & 0x0F) != REQ_ACK) len = 0;
      }
      radio.standby();
      if (len < RADIO_HEADER + 8) {  // the ack, or the window's last frame, was lost: ask again with that frame
        if (++misses >= MAX_MISSES) return -1;
        resend = 1UL << (31 - __builtin_clz(missing));
        continue;
      }
      misses = 0;
      const uint8_t *a = ack + RADIO_HEADER;
      if (a[6] & FLAG_ALL_HERE) return 0;
      uint16_t ack_base = radioGet16(a);
      if (ack_base == base) missing &= ~radioGet32(a + 2);
      resend = missing;
    }
  }
  return 0;  // every window acknowledged (the last ack says so too)
}

static size_t shortFrame(uint8_t type, uint8_t x) { return radioHeader(frame, type, node, x); }

int radioLinkRequest(const char *method, const char *path, const char *key, const String &meta, const char *ctype,
                     File *body, RadioSink &sink, uint32_t timeout_ms, uint32_t *uploaded_ms) {
  if (!radioLinkBegin()) return -4;
  uint32_t start = millis(), deadline = start + timeout_ms;
  uint8_t x = ++xfer ? xfer : ++xfer;  // never 0
  String head = String("{\"m\":\"") + method + "\",\"p\":\"" + path + "\"";
  if (key && key[0]) head += String(",\"a\":\"") + key + "\"";
  if (meta.length()) {
    head += ",\"x\":\"";
    for (const char *c = meta.c_str(); *c; c++) {  // meta is JSON: escape it as a JSON string
      if (*c == '"' || *c == '\\') head += '\\';
      head += *c;
    }
    head += "\"";
  }
  if (ctype && ctype[0]) head += String(",\"t\":\"") + ctype + "\"";
  head += "}";
  Blob blob = {head, body};
  if (upload(blob, x, deadline) != 0) { radio.standby(); return -1; }
  if (uploaded_ms) *uploaded_ms = millis();
  uint32_t sent_up = blob.total();

  // Ask until the hub has the gateway's reply.
  uint8_t in[MAX_FRAME];
  int misses = 0, status = 0;
  uint32_t total = 0;
  for (;;) {
    if ((int32_t)(deadline - millis()) < 0) return -1;
    send(shortFrame(POLL, x));
    size_t len = hear(in, x, ACK_WAIT_MS);
    radio.standby();
    if (len < RADIO_HEADER + 8 || (in[0] & 0x0F) != RESP_INFO) {
      if (++misses >= MAX_MISSES) return -1;
      continue;
    }
    misses = 0;
    const uint8_t *r = in + RADIO_HEADER;
    if (r[0] == STATE_UNKNOWN) return -2;
    if (r[0] == STATE_READY) { status = radioGet16(r + 1); total = radioGet32(r + 3); break; }
    delay(WORKING_WAIT_MS);
  }
  if (!sink.begin(status, total)) { send(shortFrame(DONE, x)); radio.standby(); return -3; }

  // Pull the reply a window at a time, asking again for whatever didn't arrive.
  uint16_t n = (total + CHUNK - 1) / CHUNK;
  for (uint16_t base = 0; base < n; base += WINDOW) {
    uint16_t count = std::min((uint16_t)WINDOW, (uint16_t)(n - base));
    uint32_t missing = count == 32 ? 0xFFFFFFFF : (1UL << count) - 1;
    misses = 0;
    while (missing) {
      if ((int32_t)(deadline - millis()) < 0) return -1;
      size_t h = shortFrame(PULL, x);
      radioPut16(frame + h, base);
      radioPut32(frame + h + 2, missing);
      send(h + 6);
      uint32_t before = missing;
      size_t len = hear(in, x, ACK_WAIT_MS);
      while (len) {
        if ((in[0] & 0x0F) == RESP_DATA && len > RADIO_HEADER + 2) {
          uint16_t seq = radioGet16(in + RADIO_HEADER);
          uint16_t i = seq - base;
          if (seq >= base && i < count && missing >> i & 1) {
            memcpy(window + i * CHUNK, in + RADIO_HEADER + 2, std::min(len - RADIO_HEADER - 2, CHUNK));
            missing &= ~(1UL << i);
          }
        }
        if (!missing) break;
        len = hear(in, x, CHUNK_GAP_MS, false);
      }
      radio.standby();
      if (missing == before && ++misses >= MAX_MISSES) return -1;
      if (missing != before) misses = 0;
    }
    size_t bytes = std::min((size_t)count * CHUNK, (size_t)total - base * CHUNK);
    if (!sink.write(window, bytes)) { send(shortFrame(DONE, x)); radio.standby(); return -3; }
  }
  send(shortFrame(DONE, x));
  radio.standby();
  Serial.printf("radio %s %s -> %d (%lu B up, %lu B down, %lu ms, %d dBm)\n", method, path, status,
                (unsigned long)sent_up, (unsigned long)total, (unsigned long)(millis() - start), last_rssi);
  return status;
}
#endif
