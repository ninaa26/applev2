"""The decisions check_liner_photos.py makes about each field-card photo, kept free of OpenCV so they can be tested.

What a photo can do to the model, and so what is checked (docs/ml-research-status.md, .claude/rules/ml.md):
  - the wrong scale: make_trap_style.py --field shrinks each insect to trap px/mm with the scale read off the
    card's grid, so a photo with no readable grid, or one whose grid reads differently in different corners,
    gives wrongly sized training insects;
  - a copy instead of the original (a chat app's: small, recompressed, EXIF stripped): its fine detail is gone;
  - the whole shot out of focus, blown out or dark: insects can't be told apart. Blurred *insects* on a sharp
    photo stay in: the trap camera is blurrier than a phone, and "box every insect" is the rule;
  - the same card twice: kept, but grouped as one card, so its shots never land on both sides of a split.
Exclusions are made by this script, not a person, and recorded with their reason in photo_checks.csv; whether
they help is checked by scoring with and without them, not assumed.
"""

from __future__ import annotations

import hashlib

import numpy as np

# IJG standard luminance quantisation table (JPEG Annex K), row by row as Pillow's im.quantization gives it.
_STD_LUMA = np.array([
    16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99], dtype=np.float64)

# Thresholds. Set on the 11 Cornell cards of Oct 2026; ratios are against the batch's median, because a
# Laplacian or a glare share means different things on different phones and distances.
MIN_MEGAPIXELS = 3.0  # phones of the last ten years shoot 8-50 MP; chat apps resize to ~1-2 MP
COPY_QUALITY = 80  # JPEG quality below this, with no camera EXIF: likely a recompressed copy
BLUR_EXCLUDE = 0.25  # sharpness under this share of the batch median: the shot itself is out of focus
BLUR_FLAG = 0.5
GLARE_EXCLUDE = 0.35  # share of the card blown out to white
GLARE_FLAG = 0.08
DARK_FLAG = 70  # median grey of the card (0-255)
SCALE_SPREAD_FLAG = 1.35  # grid scale in the photo's corners, largest over smallest: a strong tilt or curl
LOW_PPM = 5.0  # px/mm under which a moth is under ~50 px long
HELD_OUT_SHARE = 1 / 3  # of new cards, picked by a hash of the card's name


def jpeg_quality(quantization: dict | None) -> int | None:
    """The IJG quality (1-100) a JPEG was saved at, estimated from its luminance table; None if not a JPEG."""
    if not quantization or 0 not in quantization:
        return None
    t = np.asarray(quantization[0], dtype=np.float64)
    if t.size != 64:
        return None
    scale = float(np.mean(t / _STD_LUMA)) * 100  # IJG: table = std * scale / 100
    q = 5000 / scale if scale > 100 else (200 - scale) / 2
    return int(round(min(100, max(1, q))))


def decide(m: dict, batch_sharpness: float | None, originals: bool = False) -> tuple[str, list[str]]:
    """("exclude" | "flag" | "keep", reasons) for one photo's measurements. The size and copy checks apply only
    where full-size originals are expected (our own phone photos); web photos are small exports by nature.

    m: megapixels, camera_exif (bool), jpeg_q (int|None), px_per_mm (float|None), scale_spread (float|None),
       sharpness (float), glare (float), brightness (float), duplicate_of (str|"")."""
    out, flags = [], []
    if m.get("duplicate_of"):
        out.append(f"the same image as {m['duplicate_of']} (saved twice)")
    copy_like = (m.get("jpeg_q") or 100) < COPY_QUALITY and not m.get("camera_exif")
    if originals and m["megapixels"] < MIN_MEGAPIXELS:
        (out if copy_like or not m.get("camera_exif") else flags).append(f"small ({m['megapixels']:.1f} MP): likely a copy, not the original")
    elif originals and copy_like:
        flags.append(f"recompressed (JPEG quality ~{m['jpeg_q']}) with no camera EXIF: maybe a copy")
    if not m.get("px_per_mm"):
        out.append("no grid found: no scale, so its insects can't be sized for the trap")
    elif m["px_per_mm"] < LOW_PPM:
        flags.append(f"low resolution ({m['px_per_mm']:.1f} px/mm; the trap camera ~15): small insects are a few px")
    elif (m.get("scale_spread") or 1) > SCALE_SPREAD_FLAG:
        flags.append(f"grid scale differs {m['scale_spread']:.2f}x across the photo: tilted or curled card")
    if batch_sharpness:
        r = m["sharpness"] / batch_sharpness
        if r < BLUR_EXCLUDE:
            out.append(f"whole photo blurred ({r:.2f} of the batch's sharpness)")
        elif r < BLUR_FLAG:
            flags.append(f"softer than most ({r:.2f} of the batch's sharpness)")
    if m["glare"] > GLARE_EXCLUDE:
        out.append(f"{m['glare']:.0%} of the card blown out")
    elif m["glare"] > GLARE_FLAG:
        flags.append(f"glare on {m['glare']:.0%} of the card")
    if m["brightness"] < DARK_FLAG:
        flags.append(f"dark (card median {m['brightness']:.0f}/255)")
    if out:
        return "exclude", out + flags
    return ("flag" if flags else "keep"), flags


def card_groups(names: list[str], same_card: list[tuple[str, str]]) -> dict[str, str]:
    """Photo -> its card's id (the first name, sorted, among the photos linked to it)."""
    parent = {n: n for n in names}

    def root(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for a, b in same_card:
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    groups: dict[str, list[str]] = {}
    for n in names:
        groups.setdefault(root(n), []).append(n)
    return {n: min(members) for members in groups.values() for n in members}


def pick_held_out(card: str, share: float = HELD_OUT_SHARE) -> bool:
    """Whether a new card goes to the held-out list: a fixed hash of its id, so re-runs agree."""
    h = int(hashlib.sha256(card.encode()).hexdigest()[:8], 16)
    return h / 0xFFFFFFFF < share
