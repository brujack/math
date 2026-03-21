#!/usr/bin/env python3
"""
Unit tests for pi.py.

Run with:
    python -m pytest test_pi.py -v
or:
    python -m unittest test_pi -v

gmpy2-dependent tests are skipped automatically when gmpy2 is not installed.
"""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

# Ensure the pi module is importable from this directory.
sys.path.insert(0, os.path.dirname(__file__))

import pi as pi_module
from pi import (
    _HAS_GMPY2,
    _CHU_A,
    _CHU_B,
    _CHU_C3_OVER_24,
    _tree_combine,
    _pwrite_all,
    _pi_to_str,
    calculate_pi_high_precision,
)

# Known decimal expansion of π — used for accuracy assertions.
PI_REF = "3.14159265358979323846264338327950288419716939937510"


def _quiet_pi(digits):
    """Compute π while suppressing the progress prints to stdout."""
    with redirect_stdout(io.StringIO()):
        return calculate_pi_high_precision(digits)


# ---------------------------------------------------------------------------
# _tree_combine
# ---------------------------------------------------------------------------

class TestTreeCombine(unittest.TestCase):
    """Tests for _tree_combine (pure Python, no gmpy2 dependency)."""

    @staticmethod
    def _merge(l, r):
        Pl, Ql, Tl = l
        Pr, Qr, Tr = r
        return Pl * Pr, Ql * Qr, Qr * Tl + Pl * Tr

    def test_single_element(self):
        pqt = (1, 2, 3)
        self.assertEqual(_tree_combine([pqt]), pqt)

    def test_two_elements(self):
        a = (2, 3, 5)
        b = (7, 11, 13)
        expected = self._merge(a, b)
        self.assertEqual(_tree_combine([a, b]), expected)

    def test_four_elements_tree_order(self):
        """tree_combine pairs (0,1) and (2,3) before combining the pairs."""
        chunks = [(1, 1, 1), (2, 3, 5), (7, 11, 13), (17, 19, 23)]
        m01 = self._merge(chunks[0], chunks[1])
        m23 = self._merge(chunks[2], chunks[3])
        expected = self._merge(m01, m23)
        self.assertEqual(_tree_combine(list(chunks)), expected)

    def test_odd_length_passthrough(self):
        """With 3 elements, the last passes through level 1 unmerged."""
        chunks = [(1, 1, 1), (2, 3, 5), (7, 11, 13)]
        m01 = self._merge(chunks[0], chunks[1])
        expected = self._merge(m01, chunks[2])
        self.assertEqual(_tree_combine(list(chunks)), expected)

    def test_large_input_deterministic(self):
        """16-element reduction is stable across calls."""
        chunks = [(i + 1, i + 2, i + 3) for i in range(16)]
        result_a = _tree_combine(list(chunks))
        result_b = _tree_combine(list(chunks))
        self.assertEqual(result_a, result_b)

    def test_identity_with_known_values(self):
        """Combine formula: T(a,b) = Qr*Tl + Pl*Tr."""
        # Pl=2, Ql=3, Tl=5, Pr=7, Qr=11, Tr=13
        # T_expected = 11*5 + 2*13 = 55 + 26 = 81
        result = _tree_combine([(2, 3, 5), (7, 11, 13)])
        self.assertEqual(result[2], 81)
        self.assertEqual(result[0], 14)   # Pl*Pr = 2*7
        self.assertEqual(result[1], 33)   # Ql*Qr = 3*11


# ---------------------------------------------------------------------------
# _pwrite_all
# ---------------------------------------------------------------------------

