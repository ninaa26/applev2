"""python -m unittest discover ml/tests   (needs numpy + pillow only)"""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
