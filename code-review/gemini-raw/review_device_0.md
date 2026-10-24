Here is the thorough, read-only code review of **Chunk 1 of 3** covering `device/esp32-node/`, device setup scripts, configuration templates, and repository documentation.

---

### 1. BUGS (Correctness, Crashes, Race Conditions, Leaks, State Gaps)

#### [main.cpp:196-201](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L196-L201) — RTC Drift Rate Calculation Never Runs on Normal Schedules
- **Severity**: High
- **Quoted Code**:
  ```cpp
  196|   if (synced && now_clock - sync_clock > 3600) {
  197|     // Over the last stretch the hub's time moved (now_clock - sync_clock) + (new_offset - offset) seconds.
  198|     double r = ((now_clock - sync_clock) + (new_offset - offset)) / (now_clock - sync_clock);
  199|     if (r > 0.9 && r < 1.1) rate = 0.7 * rate + 0.3 * r;
  200|   }
  201|   offset = new_offset; sync_clock = now_clock; synced = true;
  ```
- **Failure Scenario**:
  `sync_clock` is updated to `now_clock` unconditionally on *every* hub contact (line 201). By default, check-ins run every 30 minutes (`checkin_min = 30`), and testing bench hubs wake every 15 minutes. Because contacts happen every 15–30 minutes, `now_clock - sync_clock` is always ~900–1800 seconds and never exceeds `3600`. Consequently, `rate` is never recalculated and remains permanently stuck at `1.0`. Clock drift correction over sleep cycles fails to operate as designed.
- **Suggested Fix**:
  Update `sync_clock` only when the elapsed time exceeds 3600 seconds, or decouple the drift reference timestamp from the last contact timestamp:
  ```cpp
  if (synced && (now_clock - sync_clock > 3600)) {
    double r = ((now_clock - sync_clock) + (new_offset - offset)) / (now_clock - sync_clock);
    if (r > 0.9 && r < 1.1) rate = 0.7 * rate + 0.3 * r;
    sync_clock = now_clock;
  } else if (!synced) {
    sync_clock = now_clock;
  }
  offset = new_offset;
  synced = true;
  ```

---

#### [main.cpp:507-510](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L507-L510) — Infinite Photo Capture & Reboot Loop on Dashboard Request
- **Severity**: Critical
- **Quoted Code**:
  ```cpp
  506|       askSchedule();
  507|       if (photo_now) {  // asked for on the dashboard since this node's last photo
  508|         Serial.println("photo asked for on the dashboard");
  509|         if (captureToQueue("requested", false)) restartForUpload("requested");
  510|       }
  ```
- **Failure Scenario**:
  When "Take a photo now" is triggered, the node receives `photo_now = true` in `askSchedule()`, captures a photo, and calls `restartForUpload("requested")`. Upon restarting, the node uploads the photo and immediately executes `askSchedule()` again (line 506). If the hub has not yet received confirmation from the backend server or cleared its internal flag within that sub-second upload window, `photo_now` remains `true`. The node immediately captures another photo and reboots again, entering an infinite loop that drains the battery and overflows LittleFS.
- **Suggested Fix**:
  Do not honor `photo_now` if the current wake was already fulfilling a `"requested"` capture:
  ```cpp
  if (photo_now && strcmp(wake_reason, "requested") != 0) {
    Serial.println("photo asked for on the dashboard");
    if (captureToQueue("requested", false)) restartForUpload("requested");
  }
  ```

---

#### [main.cpp:263-270](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L263-L270) — Non-200/4xx HTTP Responses Block Queue and Loop Retries
- **Severity**: High
- **Quoted Code**:
  ```cpp
  263|     if (code == 200 || code == 201 || code == 413 || code == 415 || code == 422) {
  264|       if (code >= 400) setError("hub refused a photo");
  265|       LittleFS.remove(stem + ".jpg"); LittleFS.remove(stem + ".json");
  266|       if (code < 400) last_error[0] = 0;
  267|     } else {
  268|       if (code == 401) setError("hub does not know this trap's key");
  269|       return code == 0 ? -1 : code;
  270|     }
  ```
