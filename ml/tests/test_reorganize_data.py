"""python -m unittest discover ml/tests   (needs numpy only)"""

import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reorganize_data as rd  # noqa: E402


class Rewrite(unittest.TestCase):
    def test_relative_absolute_and_doc_paths(self):
        self.assertEqual(rd.rewrite("data/inat/CM/1.jpg"), "data/web_moth_photos/inaturalist/CM/1.jpg")
        self.assertEqual(rd.rewrite("/Users/x/applev2/ml/data/synth/CM/a.jpg"),
                         "/Users/x/applev2/ml/data/trap_style/v1_webcam_2026-09/photos/CM/a.jpg")
        self.assertEqual(rd.rewrite("data/synth/manifest.csv"), "data/trap_style/v1_webcam_2026-09/manifest.csv")
        self.assertEqual(rd.rewrite("see `data/field/test_cards.txt`."), "see `data/training/held_out/field_cards.txt`.")
        self.assertEqual(rd.rewrite("../ml/models/v1/head.npz"), "../ml/models/classifier/bioclip_head/current/head.npz")
        self.assertEqual(rd.rewrite("models/v1-cuda/"), "models/classifier/bioclip_head/archive/2026-10-08_cuda_retrain/")
        self.assertEqual(rd.rewrite("data/yolo-blank/data.yaml"), "data/training/detector/yolo_blank/data.yaml")

    def test_leaves_other_folders_alone(self):
        for text in ("server/data/media/T1/a.jpg", "data/web_liners_old/x", "metadata/inat/x",
                     "data/dataset.backup.csv.gz", "https://example.org/ml/data/inat/1.jpg"):
            self.assertEqual(rd.rewrite(text), text)
        self.assertEqual(rd.rewrite("data/web_liners/field/inbox/a.jpg"),
                         "data/real_liners/from_the_web/field/inbox/a.jpg")  # not the Cornell field cards


class MoveAndUndo(unittest.TestCase):
    def test_moves_rewrites_relinks_and_undoes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ml = Path(tmp) / "ml"
            data, models = ml / "data", ml / "models"
            (data / "inat" / "CM").mkdir(parents=True)
            (data / "inat" / "CM" / "1.jpg").write_bytes(b"jpg")
            (data / "synth" / "CM").mkdir(parents=True)
            (data / "synth" / "CM" / "a.jpg").write_bytes(b"jpg")
            with open(data / "synth" / "manifest.csv", "w", newline="") as f:
                csv.writer(f).writerows([["path", "source_path"], ["data/synth/CM/a.jpg", "data/inat/CM/1.jpg"]])
            (data / "dataset.csv").write_text(f"path\ndata/inat/CM/1.jpg\n{data}/synth/CM/a.jpg\n")
            (data / "embeddings").mkdir()
            np.savez(data / "embeddings" / "m.npz", paths=np.array([f"{data}/inat/CM/1.jpg", "data/synth/CM/a.jpg"]),
                     feats=np.eye(2, dtype=np.float16))
            (data / "web_liners" / "inat").mkdir(parents=True)
            os.symlink(data / "inat" / "CM" / "1.jpg", data / "web_liners" / "inat" / "link.jpg")
            (data / "segments").mkdir()
            (models / "v1").mkdir(parents=True)
            (models / "v1" / "head.npz").write_bytes(b"npz")
            before = sorted(str(p.relative_to(ml)) for p in ml.rglob("*"))

            self.assertEqual(rd.main(["--data", str(data), "--models", str(models), "--write"]), 0)
            v1 = data / "trap_style" / "v1_webcam_2026-09"
            self.assertTrue((v1 / "photos" / "CM" / "a.jpg").exists())
            self.assertFalse((data / "synth").exists() or (data / "segments").exists())
            self.assertEqual((v1 / "manifest.csv").read_text().splitlines()[1],
                             "data/trap_style/v1_webcam_2026-09/photos/CM/a.jpg,data/web_moth_photos/inaturalist/CM/1.jpg")
            self.assertEqual((data / "training/classifier/dataset.csv").read_text().splitlines()[2],
                             f"{v1}/photos/CM/a.jpg")
            z = np.load(data / "training/classifier/bioclip_embeddings/m.npz")
            self.assertEqual(sorted(z["paths"].tolist()), z["paths"].tolist())
            feats = dict(zip(z["paths"].tolist(), z["feats"].tolist()))
            self.assertEqual(feats[f"{data}/web_moth_photos/inaturalist/CM/1.jpg"], [1.0, 0.0])  # features follow
            self.assertEqual(feats["data/trap_style/v1_webcam_2026-09/photos/CM/a.jpg"], [0.0, 1.0])
            self.assertTrue((data / "real_liners/from_the_web/inat/link.jpg").exists())  # relinked
            self.assertTrue((models / "classifier/bioclip_head/current/head.npz").exists())

            self.assertEqual(rd.undo(data, models), 0)
            after = sorted(str(p.relative_to(ml)) for p in ml.rglob("*") if "old" not in p.relative_to(ml).parts)
            self.assertEqual(after, before)
            self.assertEqual((data / "synth" / "manifest.csv").read_text().splitlines()[1],
                             "data/synth/CM/a.jpg,data/inat/CM/1.jpg")
            self.assertTrue((data / "web_liners" / "inat" / "link.jpg").exists())


if __name__ == "__main__":
    unittest.main()
