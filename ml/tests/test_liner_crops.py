"""python -m unittest discover ml/tests   (needs numpy + pillow only)"""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_dataset  # noqa: E402
import liner_crops  # noqa: E402
import train_v1  # noqa: E402

FIELDS = ["photo", "n", "label", "source", "crop", "cutout", "x1", "y1", "x2", "y2", "conf", "ppm", "length_mm"]


class LinerCrops(unittest.TestCase):
    def test_uploader_species_pass1_labels_and_liner_groups(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "label" / "ofm-ervins"
            folder.mkdir(parents=True)
            rows = [("day2.jpg", "moth", "roboflow:OFM"), ("day1.jpg", "other_insect", "flatbug"),
                    ("day1.jpg", "CM", "roboflow:OFM"),       # pass 2 overrules the uploader
                    ("day1.jpg", "skip", "roboflow:OFM"), ("alone.jpg", "", "baseline"), ("alone.jpg", "moth", "manual")]
            with open(folder / "labels.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS, restval="")
                w.writeheader()
                w.writerows({"photo": p, "label": lab, "source": s, "crop": f"{k}.jpg", "ppm": "26.0", "length_mm": "6.0"}
                            for k, (p, lab, s) in enumerate(rows))
            (folder / "liners.json").write_text(json.dumps([["day2.jpg", "day1.jpg"]]))
            got = liner_crops.ofm_liner_rows(Path(tmp))
        self.assertEqual([(r["label"], r["group"]) for r in got], [("OFM", "day1"), ("other_insect", "day1"), ("CM", "day1")])

    def test_field_card_species_from_pass_2_or_the_species_file_and_held_out_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            field = Path(tmp)
            rows = [("PXL_20250617_1.jpg", "1", "moth"), ("PXL_20250617_1.jpg", "2", "moth"),   # 2: nobody named it
                    ("PXL_20250617_1.jpg", "3", "CM"),                                          # pass 2 in labels.csv
                    ("PXL_20250617_1.jpg", "4", "other_insect"), ("card_T.jpg", "1", "moth"),
                    ("PXL_20250422_174434151.RAW.jpg", "1", "moth")]
            with open(field / "labels.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS, restval="")
                w.writeheader()
                w.writerows({"photo": p, "n": n, "label": lab, "crop": f"{p}_{n}.jpg", "ppm": "40", "length_mm": "9"}
                            for p, n, lab in rows)
            (field / "species.csv").write_text("photo,n,species,by,note\nPXL_20250617_1.jpg,1,OBLR,claude,\n"
                                               "PXL_20250617_1.jpg,2,,claude,unsure\ncard_T.jpg,1,CM,claude,\n"
                                               "PXL_20250422_174434151.RAW.jpg,1,OFM,claude,\n")
            (field / "test_cards.txt").write_text("# held out\ncard_T.jpg\n")
            got = liner_crops.field_card_rows(field)
        self.assertEqual([(r["label"], r["held_out"]) for r in got],
                         [("OBLR", False), ("CM", False), ("CM", True), ("OFM", True)])

    def test_only_resolutions_the_photo_can_give(self):
        self.assertEqual(liner_crops.resolutions(26.0, [15.0, 10.0]), [15.0, 10.0])
        self.assertEqual(liner_crops.resolutions(10.3, [15.0, 10.0]), [10.0])
        self.assertEqual(liner_crops.resolutions(6.0, [15.0, 10.0]), [10.0])

    def test_dataset_keeps_held_out_liners_in_test_and_a_liner_on_one_side(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "web_liners" / "species").mkdir(parents=True)
            with open(data / "web_liners" / "species" / "manifest.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=liner_crops.FIELDS)
                w.writeheader()
                for g in range(9):
                    for k in range(3):
                        w.writerow({"path": f"{g}_{k}.jpg", "label": "OFM", "set": "ofm-liners", "photo": f"{g}.jpg",
                                    "group": f"g{g}", "split": "test" if g == 0 else "", "ppm": "15.0", "length_mm": "6"})
            build_dataset.main(["--data", str(data)])
            with open(data / "dataset.csv", newline="") as f:
                rows = list(csv.DictReader(f))
        splits = {}
        for r in rows:
            self.assertEqual(r["source"], "liner")
            splits.setdefault(r["group"], set()).add(r["split"])
        self.assertTrue(all(len(s) == 1 for s in splits.values()))
        self.assertEqual(splits["liner:g0"], {"test"})
        self.assertEqual(sorted(next(iter(s)) for g, s in splits.items() if g != "liner:g0").count("val"), 2)  # a fifth of 24 crops
        self.assertNotIn("test", {next(iter(s)) for g, s in splits.items() if g != "liner:g0"})


class Intervals(unittest.TestCase):
    def test_wilson_is_wide_for_few_crops_and_stays_in_range(self):
        import eval_liner_species as ev

        lo, hi = ev.wilson(2, 4)
        self.assertLess(lo, 0.2)
        self.assertGreater(hi, 0.8)
        lo, hi = ev.wilson(155, 162)
        self.assertTrue(0.91 < lo < 0.96 < hi < 0.99)
        self.assertEqual(ev.wilson(0, 0), (0.0, 1.0))
        self.assertEqual(ev.wilson(5, 5)[1], 1.0)


class Exclude(unittest.TestCase):
    def test_excluded_photos_are_left_out(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / "inat").mkdir()
            rng = np.random.default_rng(0)
            rows = []
            for k in range(3):
                path = data / "inat" / f"{k}.jpg"
                Image.fromarray(rng.integers(0, 255, (120, 120, 3), dtype=np.uint8)).save(path)
                rows.append({"local_path": str(path), "label": "CM", "observation": str(k), "photo": str(k),
                             "license": "cc0", "attribution": "", "status": "ok"})
            with open(data / "inat" / "manifest.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
            with open(data / "exclude.csv", "w", newline="") as f:
                f.write(f"path,why\n{rows[1]['local_path']},not adult: larva 0.99\n")
            build_dataset.main(["--data", str(data)])
            with open(data / "dataset.csv", newline="") as f:
                kept = [Path(r["path"]).name for r in csv.DictReader(f)]
        self.assertEqual(sorted(kept), ["0.jpg", "2.jpg"])


class Temperature(unittest.TestCase):
    def test_overconfident_logits_get_a_temperature_above_one(self):
        rng = np.random.default_rng(0)
        y = rng.integers(0, 3, 600)
        logits = rng.normal(0, 1, (600, 3))
        logits[np.arange(600), y] += 1.0          # right about 55% of the time ...
        self.assertGreater(train_v1.fit_temperature(logits * 8, y), 4)   # ... but sure of itself
        self.assertAlmostEqual(train_v1.fit_temperature(logits, y), 1.0, delta=0.35)
        self.assertEqual(train_v1.fit_temperature(logits[:0], y[:0]), 1.0)


if __name__ == "__main__":
    unittest.main()