- **Failure Scenario**:
  If the gateway or upstream server returns HTTP `409 Conflict` (for duplicate captures already received) or HTTP `400 Bad Request`, `code` falls into the `else` block (line 267). `uploadQueue()` exits immediately and returns `code`. In `setup()`, the retry loop checks `code != 0 && code != 401` and continues retrying the exact same conflicting photo every 5 seconds until the 2–5 minute connect window expires. The unprocessable photo is never removed from LittleFS, permanently blocking all subsequent queued photos behind it across future boots.
- **Suggested Fix**:
  Include `409` (and optionally `400`) in the terminal/discard status list:
  ```cpp
  if (code == 200 || code == 201 || code == 409 || code == 413 || code == 415 || code == 422) {
    if (code >= 400 && code != 409) setError("hub refused a photo");
    LittleFS.remove(stem + ".jpg"); LittleFS.remove(stem + ".json");
    if (code < 400 || code == 409) last_error[0] = 0;
  }
  ```

---

#### [main.cpp:310-344](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L310-L344) — Race Condition and Driver Panic between Live Stream and Full-Size Still
- **Severity**: High
- **Quoted Code**:
  ```cpp
  310| static esp_err_t stillHandler(httpd_req_t *req) {
  311|   still_busy = true;
  312|   sensor_t *s = esp_camera_sensor_get();
  313|   s->set_framesize(s, CAM_FRAMESIZE);
  ...
  324|   s->set_framesize(s, PREVIEW_FRAMESIZE);
  325|   still_busy = false;
  326|   return r;
  327| }
  ...
  331|   while ((int32_t)(preview_until - millis()) > 0) {
  332|     if (still_busy) { delay(50); continue; }
  333|     camera_fb_t *fb = esp_camera_fb_get();
  ```
- **Failure Scenario**:
  The web server (port 80) and stream server (port 81) execute in separate FreeRTOS tasks. Synchronization between `stillHandler` and `streamHandler` relies solely on `volatile bool still_busy` without a mutex. If `stillHandler` calls `s->set_framesize(s, CAM_FRAMESIZE)` while `streamHandler` is executing `esp_camera_fb_get()` or while DMA transfer is underway, the ESP32 camera driver faults or panics due to mismatched sensor registers and DMA buffer descriptors. Furthermore, `still_busy` is set to `false` before `httpd_resp_send()` finishes if `fb` is null.
- **Suggested Fix**:
  Protect all camera sensor frame-size adjustments and buffer captures with a FreeRTOS mutex (`SemaphoreHandle_t`), ensuring exclusive access to the camera peripheral across both handlers.

---

#### [main.cpp:372-377](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L372-L377) — Use-After-Free / Panic on Setup Preview Teardown
- **Severity**: High
- **Quoted Code**:
  ```cpp
  372|   while ((int32_t)(preview_until - millis()) > 0) delay(200);
  373|   delay(500);  // let an open stream see the deadline and end
  374|   if (stream) httpd_stop(stream);
  375|   if (web) httpd_stop(web);
  376|   if (LED_PIN >= 0) digitalWrite(LED_PIN, LOW);
  377|   esp_camera_deinit();
  ```
- **Failure Scenario**:
  `delay(500)` makes an unverified assumption that `streamHandler` will exit its loop and terminate within 500 ms. If a connected client has a stalled TCP connection, `streamHandler` blocks inside `httpd_resp_send_chunk()` for several seconds. Calling `esp_camera_deinit()` while `streamHandler` is actively holding or freeing camera frame buffers leads to an invalid memory access or assertion failure in `esp_camera`.
- **Suggested Fix**:
  Track active streaming connections using an atomic counter or FreeRTOS event group, and wait for `streamHandler` to exit cleanly before calling `esp_camera_deinit()`.

