# ML data and experiments

## Quick start: dataset → v0/v1/v2 species ID

```bash
uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -r requirements.txt
python3 fetch_ami.py --out data/ami --other-moths 60     # ~4,000 photos (AMI / GBIF)
python3 fetch_inat.py --out data/inat                    # ~8,500 photos (iNaturalist, research grade, CC)
.venv/bin/python build_dataset.py                        # merge, de-duplicate, split -> data/dataset.csv
.venv/bin/python segment_moths.py                        # flatbug cutout of each insect (~45 min, resumable)
.venv/bin/python make_trap_style.py                      # paste cutouts onto data/liners/*.jpg -> data/synth/
.venv/bin/python build_dataset.py                        # again, to add the trap-style photos
.venv/bin/python train_v1.py                             # BioCLIP 2 features -> v0 zero-shot + v1 head -> models/v1/
.venv/bin/python train_v2.py                             # fine-tuned EfficientNet-B0 -> models/v2/ (~1 h on an M3)
```

**Classes** (what the server stores): `CM`, `OFM`, `OBLR`, `other_moth` (other tortricids, lesser
appleworm, redbanded leafroller, 60 common NE moths) and `debris`: bare liner (grid, glare, shadows)
plus non-moth bycatch, fetched as `other_insect` (flies, wasps, beetles, true bugs photographed in NY).

**Trap-style photos.** Web photos are sharp, full size and naturally lit. In the trap a CM is ~70 px
long (webcam) under orange light on a gridded liner. `segment_moths.py` cuts each insect out with
flatbug; `make_trap_style.py` pastes it onto real liner photos at its real length in mm and a random
5-16 px/mm, tints it by the liner's light, adds a contact shadow, crops the way the server does
(pad 0.35), then blurs, adds noise and JPEG-compresses. `python make_trap_style.py --preview 48`
writes a contact sheet. Each copy keeps its source photo's split. **Liner photos:** put 640×480 or
larger photos of a *blank* liner, taken by the trap camera, in `data/liners/`. Today there are 3,
all from the webcam in the lab, so the trap-style set knows little about lighting variety; add more
as soon as the Camera Module 3 is in the trap, and re-run `make_trap_style.py`.

**Photos from the trap itself.** `export_server_crops.py --server ../server/data` writes every insect
reviewed on the dashboard (confirmed/relabelled → that label, rejected → `debris`) into
`data/own/<label>/<card>/`, cropped exactly like the server crops for the classifier.
`--empty-card <card>` adds every detection on a card known to be blank as `debris`; only use it for
photos of a real liner, not bench shots of the room.

**Adding our own photos later:** save insect crops as `data/own/<label>/<card>/*.jpg` (labels `CM`, `OFM`,
`OBLR`, `other_moth`, `debris`; one folder per staged card), list the cards set aside for the final
evaluation in `data/own/locked_test.txt`, then re-run `build_dataset.py` and `train_v1.py`. Only new
photos get embedded. Run `train_v1.py --final` once, at the end, for the report's numbers.

**Don't quote the web-photo test scores as trap accuracy.** BioCLIP 2 was trained on iNaturalist/GBIF
photos (TreeOfLife-200M), so it has likely seen these exact test photos with their names, and they
show whole moths in natural poses rather than moths flattened on a glue liner. On Sep 24 2026 the
AMI-only test gave v0 zero-shot 0.72 balanced accuracy and v1 0.996: a sign the pipeline works,
not how well the trap will do.

**Using the model in the server:** in `server/.env` set `SENTINEL_CLASSIFIER=bioclip-v1` and
`SENTINEL_CLASSIFIER_HEAD=../ml/models/v1/head.npz`.

## Get training photos from AMI (primary external source)

```bash
python3 fetch_ami.py --out data/ami --dry-run              # counts only (~330 MB of metadata, cached)
python3 fetch_ami.py --out data/ami --other-moths 60       # download: our moths + 60 common NE moths
```

Checked Sep 23 2026 (adults, all AMI splits): CM 729, OBLR 1,300, **OFM 72**, lesser appleworm 84,
redbanded leafroller 1,300, 900 "other moth" photos at 60 × 15. A few links (the SCAN museum portal)
refuse automated downloads; the script logs them in `manifest.csv` and moves on. `manifest.csv`
also keeps every photo's source URL, for credits.

These are photos of live or pinned moths, **not** moths on sticky liners. Use them to train only,
never to report accuracy. Accuracy numbers come from our own staged-card photos, split by card.

## Model versions (see the architecture page)

| Version | Detector | Species ID | Where it lives |
|---|---|---|---|
| v0 | baseline OpenCV → flatbug | none → BioCLIP 2 zero-shot | `server/sentinel_server/pipeline/` (`SENTINEL_DETECTOR`, `SENTINEL_CLASSIFIER`) |
| v1 | flatbug | BioCLIP 2 features + logistic regression (`train_v1.py`); InsectNet / DINOv2 comparison still to do | `ml/train_v1.py` → `models/v1/head.npz`, server `SENTINEL_CLASSIFIER=bioclip-v1` |
| v2 | fine-tuned flatbug or YOLO11 | fine-tuned EfficientNet-B0 / MobileNetV3 (`train_v2.py`, from Patti's MobileNet script) vs v1 | `models/v2/<arch>.pt`; runs on the Mac's MPS (~1 h) |
