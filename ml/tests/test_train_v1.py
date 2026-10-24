"""train_v1.py end to end on fake embeddings (needs scikit-learn; skipped without it, as in CI)."""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import train_v1  # noqa: E402

try:
    import sklearn  # noqa: F401
except ImportError:
    sklearn = None

CLASSES = ["CM", "OFM", "other_moth"]


class FakeEmbedder:
    def texts(self, prompts):
        return np.eye(len(prompts), 8)


def fake_rows(rng):
    rows, X = [], []
    for split, n in (("train", 30), ("val", 12), ("test", 9), ("locked", 6)):
        for i in range(n):
            k = i % len(CLASSES)
            rows.append({"split": split, "class": CLASSES[k], "source": "liner"})
            v = np.eye(8)[k] + 0.1 * rng.standard_normal(8)
            X.append(v / np.linalg.norm(v))
    return rows, np.array(X, np.float32)


@unittest.skipIf(sklearn is None, "needs scikit-learn")
class Final(unittest.TestCase):
    def test_final_scores_the_locked_cards(self):
        """--final used to crash: the text embeddings T were overwritten by the fitted temperature."""
        rows, X = fake_rows(np.random.default_rng(0))
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            with open(data / "dataset.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["split", "class", "source"])
                w.writeheader()
                w.writerows(rows)
            out = Path(tmp) / "out"
            with mock.patch.object(train_v1, "embeddings", return_value=(X, FakeEmbedder())):
                self.assertEqual(train_v1.main(["--data", str(data), "--out", str(out), "--final"]), 0)
            results = json.loads((out / "metrics.json").read_text())
            self.assertIn("v0 zero-shot · LOCKED own cards", results)
            self.assertIn("v1 linear head · LOCKED own cards", results)
            head = np.load(out / "head.npz")
            self.assertEqual(head["T"].shape, ())  # the temperature, a scalar


if __name__ == "__main__":
    unittest.main()
