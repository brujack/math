#!/usr/bin/env python3
"""Unit tests for factorial.py."""

import argparse
import io
import os
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

from factorial import (
    _HAS_GMPY2,
    _gmpy2,
    _sieve,
    _compute_swing,
    _compute_swing_chunk,
    _tree_combine_int,
    calculate_factorial,
    parse_args,
    get_target_n,
    _write_factorial_file,
)

# Known exact factorial values for testing.
FACTORIAL_REF = {
    0: 1, 1: 1, 2: 2, 3: 6, 4: 24,
    5: 120, 10: 3628800, 20: 2432902008176640000,
}


def _quiet_factorial(n):
    """Compute factorial while suppressing stdout."""
    with redirect_stdout(io.StringIO()):
        return calculate_factorial(n)


class TestSieve(unittest.TestCase):

    def test_empty_below_2(self):
        self.assertEqual(_sieve(0), [])
        self.assertEqual(_sieve(1), [])

    def test_n_equals_2(self):
        self.assertEqual(_sieve(2), [2])

    def test_small_known_primes(self):
        self.assertEqual(_sieve(10), [2, 3, 5, 7])

    def test_no_composites(self):
        result = _sieve(20)
        for p in result:
            for d in range(2, p):
                self.assertNotEqual(p % d, 0, f"{p} is not prime")

    def test_prime_count_to_100(self):
        # π(100) = 25
        self.assertEqual(len(_sieve(100)), 25)


class TestComputeSwingChunk(unittest.TestCase):

    def test_empty_prime_chunk(self):
        self.assertEqual(_compute_swing_chunk(10, []), 1)

    def test_prime_greater_than_m_returns_1(self):
        # p=7 > m=5, so no contribution
        self.assertEqual(_compute_swing_chunk(5, [7, 11]), 1)

    def test_swing_of_2_via_chunk(self):
        # p=2, m=2: q=2//2=1, 1%2=1, exp=1 → 2^1=2
        self.assertEqual(_compute_swing_chunk(2, [2]), 2)

    def test_swing_of_4_p2_contribution(self):
        # p=2, m=4: q=4//2=2, 2%2=0; q=2//2=1, 1%2=1 → exp=1 → 2^1=2
        self.assertEqual(_compute_swing_chunk(4, [2]), 2)

    def test_swing_of_6_p2_contribution(self):
        # p=2, m=6: q=6//2=3, 3%2=1, exp++; q=3//2=1, 1%2=1, exp++ → exp=2 → 2^2=4
        self.assertEqual(_compute_swing_chunk(6, [2]), 4)

    def test_swing_of_6_p3_contribution(self):
        # p=3, m=6: q=6//3=2, 2%2=0; q=2//3=0, done → exp=0 → no contribution
        self.assertEqual(_compute_swing_chunk(6, [3]), 1)

    def test_swing_of_6_p5_contribution(self):
        # p=5, m=6: q=6//5=1, 1%2=1 → exp=1 → 5^1=5
        self.assertEqual(_compute_swing_chunk(6, [5]), 5)

    def test_swing_chunk_mixed_primes_some_exceed_m(self):
        # Normal production pattern: chunk contains primes below AND above m.
        # Primes above m should be skipped via the early break.
        # For m=6, primes [2, 3, 5] contribute; 7 and 11 are > m and break early.
        # p=2: q=6->3(odd,+1)->1(odd,+1) -> exp=2, contrib=4
        # p=3: q=6->2(even)->0 -> exp=0, contrib=1
        # p=5: q=6->1(odd,+1) -> exp=1, contrib=5
        # 7 > 6: break. Result = 4 * 1 * 5 = 20.
        self.assertEqual(_compute_swing_chunk(6, [2, 3, 5, 7, 11]), 20)


class TestTreeCombineInt(unittest.TestCase):

    def test_empty_returns_1(self):
        self.assertEqual(_tree_combine_int([]), 1)

    def test_single_element(self):
        self.assertEqual(_tree_combine_int([42]), 42)

    def test_two_elements(self):
        self.assertEqual(_tree_combine_int([3, 7]), 21)

    def test_four_elements_tree_order(self):
        # (2*3) * (5*7) = 6 * 35 = 210
        self.assertEqual(_tree_combine_int([2, 3, 5, 7]), 210)

    def test_odd_length(self):
        # (2*3) * 5 = 30
        self.assertEqual(_tree_combine_int([2, 3, 5]), 30)


