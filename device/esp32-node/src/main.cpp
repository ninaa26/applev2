// ESP32-S3 camera trap: wake, photograph the liner, queue the photo in flash, upload the queue to the
// hub Pi, ask it when to wake next, deep-sleep. See device/esp32-node/README.md.
//
// Timekeeping: the node never sets its clock. `clock` is seconds since power-on, which keeps counting
// through deep sleep on the RTC timer, and `offset` (hub time - clock) is measured on every contact.
// Comparing successive offsets gives the RTC's drift, which shortens or lengthens the next sleep.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <WiFi.h>
#include <algorithm>
#include <sys/time.h>
#include <vector>
#include "esp_camera.h"
#include "node_config.h"

#define FW_VERSION "0.1.0"
static const int CONNECT_MIN_S = 120;      // keep trying the hub at least this long per wake
static const int CONNECT_MAX_S = 300;
static const int UNSYNCED_SLEEP_S = 600;   // never heard from the hub: try again this often
static const size_t FS_RESERVE = 600000;   // drop the oldest photos to keep this much flash free
static const int MAX_WAKES = 12;

// Survives deep sleep, lost on power loss.
RTC_DATA_ATTR uint32_t session = 0;        // random per power-on: photos from an older session have no usable clock
RTC_DATA_ATTR bool synced = false;
RTC_DATA_ATTR double offset = 0;           // hub unix time - clock
RTC_DATA_ATTR double sync_clock = 0;       // clock at that measurement
RTC_DATA_ATTR double rate = 1.0;           // real seconds per clock second while asleep
RTC_DATA_ATTR int64_t wakes[MAX_WAKES];    // upcoming wake times (hub unix seconds)
RTC_DATA_ATTR int n_wakes = 0;
RTC_DATA_ATTR uint32_t boots = 0;
RTC_DATA_ATTR char last_error[96] = "";

static double clockNow() {
  struct timeval tv;
  gettimeofday(&tv, nullptr);
  return tv.tv_sec + tv.tv_usec / 1e6;
}

static void setError(const char *msg) {
  Serial.printf("ERROR %s\n", msg);
  strlcpy(last_error, msg, sizeof(last_error));
}

static String isoTime(double unix) {
  time_t t = (time_t)unix;
  struct tm tm;
  gmtime_r(&t, &tm);
  char buf[32];
  strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S+00:00", &tm);
  return buf;
}

// ------------------------------------------------------------------ camera

static bool cameraInit() {
  camera_config_t c = {};
  c.pin_pwdn = -1; c.pin_reset = -1; c.pin_xclk = CAM_PIN_XCLK;
  c.pin_sccb_sda = CAM_PIN_SIOD; c.pin_sccb_scl = CAM_PIN_SIOC;
  c.pin_d7 = CAM_PIN_D7; c.pin_d6 = CAM_PIN_D6; c.pin_d5 = CAM_PIN_D5; c.pin_d4 = CAM_PIN_D4;
  c.pin_d3 = CAM_PIN_D3; c.pin_d2 = CAM_PIN_D2; c.pin_d1 = CAM_PIN_D1; c.pin_d0 = CAM_PIN_D0;
  c.pin_vsync = CAM_PIN_VSYNC; c.pin_href = CAM_PIN_HREF; c.pin_pclk = CAM_PIN_PCLK;
  c.xclk_freq_hz = 20000000; c.ledc_timer = LEDC_TIMER_0; c.ledc_channel = LEDC_CHANNEL_0;
  c.pixel_format = PIXFORMAT_JPEG; c.frame_size = CAM_FRAMESIZE; c.jpeg_quality = CAM_JPEG_QUALITY;
  c.fb_count = 2; c.fb_location = CAMERA_FB_IN_PSRAM; c.grab_mode = CAMERA_GRAB_LATEST;
  if (esp_camera_init(&c) != ESP_OK) return false;
  sensor_t *s = esp_camera_sensor_get();
  if (CAM_AEC_VALUE >= 0) { s->set_exposure_ctrl(s, 0); s->set_aec_value(s, CAM_AEC_VALUE); }
  if (CAM_AGC_GAIN >= 0) { s->set_gain_ctrl(s, 0); s->set_agc_gain(s, CAM_AGC_GAIN); }
  return true;
}

