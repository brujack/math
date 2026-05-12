import argparse
import array
import io
import os
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout

from collatz import (
    collatz_next,
    collatz_length,
    generate_records,
    get_exponent,
    main,
    parse_args,
)


class TestCollatzNext(unittest.TestCase):
    def test_even_input(self):
        self.assertEqual(collatz_next(6), 3)

    def test_odd_input(self):
        self.assertEqual(collatz_next(3), 10)

    def test_n2_yields_1(self):
        self.assertEqual(collatz_next(2), 1)


if __name__ == "__main__":
    unittest.main()
