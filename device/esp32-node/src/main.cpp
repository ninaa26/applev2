// ESP32-S3 camera trap: wake, photograph the liner, queue the photo in flash, upload the queue to the
// hub Pi, ask it when to wake next, deep-sleep. See device/esp32-node/README.md.
//
// Setup mode (after power-on, or BOOT held for 3 s): a live preview for aiming the camera, served by the
// node itself and listed on the hub's page, then the normal photo. Between photos the node wakes every
// checkin_s (from the hub) just to ask whether a photo was asked for on the dashboard.
//
// Identity: the trap id and key live in flash (NVS), not in the firmware, so one release build serves every
// camera. A new camera has none: it pairs (POST /node/v1/pair with the last 6 hex digits of its MAC) until
// it is added on the dashboard and the hub hands it its key. BOOT held for 10 s forgets them, to pair again.
// A dev build flashed for one trap (flash-camera.sh T3 <key>) stores the id and key compiled into it.
//
// Updates: the hub offers firmware sent from the dashboard ("firmware" in its replies). The node writes it to
// the other app slot and restarts into it. The new firmware keeps itself only if it reaches the hub on that
// first boot; if it can't, or crashes, the bootloader goes back to the old one.
//
// Timekeeping: the node never sets its clock. `clock` is seconds since power-on, which keeps counting
// through deep sleep on the RTC timer, and `offset` (hub time - clock) is measured on every contact.
// Comparing offsets an hour or more apart gives the RTC's drift (drift.h), which shortens or lengthens
// the next sleep.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <Update.h>
#include <WiFi.h>
#include <algorithm>
#include <sys/time.h>
#include <vector>
#include "driver/rtc_io.h"
#include "esp_camera.h"
#include "esp_ota_ops.h"
#include "drift.h"
#include "esp_http_server.h"
#include "node_config.h"

// Settings added after the first node_config.h files were written: defaults for those.
#ifndef SETUP_PREVIEW_S
#define SETUP_PREVIEW_S 120              // how long the live preview runs in setup mode
#endif
#ifndef PREVIEW_FRAMESIZE
#define PREVIEW_FRAMESIZE FRAMESIZE_VGA  // live preview size; "full size" on the page uses CAM_FRAMESIZE
#endif
#ifndef SETUP_HOLD_MS
#define SETUP_HOLD_MS 3000               // hold BUTTON_PIN this long on a button wake for setup mode
#endif

#ifndef TRAP_ID
#define TRAP_ID ""  // a release build: the id and key come from pairing
#endif
#ifndef API_KEY
#define API_KEY ""
#endif

#define FW_VERSION "0.3.0"
#ifdef RELEASE_BUILD
#define FW_KIND "release"
#else
#define FW_KIND "dev"
#endif
// The server reads the version from the file (fleet.read_firmware_version) and takes only release builds:
// a dev build has one trap's key compiled in.
extern "C" const char fw_marker[] = "SENTINEL_FW_VERSION=" FW_VERSION ";" FW_KIND;
static const int CONNECT_MIN_S = 120;      // keep trying the hub at least this long per wake
static const int CONNECT_MAX_S = 300;
static const int UNSYNCED_SLEEP_S = 600;   // never heard from the hub: first retry after this long,
static const int UNSYNCED_SLEEP_MAX_S = 1800;  // doubling up to this, without a photo on retries
static const int RETRY_CONNECT_S = 120;    // Wi-Fi tries on a retry wake (no schedule to aim at)
static const size_t FS_RESERVE = 600000;   // drop the oldest photos to keep this much flash free
static const int MAX_WAKES = 12;
static const int CHECKIN_CONNECT_S = 20;   // a check-in that can't reach the hub gives up quickly
static const int HUB_DOWN_CONNECT_S = 45;  // photo wakes after one that couldn't reach the hub, until it answers
static const int PAIR_FAST_TRIES = 30;     // a new camera asks to be added every 30 s for 15 min, then every 10 min
static const int RESET_HOLD_MS = 10000;    // BOOT held this long forgets the trap id and key
static const int OTA_MAX_TRIES = 2;        // a firmware version that failed this often is not tried again

