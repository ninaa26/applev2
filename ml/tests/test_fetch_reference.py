"""python -m unittest discover ml/tests   (needs numpy + pillow only)"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fetch_reference import gbif_license, image_kind  # noqa: E402


class GbifLicense(unittest.TestCase):
    def test_urls_and_short_names(self):
        cases = {
            "http://creativecommons.org/licenses/by-nc/4.0/": "cc-by-nc",
            "https://creativecommons.org/licenses/by-nc-sa/3.0/legalcode": "cc-by-nc-sa",
            "http://creativecommons.org/publicdomain/zero/1.0/legalcode": "cc0",
            "CC_BY_4_0": "cc-by",
            "CC BY-NC 4.0": "cc-by-nc",
            "": "",
            "All rights reserved": "",
        }
        for given, want in cases.items():
            self.assertEqual(gbif_license(given), want, given)


class ImageKind(unittest.TestCase):
    def test_pictures_and_error_pages(self):
        self.assertEqual(image_kind(b"\xff\xd8\xff\xe0rest"), ".jpg")
        self.assertEqual(image_kind(b"\x89PNG\r\n"), ".png")
        self.assertEqual(image_kind(b"GIF89a..."), ".gif")
        self.assertEqual(image_kind(b"RIFF\x00\x00\x00\x00WEBPVP8 "), ".webp")
        self.assertEqual(image_kind(b"<!DOCTYPE html>"), "")
        self.assertEqual(image_kind(b""), "")


if __name__ == "__main__":
    unittest.main()
