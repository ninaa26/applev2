"""Who labels what, and what happens when they're done. Standard library only.

assign():
  - hidden test photos ("gold"): --gold photos (about 12), spread over the sets, are labelled carefully by the
    experts first (a gold_truth task each, on the "gold" copy). Each labeller also gets --gold-each of them in
    their queue as ordinary-looking photos (gold_check, on a private copy, pre-labelled by the models like any
    other) at random places, so nobody can tell them apart. Their copy is scored against the gold copy.
  - two people ("double"): --double of the remaining photos (10%) go to two labellers, each on a private copy.
    When both are done they are merged (scoring.merge_two); boxes they disagree on are marked disputed with an
    issue each, and a third person gets a tiebreak task on the main copy. Agreement is recorded per photo.
  - everyone else: one labeller each (label, on the main copy), balanced by box count, most unsure photos first.
done(): a finished label / tiebreak goes to review (status done) for an admin to accept or send back; a merged
double goes to tiebreak or straight to review; an accepted photo gets a species task (pass 2) for a species expert.
"""

from __future__ import annotations

import random
import time

from . import scoring
from .db import Store

LABEL_KINDS = ("label", "double", "gold_check", "tiebreak")


def assign(store: Store, labellers: list[str], experts: list[str], gold: int = 12, gold_each: int = 3,
           double: float = 0.10, seed: int = 26) -> dict:
    rng = random.Random(seed)
    photos = store.q("SELECT p.name, p.set_name, p.priority, (SELECT count(*) FROM boxes b WHERE b.photo=p.name"
                     " AND b.copy='main') AS n FROM photos p WHERE p.name NOT IN (SELECT photo FROM tasks)"
                     " ORDER BY p.name")
    if not photos:
        return {"photos": 0}
    out = {"photos": len(photos), "gold": 0, "double": 0, "label": 0, "gold_check": 0}
    have_gold = {r["name"] for r in store.q("SELECT name FROM photos WHERE gold=1")}
    # Hidden test photos: spread over the sets, round-robin, from photos with at least a few boxes.
    want = max(0, gold - len(have_gold))
    by_set: dict[str, list[dict]] = {}
    for p in photos:
        if p["n"] >= 3:
            by_set.setdefault(p["set_name"], []).append(p)
    for v in by_set.values():
        rng.shuffle(v)
    picked = []
    while want and any(by_set.values()):
        for k in sorted(by_set):
            if want and by_set[k]:
                picked.append(by_set[k].pop())
                want -= 1
    for p in picked:
        store.con.execute("UPDATE photos SET gold=1 WHERE name=?", (p["name"],))
        store.clone(p["name"], "main", "gold")
        if experts:  # the first expert labels the test photos (pass 1 and, where they can, species)
            store.add_task(p["name"], experts[0], "gold_truth", "gold", 1.0)
        out["gold"] += 1
    gold_names = have_gold | {p["name"] for p in picked}
    rest = [p for p in photos if p["name"] not in gold_names]
    rng.shuffle(rest)
    n_double = round(len(rest) * double) if len(labellers) >= 3 else 0
    load = {u: 0 for u in labellers}
    for p in rest[:n_double]:
        a, b = sorted(load, key=lambda u: (load[u], rng.random()))[:2]
        for u in (a, b):
            store.clone(p["name"], "main", f"u:{u}")
            store.add_task(p["name"], u, "double", f"u:{u}", p["priority"])
            load[u] += p["n"]
        out["double"] += 1
    for p in sorted(rest[n_double:], key=lambda p: -p["n"]):  # biggest first, to the least loaded
        u = min(load, key=lambda u: (load[u], rng.random()))
        store.add_task(p["name"], u, "label", "main", p["priority"])
        load[u] += p["n"]
        out["label"] += 1
    # Each labeller's hidden test photos, at random priorities among their own.
    for u in labellers:
        prios = [t["priority"] for t in store.q("SELECT priority FROM tasks WHERE user=? AND kind IN ('label','double')", u)] or [0.5]
        for g in rng.sample(sorted(gold_names), min(gold_each, len(gold_names))):
            if store.q("SELECT 1 FROM tasks WHERE photo=? AND user=?", g, u):
                continue
            store.clone(g, "main", f"u:{u}")
            store.add_task(g, u, "gold_check", f"u:{u}", rng.choice(prios))
            out["gold_check"] += 1
    return out


def done(store: Store, task: dict, user: str) -> str:
    """Mark a task finished. Returns what happened, for the page to say."""
    store.set_task(task["id"], status="done", done_at=time.time())
    if task["kind"] == "double":
        pair = store.q("SELECT * FROM tasks WHERE photo=? AND kind='double'", task["photo"])
        if len(pair) == 2 and all(t["status"] in ("done", "accepted") for t in pair):
            return merge_double(store, task["photo"], pair)
        return "saved; the photo merges once the other person finishes too"
    if task["kind"] == "gold_check":
        store.set_task(task["id"], status="accepted")  # scored, not reviewed
        return "done"
    if task["kind"] == "gold_truth":
        store.set_task(task["id"], status="accepted")
        return "done: this is now a reference photo"
    return "done: it goes to review"


