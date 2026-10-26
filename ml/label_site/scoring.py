"""Matching two people's boxes on one photo: the hidden-test score and the two-person merge. Standard library only.

A box is a dict with x1, y1, x2, y2, label, and optionally model_label and confirmed (the person pressed Enter or a
label key on it). Deleted boxes (label "skip") are left out before matching. Two boxes match when they overlap by
at least MATCH_IOU (intersection over union), greedily from the best overlap down, each box used once.
"""

from __future__ import annotations

MATCH_IOU = 0.5
MOTHS = {"CM", "OFM", "OBLR", "other_moth", "lookalike_RBLR", "lookalike_LAW", "other_tortricid", "moth"}


def pass1(label: str) -> str:
    return "moth" if label in MOTHS else label


def iou(a: dict, b: dict) -> float:
    ix = max(0.0, min(a["x2"], b["x2"]) - max(a["x1"], b["x1"]))
    iy = max(0.0, min(a["y2"], b["y2"]) - max(a["y1"], b["y1"]))
    inter = ix * iy
    union = (a["x2"] - a["x1"]) * (a["y2"] - a["y1"]) + (b["x2"] - b["x1"]) * (b["y2"] - b["y1"]) - inter
    return inter / union if union > 0 else 0.0


def live(boxes: list[dict]) -> list[dict]:
    return [b for b in boxes if b.get("label") != "skip"]


def match(a: list[dict], b: list[dict], thr: float = MATCH_IOU) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """(matched index pairs, unmatched in a, unmatched in b)."""
    pairs = sorted(((iou(x, y), i, j) for i, x in enumerate(a) for j, y in enumerate(b)), reverse=True)
    used_a, used_b, out = set(), set(), []
    for v, i, j in pairs:
        if v < thr:
            break
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        out.append((i, j))
    return out, [i for i in range(len(a)) if i not in used_a], [j for j in range(len(b)) if j not in used_b]


def gold_score(person: list[dict], gold: list[dict], species: bool = False) -> dict:
    """How one person did on a hidden test photo, against the expert's labels.

    found          share of the expert's insects the person has a box on
    extra          the person's boxes with no expert box under them
    label_right    of the matched boxes, how many carry the expert's label (pass-1 level unless species)
    took_wrong     matched boxes where the person kept the model's label and the model was wrong: the
                   "pressed Enter without looking" number
    """
    p, g = live(person), live(gold)
    pairs, extra, _ = match(p, g)
    norm = (lambda s: s or "") if species else pass1
    right = sum(norm(p[i].get("label", "")) == norm(g[j].get("label", "")) for i, j in pairs)
    model_wrong = [(i, j) for i, j in pairs if p[i].get("model_label")
                   and norm(p[i]["model_label"]) != norm(g[j].get("label", ""))]
    took = sum(norm(p[i].get("label", "")) == norm(p[i]["model_label"]) for i, j in model_wrong)
    return {"gold": len(g), "boxes": len(p), "found": len(pairs), "extra": len(extra), "label_right": right,
            "model_wrong": len(model_wrong), "took_wrong": took}


def merge_two(a: list[dict], b: list[dict], who: tuple[str, str]) -> tuple[list[dict], list[dict], float]:
    """Merge two people's boxes for one photo: (merged boxes, disputes, agreement).

    Matched boxes with the same label are kept (a's box) with by = "a+b". Everything else is kept too, marked
    disputed, with a dispute row saying what each person said, so a third person decides. agreement is the share
    of all boxes (matched pairs count once) the two agree on."""
    a, b = live(a), live(b)
    pairs, only_a, only_b = match(a, b)
    pairs.sort()  # in a's order
    merged, disputes = [], []
    for i, j in pairs:
        box = {**a[i], "by": f"{who[0]}+{who[1]}"}
        if a[i].get("label") != b[j].get("label"):
            box["disputed"] = True
            disputes.append({"box": box, "text": f"{who[0]}: {a[i].get('label') or '?'} · {who[1]}: {b[j].get('label') or '?'}"})
        merged.append(box)
    for i in only_a:
        box = {**a[i], "disputed": True}
        merged.append(box)
        disputes.append({"box": box, "text": f"only {who[0]} boxed this ({a[i].get('label') or '?'})"})
    for j in only_b:
        box = {**b[j], "disputed": True}
        merged.append(box)
        disputes.append({"box": box, "text": f"only {who[1]} boxed this ({b[j].get('label') or '?'})"})
    total = len(pairs) + len(only_a) + len(only_b)
    agreed = sum(a[i].get("label") == b[j].get("label") for i, j in pairs)
    return merged, disputes, (agreed / total if total else 1.0)


def seconds_per_box(times: list[float], gap: float = 300) -> float | None:
    """Median seconds between one person's consecutive box changes, ignoring breaks longer than `gap`."""
    t = sorted(times)
    d = sorted(y - x for x, y in zip(t, t[1:]) if 0 < y - x <= gap)
    return d[len(d) // 2] if d else None