// Photograph the liner and queue it in flash as /q/<seq>-<id>.jpg + .json.
static bool captureToQueue(const char *wake_reason, bool new_card) {
  if (!cameraInit()) { setError("camera not found"); return false; }
  if (LED_PIN >= 0) { pinMode(LED_PIN, OUTPUT); digitalWrite(LED_PIN, HIGH); delay(LED_SETTLE_MS); }
  for (int i = 0; i < CAM_SETTLE_FRAMES; i++) { camera_fb_t *f = esp_camera_fb_get(); if (f) esp_camera_fb_return(f); }
  camera_fb_t *fb = esp_camera_fb_get();
  double taken = clockNow();
  if (LED_PIN >= 0) digitalWrite(LED_PIN, LOW);
  if (!fb) { setError("capture failed"); esp_camera_deinit(); return false; }

  sensor_t *s = esp_camera_sensor_get();
  JsonDocument meta;
  char id[17];
  snprintf(id, sizeof(id), "%08lx%08lx", (unsigned long)esp_random(), (unsigned long)esp_random());
  meta["node_capture_id"] = id;
  meta["clock"] = taken;
  meta["session"] = session;
  meta["wake_reason"] = wake_reason;
  meta["new_card"] = new_card;
  if (new_card) meta["new_card_source"] = "button";
  JsonObject cam = meta["camera"].to<JsonObject>();
  cam["sensor_pid"] = s->id.PID; cam["width"] = fb->width; cam["height"] = fb->height;
  cam["jpeg_quality"] = CAM_JPEG_QUALITY; cam["aec_value"] = CAM_AEC_VALUE; cam["agc_gain"] = CAM_AGC_GAIN;

  // Make room: oldest photos go first.
  std::vector<String> names;
  File dir = LittleFS.open("/q");
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) if (String(f.name()).endsWith(".jpg")) names.push_back(f.name());
  std::sort(names.begin(), names.end());
  for (size_t i = 0; i < names.size() && LittleFS.totalBytes() - LittleFS.usedBytes() < fb->len + FS_RESERVE; i++) {
    String stem = "/q/" + names[i].substring(0, names[i].length() - 4);
    LittleFS.remove(stem + ".jpg"); LittleFS.remove(stem + ".json");
    setError("flash full: dropped the oldest photo");
  }

  Preferences prefs;
  prefs.begin("node");
  uint32_t seq = prefs.getUInt("seq", 0) + 1;
  prefs.putUInt("seq", seq);
  prefs.end();
  char stem[40];
  snprintf(stem, sizeof(stem), "/q/%08lu-%s", (unsigned long)seq, id);
  File jpg = LittleFS.open(String(stem) + ".jpg", "w");
  bool ok = jpg && jpg.write(fb->buf, fb->len) == fb->len;
  jpg.close();
  File js = LittleFS.open(String(stem) + ".json", "w");
  ok = ok && js && serializeJson(meta, js) > 0;
  js.close();
  Serial.printf("captured %s %ux%u %u bytes\n", stem, fb->width, fb->height, fb->len);
  esp_camera_fb_return(fb);
  esp_camera_deinit();
  if (!ok) { LittleFS.remove(String(stem) + ".jpg"); setError("could not save photo"); }
  return ok;
}

// ------------------------------------------------------------------ hub

