"""python -m unittest discover ml/tests   (needs numpy + pillow only)"""

import random
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import export_server_crops  # noqa: E402
import make_trap_style as ts  # noqa: E402


def fake_moth(w=300, h=100) -> Image.Image:
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((0, 0, w - 1, h - 1), fill=(60, 50, 40, 255))
    return im


class TrapStyle(unittest.TestCase):
    def setUp(self):
        liner = np.full((480, 640, 3), (230, 120, 40), np.float32)  # orange-lit blank liner
        liner[:, ::90] = (120, 50, 20)  # grid lines
        self.liners = [("liner.jpg", liner)]

    def test_moth_is_trap_sized_and_centred(self):
        rng = random.Random(1)
        for _ in range(20):
            img, meta = ts.paste_moth(rng, fake_moth(), "CM", self.liners)
            ppm, length = float(meta["ppm"]), float(meta["length_mm"])
            self.assertTrue(ts.PPM[0] <= ppm <= ts.PPM[1] and 9 <= length <= 11)
            # square crop around a moth of length*ppm px with the server's padding (+ jitter)
            self.assertEqual(img.width, img.height)
            self.assertLess(img.width, length * ppm * (1 + 2 * ts.PAD) * 1.25 + 4)
            a = np.asarray(img, dtype=np.float32)
            c = img.width // 2
            centre = a[c - 2:c + 3, c - 2:c + 3].mean()
            self.assertLess(centre, a.mean())  # the dark moth is in the middle

    def test_moth_takes_the_liners_light(self):
        img, _ = ts.paste_moth(random.Random(2), fake_moth(), "OBLR", self.liners)
        r, g, b = np.asarray(img, dtype=np.float32).reshape(-1, 3).mean(0)
        self.assertGreater(r, g)
        self.assertGreater(g, b)

    def test_debris_is_bare_liner(self):
        img, meta = ts.debris_crop(random.Random(3), self.liners)
        self.assertEqual(meta["length_mm"], "")
        self.assertEqual(img.width, img.height)


class ExportServerCrops(unittest.TestCase):
    def test_reviewed_and_empty_card_detections(self):
        with tempfile.TemporaryDirectory() as tmp:
            server, data = Path(tmp) / "server", Path(tmp) / "data"
            (server / "media" / "T1").mkdir(parents=True)
            Image.new("RGB", (640, 480), "orange").save(server / "media" / "T1" / "a.jpg")
            db = sqlite3.connect(server / "sentinel.db")
            db.executescript("""
                CREATE TABLE cards (id INTEGER, trap_id TEXT, installed_at TEXT);
                CREATE TABLE captures (id INTEGER, card_id INTEGER, image_path TEXT);
                CREATE TABLE tracks (id INTEGER, review_status TEXT, reviewed_label TEXT);
                CREATE TABLE detections (id INTEGER, capture_id INTEGER, track_id INTEGER,
                                         x1 REAL, y1 REAL, x2 REAL, y2 REAL);
                INSERT INTO cards VALUES (1, 'T1', '2026-09-24 16:50:35.7'), (2, 'T1', '2026-10-01 09:00:00');
                INSERT INTO captures VALUES (1, 1, 'T1/a.jpg'), (2, 2, 'T1/a.jpg');
                INSERT INTO tracks VALUES (1, 'confirmed', 'OFM'), (2, 'rejected', NULL), (3, 'review', NULL);
                INSERT INTO detections VALUES
                    (1, 1, 1, 100, 100, 160, 120),
                    (2, 1, 2, 300, 300, 340, 330),
                    (3, 1, 3, 400, 100, 450, 130),
                    (4, 2, NULL, 200, 200, 240, 230),
                    (5, 1, 1, 10, 10, 15, 15);
            """)
            db.commit()
            db.close()
            export_server_crops.main(["--server", str(server), "--data", str(data),
                                      "--empty-card", "T1-20261001T0900"])
            got = sorted(str(p.relative_to(data / "own")) for p in (data / "own").rglob("*.jpg"))
            self.assertEqual(got, ["OFM/T1-20260924T1650/a_d1.jpg",        # confirmed
                                   "debris/T1-20260924T1650/a_d2.jpg",     # rejected
                                   "debris/T1-20261001T0900/a_d4.jpg"])    # empty card; d3 unreviewed, d5 tiny
            with Image.open(data / "own" / "OFM" / "T1-20260924T1650" / "a_d1.jpg") as im:
                self.assertEqual(im.size, (102, 102))  # 60 px box, padded 0.35 each side, square


if __name__ == "__main__":
    unittest.main()