// Survives deep sleep, lost on power loss.
RTC_DATA_ATTR uint32_t session = 0;        // random per power-on: photos from an older session have no usable clock
RTC_DATA_ATTR bool synced = false;
RTC_DATA_ATTR double offset = 0;           // hub unix time - clock
RTC_DATA_ATTR double sync_clock = 0;       // clock at that measurement
RTC_DATA_ATTR double rate = 1.0;           // real seconds per clock second while asleep
RTC_DATA_ATTR DriftRef drift_ref = {0, 0, false};  // the contact the next rate update measures from
RTC_DATA_ATTR int64_t wakes[MAX_WAKES];    // upcoming wake times (hub unix seconds)
RTC_DATA_ATTR int n_wakes = 0;
RTC_DATA_ATTR uint32_t boots = 0;
RTC_DATA_ATTR char last_error[96] = "";
RTC_DATA_ATTR int retries = 0;             // wakes in a row spent looking for a hub we have no schedule from
RTC_DATA_ATTR int checkin_s = 0;           // from the hub: check in this often between photos (0: don't)
RTC_DATA_ATTR bool checkin_next = false;   // the coming timer wake is a check-in, not a photo
RTC_DATA_ATTR int hub_misses = 0;          // photo wakes in a row that couldn't reach the hub
RTC_DATA_ATTR int pair_tries = 0;          // wakes spent asking to be added
static char trap_id[33] = "";              // from NVS (loadIdentity); empty until the camera is added
static char api_key[65] = "";
static String fw_offer, fw_offer_md5;      // the hub's last reply: firmware sent from the dashboard
static size_t fw_offer_size = 0;
static bool photo_now = false;             // the hub's last reply: a photo was asked for on the dashboard
// The previous wake, reported at the end of this one: how long it was awake (power) and whether it got through.
RTC_DATA_ATTR uint32_t prev_awake_ms = 0;
RTC_DATA_ATTR char prev_wake[12] = "";
RTC_DATA_ATTR bool prev_reached_hub = false;
// A wake that used the camera restarts in a short deep sleep and uploads in the fresh boot (restartForUpload).
RTC_DATA_ATTR bool upload_next = false;    // the coming timer wake is the second half of this wake
RTC_DATA_ATTR char upload_reason[12] = ""; // the first half's wake reason
RTC_DATA_ATTR uint32_t upload_before_ms = 0;  // how long the first half was awake
static uint32_t awake_before_ms = 0;       // the same, in the second half: counted in this wake's awake time
static const char *wake_reason = "";
static bool reached_hub = false;

static double clockNow() {
  struct timeval tv;
  gettimeofday(&tv, nullptr);
  return tv.tv_sec + tv.tv_usec / 1e6;
}

// ------------------------------------------------------------------ identity

static void loadIdentity() {
  Preferences p;
  p.begin("id");
#ifndef RELEASE_BUILD
  if (strlen(TRAP_ID) && strlen(API_KEY) && strncmp(API_KEY, "paste", 5) != 0 &&
      (p.getString("trap_id") != TRAP_ID || p.getString("api_key") != API_KEY)) {
    p.putString("trap_id", TRAP_ID);
    p.putString("api_key", API_KEY);
  }
#endif
  strlcpy(trap_id, p.getString("trap_id", "").c_str(), sizeof(trap_id));
  strlcpy(api_key, p.getString("api_key", "").c_str(), sizeof(api_key));
  p.end();
}

static void saveIdentity(const char *id, const char *key) {
  Preferences p;
  p.begin("id");
  p.putString("trap_id", id);
  p.putString("api_key", key);
  p.end();
  strlcpy(trap_id, id, sizeof(trap_id));
  strlcpy(api_key, key, sizeof(api_key));
}

static void forgetIdentity() {
  Preferences p;
  p.begin("id");
  p.clear();
  p.end();
  trap_id[0] = api_key[0] = 0;
}

