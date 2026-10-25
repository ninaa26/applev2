// Host test for include/ota.h (and drift.h): plain C++, no board. device/tests/test_esp32_host.py builds and
// runs it with the computer's C++ compiler; by hand: c++ -std=c++17 -I include test/test_ota.cpp && ./a.out
#include <cmath>
#include <cstdio>
#include <string>

#include "drift.h"
#include "ota.h"

static int failures = 0;
#define CHECK(cond)                                                \
  do {                                                             \
    if (!(cond)) {                                                 \
      std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
      failures++;                                                  \
    }                                                              \
  } while (0)

static const char *SHA = "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08";
static const long SLOT = 0x200000;

// The usual case around one offer: 0.2.7 running, the hub offers 0.2.8, nothing queued, no battery reading.
static OtaDecision decide(const char *offered, long size = 1068448, const char *sha = SHA, bool queue_empty = true,
                          double battery_v = NAN, const char *tried = "", int tries = 0) {
  return otaDecide("0.2.7", offered, size, SLOT, sha, queue_empty, battery_v, 3.7, tried, tries, 3);
}

int main() {
  bool ok;
  CHECK(compareVersions("0.2.10", "0.2.9", &ok) > 0 && ok);
  CHECK(compareVersions("0.2.7", "0.2.7", &ok) == 0 && ok);
  CHECK(compareVersions("0.2.6", "0.2.7") < 0);
  CHECK(compareVersions("1.0", "0.9.9") > 0);
  CHECK(compareVersions("0.3", "0.3.0", &ok) == 0 && ok);
  CHECK(compareVersions("0.2.7.1", "0.2.7") > 0);
  for (const char *bad : {"", "0.2.", ".2", "0..2", "v0.2.8", "0.2.8-rc1", "1.2.3.4.5", "0.2 "}) {
    compareVersions(bad, "0.2.7", &ok);
    if (ok) std::printf("accepted %s\n", bad);
    CHECK(!ok);
  }

  CHECK(decide("0.2.8") == OTA_UPDATE);
  CHECK(decide("0.2.10") == OTA_UPDATE);
  CHECK(decide(nullptr) == OTA_UP_TO_DATE);
  CHECK(decide("") == OTA_UP_TO_DATE);
  CHECK(decide("0.2.7") == OTA_UP_TO_DATE);  // the build it runs
  CHECK(decide("0.2.6") == OTA_UP_TO_DATE);  // never downgrade
  CHECK(decide("latest") == OTA_BAD_OFFER);
  CHECK(decide("0.2.8", 0) == OTA_BAD_OFFER);
  CHECK(decide("0.2.8", SLOT + 1) == OTA_BAD_OFFER);  // wouldn't fit the free app slot
  CHECK(decide("0.2.8", SLOT) == OTA_UPDATE);
  CHECK(decide("0.2.8", 1000, "abc") == OTA_BAD_OFFER);
  CHECK(decide("0.2.8", 1000, std::string(64, 'g').c_str()) == OTA_BAD_OFFER);
  CHECK(decide("0.2.8", 1000, "9F86D081884C7D659A2FEAA0C55AD015A3BF4F1B2B0B822CD15D6C15B0F00A08") == OTA_UPDATE);
  CHECK(decide("0.2.8", 1000, SHA, false) == OTA_PHOTOS_QUEUED);
  CHECK(decide("0.2.8", 1000, SHA, true, 3.69) == OTA_BATTERY_LOW);
  CHECK(decide("0.2.8", 1000, SHA, true, 3.7) == OTA_UPDATE);
  CHECK(decide("0.2.8", 1000, SHA, true, -1) == OTA_UPDATE);  // not measured
  // Failed downloads of 0.2.8: tried again until the third, then not until a newer version.
  CHECK(decide("0.2.8", 1000, SHA, true, NAN, "0.2.8", 2) == OTA_UPDATE);
  CHECK(decide("0.2.8", 1000, SHA, true, NAN, "0.2.8", 3) == OTA_GAVE_UP);
  CHECK(decide("0.2.9", 1000, SHA, true, NAN, "0.2.8", 3) == OTA_UPDATE);
  CHECK(std::string(otaDecisionText(OTA_BATTERY_LOW)) == "battery low");

  // drift.h: the rate moves only over an hour or more of clock, and the reference moves with it.
  DriftRef ref = {0, 0, false};
  double rate = 1.0;
  updateDrift(ref, rate, 100, 50);
  updateDrift(ref, rate, 1900, 50.9);  // half an hour later: too soon
  CHECK(rate == 1.0 && ref.clock == 100);
  updateDrift(ref, rate, 3700, 51.8);  // an hour: the hub moved 3601.8 s while the clock moved 3600
  CHECK(std::fabs(rate - (0.7 + 0.3 * 3601.8 / 3600)) < 1e-12 && ref.clock == 3700);

  if (failures) {
    std::printf("%d failed\n", failures);
    return 1;
  }
  std::printf("ota.h and drift.h: all passed\n");
  return 0;
}
