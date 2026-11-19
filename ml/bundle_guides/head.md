# Orchard Sentinel: train the moth species head (BioCLIP 2) on this PC

This folder is a one-run bundle from the Orchard Sentinel repo (a camera in a pheromone trap that counts
codling moth, oriental fruit moth and obliquebanded leafroller on a sticky liner). It holds everything this
run needs: `ml/` with the scripts, the dataset and every photo it lists. Nothing else from the repo is needed.
Made by `ml/make_bundle.py --what head`.

The job: train the species head for boxes the detector has already called `moth`. BioCLIP 2 (a large
pretrained model of living things) turns each photo into features, and a small linear head on top learns four
classes: `CM` (codling moth), `OFM` (oriental fruit moth), `OBLR` (obliquebanded leafroller) and
`other_moth`. Then zip the result so it can be carried back to the Mac.

The data (`ml/data/training/classifier/moth_dataset.csv`, from `build_moth_dataset.py`):
- 44,845 web photos of these moths and look-alikes (iNaturalist, GBIF and others, adults only), split by
  observation into train, val and test. The head learns from train; the regularisation C and the temperature
  T are picked on val; test is a check that the pipeline works.
- **No liner photos.** Liner labels are moth / other insect / debris only, so nothing in this run says how the
  head does on a real liner. That comes later, from the trap's own cards. Don't present the web test as trap
  accuracy: BioCLIP 2 has likely seen many of these photos.
- OFM is thin: 116 training photos against about 16,000 CM.

The PC has an **NVIDIA RTX 3060**. Expect 20–60 minutes, nearly all of it BioCLIP reading 45,000 photos once.

## Rules

- Run the scripts as they are. Don't edit them to get a run through or to raise a score; if one fails, stop
  and report the error with what you tried.
- Never change a row's split in `moth_dataset.csv`, and never train on the `test` rows.
- Write the new head under `models/classifier/bioclip_head/archive/`, never over `current/` (that is the head
  the server runs now, included for comparison).
- Everything runs from `ml/` with its `.venv` active.

## 1. Check the machine

```bash
nvidia-smi                                                    # must show the RTX 3060 and a driver
nvidia-smi --query-gpu=name,memory.total --format=csv
```

- **WSL 2 on Windows:** the NVIDIA driver goes on Windows only, never inside WSL, and this folder must sit in
  the Linux home (`~`), not under `/mnt/c/...` (reading 46,000 photos from the Windows drive is several times
  slower). `wsl -l -v` in PowerShell must say version 2. `ml/RUN_ON_CUDA.md` has more on WSL.
- Plain Linux works the same. Native Windows Python also works; use `py -3.12 -m venv .venv` and
  `.venv\Scripts\activate` in place of the two venv lines below.
- **Internet is needed:** BioCLIP 2 downloads from Hugging Face (about 1.7 GB) on the first run.
- Free disk: about 10 GB (the 4.1 GB zip, the unzipped folder, PyTorch and BioCLIP).

## 2. Set up (once)

```bash
cd ml
python3 -m venv .venv && . .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements-train.txt
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"   # must print True
```

If the last line prints `False`, the GPU isn't visible: check `nvidia-smi` and the WSL notes above before
going on.

## 3. Train

```bash
python train_v1.py --dataset moth --device cuda --batch 64 \
    --out models/classifier/bioclip_head/archive/moth_only_all_by_species
```

It embeds every photo first (progress every 640 photos; the features are saved as it goes to
`data/training/classifier/bioclip_embeddings/`, so a crash or a rerun picks up where it stopped), then tries six
values of C, picks one and a temperature on val, refits on train and val, and writes `head.npz`, `metrics.json`,
`report.md` and `trained_on.json`.

- **"CUDA out of memory":** run again with `--batch 32`, then 16.
- **Killed with no message (WSL):** WSL ran out of RAM; close other programs, or give WSL more memory in
  `%UserProfile%\.wslconfig`.
- **Hugging Face download fails:** check the internet connection and run again; nothing is lost.

## 4. Check the result

Read `models/classifier/bioclip_head/archive/moth_only_all_by_species/report.md`. Report:
- the C and temperature it picked;
- **"v1 linear head · test · web photos"**: precision and recall per class and the confusion matrix. OFM has
  only 9 test photos, so give its counts ("7 of 9"), not just a percentage;
- the same table for "v0 zero-shot" (BioCLIP with text prompts, no head), as the baseline the head must beat;
- say plainly that these are web photos, not liner photos.

`models/classifier/bioclip_head/current/report.md` is the head the server runs now (six classes, trained
differently). Its numbers are on other test photos, so don't put them side by side as if they were the same test.

## 5. Zip the result for the Mac

```bash
cd ml && python - <<'EOF'
import shutil
shutil.make_archive("results-head", "zip", ".", "models/classifier/bioclip_head/archive/moth_only_all_by_species")
EOF
```

On WSL, copy `results-head.zip` to Windows with `cp results-head.zip /mnt/c/Users/<you>/Downloads/`. On the
Mac it is unzipped inside the repo's `ml/`, so the head lands in `ml/models/classifier/bioclip_head/archive/`.

Finish by telling the user: the GPU and batch used, how long it took, the numbers above, and where the zip is.
