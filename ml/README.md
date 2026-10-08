# ML data and experiments

## Quick start: dataset → v0/v1/v2 species ID

```bash
uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -r requirements.txt
python3 fetch_ami.py --out data/ami --other-moths 60     # ~4,000 photos (AMI / GBIF)
python3 fetch_inat.py --out data/inat                    # ~10,300 photos (iNaturalist, research grade, CC; incl. ~3,000 non-moth bycatch)
.venv/bin/python build_dataset.py                        # merge, de-duplicate, split -> data/dataset.csv
.venv/bin/python segment_moths.py                        # flatbug cutout of each insect (~45 min, resumable)
.venv/bin/python make_trap_style.py                      # paste cutouts onto data/liners/*.jpg -> data/synth/
.venv/bin/python liner_crops.py                          # real insects on other people's liners, at trap px/mm -> data/web_liners/species/
.venv/bin/python build_dataset.py                        # again, to add the trap-style photos and the real-liner crops
.venv/bin/python train_v1.py                             # BioCLIP 2 features -> v0 zero-shot + v1 head -> models/v1/
.venv/bin/python eval_liner_species.py                   # the head on held-out real liners, as the server would treat each crop
.venv/bin/python train_v2.py                             # fine-tuned EfficientNet-B0 -> models/v2/ (ConvNeXt-T, MobileNetV3-L: RUN_ON_CUDA.md)
```

**Classes** (what the server stores): `CM`, `OFM`, `OBLR`, `other_moth` (other tortricids, lesser
appleworm, redbanded leafroller, 60 common NE moths), `other_insect` (non-moth bycatch photographed in
NY: `other_insect` and the `bycatch_*` labels: flies, wasps, beetles, bugs, lacewings, leafhoppers,
spiders) and `debris` (bare liner: grid, glare, shadows; later real leaf bits and insect remains).

**Trap-style photos.** Web photos are sharp, full size and naturally lit. In the trap a CM is ~150 px
long (wide-angle IMX219, ~15 px/mm in the centre, 10–11 at the edges; ~70 px on the old webcam) on a
gridded liner under the trap's LED. `segment_moths.py` cuts each insect out with
flatbug; `make_trap_style.py` pastes it onto real liner photos at its real length in mm and a random
5-16 px/mm, tints it by the liner's light, adds a contact shadow, crops the way the server does
(pad 0.35), then blurs, adds noise and JPEG-compresses. `python make_trap_style.py --preview 48`
writes a contact sheet. Each copy keeps its source photo's split. **Liner photos:** put 640×480 or
larger photos of a *blank* liner, taken by the trap camera, in `data/liners/`. Today there are 3,
all from the old 640×480 webcam in the lab (Sep 24 2026), and all 24,112 trap-style photos are pasted
onto them: the set has never seen the IMX219's resolution, lens or light. Blank-liner IMX219 photos
exist (`data/trap_camera/capture_2026-10-06/`, Oct 6 2026) but were taken before the LED was moved;
once the camera is recalibrated for the new light, put fresh blank-liner photos in `data/liners/` and
re-run `make_trap_style.py`, `build_dataset.py` and `train_v1.py`.

**Photos from the trap itself.** `export_server_crops.py --server ../server/data` writes every insect
reviewed on the dashboard (confirmed/relabelled → that label, rejected → `debris`) into
`data/own/<label>/<card>/`, cropped exactly like the server crops for the classifier.
`--empty-card <card>` adds every detection on a card known to be blank as `debris`; only use it for
photos of a real liner, not bench shots of the room. As of Oct 6 2026 `data/own/` does not exist: the server
holds 6 webcam photos (640×480, Sep 24 and Oct 1 2026) and no reviews, so no model has trained on or been
scored against our own trap.

**Adding our own photos later:** save insect crops as `data/own/<label>/<card>/*.jpg` (labels `CM`, `OFM`,
`OBLR`, `other_moth`, `other_insect`, `debris`; one folder per staged card), list the cards set aside for the final
evaluation in `data/own/locked_test.txt`, then re-run `build_dataset.py` and `train_v1.py`. Only new
photos get embedded. Run `train_v1.py --final` once, at the end, for the report's numbers.

