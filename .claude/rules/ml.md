---
paths:
  - "ml/**"
---

# ML scripts, datasets and labelling

[ml/README.md](../../ml/README.md) is the full reference; these are the rules that are easy to break.

## Running

- Each training script writes `trained_on.json` next to the model (dataset fingerprint, trap-style version, held-out lists, commit). New classifier experiments go to `models/classifier/bioclip_head/archive/<date>_<what changed>/` (or copy `current/` there first), so `current/` stays the deployed head.
- Training on another machine: `make_bundle.py`, then [ml/RUN_ON_CUDA.md](../../ml/RUN_ON_CUDA.md). `data/` and `models/` are not in git.
- Run scripts from inside `ml/` with `.venv/bin/python`; paths like `data/` and `models/` are relative to it.
- `train_v1.py` on the 16 GB M3: batch 16 and `--device cpu` (larger batches hang MPS). `train_v1.py --final` is run once, at the end, for the report's numbers.
- Tests are `unittest` and need numpy + pillow only: `.venv/bin/python -m unittest discover tests`. Keep new tests free of torch so CI stays light.

## Data

- Everything under `data/` and `models/` is gitignored, except `data/README.md` (the map of the folders) and `data/training/held_out/`. Folder names live in `ml/paths.py`; scripts use those constants, not literal paths. When a script changes what it writes there, update `ml/README.md` and `data/README.md` in the same change.
- Sources stay apart: `data/web_moth_photos/ami_gbif`, `data/web_moth_photos/inaturalist` (web photos), `data/trap_style/<version>/` (trap-style composites, one folder per version), `data/real_liners/cornell_field_cards` (phone photos of used field cards), `data/real_liners/from_the_web` (other people's liner photos; its species crops from `liner_crops.py` are source `liner` in `dataset.csv`), `data/real_liners/our_trap` (our trap, reviewed on the dashboard), `data/real_liners/our_trap_bench_tests` (bench captures).
- `data/real_liners/our_trap/<label>/<card>/*.jpg`, one folder per card. Field-card crops do not go in `data/real_liners/our_trap/`: real moths on glue, but not our liner or camera.
- Held-out sets are listed in files in git, not chosen at random each run: `data/training/held_out/*.txt` (its README.md says which model each list is kept out of). Never train on them, and note any change to a list in `ml/README.md` with the date.
- A split keeps every photo of one liner or card on the same side. Synthetic copies keep their source photo's split.
- Trap-style sets are versioned: a new set gets its own `data/trap_style/<version>/` with its `blank_liners/` (from the trap camera), made with `make_trap_style.py --version`; never overwrite an older set a model was trained on. `build_dataset.py --trap-style` picks the set, the default is `TRAP_STYLE_VERSION` in `paths.py`.

## Labels

- Classes: `CM`, `OFM`, `OBLR`, `other_moth`, `other_insect`, `debris`.
- Leg clumps, wing bits and leaf fragments on a card are `debris`, not deleted: the trap sees them too. Delete only what is not on the card.
- Box every insect on a photo, also the tiny, blurred, half-hidden, overlapping and decayed ones. A detector trained on photos where they were left out learns to miss them, and its counts become biased towards big insects.
- Labelling is two passes: pass 1 (anyone) moth / other insect / debris and box fixes; pass 2 the species of each moth. On the team labelling site anyone may do pass 2 (decided Oct 25 2026); `0` (moth, unsure) beats a guess, and each person's species calls are scored on the hidden test photos (dashboard) so you know whose to trust.
- Trap-camera sets photograph one liner on several days. Label the latest photo of each liner, stop the labeller, then run `carry_liner_labels.py --write` to copy labels to the earlier photos.
- Labels Claude adds go where a person can check them and never silently into a labelled file: a list beside it (`labelled_by_claude.csv`, `species.csv` with a `by` column), the contact sheets it looked at, a backup of the file first, and anything it was unsure of marked unsure or left blank, never passed off as sure.
- `labels.csv` also records how flatbug did (`skip`, `flatbug-edited`, `manual`); keep those values intact when editing it by script.

## Reporting results

- Every number in the README carries its date, the model, the data it was measured on and the resolution (native or trap px/mm).
- Web-photo test scores are a pipeline check, never trap accuracy: BioCLIP 2 has likely seen those photos.
- Judge a change to the classifier on real-liner crops (`eval_liner_species.py`, held-out liners), by resolution, not on the web-photo or trap-style test. Report "auto & wrong" next to recall: a confident wrong label is counted with no one looking.
- Regularisation, temperature and confidence thresholds are picked on real-liner val crops, never on web photos (picked there, 19–30% of real OFM were auto-counted as something else, Oct 7 2026).
- The real-liner score is a development check: uploader's species, not our camera, and the same held-out liners get looked at repeatedly. It is not the report's number either.
- After any change of trap, lure, liner, camera, lighting or season, re-score before trusting earlier numbers.
- Tried and dropped, so not to be retried without new data: the list at the end of [docs/ml-research-status.md](../../docs/ml-research-status.md).
- Web photos are removed only through `data/training/classifier/exclude.csv`, after a person has looked at them (`clean_dataset.py` makes the lists). Don't filter training photos with zero-shot prompts: tried Oct 7 2026, its "larvae" were adult moths.
- Recall on a small set is quoted with its interval or its counts ("2 of 4"), never as a bare percentage.
- In the public liner sets only the target moth was boxed, so detector precision there is a lower bound.
- mAP alone is not a result. Give recall by insect size, and for anything meant for the trap, count error against a person's count.
- A newer or bigger detector is not the fix while labels are few: finish the labelling and get the resolution right first.
- Accuracy for the report comes from our own trap's photos on locked cards, through `sentinel-server evaluate` ([docs/evaluation.md](../../docs/evaluation.md)).
