# Orchard Sentinel: Architectural Review & Production Recommendations

This report benchmarks the **Orchard Sentinel** system (ESP32-S3 traps $\rightarrow$ Raspberry Pi gateway $\rightarrow$ Tailscale $\rightarrow$ Raspberry Pi 5 FastAPI/SQLite server $\rightarrow$ ML pipeline $\rightarrow$ NEWA biofix dashboard) against commercial smart traps, academic literature, and production IoT/MLOps patterns.

---

## 1. What Professionals Do

### 1.1 Commercial & Academic Automated Insect-Trap Camera Systems
Commercial pest-monitoring systems—such as [Trapview](https://www.trapview.com) (EFOS), [Pessl Instruments iSCOUT](https://metos.global), [Semios](https://semios.com), and the [DTN Smart Trap / Spensa Z-Trap](https://www.dtn.com)—alongside academic platforms like [Sticky Pi](https://journals.plos.org/plosbiology/article?id=10.1371/journal.pbio.3001689) ([Geissmann et al., *PLOS Biology*, 2022](https://doc.sticky-pi.com)) and reviews by [Preti et al. (*Journal of Pest Science*, 2021)](https://link.springer.com/article/10.1007/s10340-020-01312-w), follow specific engineering patterns:

* **Capture Frequency & Timing:** Instead of continuous streaming, commercial systems capture **1 to 4 images per day**. Imaging is scheduled during fixed windows (typically at night between 23:00 and 03:00 or at dawn) to eliminate ambient sunlight variance, sun glare on sticky adhesive, and harsh canopy shadows. In contrast, optical-acoustic sensors like [FarmSense FlightSensor](https://farmsense.io) monitor wingbeat frequencies continuously in real time rather than using sticky-card vision.
* **Resolution & Optics:** Sensors range from 2–5 MP (Trapview Standard/Plus) to 10 MP (Pessl iSCOUT). Academic platforms like Sticky Pi use 5–12 MP Raspberry Pi camera sensors. Lenses are fixed-focus macro/wide-angle mounted orthogonally 10–18 cm above the liner.
* **Illumination:** Dedicated artificial lighting is universal. Enclosed chambers use diffused, ring-mounted white LEDs or strobe flashes to avoid specular reflections off sticky glue.
* **Power Autonomy:** Nodes enter deep sleep (<15 µA quiescent draw). Systems run on a single 18650 Li-ion cell (2600–3500 mAh) or 6V lead-acid/LiFePO4 battery paired with a 2W–7W monocrystalline solar panel, achieving multi-season field autonomy.
* **Data Transfer:** Commercial systems transmit directly via cellular (LTE Cat-1, LTE-M, NB-IoT) or sub-GHz mesh (Semios uses a proprietary 900 MHz canopy mesh). LoRaWAN is restricted to numerical counts and telemetry; its duty cycle limits (1%) and payload constraints (~51–222 bytes) make transmitting raw 100 KB–1 MB JPEG images impractical without aggressive tiling or lossy edge compression.
* **Counting & De-duplication:** Because sticky liners permanently retain dead insects, counting cannot rely solely on per-frame object detection. Systems solve this via:
  1. **Consecutive Frame Registration:** Aligning consecutive photos using homography/feature-matching to counteract wind-induced trap displacement.
  2. **Temporal Instance Tracking / Change Detection:** Associating detected insects between frame $T_{k-1}$ and frame $T_k$ using IoU overlap and Hungarian bipartite matching (or Sticky Pi’s Siamese network matcher). Only newly detected instances not matching any prior specimen are counted toward that day's delta.
* **Validation & Agronomics:** Systems are validated by computing the Pearson correlation ($R^2 > 0.85–0.95$) and Mean Absolute Error (MAE) against manual counts by entomologists. Crucially, systems validate the **biofix date error** (days offset from true sustained moth catch), which directly drives [Cornell NEWA degree-day models](https://newa.cornell.edu) for Codling Moth (*Cydia pomonella*, base 50°F), Oriental Fruit Moth (*Grapholita molesta*, base 45°F), and Obliquebanded Leafroller (*Choristoneura rosaceana*, base 43°F).

---

### 1.2 Edge $\rightarrow$ Hub $\rightarrow$ Server IoT Patterns
* **Protocol & Transport:** HTTP POST with `multipart/form-data` is standard for binary image payloads. MQTT is reserved for lightweight signaling, wake triggers, and telemetry. Forcing multi-hundred-kilobyte images through MQTT brokers increases packet segmentation overhead and requires Base64 encoding (+33% payload inflation).
* **Store-and-Forward & Idempotency:** Edge nodes buffer unsent images to local flash (LittleFS/SPIFFS) or SD cards upon Wi-Fi failure. Every capture is assigned a **SHA-256 content hash** or a deterministic composite key (`node_uuid + capture_timestamp`). The server enforces idempotency via unique constraints on this hash, discarding duplicates without re-triggering inference pipelines.
* **Offline Buffering & Backpressure:** The intermediate gateway (Hub Pi) runs a disk-backed queue (local SQLite or Redis) to buffer images when upstream connectivity (Tailscale) is down, applying exponential backoff and batch draining upon reconnection.
* **Authentication & Transport Security:** Tailscale provides encrypted WireGuard tunnels for the Hub $\rightarrow$ Server link, eliminating exposed public ports. Edge $\rightarrow$ Hub uses pre-shared API bearer tokens over localized WPA2/WPA3 private orchard Wi-Fi.
* **ESP32 Signed OTA & Hardware Rollback:** Production firmware uses the [ESP-IDF App Rollback Mechanism](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/system/ota.html) with dual OTA partitions (`ota_0`, `ota_1`). A newly flashed image boots into `ESP_OTA_IMG_PENDING_VERIFY`. Only after successfully capturing an image and transmitting an initial heartbeat does firmware execute `esp_ota_mark_app_valid_cancel_rollback()`; crashes or watchdog timeouts automatically trigger the bootloader to revert to the previous functional partition.
* **Fleet Telemetry & Time Sync:** Nodes wake, sync their real-time clock via local SNTP against the Hub Pi gateway, capture image telemetry (battery voltage, Wi-Fi RSSI, camera init return code, reboot reason), and upload before returning to deep sleep.

---

### 1.3 Server: FastAPI + SQLite in Production
* **Concurrency Configuration:** By default, SQLite runs in `DELETE` rollback mode, where writes block reads and reads block writes. Production deployment requires three pragmas applied on connection:
  * `PRAGMA journal_mode = WAL;` (enables concurrent readers alongside a writer via [Write-Ahead Logging](https://www.sqlite.org/wal.html))
  * `PRAGMA busy_timeout = 5000;` (prevents immediate `database is locked` errors by waiting up to 5 seconds for write locks to clear)
  * `PRAGMA synchronous = NORMAL;` (eliminates redundant `fsync` calls while maintaining crash resilience)
* **Write Discipline:** SQLite supports only a single concurrent writer. Transactions performing writes must issue `BEGIN IMMEDIATE` to prevent read-to-write lock escalation deadlocks.
* **Out-of-Process Inference Queues:** FastAPI's built-in `BackgroundTasks` executes in the same process and Python asyncio loop. Running heavyweight PyTorch/ONNX ML inference inside `BackgroundTasks` blocks the event loop and risks process termination from Out-of-Memory (OOM) errors on a Raspberry Pi 5. Production designs offload inference to out-of-process workers ([ARQ with Redis](https://arq-docs.readthedocs.io), [RQ](https://python-rq.org), or [Huey with SQLite backend](https://huey.readthedocs.io)).
* **Migrations & Storage:** Database migrations must use [Alembic's batch mode](https://alembic.sqlalchemy.org/en/latest/batch.html) (`render_as_batch=True`) to work around SQLite's lack of native `ALTER TABLE` support. Images are stored on the filesystem (or local MinIO/S3 object storage) and referenced in SQLite by relative URI, avoiding database bloat.
* **Continuous Backups:** SQLite databases are replicated in real time using [Litestream](https://litestream.io), which streams WAL frame changes directly to external object storage (S3/R2/B2) with minimal CPU and memory overhead.
* **When to Migrate to PostgreSQL / Cloud:** Transition from SQLite on Pi 5 to PostgreSQL/Cloud is warranted when: (a) write concurrency exceeds ~50 writes/second across many hubs; (b) multiple distributed server nodes require shared state; or (c) storage needs exceed local SSD capacities.

---

### 1.4 MLOps for Small Datasets
* **Grouped Data Splits (Preventing Leakage):** Sticky trap imagery suffers from high background autocorrelation (specific glue spots, lighting angles, trapped debris). Performing standard random train/val/test splits causes severe **data leakage**; the network memorizes trap backgrounds rather than insect morphology ([Beery et al., *ECCV*, 2018](https://arxiv.org/abs/1806.00731)). Production pipelines enforce `StratifiedGroupKFold` using [`scikit-learn`](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html), grouping by `trap_id` or `liner_id` so validation images come exclusively from traps unseen during training.
* **Active Learning (AL):** With limited manual labels, models prioritize unlabelled field images via uncertainty sampling:
  1. *Classification Margin/Entropy:* Identifying boxes where the top two class predictions have similar probabilities (e.g., confusing Codling Moth with Oriental Fruit Moth).
  2. *Detection Confidence Band:* Sampling bounding boxes in the 0.30–0.65 confidence interval.
  3. *Diversity Filtering:* Clustering backbone feature embeddings via $k$-means to avoid annotating duplicate instances.
* **Human-in-the-Loop (HITL) Review Queues:** Dashboards present low-confidence inferences to human scouts for one-click verification/relabeling using tools like [Label Studio](https://labelstud.io) or custom UI components.
* **Versioning:** [DVC (Data Version Control)](https://dvc.org) versions raw images and YOLO annotation labels in remote storage via Git pointers. [MLflow](https://docs.ultralytics.com/integrations/mlflow/) tracks model hyperparameters, loss curves, and mAP50/mAP50-95 metrics, managing stage transitions (`@champion`, `@staging`).

---

## 2. Likely Gaps in Orchard Sentinel’s Pipeline

| Layer | Likely Gap | Real-World Consequence |
| :--- | :--- | :--- |
| **Edge Hardware** | Daylight-dependent capture without uniform LED enclosure | Specular reflections on wet adhesive and harsh canopy shadows degrade YOLO classification accuracy. |
| **Edge Power** | Node stays awake or lacks deep sleep between shots | Battery depletes in days rather than lasting the 4–5 month apple growing season. |
| **IoT / Transport** | Synchronous edge-to-server HTTP without local persistence | Gateway or server restarts drop captures permanently; network retries without idempotency cause duplicate counting. |
| **Firmware** | Single-partition ESP32 firmware flashes without rollback | A failed remote OTA update bricks traps mounted high in orchard trees, requiring physical ladder retrieval. |
| **Server Database** | SQLite running with default settings (`journal_mode=DELETE`, no timeout) | Concurrency deadlocks (`sqlite3.OperationalError: database is locked`) when edge nodes upload while the dashboard queries data. |
| **Server ML** | Inference executed in FastAPI request thread or `BackgroundTasks` | Uvicorn event loop freezes; web dashboard becomes unresponsive; Pi 5 risks OOM crash during simultaneous uploads. |
| **ML Tracking** | Naive per-frame object detection counting | Dead moths that remain stuck on the liner for 20 days are counted 20 times, corrupting daily catch rates. |
| **ML Evaluation** | Random train/test split on hand-labelled dataset | Overfitting to trap background artifacts yields falsely high mAP on validation sets, followed by failure in field conditions. |
| **Agronomic Logic** | Single-day false positive triggering biofix | Stray moth detection prematurely triggers degree-day accumulation; NEWA models recommend pesticide sprays weeks off target. |

---

## 3. Recommended Changes (Prioritized by Impact)

```
┌────────────────────────────────────────────────────────────────────────────┐
│ Priority 0: Fix ML Double-Counting & Data Leakage (Core Accuracy)          │
│ P0.1 Temporal IoU De-duplication  │ P0.2 StratifiedGroupKFold Data Splits  │
└─────────────────────────────────────┬──────────────────────────────────────┘
                                      ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ Priority 1: Server Reliability & Asynchronous ML Execution                 │
│ P1.1 SQLite WAL & Pragmas         │ P1.2 Out-of-Process Task Queue (ARQ)   │
│ P1.3 Litestream S3 Backups        │ P1.4 Alembic Batch Mode Migrations     │
└─────────────────────────────────────┬──────────────────────────────────────┘
                                      ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ Priority 2: Edge Robustness, Idempotency & OTA Safety                      │
│ P2.1 SHA-256 Idempotency Keying   │ P2.2 Store-and-Forward Disk Buffers    │
│ P2.3 ESP-IDF OTA Dual-Rollback    │ P2.4 Standardized Night/LED Capture    │
└─────────────────────────────────────┬──────────────────────────────────────┘
                                      ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ Priority 3: Agronomic Biofix Verification & Active Learning                │
│ P3.1 Multi-Day Sustained Catch    │ P3.2 Dashboard HITL Review Queue       │
│ P3.3 DVC & MLflow Tracking        │                                        │
└────────────────────────────────────────────────────────────────────────────┘
```

---

### Priority 0: Core ML Integrity & Data Splitting (High Impact / Immediate)

#### 1. Implement Consecutive Frame De-duplication (IoU Tracking)
* **Effort:** Medium (M)
* **Implementation:** Rather than using raw frame counts, track persistent bounding boxes across consecutive daily images using spatial overlap:
  1. Compute IoU matrix between bounding boxes at day $T_{k-1}$ and day $T_k$.
  2. Solve linear sum assignment via Hungarian matching (`scipy.optimize.linear_sum_assignment`).
  3. Bounding boxes in day $T_k$ with $\text{IoU} < 0.3$ against all day $T_{k-1}$ instances are registered as **new arrivals** ($\Delta \text{count}$).
  4. Only $\Delta \text{count}$ increments the trap tally.

#### 2. Enforce `StratifiedGroupKFold` by `liner_id`
* **Effort:** Small (S)
* **Implementation:** Refactor the model training pipeline to isolate physical trap liners across splits:
  ```python
  from sklearn.model_selection import StratifiedGroupKFold

  sgkf = StratifiedGroupKFold(n_splits=5)
  for train_idx, val_idx in sgkf.split(
      X=image_paths, y=species_labels, groups=liner_ids
  ):
    # Guarantees zero background/liner overlap between train and validation folds
    assert set(liner_ids[train_idx]).isdisjoint(set(liner_ids[val_idx]))
```

---

### Priority 1: Server Architecture & Database Hardening (High Impact)

#### 3. Configure Production SQLite Pragmas
* **Effort:** Small (S)
* **Implementation:** Attach an event listener to SQLAlchemy engine initialization in FastAPI:
  ```python
  from sqlalchemy import event


  @event.listens_for(engine.sync_engine, "connect")
  def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA busy_timeout = 5000;")
    cursor.execute("PRAGMA synchronous = NORMAL;")
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.close()
```

#### 4. Decouple ML Inference via an Out-of-Process Task Queue
* **Effort:** Medium (M)
* **Implementation:** Remove model execution from FastAPI route handlers and `BackgroundTasks`. Deploy [ARQ](https://arq-docs.readthedocs.io) or [RQ](https://python-rq.org) with a local Redis container on the Pi 5. The upload endpoint saves the raw image to disk, commits metadata, enqueues job ID `run_yolo_pipeline.delay(image_path)`, and immediately returns HTTP 202 Accepted.

#### 5. Automated Streaming Backups with Litestream
* **Effort:** Small (S)
* **Implementation:** Run [Litestream](https://litestream.io) as a `systemd` background service on the Pi 5, continuously replicating the SQLite WAL journal to an S3-compatible bucket (e.g., Cloudflare R2 or MinIO).

#### 6. Configure Alembic Batch Mode
* **Effort:** Small (S)
* **Implementation:** In `alembic/env.py`, set `render_as_batch=True` and `compare_type=True` within `context.configure()` to allow schema alterations on SQLite without migration failures.

---

### Priority 2: Edge Reliability, Transport & OTA Safety (Medium-to-High Impact)

#### 7. Idempotent Uploads via SHA-256 Content Hashing
* **Effort:** Small (S)
* **Implementation:** The ESP32-S3 computes the SHA-256 hash of the JPEG buffer prior to transmission and includes it in the header `X-Image-SHA256`. The server stores this in a `UNIQUE` column on the `captures` table. Duplicate uploads from network retries resolve with HTTP 200 without executing duplicate ML jobs.

#### 8. Gateway Store-and-Forward Buffering
* **Effort:** Medium (M)
* **Implementation:** Configure the Python gateway on the Hub Pi to write incoming images to a local disk spool (`/var/spool/orchard/`). A background worker reads the spool and forwards payloads to the Pi 5 over Tailscale, backing off exponentially during disconnections.

#### 9. Dual-Partition ESP32 OTA with Automated Rollback
* **Effort:** Medium (M)
* **Implementation:** Update the ESP32 partition table with dual application slots (`ota_0`, `ota_1`) and enable `CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y`. In the firmware entrypoint, execute health checks before confirming boot validity:
  ```c
  if (health_checks_succeeded()) {
      esp_ota_mark_app_valid_cancel_rollback();
  } else {
      esp_ota_mark_app_invalid_rollback_and_reboot();
  }
  ```

#### 10. Standardize Nighttime / Uniform LED Image Capture
* **Effort:** Medium (M)
* **Implementation:** Schedule ESP32 captures at a fixed night hour (e.g., 01:00) using deep sleep RTC wake timers. Trigger a diffused warm-white LED ring for 200 ms during exposure to establish uniform lighting across seasons.

---

### Priority 3: Agronomic Logic & MLOps Pipeline (Medium Impact / Polish)

#### 11. Multi-Day Sustained Catch Verification for Biofix
* **Effort:** Small (S)
* **Implementation:** Align biofix detection with [Cornell NEWA IPM guidelines](https://newa.cornell.edu): do not trigger biofix on a single moth detection. Require a sustained catch threshold (e.g., $\ge 2$ moths in a trap or non-zero catches across two consecutive check intervals) before locking the biofix date and starting degree-day accumulation.

#### 12. Active Learning Uncertainty & Dashboard HITL Review
* **Effort:** Medium (M)
* **Implementation:** Add an "Unverified Catches" review queue to the web dashboard. Automatically flag detections where maximum class softmax probability is between 0.35 and 0.65, or where total catch delta exceeds historical standard deviations ($\ge 3\sigma$). Allow growers or student researchers to confirm or reclassify boxes with one click.

#### 13. Model & Dataset Versioning (DVC + MLflow)
* **Effort:** Medium (M)
* **Implementation:** Store annotated sticky-card datasets in [DVC](https://dvc.org) connected to remote cloud storage. Enable Ultralytics' native [MLflow](https://docs.ultralytics.com/integrations/mlflow/) callback (`settings.update({"mlflow": True})`) to automatically record run parameters, precision-recall curves, and mAP metrics across training experiments.

---

## 4. Implementation Matrix

| Recommendation | Target Subsystem | Priority | Effort | Key Benefit |
| :--- | :--- | :--- | :--- | :--- |
| **Temporal IoU De-duplication** | ML Pipeline | **P0** | **M** | Eliminates cumulative multi-counting of dead insects. |
| **Grouped Data Splits (`liner_id`)** | ML Training | **P0** | **S** | Prevents background data leakage and model overoptimism. |
| **SQLite WAL + Pragmas** | Server DB | **P1** | **S** | Resolves `database is locked` concurrency errors. |
| **Decoupled Task Queue (ARQ/Redis)** | Server Core | **P1** | **M** | Prevents FastAPI event loop freezing and Pi 5 OOM crashes. |
| **Litestream S3 Backups** | Server DB | **P1** | **S** | Real-time zero-maintenance SQLite disaster recovery. |
| **Alembic `render_as_batch`** | Server DB | **P1** | **S** | Prevents migration failures during SQLite schema updates. |
| **SHA-256 Upload Idempotency** | IoT Transport | **P2** | **S** | Prevents duplicate records on network retries. |
| **Hub Store-and-Forward Spool** | Hub Gateway | **P2** | **M** | Resilient against field network and Tailscale drops. |
| **ESP-IDF Dual OTA Rollback** | Edge Firmware | **P2** | **M** | Eliminates bricked nodes during remote firmware updates. |
| **Controlled Night LED Capture** | Edge Hardware | **P2** | **M** | Normalizes lighting and eliminates solar glare on glue. |
| **NEWA Sustained Catch Logic** | Agronomic Core | **P3** | **S** | Prevents premature biofix triggers from false positives. |
| **HITL Review Queue** | Web Dashboard | **P3** | **M** | Focuses human annotation effort on confusing edge cases. |
| **DVC + MLflow Tracking** | MLOps Core | **P3** | **M** | Establishes reproducible model lineage and data tracking. |
