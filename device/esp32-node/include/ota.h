// Over-the-air updates from the hub: whether to take the update the hub offers. Plain C++, so it can be
// checked off the board (test/test_ota.cpp). The download and the rollback are in main.cpp.
#pragma once

#include <cctype>
#include <cmath>
#include <cstdlib>
#include <cstring>

// Compare dotted versions numerically ("0.2.10" is newer than "0.2.9"): <0, 0 or >0 like strcmp. Sets *ok to
// false (and returns 0) unless both are 1-4 numbers separated by dots.
inline int compareVersions(const char *a, const char *b, bool *ok = nullptr) {
  long pa[4] = {0, 0, 0, 0}, pb[4] = {0, 0, 0, 0};
  const char *s[2] = {a, b};
  long *parts[2] = {pa, pb};
  for (int k = 0; k < 2; k++) {
    const char *p = s[k];
    int n = 0;
    while (p && *p) {
      if (n == 4 || !isdigit((unsigned char)*p)) { p = nullptr; break; }
      char *end;
      parts[k][n++] = strtol(p, &end, 10);
      p = end;
      if (*p == '.') {
        p++;
        if (!*p) { p = nullptr; break; }  // "0.2."
      } else if (*p) {
        p = nullptr;
      }
    }
    if (!p || n == 0) {
      if (ok) *ok = false;
      return 0;
    }
  }
  if (ok) *ok = true;
  for (int i = 0; i < 4; i++)
    if (pa[i] != pb[i]) return pa[i] < pb[i] ? -1 : 1;
  return 0;
}

enum OtaDecision {
  OTA_UPDATE,         // download it now
  OTA_UP_TO_DATE,     // nothing offered, or not newer than this build: nothing to report
  OTA_BAD_OFFER,      // the hub's offer doesn't make sense (version, size or hash)
  OTA_PHOTOS_QUEUED,  // photos still waiting for the hub: send those first
  OTA_BATTERY_LOW,
  OTA_GAVE_UP,        // this version failed max_tries times (or rolled back): wait for a newer one
};

inline const char *otaDecisionText(OtaDecision d) {
  switch (d) {
    case OTA_UPDATE: return "updating";
    case OTA_UP_TO_DATE: return "up to date";
    case OTA_BAD_OFFER: return "bad offer from the hub";
    case OTA_PHOTOS_QUEUED: return "photos still queued";
    case OTA_BATTERY_LOW: return "battery low";
    case OTA_GAVE_UP: return "gave up on this version";
  }
  return "?";
}

inline bool isSha256Hex(const char *h) {
  if (!h || strlen(h) != 64) return false;
  for (const char *p = h; *p; p++)
    if (!isxdigit((unsigned char)*p)) return false;
  return true;
}

// Called after a wake's last hub contact with the hub's offer (offered may be null or empty: none).
// slot_size: the free app slot's size. battery_v: the battery now, or NaN / below 0 if it isn't measured.
// tried and tries: the version the last attempts were for, and how many there were (a rollback counts as
// max_tries, so a build that can't reach the hub is not installed again and again).
inline OtaDecision otaDecide(const char *running, const char *offered, long size, long slot_size,
                             const char *sha256_hex, bool queue_empty, double battery_v, double min_battery_v,
                             const char *tried, int tries, int max_tries) {
  if (!offered || !*offered) return OTA_UP_TO_DATE;
  bool ok;
  int cmp = compareVersions(offered, running, &ok);
  if (!ok) return OTA_BAD_OFFER;
  if (cmp <= 0) return OTA_UP_TO_DATE;
  if (size <= 0 || size > slot_size || !isSha256Hex(sha256_hex)) return OTA_BAD_OFFER;
  if (tried && strcmp(tried, offered) == 0 && tries >= max_tries) return OTA_GAVE_UP;
  if (!queue_empty) return OTA_PHOTOS_QUEUED;
  if (!std::isnan(battery_v) && battery_v >= 0 && battery_v < min_battery_v) return OTA_BATTERY_LOW;
  return OTA_UPDATE;
}
