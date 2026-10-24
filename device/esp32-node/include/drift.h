// The RTC's drift, from successive hub contacts (see main.cpp's timekeeping note). Plain C++, so it can be
// checked off the board.
#pragma once

struct DriftRef {
  double clock;   // clock at the reference contact
  double offset;  // hub time - clock measured then
  bool set;
};

// Called on every hub contact with that contact's offset. The rate is measured from a reference contact at
// least min_span_s of clock back, and the reference moves only when the rate is updated: nodes check in
// every 10-30 min, and a reference moved on every contact never gets an hour behind (Oct 2026: drift_ppm 0
// in all 255 reports).
inline void updateDrift(DriftRef &ref, double &rate, double now_clock, double new_offset,
                        double min_span_s = 3600) {
  if (!ref.set || now_clock < ref.clock) {
    ref = {now_clock, new_offset, true};
    return;
  }
  double span = now_clock - ref.clock;
  if (span < min_span_s) return;
  // Over the stretch the hub's time moved span + (new_offset - ref.offset) seconds.
  double r = (span + (new_offset - ref.offset)) / span;
  if (r > 0.9 && r < 1.1) rate = 0.7 * rate + 0.3 * r;
  ref = {now_clock, new_offset, true};
}
