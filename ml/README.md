# ML data and experiments

## Quick start: dataset → v0/v1/v2 species ID

```bash
uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -r requirements.txt
python3 fetch_ami.py --out data/ami --other-moths 60     # ~4,000 photos (AMI / GBIF)
python3 fetch_inat.py --out data/inat                    # ~10,300 photos (iNaturalist, research grade, CC; incl. ~3,000 non-moth bycatch)
.venv/bin/python build_dataset.py                        # merge, de-duplicate, split -> data/dataset.csv
.venv/bin/python segment_moths.py                        # flatbug cutout of each insect (~45 min, resumable)
.venv/bin/python make_trap_style.py                      # paste cutouts onto data/liners/*.jpg -> data/synth/
.venv/bin/python build_dataset.py                        # again, to add the trap-style photos
.venv/bin/python train_v1.py                             # BioCLIP 2 features -> v0 zero-shot + v1 head -> models/v1/
.venv/bin/python train_v2.py                             # fine-tuned EfficientNet-B0 -> models/v2/ (~1 h on an M3)
```

**Classes** (what the server stores): `CM`, `OFM`, `OBLR`, `other_moth` (other tortricids, lesser
appleworm, redbanded leafroller, 60 common NE moths), `other_insect` (non-moth bycatch photographed in
NY: `other_insect` and the `bycatch_*` labels: flies, wasps, beetles, bugs, lacewings, leafhoppers,
spiders) and `debris` (bare liner: grid, glare, shadows; later real leaf bits and insect remains).

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
`OBLR`, `other_moth`, `other_insect`, `debris`; one folder per staged card), list the cards set aside for the final
evaluation in `data/own/locked_test.txt`, then re-run `build_dataset.py` and `train_v1.py`. Only new
photos get embedded. Run `train_v1.py --final` once, at the end, for the report's numbers.

**Don't quote the web-photo test scores as trap accuracy.** BioCLIP 2 was trained on iNaturalist/GBIF
photos (TreeOfLife-200M), so it has likely seen these exact test photos with their names, and they
show whole moths in natural poses rather than moths flattened on a glue liner. On Sep 24 2026 the
AMI-only test gave v0 zero-shot 0.72 balanced accuracy and v1 0.996: a sign the pipeline works,
not how well the trap will do.

**Using the model in the server:** in `server/.env` set `SENTINEL_CLASSIFIER=bioclip-v1` and
`SENTINEL_CLASSIFIER_HEAD=../ml/models/v1/head.npz`.

**Photos of used field cards** (phone shots of real liners, e.g. Trécé Pherocon VI cards from the
orchard; full-resolution originals, not the copies a chat app makes):

```bash
cp ~/Downloads/<folder>/*.jpg data/field/inbox/
.venv/bin/python crop_field_cards.py          # flatbug boxes every insect -> data/field/labels.csv, crops/, cutouts/, boxes/
.venv/bin/python label_field_cards.py         # label in the browser: http://localhost:8765
```

`crop_field_cards.py` takes px/mm from each card's printed grid (`--grid-mm`, default 25), measured
around each insect so a card shot at an angle still gets the right scale. The labelling page has two
passes. Pass 1 (anyone): moth / other insect / debris, Delete for things that aren't on the card or
aren't insects, B (or the Draw box button) then drag to box an insect flatbug missed, drag a box's
handles to fix it, ⌘Z to undo. Drag or two-finger scroll pans; pinch, wheel or double-click zooms; F fits.
Pass 2 (a trained eye): the species of every `moth`. `labels.csv` records which boxes flatbug got
right, which it got wrong (`skip`), which needed fixing (`flatbug-edited`) and which it missed
(`manual`), which is also flatbug's score on field cards. Oct 1 2026, 11 cards: 63% of 95 moths
found, worst on pale OBLR on a white card; 7 of 81 boxes were not insects (leg clumps, a leaf bud, the lure).
Leg clumps and wing bits on the card are `debris`, not deleted: the trap sees them too.
These are real moths on glue but not our liner or camera, so they stay apart from `data/own/`.
Insects and debris with species-free labels train the classifier through `make_trap_style.py
--field` (cards in `data/field/test_cards.txt` are held out); `eval_field_cards.py` then scores
`models/v1/head.npz` on every labelled crop as moth / other insect / debris, at the trap camera's
resolution and as photographed, with crops it trained on reported apart (`data/field/eval.md`).
`--mask-neighbours` greys out the other boxes inside each crop first. Oct 2 2026, crops it never
trained on, trap resolution: 92/94 moths, 8/9 other insects, 2/3 debris; masking changed nothing overall.

**Other people's liner photos** (`data/web_liners/`, gitignored; its README lists every source and
license). Collected for liners like ours: white delta liners with a ~25 mm printed grid. Public Roboflow
sets with hand-drawn moth boxes: Trécé CM cards, OFM trap-camera liners, Insect Science delta liners,
grape-moth cards; photos that don't look like our liner are kept apart in `nongrid/`.

```bash
.venv/bin/python eval_detector_roboflow.py --trap-ppm 8   # baseline and flatbug vs the boxes, native and at trap px/mm
.venv/bin/python eval_detector_combine.py                 # what a shape filter and baseline+flatbug add
.venv/bin/python import_roboflow_labels.py ofm-ervins     # a set's boxes + detector boxes -> label_field_cards.py folder
.venv/bin/python label_field_cards.py --data data/web_liners/label/ofm-ervins --port 8767
.venv/bin/python carry_liner_labels.py --data data/web_liners/label/ofm-ervins --write   # labeller stopped first
```

Oct 2 2026, recall of boxed moths: the server's baseline detector found 89–94% on the OFM liners and
full-size CM cards, flatbug 43–60% (20% on OFM at 8 px/mm); both miss most moths under ~25 px long. A
shape filter on baseline boxes (short side ≥ 2.5 mm, long/short ≤ 3.5) halved its false boxes for ~1%
of moths. Only the target moth was boxed in these sets, so precision is a lower bound until the bycatch
is labelled (the OFM set is being labelled in pass 1). `recover_roboflow_originals.py` moved stretched
export boxes back onto original uploads (already run). Trap-camera sets photograph the same liner on
several days: `carry_liner_labels.py` copies labels between them, and train/test splits must keep a
liner's (or a card's) photos together.

**YOLO11 detector and trying models** (`train_yolo.py`, `model_playground.py`):

```bash
.venv/bin/python train_yolo.py                                          # hand-checked liner photos only -> models/yolo11/<run>/
.venv/bin/python train_yolo.py --synth 3000 --out data/yolo-synth --epochs 50   # plus AMI/iNat cutouts pasted on tiles
.venv/bin/python model_playground.py                                    # http://localhost:8770: any detector/classifier on a photo or a screen capture
```

Oct 2 2026, yolo11s at 12 px/mm, trained on the 25 fully labelled photos (field cards + 14 OFM liners), held out
2 field cards + 2 OFM liners: mAP50 moth 0.89, other insect 0.74, debris 0.04 (89 training boxes).

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