class TestComputeSwing(unittest.TestCase):

    def test_swing_0(self):
        # swing(0) = empty product = 1
        primes = _sieve(10)
        self.assertEqual(_compute_swing(0, primes), 1)

    def test_swing_1(self):
        # swing(1) = empty product = 1 (no primes <= 1)
        primes = _sieve(10)
        self.assertEqual(_compute_swing(1, primes), 1)

    def test_swing_2(self):
        # swing(2) = 2 (p=2: q=2->1(odd,+1) -> exp=1)
        primes = _sieve(10)
        self.assertEqual(_compute_swing(2, primes), 2)

    def test_swing_6(self):
        # swing(6) = 20 (p=2: exp=2 -> 4; p=3: exp=0 -> 1; p=5: exp=1 -> 5; 7>6 skip)
        primes = _sieve(10)
        self.assertEqual(_compute_swing(6, primes), 20)

    def test_swing_empty_primes(self):
        # empty primes list returns 1
        self.assertEqual(_compute_swing(100, []), 1)

    def test_swing_returns_int(self):
        # return type must be plain int (not gmpy2.mpz) for later use
        primes = _sieve(10)
        result = _compute_swing(6, primes)
        self.assertIsInstance(result, int)

    def test_swing_four(self):
        # swing(4): p=2 gives exp=1 (4//2=2 even, 2//2=1 odd -> 1), contrib=2;
        # p=3 gives exp=1 (4//3=1 odd -> 1), contrib=3. Result = 2*3 = 6.
        primes = _sieve(10)
        self.assertEqual(_compute_swing(4, primes), 6)

    def test_swing_satisfies_factorial_recursion(self):
        # Core prime swing identity: swing(n) * (n//2)! ** 2 == n!
        # For n=6: swing(6) * 3!^2 == 6!
        # swing(6) = 20, 3! = 6, 6^2 = 36, 20 * 36 = 720 = 6!
        primes = _sieve(10)
        self.assertEqual(_compute_swing(6, primes) * (6) ** 2, 720)


class TestCalculateFactorial(unittest.TestCase):

    def test_factorial_0(self):
        self.assertEqual(int(_quiet_factorial(0)), FACTORIAL_REF[0])

    def test_factorial_1(self):
        self.assertEqual(int(_quiet_factorial(1)), FACTORIAL_REF[1])

    def test_factorial_2(self):
        self.assertEqual(int(_quiet_factorial(2)), FACTORIAL_REF[2])

    def test_factorial_5(self):
        self.assertEqual(int(_quiet_factorial(5)), FACTORIAL_REF[5])

    def test_factorial_10(self):
        self.assertEqual(int(_quiet_factorial(10)), FACTORIAL_REF[10])

    def test_factorial_20(self):
        self.assertEqual(int(_quiet_factorial(20)), FACTORIAL_REF[20])

    def test_factorial_3(self):
        self.assertEqual(int(_quiet_factorial(3)), FACTORIAL_REF[3])

    def test_factorial_4(self):
        self.assertEqual(int(_quiet_factorial(4)), FACTORIAL_REF[4])

    def test_factorial_negative_raises(self):
        with self.assertRaises(ValueError):
            calculate_factorial(-1)

    def test_factorial_returns_mpz_when_gmpy2_available(self):
        """When gmpy2 is installed, calculate_factorial returns gmpy2.mpz."""
        if not _HAS_GMPY2:
            self.skipTest("gmpy2 not installed")
        result = _quiet_factorial(5)
        self.assertIsInstance(result, _gmpy2.mpz)


class TestParseArgs(unittest.TestCase):
    def test_no_args_n_is_none(self):
        args = parse_args([])
        self.assertIsNone(args.n)

    def test_positional_arg(self):
        args = parse_args(["100"])
        self.assertEqual(args.n, 100)

    def test_help_exits(self):
        with self.assertRaises(SystemExit):
            parse_args(["--help"])


class TestGetTargetN(unittest.TestCase):
    def test_from_args(self):
        args = argparse.Namespace(n=42)
        self.assertEqual(get_target_n(args), 42)

    def test_zero_from_args(self):
        args = argparse.Namespace(n=0)
        self.assertEqual(get_target_n(args), 0)

    def test_negative_raises(self):
        args = argparse.Namespace(n=-1)
        with self.assertRaises(ValueError):
            get_target_n(args)

    def test_interactive_valid(self):
        args = argparse.Namespace(n=None)
        with patch("builtins.input", return_value="7"):
            self.assertEqual(get_target_n(args), 7)

    def test_interactive_non_integer_then_valid(self):
        args = argparse.Namespace(n=None)
        with patch("builtins.input", side_effect=["abc", "5"]):
            with patch("builtins.print"):
                self.assertEqual(get_target_n(args), 5)


class TestOutputFile(unittest.TestCase):
    def test_file_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                _write_factorial_file(120, 5)
                self.assertTrue(os.path.exists("factorial_5.txt"))
            finally:
                os.chdir(original_dir)

    def test_filename_correct(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                filename = _write_factorial_file(6, 3)
                self.assertEqual(filename, "factorial_3.txt")
            finally:
                os.chdir(original_dir)

    def test_content_is_digits_string(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("builtins.print"):
                    _write_factorial_file(3628800, 10)
                with open("factorial_10.txt") as f:
                    content = f.read()
                self.assertEqual(content, "3628800")
            finally:
                os.chdir(original_dir)

    def test_idempotent_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("builtins.print"):
                    _write_factorial_file(120, 5)
                    _write_factorial_file(120, 5)
                with open("factorial_5.txt") as f:
                    self.assertEqual(f.read(), "120")
            finally:
                os.chdir(original_dir)


if __name__ == "__main__":
    unittest.main()
