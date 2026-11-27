# pyright: reportAttributeAccessIssue=false
# The canary copies this file beside its own sq.py; root pyright resolves `sq` to sq/sq.py instead.
import unittest

import sq


class TestSq(unittest.TestCase):
    def test_label(self):
        with self.assertRaises(ValueError):
            sq.ok()
        self.assertTrue(sq.ok())
