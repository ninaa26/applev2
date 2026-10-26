"""The labelling site's logic: logins, the photo checks' decisions, scoring, the store and the workflow.
Standard library + numpy + Pillow only (no OpenCV, no torch), like the other ml tests."""

from __future__ import annotations

import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from label_site import scoring, workflow  # noqa: E402
from label_site.auth import MAX_FAILS, Auth, check_password, hash_password, read_cookie  # noqa: E402
from label_site.db import Conflict, Store, import_site  # noqa: E402
from photo_checks import card_groups, decide, jpeg_quality, pick_held_out  # noqa: E402


def box(x1, y1, x2, y2, label="moth", **kw):
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "label": label, **kw}


class TestScoring(unittest.TestCase):
    def test_match_greedy_by_overlap(self):
        a = [box(0, 0, 10, 10), box(50, 50, 60, 60)]
        b = [box(1, 1, 11, 11), box(100, 100, 110, 110)]
        pairs, only_a, only_b = scoring.match(a, b)
        self.assertEqual(pairs, [(0, 0)])
        self.assertEqual((only_a, only_b), ([1], [1]))

    def test_gold_score_counts_kept_wrong_model_labels(self):
        gold = [box(0, 0, 10, 10, "moth"), box(20, 20, 30, 30, "debris"), box(40, 40, 50, 50, "other_insect")]
        person = [box(0, 0, 10, 10, "moth", model_label="OFM"),          # right; model right at pass 1
                  box(20, 20, 30, 30, "moth", model_label="CM"),         # model wrong, kept: pressed Enter
                  box(80, 80, 90, 90, "debris"),                         # extra
                  box(5, 5, 9, 9, "skip")]                               # deleted: ignored
        s = scoring.gold_score(person, gold)
        self.assertEqual((s["gold"], s["found"], s["extra"], s["label_right"]), (3, 2, 1, 1))
        self.assertEqual((s["model_wrong"], s["took_wrong"]), (1, 1))
        sp = scoring.gold_score([box(0, 0, 10, 10, "OFM"), box(20, 20, 30, 30, "CM")],
                                [box(0, 0, 10, 10, "OFM"), box(20, 20, 30, 30, "OBLR")])
        self.assertEqual((sp["species_named"], sp["species_right"]), (2, 1))

    def test_merge_two_marks_disputes(self):
        a = [box(0, 0, 10, 10, "moth"), box(20, 20, 30, 30, "debris"), box(60, 60, 70, 70, "moth")]
        b = [box(1, 1, 10, 10, "moth"), box(20, 20, 30, 30, "other_insect"), box(90, 90, 99, 99, "moth")]
        merged, disputes, agreement = scoring.merge_two(a, b, ("ann", "bob"))
        self.assertEqual(len(merged), 4)
        self.assertEqual(len(disputes), 3)  # label differs, only ann, only bob
        self.assertAlmostEqual(agreement, 1 / 4)
        self.assertEqual(merged[0]["by"], "ann+bob")
        self.assertFalse(merged[0].get("disputed"))

    def test_overlapping(self):
        bs = [box(0, 0, 10, 10), box(5, 5, 15, 15), box(10, 0, 20, 10), box(2, 2, 4, 4, "skip"), box(50, 50, 60, 60)]
        # 0 and 1 share 25% of a box; 0 and 2 only touch at an edge; 3 is deleted; 4 is alone
        self.assertEqual(scoring.overlapping(bs), {0, 1, 2})  # 1 and 2 overlap too (x 10-15, y 5-10: 25%)
        self.assertEqual(scoring.overlapping([box(0, 0, 100, 100), box(99, 99, 110, 110)]), set())  # 1% of the small one

    def test_seconds_per_box_skips_breaks(self):
        self.assertEqual(scoring.seconds_per_box([0, 2, 4, 1000, 1003]), 2)
        self.assertIsNone(scoring.seconds_per_box([5]))


