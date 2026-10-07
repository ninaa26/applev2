"""python -m unittest discover ml/tests   (needs numpy + pillow only)"""

import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import train_v2  # noqa: E402


def stripes(w=400, h=300) -> Image.Image:
    a = np.zeros((h, w, 3), np.uint8)
    a[:, ::2] = 255  # 1 px stripes: the detail a small crop can't hold
    return Image.fromarray(a)


class MixRes(unittest.TestCase):
    def test_keeps_size_and_loses_detail(self):
        im = stripes()
        out = train_v2.MixRes(sides=(48, 48), p=1.0, seed=0)(im)
        self.assertEqual(out.size, im.size)
        self.assertLess(np.asarray(out).std(), np.asarray(im).std() / 4)

    def test_leaves_small_photos_and_the_unlucky_half_alone(self):
        im = stripes(100, 80)
        self.assertIs(train_v2.MixRes(sides=(160, 160), p=1.0, seed=0)(im), im)
        big = stripes()
        self.assertIs(train_v2.MixRes(p=0.0, seed=0)(big), big)


if __name__ == "__main__":
    unittest.main()