static String pairingCode() {  // the last 6 hex digits of the MAC, written on the camera's sticker
  uint8_t mac[6];
  esp_read_mac(mac, ESP_MAC_WIFI_STA);
  char code[7];
  snprintf(code, sizeof(code), "%02X%02X%02X", mac[3], mac[4], mac[5]);
  return code;
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
  if (WiFi.status() == WL_CONNECTED) return true;
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
  if (reply["checkin_s"].is<int>()) checkin_s = reply["checkin_s"].as<int>();
  fw_offer = reply["firmware"]["version"] | "";
  fw_offer_md5 = reply["firmware"]["md5"] | "";
  fw_offer_size = reply["firmware"]["size"] | 0;
  photo_now = reply["photo_now"] | false;
  if (!reply["now"].is<double>()) return;
  double now_clock = clockNow();
  double new_offset = reply["now"].as<double>() - (sent_clock + now_clock) / 2;
  updateDrift(drift_ref, rate, now_clock, new_offset);
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
  if (api_key[0]) http.addHeader("Authorization", String("Bearer ") + api_key);
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
    meta["trap_id"] = trap_id;
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

// The last call of a wake: report status, get the schedule. Tells the hub this node is done.
static int askSchedule() {
  JsonDocument st, reply;
  st["last_error"] = last_error[0] ? last_error : nullptr;
  st["rssi"] = WiFi.RSSI();
  // Awake time per wake, for estimating power: this one so far, and the whole of the previous one.
  st["fw"] = FW_VERSION; st["boots"] = boots; st["wake"] = wake_reason; st["awake_ms"] = awake_before_ms + millis();
  if (prev_wake[0]) {
    st["prev_wake"] = prev_wake; st["prev_awake_ms"] = prev_awake_ms; st["prev_reached_hub"] = prev_reached_hub;
  }
  st["cpu_temp_c"] = temperatureRead(); st["drift_ppm"] = (rate - 1.0) * 1e6;
  Preferences p;
  p.begin("ota", true);
  if (p.getInt("tries", 0) >= OTA_MAX_TRIES) st["fw_failed"] = p.getString("version");
  p.end();
  reached_hub = true;
  String status;
  serializeJson(st, status);
  return post("/node/v1/schedule", "GET", nullptr, status, reply);
}

// ------------------------------------------------------------------ setup mode: live preview

static volatile uint32_t preview_until = 0;  // millis()
static volatile bool still_busy = false;     // the full-size photo has the camera: the stream waits

static esp_err_t indexHandler(httpd_req_t *req) {
  String page = String("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
      "<title>") + trap_id + " preview</title><body style='font:16px system-ui;margin:12px;background:#111;color:#eee'>"
      "<h1 style='font-size:20px'>" + trap_id + " live preview</h1>"
      "<p>Aim the camera so the liner fills the picture and is sharp. The preview stops by itself, then the "
      "camera takes its photo. <a style='color:#9cf' href='/still' target=_blank>Full-size photo</a> to check focus.</p>"
      "<img id=v style='width:100%;max-width:800px' alt='live preview'>"
      "<script>document.getElementById('v').src='http://'+location.hostname+':81/stream'</script>";
  httpd_resp_set_type(req, "text/html");
  return httpd_resp_send(req, page.c_str(), page.length());
}

static esp_err_t stillHandler(httpd_req_t *req) {
  still_busy = true;
  sensor_t *s = esp_camera_sensor_get();
  s->set_framesize(s, CAM_FRAMESIZE);
  for (int i = 0; i < 3; i++) { camera_fb_t *f = esp_camera_fb_get(); if (f) esp_camera_fb_return(f); }
  camera_fb_t *fb = esp_camera_fb_get();
  esp_err_t r = ESP_FAIL;
  if (fb) {
    httpd_resp_set_type(req, "image/jpeg");
    r = httpd_resp_send(req, (const char *)fb->buf, fb->len);
    esp_camera_fb_return(fb);
  } else {
    httpd_resp_send_500(req);
  }
  s->set_framesize(s, PREVIEW_FRAMESIZE);
  still_busy = false;
  return r;
}

static esp_err_t streamHandler(httpd_req_t *req) {
  httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=frame");
  while ((int32_t)(preview_until - millis()) > 0) {
    if (still_busy) { delay(50); continue; }
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) { delay(50); continue; }
    char head[96];
    int n = snprintf(head, sizeof(head), "\r\n--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", fb->len);
    esp_err_t r = httpd_resp_send_chunk(req, head, n);
    if (r == ESP_OK) r = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
    esp_camera_fb_return(fb);
    if (r != ESP_OK) return ESP_FAIL;  // the viewer went away
  }
  httpd_resp_send_chunk(req, nullptr, 0);
  return ESP_OK;
}