---

#### [main.cpp:153-163](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L153-L163) — Orphaned Empty `.json` Files on JPEG Write Failure
- **Severity**: Medium
- **Quoted Code**:
  ```cpp
  153|   File jpg = LittleFS.open(String(stem) + ".jpg", "w");
  154|   bool ok = jpg && jpg.write(fb->buf, fb->len) == fb->len;
  155|   jpg.close();
  156|   File js = LittleFS.open(String(stem) + ".json", "w");
  157|   ok = ok && js && serializeJson(meta, js) > 0;
  158|   js.close();
  ...
  162|   if (!ok) { LittleFS.remove(String(stem) + ".jpg"); setError("could not save photo"); }
  ```
- **Failure Scenario**:
  If writing the JPEG fails (e.g. flash write error or out-of-space), `ok` evaluates to `false`. On line 156, `File js = LittleFS.open(..., "w")` still executes and truncates/creates a 0-byte `.json` file on flash. Because `ok` is false, `serializeJson` short-circuits. On line 162, `LittleFS.remove(stem + ".jpg")` is called, but the orphaned 0-byte `.json` file is never deleted. Because `uploadQueue()` only searches for `.jpg` files, these orphaned `.json` files permanently leak flash storage.
- **Suggested Fix**:
  Only open the JSON file if the JPEG write succeeded, and delete both files on any failure:
  ```cpp
  bool ok = false;
  File jpg = LittleFS.open(String(stem) + ".jpg", "w");
  if (jpg && jpg.write(fb->buf, fb->len) == fb->len) {
    jpg.close();
    File js = LittleFS.open(String(stem) + ".json", "w");
    if (js && serializeJson(meta, js) > 0) {
      ok = true;
    }
    if (js) js.close();
  } else if (jpg) {
    jpg.close();
  }
  if (!ok) {
    LittleFS.remove(String(stem) + ".jpg");
    LittleFS.remove(String(stem) + ".json");
    setError("could not save photo");
  }
  ```

---

#### [main.cpp:137](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L137) & [main.cpp:230](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L230) — Directory Handle Leak and Mutation While Open
- **Severity**: Medium
- **Quoted Code**:
  ```cpp
  137|   File dir = LittleFS.open("/q");
  138|   for (File f = dir.openNextFile(); f; f = dir.openNextFile()) if (String(f.name()).endsWith(".jpg")) names.push_back(f.name());
  ...
  142|     LittleFS.remove(stem + ".jpg"); LittleFS.remove(stem + ".json");
  ```
  ```cpp
  230|   File dir = LittleFS.open("/q");
  231|   for (File f = dir.openNextFile(); f; f = dir.openNextFile()) if (String(f.name()).endsWith(".jpg")) names.push_back(f.name());
  ...
  265|       LittleFS.remove(stem + ".jpg"); LittleFS.remove(stem + ".json");
  ```
- **Failure Scenario**:
  In both `captureToQueue()` and `uploadQueue()`, `dir.close()` is never called. Furthermore, `LittleFS.remove()` is called while `dir` remains open in the same scope. In LittleFS / ESP-IDF VFS, modifying directory contents while holding an open directory descriptor can corrupt traversal state or leak internal VFS directory structures across prolonged wake cycles.
- **Suggested Fix**:
  Explicitly call `dir.close()` immediately after collecting the file names into the `names` vector, prior to any sorting, file uploading, or deletion.

---

