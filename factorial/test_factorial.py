#!/usr/bin/env python3
"""Unit tests for factorial.py."""

import io
import os
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(__file__))

import factorial as fac_module
from factorial import (
    _HAS_GMPY2,
    _sieve,
    _compute_swing_chunk,
    _tree_combine_int,
    _write_factorial_file,
    calculate_factorial,
    get_target_n,
    parse_args,
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


if __name__ == "__main__":
    unittest.main()
