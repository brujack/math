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
import unittest.mock
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
    _gmpy2_str_from_QT,
    _gmpy2_mpfr_to_str,
    _convert_gmpy2_worker,
    _convert_mpmath_worker,
    show_pi_preview,
    save_pi_to_file,
    get_target_digits,
    parse_args,
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
    def _merge(left, r):
        Pl, Ql, Tl = left
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

    def test_empty_list_raises(self):
        # No elements to combine: pqt_list[0] raises IndexError.
        with self.assertRaises(IndexError):
            _tree_combine([])

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


# ---------------------------------------------------------------------------
# _pwrite_all — stall error branch
# ---------------------------------------------------------------------------

class TestPwriteAllStall(unittest.TestCase):
    """_pwrite_all must raise OSError when os.pwrite returns 0."""

    def test_raises_on_stall(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
            try:
                os.ftruncate(fd, 10)
                with unittest.mock.patch("pi.os.pwrite", return_value=0):
                    with self.assertRaises(OSError):
                        _pwrite_all(fd, b"hello", 0)
            finally:
                os.close(fd)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# _gmpy2_str_from_QT and _gmpy2_mpfr_to_str — requires gmpy2
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
class TestGmpy2Conversions(unittest.TestCase):
    """Tests for _gmpy2_str_from_QT and _gmpy2_mpfr_to_str."""

    @classmethod
    def setUpClass(cls):
        # Compute Q and T once for all tests in this class.
        from pi import _chudnovsky_bs
        _, Q, T = _chudnovsky_bs(0, 50)
        cls._Q = int(Q)
        cls._T = int(T)

    def test_str_from_qt_starts_with_3_dot(self):
        result = _gmpy2_str_from_QT(self._Q, self._T, 10)
        self.assertTrue(result.startswith("3."))

    def test_str_from_qt_correct_digits(self):
        result = _gmpy2_str_from_QT(self._Q, self._T, 20)
        self.assertEqual(result, PI_REF[:22])

    def test_str_from_qt_decimal_place_count(self):
        for digits in (10, 20, 50):
            with self.subTest(digits=digits):
                result = _gmpy2_str_from_QT(self._Q, self._T, digits)
                _, dec = result.split(".")
                self.assertEqual(len(dec), digits)

    def test_mpfr_to_str_correct_digits(self):
        import gmpy2
        prec = int(20 * 3.3219280948873626) + 100
        ctx = gmpy2.get_context()
        ctx.precision = prec
        sqrt_10005 = gmpy2.sqrt(gmpy2.mpfr(10005))
        pi_mpfr = (gmpy2.mpfr(426880) * sqrt_10005
                   * gmpy2.mpfr(self._Q) / gmpy2.mpfr(self._T))
        result = _gmpy2_mpfr_to_str(pi_mpfr, 20)
        self.assertEqual(result, PI_REF[:22])

    def test_mpfr_to_str_decimal_count(self):
        import gmpy2
        prec = int(10 * 3.3219280948873626) + 100
        ctx = gmpy2.get_context()
        ctx.precision = prec
        sqrt_10005 = gmpy2.sqrt(gmpy2.mpfr(10005))
        pi_mpfr = (gmpy2.mpfr(426880) * sqrt_10005
                   * gmpy2.mpfr(self._Q) / gmpy2.mpfr(self._T))
        result = _gmpy2_mpfr_to_str(pi_mpfr, 10)
        _, dec = result.split(".")
        self.assertEqual(len(dec), 10)


# ---------------------------------------------------------------------------
# _convert_gmpy2_worker and _convert_mpmath_worker
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
class TestConvertGmpy2Worker(unittest.TestCase):
    """_convert_gmpy2_worker returns the same string as _gmpy2_str_from_QT."""

    @classmethod
    def setUpClass(cls):
        from pi import _chudnovsky_bs
        _, Q, T = _chudnovsky_bs(0, 50)
        cls._Q = int(Q)
        cls._T = int(T)

    def test_returns_string(self):
        result = _convert_gmpy2_worker(self._Q, self._T, 10)
        self.assertIsInstance(result, str)

    def test_matches_str_from_qt(self):
        result = _convert_gmpy2_worker(self._Q, self._T, 20)
        expected = _gmpy2_str_from_QT(self._Q, self._T, 20)
        self.assertEqual(result, expected)


class TestConvertMpmathWorker(unittest.TestCase):
    """_convert_mpmath_worker returns a correctly formatted string."""

    @classmethod
    def setUpClass(cls):
        import mpmath
        mpmath.mp.dps = 60
        cls._pi_mpf = mpmath.pi

    def test_returns_string(self):
        result = _convert_mpmath_worker(self._pi_mpf, 10)
        self.assertIsInstance(result, str)

    def test_starts_with_3_dot(self):
        result = _convert_mpmath_worker(self._pi_mpf, 10)
        self.assertTrue(result.startswith("3."))

    def test_correct_leading_digits(self):
        result = _convert_mpmath_worker(self._pi_mpf, 10)
        # mpmath.nstr rounds to nearest — compare only the first 9 digits
        # (digit 10 is ambiguous due to rounding of the trailing digits).
        self.assertEqual(result[:10], PI_REF[:10])


# ---------------------------------------------------------------------------
# mpmath fallback path in calculate_pi_high_precision
# ---------------------------------------------------------------------------

class TestMpmathFallback(unittest.TestCase):
    """When gmpy2 is unavailable, calculate_pi_high_precision uses mpmath."""

    def test_fallback_returns_correct_digits(self):
        with unittest.mock.patch.object(pi_module, "_HAS_GMPY2", False):
            pi_val = _quiet_pi(20)
        # mpmath.mpf — _pi_to_str dispatches to mpmath.nstr
        with unittest.mock.patch.object(pi_module, "_HAS_GMPY2", False):
            result = _pi_to_str(pi_val, 20)
        self.assertEqual(result[:22], PI_REF[:22])

    def test_fallback_result_is_mpmath_type(self):
        with unittest.mock.patch.object(pi_module, "_HAS_GMPY2", False):
            pi_val = _quiet_pi(10)
        # mpmath constants are a subtype of mpf; check the module rather than
        # the exact class since mpmath.pi is not a plain mpmath.mpf instance.
        self.assertIn("mpmath", type(pi_val).__module__)


# ---------------------------------------------------------------------------
# show_pi_preview
# ---------------------------------------------------------------------------

class TestShowPiPreview(unittest.TestCase):
    """show_pi_preview prints a correctly formatted π preview."""

    @classmethod
    def setUpClass(cls):
        cls._pi = _quiet_pi(50)

    def _capture(self, digits):
        buf = io.StringIO()
        with redirect_stdout(buf):
            show_pi_preview(self._pi, digits)
        return buf.getvalue()

    def test_output_contains_pi_equals(self):
        out = self._capture(10)
        self.assertIn("π =", out)

    def test_output_starts_with_3_dot(self):
        out = self._capture(10)
        self.assertIn("3.", out)

    def test_output_mentions_decimal_places(self):
        out = self._capture(10)
        self.assertIn("decimal places", out)

    def test_preview_capped_at_200(self):
        """Requesting >200 preview digits is silently capped at 200."""
        out = self._capture(500)
        self.assertIn("200", out)


# ---------------------------------------------------------------------------
# save_pi_to_file
# ---------------------------------------------------------------------------

class TestSavePiToFile(unittest.TestCase):
    """save_pi_to_file writes a correctly structured output file."""

    @classmethod
    def setUpClass(cls):
        cls._pi = _quiet_pi(50)

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        self._path = self._tmp.name
        self._tmp.close()

    def tearDown(self):
        os.unlink(self._path)

    def _save(self, digits=50):
        buf = io.StringIO()
        with redirect_stdout(buf):
            save_pi_to_file(self._pi, digits, self._path)

    def test_file_is_created(self):
        self._save()
        self.assertTrue(os.path.exists(self._path))

    def test_file_contains_header(self):
        self._save()
        with open(self._path) as f:
            content = f.read()
        self.assertIn("π calculated to", content)

    def test_file_contains_pi_digits(self):
        self._save()
        with open(self._path) as f:
            content = f.read()
        self.assertIn("3.14159265358979", content)

    def test_file_contains_footer(self):
        self._save()
        with open(self._path) as f:
            content = f.read()
        self.assertIn("Total decimal places", content)

    def test_file_size_is_nonzero(self):
        self._save()
        self.assertGreater(os.path.getsize(self._path), 0)


# ---------------------------------------------------------------------------
# _calculate_pi_gmpy2 parallel path — requires gmpy2
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
class TestCalculatePiParallel(unittest.TestCase):
    """_calculate_pi_gmpy2 parallel path (n_workers > 1)."""

    def test_parallel_result_matches_serial(self):
        """With _CPU_COUNT=4 and enough terms, result matches single-worker."""
        # Force multi-worker path.
        with unittest.mock.patch.object(pi_module, "_CPU_COUNT", 4):
            pi_parallel = _quiet_pi(2000)
        # Compare to single-worker result (normal call with small digit count).
        pi_serial = _quiet_pi(20)
        # Both must agree on the first 20 known digits.
        from pi import _pi_to_str
        s_par = _pi_to_str(pi_parallel, 20)
        s_ser = _pi_to_str(pi_serial, 20)
        self.assertEqual(s_par[:22], PI_REF[:22])
        self.assertEqual(s_ser[:22], s_par[:22])


# ---------------------------------------------------------------------------
# get_target_digits — non-interactive paths
# ---------------------------------------------------------------------------

class TestGetTargetDigits(unittest.TestCase):
    """get_target_digits with CLI args (non-interactive paths only)."""

    class _Args:
        def __init__(self, digits):
            self.digits = digits

    def test_returns_digits_from_args(self):
        self.assertEqual(get_target_digits(self._Args(50)), 50)

    def test_raises_on_zero(self):
        with self.assertRaises(ValueError):
            get_target_digits(self._Args(0))

    def test_raises_on_negative(self):
        with self.assertRaises(ValueError):
            get_target_digits(self._Args(-1))

    def test_large_digits_prints_warning_and_returns(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = get_target_digits(self._Args(2_000_000))
        self.assertEqual(result, 2_000_000)
        self.assertIn("Warning", buf.getvalue())

    def test_minimum_valid_value(self):
        # digits=1 is the smallest positive value; no warning, returns 1.
        self.assertEqual(get_target_digits(self._Args(1)), 1)


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------

class TestParseArgs(unittest.TestCase):
    """parse_args correctly handles CLI arguments."""

    def test_no_args_gives_none(self):
        with unittest.mock.patch("sys.argv", ["pi.py"]):
            args = parse_args()
        self.assertIsNone(args.digits)

    def test_positional_digit_arg(self):
        with unittest.mock.patch("sys.argv", ["pi.py", "100"]):
            args = parse_args()
        self.assertEqual(args.digits, 100)

    def test_invalid_arg_exits(self):
        with unittest.mock.patch("sys.argv", ["pi.py", "abc"]):
            with self.assertRaises(SystemExit):
                parse_args()


@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
class TestPiToStrNegativeSign(unittest.TestCase):
    """Cover the negative-sign branch in `_gmpy2_mpfr_to_str`."""

    def test_negative_mpfr_sign_branch(self):
        from pi import _gmpy2 as g, _gmpy2_mpfr_to_str
        ctx = g.get_context()
        saved = ctx.precision
        ctx.precision = 200
        try:
            neg = -g.mpfr("3.14159265358979")
        finally:
            ctx.precision = saved
        s = _gmpy2_mpfr_to_str(neg, 5)
        self.assertTrue(s.startswith("-"))


class TestShowPiPreviewNoDecimal(unittest.TestCase):
    """Cover the `else` branch (no '.' character in preview string)."""

    def test_no_decimal_point_branch(self):
        from pi import show_pi_preview

        class FakePi:
            pass

        with unittest.mock.patch("pi._pi_to_str", return_value="3"):
            with redirect_stdout(io.StringIO()) as buf:
                show_pi_preview(FakePi(), 1)
        self.assertIn("\u03c0 = 3.", buf.getvalue())


class TestGetTargetDigitsInteractive(unittest.TestCase):
    """Cover get_target_digits interactive prompt loop."""

    def _ns(self, digits):
        import argparse
        return argparse.Namespace(digits=digits)

    def test_interactive_valid(self):
        from pi import get_target_digits
        with unittest.mock.patch("builtins.input", side_effect=["100"]), redirect_stdout(io.StringIO()):
            self.assertEqual(get_target_digits(self._ns(None)), 100)

    def test_interactive_zero_then_valid(self):
        from pi import get_target_digits
        with unittest.mock.patch("builtins.input", side_effect=["0", "10"]), redirect_stdout(io.StringIO()):
            self.assertEqual(get_target_digits(self._ns(None)), 10)

    def test_interactive_non_integer_then_valid(self):
        from pi import get_target_digits
        with unittest.mock.patch("builtins.input", side_effect=["xyz", "5"]), redirect_stdout(io.StringIO()):
            self.assertEqual(get_target_digits(self._ns(None)), 5)

    def test_interactive_too_large_decline_then_accept(self):
        from pi import get_target_digits
        with unittest.mock.patch(
            "builtins.input",
            side_effect=["2000000", "n", "100"],
        ), redirect_stdout(io.StringIO()):
            self.assertEqual(get_target_digits(self._ns(None)), 100)

    def test_interactive_too_large_accept(self):
        from pi import get_target_digits
        with unittest.mock.patch(
            "builtins.input",
            side_effect=["1500000", "y"],
        ), redirect_stdout(io.StringIO()):
            self.assertEqual(get_target_digits(self._ns(None)), 1_500_000)


class TestSavePiEstimateAndProgress(unittest.TestCase):
    """Cover save_pi_to_file's estimate_conversion_time tiers via patched ProcessPool."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_estimate_conversion_time_tiers(self):
        from pi import save_pi_to_file
        import mpmath

        class _FakeFuture:
            def __init__(self, v):
                self._v = v
            def done(self):
                return True
            def result(self):
                return self._v

        class _FakePool:
            def __init__(self, *_, **__):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *_a):
                return False
            def submit(self, fn, *args, **kwargs):
                return _FakeFuture("3.14159\n")

        mpmath.mp.dps = 30
        pi_val = +mpmath.pi  # mpmath path

        for d in (50_000, 500_000, 5_000_000, 50_000_000):
            path = os.path.join(self._tmp, f"pi_{d}.txt")
            with unittest.mock.patch(
                "pi.concurrent.futures.ProcessPoolExecutor", _FakePool
            ), redirect_stdout(io.StringIO()):
                save_pi_to_file(pi_val, d, path)
            self.assertTrue(os.path.exists(path))
            os.unlink(path)


class TestMain(unittest.TestCase):
    """Cover main() — small/large display branches and error handlers."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def _run(self, argv, inputs):
        from pi import main
        with unittest.mock.patch("sys.argv", argv), \
             unittest.mock.patch("builtins.input", side_effect=inputs), \
             redirect_stdout(io.StringIO()) as buf:
            main()
        return buf.getvalue()

    def test_small_digits_display_branch(self):
        out = self._run(["pi.py", "10"], ["y"])
        self.assertIn("3.14159", out)
        self.assertIn("Total digits", out)

    def test_small_digits_save_branch(self):
        out = self._run(["pi.py", "10"], ["n"])
        self.assertIn("3.14159", out)
        self.assertTrue(os.path.exists("pi_10_digits.txt"))

    def test_value_error_path(self):
        from pi import main
        with unittest.mock.patch("sys.argv", ["pi.py", "0"]), \
             redirect_stdout(io.StringIO()) as buf:
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Error:", buf.getvalue())

    def test_keyboard_interrupt_path(self):
        from pi import main
        with unittest.mock.patch("sys.argv", ["pi.py", "10"]), \
             unittest.mock.patch("pi.calculate_pi_high_precision", side_effect=KeyboardInterrupt), \
             redirect_stdout(io.StringIO()) as buf:
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("interrupted", buf.getvalue())

    def test_generic_exception_path(self):
        from pi import main
        with unittest.mock.patch("sys.argv", ["pi.py", "10"]), \
             unittest.mock.patch("pi.calculate_pi_high_precision", side_effect=RuntimeError("boom")), \
             redirect_stdout(io.StringIO()) as buf:
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Error occurred", buf.getvalue())


class TestEntryPointGuard(unittest.TestCase):
    """Cover the `if __name__ == "__main__"` block and main-process guard."""

    def test_module_runs_via_subprocess(self):
        import subprocess
        proc = subprocess.run(
            [sys.executable, pi_module.__file__, "5"],
            input="n\n",
            capture_output=True,
            text=True,
            timeout=30,
            cwd=tempfile.gettempdir(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("3.14159", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