// Serve a live preview on the hub's Wi-Fi for SETUP_PREVIEW_S: the page on port 80, the stream on 81
// (one server can't serve the page while it streams). The hub lists it on its own page.
static void runPreview() {
  if (!connectWifi(60)) { setError("setup: hub Wi-Fi not reachable"); return; }
  if (!cameraInit()) { setError("camera not found"); return; }
  sensor_t *s = esp_camera_sensor_get();
  s->set_framesize(s, PREVIEW_FRAMESIZE);
  if (LED_PIN >= 0) { pinMode(LED_PIN, OUTPUT); digitalWrite(LED_PIN, HIGH); }

  httpd_handle_t web = nullptr, stream = nullptr;
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  httpd_uri_t index = {"/", HTTP_GET, indexHandler, nullptr}, still = {"/still", HTTP_GET, stillHandler, nullptr};
  if (httpd_start(&web, &cfg) == ESP_OK) { httpd_register_uri_handler(web, &index); httpd_register_uri_handler(web, &still); }
  cfg.server_port = 81; cfg.ctrl_port += 1;
  httpd_uri_t live = {"/stream", HTTP_GET, streamHandler, nullptr};
  if (httpd_start(&stream, &cfg) == ESP_OK) httpd_register_uri_handler(stream, &live);

  preview_until = millis() + SETUP_PREVIEW_S * 1000UL;
  String url = "http://" + WiFi.localIP().toString() + "/";
  Serial.printf("live preview at %s for %d s\n", url.c_str(), SETUP_PREVIEW_S);
  JsonDocument m, reply;
  m["url"] = url; m["seconds"] = SETUP_PREVIEW_S;
  String meta;
  serializeJson(m, meta);
  post("/node/v1/preview", "POST", nullptr, meta, reply);  // the hub lists it on its page (and gives the time)

  while ((int32_t)(preview_until - millis()) > 0) delay(200);
  delay(500);  // let an open stream see the deadline and end
  if (stream) httpd_stop(stream);
  if (web) httpd_stop(web);
  if (LED_PIN >= 0) digitalWrite(LED_PIN, LOW);
  esp_camera_deinit();
}

// After the camera has run, uploads from the same boot crawl or fail for the rest of the wake (Oct 22 2026,
// RedRover: every wake with a photo or the preview, while the check-ins between them, which don't use the
// camera, sent 3 photos in a second). A deep sleep resets the chip, so upload from a fresh boot.
static void restartForUpload(const char *reason) {
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  upload_next = true;
  strlcpy(upload_reason, reason, sizeof(upload_reason));
  upload_before_ms = millis();
  Serial.println("restarting to upload");
  Serial.flush();
  esp_sleep_enable_timer_wakeup(200000);
  esp_deep_sleep_start();
}

// On a button wake: released before SETUP_HOLD_MS means a new liner (0), held past it setup mode (1),
// and held past RESET_HOLD_MS forget the trap id and key (2).
static int buttonHeld() {
  if (BUTTON_PIN < 0) return 0;
  rtc_gpio_deinit((gpio_num_t)BUTTON_PIN);
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  uint32_t start = millis();
  while (digitalRead(BUTTON_PIN) == LOW) {
    if (millis() - start >= RESET_HOLD_MS) return 2;
    delay(20);
  }
  return millis() - start >= SETUP_HOLD_MS ? 1 : 0;
}

