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


def paused(store: Store) -> set[str]:
    return {r["user"] for r in store.q("SELECT user FROM people WHERE paused=1")}


def set_paused(store: Store, user: str, on: bool) -> None:
    with store.lock:
        store.con.execute("INSERT OR REPLACE INTO people (user, paused, at) VALUES (?,?,?)", (user, int(on), time.time()))
        store.log("admin", "", "", None, "pause" if on else "resume", None, {"user": user})


def open_load(store: Store) -> dict[str, int]:
    """Unchecked boxes in each person's open photos: what 'least loaded' means."""
    rows = store.q("SELECT t.user, sum((SELECT count(*) FROM boxes b WHERE b.photo=t.photo AND b.copy=t.copy"
                   " AND b.label!='skip' AND (b.by='' OR b.label=''))) AS n FROM tasks t"
                   " WHERE t.status IN ('open','returned') GROUP BY t.user")
    return {r["user"]: r["n"] or 0 for r in rows}


def started(store: Store, task: dict) -> bool:
    """Whether the task's owner has done anything on it (a checked box or a logged change in their copy)."""
    if task["copy"].startswith("u:"):
        return bool(store.q("SELECT 1 FROM boxes WHERE photo=? AND copy=? AND by!='' LIMIT 1", task["photo"], task["copy"]))
    return bool(store.q("SELECT 1 FROM log WHERE photo=? AND copy=? AND user=? LIMIT 1", task["photo"], task["copy"], task["user"]))


def reassign(store: Store, task: dict, to: str, by: str) -> str:
    """Give an open task to someone else. A main-copy task (label, tiebreak, species, reference) just changes hands:
    what was done on the photo stays. A private copy (double, hidden test) is started fresh for the new person, so
    it is refused once its owner has started it, and the new person must not already have that photo."""
    if task["status"] not in ("open", "returned"):
        raise ValueError("only open photos can move")
    if to == task["user"]:
        raise ValueError("already theirs")
    # One person never holds two tasks on one photo: a hidden test next to its reference would show the answers,
    # and a two-person photo would no longer be two people.
    if store.q("SELECT 1 FROM tasks WHERE photo=? AND user=?", task["photo"], to):
        raise ValueError(f"{to} already has this photo")
    if task["copy"].startswith("u:"):
        if started(store, task):
            raise ValueError(f"{task['user']} has started this copy; moving it would lose their work")
        with store.lock:
            store.con.execute("DELETE FROM boxes WHERE photo=? AND copy=?", (task["photo"], task["copy"]))
        store.clone(task["photo"], "main", f"u:{to}")
        with store.lock:
            store.con.execute("UPDATE tasks SET user=?, copy=? WHERE id=?", (to, f"u:{to}", task["id"]))
    else:
        with store.lock:
            store.con.execute("UPDATE tasks SET user=? WHERE id=?", (to, task["id"]))
    with store.lock:
        store.log(by, task["photo"], task["copy"], None, "reassign", {"user": task["user"]}, {"user": to, "task": task["id"]})
    return f"moved to {to}"


def release(store: Store, user: str, to: list[str], by: str) -> dict:
    """Pause a person and hand their open photos out, least loaded first (by unchecked boxes). Their hidden test
    photos are dropped rather than moved (everyone else has their own). Started private copies stay with them."""
    set_paused(store, user, True)
    to = [u for u in to if u != user and u not in paused(store)]
    if not to:
        raise ValueError("nobody to hand the photos to")
    load = {u: open_load(store).get(u, 0) for u in to}
    out = {"moved": 0, "dropped_tests": 0, "kept_started": 0}
    tasks = store.q("SELECT * FROM tasks WHERE user=? AND status IN ('open','returned') ORDER BY priority DESC", user)
    sizes = {t["id"]: store.q("SELECT count(*) AS n FROM boxes WHERE photo=? AND copy=? AND label!='skip'",
                              t["photo"], t["copy"])[0]["n"] for t in tasks}
    for t in sorted(tasks, key=lambda t: -sizes[t["id"]]):  # biggest first, to the least loaded
        if t["kind"] == "gold_check" and not started(store, t):
            with store.lock:
                store.con.execute("DELETE FROM boxes WHERE photo=? AND copy=?", (t["photo"], t["copy"]))
                store.con.execute("DELETE FROM tasks WHERE id=?", (t["id"],))
                store.log(by, t["photo"], t["copy"], None, "drop-test", {"user": user}, None)
            out["dropped_tests"] += 1
            continue
        for u in sorted(load, key=lambda u: load[u]):
            try:
                reassign(store, t, u, by)
            except ValueError:
                continue
            load[u] += sizes[t["id"]]
            out["moved"] += 1
            break
        else:
            out["kept_started"] += 1
    return out


