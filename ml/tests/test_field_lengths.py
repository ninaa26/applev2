"""python -m unittest discover ml/tests   (needs numpy + pillow only)"""

import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import field_lengths as fl  # noqa: E402


def moth(length=200, width=60, angle=0.0, legs=False, size=400) -> np.ndarray:
    """A filled ellipse `length` px long at `angle` degrees, optionally with thin legs and antennae."""
    im = Image.new("L", (size, size), 0)
    ImageDraw.Draw(im).ellipse((size / 2 - length / 2, size / 2 - width / 2, size / 2 + length / 2, size / 2 + width / 2), fill=255)
    if legs:
        d = ImageDraw.Draw(im)
        c = size / 2
        d.line((c + length / 2 - 5, c, c + length / 2 + 60, c - 30), fill=255, width=3)  # antenna past the head
        d.line((c + length / 2 - 5, c, c + length / 2 + 60, c + 30), fill=255, width=3)
        for x in (-40, 0, 40):
            d.line((c + x, c, c + x + 10, c + width / 2 + 40), fill=255, width=3)  # legs out to the side
    return np.asarray(im.rotate(angle, resample=Image.NEAREST)) > 127


class LongSide(unittest.TestCase):
    def test_axis_aligned_rectangle(self):
        m = np.zeros((50, 80), bool)
        m[10:20, 5:65] = True
        self.assertAlmostEqual(fl.long_side_px(m), 60, delta=0.5)

    def test_diagonal_insect_is_not_its_box(self):
        m = moth(200, 60, angle=45)
        ys, xs = np.nonzero(m)
        box_long = max(np.ptp(xs), np.ptp(ys)) + 1
        self.assertLess(box_long / 200, 0.8)  # the old measure: a slim insect at 45 degrees comes out short
        self.assertAlmostEqual(fl.long_side_px(m), 200, delta=4)

    def test_empty_and_single_pixel(self):
        self.assertEqual(fl.long_side_px(np.zeros((5, 5), bool)), 0.0)
        m = np.zeros((5, 5), bool)
        m[2, 3] = True
        self.assertEqual(fl.long_side_px(m), 1.0)


class Body(unittest.TestCase):
    def test_legs_and_antennae_are_trimmed(self):
        for angle in (0, 30, 90, 135):
            with self.subTest(angle=angle):
                m = moth(200, 60, angle=angle, legs=True)
                self.assertGreater(fl.long_side_px(m), 240)  # the antennae make the outline longer
                self.assertAlmostEqual(fl.body_px(m), 200, delta=200 * 0.12)  # tapering ends lose a bit

    def test_plain_body_loses_little(self):
        self.assertGreater(fl.body_px(moth(200, 60)), 200 * 0.85)


class Measure(unittest.TestCase):
    def test_outline_used_when_it_fills_the_box(self):
        m = moth(200, 60, angle=45)
        ys, xs = np.nonzero(m)
        crop = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        box = (100, 100, 100 + crop.shape[1], 100 + crop.shape[0])
        got = fl.measure(crop, box, ppm=10.0)
        self.assertEqual(got["length_from"], "outline")
        self.assertAlmostEqual(float(got["length_mm"]), 20.0, delta=0.5)
        self.assertLessEqual(float(got["body_mm"]), float(got["length_mm"]))

    def test_box_when_no_outline_or_a_fragment(self):
        box = (0, 0, 100, 40)
        for mask in (None, np.zeros((40, 100), bool)):
            self.assertEqual(fl.measure(mask, box, 10.0), {"length_mm": "10.0", "body_mm": "", "length_from": "box"})
        frag = np.zeros((40, 100), bool)
        frag[10:30, 40:60] = True  # 10% of the box: a wing patch, not the insect
        self.assertEqual(fl.measure(frag, box, 10.0)["length_from"], "box")
        short = np.zeros((40, 100), bool)
        short[:, 30:70] = True  # fills 40% but spans only 40 of 100 px
        self.assertEqual(fl.measure(short, box, 10.0)["length_from"], "box")

    def test_no_grid_gives_blank_lengths(self):
        m = np.ones((40, 100), bool)
        self.assertEqual(fl.measure(m, (0, 0, 100, 40), None), {"length_mm": "", "body_mm": "", "length_from": "outline"})
        self.assertEqual(fl.measure(None, (0, 0, 100, 40), None)["length_mm"], "")


class ScaleWarning(unittest.TestCase):
    def test_plausible_card_is_quiet(self):
        self.assertIsNone(fl.scale_warning([2.0, 3.0, 4.0, 9.0, 10.0, 12.0, 14.0]))

    def test_grid_locked_on_every_third_line(self):
        self.assertIn("grid scale", fl.scale_warning([x / 3 for x in (2.0, 3.0, 4.0, 9.0, 10.0, 12.0, 14.0)]))

    def test_too_big_and_too_few(self):
        self.assertIsNotNone(fl.scale_warning([30.0, 35.0, 40.0]))
        self.assertIsNone(fl.scale_warning([1.0, 1.0]))


if __name__ == "__main__":
    unittest.main()