// ------------------------------------------------------------------ pairing and updates

static void sleepFor(double s) {
  Serial.printf("sleeping %.0f s, awake %lu ms\n", s, (unsigned long)millis());
  Serial.flush();
  esp_sleep_enable_timer_wakeup((uint64_t)(s * 1e6));
  if (BUTTON_PIN >= 0) esp_sleep_enable_ext0_wakeup((gpio_num_t)BUTTON_PIN, 0);
  esp_deep_sleep_start();
}

// A camera with no trap id or key: ask the hub to be added, then start like a fresh install. Never returns.
static void pairWake() {
  String code = pairingCode();
  Serial.printf("not added yet: pairing code %s\n", code.c_str());
  if (connectWifi(pair_tries < PAIR_FAST_TRIES ? 20 : 60)) {
    JsonDocument m, reply;
    m["code"] = code; m["fw"] = FW_VERSION; m["rssi"] = WiFi.RSSI();
    String meta;
    serializeJson(m, meta);
    int c = post("/node/v1/pair", "POST", nullptr, meta, reply);
    const char *id = reply["trap_id"] | "", *key = reply["api_key"] | "";
    if (c == 200 && id[0] && key[0] && strlen(id) < sizeof(trap_id) && strlen(key) < sizeof(api_key)) {
      saveIdentity(id, key);
      Serial.printf("added on the dashboard as %s\n", trap_id);
      pair_tries = 0;
      WiFi.disconnect(true);
      esp_restart();  // as if just powered on: the live preview for aiming, then the first photo
    }
    Serial.printf("pair -> %d (waiting to be added on the dashboard)\n", c);
  } else {
    setError("hub not reachable");
  }
  pair_tries++;
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  sleepFor(pair_tries <= PAIR_FAST_TRIES ? 30 : 600);
}

// The firmware the hub offers, if it is new to this node and hasn't already failed here. Restarts into it.
static void maybeUpdate() {
  if (!fw_offer.length() || fw_offer == FW_VERSION || !fw_offer_size || fw_offer_md5.length() != 32) return;
  Preferences p;
  p.begin("ota");
  if (p.getString("version") != fw_offer) { p.putString("version", fw_offer); p.putInt("tries", 0); }
  int tries = p.getInt("tries", 0);
  if (tries >= OTA_MAX_TRIES) { p.end(); return; }  // it failed here: wait for a different version
  p.putInt("tries", tries + 1);  // counted before trying: a crash or a rollback counts too
  p.end();
  Serial.printf("updating firmware %s -> %s (%u bytes)\n", FW_VERSION, fw_offer.c_str(), (unsigned)fw_offer_size);
  HTTPClient http;
  http.begin(String(HUB_URL) + "/node/v1/firmware");
  http.setTimeout(30000);
  http.addHeader("Authorization", String("Bearer ") + api_key);
  int code = http.GET();
  bool ok = code == 200 && http.getSize() == (int)fw_offer_size && Update.begin(fw_offer_size);
  if (ok) {
    Update.setMD5(fw_offer_md5.c_str());
    ok = Update.writeStream(*http.getStreamPtr()) == fw_offer_size && Update.end();
    if (!ok) Update.abort();
  }
  http.end();
  if (!ok) { Serial.printf("firmware -> %d, %s\n", code, Update.errorString()); setError("firmware update failed"); return; }
  Serial.println("firmware written: restarting into it");
  Serial.flush();
  WiFi.disconnect(true);
  esp_restart();
}

// The first boot of new firmware: the bootloader keeps it only once it says so here.
static bool firmwareOnTrial() {
  esp_ota_img_states_t st;
  return esp_ota_get_state_partition(esp_ota_get_running_partition(), &st) == ESP_OK && st == ESP_OTA_IMG_PENDING_VERIFY;
}