#### [main.cpp:47-68](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L47-L68) & [main.cpp:466](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L466) — Uninitialized `RTC_DATA_ATTR` Variables on Power-On Cold Boot
- **Severity**: Medium
- **Quoted Code**:
  ```cpp
  47| RTC_DATA_ATTR uint32_t session = 0;        // random per power-on: photos from an older session have no usable clock
  48| RTC_DATA_ATTR bool synced = false;
  49| RTC_DATA_ATTR double offset = 0;           // hub unix time - clock
  50| RTC_DATA_ATTR double sync_clock = 0;       // clock at that measurement
  51| RTC_DATA_ATTR double rate = 1.0;           // real seconds per clock second while asleep
  52| RTC_DATA_ATTR int64_t wakes[MAX_WAKES];    // upcoming wake times (hub unix seconds)
  53| RTC_DATA_ATTR int n_wakes = 0;
  ...
  466|   if (session == 0) session = esp_random() | 1;
  ```
- **Failure Scenario**:
  On an ESP32 power-on reset or following power fluctuations/brownouts, SRAM in the RTC fast/slow memory segment can retain arbitrary non-zero garbage. If `session == 0` is used to detect cold boots, none of the other RTC variables (`synced`, `rate`, `n_wakes`, `retries`) are sanitized or reset. If `n_wakes` contains an uninitialized large integer, `untilNextWake()` (line 416) loops out of bounds past `MAX_WAKES` and reads garbage memory. If `rate` evaluates to `0.0`, `NaN`, or negative, `sleepUntilNextWake()` produces a divide-by-zero or crash.
- **Suggested Fix**:
  Reset all RTC state variables when `session == 0` or when `cause == ESP_SLEEP_WAKEUP_UNDEFINED`:
  ```cpp
  if (session == 0 || cause == ESP_SLEEP_WAKEUP_UNDEFINED) {
    session = esp_random() | 1;
    synced = false;
    offset = 0;
    sync_clock = 0;
    rate = 1.0;
    n_wakes = 0;
    retries = 0;
    boots = 0;
    upload_next = false;
    checkin_next = false;
    last_error[0] = '\0';
    prev_wake[0] = '\0';
  }
  ```

---

#### [install.sh:14](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/install.sh#L14) — User Group Assignment Skipped if User Exists
- **Severity**: Medium
- **Quoted Code**:
  ```bash
  14| id -u sentinel >/dev/null 2>&1 || useradd --system --create-home --groups video,gpio,i2c sentinel
  ```
- **Failure Scenario**:
  If the `sentinel` user was previously created by `install-hub.sh` (which runs `useradd --system --create-home sentinel` without supplemental groups) or created during system provisioning, `id -u sentinel` succeeds (exit code 0). The `useradd` command is skipped, and `sentinel` is never added to the `video`, `gpio`, and `i2c` groups. When `sentinel-cycle` runs as user `sentinel`, it lacks permissions to open `/dev/video*`, access GPIOs via `lgpio`, or communicate over I2C with the SHT45/INA219 sensors.
- **Suggested Fix**:
  Unconditionally ensure group memberships if the user already exists:
  ```bash
  if id -u sentinel >/dev/null 2>&1; then
    usermod -a -G video,gpio,i2c sentinel
  else
    useradd --system --create-home --groups video,gpio,i2c sentinel
  fi
  ```

---

### 2. Security Issues

#### [main.cpp:297-344](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L297-L344) — Unauthenticated Web Server and Live Camera Stream
- **Severity**: Medium
- **Quoted Code**:
  ```cpp
  357|   httpd_uri_t index = {"/", HTTP_GET, indexHandler, nullptr}, still = {"/still", HTTP_GET, stillHandler, nullptr};
  358|   if (httpd_start(&web, &cfg) == ESP_OK) { httpd_register_uri_handler(web, &index); httpd_register_uri_handler(web, &still); }
  359|   cfg.server_port = 81; cfg.ctrl_port += 1;
  360|   httpd_uri_t live = {"/stream", HTTP_GET, streamHandler, nullptr};
  361|   if (httpd_start(&stream, &cfg) == ESP_OK) httpd_register_uri_handler(stream, &live);
  ```
