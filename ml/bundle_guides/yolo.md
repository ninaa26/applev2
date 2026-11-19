# Orchard Sentinel: train the insect detector (YOLO11) on this PC

This folder is a one-run bundle from the Orchard Sentinel repo (a camera in a pheromone trap that counts
codling moth, oriental fruit moth and obliquebanded leafroller on a sticky liner). It holds everything this
run needs: `ml/` with the scripts, the labelled liner photos and the starting weights. Nothing else from the
repo is needed. Made by `ml/make_bundle.py --what yolo`.

The job: train YOLO11s to find every insect on a liner photo and call it `moth`, `other_insect` or `debris`,
then zip the result so it can be carried back to the Mac. On the server, only the boxes this detector calls
`moth` go on to the species classifier, so moth recall matters most.

The PC has an **NVIDIA RTX 3060 Ti (8 GB)**. Expect 1–2 hours; training stops by itself when val stops improving.

## Rules

- Run the scripts as they are. Don't edit them to get a run through or to raise a score; if one fails, stop
  and report the error with what you tried.
- Never move photos between splits, and never train on what `ml/data/training/held_out/` lists. The `test` score
  is the one to report; `val` picked the checkpoint and flatters it.
- Everything runs from `ml/` with its `.venv` active.

## 1. Check the machine

```bash
nvidia-smi                                                    # must show the RTX 3060 Ti and a driver
nvidia-smi --query-gpu=name,memory.total --format=csv         # 8 GB (8192 MiB)
```

- **WSL 2 on Windows:** the NVIDIA driver goes on Windows only, never inside WSL, and this folder must sit in
  the Linux home (`~`), not under `/mnt/c/...` (reading photos from the Windows drive is several times slower).
  `wsl -l -v` in PowerShell must say version 2. `ml/RUN_ON_CUDA.md` has more on WSL.
- Plain Linux works the same. Native Windows Python also works; use `py -3.12 -m venv .venv` and
  `.venv\Scripts\activate` in place of the two venv lines below.
- Free disk: about 5 GB (the tiles the script cuts, plus PyTorch).

## 2. Set up (once)

```bash
cd ml
python3 -m venv .venv && . .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements-train.txt
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"   # must print True
```

If the last line prints `False`, the GPU isn't visible: check `nvidia-smi` and the WSL notes above before
going on. CPU training would take days.

## 3. Train

Batch 16 fits the 3060 Ti's 8 GB; don't raise it.

```bash
python train_yolo.py --device 0 --batch 16 --name yolo11s-ppm12-site \
    --blank 'data/real_liners/our_trap_bench_tests/capture_2026-10-06/calibrated_*.jpg' --blank-ppm 15.3
```

What it does first: cuts every checked liner photo (the team labelling site's export, about 190 photos and
9,000 boxes) into 640 px tiles at 12 px/mm, splits them by liner into train, val and test, adds the blank
trap-camera liners as empty tiles, and prints the counts. Then YOLO trains for up to 150 epochs.

- **"CUDA out of memory":** run again with half the `--batch`.
- **Killed with no message (WSL):** WSL ran out of RAM; close other programs, or give WSL more memory in
  `%UserProfile%\.wslconfig`.
- **Epochs slow with the GPU mostly idle** (`nvidia-smi` in a second terminal): the files are under `/mnt/c`.

## 4. Check the result

Read `models/detector/yolo/yolo11s-ppm12-site/summary.json`. Report from its **`test`** block: mAP50,
precision and recall, `per_class_mAP50`, and `at_predict_conf` (precision, recall and F1 per class at the
confidence the server will use). Also give the `predict` block (the NMS IoU and confidence chosen on val) and
the photo and box counts per split from the top of the file.

For comparison, the Oct 8 2026 run (31 training photos, 4 test photos) had test mAP50 0.51, and moth precision
0.79 and recall 0.74 at its chosen confidence. The test photos are not the same this time (they now include two
Cornell field cards), so compare with care.

## 5. Zip the result for the Mac

```bash
cd ml && python - <<'EOF'
import shutil
shutil.make_archive("results-yolo", "zip", ".", "models/detector/yolo/yolo11s-ppm12-site")
EOF
```

On WSL, copy `results-yolo.zip` to Windows with `cp results-yolo.zip /mnt/c/Users/<you>/Downloads/`. On the
Mac it is unzipped inside the repo's `ml/`, so the run lands in `ml/models/detector/yolo/`; `weights/best.pt`
and `summary.json` are what the server needs.

Finish by telling the user: the GPU and batch used, how long it took, the test numbers above, and where the
zip is.
