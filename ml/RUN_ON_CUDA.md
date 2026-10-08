# Training on a machine with a CUDA GPU

The bundle from `make_bundle.py` (`orchard-train.zip`, 1.75 GB) holds the scripts, the dataset and every image
it lists. Nothing else is needed from the Mac, and nothing here needs Claude: these are ordinary Python
scripts. Written for an RTX 3060 Ti (8 GB) under WSL 2 on Windows; plain Linux is the same minus the WSL notes.
Allow about 10 GB of free disk and 2–3 hours for everything (estimates, not measured on that card).

## Before you start (WSL)

- **WSL 2, not WSL 1.** In PowerShell: `wsl -l -v`.
- **NVIDIA driver on Windows only.** Install the normal Windows driver; do not install an NVIDIA driver inside
  WSL. `nvidia-smi` inside WSL should then show the 3060 Ti.
- **Keep the files inside WSL.** Unzip into your Linux home (`~`), not under `/mnt/c/...`: reading 41,000
  photos from the Windows drive is several times slower.
- **Internet for the first run:** PyTorch, the packages, and each network's pretrained starting weights.

## Set up (once)

```bash
sudo apt update && sudo apt install -y zip unzip python3-venv
cp /mnt/c/Users/YOU/Downloads/orchard-train.zip ~/ && cd ~        # YOU = your Windows user name
unzip -q orchard-train.zip && cd orchard-train/ml
python3 -m venv .venv && . .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements-train.txt
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"   # must print True
```

If the last line prints `False`, the GPU is not visible in WSL: check `nvidia-smi`. Every command below runs
from `~/orchard-train/ml` with the environment active (`. .venv/bin/activate` in a new terminal).

## 1. Species classifier, fine-tuned CNN (v2)

Three runs, each a different size of network. Each prints its time after every epoch, so one epoch × 20 is
the run's length: very roughly 15–30 min, 25–45 min and 10–25 min.

```bash
python train_v2.py --arch efficientnet_b0    --epochs 20 --batch 64 --samples-per-epoch 24000 --out models/v2
python train_v2.py --arch convnext_tiny      --epochs 20 --batch 32 --samples-per-epoch 24000 --lr 1e-4 --out models/v2-convnext
python train_v2.py --arch mobilenet_v3_large --epochs 20 --batch 64 --samples-per-epoch 24000 --out models/v2-mobilenet
```

If one result tonight is enough, run the first.

- **"CUDA out of memory":** halve that run's `--batch` and run it again.
- **Killed with no error message:** WSL ran out of RAM (it gets about half the PC's by default). Add `--workers 4`,
  or `--workers 2`.
- **Slow epochs with the GPU mostly idle** (`nvidia-smi` in a second terminal): the photos are the bottleneck.
  Check the files are not under `/mnt/c`, and add `--workers 8` if the PC has 8 or more cores.

Each run writes `<arch>.pt`, `metrics.json` and `report.md` into its folder. **The table to read is
"test · real liners (held out)"** in `report.md`: recall for CM, OFM, OBLR and other_moth on moths that sat on
glue and that no model trained on. The web-photo and trap-style tables only show the pipeline works.

## 2. Species classifier, linear head on BioCLIP 2 (v1)

Already trained on the Mac (`models/v1/`; its `report.md` is the bar v2 has to beat). Optional: retraining it
here takes a few minutes with the cached features in `data/embeddings/`, plus a model download of a GB or
more the first time.

```bash
python train_v1.py --device cuda --batch 64
python eval_liner_species.py --device cuda        # what the server would do with each held-out crop
```

## 3. Detector (YOLO11)

Uses the fully labelled photos only: 11 field cards and all 31 OFM liner photos (17 of them finished on
Oct 7 2026), plus blank trap-camera liners as empty tiles. Perhaps 30–60 minutes; it stops early when val
stops improving, so it can be left overnight. Batch 16 for 8 GB; drop to 8 if it runs out of memory.

```bash
python train_yolo.py --device 0 --batch 16 --out data/yolo-cuda --name yolo11s-ppm12-cuda \
    --blank 'data/trap_camera/capture_2026-10-06/calibrated_*.jpg' --blank-ppm 15.3
```

Read the `test` block of `models/yolo11/yolo11s-ppm12-cuda/summary.json`; the `val` block picked the
checkpoint and flatters it.

## Bring back

Zip the results and copy the zip to Windows, then to the Mac:

```bash
cd ~/orchard-train/ml && zip -qr results.zip models -x 'models/v1/*' && cp results.zip /mnt/c/Users/YOU/Downloads/
```

On the Mac, unzip it inside `ml/` so the folders land under `ml/models/`:

- `models/v2/`, `models/v2-convnext/`, `models/v2-mobilenet/`
- `models/yolo11/yolo11s-ppm12-cuda/` (`weights/best.pt` and `summary.json` are what matter)

Then in `server/.env`: `SENTINEL_CLASSIFIER=cnn-v2` with `SENTINEL_CLASSIFIER_MODEL=../ml/models/v2/<arch>.pt`,
or `bioclip-v1` with `SENTINEL_CLASSIFIER_HEAD=../ml/models/v1/head.npz`, whichever scored better on the real
liners.

Done once, Oct 8 2026, on an RTX 3060 Ti: v1 scored better (the CNNs miss most OFM from a second camera), so
the server stays on `bioclip-v1`. The numbers are in [README.md](README.md), "The CUDA runs".

## What the labels are worth

The species on real liners comes from three places: the uploader of each public set, pass-1 labels on the
OFM liners (454 of them by Claude on Oct 7 2026, listed in `labelled_by_claude.csv`), and species on the
field-card moths read from the photos by Claude (`data/field/species.csv`, not yet checked by anyone who
knows the moths). Treat every score as provisional until those are checked.