static bool connectWifi(int max_s) {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  uint32_t until = millis() + max_s * 1000UL;
  wl_status_t st = WL_IDLE_STATUS;
  while (millis() < until) {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    for (int i = 0; i < 100 && (st = WiFi.status()) != WL_CONNECTED; i++) delay(100);
    if (st == WL_CONNECTED) {
      Serial.printf("wifi %s ip %s rssi %d\n", WIFI_SSID, WiFi.localIP().toString().c_str(), WiFi.RSSI());
      return true;
    }
    WiFi.disconnect();
    delay(3000);  // the hub may still be booting
  }
  // 1: SSID not seen, 4: refused (password, or a network that wants this MAC registered), 6: lost
  Serial.printf("wifi %s failed status %d mac %s\n", WIFI_SSID, st, WiFi.macAddress().c_str());
  return false;
}

// Everything the hub's reply says about time: measure the offset, update the drift, store the wakes.
static void takeTime(JsonDocument &reply, double sent_clock) {
  if (!reply["now"].is<double>()) return;
  double now_clock = clockNow();
  double new_offset = reply["now"].as<double>() - (sent_clock + now_clock) / 2;
  if (synced && now_clock - sync_clock > 3600) {
    // Over the last stretch the hub's time moved (now_clock - sync_clock) + (new_offset - offset) seconds.
    double r = ((now_clock - sync_clock) + (new_offset - offset)) / (now_clock - sync_clock);
    if (r > 0.9 && r < 1.1) rate = 0.7 * rate + 0.3 * r;
  }
  offset = new_offset; sync_clock = now_clock; synced = true;
  JsonArray w = reply["wakes"].as<JsonArray>();
  if (!w.isNull()) {
    n_wakes = 0;
    for (JsonVariant v : w) if (n_wakes < MAX_WAKES) wakes[n_wakes++] = v.as<int64_t>();
  }
}

static int post(const String &path, const char *method, File *body, const String &meta, JsonDocument &reply) {
  HTTPClient http;
  http.begin(String(HUB_URL) + path);
  http.setTimeout(20000);
  http.addHeader("Authorization", String("Bearer ") + API_KEY);
  if (meta.length()) http.addHeader("X-Sentinel-Meta", meta);
  double sent = clockNow();
  int code;
  if (body) { http.addHeader("Content-Type", "image/jpeg"); code = http.sendRequest(method, body, body->size()); }
  else code = http.sendRequest(method);
  if (code > 0) {
    if (!deserializeJson(reply, http.getString())) takeTime(reply, sent);
  }
  http.end();
  return code;
}

// Upload the queue oldest first. Returns 0 when it is empty, or the reply that stopped it
// (401: the hub does not know this key; anything else: the hub is not answering yet).
static int uploadQueue() {
  std::vector<String> names;
  File dir = LittleFS.open("/q");
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) if (String(f.name()).endsWith(".jpg")) names.push_back(f.name());
  std::sort(names.begin(), names.end());
  for (const String &name : names) {
    String stem = "/q/" + name.substring(0, name.length() - 4);
    File js = LittleFS.open(stem + ".json");
    JsonDocument meta;
    if (!js || deserializeJson(meta, js)) { js.close(); LittleFS.remove(stem + ".jpg"); LittleFS.remove(stem + ".json"); continue; }
    js.close();
    double clk = meta["clock"].as<double>();
    bool same_session = meta["session"].as<uint32_t>() == session;
    if (synced && same_session) {
      meta["clock_synced"] = true;
      meta["captured_at"] = isoTime(clk + offset);
    } else {
      meta["clock_synced"] = false;
      meta["age_s"] = same_session ? clockNow() - clk : 0;
      if (!same_session) meta["clock_lost"] = true;  // power was lost since: the hub dates it on arrival
    }
    meta["trap_id"] = TRAP_ID;
    JsonObject dev = meta["device"].to<JsonObject>();
    dev["sw_version"] = FW_VERSION; dev["rssi"] = WiFi.RSSI(); dev["boots"] = boots;
    dev["cpu_temp_c"] = temperatureRead(); dev["last_error"] = last_error[0] ? last_error : nullptr;
    dev["fs_free_kb"] = (LittleFS.totalBytes() - LittleFS.usedBytes()) / 1000;
    dev["drift_ppm"] = (rate - 1.0) * 1e6;
    String header;
    serializeJson(meta, header);

    File jpg = LittleFS.open(stem + ".jpg");
    JsonDocument reply;
    int code = post("/node/v1/captures", "POST", &jpg, header, reply);
    jpg.close();
    Serial.printf("upload %s -> %d\n", stem.c_str(), code);
    if (code == 200 || code == 201 || code == 413 || code == 415 || code == 422) {
      if (code >= 400) setError("hub refused a photo");
      LittleFS.remove(stem + ".jpg"); LittleFS.remove(stem + ".json");
      if (code < 400) last_error[0] = 0;
    } else {
      if (code == 401) setError("hub does not know this trap's key");
      return code == 0 ? -1 : code;
    }
  }
  return 0;
}

