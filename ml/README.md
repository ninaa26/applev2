# ML data and experiments

What each folder under `data/` and `models/` holds: [data/README.md](data/README.md). Folder names are set in
[paths.py](paths.py), and the photos no model trains on are listed in git in
[data/training/held_out/](data/training/held_out/README.md). A copy of the data from before Oct 25 2026 (the old
flat layout: `data/inat`, `data/synth`, `models/v1`, …) is moved into place with `python reorganize_data.py`
(a dry run; then `--write`, and `--undo` to go back).

## Quick start: dataset → v0/v1/v2 species ID

```bash
uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -r requirements.txt
python3 fetch_ami.py --out data/web_moth_photos/ami_gbif --other-moths 60     # ~4,000 photos (AMI / GBIF)
python3 fetch_inat.py --out data/web_moth_photos/inaturalist                    # ~10,300 photos (iNaturalist, research grade, CC; incl. ~3,000 non-moth bycatch)
.venv/bin/python build_dataset.py                        # merge, de-duplicate, split -> data/training/classifier/dataset.csv
.venv/bin/python segment_moths.py                        # flatbug cutout of each insect (~45 min, resumable)
.venv/bin/python make_trap_style.py                      # paste cutouts onto data/trap_style/v1_webcam_2026-09/blank_liners/*.jpg -> data/trap_style/v1_webcam_2026-09/photos/
.venv/bin/python liner_crops.py                          # real insects on other people's liners, at trap px/mm -> data/real_liners/from_the_web/species/
.venv/bin/python build_dataset.py                        # again, to add the trap-style photos and the real-liner crops
.venv/bin/python train_v1.py                             # BioCLIP 2 features -> v0 zero-shot + v1 head -> models/classifier/bioclip_head/current/
.venv/bin/python eval_liner_species.py                   # the head on held-out real liners, as the server would treat each crop
.venv/bin/python train_v2.py                             # fine-tuned EfficientNet-B0 -> models/classifier/cnn/efficientnet_b0/ (ConvNeXt-T, MobileNetV3-L: RUN_ON_CUDA.md)
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
writes a contact sheet. Each copy keeps its source photo's split. **Liner photos and versions:** each set
of trap-style photos is one folder, `data/trap_style/<version>/`, holding the photos of a *blank* liner
(640×480 or larger, taken by the trap camera) it was pasted onto in `blank_liners/`, the fakes in `photos/`,
`manifest.csv` and `preview/`. The one set so far is `v1_webcam_2026-09`: 3 blank-liner photos, all from the
old 640×480 webcam in the lab (Sep 24 2026), and all 24,112 trap-style photos are pasted onto them, so the
set has never seen the IMX219's resolution, lens or light. Blank-liner IMX219 photos
exist (`data/real_liners/our_trap_bench_tests/capture_2026-10-06/`, Oct 6 2026) but were taken before the LED was moved;
once the camera is recalibrated for the new light, make the next set beside v1 rather than over it: put fresh
blank-liner photos in `data/trap_style/v2_imx219_<date>/blank_liners/`, run `segment_moths.py` if there are new
web photos, then `make_trap_style.py --version v2_imx219_<date>` (and `--field`),
`build_dataset.py --trap-style v2_imx219_<date>` and `train_v1.py --out
models/classifier/bioclip_head/archive/<date>_trap_style_v2`. Compare it with `current/` on the real-liner
crops (`eval_liner_species.py --head ...`) before making v2 the default (`TRAP_STYLE_VERSION` in `paths.py`).

**Photos from the trap itself.** `export_server_crops.py --server ../server/data` writes every insect
reviewed on the dashboard (confirmed/relabelled → that label, rejected → `debris`) into
`data/real_liners/our_trap/<label>/<card>/`, cropped exactly like the server crops for the classifier.
`--empty-card <card>` adds every detection on a card known to be blank as `debris`; only use it for
photos of a real liner, not bench shots of the room. As of Oct 6 2026 `data/real_liners/our_trap/` does not exist: the server
holds 6 webcam photos (640×480, Sep 24 and Oct 1 2026) and no reviews, so no model has trained on or been
scored against our own trap.

**Adding our own photos later:** save insect crops as `data/real_liners/our_trap/<label>/<card>/*.jpg` (labels `CM`, `OFM`,
`OBLR`, `other_moth`, `other_insect`, `debris`; one folder per staged card), list the cards set aside for the final
evaluation in `data/training/held_out/our_trap_locked.txt`, then re-run `build_dataset.py` and `train_v1.py`. Only new
photos get embedded. Run `train_v1.py --final` once, at the end, for the report's numbers.

**Don't quote the web-photo test scores as trap accuracy.** BioCLIP 2 was trained on iNaturalist/GBIF
photos (TreeOfLife-200M), so it has likely seen these exact test photos with their names, and they
show whole moths in natural poses rather than moths flattened on a glue liner. Oct 7 2026,
`models/classifier/bioclip_head/current` (trained on 6,846 iNat + 2,684 AMI + 16,976 trap-style photos + 2,099 real-liner crops,
C=10, T=1.18), balanced accuracy on the test split: web photos v0 zero-shot 0.67, v1 0.98; their trap-style
copies (webcam liners, 5–16 px/mm) v0 0.54, v1 0.89. A sign the pipeline works, not how well the trap
will do. Earlier heads are kept for comparison: `models/classifier/bioclip_head/archive/2026-10-07_no_real_liners/` (retrained Oct 7 the Oct 2 way, without real-liner crops: 0.99 and
0.90), `models/classifier/bioclip_head/archive/2026-10-07a_no_nontarget_moths/` (the first Oct 7 head, real OFM and CM crops but no real non-target moths)
and `models/classifier/bioclip_head/archive/2026-10-07b_before_field_cards/` (with the non-target moths, before the field cards and the finished OFM-liner labels).

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
crops, in `data/real_liners/cornell_field_cards/species.csv` with the sheets in `data/real_liners/cornell_field_cards/claude_sheets/`: 70 of 94 named, 24 left
blank as unsure, `labels.csv` untouched. Neither has been checked by someone who knows the moths. Tan
leafrollers with oblique bands were called OBLR, grey moths with wavy lines and a dark wing tip CM, small plain
dark-grey moths on the April card OFM; a threelined leafroller or a lesser appleworm among them would look
much the same in these photos.

They join `dataset.csv` as source `liner`, grouped by liner or card. Held out and never trained on:
`data/training/held_out/web_liners_classifier.txt` for the OFM liners and CM cards (a third of their moths,
including `train_yolo.py`'s test liners), a hash-picked quarter of the PTM photos (97 of 881 moths), and for the
field cards those in `held_out/field_cards.txt` (CM) plus `held_out/field_cards_classifier_only.txt` (the April
2025 OFM card and the June 2024 OBLR photos), so every target
has field moths no head trained on. Liners with a fifth of the remaining crops are val, and `train_v1.py`
picks C and the temperature T on them instead of on web photos. **Found Oct 25 2026:** `make_trap_style.py --field`
only left out `field_cards.txt`, so every head up to then (`current/` included) trained on 480 trap-style copies of
the 11 other insects and debris on the April 2025 OFM card and one June 2024 OBLR photo. Their moths were not pasted
(they are plain `moth` in `labels.csv`), so the held-out moth scores below stand; the other-insect and debris
scores on those cards are optimistic. Fixed for the next `--field` run.

Held-out liners and cards, Oct 7 2026, found / auto & wrong ("auto & wrong" is a wrong label at confidence
≥ 0.80, which the server counts with no one looking):

| true class (crops), set | px/mm | Oct 2 head (web + trap-style) | `archive/2026-10-07b_before_field_cards` (+ OFM, CM, PTM liners) | `models/classifier/bioclip_head/current` (+ field cards, finished pass 1) |
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
Wikimedia Commons and iNaturalist (`data/real_liners/from_the_web/species/independent/`, oblique views, ~85 px moths).
`2026-10-07b_before_field_cards` called 18 CM, 4 other moth, 2 OFM, none wrong at ≥ 0.80.

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
same 785 held-out real-liner crops as `models/classifier/bioclip_head/current` (15 and 10 px/mm together), each with its own temperature:

| | `models/classifier/bioclip_head/current` linear head | `cnn/efficientnet_b0/` | `cnn/convnext_tiny/` | `cnn/mobilenet_v3_large/` |
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
v1 retrained on the CUDA machine (`models/classifier/bioclip_head/archive/2026-10-08_cuda_retrain/`) gives the same tables as the Mac's to within a crop or two.

**Detector on the same machine** (`models/detector/yolo/yolo11s-ppm12-cuda/`, 31 training photos with the finished
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
`SENTINEL_CLASSIFIER_HEAD=../ml/models/classifier/bioclip_head/current/head.npz`, and install the server's `[bioclip]` extra. As of Oct 6
2026 this has not been done: the server runs `SENTINEL_CLASSIFIER=none` and its venv has no torch, so species
ID has only ever run from the scripts in `ml/`.

**Photos of used field cards** (phone shots of real liners, e.g. Trécé Pherocon VI cards from the
orchard; full-resolution originals, not the copies a chat app makes):

```bash
cp ~/Downloads/<folder>/*.jpg data/real_liners/cornell_field_cards/inbox/
.venv/bin/python crop_field_cards.py          # flatbug boxes every insect -> data/real_liners/cornell_field_cards/labels.csv, crops/, cutouts/, boxes/
.venv/bin/python label_field_cards.py         # label in the browser: http://localhost:8765
```

`crop_field_cards.py` takes px/mm from each card's printed grid (`--grid-mm`, default 25), measured
around each insect so a card shot at an angle still gets the right scale. The labelling page has two
passes. Pass 1 (anyone): moth / other insect / debris, Delete for things that aren't on the card or
aren't insects, B (or the Draw box button) then drag to box an insect flatbug missed, drag a box's
handles to fix it, ⌘Z to undo. Drag or two-finger scroll pans; pinch, wheel or double-click zooms; F fits.
Pass 2 (anyone who is sure; `0` when not): the species of every `moth`. `labels.csv` records which boxes flatbug got
right, which it got wrong (`skip`), which needed fixing (`flatbug-edited`) and which it missed
(`manual`), which is also flatbug's score on field cards. Oct 2 2026 labels, 11 cards, phone
resolution: 60 of 94 moths found (64%), worst on pale OBLR on a white card; 7 of 81 boxes were not
insects (leg clumps, a leaf bud, the lure).

Each insect in `labels.csv` has two lengths ([field_lengths.py](field_lengths.py)). `length_mm` is the
long side of the smallest rotated rectangle around its whole outline, with legs, antennae and spread
wings. It is the length `make_trap_style.py --field` gives the cutout. `body_mm` is the same insect
with the slices narrower than a quarter of its widest part trimmed off along its long axis, so legs,
antennae and a grid line the outline ran into are dropped. Compare `body_mm` with the resting lengths
in `LENGTH_MM`. `length_from` is `outline`, or `box` when no usable outline was found and `length_mm`
is the box's long side; treat a `box` length as rough. flatbug's boxes are measured on its outline.
A box drawn or resized in the labeller is measured on save, on the outline GrabCut finds inside the
box (`crop_field_cards.grabcut_mask`, ~0.1 s). Before Oct 25 2026 such a box got the box's long side,
which comes out short for a slim insect lying diagonally (0.71x at 45°) and long for a loosely drawn
box. `crop_field_cards.py --cutouts` re-measures rows from before the column existed. It also prints
a warning for any photo whose labelled moths come out implausibly small or big for its grid scale
(the median of the larger half outside 6–25 mm).

Oct 25 2026, 11 cards, phone resolution (old values in `data/real_liners/cornell_field_cards/labels.backup-before-lengths.csv`).
Re-measuring changed `length_mm` on 41 of the 58 drawn or resized boxes with a grid scale. Drawn
boxes became 0.88x their box length in the median (0.62–1.08x), resized ones 0.96x (0.73–1.12x).
Mostly they got shorter: the boxes were drawn loose and around legs. 8 drawn boxes kept the box
length (`box`). They are insects partly off the photo or hidden, and small insects in loose boxes.
Lengths by species (Claude's reading in `species.csv`):

| species (n) | resting length (`LENGTH_MM`) | before: median (IQR) | `length_mm` | `body_mm` |
|---|---|---|---|---|
| CM (13) | 9–11 mm | 13.8 (12.8–15.5) | 13.3 (12.8–15.1) | 12.9 (12.3–13.5) |
| OFM (19) | 6–7.5 mm | 9.1 (8.5–10.0) | 9.0 (8.5–9.5) | 8.6 (8.3–9.3) |
| OBLR (35) | 10–14 mm | 16.6 (13.6–19.0) | 14.9 (13.2–17.2) | 14.1 (13.1–16.2) |

`body_mm` has the smallest spread within each species (sd of log length 0.10 / 0.11 / 0.17, against
0.12 / 0.12 / 0.19 for `length_mm`). Every species still measures ~1.2–1.35x its resting length on
every card. That points at the scale, not the outlines. The cards' grid may be smaller than the
25 mm `--grid-mm` assumes: one published delta-trap liner is 20.3 × 17.8 cm, and these cards fit a
9 × 9 grid plus a margin. At 20 mm all three species would land inside their ranges. Measure a
card's grid with a ruler before relying on absolute field lengths. Until then, `length_mm` is right
relative to its cutout but probably ~25% too big in mm. Also checked and not changed:
- **Tilt**: one px/mm per insect is enough. On the most tilted card (June 2025, OBLR), the px/mm at
  an insect's two ends differs by at most 1.6%. Measuring at the centre cancels that to first order,
  leaving a length error under 0.01%. The per-insect px/mm on that card scatters ±5% (sd)
  around a smooth fit across the card, which is bigger than the tilt effect.
- **Wrong grid spacing**: none of the 10 cards with a grid locked onto a wrong spacing. Each species
  measures the same ~1.3x on every card, and a wrong lock is 2–5x. The new warning catches a lock 2x
  or more off on a card of small moths, and 3x or more on most cards.
Leg clumps and wing bits on the card are `debris`, not deleted: the trap sees them too.
These are real moths on glue but not our liner or camera, so they stay apart from `data/real_liners/our_trap/`.
Insects and debris with species-free labels train the classifier through `make_trap_style.py
--field` (cards in `data/training/held_out/field_cards.txt` are held out); `eval_field_cards.py` then scores
`models/classifier/bioclip_head/current/head.npz` on every labelled crop as moth / other insect / debris, at the trap camera's
resolution and as photographed, with crops it trained on reported apart (`data/real_liners/cornell_field_cards/eval.md`).
`--mask-neighbours` greys out the other boxes inside each crop first. Oct 2 2026, the head then in `models/v1` (most likely the one saved
Oct 2 00:01, now `models/classifier/bioclip_head/archive/2026-10-01_web_and_trap_style`), crops it
never trained on, shrunk to 8 px/mm (the trap camera is ~15): 92/94 moths, 8/9 other insects, 2/3 debris;
masking changed nothing overall. The non-moth part of that is 12 crops from two cards. Real debris is
not recognised: of the 6 debris crops whose copies *were* in training, none was called debris (5 other
insect, 1 moth), so 2 of 9 in all. Species is unchecked: no pass-2 labels exist yet, and the 94 moths
were called 42 OBLR, 24 OFM, 16 CM, 10 other moth, 2 other insect at a median confidence of 0.99.
Oct 7 2026, the Oct 7 head (with real-liner crops), same crops shrunk to 15 px/mm: 94/94 moths, 7/9 other
insects, 0/3 debris not in training (0/6 of those in training); the moths' species calls keep the same
card-by-card pattern, so the OFM liners did not teach it to call every moth OFM.

**Other people's liner photos** (`data/real_liners/from_the_web/`, gitignored; its README lists every source and
license). Collected for liners like ours: white delta liners with a ~25 mm printed grid. Public Roboflow
sets with hand-drawn moth boxes: Trécé CM cards, OFM trap-camera liners, Insect Science delta liners,
grape-moth cards; photos that don't look like our liner are kept apart in `nongrid/`.

```bash
.venv/bin/python eval_detector_roboflow.py --trap-ppm 8   # baseline and flatbug vs the boxes, native and at trap px/mm
.venv/bin/python eval_detector_combine.py                 # what a shape filter and baseline+flatbug add
.venv/bin/python import_roboflow_labels.py ofm-ervins     # a set's boxes + detector boxes -> label_field_cards.py folder
.venv/bin/python label_field_cards.py --data data/real_liners/from_the_web/label/ofm-ervins --port 8767
.venv/bin/python carry_liner_labels.py --data data/real_liners/from_the_web/label/ofm-ervins --write   # labeller stopped first
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
.venv/bin/python train_yolo.py                                          # hand-checked liner photos only -> models/detector/yolo/<run>/summary.json
.venv/bin/python train_yolo.py --synth 3000 --out data/training/detector/yolo_synth --epochs 50   # plus AMI/iNat cutouts pasted on tiles
.venv/bin/python train_yolo.py --blank 'data/real_liners/our_trap_bench_tests/capture_2026-10-06/calibrated_*.jpg' --blank-ppm 15.3   # plus blank trap-camera liners, no boxes
.venv/bin/python model_playground.py                                    # http://localhost:8770: any detector/classifier on a photo or a screen capture
```

`train_yolo.py` splits the fully labelled photos three ways, by card/liner: **test** (`data/training/held_out/field_cards.txt`
plus two OFM liners; scored once, after training), **val** (about 15% of the rest, the same photos every run;
training stops on them and keeps the epoch that does best on them) and train. Only the `test` block of
`summary.json` is a score to quote.

Oct 2 2026, yolo11s at 12 px/mm, 25 fully labelled photos (11 field cards + 14 OFM liners): 21 trained, 2 field
cards + 2 OFM liners held out: mAP50 0.55 over the three classes (precision 0.49, recall 0.59); moth 0.89, other
insect 0.74, debris 0.04 (89 training boxes). **These are optimistic:** that run had no separate val set, so the
same 4 held-out photos also picked the best of 150 epochs. Not yet re-run with the three-way split (16 train /
5 val / the same 4 test photos); `data/training/detector/yolo_real/` and `models/detector/yolo/yolo11s-ppm12/` on disk are still the old two-way
run. Replace these numbers when it is. The `--synth 3000` run was stopped at epoch 7 of 50 and has no score.

**Oct 7 2026, the first run with a test score** (`models/detector/yolo/yolo11s-ppm12-blank/`, data in `data/training/detector/yolo_blank/`):
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

**Oct 8 2026, twice the labelled photos** (`models/detector/yolo/yolo11s-ppm12-cuda/`, data in `data/yolo-cuda/`, on an RTX
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

## Team labelling site (every gridded liner photo, checked and pre-labelled)

All the real-liner photos with a printed grid (our Cornell cards and the web sets, listed in `label_sets.py`;
the matogen Insect Science liners were taken off on Oct 26 2026: ~300 boxes a photo, 82% of all boxes, and too blurry)
go on one website the team labels together, hosted on a Pi behind Tailscale Funnel, so anyone with a login can
reach it from any network. Three steps on the Mac, then the Pi:

```bash
.venv/bin/python check_liner_photos.py     # every set -> data/review/labelling_site/photo_checks.csv (+ a contact sheet per set)
.venv/bin/python prelabel_liners.py        # YOLO11 boxes + v1 classifier labels, all unchecked -> labels.csv, inbox/
.venv/bin/python -m label_site users nina sunny patti jacqui claire anna emily albert --admin nina
.venv/bin/python -m label_site init && .venv/bin/python -m label_site guide
.venv/bin/python -m label_site assign --labellers sunny patti jacqui claire anna emily albert --experts nina --species patti
label_site/deploy.sh pi@100.81.208.95      # code, photos, logins, a user service and a nightly backup on the Pi
label_site/deploy.sh pi@100.81.208.95 --fetch   # later: site.db and an export (labels.csv, COCO, YOLO) back here
```

The guide's photos: `guide` on the Mac copies species examples from the web liner crops (`examples.json`); run on the Pi
(`ssh pi@100.81.208.95 'cd ~/orchard-labels/ml && .venv/bin/python -m label_site guide'`) it also cuts pass-1 examples
from the accepted reference photos (`reference.json`, `ref_*.jpg`). Re-run it there when more reference photos are accepted.

`check_liner_photos.py` decides keep / flag / exclude per photo, by itself (`photo_checks.py` says why each check
matters): no readable grid (no scale, so no trap-sized training insects), the whole shot out of focus or blown out,
a copy instead of the original (our own phone photos only), and the same image saved twice. Tiny, blurred or worn
*insects* are never a reason: every insect gets a box. Shots of the same card are grouped (ORB features + a
homography), so they share a split, and new Cornell cards are held out by a fixed hash (`--write-held-out`). Tags
people set on the site ("unusable", "not a gridded liner", "wrong scale") overrule it on the next run. Oct 25 2026,
first run on the Cornell cards: the grid scale agreed with the px/mm `crop_field_cards.py` measured around each
insect on all 10 cards with a grid (9 within 3%) once the grid was read on its green ink, with each lattice patch
needing a second patch to agree; before that it was off 0.5-10x on 5 cards and called two sharp close-ups blurred.

`prelabel_liners.py` uses our own models: boxes from YOLO11 (`yolo11s-ppm12-cuda`, run as the server's
YoloDetector but at the scale the check measured), labels from the v1 head on server-style crops shrunk to 15
px/mm (pass-1 label in `label`, the species guess in `model_label`). Boxes an earlier pass or an uploader drew
that YOLO missed are added too. Every row starts unchecked (`by` empty): the site shows it dashed until a person
presses Enter (the guess is right) or a label key. YOLO trained on most Cornell cards and the OFM liners, so it
looks best there.

The site (`label_site/`, `python -m label_site serve`): each person gets their own queue, most-unsure photos
first, and a "Done" button; an admin reviews (accept or send back) and pins comments on a spot. About 12 photos
are hidden tests: an expert labels them first, each labeller gets 3 mixed in unknowingly, and the dashboard scores
them (insects found, labels right, and how often they kept a wrong model label, i.e. pressed Enter without
looking). 10% of photos go to two people; their copies are merged, agreement recorded, and disagreements go to a
third. Box tags O overlapping, E cut off, W worn, U unsure; photo tags; brightness/contrast/colour sliders; filters
(not checked, model under 0.8, missed by the detector, disputed); a slider that hides weak detector boxes from
view only; click-to-box (GrabCut); lock and hide boxes; an in-app guide with example crops; an append-only change
log (`revert --user X --since DATE` undoes one person's work); `carry` copies a finished photo's boxes to other
shots of its card; COCO and YOLO export. Logins: salted PBKDF2 hashes, signed 14-day cookies, CSRF tokens, a
15-minute lockout after 5 wrong passwords, and the server only listens on 127.0.0.1 with Funnel the way in.

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
  `data/review/cleaning_suspects/`. It excludes nothing: a person copies the junk into `data/training/classifier/exclude.csv` (`path,why`), which
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
python3 fetch_ami.py --out data/web_moth_photos/ami_gbif --dry-run              # counts only (~330 MB of metadata, cached)
python3 fetch_ami.py --out data/web_moth_photos/ami_gbif --other-moths 60       # download: our moths + 60 common NE moths
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
| (Sep 24) | none | Patti's first classifier: MobileNetV3-Small, codling moth vs not, on an ImageFolder (`mobilenet_cm_patti.py`). Kept for the record; `train_v2.py` grew out of it | `ml/mobilenet_cm_patti.py` → `models/codling_moth_model.pth` |
| v0 | baseline OpenCV → flatbug | none → BioCLIP 2 zero-shot | `server/sentinel_server/pipeline/` (`SENTINEL_DETECTOR`, `SENTINEL_CLASSIFIER`) |
| v1 | flatbug | BioCLIP 2 features + logistic regression (`train_v1.py`); InsectNet / DINOv2 comparison still to do | `ml/train_v1.py` → `models/classifier/bioclip_head/current/head.npz`, server `SENTINEL_CLASSIFIER=bioclip-v1` |
| v2 | fine-tuned flatbug or YOLO11 (YOLO11: three scored runs, the latest Oct 8 2026; playground and `SENTINEL_DETECTOR=yolo`) | fine-tuned EfficientNet-B0 / ConvNeXt-T / MobileNetV3-L (`train_v2.py`, from Patti's MobileNet script); trained Oct 8 2026, none beats v1 on OFM from a second camera | `models/detector/yolo/<run>/`, `models/classifier/cnn/<arch>/<arch>.pt` (server `SENTINEL_CLASSIFIER=cnn-v2`) |
