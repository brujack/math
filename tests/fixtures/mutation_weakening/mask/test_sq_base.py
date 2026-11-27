import unittest

import sq


class TestSq(unittest.TestCase):
    def test_label(self):
        self.assertEqual(sq.label(), "old")
        self.assertTrue(sq.ok())