**Don't quote the web-photo test scores as trap accuracy.** BioCLIP 2 was trained on iNaturalist/GBIF
photos (TreeOfLife-200M), so it has likely seen these exact test photos with their names, and they
show whole moths in natural poses rather than moths flattened on a glue liner. Oct 7 2026,
`models/v1` (trained on 6,846 iNat + 2,684 AMI + 16,976 trap-style photos + 2,099 real-liner crops,
C=10, T=1.18), balanced accuracy on the test split: web photos v0 zero-shot 0.67, v1 0.98; their trap-style
copies (webcam liners, 5–16 px/mm) v0 0.54, v1 0.89. A sign the pipeline works, not how well the trap
will do. Earlier heads are kept for comparison: `models/v1-no-liner/` (Oct 2, no real-liner crops: 0.99 and
0.90), `models/v1-2026-10-07a/` (the first Oct 7 head, real OFM and CM crops but no real non-target moths)
and `models/v1-2026-10-07b/` (with the non-target moths, before the field cards and the finished OFM-liner labels).

**Real insects on real liners** (`liner_crops.py`, `eval_liner_species.py`). The web-photo → trap gap is
the main problem in the insect-ML literature (8–16 points on AMI traps), and ours was worse: Oct 7 2026,
the Oct 2 head on other people's liner photos at 15 px/mm found 43% of 162 OFM (19% were counted
automatically as something else) and no debris. `liner_crops.py` turns real-liner photos into crops at trap
resolution (15 and 10 px/mm), 2,309 insects from 123 liners and cards:

