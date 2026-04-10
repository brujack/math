#!/usr/bin/env python3
"""Unit tests for fib.py."""

import argparse
import sys
import unittest

from fib import generate_fibonacci, parse_args, get_exponent


class TestGenerateFibonacci(unittest.TestCase):

    def test_single_digit_sequence(self):
        # max_digits=1, limit=10^1=10: yields 1,1,2,3,5,8 (all < 10); 13 >= 10 stops
        result = list(generate_fibonacci(1))
        self.assertEqual(result, [1, 1, 2, 3, 5, 8])

    def test_count_single_digit(self):
        self.assertEqual(len(list(generate_fibonacci(1))), 6)

    def test_count_two_digits(self):
        # max_digits=2, limit=100: 1,1,2,3,5,8,13,21,34,55,89 (11 total); 144 >= 100 stops
        self.assertEqual(len(list(generate_fibonacci(2))), 11)

    def test_last_two_digit_value(self):
        result = list(generate_fibonacci(2))
        self.assertEqual(result[-1], 89)

    def test_three_digit_excluded(self):
        result = list(generate_fibonacci(2))
        self.assertNotIn(144, result)

    def test_each_is_sum_of_previous_two(self):
        result = list(generate_fibonacci(3))
        for i in range(2, len(result)):
            self.assertEqual(result[i], result[i - 1] + result[i - 2])

    def test_all_positive(self):
        result = list(generate_fibonacci(2))
        self.assertTrue(all(n > 0 for n in result))

    def test_known_first_ten_values(self):
        result = list(generate_fibonacci(2))
        self.assertEqual(result[:10], [1, 1, 2, 3, 5, 8, 13, 21, 34, 55])

    def test_max_digits_zero_empty(self):
        # max_digits=0: limit=10^0=1, b=1, 1<1 is False → yields nothing
        result = list(generate_fibonacci(0))
        self.assertEqual(result, [])


class TestParseArgs(unittest.TestCase):

    def test_no_args(self):
        old_argv = sys.argv
        sys.argv = ["fib.py"]
        args = parse_args()
        sys.argv = old_argv
        self.assertIsNone(args.exponent)

    def test_with_valid_arg(self):
        old_argv = sys.argv
        sys.argv = ["fib.py", "3"]
        args = parse_args()
        sys.argv = old_argv
        self.assertEqual(args.exponent, 3)

    def test_invalid_non_integer_arg_exits(self):
        old_argv = sys.argv
        sys.argv = ["fib.py", "abc"]
        try:
            with self.assertRaises(SystemExit):
                parse_args()
        finally:
            sys.argv = old_argv


class TestGetExponent(unittest.TestCase):

    def _args(self, exponent):
        return argparse.Namespace(exponent=exponent)

    def test_valid_low_boundary(self):
        self.assertEqual(get_exponent(self._args(1)), 1)

    def test_valid_high_boundary(self):
        self.assertEqual(get_exponent(self._args(5)), 5)

    def test_valid_midrange(self):
        self.assertEqual(get_exponent(self._args(3)), 3)

    def test_zero_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._args(0))

    def test_too_high_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._args(6))

    def test_negative_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._args(-1))


if __name__ == "__main__":
    unittest.main()
