"""python -m unittest discover ml/tests   (needs pillow only)"""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import train_yolo as ty  # noqa: E402


def fake_source(root: Path, photos: list[str], liners: list[list[str]], test_cards: list[str]) -> Path:
    (root / "inbox").mkdir(parents=True)
    with open(root / "labels.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["photo", "label", "x1", "y1", "x2", "y2", "ppm"])
        w.writeheader()
        for p in photos:
            Image.new("RGB", (800, 700), "white").save(root / "inbox" / p)
            w.writerow({"photo": p, "label": "moth", "x1": 100, "y1": 100, "x2": 190, "y2": 140, "ppm": 12})
    (root / "liners.json").write_text(json.dumps(liners))
    (root / "test_cards.txt").write_text("# held out\n" + "\n".join(test_cards))
    return root


class Splits(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.photos = [f"liner{i:02d}_day{d}.jpg" for i in range(12) for d in (1, 2)]
        self.liners = [[f"liner{i:02d}_day1.jpg", f"liner{i:02d}_day2.jpg"] for i in range(12)]
        self.src = fake_source(root / "src", self.photos, self.liners, ["liner00_day1.jpg"])
        self.out = root / "yolo"
        self.info = ty.build(self.out, 12, 640, 160, ["liner01_day2"], 0.4, sources=[self.src])

    def tearDown(self):
        self.tmp.cleanup()

    def liners_in(self, split: str) -> set[str]:
        return {p.name.split("__")[1][:7] for p in (self.out / "images" / split).glob("*.jpg")}

    def test_three_splits_never_share_a_liner(self):
        train, val, test = (self.liners_in(s) for s in ty.SPLITS)
        self.assertEqual(test, {"liner00", "liner01"})  # test_cards.txt and --test-photos, with their other days
        self.assertTrue(val and train)
        self.assertFalse(train & val or train & test or val & test)
        self.assertEqual(len(train | val | test), 12)
        self.assertEqual(sum(self.info["splits"][s]["photos"] for s in ty.SPLITS), 24)

    def test_data_yaml_names_a_test_split(self):
        self.assertIn("test: images/test", (self.out / "data.yaml").read_text())

    def test_val_is_the_same_every_run_and_survives_a_new_photo(self):
        rest = [p for p in self.photos if not p.startswith(("liner00", "liner01"))]
        val = ty.pick_val(self.src, rest, 0.15)
        self.assertEqual(val, ty.pick_val(self.src, list(reversed(rest)), 0.15))
        self.assertGreaterEqual(len(val), 0.15 * len(rest))
        self.assertLessEqual(val, ty.pick_val(self.src, rest + ["zz_new.jpg"], 0.15) | val)

    def test_no_val_frac_means_no_val_photos(self):
        self.assertEqual(ty.pick_val(self.src, self.photos, 0), set())


class TilesAndBlanks(unittest.TestCase):
    def test_overlap_fits_the_longest_moth(self):
        self.assertEqual(ty.default_overlap(12), 224)   # 18 mm at 12 px/mm = 216 px
        self.assertEqual(ty.default_overlap(7), 160)    # never less than before
        self.assertGreaterEqual(ty.default_overlap(15.3), 18 * 15.3)

    def test_blank_liner_photos_become_tiles_with_no_boxes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for d in ("images/train", "labels/train"):
                (tmp / "out" / d).mkdir(parents=True)
            (tmp / "blank").mkdir()
            Image.new("RGB", (1600, 1200), "white").save(tmp / "blank" / "calibrated_1.jpg")
            info = ty.add_blanks(tmp / "out", [str(tmp / "blank" / "calibrated_*.jpg")], 16, 8, 640, 224)
            labels = list((tmp / "out/labels/train").glob("blank__*.txt"))
            self.assertEqual(info, {"photos": 1, "tiles": len(labels)})
            self.assertGreater(len(labels), 0)  # 800x600 at 8 px/mm
            self.assertTrue(all(f.read_text() == "" for f in labels))
            self.assertEqual(len(list((tmp / "out/images/train").glob("blank__*.jpg"))), len(labels))

    def test_one_insect_class_folds_moths_and_bycatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = fake_source(Path(tmp) / "src", ["a.jpg", "b.jpg"], [], [])
            classes, merge = list(ty.CLASSES), dict(ty.MERGE)
            try:
                ty.one_insect_class()
                info = ty.build(Path(tmp) / "out", 12, 640, 224, [], 0.4, 0, sources=[src])
                self.assertEqual(ty.CLASSES, ["insect", "debris"])
                self.assertEqual(info["boxes_per_class"]["train"]["insect"], info["splits"]["train"]["boxes"])
                self.assertIn("0: insect", (Path(tmp) / "out/data.yaml").read_text())
            finally:
                ty.CLASSES, ty.MERGE = classes, merge
                ty.MERGE.clear(); ty.MERGE.update(merge)

    def test_confidence_is_chosen_where_f1_peaks(self):
        class Box:
            px = [0.0, 0.25, 0.5, 0.75]
            f1_curve = [[0.2, 0.8, 0.6, 0.1], [0.2, 0.4, 0.6, 0.1]]
            p_curve = [[0.1, 0.7, 0.9, 1.0], [0.1, 0.3, 0.5, 1.0]]
            r_curve = [[1.0, 0.9, 0.5, 0.1], [1.0, 0.6, 0.7, 0.1]]
            ap_class_index = [0, 2]
        self.assertEqual(ty.best_conf(Box), (0.25, 0.6))  # mean F1: 0.2, 0.6, 0.6, 0.1 -> the first peak
        self.assertEqual(ty.at_conf(Box, 0.5)["debris"], {"precision": 0.5, "recall": 0.7, "f1": 0.6})


if __name__ == "__main__":
    unittest.main()