def merge_double(store: Store, photo: str, pair: list[dict]) -> str:
    a, b = pair
    merged, disputes, agreement = scoring.merge_two(store.boxes(photo, a["copy"]), store.boxes(photo, b["copy"]),
                                                    (a["user"], b["user"]))
    for m in merged:
        if m.get("disputed"):
            m["attrs"] = ",".join(sorted(set(filter(None, (m.get("attrs") or "").split(","))) | {"disputed"}))
            m["by"] = ""  # unchecked until the tiebreak
    ids = store.replace_copy(photo, "main", merged, "merge")
    for m, i in zip(merged, ids):
        m["new_id"] = i
    for d in disputes:
        box = d["box"]
        store.add_issue(photo, "main", box.get("new_id"), (box["x1"] + box["x2"]) / 2, box["y1"], "disagree", d["text"], "merge")
    with store.lock:
        store.con.execute("INSERT OR REPLACE INTO merges VALUES (?,?,?,?,?,?)",
                          (photo, a["user"], b["user"], agreement, len(disputes), time.time()))
    if not disputes:
        return f"merged: you two agreed on every box ({agreement:.0%})"
    users = [r["user"] for r in store.q("SELECT user, count(*) AS n FROM tasks WHERE status='open' AND kind IN"
                                        " ('label','double','tiebreak') GROUP BY user ORDER BY n")]
    third = next((u for u in users if u not in (a["user"], b["user"])), None)
    if third is None:
        third = next((r["user"] for r in store.q("SELECT DISTINCT user FROM tasks WHERE kind='label'")
                      if r["user"] not in (a["user"], b["user"])), a["user"])
    store.add_task(photo, third, "tiebreak", "main", 1.0)
    return f"merged: {len(disputes)} boxes you two disagreed on go to {third}"


def review(store: Store, task: dict, reviewer: str, accept: bool, note: str, species_experts: list[str]) -> None:
    store.set_task(task["id"], status="accepted" if accept else "returned", reviewer=reviewer,
                   reviewed_at=time.time(), note=note[:2000])
    if accept and task["kind"] in ("label", "tiebreak") and species_experts:
        has_moth = store.q("SELECT 1 FROM boxes WHERE photo=? AND copy='main' AND label='moth' LIMIT 1", task["photo"])
        if has_moth and not store.q("SELECT 1 FROM tasks WHERE photo=? AND kind='species'", task["photo"]):
            store.add_task(task["photo"], species_experts[0], "species", "main", 0.5)


def dashboard(store: Store) -> dict:
    users = sorted({r["user"] for r in store.q("SELECT DISTINCT user FROM tasks")})
    people = []
    for u in users:
        t = store.q("SELECT kind, status FROM tasks WHERE user=?", u)
        times = [r["at"] for r in store.q("SELECT at FROM log WHERE user=? AND box_id IS NOT NULL", u)]
        gold = [gold_result(store, r["photo"], r["copy"]) for r in
                store.q("SELECT photo, copy FROM tasks WHERE user=? AND kind='gold_check' AND status!='open'", u)]
        gold = [g for g in gold if g]
        tot = {k: sum(g[k] for g in gold) for k in ("gold", "found", "extra", "label_right", "model_wrong", "took_wrong",
                                                     "species_named", "species_right")}
        people.append({
            "user": u,
            "open": sum(r["status"] == "open" for r in t), "returned": sum(r["status"] == "returned" for r in t),
            "done": sum(r["status"] == "done" for r in t), "accepted": sum(r["status"] == "accepted" for r in t),
            "box_changes": len(times), "sec_per_box": scoring.seconds_per_box(times),
            "gold_photos": len(gold), **{f"gold_{k}": v for k, v in tot.items()},
        })
    merges = store.q("SELECT * FROM merges ORDER BY at DESC")
    photos = store.q("SELECT count(*) AS n, sum(gold) AS gold FROM photos")[0]
    boxes = store.q("SELECT count(*) AS n, sum(by != '' AND label != '') AS checked FROM boxes WHERE copy='main' AND label != 'skip'")[0]
    return {"people": people, "merges": merges, "photos": photos, "boxes": boxes,
            "mean_agreement": sum(m["agreement"] for m in merges) / len(merges) if merges else None,
            "issues_open": store.q("SELECT count(*) AS n FROM issues WHERE resolved_at IS NULL")[0]["n"]}


def gold_result(store: Store, photo: str, copy: str) -> dict | None:
    truth = store.q("SELECT status FROM tasks WHERE photo=? AND kind='gold_truth'", photo)
    if not truth or truth[0]["status"] != "accepted":
        return None  # the expert hasn't finished the reference yet
    return scoring.gold_score(store.boxes(photo, copy), store.boxes(photo, "gold"))
