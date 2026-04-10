#!/usr/bin/env python3
"""Unit tests for sq.py."""

import argparse
import sys
import unittest

from sq import generate_squares, parse_args, get_exponent


class TestGenerateSquares(unittest.TestCase):

    def test_zero_max_digits_empty(self):
        # max_digits=0: limit=10^0=1, k=1, k*k=1 >= 1 → yields nothing
        self.assertEqual(list(generate_squares(0)), [])

    def test_one_digit_squares(self):
        # max_digits=1: limit=10, yields 1, 4, 9 then 16 >= 10 stops
        self.assertEqual(list(generate_squares(1)), [1, 4, 9])

    def test_two_digit_count(self):
        # max_digits=2: limit=100, k=1..9 (9^2=81 < 100, 10^2=100 >= 100)
        self.assertEqual(len(list(generate_squares(2))), 9)

    def test_two_digit_last_value(self):
        result = list(generate_squares(2))
        self.assertEqual(result[-1], 81)

    def test_two_digit_excludes_100(self):
        result = list(generate_squares(2))
        self.assertNotIn(100, result)

    def test_each_is_perfect_square(self):
        import math
        for sq in generate_squares(3):
            root = math.isqrt(sq)
            self.assertEqual(root * root, sq)

    def test_strictly_increasing(self):
        result = list(generate_squares(3))
        for i in range(1, len(result)):
            self.assertGreater(result[i], result[i - 1])

    def test_ten_digit_count(self):
        # max_digits=10: k=1..99999 → exactly 99,999 squares
        self.assertEqual(sum(1 for _ in generate_squares(10)), 99_999)

    def test_ten_digit_last_value(self):
        # Last square: 99999^2 = 9,999,800,001
        result = list(generate_squares(10))
        self.assertEqual(result[-1], 99_999 * 99_999)

    def test_ten_digit_excludes_100000_squared(self):
        result = list(generate_squares(10))
        self.assertNotIn(100_000 * 100_000, result)


class TestParseArgs(unittest.TestCase):

    def test_no_args(self):
        old_argv = sys.argv
        sys.argv = ["sq.py"]
        args = parse_args()
        sys.argv = old_argv
        self.assertIsNone(args.exponent)

    def test_with_valid_arg(self):
        old_argv = sys.argv
        sys.argv = ["sq.py", "1"]
        args = parse_args()
        sys.argv = old_argv
        self.assertEqual(args.exponent, 1)

    def test_invalid_non_integer_exits(self):
        old_argv = sys.argv
        sys.argv = ["sq.py", "abc"]
        try:
            with self.assertRaises(SystemExit):
                parse_args()
        finally:
            sys.argv = old_argv


class TestGetExponent(unittest.TestCase):

    def _args(self, exponent):
        return argparse.Namespace(exponent=exponent)

    def test_valid_value(self):
        self.assertEqual(get_exponent(self._args(1)), 1)

    def test_zero_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._args(0))

    def test_too_high_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._args(2))

    def test_negative_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._args(-1))


if __name__ == "__main__":
    unittest.main()