class TestCleanBoxes(unittest.TestCase):
    def test_off_photo_box_is_pulled_back(self):
        from label_site.server import clean_boxes

        got = clean_boxes([{"x1": -12.5, "y1": 40, "x2": 30, "y2": 2000, "label": "moth"},
                           {"x1": 50, "y1": 50, "x2": 50, "y2": 60, "label": "debris"}], (1000, 800))
        self.assertEqual((got[0]["x1"], got[0]["y2"]), (0.0, 800))
        self.assertGreater(got[1]["x2"], got[1]["x1"])  # zero width becomes one pixel, not a refused save
        with self.assertRaises(ValueError):
            clean_boxes([{"x1": 0, "y1": 0, "x2": 1, "y2": 1, "label": "dog"}])


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "users.json").write_text(json.dumps({"ann": {**hash_password("pw-ann", iterations=1000), "admin": True},
                                                         "bob": hash_password("pw-bob", iterations=1000)}))
        (self.tmp / "secret").write_text("ab" * 32)
        self.auth = Auth(self.tmp / "users.json", self.tmp / "secret")

    def test_password_hash(self):
        rec = hash_password("x", iterations=1000)
        self.assertTrue(check_password("x", rec))
        self.assertFalse(check_password("y", rec))
        self.assertNotIn("x", json.dumps(rec))

    def test_login_cookie_csrf(self):
        self.assertEqual(self.auth.login("Ann ", "pw-ann"), "ann")
        self.assertIsNone(self.auth.login("ann", "nope"))
        self.assertIsNone(self.auth.login("nobody", "pw-ann"))
        c = self.auth.make_cookie("bob", now=1000)
        self.assertEqual(self.auth.user_of(c, now=2000), "bob")
        self.assertIsNone(self.auth.user_of(c, now=1000 + 15 * 24 * 3600))  # expired
        self.assertIsNone(self.auth.user_of(c.replace("bob", "ann")))  # forged name
        self.assertTrue(self.auth.csrf_ok(c, self.auth.csrf(c)))
        self.assertFalse(self.auth.csrf_ok(c, "0" * 64))
        self.assertTrue(self.auth.is_admin("ann"))
        self.assertFalse(self.auth.is_admin("bob"))
        self.assertEqual(read_cookie("a=1; labels_session=xyz; b=2"), "xyz")

    def test_lockout(self):
        for _ in range(MAX_FAILS):
            self.auth.login("bob", "wrong", now=100)
        self.assertIsNone(self.auth.login("bob", "pw-bob", now=101))  # locked even with the right password
        self.assertEqual(self.auth.login("bob", "pw-bob", now=100 + 16 * 60), "bob")


class TestPhotoChecks(unittest.TestCase):
    def test_jpeg_quality(self):
        for q in (40, 75, 92):
            buf = io.BytesIO()
            Image.new("RGB", (32, 32)).save(buf, "JPEG", quality=q)
            buf.seek(0)
            self.assertEqual(jpeg_quality(Image.open(buf).quantization), q)
        self.assertIsNone(jpeg_quality(None))

    def test_decide(self):
        ok = {"megapixels": 12, "camera_exif": True, "jpeg_q": 95, "px_per_mm": 13, "scale_spread": 1.1,
              "sharpness": 100, "glare": 0.01, "brightness": 180, "duplicate_of": ""}
        self.assertEqual(decide(ok, 100, originals=True), ("keep", []))
        self.assertEqual(decide({**ok, "px_per_mm": None}, 100)[0], "flag")  # no scale: still labelled
        self.assertEqual(decide({**ok, "sharpness": 10}, 100)[0], "exclude")
        self.assertEqual(decide({**ok, "sharpness": 30}, 100)[0], "flag")
        copy = {**ok, "megapixels": 1.0, "camera_exif": False, "jpeg_q": 70}
        self.assertEqual(decide(copy, 100, originals=True)[0], "exclude")
        self.assertEqual(decide(copy, 100, originals=False)[0], "keep")  # a web export: small is normal
        self.assertEqual(decide({**ok, "px_per_mm": 2.4}, 100)[0], "flag")  # low resolution

    def test_card_groups_and_held_out(self):
        g = card_groups(["a", "b", "c", "d"], [("b", "c"), ("c", "d")])
        self.assertEqual(g, {"a": "a", "b": "b", "c": "b", "d": "b"})
        picks = [pick_held_out(f"card{i}") for i in range(300)]
        self.assertTrue(70 < sum(picks) < 130)  # about a third
        self.assertEqual(pick_held_out("x"), pick_held_out("x"))


