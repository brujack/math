import unittest

import sq


class TestSq(unittest.TestCase):
    def test_label(self):
        with self.assertRaises(ValueError):
            sq.ok()
        self.assertTrue(sq.ok())