- **Failure Scenario**:
  Setup mode starts an HTTP server on port 80 and port 81 without any authentication or CSRF tokens. Documentation explicitly recommends using shared university networks (e.g. Cornell's `RedRover`, documented in [esp32-traps.md:147-153](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/esp32-traps.md#L147-L153)) where device isolation is absent. Any student or device on the same subnet can access `http://<node-ip>/`, view live trap imagery, or trigger repeated full-frame captures via `/still`, starving the preview task of memory.
- **Suggested Fix**:
  Require a shared secret or verification token query parameter (e.g. `/?key=...` matching `API_KEY`) before serving index, still, or stream endpoints.

---

#### [node_config.example.h:11](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/include/node_config.example.h#L11) & [main.cpp:211-213](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L211-L213) — Cleartext HTTP and Bearer Tokens over Wi-Fi
- **Severity**: Medium
- **Quoted Code**:
  ```cpp
  11| #define HUB_URL "http://10.42.0.1:8080"
  ```
  ```cpp
  211|   http.begin(String(HUB_URL) + path);
  212|   http.setTimeout(20000);
  213|   http.addHeader("Authorization", String("Bearer ") + API_KEY);
  ```
- **Failure Scenario**:
  All communication between the ESP32 node and the hub gateway is transmitted over plain HTTP over Wi-Fi. In environments like `RedRover` where `WIFI_PASSWORD ""` is used, the `API_KEY` is broadcast in unencrypted HTTP headers, allowing eavesdroppers to obtain the trap's credentials and upload forged captures or deplete server resources.
- **Suggested Fix**:
  Enforce WPA2/WPA3 encryption on the hub access point at all times, and disallow unencrypted networks in production. If deployed across shared networks, use HTTPS with TLS verification (`WiFiClientSecure`).

---

### 3. Deprecated APIs / Outdated Patterns

#### [main.cpp:20](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L20) & [main.cpp:398](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L398) — Deprecated ESP-IDF RTC GPIO & Sensor APIs
- **Severity**: Low
- **Quoted Code**:
  ```cpp
  20| #include "driver/rtc_io.h"
  ...
  398|   rtc_gpio_deinit((gpio_num_t)BUTTON_PIN);
  ...
  455|   if (BUTTON_PIN >= 0) esp_sleep_enable_ext0_wakeup((gpio_num_t)BUTTON_PIN, 0);
  ```
- **Failure Scenario**:
  `driver/rtc_io.h`, `rtc_gpio_deinit()`, and `esp_sleep_enable_ext
Continuing from where the response cut off under **3. Deprecated APIs / Outdated Patterns**:

```cpp
20| #include "driver/rtc_io.h"
...
398|   rtc_gpio_deinit((gpio_num_t)BUTTON_PIN);
...
455|   if (BUTTON_PIN >= 0) esp_sleep_enable_ext0_wakeup((gpio_num_t)BUTTON_PIN, 0);
```
- **Failure Scenario**:
  In ESP-IDF v5 (and Arduino-ESP32 3.x), `rtc_gpio_*` functions and `esp_sleep_enable_ext0_wakeup` are deprecated on ESP32-S3. While currently compiling under `espressif32@6.9.0` (Arduino-ESP32 2.0.17 / ESP-IDF 4.4), upgrading the toolchain will produce deprecation errors or build failures. Additionally, legacy `temperatureRead()` ([main.cpp:252, 285](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L252)) has been replaced by the dedicated `temperature_sensor` driver.
- **Suggested Fix**:
  Migrate to modern deep sleep wakeup APIs (`esp_deep_sleep_enable_gpio_wakeup` or `esp_sleep_enable_ext1_wakeup`) and use `gpio_reset_pin()` in place of `rtc_gpio_deinit()`.

---

### 4. Inconsistencies

#### [main.cpp:251](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L251) vs [main.cpp:281](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L281) — Field Naming Inconsistency Between Capture and Schedule Requests
- **Severity**: Medium
- **Quoted Code**:
  ```cpp
  // uploadQueue() - POST /node/v1/captures
  251|     dev["sw_version"] = FW_VERSION; dev["rssi"] = WiFi.RSSI(); dev["boots"] = boots;
  ...
  // askSchedule() - GET /node/v1/schedule
  281|   st["fw"] = FW_VERSION; st["boots"] = boots; st["wake"] = wake_reason; st["awake_ms"] = awake_before_ms + millis();
  ```
- **Failure Scenario**:
  In `/node/v1/captures`, firmware version is named `sw_version` and wake reason is `wake_reason` (line 128). In `/node/v1/schedule`, the same values are named `fw` and `wake`. This discrepancy creates dual-parsing logic in `gateway.py` and downstream database stores, risking `null` values if gateway validation expects consistent schemas.
- **Suggested Fix**:
  Standardize on consistent field names across all endpoints: `sw_version` and `wake_reason`.

---

#### [hub.example.toml:16-20](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/hub.example.toml#L16-L20) vs [config.example.toml:54-61](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/config.example.toml#L54-L61) — Divergent Config Keys
- **Severity**: Low
- **Quoted Code**:
  ```toml
  # hub.example.toml:
  16| [hub]
  17| enabled = true
  18| port = 8080
  19| node_offset_s = 60
  20| checkin_min = 30
  ```
  ```toml
  # config.example.toml:
  54| [hub]
  58| enabled = false
  59| port = 8080
  60| window_s = 240
  61| node_offset_s = 60
  ```
- **Failure Scenario**:
  `config.example.toml` contains `window_s` but lacks `checkin_min`. `hub.example.toml` contains `checkin_min` but lacks `window_s`. If a user enables hub mode on a camera-equipped Pi using `config.example.toml`, `gateway.py` will fall back to implicit defaults or fail to configure camera node check-in intervals properly.
- **Suggested Fix**:
  Include all `[hub]` configuration options in both templates with documented defaults (`window_s = 240`, `checkin_min = 30`).

---

### 5. Dead Code, Duplication, and Coupling

#### [install-hub.sh:11, 17](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/install-hub.sh#L11) & [pyproject.toml:6-11](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/pyproject.toml#L6-L11) — Unnecessary Heavy Dependencies on Headless Hub Pi
- **Severity**: Medium
- **Quoted Code**:
  ```bash
  11| apt-get install -y python3-venv
  ...
  17| /opt/sentinel/venv/bin/pip install .
  ```
  ```toml
  6| dependencies = [
  7|     "requests>=2.31",
  8|     "smbus2>=0.4",
  9|     "numpy>=1.24",
  10|     "pillow>=10.0",
  11| ]
  ```
- **Failure Scenario**:
  The hub Pi has no camera, LED, or sensors ([docs/esp32-traps.md:28](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/esp32-traps.md#L28)). It only forwards requests via `gateway.py`. Yet `install-hub.sh` installs the entire `sentinel-device` package, requiring `numpy`, `pillow`, and `smbus2`. Because `install-hub.sh` omits build dependencies (`gcc`, `python3-dev`), installing `smbus2` or compiling wheels can fail or require huge wheel downloads on bandwidth-constrained field cellular links.
- **Suggested Fix**:
  Split dependencies into optional groups in `pyproject.toml` (e.g. `gateway = ["requests"]`, `trap = ["smbus2", "numpy", "pillow"]`) and install only gateway dependencies in `install-hub.sh`.

---

#### [partitions.csv:4-5](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/partitions.csv#L4-L5) — Unused OTA Partition
- **Severity**: Low
- **Quoted Code**:
  ```csv
  4| otadata,  data, ota,      0xe000,   0x2000
  5| app0,     app,  ota_0,    0x10000,  0x200000
  ```
- **Failure Scenario**:
  The file header states `# no over-the-air updates`. However, `otadata` (8 KB) and subtype `ota_0` are still present without a corresponding `ota_1` partition.
- **Suggested Fix**:
  Change `app0` subtype from `ota_0` to `factory` and remove the `otadata` row to reclaim flash for LittleFS.

---

### 6. Performance and Optimization Opportunities

#### [main.cpp:488-491](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L488-L491) — Battery Depletion when Hub is Unreachable After Initial Sync
- **Severity**: High
- **Quoted Code**:
  ```cpp
  488|   double real_margin = haveSchedule() ? 15 + 0.003 * 43200 : 0;  // as early as we might have woken
  489|   int connect_s = checkin ? CHECKIN_CONNECT_S : search ? RETRY_CONNECT_S
  490|                           : std::min(CONNECT_MAX_S, CONNECT_MIN_S + (int)(2 * real_margin));
  491|   uint32_t until = millis() + connect_s * 1000UL;
  ```
- **Failure Scenario**:
  If the node has synced once, `haveSchedule()` returns `true`. If the hub subsequently loses power or goes offline, `connect_s` evaluates to `std::min(300, 120 + 289) = 300` seconds (5 minutes). The node keeps its Wi-Fi radio at maximum TX power attempting to connect and retry every 5 seconds for 5 full minutes on every wake slot. At 6 wakes a day, this burns 30 minutes of continuous radio transmission daily, draining the battery in days.
- **Suggested Fix**:
  Implement progressive backoff on connection failure even when a schedule is present, capping failed scheduled connects to 60 seconds after the first failure.

---

#### [main.cpp:217-218](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L217-L218) — Non-Streaming String Metadata Header
- **Severity**: Medium
- **Quoted Code**:
  ```cpp
  214|   if (meta.length()) http.addHeader("X-Sentinel-Meta", meta);
  ...
  217|   if (body) { http.addHeader("Content-Type", "image/jpeg"); code = http.sendRequest(method, body, body->size()); }
  ```
- **Failure Scenario**:
  Placing 500+ bytes of JSON metadata in the `X-Sentinel-Meta` header forces HTTP servers and intermediaries to parse large headers. Any unescaped character or locale change in `last_error` can corrupt HTTP/1.1 framing.
- **Suggested Fix**:
  Switch to standard `multipart/form-data` with one field for `metadata` (JSON) and one for `photo` (binary JPEG), avoiding bloated custom HTTP headers.

---

### 7. Test Coverage Gaps

1. **ESP32 Schedule Wrapping & Drift**: No automated unit tests verify `untilNextWake()` across DST boundaries, multi-day schedule rollover, or `n_wakes` edge cases.
2. **Flash Queue Deletion Logic**: No test validates that orphaned `.json` files are cleaned up or that `FS_RESERVE` is correctly maintained under flash-full conditions.
3. **HTTP Status Code Resilience**: No mock tests ensure that the firmware queue progresses past 409, 400, or 500 error responses without stalling.
4. **Hub Installation Script (`install-hub.sh`)**: No CI validation ensures that `install-hub.sh` executes cleanly in a fresh minimal Debian/Raspberry Pi OS container without ambient pip build dependencies.

---

### Prioritized Next Steps

1. **Fix `photo_now` loop** ([main.cpp:507](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L507)): Prevent requested wake cycles from immediately re-requesting captures.
2. **Fix queue stalling on HTTP errors** ([main.cpp:263](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L263)): Handle HTTP 409 Conflict and 400 Bad Request by discarding unprocessable files rather than retrying indefinitely.
3. **Correct RTC drift update condition** ([main.cpp:196-201](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L196-L201)): Only reset `sync_clock` when `rate` is updated or when initially syncing so sleep calibration can function.
4. **Fix user groups in `install.sh`** ([install.sh:14](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/install.sh#L14)): Ensure the `sentinel` user is added to `video`, `gpio`, and `i2c` even if the user already exists.
5. **Add mutex protection in setup mode** ([main.cpp:310-344](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/device/esp32-node/src/main.cpp#L310-L344)): Synchronize framesize changes and buffer grabs between the web and stream servers.