// Arduino would mark new firmware good as soon as it boots; this firmware waits until it has reached the hub.
extern "C" bool verifyRollbackLater() { return true; }

// ------------------------------------------------------------------ sleep

// Seconds of hub time until the next wake on the hub's schedule, or -1 without one. The hub sends the next
// 12 wakes; once those have passed (the hub was out of reach for days), its schedule repeats daily, so the
// same times a whole number of days later are used rather than falling back to frequent blind retries.
static double untilNextWake(double hub_now) {
  if (!synced || n_wakes == 0) return -1;
  for (int days = 0; days <= 60; days++) {
    for (int i = 0; i < n_wakes; i++) {
      double real = wakes[i] + days * 86400.0 - hub_now;
      if (real >= 60) return real;
    }
  }
  return -1;
}

static bool haveSchedule() { return untilNextWake(clockNow() + offset) >= 0; }

static void sleepUntilNextWake() {
  double now = clockNow();
  double real = untilNextWake(now + offset);
  double sleep_clock;
  checkin_next = false;
  if (real >= 0) {
    retries = 0;
    if (checkin_s > 0 && real > checkin_s + 120) {
      // Check in before then, in case a photo is asked for on the dashboard. Timing needn't be exact.
      sleep_clock = checkin_s / rate;
      checkin_next = true;
    } else {
      // Wake early by a margin that grows with the sleep, then convert hub seconds to RTC seconds.
      double margin = 15 + 0.003 * real;
      sleep_clock = (real - margin) / rate;
    }
  } else {
    // No schedule yet: look for the hub again, less often each time, so a node that never finds it
    // does not flatten its battery (the hub is up for a few minutes after each of its wakes).
    sleep_clock = std::min(UNSYNCED_SLEEP_MAX_S, UNSYNCED_SLEEP_S << std::min(retries, 4));
    retries++;
  }
  if (sleep_clock < 30) sleep_clock = 30;
  Serial.printf("sleeping %.0f s%s, awake %lu ms\n", sleep_clock, checkin_next ? " (check-in)" : "", (unsigned long)millis());
  prev_awake_ms = awake_before_ms + millis();
  strlcpy(prev_wake, wake_reason, sizeof(prev_wake));
  prev_reached_hub = reached_hub;
  Serial.flush();
  esp_sleep_enable_timer_wakeup((uint64_t)(sleep_clock * 1e6));
  if (BUTTON_PIN >= 0) esp_sleep_enable_ext0_wakeup((gpio_num_t)BUTTON_PIN, 0);
  esp_deep_sleep_start();
}

