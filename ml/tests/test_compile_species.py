"""python -m unittest discover ml/tests   (needs numpy + pillow only)"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compile_species import photo_key  # noqa: E402


class PhotoKey(unittest.TestCase):
    def test_one_name_per_photo(self):
        # iNaturalist: any size, either host, is the photo number
        self.assertEqual(photo_key("https://inaturalist-open-data.s3.amazonaws.com/photos/738247218/medium.jpg"),
                         "inat:738247218")
        self.assertEqual(photo_key("https://static.inaturalist.org/photos/738247218/original.jpg"), "inat:738247218")
        # SCAN's old address, http or :443, and Symbiota's _lg size are the same museum photo
        a = photo_key("https://scan-bugs.org:443/imglib/scan/MISSA_MEM/MEM348/MEM348500_x_1527732238_lg.jpg")
        b = photo_key("http://media01.symbiota.org/media/scan/MISSA_MEM/MEM348/MEM348500_x_1527732238.jpg")
        self.assertEqual(a, b)
        self.assertNotEqual(photo_key("https://bugwoodcloud.org/images/768x512/1.jpg"),
                            photo_key("https://bugwoodcloud.org/images/768x512/2.jpg"))


if __name__ == "__main__":
    unittest.main()
