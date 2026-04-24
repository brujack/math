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


if __name__ == "__main__":
    unittest.main()