- **OFM liners** (trap camera): 478 OFM (the uploader's boxes), 664 other insects and 87 debris (pass-1 labels).
- **CM cards** (phone, full-size photos, 10 px/mm only): 131 CM.
- **PTM liners** (Insect Science delta liners, phone, ~7 px/mm, kept as photographed): 881 potato tuber moths
  and *Tuta*, as `other_moth`. The only real non-target moths on glue in any number.
- **Field cards** (our orchard's Trécé cards, phone): 35 OBLR, 20 OFM, 13 CM, 1 lesser appleworm, 1 other moth.
  The only real-liner OBLR, and a second source of OFM and CM.

**Who labelled what (Oct 7 2026), and what still needs a person's eye.** Pass 1 on the OFM liners is finished:
454 of its 1,361 boxes were labelled by Claude from contact sheets (`labelled_by_claude.csv` beside
`labels.csv` lists each one, 65 marked unsure; the sheets are in `claude_sheets/`; the labels before that are
in `labels.backup-before-claude.csv`). Species on the field-card moths is Claude's reading of the full-size
crops, in `data/field/species.csv` with the sheets in `data/field/claude_sheets/`: 70 of 94 named, 24 left
blank as unsure, `labels.csv` untouched. Neither has been checked by someone who knows the moths. Tan
leafrollers with oblique bands were called OBLR, grey moths with wavy lines and a dark wing tip CM, small plain
dark-grey moths on the April card OFM; a threelined leafroller or a lesser appleworm among them would look
much the same in these photos.

They join `dataset.csv` as source `liner`, grouped by liner or card. Held out and never trained on:
`liner_crops.TEST_GROUPS` for the OFM liners and CM cards (a third of their moths, including `train_yolo.py`'s
test liners), a hash-picked quarter of the PTM photos (97 of 881 moths), and for the field cards those in
`data/field/test_cards.txt` (CM) plus the April 2025 OFM card and the June 2024 OBLR photos, so every target
has field moths no head trained on. Liners with a fifth of the remaining crops are val, and `train_v1.py`
picks C and the temperature T on them instead of on web photos.

Held-out liners and cards, Oct 7 2026, found / auto & wrong ("auto & wrong" is a wrong label at confidence
≥ 0.80, which the server counts with no one looking):

| true class (crops), set | px/mm | Oct 2 head (web + trap-style) | `v1-2026-10-07b` (+ OFM, CM, PTM liners) | `models/v1` (+ field cards, finished pass 1) |
|---|---|---|---|---|
| OFM (162), OFM liners | 15 | 0.43 / 0.19 | 0.94 / 0.00 | 0.94 / 0.00 |
| OFM (162), OFM liners | 10 | 0.40 / 0.30 | 0.92 / 0.01 | 0.90 / 0.01 |
| OFM (19), field card | 10 | | 18 of 19 / 0 | 18 of 19 / 0 |
| CM (37), CM cards | 10 | 0.89 / 0.00 | 0.89 / 0.00 | 0.92 / 0.00 |
| CM (10), field cards | 10 | | 10 of 10 / 0 | 10 of 10 / 0 |
| OBLR (14), field cards | 10 | | 14 of 14 / 0 | 14 of 14 / 0 |
| other moth (97), PTM liners | ~7 | 0.07 / 0.53 | 0.96 / 0.00 | 0.92 / 0.01 |
| other insect (127), OFM liners | 15 | | 0.80 / 0.02 | 0.85 / 0.02 |
| other insect (127), OFM liners | 10 | | 0.72 / 0.07 | 0.81 / 0.03 |
| debris (12), OFM liners | 15 | | 6 of 12 | 7 of 12 |

Two things in that table carry the weight. The other-moth row: before the PTM liners a head trained on real
OFM had learnt that a moth on a real liner is OFM (71 of 97 unseen non-target moths called OFM). And the
field-card rows in the middle column: that head had never seen a field-card moth or a real-liner OBLR, and
it agrees with the species read off the photos on 42 of 43. Two readings that could share a mistake, but
they were made separately.

A check on photos from no set at all (Oct 7 2026): 24 codling moths boxed by hand on two liner photos from
Wikimedia Commons and iNaturalist (`data/web_liners/species/independent/`, oblique views, ~85 px moths).
`v1-2026-10-07b` called 18 CM, 4 other moth, 2 OFM, none wrong at ≥ 0.80.

Read all of this for what it is: the species is an uploader's claim or a reading from a photo, the cameras
are not ours, most classes lean on one source (the PTM liners have a green grid, the OFM liners a black one),
the field-card numbers are 10–19 moths each, and the same held-out crops are looked at each time a head is
compared. A development check; the report's numbers still come from our own locked cards.

**Training somewhere else.** `data/` is not in git, so `make_bundle.py` packs the scripts, `dataset.csv`,
every image it lists (web photos shrunk to 512 px), the cached features, the current head and what
`train_yolo.py` reads into `data/bundle/orchard-train.zip` (about 1.8 GB). [RUN_ON_CUDA.md](RUN_ON_CUDA.md) has
the commands for a machine with a CUDA GPU: three v2 runs (`efficientnet_b0`, `convnext_tiny`,
`mobilenet_v3_large`), v1, and the detector, which now has all 31 OFM liner photos. `train_v2.py` keeps the
epoch that does best on real-liner val crops and saves a temperature with the weights; the server applies it.

**The CUDA runs (Oct 8 2026, RTX 3060 Ti under WSL).** Three fine-tuned CNNs, 20 epochs each, scored on the
same 785 held-out real-liner crops as `models/v1` (15 and 10 px/mm together), each with its own temperature:

| | `models/v1` linear head | `v2/` EfficientNet-B0 | `v2-convnext/` ConvNeXt-T | `v2-mobilenet/` MobileNetV3-L |
|---|---|---|---|---|
| all crops right | 0.89 | 0.90 | 0.87 | 0.90 |
| wrong at ≥ 0.80 (counted with no one looking) | 1.3% | 4.5% | 6.6% | 4.2% |
| OFM, OFM liners (324) | 299 | 292 | 291 | 301 |
| **OFM, held-out field card (19)** | **18** | **3** | **6** | **4** |
| CM, CM cards (37) | 34 | 37 | 37 | 37 |
| CM, field cards (12) | 12 | 12 | 12 | 12 |
| OBLR, field cards (17) | 17 | 17 | 17 | 17 |
| other moth, PTM liners (97) | 89 | 97 | 97 | 97 |
| other insect, OFM liners (254) | 211 | 238 | 206 | 218 |
| debris, OFM liners (24) | 17 | 10 | 17 | 16 |

**v1 stays.** The CNNs match it on average and are better on bycatch and on sets they trained a part of, but
on the one OFM card from a different camera they call the moths other moth or CM, a third of them at ≥ 0.80.
Every OFM they trained on came from one trap camera, and fine-tuning the whole network learnt that camera;
the frozen BioCLIP features did not. That is the single-source warning above coming true, and it would not
show in any of the three tables `train_v2.py` prints, where the field card is 19 crops among 343 OFM. Their
wrong-at-0.80 rate is also 3–5 times v1's. Averaging all four models gets 0.93 of crops right and 0.6% wrong
at ≥ 0.80, but only 10 of the 19 field-card OFM. The field-card species are Claude's reading of the photos, so
a wrong reading of that card would change this; v1 and that reading were made separately and agree.
v1 retrained on the CUDA machine (`models/v1-cuda/`) gives the same tables as the Mac's to within a crop or two.

**Detector on the same machine** (`models/yolo11/yolo11s-ppm12-cuda/`, 31 training photos with the finished
OFM-liner labels, 7 val, the same 4 test photos, stopped at epoch 106). At its saved confidence (0.49) on the
test photos: moth precision 0.79, recall 0.74; other insect 0.82, 0.54; debris 0 of 13. The Oct 7 run with
half the labelled photos (`yolo11s-ppm12-blank`) had moth 0.77, 0.80 and other insect 0.86, 0.47. Four test
photos cannot separate those: twice the labels did not visibly improve moth detection, and debris is still
not found (225 training boxes).

**OFM is the weak class on web photos.** There are 117 OFM web photos from 71 observations; the test
split has 12 photos from 8 observations (96 trap-style copies). On those trap-style copies the Oct 7 head
found 89% of OFM at precision 0.32 (the same as the Oct 2 head): most crops it calls OFM there are CM or
other moths.

**Using the model in the server:** in `server/.env` set `SENTINEL_CLASSIFIER=bioclip-v1` and
`SENTINEL_CLASSIFIER_HEAD=../ml/models/v1/head.npz`, and install the server's `[bioclip]` extra. As of Oct 6
2026 this has not been done: the server runs `SENTINEL_CLASSIFIER=none` and its venv has no torch, so species
ID has only ever run from the scripts in `ml/`.

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
(`manual`), which is also flatbug's score on field cards. Oct 2 2026 labels, 11 cards, phone
resolution: 60 of 94 moths found (64%), worst on pale OBLR on a white card; 7 of 81 boxes were not
insects (leg clumps, a leaf bud, the lure).
Leg clumps and wing bits on the card are `debris`, not deleted: the trap sees them too.
These are real moths on glue but not our liner or camera, so they stay apart from `data/own/`.
Insects and debris with species-free labels train the classifier through `make_trap_style.py
--field` (cards in `data/field/test_cards.txt` are held out); `eval_field_cards.py` then scores
`models/v1/head.npz` on every labelled crop as moth / other insect / debris, at the trap camera's
resolution and as photographed, with crops it trained on reported apart (`data/field/eval.md`).
`--mask-neighbours` greys out the other boxes inside each crop first. Oct 2 2026, `models/v1`, crops it
never trained on, shrunk to 8 px/mm (the trap camera is ~15): 92/94 moths, 8/9 other insects, 2/3 debris;
masking changed nothing overall. The non-moth part of that is 12 crops from two cards. Real debris is
not recognised: of the 6 debris crops whose copies *were* in training, none was called debris (5 other
insect, 1 moth), so 2 of 9 in all. Species is unchecked: no pass-2 labels exist yet, and the 94 moths
were called 42 OBLR, 24 OFM, 16 CM, 10 other moth, 2 other insect at a median confidence of 0.99.
Oct 7 2026, the Oct 7 head (with real-liner crops), same crops shrunk to 15 px/mm: 94/94 moths, 7/9 other
insects, 0/3 debris not in training (0/6 of those in training); the moths' species calls keep the same
card-by-card pattern, so the OFM liners did not teach it to call every moth OFM.

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
full-size CM cards, flatbug 43–60% (20% on OFM at 8 px/mm); both miss most moths under ~25 px long. Where
the baseline's recall is good its count is not: it reported 2.3–2.8 times the boxed moths on the OFM liners
and 9.5–12.5 times on the full-size CM cards (bycatch included), so a count needs the classifier or review. On
the other two sets the baseline does far worse: 30% of boxed moths on the Insect Science liners (native,
7.3 px/mm) and 52% on the grape-moth cards (native, 8.4 px/mm), 6% and 17% at 8 px/mm; flatbug under 10%
on both. A shape filter on baseline boxes (short side ≥ 2.5 mm, long/short ≤ 3.5) cut its unmatched boxes
per photo from 60 to 32 on the full-size CM cards and from 22 to 13 on the OFM liners (native), losing 1
of 131 and 5 of 482 moths; it is not in the server's detector yet. Only the target moth was boxed in
these sets, so precision is a lower bound until the bycatch is labelled. Pass 1 on the OFM set: 14 of 31
photos done, 454 boxes left (Oct 2 2026); `carry_liner_labels.py` not yet run, no pass 2 anywhere. `recover_roboflow_originals.py` moved stretched
export boxes back onto original uploads (already run). Trap-camera sets photograph the same liner on
several days: `carry_liner_labels.py` copies labels between them, and train/test splits must keep a
liner's (or a card's) photos together.

**YOLO11 detector and trying models** (`train_yolo.py`, `model_playground.py`):

```bash
.venv/bin/python train_yolo.py                                          # hand-checked liner photos only -> models/yolo11/<run>/summary.json
.venv/bin/python train_yolo.py --synth 3000 --out data/yolo-synth --epochs 50   # plus AMI/iNat cutouts pasted on tiles
.venv/bin/python train_yolo.py --blank 'data/trap_camera/capture_2026-10-06/calibrated_*.jpg' --blank-ppm 15.3   # plus blank trap-camera liners, no boxes
.venv/bin/python model_playground.py                                    # http://localhost:8770: any detector/classifier on a photo or a screen capture
```

`train_yolo.py` splits the fully labelled photos three ways, by card/liner: **test** (`data/field/test_cards.txt`
plus two OFM liners; scored once, after training), **val** (about 15% of the rest, the same photos every run;
training stops on them and keeps the epoch that does best on them) and train. Only the `test` block of
`summary.json` is a score to quote.

Oct 2 2026, yolo11s at 12 px/mm, 25 fully labelled photos (11 field cards + 14 OFM liners): 21 trained, 2 field
cards + 2 OFM liners held out: mAP50 0.55 over the three classes (precision 0.49, recall 0.59); moth 0.89, other
insect 0.74, debris 0.04 (89 training boxes). **These are optimistic:** that run had no separate val set, so the
same 4 held-out photos also picked the best of 150 epochs. Not yet re-run with the three-way split (16 train /
5 val / the same 4 test photos); `data/yolo/` and `models/yolo11/yolo11s-ppm12/` on disk are still the old two-way
run. Replace these numbers when it is. The `--synth 3000` run was stopped at epoch 7 of 50 and has no score.

**Oct 7 2026, the first run with a test score** (`models/yolo11/yolo11s-ppm12-blank/`, data in `data/yolo-blank/`):
yolo11s at 12 px/mm, 16 photos trained + 150 blank trap-camera tiles, 5 val, 4 test (2 field cards + 2 OFM liners,
498 boxes), overlap 224, stopped at epoch 141. On the test photos: mAP50 0.52 over the three classes; moth 0.82,
other insect 0.72, debris 0.01 (13 test boxes, 112 in training). At the settings chosen on val (confidence 0.425, NMS
IoU 0.5): moth precision 0.77, recall 0.80; other insect 0.86 and 0.47; debris never found. The Oct 2 figures above
(moth 0.89) were on photos that also picked the checkpoint; on val this run scores moth 0.92, so the honest number
is about 0.1 lower than the flattering one. Through the server's detector on IMX219 photos: 0 boxes on the empty
liner (4 with the Oct 2 weights), but that photo's own tiles were in training as blanks, so it shows the blanks were
learned, not that a new empty liner would be clean. It finds only 1 and 2 of the 7 pinned specimens: they are
15–45 mm, far larger than anything it trained on, and say nothing about 6–14 mm moths. Still no target-size moth
from the trap camera to test on.

**Oct 8 2026, twice the labelled photos** (`models/yolo11/yolo11s-ppm12-cuda/`, data in `data/yolo-cuda/`, on an RTX
3060 Ti): the same settings and the same 4 test photos (498 boxes), but 31 photos trained (2,888 boxes: 1,036 moth,
1,627 other insect, 225 debris) + the same 150 blank tiles, 7 val; stopped at epoch 106 (patience 40). On the test
photos: mAP50 0.51 over the three classes; moth 0.77, other insect 0.73, debris 0.03. At the settings chosen on val
(confidence 0.49, NMS IoU 0.5): moth precision 0.79, recall 0.74 (Oct 7: 0.77, 0.80); other insect 0.82 and 0.54
(0.86, 0.47); debris 0 of 13. On its own val photos moth scores 0.90, so the val-to-test drop is the same as before.
Four test photos cannot tell the two runs apart; what they do show is that doubling the OFM-liner labels did not
lift moth detection on the field cards and liners held out, and that 225 debris boxes are still not enough to
find debris. Not yet run through the server on IMX219 photos.

Other options, none used in a scored run yet: `--imgsz 800` enlarges the tiles for the network (modest gains
for small insects elsewhere); `--one-insect-class` trains `insect` + `debris` instead of three classes (a generic
insect detector found 80% of species it had never seen, and the classifier names them anyway; our `debris` class
scored 0.04). After training, the confidence cut and the NMS IoU are chosen on the val photos by best F1 and saved
as `predict` in `summary.json`, with precision and recall at that cut per class; the server reads them. Oct 7 2026,
the Oct 2 weights on their 4 val photos (the ones that also picked the checkpoint): NMS IoU 0.5 → moth F1 0.84,
0.7 → 0.84, 0.9 → 0.74; best confidence 0.14, not the 0.25 default. A setting tuned for another trap (0.9 in
Yolo-pest) would have cost us.

Tiles overlap by at least the longest single moth (18 mm: 224 px at 12 px/mm; it was 160 px for the Oct 2 run),
so every insect is whole in some tile. `--blank` adds blank-liner photos from the trap camera as tiles with no
boxes: the grid, glare, walls and clips the detector must learn to leave alone. The Oct 7 and Oct 8 runs use both.

The server can run a YOLO run: `SENTINEL_DETECTOR=yolo` with `SENTINEL_DETECTOR_MODEL=<run>/weights/best.pt`
(`docs/server-on-mac.md`); the playground merges tiles the same way the server does. Oct 7 2026, the Oct 2 weights
through the server's detector on IMX219 photos (15 px/mm, shrunk to 12): 4 false boxes on the empty liner
(`capture_2026-10-06/calibrated_1.jpg`) and 9 boxes for the 7 pinned specimens under the new light
(`capture_bugs_light2_2026-10-06/calibrated_1.jpg`). Two photos, not a score; the false boxes on a blank liner are
what `--blank` is for.

## What insect-ML papers found, and what we do about it

Every finding in the Oct 6 2026 literature notes, with what was changed, tested, left alone or could not be
done: [docs/ml-research-status.md](../docs/ml-research-status.md). What it changed in this folder:

- **Real-liner crops in training and as a held-out test** (`liner_crops.py`, above): the one change that moved
  the score.
- **C and a temperature picked on real-liner val crops** (`train_v1.py`); the head carries the temperature and
  the server, the playground and the scorers apply it.
- **`eval_liner_species.py`** reports recall with a 95% interval, what the server would do with each crop, and
  recall by crop size.
- **`clean_dataset.py`** lists web photos far from the rest of their species (label cards, blank frames, moths
  that are a dot, pinned specimens) and photos the head would label differently, with contact sheets in
  `data/clean/`. It excludes nothing: a person copies the junk into `data/exclude.csv` (`path,why`), which
  `build_dataset.py` leaves out along with its trap-style copies. Oct 7 2026: 220 odd photos and 21 possible
  label errors of 13,564; leaving all 220 out did not change the real-liner score.
- **`train_v2.py`** has RandAugment, mixed resolution, a warm-up epoch and label smoothing 0.1, and reports
  the held-out real-liner test. Run Oct 8 2026 on three architectures (the CUDA runs, above): none replaces v1.

Tried on the held-out liners and dropped (Oct 7 2026, numbers in the status page): a moth / non-moth gate
before the species head, a head on the 15 fine labels, capping labels at 1,000 photos, leaving out spiders,
leaving out the AMI photos, a temperature fitted on web photos, zero-shot life-stage filtering, black-padded
tight crops.

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
| v2 | fine-tuned flatbug or YOLO11 (YOLO11: three scored runs, the latest Oct 8 2026; playground and `SENTINEL_DETECTOR=yolo`) | fine-tuned EfficientNet-B0 / ConvNeXt-T / MobileNetV3-L (`train_v2.py`, from Patti's MobileNet script); trained Oct 8 2026, none beats v1 on OFM from a second camera | `models/yolo11/<run>/`, `models/v2/<arch>.pt` (server `SENTINEL_CLASSIFIER=cnn-v2`) |
