"""python -m unittest discover ml/tests   (needs numpy + pillow only)"""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build_moth_dataset as bm  # noqa: E402
import paths  # noqa: E402


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


class WebPhotos(unittest.TestCase):
    def test_four_classes_adults_only_and_one_observation_stays_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            row = {"label": "CM", "file": "", "source": "inat", "license": "cc-by", "attribution": "x",
                   "record_url": "", "life_stage": ""}
            write_csv(data / paths.ALL_SPECIES / "manifest.csv", [
                {**row, "file": "CM/a.jpg", "record_url": "obs/1", "life_stage": "adult"},
                {**row, "file": "CM/b.jpg", "record_url": "obs/1", "life_stage": "Adult(s)"},
                {**row, "file": "CM/c.jpg", "record_url": "obs/2", "life_stage": "larva"},
                {**row, "label": "lookalike_RBLR", "file": "lookalike_RBLR/d.jpg", "record_url": "obs/3"},
                {**row, "label": "other_insect", "file": "other_insect/e.jpg", "record_url": "obs/4"},
            ])
            rows, left_out = bm.web_rows(data, 0, 0.15, 0.05)
            self.assertEqual([(r["path"].split("/")[-1], r["class"]) for r in rows],
                             [("a.jpg", "CM"), ("b.jpg", "CM"), ("d.jpg", "other_moth")])
            self.assertEqual(rows[0]["split"], rows[1]["split"])
            self.assertEqual(left_out, {"life stage larva": 1, "label other_insect": 1})


class RealLinerCrops(unittest.TestCase):
    def test_checked_species_boxes_are_cropped_tuned_on_or_held_out_never_trained(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            inbox = data / paths.LABEL_SITE / "inbox"
            inbox.mkdir(parents=True)
            box = {"n": 1, "x1": 300, "y1": 300, "x2": 400, "y2": 340, "ppm": 30, "by": "claude", "attrs": ""}
            labels = []
            for photo in ("ofm__liner1_day1.jpg", "ofm__liner1_day2.jpg", "ofm__liner2.jpg"):
                Image.new("RGB", (1000, 800), "white").save(inbox / photo)
                labels.append({"site_photo": photo, "photo": photo.split("__")[1], "label": "OFM", **box})
            labels += [
                {**labels[2], "n": 2, "label": "moth"},                     # no species yet
                {**labels[2], "n": 3, "label": "debris"},                   # not a moth
                {**labels[2], "n": 4, "label": "CM", "attrs": "unsure"},    # species unsure
                {**labels[2], "n": 5, "label": "other_tortricid"},          # -> other_moth
            ]
            export = data / paths.LABEL_SITE_EXPORTS / "1" / "labels.csv"
            write_csv(export, labels)
            (data / paths.WEB_LINERS / "label/ofm").mkdir(parents=True)
            (data / paths.WEB_LINERS / "label/ofm/liners.json").write_text(
                json.dumps([["liner1_day1.jpg", "liner1_day2.jpg"]]))

            rows, skipped = bm.site_rows(data, export, [15.0, 10.0], ["liner1_day1"])
            got = sorted((r["credit"], r["class"], r["split"], r["ppm"]) for r in rows)
            self.assertEqual(got, [
                ("ofm__liner1_day1.jpg #1", "OFM", "test", "10.0"), ("ofm__liner1_day1.jpg #1", "OFM", "test", "15.0"),
                ("ofm__liner1_day2.jpg #1", "OFM", "test", "10.0"), ("ofm__liner1_day2.jpg #1", "OFM", "test", "15.0"),
                ("ofm__liner2.jpg #1", "OFM", "tune", "10.0"), ("ofm__liner2.jpg #1", "OFM", "tune", "15.0"),
                ("ofm__liner2.jpg #5", "other_moth", "tune", "10.0"), ("ofm__liner2.jpg #5", "other_moth", "tune", "15.0"),
            ])
            self.assertEqual(skipped, {"marked unsure": 1})
            self.assertTrue(all(r["source"] == "liner" for r in rows))
            # 100 px at 30 px/mm with the server's padding, shrunk to 15 px/mm: 170 / 2 = 85 px
            with Image.open(next(r["path"] for r in rows if r["ppm"] == "15.0")) as im:
                self.assertEqual(im.size, (85, 85))


if __name__ == "__main__":
    unittest.main()