class TestPwriteAll(unittest.TestCase):
    """Tests for _pwrite_all (POSIX pwrite wrapper)."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(delete=False)
        self._path = self._tmp.name
        self._tmp.close()

    def tearDown(self):
        os.unlink(self._path)

    def _open_rw(self):
        return os.open(self._path, os.O_RDWR | os.O_CREAT, 0o644)

    def test_writes_at_correct_offset(self):
        fd = self._open_rw()
        try:
            os.ftruncate(fd, 20)
            _pwrite_all(fd, b"hello", 5)
            _pwrite_all(fd, b"world", 10)
        finally:
            os.close(fd)
        with open(self._path, "rb") as f:
            data = f.read()
        self.assertEqual(data[5:10], b"hello")
        self.assertEqual(data[10:15], b"world")

    def test_returns_byte_count(self):
        fd = self._open_rw()
        try:
            os.ftruncate(fd, 10)
            n = _pwrite_all(fd, b"abc", 0)
        finally:
            os.close(fd)
        self.assertEqual(n, 3)

    def test_empty_data_returns_zero(self):
        fd = self._open_rw()
        try:
            os.ftruncate(fd, 10)
            n = _pwrite_all(fd, b"", 0)
        finally:
            os.close(fd)
        self.assertEqual(n, 0)

    def test_does_not_move_file_pointer(self):
        """Sequential pwrite calls at different offsets must not interfere."""
        fd = self._open_rw()
        try:
            os.ftruncate(fd, 30)
            _pwrite_all(fd, b"AAA", 0)
            _pwrite_all(fd, b"BBB", 10)
            _pwrite_all(fd, b"CCC", 20)
        finally:
            os.close(fd)
        with open(self._path, "rb") as f:
            data = f.read()
        self.assertEqual(data[0:3],   b"AAA")
        self.assertEqual(data[10:13], b"BBB")
        self.assertEqual(data[20:23], b"CCC")


# ---------------------------------------------------------------------------
# _chudnovsky_bs — requires gmpy2
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
class TestChudnovskyBS(unittest.TestCase):
    """Tests for _chudnovsky_bs (requires gmpy2)."""

    def setUp(self):
        from pi import _chudnovsky_bs
        self.bs = _chudnovsky_bs

    def test_leaf_a0_values(self):
        """Leaf at a=0: P=1, Q=1, T=CHU_A (the series constant)."""
        P, Q, T = self.bs(0, 1)
        self.assertEqual(int(P), 1)
        self.assertEqual(int(Q), 1)
        self.assertEqual(int(T), _CHU_A)

    def test_leaf_a1_P(self):
        """P at a=1: (6·1−5)(2·1−1)(6·1−1) = 1·1·5 = 5."""
        P, _, _ = self.bs(1, 2)
        self.assertEqual(int(P), 5)

    def test_leaf_a1_Q(self):
        """Q at a=1: 1³ × C³/24 = CHU_C3_OVER_24."""
        _, Q, _ = self.bs(1, 2)
        self.assertEqual(int(Q), _CHU_C3_OVER_24)

    def test_leaf_a1_T(self):
        """T at a=1: −P·(A + B·1) — negative because a=1 is odd."""
        _, _, T = self.bs(1, 2)
        self.assertEqual(int(T), -(5 * (_CHU_A + _CHU_B)))

    def test_odd_leaf_negative(self):
        """Odd-indexed leaf terms are negated."""
        _, _, T = self.bs(1, 2)
        self.assertLess(int(T), 0)

    def test_even_leaf_positive(self):
        """Even-indexed (non-zero) leaf terms are positive."""
        _, _, T = self.bs(2, 3)
        self.assertGreater(int(T), 0)

    def test_split_consistency(self):
        """bs(0, 4) equals manually merging bs(0, 2) and bs(2, 4)."""
        P_full, Q_full, T_full = self.bs(0, 4)
        Pl, Ql, Tl = self.bs(0, 2)
        Pr, Qr, Tr = self.bs(2, 4)
        self.assertEqual(int(P_full), int(Pl * Pr))
        self.assertEqual(int(Q_full), int(Ql * Qr))
        self.assertEqual(int(T_full), int(Qr * Tl + Pl * Tr))

    def test_larger_range_consistency(self):
        """bs(0, 8) equals merging bs(0, 4) and bs(4, 8)."""
        P_full, Q_full, T_full = self.bs(0, 8)
        Pl, Ql, Tl = self.bs(0, 4)
        Pr, Qr, Tr = self.bs(4, 8)
        self.assertEqual(int(P_full), int(Pl * Pr))
        self.assertEqual(int(Q_full), int(Ql * Qr))
        self.assertEqual(int(T_full), int(Qr * Tl + Pl * Tr))


# ---------------------------------------------------------------------------
# _bs_chunk_worker — requires gmpy2
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
class TestBsChunkWorker(unittest.TestCase):
    """Tests for _bs_chunk_worker (requires gmpy2)."""

    def setUp(self):
        from pi import _bs_chunk_worker, _chudnovsky_bs
        self.worker = _bs_chunk_worker
        self.bs = _chudnovsky_bs

    def test_returns_plain_python_ints(self):
        """Must return plain int, not gmpy2.mpz — ensures picklability."""
        P, Q, T = self.worker(0, 10)
        self.assertIsInstance(P, int)
        self.assertIsInstance(Q, int)
        self.assertIsInstance(T, int)

    def test_values_match_chudnovsky_bs(self):
        """Results must be numerically identical to _chudnovsky_bs."""
        P_w, Q_w, T_w = self.worker(0, 20)
        P_bs, Q_bs, T_bs = self.bs(0, 20)
        self.assertEqual(P_w, int(P_bs))
        self.assertEqual(Q_w, int(Q_bs))
        self.assertEqual(T_w, int(T_bs))

    def test_non_zero_range(self):
        """Worker handles mid-series ranges correctly."""
        P, Q, T = self.worker(10, 20)
        P_bs, Q_bs, T_bs = self.bs(10, 20)
        self.assertEqual(P, int(P_bs))
        self.assertEqual(Q, int(Q_bs))
        self.assertEqual(T, int(T_bs))


# ---------------------------------------------------------------------------
# _pi_to_str output format
# ---------------------------------------------------------------------------

class TestPiToStr(unittest.TestCase):
    """Tests for _pi_to_str: format, length, and known-digit checks."""

    @classmethod
    def setUpClass(cls):
        cls._pi50 = _quiet_pi(50)

    def test_starts_with_3_dot(self):
        result = _pi_to_str(self._pi50, 10)
        self.assertTrue(result.startswith("3."), f"Expected '3.' prefix, got: {result!r}")

    def test_no_exponent_notation(self):
        result = _pi_to_str(self._pi50, 10)
        self.assertNotIn("e", result.lower())

    def test_exactly_n_decimal_places(self):
        for digits in (10, 20, 50):
            with self.subTest(digits=digits):
                result = _pi_to_str(self._pi50, digits)
                _, dec = result.split(".")
                self.assertEqual(len(dec), digits)

    def test_known_10_digits(self):
        result = _pi_to_str(self._pi50, 10)
        self.assertEqual(result, PI_REF[:12])  # "3." + 10 digits

    def test_known_20_digits(self):
        result = _pi_to_str(self._pi50, 20)
        self.assertEqual(result, PI_REF[:22])

    def test_known_50_digits(self):
        result = _pi_to_str(self._pi50, 50)
        self.assertEqual(result, PI_REF)


# ---------------------------------------------------------------------------
# calculate_pi_high_precision — end-to-end accuracy
# ---------------------------------------------------------------------------

class TestPiAccuracy(unittest.TestCase):
    """End-to-end accuracy tests against the known decimal expansion of π."""

    def _assert_correct(self, digits):
        pi_val = _quiet_pi(digits)
        pi_str = _pi_to_str(pi_val, digits)
        expected = PI_REF[:digits + 2]  # "3." + digits chars
        self.assertEqual(pi_str, expected,
                         f"π to {digits} digits incorrect: {pi_str!r}")

    def test_10_digits(self):
        self._assert_correct(10)

    def test_20_digits(self):
        self._assert_correct(20)

    def test_50_digits(self):
        self._assert_correct(50)

    def test_result_is_not_none(self):
        result = _quiet_pi(10)
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
