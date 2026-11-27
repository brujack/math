import unittest

import sq


class TestSq(unittest.TestCase):
    def test_label(self):
        with self.assertRaises(ValueError) as cm:
            sq.ok()
        self.assertEqual(str(cm.exception), "bad")
        self.assertTrue(sq.ok())
