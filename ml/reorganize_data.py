"""Move ml/data/ and ml/models/ from the old flat layout (Oct 2026) to the one in data/README.md.

    python reorganize_data.py            # dry run: every move and every file whose paths would change
    python reorganize_data.py --write    # do it (stop the labeller and any training first)
    python reorganize_data.py --undo     # put everything back, from the log the --write run left in data/old/

Run it once on each copy of the data (the Mac, a CUDA machine's bundle is rebuilt with make_bundle.py instead),
right after pulling the code that expects the new layout. It only renames folders on the same disk, so it takes
seconds, and then rewrites the paths stored in the data itself, so nothing has to be re-made:
  - dataset.csv, every manifest.csv, labels.csv, suspects.csv and the other csv/json/yaml/txt files, both the
    relative form (data/inat/CM/1.jpg) and the absolute one (/Users/.../ml/data/inat/CM/1.jpg);
  - the photo paths in the BioCLIP embedding cache (41k photos: without this, retraining embeds them all again);
  - symlinks that point at absolute paths inside data/.
Before changing a file it copies it to data/old/reorganize-<time>/, and the moves and copies are logged there
for --undo. The held-out lists that used to sit in the data (field/test_cards.txt) now live in git
(data/training/held_out/); the old file is moved there only if git doesn't already have the same names.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE  # --data's parent
V1 = "trap_style/v1_webcam_2026-09"
ARCHIVE = "classifier/bioclip_head/archive"

# Old path (relative to data/ or models/) -> new path. Longer, more specific entries first: they are tried in order.
DATA_MOVES = [
    ("field/test_cards.txt", "training/held_out/field_cards.txt"),
    ("own/locked_test.txt", "training/held_out/our_trap_locked.txt"),
    ("ami", "web_moth_photos/ami_gbif"),
    ("inat", "web_moth_photos/inaturalist"),
    ("cutouts", "web_moth_photos/cutouts"),
    ("web_liners", "real_liners/from_the_web"),
    ("field", "real_liners/cornell_field_cards"),
    ("own", "real_liners/our_trap"),
    ("trap_camera", "real_liners/our_trap_bench_tests"),
    ("liners", f"{V1}/blank_liners"),
    ("synth/manifest.csv", f"{V1}/manifest.csv"),
    ("synth/preview.jpg", f"{V1}/preview.jpg"),
    ("synth/preview", f"{V1}/preview"),
    ("synth", f"{V1}/photos"),  # what is left in synth/: one folder per label
    ("dataset.csv", "training/classifier/dataset.csv"),
    ("exclude.csv", "training/classifier/exclude.csv"),
    ("embeddings", "training/classifier/bioclip_embeddings"),
    ("yolo-blank", "training/detector/yolo_blank"),
    ("yolo-synth", "training/detector/yolo_synth"),
    ("yolo", "training/detector/yolo_real"),
    ("clean", "review/cleaning_suspects"),
    ("dataset.backup.csv", "old/dataset.backup.csv"),
    ("run_all.log", "logs/run_all.log"),
    ("run_all.sh", "logs/run_all.sh"),
    ("run_train.sh", "logs/run_train.sh"),
    ("v1.log", "logs/v1.log"),
    ("v1.sep25.log", "logs/v1.sep25.log"),
]
MODEL_MOVES = [
    ("v1-2026-10-01", f"{ARCHIVE}/2026-10-01_web_and_trap_style"),
    ("v1-no-liner", f"{ARCHIVE}/2026-10-07_no_real_liners"),
    ("v1-2026-10-07a", f"{ARCHIVE}/2026-10-07a_no_nontarget_moths"),
    ("v1-2026-10-07b", f"{ARCHIVE}/2026-10-07b_before_field_cards"),
    ("v1-ami-only", f"{ARCHIVE}/2026-09-24_ami_photos_only"),
    ("v1-web-only", f"{ARCHIVE}/2026-09-24_web_photos_only"),
    ("v1-cuda", f"{ARCHIVE}/2026-10-08_cuda_retrain"),
    ("v1", "classifier/bioclip_head/current"),
    ("v2-convnext", "classifier/cnn/convnext_tiny"),
    ("v2-mobilenet", "classifier/cnn/mobilenet_v3_large"),
    ("v2", "classifier/cnn/efficientnet_b0"),
    ("yolo11", "detector/yolo"),
]
LOOSE_WEIGHTS = ["flat_bug_M.pt", "yolo11s.pt"]  # in ml/, -> models/detector/pretrained/
EMPTY_TO_DELETE = ["segments"]
TEXT = {".csv", ".json", ".yaml", ".yml", ".txt", ".md"}
SKIP_TEXT = {"logs", "old"}  # logs keep the paths they were written with


def _pattern(moves: list[tuple[str, str]], root: str) -> re.Pattern:
    keys = "|".join(re.escape(old) for old, _ in moves)
    # "data/inat/..." or ".../ml/data/inat/...", but not "server/data/..." or "web_liners/field".
    return re.compile(rf"(?<![\w.-])(?P<pre>(?:[^\s\"',;()\[\]`<>]*/)?){root}/(?P<key>{keys})(?![\w-]|\.\w)")


DATA_RE = _pattern(DATA_MOVES, "data")
MODELS_RE = _pattern(MODEL_MOVES, "models")


def _sub(pattern: re.Pattern, moves: dict[str, str], root: str, text: str) -> str:
    def repl(m: re.Match) -> str:
        pre = m["pre"]
        if "://" in pre or (pre and not (pre.endswith("ml/") or pre in ("./", "../"))):
            return m[0]  # another project's data/ (server/data/, device/data/) or a bundle's
        return f"{pre}{root}/{moves[m['key']]}"
    return pattern.sub(repl, text)


def rewrite(text: str) -> str:
    """Every old data/ and models/ path in `text`, in its new place. Also used on the docs, once."""
    text = _sub(DATA_RE, dict(DATA_MOVES), "data", text)
    text = _sub(MODELS_RE, dict(MODEL_MOVES), "models", text)
    for w in LOOSE_WEIGHTS:  # "ml/flat_bug_M.pt" -> "ml/models/detector/pretrained/flat_bug_M.pt"
        text = re.sub(rf"(?<=ml/){re.escape(w)}", f"models/detector/pretrained/{w}", text)
    return text


def plan(data: Path, models: Path) -> list[tuple[Path, Path]]:
    moves = []
    for root, table in ((data, DATA_MOVES), (models, MODEL_MOVES)):
        for old, new in table:
            src, dst = root / old, root / new
            if src.exists() or src.is_symlink():
                moves.append((src, dst))
    for w in LOOSE_WEIGHTS:
        if (HERE / w).exists():
            moves.append((HERE / w, models / "detector" / "pretrained" / w))
    return moves


def rel(p: Path) -> str:
    """`p` as shown and as kept in the backup: relative to ml/ (or to --data's parent, in a test)."""
    return os.path.relpath(p, HERE) if HERE in p.parents else os.path.relpath(p, ROOT)


def text_files(*roots: Path):
    for root in roots:
        for dirpath, dirnames, files in os.walk(root):
            dirnames[:] = [d for d in dirnames if not (Path(dirpath) == root and d in SKIP_TEXT)]
            for f in files:
                p = Path(dirpath) / f
                if p.suffix.lower() in TEXT and not p.is_symlink():
                    yield p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=HERE / "data")
    ap.add_argument("--models", type=Path, default=HERE / "models")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--undo", action="store_true")
    args = ap.parse_args(argv)
    data, models = args.data.resolve(), args.models.resolve()
    global ROOT
    ROOT = data.parent
    if args.undo:
        return undo(data, models)

    moves = plan(data, models)
    held = data / "training/held_out/field_cards.txt"
    old_cards = data / "field/test_cards.txt"
    if old_cards.exists() and held.exists():
        names = lambda p: sorted(ln.strip() for ln in p.read_text().splitlines()  # noqa: E731
                                 if ln.strip() and not ln.lstrip().startswith("#"))
        if names(old_cards) != names(held):
            raise SystemExit(f"{old_cards} and {held} (in git) list different cards; make them agree first")
        moves = [(s, d) for s, d in moves if s != old_cards]  # git's copy wins; the old one goes to the backup
    taken = [(s, d) for s, d in moves if d.exists()]
    if taken:
        raise SystemExit("already there, so not moving: " + ", ".join(str(d) for _, d in taken))
    print(f"{len(moves)} moves:")
    for s, d in moves:
        print(f"  {rel(s)}  ->  {rel(d)}")
    if not args.write:
        changed = sum(1 for p in text_files(data, models) if rewrite(p.read_text(errors="ignore")) != p.read_text(errors="ignore"))
        print(f"\nThen the paths stored in {changed} csv/json/yaml/txt files, the embedding cache and the symlinks"
              " are rewritten. Dry run: nothing changed. Run again with --write.")
        return 0

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = data / "old" / f"reorganize-{stamp}"
    backup.mkdir(parents=True)
    log: dict = {"moves": [], "rewritten": [], "relinked": [], "deleted": []}

    def save_log():
        (backup / "log.json").write_text(json.dumps(log, indent=1))

    if old_cards.exists():  # the copy git now has; kept with the backup for --undo
        shutil.move(old_cards, backup / "field_test_cards.txt")
        log["moves"].append([str(old_cards), str(backup / "field_test_cards.txt")])
    for s, d in moves:
        d.parent.mkdir(parents=True, exist_ok=True)
        os.rename(s, d)
        log["moves"].append([str(s), str(d)])
        save_log()
    for name in ("synth", "own", "field"):  # left empty once their contents moved
        if (data / name).is_dir() and not any((data / name).iterdir()):
            (data / name).rmdir()
            log["deleted"].append(str(data / name))
    for name in EMPTY_TO_DELETE:
        p = data / name
        if p.is_dir() and not any(p.rglob("*")):
            p.rmdir()
            log["deleted"].append(str(p))

    for p in text_files(data, models):
        if backup in p.parents:
            continue
        old = p.read_text(errors="surrogateescape")
        new = rewrite(old)
        if new != old:
            keep = backup / "files" / rel(p)
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, keep)
            p.write_text(new, errors="surrogateescape")
            log["rewritten"].append(str(p))
    for cache in (data / "training/classifier/bioclip_embeddings").glob("*.npz"):
        z = np.load(cache, allow_pickle=False)
        old_paths = z["paths"].tolist()
        new_paths = [rewrite(p) for p in old_paths]
        if new_paths != old_paths:
            keep = backup / "files" / rel(cache)
            keep.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cache, keep)
            order = np.argsort(new_paths)  # train_v1.py keeps the cache sorted by path
            np.savez(cache, paths=np.array(new_paths)[order], feats=z["feats"][order])
            log["rewritten"].append(str(cache))
    for dirpath, _, files in os.walk(data):
        for f in files:
            p = Path(dirpath) / f
            if p.is_symlink():
                target = os.readlink(p)
                new = rewrite(target)
                if new != target:
                    p.unlink()
                    p.symlink_to(new)
                    log["relinked"].append([str(p), target])
    save_log()
    broken = [str(p) for p in data.rglob("*") if p.is_symlink() and not p.exists()]
    print(f"\nMoved {len(moves)}, rewrote paths in {len(log['rewritten'])} files, relinked {len(log['relinked'])} "
          f"symlinks. Backup and log: {rel(backup)}")
    if broken:
        print(f"{len(broken)} symlinks point nowhere, e.g. {broken[0]}", file=sys.stderr)
        return 1
    return 0


def undo(data: Path, models: Path) -> int:
    logs = sorted((data / "old").glob("reorganize-*/log.json"))
    if not logs:
        raise SystemExit("no reorganize log in data/old/")
    backup = logs[-1].parent
    log = json.loads(logs[-1].read_text())
    # Files were rewritten and links relinked after the moves, at their new paths: restore those first.
    for p in log["rewritten"]:
        shutil.copy2(backup / "files" / rel(Path(p)), p)
    for p, target in log["relinked"]:
        Path(p).unlink()
        Path(p).symlink_to(target)
    for p in log["deleted"]:
        Path(p).mkdir(parents=True, exist_ok=True)
    for s, d in reversed(log["moves"]):
        Path(s).parent.mkdir(parents=True, exist_ok=True)
        os.rename(d, s)
    for _, d in log["moves"]:  # the new folders the moves made, now empty
        for parent in Path(d).parents:
            if parent in (data, models, data.parent) or not parent.is_dir() or any(parent.iterdir()):
                break
            parent.rmdir()
    print(f"Undid {backup.name}: {len(log['moves'])} moves, {len(log['rewritten'])} files. The backup folder stays.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
