# Code Review Report: Chunk 1 of 3 (Cross-Cutting & Documentation)

This review covers the cross-cutting repository files provided in Scope Chunk 1: [CLAUDE.md](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/CLAUDE.md), [README.md](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/README.md), [Patti's code](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/Patti%27s%20code), [.claude/launch.json](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.claude/launch.json), [.claude/rules/ml.md](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.claude/rules/ml.md), [.github/workflows/tests.yml](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.github/workflows/tests.yml), [.gitignore](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.gitignore), and the documentation guides under `docs/` ([docs/bring-up.md](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/bring-up.md), [docs/camera-bench.md](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/camera-bench.md), [docs/cv-research-status.md](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/cv-research-status.md), [docs/esp32-traps.md](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/esp32-traps.md), [docs/evaluation.md](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/evaluation.md)).

---

## 1. BUGS (Correctness, Crashes, Data Integrity)

### [Patti's code:221-223](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/Patti%27s%20code#L221-L223) & [Patti's code:257-259](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/Patti%27s%20code#L257-L259)
- **Severity**: Medium
- **Quote**:
  ```python
  221|     train_accuracy = (
  222|         100 * correct / total
  223|     )
  ...
  257|     val_accuracy = (
  258|         100 * val_correct / val_total
  259|     )
  ```
- **Concrete Failure Scenario**: If `val_dataset` contains no images (e.g. if the directory structure is empty, missing, or improperly mounted), `val_total` remains `0`. At the end of the first epoch, line 258 evaluates `100 * val_correct / val_total`, raising an unhandled `ZeroDivisionError: division by zero` and crashing the training process after computing a full training epoch.
- **Suggested Fix**: Guard against division by zero before dividing:
  ```python
  train_accuracy = (100.0 * correct / total) if total > 0 else 0.0
  val_accuracy = (100.0 * val_correct / val_total) if val_total > 0 else 0.0
  ```
  Additionally, add an assertion immediately after dataset initialization:
  ```python
  if len(train_dataset) == 0 or len(val_dataset) == 0:
      raise ValueError(f"Datasets cannot be empty: train={len(train_dataset)}, val={len(val_dataset)}")
  ```

---

### [Patti's code:79-87, 103, 133-143, 301-303](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/Patti%27s%20code#L79-L87)
- **Severity**: High
- **Quote**:
  ```python
  79| train_dataset = datasets.ImageFolder(
  80|     os.path.join(DATA_DIR, "train"),
  81|     transform=train_transforms
  82| )
  83| 
  84| val_dataset = datasets.ImageFolder(
  85|     os.path.join(DATA_DIR, "val"),
  86|     transform=val_transforms
  87| )
  ...
  133| # Original MobileNet recognizes 1000 ImageNet classes.
  134| # We replace the final layer so it recognizes only:
  135| #
  136| # 0 = codling moth
  137| # 1 = not codling moth
  140| model.classifier[3] = nn.Linear(
  141|     num_features,
  142|     2
  143| )
  ```
- **Concrete Failure Scenario**: `torchvision.datasets.ImageFolder` assigns class index mappings dynamically based on the alphabetical sort order of the subfolder names. If the folder names on disk are `codling_moth` and `other`, then `codling_moth` is index 0. However, if the folders are named `CM` and `debris`, or `positive` and `negative`, or if `val/` has a different set of folders than `train/`, the index mapping will invert or mismatch. The model will silently train against inverted targets or evaluate validation accuracy against the wrong class labels.
- **Suggested Fix**: Enforce explicit class mapping and verify that `train_dataset.class_to_idx == val_dataset.class_to_idx`:
  ```python
  EXPECTED_CLASSES = ["codling_moth", "not_codling_moth"]
  assert train_dataset.classes == val_dataset.classes == EXPECTED_CLASSES, (
      f"Class mismatch: train={train_dataset.classes}, val={val_dataset.classes}"
  )
  ```

---

### [Patti's code:79-87](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/Patti%27s%20code#L79-L87) (Data Leakage Across Splits)
- **Severity**: High
- **Quote**:
  ```python
  79| train_dataset = datasets.ImageFolder(
  80|     os.path.join(DATA_DIR, "train"),
  81|     transform=train_transforms
  82| )
  ```
- **Concrete Failure Scenario**: According to [.claude/rules/ml.md:22-23](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.claude/rules/ml.md#L22-L23), held-out sets must be strictly controlled (`locked_test.txt`, `test_cards.txt`) and "a split keeps every photo of one liner or card on the same side." `Patti's code` blindly loads `data/train` and `data/val` as independent image folders. If insect crops from the same sticky liner appear in both train and validation folders, the model memorizes liner background artifacts, resulting in high validation accuracy that collapses during field deployment.
- **Suggested Fix**: Replace naive directory loading with the project's grouped dataset splitter that checks image hashes/card origins against `locked_test.txt`.

---

### [Patti's code:291-294, 307](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/Patti%27s%20code#L291-L294)
- **Severity**: Low
- **Quote**:
  ```python
  19| MODEL_PATH = "models/codling_moth_model.pth"
  ...
  291| os.makedirs(
  292|     "models",
  293|     exist_ok=True
  294| )
  ...
  307|     MODEL_PATH
  ```
- **Concrete Failure Scenario**: If `MODEL_PATH` is modified to point to a subfolder (e.g. `models/mobilenet/checkpoint.pth` or a custom output directory), line 291 only creates `"models"`. `torch.save` will subsequently fail with `FileNotFoundError: [Errno 2] No such file or directory`.
- **Suggested Fix**: Create the parent directory dynamically based on `MODEL_PATH`:
  ```python
  os.makedirs(os.path.dirname(MODEL_PATH) or ".", exist_ok=True)
  ```

---

### [.github/workflows/tests.yml:16, 26, 37](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.github/workflows/tests.yml#L16)
- **Severity**: Medium
- **Quote**:
  ```yaml
  16|       - uses: astral-sh/setup-uv@v6
  ...
  26|       - uses: astral-sh/setup-uv@v6
  ...
  37|       - uses: astral-sh/setup-uv@v6
  ```
- **Concrete Failure Scenario**: The GitHub Action `astral-sh/setup-uv` has released up to major version `v5`. Specifying `@v6` references a non-existent tag, which causes all CI pipeline runs to fail during action checkout with `Action not found: astral-sh/setup-uv@v6`.
- **Suggested Fix**: Pin to a valid released major version:
  ```yaml
  - uses: astral-sh/setup-uv@v5
  ```

---

## 2. Security Issues

### [.gitignore:1-15](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.gitignore#L1-L15) & [docs/esp32-traps.md:124-125](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/esp32-traps.md#L124-L125) (Exposure of Wi-Fi & API Keys)
- **Severity**: Critical
- **Quote**:
  In `docs/esp32-traps.md`:
  ```markdown
  124| 2. Firmware: `cd device/esp32-node && cp include/node_config.example.h include/node_config.h`. Paste
  125|    those two lines, fill in the hub's Wi-Fi name and password, `HUB_URL` and the LED pin, and flash it:
  ```
  In `.gitignore`:
  ```
  1| .venv/
  ...
  15| *.pt
  ```
- **Concrete Failure Scenario**: Users following the setup instructions create `device/esp32-node/include/node_config.h` containing plaintext Wi-Fi credentials (`WIFI_SSID`, `WIFI_PASSWORD`) and trap authentication keys (`API_KEY`). Because [.gitignore](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.gitignore) does not include `node_config.h`, running `git add .` or `git commit -a` will commit these active credentials directly into git version control.
- **Suggested Fix**: Add the configuration file to [.gitignore](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.gitignore):
  ```gitignore
  # ESP32 node local secrets
  device/esp32-node/include/node_config.h
  ```

---

### [.gitignore:1-15](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.gitignore#L1-L15) & [Patti's code:19, 307](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/Patti%27s%20code#L19) (Untracked Model Weights & Root Directory)
- **Severity**: Medium
- **Quote**:
  In `.gitignore`:
  ```gitignore
  11| ml/models/
  ...
  15| *.pt
  ```
  In `Patti's code`:
  ```python
  19| MODEL_PATH = "models/codling_moth_model.pth"
  ```
- **Concrete Failure Scenario**: `.gitignore` ignores `ml/models/` and `*.pt`. However, `Patti's code` saves checkpoints with extension `.pth` into `./models/` at the repository root. When `Patti's code` runs, the resulting multi-megabyte binary model file is not ignored by git and will accidentally pollute the repository commit history.
- **Suggested Fix**: Update [.gitignore](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.gitignore) to cover `.pth` and top-level models directories:
  ```gitignore
  models/
  *.pth
  ```

---

### [.claude/launch.json:9, 18, 27](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.claude/launch.json#L9) (Unbound / Open Network Interface for Labelling Tools)
- **Severity**: Low
- **Quote**:
  ```json
  9|         "cd ml && exec .venv/bin/python label_field_cards.py --port 8765"
  ...
  18|         "cd ml && exec .venv/bin/python label_field_cards.py --data data/web_liners/label/ofm-ervins --port 8766"
  ...
  27|         "cd ml && exec .venv/bin/python model_playground.py --port 8770"
  ```
- **Concrete Failure Scenario**: Unlike `server-dashboard` on line 36 (which explicitly binds `--host 127.0.0.1`), the labeling and playground servers omit a host binding flag. If these Python scripts default to `0.0.0.0` or allow external requests, any peer device on the local network (such as Cornell's shared RedRover Wi-Fi described in `docs/esp32-traps.md:148`) can connect to port 8765/8766 and modify or corrupt active annotations without authentication.
- **Suggested Fix**: Explicitly pass `--host 127.0.0.1` to all preview servers in [.claude/launch.json](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.claude/launch.json).

---

### [docs/bring-up.md:21](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/bring-up.md#L21) & [docs/esp32-traps.md:72](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/esp32-traps.md#L72)
- **Severity**: Low
- **Quote**:
  ```bash
  curl -fsSL https://tailscale.com/install.sh | sh
  ```
- **Concrete Failure Scenario**: Piping an unpinned web script directly into `sh` over HTTP/HTTPS exposes automated provisioning to MITM tampering or upstream supply-chain risks.
- **Suggested Fix**: Instruct operators to inspect the script, verify checksums, or use official distribution packages (`sudo apt-get install tailscale`).

---

## 3. Deprecated APIs & Outdated Patterns

### [docs/esp32-traps.md:101-102](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/esp32-traps.md#L101-L102)
- **Severity**: Low
- **Quote**:
  ```bash
  101| sudo nmcli con add type wifi ifname wlan0 con-name sentinel-hub autoconnect yes ssid sentinel-hub \
  102|   mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 ipv4.method shared \
  103|   wifi-sec.key-mgmt wpa-psk wifi-sec.psk 'choose-a-password'
  ```
- **Concrete Failure Scenario**: On modern Linux systems running NetworkManager (such as Raspberry Pi OS Bookworm mentioned on line 98), the `802-11-wireless.*` setting namespace is deprecated in favor of `wifi.*` (e.g. `wifi.band`, `wifi.channel`). While some versions translate this via backward compatibility aliases, newer NetworkManager releases emit deprecation warnings or fail connection validation.
- **Suggested Fix**: Update nmcli invocations to modern syntax:
  ```bash
  sudo nmcli con add type wifi ifname wlan0 con-name sentinel-hub autoconnect yes ssid sentinel-hub \
    mode ap wifi.band bg wifi.channel 6 ipv4.method shared \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk 'choose-a-password'
  ```

---

### [Patti's code:21-23](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/Patti%27s%20code#L21-L23) (Outdated PyTorch Device Selection)
- **Severity**: Low
- **Quote**:
  ```python
  21| DEVICE = torch.device(
  22|     "cuda" if torch.cuda.is_available() else "cpu"
  23| )
  ```
- **Concrete Failure Scenario**: The team works primarily on Apple Silicon Macs (M3, as noted in [.claude/rules/ml.md:14](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.claude/rules/ml.md#L14)). This device selection ignores PyTorch MPS (`torch.backends.mps.is_available()`), defaulting straight to CPU on Mac. Furthermore, `.claude/rules/ml.md:14` notes that training on MPS hangs if batch sizes are not handled properly.
- **Suggested Fix**: Support MPS with appropriate device fallback or follow project rules:
  ```python
  device_str = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
  DEVICE = torch.device(device_str)
  ```

---

## 4. Inconsistencies (Code vs Docs, Taxonomy, Defaults)

### [docs/cv-research-status.md:42](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/cv-research-status.md#L42) vs [README.md:46](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/README.md#L46) & [.claude/launch.json:36](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.claude/launch.json#L36)
- **Severity**: Medium
- **Quote**:
  In `docs/cv-research-status.md`:
  ```markdown
  42| | Two-stage detect → classify | Had | Detector finds everything, classifier names it. The classifier is still switched off in the running server |
  ```
  In `README.md`:
  ```markdown
  46| and switched on (`SENTINEL_CLASSIFIER=bioclip-v1`) on the Pi 5 server since Oct 22 2026
  ```
  In `.claude/launch.json`:
  ```json
  36| "cd server && SENTINEL_DATA_DIR=data/dev SENTINEL_CLASSIFIER=none exec .venv/bin/sentinel-server serve --host 127.0.0.1 --port 8010"
  ```
- **Concrete Failure Scenario**: A developer consulting `cv-research-status.md` is informed that classification is disabled on the server. However, `README.md` states it has been enabled since Oct 22, while `launch.json` explicitly forces it off (`SENTINEL_CLASSIFIER=none`). Running local dev via `launch.json` tests an unclassified pipeline while production runs with classification enabled.
- **Suggested Fix**: Update `docs/cv-research-status.md` to state that `SENTINEL_CLASSIFIER=bioclip-v1` was activated on Oct 22 2026. Clarify in `launch.json` whether `SENTINEL_CLASSIFIER=none` is intentionally lightweight for dev or should match production.

---

### [docs/bring-up.md:31](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/bring-up.md#L31) vs [CLAUDE.md:42](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/CLAUDE.md#L42) (Destructive Command on Shared Bench Pi)
- **Severity**: High
- **Quote**:
  In `docs/bring-up.md`:
  ```markdown
  6| The bench Pi that was `sentinel-t1` below is now that hub, renamed `apple-pi-hub`.
  ...
  30| git clone <your repo URL> sentinel && cd sentinel/device
  31| sudo ./install.sh
  ```
  In `CLAUDE.md`:
  ```markdown
  42| The bench Pi is shared. Ask before running anything on it, and do not run `device/install.sh` there.
  ```
- **Concrete Failure Scenario**: A new developer following `docs/bring-up.md` step-by-step on `apple-pi-hub` will execute `sudo ./install.sh`. This conflicts with `install-hub.sh`, installs the camera-trap daemon over the gateway service, breaks the shared hub gateway, and corrupts ongoing ESP32 bench testing.
- **Suggested Fix**: Add a prominent warning in `docs/bring-up.md` Section 3:
  > [!CAUTION]
  > If working on the shared bench Pi (`apple-pi-hub`), do NOT run `install.sh`. Use `install-hub.sh` as documented in [esp32-traps.md](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/esp32-traps.md).

---

### [Patti's code:133-143](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/Patti%27s%20code#L133-L143) vs [CLAUDE.md:37](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/CLAUDE.md#L37) (Class Taxonomy Inconsistency)
- **Severity**: High
- **Quote**:
  In `Patti's code`:
  ```python
  133| # 0 = codling moth
  134| # 1 = not codling moth
  140| model.classifier[3] = nn.Linear(
  141|     num_features,
  142|     2
  143| )
  ```
  In `CLAUDE.md`:
  ```markdown
  37| - Class labels everywhere: `CM`, `OFM`, `OBLR`, `other_moth`, `other_insect`, `debris`.
  ```
- **Concrete Failure Scenario**: `Patti's code` reduces classification to a binary classification problem (`codling moth` vs `not codling moth`), violating the 6-class standard enforced across the rest of the repository (`CM`, `OFM`, `OBLR`, `other_moth`, `other_insect`, `debris`). If this model is loaded by the server or evaluated with `sentinel-server evaluate`, it will fail because the pipeline expects 6 output logits for species voting.
- **Suggested Fix**: Change the classifier head to output 6 classes according to project conventions:
  ```python
  CLASSES = ["CM", "OFM", "OBLR", "other_moth", "other_insect", "debris"]
  model.classifier[3] = nn.Linear(num_features, len(CLASSES))
  ```

---

### [CLAUDE.md:14](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/CLAUDE.md#L14) vs [.gitignore:1-15](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.gitignore#L1-L15)
- **Severity**: Low
- **Quote**:
  In `CLAUDE.md`:
  ```markdown
  14| run output goes to its gitignored `runs/`
  ```
  In `.gitignore`:
  ```gitignore
  1| .venv/
  ...
  15| *.pt
  ```
- **Concrete Failure Scenario**: `CLAUDE.md` documents that field test outputs go into a gitignored `runs/` directory. However, neither `runs/` nor `field-tests/**/runs/` appears anywhere in `.gitignore`. Running field-test scripts will leave test artifacts untracked in git.
- **Suggested Fix**: Add `runs/` and `field-tests/**/runs/` to `.gitignore`.

---

### [docs/camera-bench.md:39](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/camera-bench.md#L39) & [docs/bring-up.md:71](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/bring-up.md#L71)
- **Severity**: Low
- **Quote**:
  In `docs/camera-bench.md`:
  ```bash
  39| sentinel-camera-bench shoot --camera cm3wide --backend picamera2 --out ~/camera_bench
  ```
  In `docs/bring-up.md`:
  ```bash
  71| sentinel-server set-mask T1 --none
  ```
- **Concrete Failure Scenario**: On a freshly installed Pi or Mac, `sentinel-camera-bench` and `sentinel-server` are installed into virtual environments (`/opt/sentinel/venv/bin` or `.venv/bin`), not system PATH. Executing these bare commands fails with `command not found`.
- **Suggested Fix**: Qualify commands with their virtualenv paths (`/opt/sentinel/venv/bin/sentinel-camera-bench` and `.venv/bin/sentinel-server`).

---

## 5. Dead Code, Duplication & Top-Level Organization

### [Patti's code:1-321](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/Patti%27s%20code#L1-L321) (Orphaned Script in Root Directory)
- **Severity**: High
- **Quote**:
  ```
  ===== FILE: Patti's code =====
  1| import os
  2| import copy
  3| import torch
  ```
- **Concrete Failure Scenario**:
  1. The filename contains a space and single quote without a `.py` extension. It cannot be imported as a Python module (`import "Patti's code"` is a syntax error).
  2. It sits orphaned in the repository root rather than inside `ml/`, directly violating [CLAUDE.md:12](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/CLAUDE.md#L12) ("`ml/`: standalone scripts run from inside `ml/`").
  3. It duplicates the training workflow already implemented by `ml/train_v1.py` and `ml/train_v2.py`.
- **Suggested Fix**: If this file is an obsolete scratch script, delete it. If it is meant to be retained, rename and move it to `ml/train_mobilenet.py`, update its class taxonomy to match the canonical 6 classes, and add it to the ML test suite.

---

### [.gitignore:1-15](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.gitignore#L1-L15) (Missing PlatformIO Build Artifacts)
- **Severity**: Medium
- **Quote**:
  ```gitignore
  1| .venv/
  2| __pycache__/
  ...
  15| *.pt
  ```
- **Concrete Failure Scenario**: The repository includes ESP32-S3 firmware in `device/esp32-node/` built with PlatformIO ([CLAUDE.md:10](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/CLAUDE.md#L10)). PlatformIO builds generate `.pio/`, `.pioenvs/`, and `.piolibdeps/`. None of these directories are in `.gitignore`. Compiling firmware generates hundreds of MBs of intermediate build artifacts that pollute `git status`.
- **Suggested Fix**: Add PlatformIO build directories to [.gitignore](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.gitignore):
  ```gitignore
  .pio/
  .pioenvs/
  .piolibdeps/
  ```

---

## 6. Performance & Optimization Opportunities

### [Patti's code:90-100](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/Patti%27s%20code#L90-L100) (DataLoader Single-Thread Bottleneck)
- **Severity**: Low
- **Quote**:
  ```python
  90| train_loader = DataLoader(
  91|     train_dataset,
  92|     batch_size=BATCH_SIZE,
  93|     shuffle=True
  94| )
  95| 
  96| val_loader = DataLoader(
  97|     val_dataset,
  98|     batch_size=BATCH_SIZE,
  99|     shuffle=False
  100| )
  ```
- **Concrete Failure Scenario**: `DataLoader` defaults to `num_workers=0` and `pin_memory=False`. The heavy augmentation pipeline (RandomResizedCrop, RandomRotation(180), ColorJitter) runs synchronously on the main thread, bottlenecking GPU training and causing severe pipeline stalls.
- **Suggested Fix**: Configure multi-worker prefetching and pinned memory:
  ```python
  train_loader = DataLoader(
      train_dataset,
      batch_size=BATCH_SIZE,
      shuffle=True,
      num_workers=4,
      pin_memory=(DEVICE.type == "cuda")
  )
  ```

---

### [Patti's code:154-157](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/Patti%27s%20code#L154-L157) (Unfrozen Backbone Fine-Tuning)
- **Severity**: Low
- **Quote**:
  ```python
  154| optimizer = optim.Adam(
  155|     model.parameters(),
  156|     lr=LEARNING_RATE
  157| )
  ```
- **Concrete Failure Scenario**: The Adam optimizer updates all backbone parameters from epoch 1 at `lr=1e-4` on a small dataset. This risks destroying pretrained feature extractors during early iterations (catastrophic forgetting).
- **Suggested Fix**: Freeze the feature extraction backbone during initial epochs:
  ```python
  for param in model.features.parameters():
      param.requires_grad = False
  optimizer = optim.Adam(model.classifier.parameters(), lr=LEARNING_RATE)
  ```

---

## 7. Test Coverage Gaps

### [.github/workflows/tests.yml:8-39](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.github/workflows/tests.yml#L8-L39) (Missing Linting & Static Type Checking)
- **Severity**: Medium
- **Quote**:
  ```yaml
  8| jobs:
  9|   server:
  ...
  19|   device:
  ...
  30|   ml:
  ```
- **Concrete Failure Scenario**: CI executes test suites for `server`, `device`, and `ml`, but has no job for linting, code style, or static analysis (`ruff check`, `mypy`). Errors like syntax bugs in untargeted modules, invalid imports, or unused variables are not caught until runtime.
- **Suggested Fix**: Add a linting job in CI:
  ```yaml
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv run ruff check .
  ```

---

### [.github/workflows/tests.yml:10, 20, 31](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.github/workflows/tests.yml#L10) (Target Architecture Absence)
- **Severity**: Medium
- **Quote**:
  ```yaml
  10|     runs-on: ubuntu-latest
  ...
  20|     runs-on: ubuntu-latest
  ...
  31|     runs-on: ubuntu-latest
  ```
- **Concrete Failure Scenario**: The actual deployment targets are Raspberry Pi (Debian ARM64) and macOS (Apple Silicon). CI tests run exclusively on x86_64 Ubuntu. Target-specific issues (e.g. `picamera2` native bindings, ARM GPIO libraries, or path handling differences) cannot be verified in CI.
- **Suggested Fix**: Add an automated test matrix or run verification against macOS runners (`macos-latest`) and emulated ARM64 containers.

---

## Prioritized Next Steps

1. **Security (Immediate)**: Add `device/esp32-node/include/node_config.h` to [.gitignore](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.gitignore) to prevent developers from committing live Wi-Fi credentials and trap API keys.
2. **CI Fix**: Fix [.github/workflows/tests.yml](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.github/workflows/tests.yml) by changing `astral-sh/setup-uv@v6` to `v5`, and add linting checks.
3. **Repository Clean-Up**: Remove or migrate [Patti's code](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/Patti%27s%20code) into `ml/` with standard naming, proper 6-class taxonomy, and division-by-zero guards.
4. **Gitignore Gaps**: Add PlatformIO build directories (`.pio/`, `.pioenvs/`), test run outputs (`runs/`), and model weights (`*.pth`, `models/`) to [.gitignore](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/.gitignore).
5. **Documentation Alignment**: Add caution banners in [docs/bring-up.md](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/bring-up.md) warning against running `install.sh` on the shared bench Pi, synchronize classifier status in [docs/cv-research-status.md](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/docs/cv-research-status.md), and qualify CLI paths in the docs.