void setup() {
  Serial.begin(115200);
  esp_sleep_wakeup_cause_t cause = esp_sleep_get_wakeup_cause();
  bool upload = cause == ESP_SLEEP_WAKEUP_TIMER && upload_next;  // the photo is taken: just upload it
  upload_next = false;
  if (upload) awake_before_ms = upload_before_ms;
  else boots++;
  if (session == 0) session = esp_random() | 1;
  bool checkin = cause == ESP_SLEEP_WAKEUP_TIMER && checkin_next && !upload;
  bool button = cause == ESP_SLEEP_WAKEUP_EXT0;
  int hold = button ? buttonHeld() : 0;
  // A timer wake without a schedule is only a search for the hub (see sleepUntilNextWake).
  bool search = cause == ESP_SLEEP_WAKEUP_TIMER && !checkin && !upload && retries > 0;
  // New firmware's first boot only checks that it reaches the hub: no preview, no photo.
  bool trial = firmwareOnTrial();
  // Powered on (installing it) or BOOT held: live preview first. A button wake means a fresh liner either way.
  bool setup_mode = !trial && ((cause != ESP_SLEEP_WAKEUP_TIMER && !button) || hold == 1);
  const char *reason = trial ? "update" : upload ? upload_reason : setup_mode ? "setup" : checkin ? "checkin" : search ? "search" : cause == ESP_SLEEP_WAKEUP_TIMER ? "scheduled" : "manual";
  wake_reason = reason;
  Serial.printf("\n%s\n", fw_marker);
  loadIdentity();
  Serial.printf("sentinel node %s fw %s wake=%s%s boots=%lu synced=%d\n", trap_id[0] ? trap_id : "(not added)", FW_VERSION,
                reason, upload ? " (upload)" : "", (unsigned long)boots, synced);

  if (!LittleFS.begin(true)) setError("flash filesystem failed");
  LittleFS.mkdir("/q");
  if (hold == 2) {  // BOOT held 10 s: forget the trap id, key and queued photos, and pair again
    Serial.println("button held 10 s: forgetting this camera's trap id and key");
    forgetIdentity();
    File dir = LittleFS.open("/q");
    std::vector<String> names;
    for (File f = dir.openNextFile(); f; f = dir.openNextFile()) names.push_back(String("/q/") + f.name());
    for (const String &n : names) LittleFS.remove(n);
    pair_tries = 0;
  }
  if (!api_key[0]) pairWake();
  if (setup_mode) runPreview();
  // A check-in takes no photo unless one was asked for. A search wake (no schedule) takes none either,
  // or the queue fills with them.
  if (!upload && !checkin && !search && !trial) {
    captureToQueue(reason, button);
    restartForUpload(reason);
  }

  double real_margin = haveSchedule() ? 15 + 0.003 * 43200 : 0;  // as early as we might have woken
  // A photo wake waits up to 5 min for the hub. With the hub down, that is 5 min of Wi-Fi on every photo
  // wake, so after one miss it tries briefly until the hub answers again (a check-in resets it too).
  int connect_s = trial ? RETRY_CONNECT_S : checkin ? CHECKIN_CONNECT_S : search ? RETRY_CONNECT_S
                  : hub_misses > 0 ? HUB_DOWN_CONNECT_S
                  : std::min(CONNECT_MAX_S, CONNECT_MIN_S + (int)(2 * real_margin));
  uint32_t until = millis() + connect_s * 1000UL;
  if (connectWifi(connect_s)) {
    // The hub's Wi-Fi can be up before its gateway opens (it is still booting or photographing its
    // own liner), so keep trying it for the rest of this wake's window. A check-in tries once.
    int code = uploadQueue();
    for (int tries = 1; !checkin && code != 0 && code != 401 && (int32_t)(until - millis()) > 5000; tries++) {
      delay(5000);
      if (tries % 3 == 0) {  // still failing on a connection that reads as up: it may be stale, so make a new one
        WiFi.disconnect(true);
        delay(200);
      }
      if (WiFi.status() != WL_CONNECTED) connectWifi(std::max(10, (int)((int32_t)(until - millis()) / 1000)));
      code = uploadQueue();
    }
    if (code == 0) {
      hub_misses = 0;
      int sched = askSchedule();
      if (trial && sched == 200) {
        esp_ota_mark_app_valid_cancel_rollback();
        Preferences p;
        p.begin("ota");
        p.clear();
        p.end();
        Serial.printf("firmware %s reached the hub: keeping it\n", FW_VERSION);
        trial = false;
      }
      if (!trial && sched == 200) maybeUpdate();  // restarts into the new firmware if there is one
      if (photo_now) {  // asked for on the dashboard since this node's last photo
        Serial.println("photo asked for on the dashboard");
        if (captureToQueue("requested", false)) restartForUpload("requested");
      }
    } else if (code != 401 && !checkin) {
      setError("hub not answering");
      if (!search) hub_misses++;
    }
  } else if (!checkin) {
    setError("hub not reachable");
    if (!search) hub_misses++;
  }
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  if (trial) {  // the new firmware didn't reach the hub: back to the one before it
    setError("new firmware didn't reach the hub: going back");
    Serial.flush();
    esp_ota_mark_app_invalid_rollback_and_reboot();
  }
  sleepUntilNextWake();
}

void loop() {}
