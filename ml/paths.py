"""Where every dataset and model lives, relative to ml/. The layout is described in data/README.md.

Scripts take a --data root (default data/) and find each set under it with these names, so a test can build the
same layout in a temporary folder. Renaming a folder is a change here plus reorganize_data.py, not in every script.
"""

from __future__ import annotations

from pathlib import Path

DATA = Path("data")
MODELS = Path("models")

# Moths photographed in nature (web), for learning species.
INAT = "web_moth_photos/inaturalist"  # <label>/<photo>.jpg + manifest.csv (fetch_inat.py)
AMI = "web_moth_photos/ami_gbif"  # <label>/<photo>.jpg + manifest.csv (fetch_ami.py)
CUTOUTS = "web_moth_photos/cutouts"  # flatbug cutout of each web insect (segment_moths.py)

# Real insects stuck on real sticky liners.
WEB_LINERS = "real_liners/from_the_web"  # other people's liner photos; see its README.md
FIELD = "real_liners/cornell_field_cards"  # phone photos of used cards from the Cornell orchard
OWN = "real_liners/our_trap"  # <label>/<card>/*.jpg, reviewed on the dashboard (export_server_crops.py)
BENCH = "real_liners/our_trap_bench_tests"  # bench captures from the trap camera

# Fakes: web insects pasted onto blank liner photos (make_trap_style.py). One folder per version, each with
# blank_liners/ (the backgrounds it used), photos/<label>/, manifest.csv and preview/.
TRAP_STYLE = "trap_style"
TRAP_STYLE_VERSION = "v1_webcam_2026-09"  # the version build_dataset.py and train_yolo.py use by default

# What training reads and writes.
CLASSIFIER = "training/classifier"
DATASET = f"{CLASSIFIER}/dataset.csv"  # build_dataset.py
EXCLUDE = f"{CLASSIFIER}/exclude.csv"  # photos a person decided to leave out (path, why)
DROPPED = f"{CLASSIFIER}/dropped.csv"  # every photo build_dataset.py left out, and why
EMBEDDINGS = f"{CLASSIFIER}/bioclip_embeddings"
DETECTOR = "training/detector"  # yolo_real/, yolo_blank/, yolo_synth/ (train_yolo.py)
HELD_OUT = "training/held_out"  # lists of photos no model trains on; in git, see its README.md
SUSPECTS = "review/cleaning_suspects"  # clean_dataset.py: web photos for a person to look at

# Held-out lists, in HELD_OUT. One name or name prefix per line; # starts a comment.
FIELD_TEST = "field_cards.txt"  # field-card photos kept out of both the detector and the classifier
FIELD_TEST_CLASSIFIER = "field_cards_classifier_only.txt"  # also kept out of the classifier (it can train YOLO)
WEB_LINER_TEST_CLASSIFIER = "web_liners_classifier.txt"  # web liners and cards the classifier never sees
WEB_LINER_TEST_DETECTOR = "web_liners_detector.txt"  # fully labelled web liners YOLO is scored on
OWN_LOCKED = "our_trap_locked.txt"  # our trap's cards for the report's final score (exact card folder names)

# Models (gitignored like data/). Classifiers name an insect crop, detectors find the insects on a photo.
BIOCLIP_HEAD = "models/classifier/bioclip_head"  # BioCLIP 2 + linear head (train_v1.py)
CLASSIFIER_HEAD = f"{BIOCLIP_HEAD}/current/head.npz"  # the one to deploy; older heads are in archive/
CNN = "models/classifier/cnn"  # fine-tuned CNNs, one folder per architecture (train_v2.py)
YOLO_RUNS = "models/detector/yolo"  # one run per folder (train_yolo.py)
PRETRAINED = "models/detector/pretrained"  # downloaded starting weights (BioCLIP 2 and the ImageNet CNNs
#                                            stay in the Hugging Face and torch caches in your home folder)
FLATBUG = f"{PRETRAINED}/flat_bug_M.pt"
YOLO_START = f"{PRETRAINED}/yolo11s.pt"


def trap_style(data: Path, version: str = TRAP_STYLE_VERSION) -> Path:
    return data / TRAP_STYLE / version


def held_out_list(data: Path, name: str) -> list[str]:
    """The entries of one held-out list (empty if the file isn't there)."""
    path = data / HELD_OUT / name
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def is_listed(name: str, entries: list[str]) -> bool:
    """A full name matches itself, a prefix matches every photo it starts (a liner's other days go with it)."""
    return any(name.startswith(e) for e in entries)