def assign(store: Store, labellers: list[str], experts: list[str], gold: int = 12, gold_each: int = 3,
           double: float = 0.10, seed: int = 26) -> dict:
    rng = random.Random(seed)
    labellers = [u for u in labellers if u not in paused(store)]  # paused people get nothing new
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
    users = [u for u in users if u not in paused(store)]
    third = next((u for u in users if u not in (a["user"], b["user"])), None)
    if third is None:
        third = next((r["user"] for r in store.q("SELECT DISTINCT user FROM tasks WHERE kind='label'")
                      if r["user"] not in (a["user"], b["user"]) and r["user"] not in paused(store)), a["user"])
    store.add_task(photo, third, "tiebreak", "main", 1.0)
    return f"merged: {len(disputes)} boxes you two disagreed on go to {third}"


def review(store: Store, task: dict, reviewer: str, accept: bool, note: str, species_experts: list[str]) -> None:
    store.set_task(task["id"], status="accepted" if accept else "returned", reviewer=reviewer,
                   reviewed_at=time.time(), note=note[:2000])
    if accept and task["kind"] in ("label", "tiebreak") and species_experts:
        has_moth = store.q("SELECT 1 FROM boxes WHERE photo=? AND copy='main' AND label='moth' LIMIT 1", task["photo"])
        if has_moth and not store.q("SELECT 1 FROM tasks WHERE photo=? AND kind='species'", task["photo"]):
            store.add_task(task["photo"], species_experts[0], "species", "main", 0.5)


def dashboard(store: Store, logins: list[str] | None = None) -> dict:
    users = sorted({r["user"] for r in store.q("SELECT DISTINCT user FROM tasks")} | set(logins or []) | paused(store))
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
    stopped = paused(store)
    for p in people:
        p["paused"] = p["user"] in stopped
        p["unchecked_open"] = open_load(store).get(p["user"], 0)
    merges = store.q("SELECT * FROM merges ORDER BY at DESC")
    photos = store.q("SELECT count(*) AS n, sum(gold) AS gold FROM photos")[0]
    boxes = store.q("SELECT count(*) AS n, sum(by != '' AND label != '') AS checked FROM boxes WHERE copy='main' AND label != 'skip'")[0]
    tasks = store.q("SELECT t.id, t.photo, t.user, t.kind, t.status, p.set_name,"
                    " (SELECT count(*) FROM boxes b WHERE b.photo=t.photo AND b.copy=t.copy AND b.label!='skip') AS n,"
                    " (SELECT count(*) FROM boxes b WHERE b.photo=t.photo AND b.copy=t.copy AND b.label!='skip'"
                    "  AND (b.by='' OR b.label='')) AS unchecked"
                    " FROM tasks t JOIN photos p ON p.name=t.photo ORDER BY t.user, t.status, t.priority DESC")
    return {"people": people, "merges": merges, "photos": photos, "boxes": boxes, "tasks": tasks,
            "mean_agreement": sum(m["agreement"] for m in merges) / len(merges) if merges else None,
            "issues_open": store.q("SELECT count(*) AS n FROM issues WHERE resolved_at IS NULL")[0]["n"]}


def gold_result(store: Store, photo: str, copy: str) -> dict | None:
    truth = store.q("SELECT status FROM tasks WHERE photo=? AND kind='gold_truth'", photo)
    if not truth or truth[0]["status"] != "accepted":
        return None  # the expert hasn't finished the reference yet
    return scoring.gold_score(store.boxes(photo, copy), store.boxes(photo, "gold"))
