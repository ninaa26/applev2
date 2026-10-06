---
paths:
  - "ml/**"
---

# ML scripts, datasets and labelling

[ml/README.md](../../ml/README.md) is the full reference; these are the rules that are easy to break.

## Running

- Run scripts from inside `ml/` with `.venv/bin/python`; paths like `data/` and `models/` are relative to it.
- `train_v1.py` on the 16 GB M3: batch 16 and `--device cpu` (larger batches hang MPS). `train_v1.py --final` is run once, at the end, for the report's numbers.
- Tests are `unittest` and need numpy + pillow only: `.venv/bin/python -m unittest discover tests`. Keep new tests free of torch so CI stays light.

## Data

- Everything under `data/` and `models/` is gitignored. When a script changes what it writes there, update `ml/README.md` in the same change.
- Sources stay apart: `data/ami`, `data/inat` (web photos), `data/synth` (trap-style composites), `data/field` (phone photos of used field cards), `data/web_liners` (other people's liner photos), `data/own` (our trap, reviewed on the dashboard), `data/trap_camera` (bench captures).
- `data/own/<label>/<card>/*.jpg`, one folder per card. Field-card crops do not go in `data/own/`: real moths on glue, but not our liner or camera.
- Held-out sets are listed in files, not chosen at random each run: `data/own/locked_test.txt`, `data/field/test_cards.txt`. Never train on them.
- A split keeps every photo of one liner or card on the same side. Synthetic copies keep their source photo's split.
- Blank-liner backgrounds for `make_trap_style.py` go in `data/liners/` and must come from the trap camera.

## Labels

- Classes: `CM`, `OFM`, `OBLR`, `other_moth`, `other_insect`, `debris`.
- Leg clumps, wing bits and leaf fragments on a card are `debris`, not deleted: the trap sees them too. Delete only what is not on the card.
- Labelling is two passes: pass 1 (anyone) moth / other insect / debris and box fixes; pass 2 (a trained eye) the species of each moth.
- Trap-camera sets photograph one liner on several days. Label the latest photo of each liner, stop the labeller, then run `carry_liner_labels.py --write` to copy labels to the earlier photos.
- `labels.csv` also records how flatbug did (`skip`, `flatbug-edited`, `manual`); keep those values intact when editing it by script.

## Reporting results

- Every number in the README carries its date, the model, the data it was measured on and the resolution (native or trap px/mm).
- Web-photo test scores are a pipeline check, never trap accuracy: BioCLIP 2 has likely seen those photos.
- In the public liner sets only the target moth was boxed, so detector precision there is a lower bound.
- Accuracy for the report comes from our own trap's photos on locked cards, through `sentinel-server evaluate` ([docs/evaluation.md](../../docs/evaluation.md)).