// ------------------------------------------------------------------ sleep

static void sleepUntilNextWake() {
  double now = clockNow();
  double sleep_clock = UNSYNCED_SLEEP_S;
  if (synced) {
    double hub_now = now + offset;
    for (int i = 0; i < n_wakes; i++) {
      double real = wakes[i] - hub_now;
      if (real < 60) continue;
      // Wake early by a margin that grows with the sleep, then convert hub seconds to RTC seconds.
      double margin = 15 + 0.003 * real;
      sleep_clock = (real - margin) / rate;
      break;
    }
  }
  if (sleep_clock < 30) sleep_clock = 30;
  Serial.printf("sleeping %.0f s\n", sleep_clock);
  Serial.flush();
  esp_sleep_enable_timer_wakeup((uint64_t)(sleep_clock * 1e6));
  if (BUTTON_PIN >= 0) esp_sleep_enable_ext0_wakeup((gpio_num_t)BUTTON_PIN, 0);
  esp_deep_sleep_start();
}

void setup() {
  Serial.begin(115200);
  boots++;
  esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
  if (session == 0) session = esp_random() | 1;
  const char *reason = cause == ESP_SLEEP_WAKEUP_TIMER ? "scheduled" : cause == ESP_SLEEP_WAKEUP_EXT0 ? "manual" : "first";
  bool new_card = cause == ESP_SLEEP_WAKEUP_EXT0;
  Serial.printf("\nsentinel node %s fw %s wake=%s boots=%lu synced=%d\n", TRAP_ID, FW_VERSION, reason, (unsigned long)boots, synced);

  if (!LittleFS.begin(true)) setError("flash filesystem failed");
  LittleFS.mkdir("/q");
  captureToQueue(reason, new_card);

  double real_margin = n_wakes ? 15 + 0.003 * 43200 : 0;  // as early as we might have woken
  int connect_s = std::min(CONNECT_MAX_S, CONNECT_MIN_S + (int)(2 * real_margin));
  uint32_t until = millis() + connect_s * 1000UL;
  if (connectWifi(connect_s)) {
    // The hub's Wi-Fi can be up before its gateway opens (it is still booting or photographing its
    // own liner), so keep trying it for the rest of this wake's window.
    int code = -1;
    while ((code = uploadQueue()) != 0 && code != 401 && (int32_t)(until - millis()) > 5000) {
      delay(5000);
      if (WiFi.status() != WL_CONNECTED) connectWifi(std::max(10, (int)((int32_t)(until - millis()) / 1000)));
    }
    if (code == 0) {
      JsonDocument reply;
      String status;
      JsonDocument st;
      st["last_error"] = last_error[0] ? last_error : nullptr;
      st["rssi"] = WiFi.RSSI();
      serializeJson(st, status);
      post("/node/v1/schedule", "GET", nullptr, status, reply);  // tells the hub this node is done
    } else if (code != 401) {
      setError("hub not answering");
    }
  } else {
    setError("hub not reachable");
  }
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  sleepUntilNextWake();
}

void loop() {}