def make_site(tmp: Path, photos: dict[str, list[dict]]) -> Path:
    site = tmp / "site"
    site.mkdir()
    with open(site / "photo_checks.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["photo", "set", "file", "source", "card", "decision", "why", "px_per_mm", "held_out"])
        w.writeheader()
        for p in photos:
            w.writerow({"photo": p, "set": p.split("__")[0], "file": p.split("__")[1], "source": f"x/{p}", "card": p,
                        "decision": "keep", "why": "", "px_per_mm": "12", "held_out": ""})
    with open(site / "labels.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["photo", "n", "label", "source", "x1", "y1", "x2", "y2", "conf", "model_label", "model_conf", "by"])
        w.writeheader()
        for p, bs in photos.items():
            for i, b in enumerate(bs, 1):
                w.writerow({"photo": p, "n": i, "source": "yolo", "conf": "0.6", "by": "", **b})
    return site


class TestStoreAndWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        boxes = [{"x1": 10 * i, "y1": 0, "x2": 10 * i + 8, "y2": 8, "label": "moth", "model_label": "OFM",
                  "model_conf": "0.95" if i % 2 else "0.5"} for i in range(4)]
        self.site = make_site(self.tmp, {f"s{k % 2}__p{k}.jpg": [dict(b) for b in boxes] for k in range(20)})
        self.store = Store(self.site)
        self.assertEqual(import_site(self.store.con, self.site), (20, 80))
        self.assertEqual(import_site(self.store.con, self.site), (0, 0))  # only what's new

    def test_save_logs_and_conflicts(self):
        s, p = self.store, "s0__p0.jpg"
        bs = s.boxes(p, "main")
        v = s.version(p, "main")
        page = [{"id": b["id"], "x1": float(b["x1"]), "y1": float(b["y1"]), "x2": float(b["x2"]), "y2": float(b["y2"]),
                 "label": b["label"], "attrs": "", "locked": 0} for b in bs]
        page[0]["confirm"] = True  # Enter on the first box
        page[1]["label"] = "debris"
        page[2]["attrs"] = "decayed"
        page.pop(3)  # deleted
        page.append({"id": None, "x1": 100.0, "y1": 100.0, "x2": 110.0, "y2": 110.0, "label": "other_insect", "attrs": "", "locked": 0})
        rows = s.save(p, "main", page, "ann", v)
        self.assertEqual(len(rows), 5)  # the detector's deleted box stays, as skip
        by_id = {r["id"]: r for r in rows}
        self.assertEqual(by_id[bs[0]["id"]]["by"], "ann")
        self.assertEqual(by_id[bs[1]["id"]]["label"], "debris")
        self.assertEqual(by_id[bs[3]["id"]]["label"], "skip")
        self.assertEqual(rows[-1]["source"], "manual")
        actions = sorted(r["action"] for r in s.q("SELECT action FROM log WHERE photo=?", p))
        self.assertEqual(actions, ["confirm", "delete", "draw", "edit", "edit"])
        with self.assertRaises(Conflict):
            s.save(p, "main", page, "bob", v)  # stale version

    def test_save_tags_overlaps_by_itself(self):
        s, p = self.store, "s0__p2.jpg"
        bs = s.boxes(p, "main")
        page = [{"id": b["id"], "x1": float(b["x1"]), "y1": float(b["y1"]), "x2": float(b["x2"]), "y2": float(b["y2"]),
                 "label": b["label"], "attrs": "", "locked": 0} for b in bs]
        page[1].update(x1=4.0, x2=12.0)  # now overlaps box 0 (0-8)
        rows = s.save(p, "main", page, "ann", None)
        self.assertEqual([("overlapping" in r["attrs"]) for r in rows], [True, True, False, False])
        self.assertEqual(rows[0]["by"], "")  # the tag isn't a person's check
        page[1].update(x1=10.0, x2=18.0)  # moved apart again
        rows = s.save(p, "main", [{**x, "attrs": "overlapping" if i < 2 else ""} for i, x in enumerate(page)], "ann", None)
        self.assertFalse(any("overlapping" in r["attrs"] for r in rows))

    def test_settings_round_trip(self):
        self.assertIsNone(self.store.setting("panels"))
        self.store.set_setting("panels", [300, 420])
        self.assertEqual(Store(self.site).setting("panels"), [300, 420])  # kept in site.db

    def test_locked_box_cannot_move(self):
        s, p = self.store, "s1__p1.jpg"
        b = s.boxes(p, "main")[0]
        one = {"id": b["id"], "x1": 0.0, "y1": 0.0, "x2": 8.0, "y2": 8.0, "label": "moth", "attrs": "", "locked": 1}
        others = [{"id": o["id"], "x1": float(o["x1"]), "y1": float(o["y1"]), "x2": float(o["x2"]), "y2": float(o["y2"]),
                   "label": o["label"], "attrs": "", "locked": 0} for o in s.boxes(p, "main")[1:]]
        s.save(p, "main", [one] + others, "ann", None)
        s.save(p, "main", [{**one, "x1": 50.0, "x2": 58.0}] + others, "bob", None)
        self.assertEqual(float(s.boxes(p, "main")[0]["x1"]), 0.0)

    def test_assign_gold_double_and_merge(self):
        s = self.store
        users = ["ann", "bob", "cat", "dan"]
        got = workflow.assign(s, users, ["nina"], gold=4, gold_each=2, double=0.25)
        self.assertEqual(got["gold"], 4)
        self.assertEqual(len(s.q("SELECT * FROM tasks WHERE kind='gold_truth' AND user='nina'")), 4)
        self.assertEqual(got["double"], 4)  # a quarter of the 16 left
        self.assertEqual(got["label"], 12)
        self.assertEqual(got["gold_check"], 8)
        self.assertEqual(len(s.boxes(s.q("SELECT photo FROM tasks WHERE kind='gold_truth'")[0]["photo"], "gold")), 4)
        # every non-gold photo is covered once (label) or twice (double)
        self.assertEqual(s.q("SELECT count(DISTINCT photo) AS n FROM tasks WHERE kind IN ('label','double')")[0]["n"], 16)
        # a double photo: two people, one disagreement -> merged with a tiebreak for a third person
        pair = s.q("SELECT * FROM tasks WHERE kind='double' ORDER BY id LIMIT 2")
        self.assertEqual(pair[0]["photo"], pair[1]["photo"])
        p = pair[0]["photo"]
        for t, lab in zip(pair, ("moth", "debris")):
            page = [{"id": b["id"], "x1": float(b["x1"]), "y1": float(b["y1"]), "x2": float(b["x2"]), "y2": float(b["y2"]),
                     "label": lab if i == 0 else b["label"], "attrs": "", "locked": 0, "confirm": True}
                    for i, b in enumerate(s.boxes(p, t["copy"]))]
            s.save(p, t["copy"], page, t["user"], None)
        self.assertIn("other person", workflow.done(s, s.task(pair[0]["id"]), pair[0]["user"]))
        msg = workflow.done(s, s.task(pair[1]["id"]), pair[1]["user"])
        self.assertIn("1 boxes", msg)
        merge = s.q("SELECT * FROM merges WHERE photo=?", p)[0]
        self.assertAlmostEqual(merge["agreement"], 3 / 4)
        tie = s.q("SELECT * FROM tasks WHERE photo=? AND kind='tiebreak'", p)[0]
        self.assertNotIn(tie["user"], (pair[0]["user"], pair[1]["user"]))
        self.assertEqual(len(s.q("SELECT * FROM issues WHERE photo=? AND kind='disagree'", p)), 1)
        disputed = [b for b in s.boxes(p, "main") if "disputed" in b["attrs"]]
        self.assertEqual(len(disputed), 1)
        self.assertEqual(disputed[0]["by"], "")

    def test_reassign_release_and_pause(self):
        s = self.store
        workflow.assign(s, ["ann", "bob", "cat"], ["nina"], gold=2, gold_each=1, double=0.2)
        main = s.q("SELECT * FROM tasks WHERE kind='label' AND user='ann' LIMIT 1")[0]
        self.assertEqual(workflow.reassign(s, main, "bob", "nina"), "moved to bob")
        ref = s.q("SELECT * FROM tasks WHERE kind='gold_truth' LIMIT 1")[0]
        tested = s.q("SELECT user FROM tasks WHERE photo=? AND kind='gold_check'", ref["photo"])
        if tested:
            with self.assertRaises(ValueError):  # would show them the answers
                workflow.reassign(s, ref, tested[0]["user"], "nina")
        self.assertEqual(s.task(main["id"])["user"], "bob")
        # a started private copy can't move
        dbl = s.q("SELECT * FROM tasks WHERE kind='double' ORDER BY id LIMIT 1")[0]
        b0 = s.boxes(dbl["photo"], dbl["copy"])[0]
        s.save(dbl["photo"], dbl["copy"], [{"id": b0["id"], "x1": float(b0["x1"]), "y1": float(b0["y1"]), "x2": float(b0["x2"]),
               "y2": float(b0["y2"]), "label": "debris", "attrs": "", "locked": 0}], dbl["user"], None)
        third = next(u for u in ("ann", "bob", "cat") if not s.q("SELECT 1 FROM tasks WHERE photo=? AND user=?", dbl["photo"], u))
        with self.assertRaises(ValueError):
            workflow.reassign(s, s.task(dbl["id"]), third, "nina")
        # pause cat: their open photos go to ann and bob, their hidden tests are dropped, nothing new comes
        cat_before = s.q("SELECT * FROM tasks WHERE user='cat' AND status='open'")
        got = workflow.release(s, "cat", ["ann", "bob", "cat"], "nina")
        tests = sum(t["kind"] == "gold_check" for t in cat_before)
        self.assertEqual(got["dropped_tests"], tests)
        self.assertEqual(got["moved"] + got["kept_started"] + tests, len(cat_before))
        left = s.q("SELECT * FROM tasks WHERE user='cat' AND status='open'")
        self.assertTrue(all(workflow.started(s, t) for t in left))
        self.assertIn("cat", workflow.paused(s))
        csv_rows = [{"photo": "s0__new.jpg", "n": 1, "label": "moth", "source": "yolo", "x1": 0, "y1": 0, "x2": 5, "y2": 5,
                     "conf": "0.6", "model_label": "OFM", "model_conf": "0.9", "by": ""}]
        with open(self.site / "labels.csv", "a", newline="") as f:
            csv.DictWriter(f, fieldnames=list(csv_rows[0])).writerows(csv_rows)
        with open(self.site / "photo_checks.csv", "a", newline="") as f:
            csv.DictWriter(f, fieldnames=["photo", "set", "file", "source", "card", "decision", "why", "px_per_mm", "held_out"]).writerow(
                {"photo": "s0__new.jpg", "set": "s0", "file": "new.jpg", "source": "x/new.jpg", "card": "new", "decision": "keep",
                 "why": "", "px_per_mm": "12", "held_out": ""})
        import_site(s.con, self.site)
        workflow.assign(s, ["ann", "bob", "cat"], ["nina"], gold=2, gold_each=1, double=0)
        self.assertNotEqual(s.q("SELECT user FROM tasks WHERE photo='s0__new.jpg'")[0]["user"], "cat")
        self.assertIn("cat", [p["user"] for p in workflow.dashboard(s, ["ann", "bob", "cat"])["people"]])

    def test_gold_scores_on_dashboard_and_review(self):
        s = self.store
        workflow.assign(s, ["ann", "bob"], ["nina"], gold=2, gold_each=1, double=0)
        check = s.q("SELECT * FROM tasks WHERE kind='gold_check' ORDER BY id")[0]
        truth = s.q("SELECT * FROM tasks WHERE kind='gold_truth' AND photo=?", check["photo"])[0]
        page = [{"id": b["id"], "x1": float(b["x1"]), "y1": float(b["y1"]), "x2": float(b["x2"]), "y2": float(b["y2"]),
                 "label": "debris" if i == 0 else "moth", "attrs": "", "locked": 0, "confirm": True}
                for i, b in enumerate(s.boxes(truth["photo"], "gold"))]
        s.save(truth["photo"], "gold", page, "nina", None)
        workflow.done(s, truth, "nina")
        page = [{"id": b["id"], "x1": float(b["x1"]), "y1": float(b["y1"]), "x2": float(b["x2"]), "y2": float(b["y2"]),
                 "label": b["label"], "attrs": "", "locked": 0, "confirm": True} for b in s.boxes(truth["photo"], check["copy"])]
        s.save(truth["photo"], check["copy"], page, check["user"], None)  # Enter on everything
        workflow.done(s, check, check["user"])
        person = next(x for x in workflow.dashboard(s)["people"] if x["user"] == check["user"])
        self.assertEqual((person["gold_found"], person["gold_label_right"]), (4, 3))
        self.assertEqual((person["gold_model_wrong"], person["gold_took_wrong"]), (1, 1))
        lab = s.q("SELECT * FROM tasks WHERE kind='label' LIMIT 1")[0]
        workflow.done(s, lab, lab["user"])
        workflow.review(s, s.task(lab["id"]), "nina", True, "", ["patti"])
        self.assertEqual(s.task(lab["id"])["status"], "accepted")
        self.assertEqual(s.q("SELECT user FROM tasks WHERE photo=? AND kind='species'", lab["photo"])[0]["user"], "patti")


if __name__ == "__main__":
    unittest.main()
