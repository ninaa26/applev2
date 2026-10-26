# Held-out photos: never trained on

These lists are in git so that which photos are test photos is recorded and reviewed like code. One photo name
or name prefix per line (a prefix takes every photo it starts, so a liner's other days go with it); `#` starts a
comment. The scripts read them through `paths.held_out_list` in [`ml/paths.py`](../../../paths.py).

| File | Kept out of | Read by |
|---|---|---|
| `field_cards.txt` | both models | `train_yolo.py` (test split), `liner_crops.py`, `make_trap_style.py --field` |
| `field_cards_classifier_only.txt` | the species classifier (still trains the detector) | `liner_crops.py`, `make_trap_style.py --field` |
| `web_liners_classifier.txt` | the species classifier | `liner_crops.py` (crops marked `test`) |
| `web_liners_detector.txt` | the detector | `train_yolo.py` (default `--test-photos`) |
| `our_trap_locked.txt` | everything until `--final` | `build_dataset.py` (split `locked`) |

Not listed here: `liner_crops.py` holds out a fixed quarter of the PTM liner photos by a hash of the photo's name
(86 photos, too many to list), and `build_dataset.py` splits web photos by a hash of their observation.

Changing a list changes what the next model is tested on, so earlier scores stop being comparable: note it in
ml/README.md with the date. Never move a photo from here into training to raise a score.
