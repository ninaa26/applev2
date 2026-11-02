// The camera's end of the 900 MHz radio link to the hub (HUB_LINK_RADIO in node_config.h). It carries the same
// requests the camera makes over Wi-Fi; the protocol is in ../radio-common/sentinel_radio.h.
#pragma once
#include <Arduino.h>
#include <FS.h>

// Where a reply's body goes as it arrives, in order.
struct RadioSink {
  virtual bool begin(int status, size_t total) = 0;  // false: don't want it (the request then fails with -3)
  virtual bool write(const uint8_t *p, size_t n) = 0;
  virtual ~RadioSink() {}
};

// A reply kept in memory (JSON replies are small).
struct StringSink : RadioSink {
  String data;
  bool begin(int, size_t total) override { return total <= 32768 && data.reserve(total); }
  bool write(const uint8_t *p, size_t n) override { return data.concat((const char *)p, n); }
};

bool radioLinkBegin();    // start the radio: false if it isn't answering (wiring, pins)
void radioLinkSleep();    // put it to sleep (under 1 uA): call before every deep sleep or restart
int radioLinkRssi();      // how strongly this camera last heard the hub, dBm (0 before it has)

// One request to the hub. Returns its HTTP status, or: -1 the hub isn't answering, -2 the hub lost the request
// part-way (try again), -3 the sink refused the reply, -4 the radio failed. *uploaded_ms, if given, is millis()
// when the hub had the whole request (for timing the reply, as the Wi-Fi code times the round trip).
int radioLinkRequest(const char *method, const char *path, const char *key, const String &meta, const char *ctype,
                     File *body, RadioSink &sink, uint32_t timeout_ms, uint32_t *uploaded_ms = nullptr);
