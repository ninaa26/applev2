"""Check every liner photo before anyone labels it, and decide which go on the labelling site.

    python check_liner_photos.py                      # every set in label_sets.py -> data/review/labelling_site/
    python check_liner_photos.py --sets cornell       # one set again (the others' rows are kept)
    python check_liner_photos.py --write-held-out     # also extend the held-out list (see below)

For each photo of each set it measures: size, camera EXIF, JPEG quality, px/mm from the printed grid (on a
lattice of patches, see grid_ppm), sharpness at a fixed px/mm, glare and brightness on the card (the server's
photo_quality), and which photos of the set show the same card (ORB features + a homography; the same shot
twice if their thumbnails match too). photo_checks.decide() turns that into keep / flag / exclude with reasons;
why each check matters is in photo_checks.py. photo_checks.csv records every number and decision (by =
check_liner_photos.py), and photo_checks_<set>.jpg is a contact sheet per set. prelabel_liners.py puts
every photo not marked exclude on the labelling site. Nothing is deleted. Tags people set on the site (exported to
photo_tags.csv) overrule the automatic decision: "unusable" or "not a gridded liner" excludes the photo, with
their name in `by`; "wrong scale" flags it.

Held-out cards (only sets with a held-out list: our Cornell cards): every shot of a card goes the same way. A
card any of whose shots is held out has all of its shots held out (always reported; added with
--write-held-out). New cards, ones no earlier labels.csv row has used (so no model trained on them), are held
out by a fixed hash of the card (photo_checks.pick_held_out, about a third). Cards already trained on are never
moved into the list: that would test the model on photos it learnt from.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

import cv2
import numpy as np
import paths
from crop_field_cards import PATCH_SIDES, photo_px_per_mm, pick_px_per_mm
from label_sets import BY_NAME, SEP, SETS, LabelSet, earlier_boxes, photos, site_name
from photo_checks import card_groups, decide, jpeg_quality, pick_held_out
from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from sentinel_server.pipeline.detect import card_outline, find_grid, photo_quality  # noqa: E402

FIELDS = ["photo", "set", "file", "source", "card", "decision", "why", "by", "megapixels", "camera_exif", "jpeg_q",
          "px_per_mm", "scale_spread", "sharpness", "glare", "brightness", "duplicate_of", "held_out"]
SHARP_PPM = 2.0  # sharpness is measured with the photo resized to this px/mm, so phones, distances and web exports
#                  compare (at 4 px/mm the 2.4 px/mm web exports were measured unresized and outscored every full-size photo)


def plausible_pitch(pitch: float, side: float, whole: bool = False) -> bool:
    """A grid reading is believed only if two squares fit in what was looked at (one square or less is a fold or
    every 2nd-10th line), and a square is at least a tenth of a patch (finer is glue texture or JPEG blocks) or,
    on the whole photo, a 25th of it (a whole card in a 640 px web export has ~60 px squares)."""
    return (0.04 if whole else 0.1) * side <= pitch <= 0.5 * side


def has_green_grid(bgr: np.ndarray) -> bool:
    """Whether the grid is printed in green (the Trécé cards): enough clearly green pixels to be lines."""
    small = cv2.resize(bgr, (400, 400), interpolation=cv2.INTER_AREA).astype(np.int16)
    return float((small[..., 1] - np.maximum(small[..., 0], small[..., 2]) > 25).mean()) > 0.003


def green_ink(bgr: np.ndarray) -> np.ndarray:
    """Single channel where the Trécé cards' green grid ink is dark and everything else (white card, grey glue
    streaks, brown insects) is white. Glue texture read as grid lines is what threw the plain reading off."""
    b, g, r = (bgr[..., i].astype(np.float32) for i in range(3))
    return np.clip(255 - 6 * np.clip(g - np.maximum(r, b), 0, None), 0, 255).astype(np.uint8)


def grid_ppm(bgr: np.ndarray, grid_mm: float, ink: str = "auto") -> tuple[float | None, float | None]:
    """(px/mm of the photo, largest/smallest px/mm across it) from the printed grid.

    As crop_field_cards.py reads it: the grid finder on patches of several sizes, here around a 3 x 3 lattice of
    points, and the value most patches agree on, on the green ink only (ink="green"). A close-up shows only 2-3
    squares, too few for any patch, so then the plain whole-photo reading is used. Checked on the 11 Oct 2026
    cards against the px/mm crop_field_cards.py had measured around each insect: all 10 with a grid agree
    within 8% (9 within 3%). Without
    the green channel and the one-vote whole photo it was off 0.5-10x on 5 of them, and two sharp close-ups came
    out "blurred" because sharpness is measured at a fixed px/mm."""
    h, w = bgr.shape[:2]
    if ink == "auto":
        ink = "green" if has_green_grid(bgr) else "any"
    v = green_ink(bgr) if ink == "green" else bgr
    per_point = []
    for fy in (0.2, 0.5, 0.8):
        for fx in (0.2, 0.5, 0.8):
            cx, cy, est = w * fx, h * fy, []
            for side in PATCH_SIDES:
                if side == 0 or side > 1.5 * max(h, w):
                    continue
                patch = v[max(0, int(cy - side / 2)):int(cy + side / 2), max(0, int(cx - side / 2)):int(cx + side / 2)]
                g = find_grid(patch)
                if g.score >= 20 and plausible_pitch(g.pitch_px, max(patch.shape[:2])):
                    est.append(g.pitch_px / grid_mm)
            per_point.append(est)
    # A patch's reading counts only if another point of the lattice agrees (within 12%): a real grid repeats
    # across the card, while a thick line's two edges or a streak of glue fools one patch at a time.
    per_point = [[x for x in est if any(abs(np.log(x / y)) < 0.12 for j, other in enumerate(per_point) if j != i
                                        for y in other)] for i, est in enumerate(per_point)]
    votes = [x for est in per_point for x in est]
    for img in ([v, bgr] if ink == "green" else [v]):  # the whole photo: one vote, plain colours as the fallback
        g = find_grid(img)
        if g.score > 0 and plausible_pitch(g.pitch_px, max(h, w), whole=True):
            votes.append(g.pitch_px / grid_mm)
            break
    whole = photo_px_per_mm(votes)
    if whole is None:
        return None, None
    near = [pick_px_per_mm([(x, 0.0) for x in est], whole) for est in per_point if est]
    near = [x for x in near if x and abs(np.log(x / whole)) < np.log(1.35)]
    return whole, (max(near) / min(near) if len(near) >= 3 else None)


def sharpness(bgr: np.ndarray, ppm: float | None, outline) -> float:
    """photo_quality's Laplacian variance, on the photo resized to SHARP_PPM px/mm (or 1000 px without a grid)."""
    f = SHARP_PPM / ppm if ppm else 1000 / max(bgr.shape[:2])
    f = min(1.0, f)
    small = cv2.resize(bgr, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    return photo_quality(small, None if outline is None else outline * f, max_side=10**6)["sharpness"]


def orb_features(bgr: np.ndarray):
    h, w = bgr.shape[:2]
    f = min(1.0, 1000 / max(h, w))
    grey = cv2.cvtColor(cv2.resize(bgr, None, fx=f, fy=f, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    kp, des = cv2.ORB_create(3000).detectAndCompute(grey, None)
    thumb = cv2.resize(grey, (256, 256), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    return kp, des, (thumb - thumb.mean()) / (thumb.std() + 1e-6)


def same_card(a, b, min_inliers: int = 60) -> tuple[bool, bool]:
    """(the same card, the same shot). A printed grid alone matches anywhere, so the homography has to agree
    on many points; the insects and stains are what make two cards different."""
    (ka, da, ta), (kb, db, tb) = a, b
    if da is None or db is None or len(ka) < 50 or len(kb) < 50:
        return False, False
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db, k=2)
    good = [m for m, *n in pairs if n and m.distance < 0.75 * n[0].distance]
    if len(good) < min_inliers:
        return False, False
    src = np.float32([ka[m.queryIdx].pt for m in good])
    dst = np.float32([kb[m.trainIdx].pt for m in good])
    H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if H is None or int(inl.sum()) < min_inliers:
        return False, False
    # The same image saved twice (a re-upload, a re-encode) correlates >= 0.99 at 256 px. Different days of one liner
    # (0.92-0.98 on the OFM liners) and other shots of one card (0.81-0.88 on cm-ervins) are the same card, not the same shot.
    return True, float(np.mean(ta * tb)) >= 0.99


def measure(path: Path, grid_mm: float, ink: str) -> tuple[dict, object, Image.Image]:
    with Image.open(path) as im:
        exif = im.getexif()
        camera = bool(exif.get(0x010F) or exif.get(0x0110))  # Make or Model
        q = jpeg_quality(getattr(im, "quantization", None))
        img = ImageOps.exif_transpose(im).convert("RGB")
    bgr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    ppm, spread = grid_ppm(bgr, grid_mm, ink)
    outline = card_outline(bgr)
    pq = photo_quality(bgr, outline)
    m = {"megapixels": img.width * img.height / 1e6, "camera_exif": camera, "jpeg_q": q,
         "px_per_mm": ppm, "scale_spread": spread, "sharpness": sharpness(bgr, ppm, outline),
         "glare": pq["glare"], "brightness": pq["brightness"], "duplicate_of": ""}
    thumb = img.copy()
    thumb.thumbnail((300, 300))
    return m, orb_features(bgr), thumb


def contact_sheet(rows: list[dict], thumbs: dict, dest: Path) -> None:
    colour = {"keep": (22, 163, 74), "flag": (234, 179, 8), "exclude": (220, 38, 38)}
    cell, cols = (300, 380), 6
    n = len(rows)
    sheet = Image.new("RGB", (cell[0] * min(cols, n), cell[1] * ((n + cols - 1) // cols)), "white")
    d = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for i, r in enumerate(rows):
        x, y = cell[0] * (i % cols), cell[1] * (i // cols)
        sheet.paste(thumbs[r["photo"]], (x, y))
        d.rectangle((x, y + 300, x + cell[0] - 1, y + cell[1] - 1), fill=colour[r["decision"]])
        text = f"{r['file'][:44]}\n{r['decision']} | {r['px_per_mm'] or '-'} px/mm\n" + "\n".join(
            w[:48] for w in r["why"].split("; ")[:3])
        d.multiline_text((x + 4, y + 304), text, fill="white" if r["decision"] != "flag" else "black", font=font)
    sheet.save(dest, quality=75)


def person_tags(site: Path) -> dict[str, list[tuple[str, str]]]:
    """Photo -> [(tag, who)] from the site (python -m label_site export writes photo_tags.csv)."""
    out: dict[str, list[tuple[str, str]]] = {}
    if (site / "photo_tags.csv").exists():
        with open(site / "photo_tags.csv", newline="") as f:
            for r in csv.DictReader(f):
                out.setdefault(r["photo"], []).append((r["tag"], r["user"]))
    return out


def check_set(data: Path, s: LabelSet, grid_mm: float, ink: str, sheet: Path,
              tags: dict | None = None) -> tuple[list[dict], list[str]]:
    """Rows for photo_checks.csv, and photos of held-out cards missing from the set's held-out list."""
    files = photos(data, s)
    if not files:
        print(f"{s.name}: no photos in {data / s.folder}")
        return [], []
    ms, feats, thumbs = {}, {}, {}
    for p in files:
        name = site_name(s, p.name)
        try:
            m, f, t = measure(p, grid_mm, ink)
        except (OSError, cv2.error) as e:
            m = {"megapixels": 0, "sharpness": 0, "glare": 0, "brightness": 0, "unreadable": str(e)}
            f, t = None, Image.new("RGB", (300, 300), "grey")
        ms[name], feats[name], thumbs[name] = {**m, "path": p}, f, t

    # Same card / same shot, within the set. The shot kept is the bigger file (the original rather than a copy).
    names, links = list(ms), []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if feats[a] is None or feats[b] is None:
                continue
            card, shot = same_card(feats[a], feats[b])
            if card:
                links.append((a, b))
            if shot:
                worse = min((a, b), key=lambda n: ms[n]["path"].stat().st_size)
                ms[worse]["duplicate_of"] = (a if worse == b else b).split(SEP, 1)[1]
    cards = card_groups(names, links)

    held_cards, add, entries = set(), [], []
    if s.held_out:
        entries = paths.held_out_list(data, s.held_out)
        trained = set(earlier_boxes(data, s))  # photos an earlier labels.csv used: a model may have trained on them
        held_cards = {cards[n] for n in names if paths.is_listed(ms[n]["path"].name, entries)}
        new_cards = {cards[n] for n in names} - {cards[n] for n in names if ms[n]["path"].name in trained}
        held_cards |= {c for c in new_cards if pick_held_out(c)}

    batch = float(np.median([m["sharpness"] for m in ms.values() if m["sharpness"] > 0] or [0])) or None
    rows = []
    for n, m in ms.items():
        if "unreadable" in m:
            decision, why = "exclude", [f"unreadable: {m['unreadable']}"]
        else:
            decision, why = decide(m, batch, originals=s.originals)
        by = "check_liner_photos.py"
        for tag, who in (tags or {}).get(n, []):  # a person who looked overrules the automatic check
            if tag in ("unusable", "not_gridded"):
                decision, by = "exclude", who
                why = [f"{who} tagged it {tag.replace('_', ' ')} on the site"] + why
            elif tag == "wrong_scale":
                decision = "flag" if decision == "keep" else decision
                why = [f"{who} says the scale looks wrong"] + why
        held = cards[n] in held_cards
        if held and not paths.is_listed(m["path"].name, entries):
            add.append(m["path"].name)
        rows.append({"photo": n, "set": s.name, "file": m["path"].name, "source": str(m["path"].relative_to(data)),
                     "card": cards[n].split(SEP, 1)[1], "decision": decision, "why": "; ".join(why),
                     "by": by, "held_out": "yes" if held else "",
                     "megapixels": f"{m['megapixels']:.1f}", "camera_exif": "yes" if m.get("camera_exif") else "",
                     "jpeg_q": m.get("jpeg_q") or "", "duplicate_of": m.get("duplicate_of", ""),
                     "px_per_mm": f"{m['px_per_mm']:.2f}" if m.get("px_per_mm") else "",
                     "scale_spread": f"{m['scale_spread']:.2f}" if m.get("scale_spread") else "",
                     "sharpness": f"{m['sharpness']:.1f}", "glare": m["glare"], "brightness": m["brightness"]})
    contact_sheet(rows, thumbs, sheet)
    counts = {d: sum(r["decision"] == d for r in rows) for d in ("keep", "flag", "exclude")}
    print(f"{s.name}: {len(rows)} photos on {len(set(cards.values()))} cards: {counts['keep']} keep, "
          f"{counts['flag']} flagged (kept), {counts['exclude']} excluded")
    for r in rows:
        if r["decision"] == "exclude":
            print(f"  exclude {r['file']}: {r['why']}")
    return rows, add


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=paths.DATA)
    ap.add_argument("--sets", nargs="*", default=[s.name for s in SETS], choices=[s.name for s in SETS])
    ap.add_argument("--grid-mm", type=float, default=25.0, help="the liners' printed grid spacing")
    ap.add_argument("--ink", choices=["auto", "green", "any"], default="auto",
                    help="the grid's ink: auto picks green where the grid is green (the Trécé cards)")
    ap.add_argument("--write-held-out", action="store_true", help="add held-out cards' other shots to the list")
    args = ap.parse_args(argv)
    site = args.data / paths.LABEL_SITE
    site.mkdir(parents=True, exist_ok=True)
    out = site / "photo_checks.csv"
    old = []
    if out.exists():  # keep other sets' rows when only some sets are re-checked
        with open(out, newline="") as f:
            old = [r for r in csv.DictReader(f) if r["set"] not in args.sets]
    rows = list(old)
    for name in args.sets:
        s = BY_NAME[name]
        got, add = check_set(args.data, s, args.grid_mm, args.ink, site / f"photo_checks_{s.name}.jpg", person_tags(site))
        rows += got
        if add:
            print(f"  {len(add)} photos of held-out cards aren't in {s.held_out}: {', '.join(add)}")
            if args.write_held_out:
                with open(args.data / paths.HELD_OUT / s.held_out, "a") as f:
                    f.write(f"# added {date.today()} by check_liner_photos.py (a held-out card's other shot, or a new card)\n")
                    f.writelines(n + "\n" for n in add)
                print("  added; note it in ml/README.md")
            else:
                print("  run again with --write-held-out to add them")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} photos -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
