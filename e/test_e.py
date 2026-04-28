#!/usr/bin/env python3
"""
Unit tests for e.py.

Run with:
    python -m pytest test_e.py -v
or:
    python -m unittest test_e -v

gmpy2-dependent tests are skipped automatically when gmpy2 is not installed.
"""

import io
import os
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout

# Ensure the e module is importable from this directory.
sys.path.insert(0, os.path.dirname(__file__))

import e as e_module
from e import (
    _HAS_GMPY2,
    _tree_combine,
    _e_to_str,
    _bs_chunk_worker,
    calculate_e,
    get_target_digits,
    parse_args,
)

# Known decimal expansion of e — used for accuracy assertions.
E_REF = "2.71828182845904523536028747135266249775724709369995"


def _quiet_e(digits):
    """Compute e while suppressing the progress prints to stdout."""
    with redirect_stdout(io.StringIO()):
        return calculate_e(digits)


# ---------------------------------------------------------------------------
# _tree_combine
# ---------------------------------------------------------------------------

class TestTreeCombine(unittest.TestCase):
    """Tests for _tree_combine (pure Python, no gmpy2 dependency)."""

    @staticmethod
    def _merge(left, right):
        Pl, Ql = left
        Pr, Qr = right
        return Pl * Pr, Ql * Pr + Qr

    def test_single_element(self):
        pq = (1, 2)
        self.assertEqual(_tree_combine([pq]), pq)

    def test_two_elements(self):
        a = (2, 3)
        b = (7, 11)
        expected = self._merge(a, b)
        self.assertEqual(_tree_combine([a, b]), expected)

    def test_four_elements_tree_order(self):
        """tree_combine pairs (0,1) and (2,3) before combining the pairs."""
        chunks = [(1, 1), (2, 3), (7, 11), (17, 19)]
        m01 = self._merge(chunks[0], chunks[1])
        m23 = self._merge(chunks[2], chunks[3])
        expected = self._merge(m01, m23)
        self.assertEqual(_tree_combine(list(chunks)), expected)

    def test_odd_length_passthrough(self):
        """With 3 elements, the last passes through level 1 unmerged."""
        chunks = [(1, 1), (2, 3), (7, 11)]
        m01 = self._merge(chunks[0], chunks[1])
        expected = self._merge(m01, chunks[2])
        self.assertEqual(_tree_combine(list(chunks)), expected)

    def test_large_input_deterministic(self):
        """16-element reduction is stable across calls."""
        chunks = [(i + 1, i + 2) for i in range(16)]
        result_a = _tree_combine(list(chunks))
        result_b = _tree_combine(list(chunks))
        self.assertEqual(result_a, result_b)

    def test_empty_list_raises(self):
        with self.assertRaises(IndexError):
            _tree_combine([])

    def test_merge_formula(self):
        """Verify the merge formula: P(a,b) = Pl*Pr, Q(a,b) = Ql*Pr + Qr."""
        a = (5, 10)
        b = (3, 7)
        P, Q = _tree_combine([a, b])
        self.assertEqual(P, 5 * 3)
        self.assertEqual(Q, 10 * 3 + 7)


# ---------------------------------------------------------------------------
# _taylor_bs
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
class TestTaylorBS(unittest.TestCase):
    """Tests for _taylor_bs (requires gmpy2)."""

    def setUp(self):
        from e import _taylor_bs
        self._taylor_bs = _taylor_bs

    def test_leaf_a0(self):
        """a=0: P=1, Q=1 (represents 1/0! = 1)."""
        P, Q = self._taylor_bs(0, 1)
        self.assertEqual(int(P), 1)
        self.assertEqual(int(Q), 1)

    def test_leaf_a1(self):
        """a=1: P=2, Q=2 (represents 1/1! contribution)."""
        P, Q = self._taylor_bs(1, 2)
        self.assertEqual(int(P), 2)
        self.assertEqual(int(Q), 2)

    def test_leaf_a2(self):
        """a=2: P=3, Q=3."""
        P, Q = self._taylor_bs(2, 3)
        self.assertEqual(int(P), 3)
        self.assertEqual(int(Q), 3)

    def test_two_term_split(self):
        """Range [0,2) should split into [0,1) and [1,2) and merge."""
        P, Q = self._taylor_bs(0, 2)
        # Manual: left=(1,1), right=(2,2)
        # Merged: P=1*2=2, Q=1*2+2=4
        self.assertEqual(int(P), 2)
        self.assertEqual(int(Q), 4)

    def test_three_term_split(self):
        """Range [0,3) covers terms 0,1,2."""
        P, Q = self._taylor_bs(0, 3)
        # [0,1)=(1,1), [1,2)=(2,2), [2,3)=(3,3)
        # [0,2): P=2, Q=4   (see test_two_term_split)
        # merge [0,2) with [2,3): P=2*3=6, Q=4*3+3=15
        self.assertEqual(int(P), 6)
        self.assertEqual(int(Q), 15)

    def test_split_consistency(self):
        """Full range equals tree-combined halves."""
        P_full, Q_full = self._taylor_bs(0, 20)
        P_l, Q_l = self._taylor_bs(0, 10)
        P_r, Q_r = self._taylor_bs(10, 20)
        # Merge: P = Pl*Pr, Q = Ql*Pr + Qr
        self.assertEqual(int(P_full), int(P_l) * int(P_r))
        self.assertEqual(int(Q_full), int(Q_l) * int(P_r) + int(Q_r))

    def test_50_terms_accuracy(self):
        """50 terms of Taylor series via binary splitting match e to 50 digits."""
        import gmpy2
        P, Q = self._taylor_bs(0, 50)
        ctx = gmpy2.get_context()
        saved = ctx.precision
        ctx.precision = 256
        try:
            e_val = gmpy2.mpfr(Q) / gmpy2.mpfr(P)
            e_str = str(e_val)
        finally:
            ctx.precision = saved
        # First 15 digits should match (50 terms gives far more than 15)
        self.assertTrue(e_str.startswith("2.71828182845904"))


# ---------------------------------------------------------------------------
# _bs_chunk_worker
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
class TestBsChunkWorker(unittest.TestCase):
    """Tests for _bs_chunk_worker (requires gmpy2)."""

    def test_returns_plain_ints(self):
        P, Q = _bs_chunk_worker(0, 10)
        self.assertIsInstance(P, int)
        self.assertIsInstance(Q, int)

    def test_matches_taylor_bs(self):
        from e import _taylor_bs
        P_bs, Q_bs = _taylor_bs(0, 10)
        P_cw, Q_cw = _bs_chunk_worker(0, 10)
        self.assertEqual(int(P_bs), P_cw)
        self.assertEqual(int(Q_bs), Q_cw)

    def test_subrange(self):
        """Worker on a subrange [5,15) returns valid ints."""
        P, Q = _bs_chunk_worker(5, 15)
        self.assertIsInstance(P, int)
        self.assertIsInstance(Q, int)
        self.assertGreater(P, 0)
        self.assertGreater(Q, 0)


# ---------------------------------------------------------------------------
# _e_to_str
# ---------------------------------------------------------------------------

class TestEToStr(unittest.TestCase):
    """Tests for _e_to_str (format checks)."""

    def test_starts_with_2_dot(self):
        e_val = _quiet_e(20)
        result = _e_to_str(e_val, 20)
        self.assertTrue(result.startswith("2."))

    def test_no_exponent(self):
        e_val = _quiet_e(50)
        result = _e_to_str(e_val, 50)
        self.assertNotIn("e", result.lower())

    def test_exact_decimal_count(self):
        e_val = _quiet_e(30)
        result = _e_to_str(e_val, 30)
        _, dec = result.split(".")
        self.assertEqual(len(dec), 30)

    def test_known_digits(self):
        e_val = _quiet_e(50)
        result = _e_to_str(e_val, 50)
        self.assertEqual(result, E_REF)

    def test_single_digit(self):
        e_val = _quiet_e(1)
        result = _e_to_str(e_val, 1)
        self.assertTrue(result.startswith("2."))
        _, dec = result.split(".")
        self.assertEqual(len(dec), 1)

    def test_large_digit_count(self):
        e_val = _quiet_e(200)
        result = _e_to_str(e_val, 200)
        _, dec = result.split(".")
        self.assertEqual(len(dec), 200)
        self.assertTrue(result.startswith(E_REF[:20]))


# ---------------------------------------------------------------------------
# TestEAccuracy
# ---------------------------------------------------------------------------

class TestEAccuracy(unittest.TestCase):
    """End-to-end accuracy tests for calculate_e."""

    def test_10_digits(self):
        e_val = _quiet_e(10)
        result = _e_to_str(e_val, 10)
        self.assertEqual(result, E_REF[:12])  # "2." + 10 digits

    def test_20_digits(self):
        e_val = _quiet_e(20)
        result = _e_to_str(e_val, 20)
        self.assertEqual(result, E_REF[:22])

    def test_50_digits(self):
        e_val = _quiet_e(50)
        result = _e_to_str(e_val, 50)
        self.assertEqual(result, E_REF)

    def test_single_digit(self):
        e_val = _quiet_e(1)
        result = _e_to_str(e_val, 1)
        self.assertEqual(result, "2.7")

    @unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
    def test_400_digits_accurate(self):
        # digits=400 is above the ~340-digit threshold where the old term-count
        # formula (N = digits/log10(digits) + 50) supplied too few Taylor terms,
        # producing silently wrong tail digits in the gmpy2 fast path.
        E_400 = (
            "2."
            "71828182845904523536028747135266249775724709369995"
            "95749669676277240766303535475945713821785251664274"
            "27466391932003059921817413596629043572900334295260"
            "59563073813232862794349076323382988075319525101901"
            "15738341879307021540891499348841675092447614606680"
            "82264800168477411853742345442437107539077744992069"
            "55170276183860626133138458300075204493382656029760"
            "67371132007093287091274437470472306969772093101416"
        )
        e_val = _quiet_e(400)
        result = _e_to_str(e_val, 400)
        self.assertEqual(result, E_400, "tail digits wrong — check term count formula")


# ---------------------------------------------------------------------------
# TestMpmathFallback
# ---------------------------------------------------------------------------

class TestMpmathFallback(unittest.TestCase):
    """Tests for mpmath fallback path."""

    def test_fallback_returns_mpmath_type(self):
        import mpmath
        with unittest.mock.patch.object(e_module, '_HAS_GMPY2', False):
            e_val = _quiet_e(20)
        self.assertIsInstance(e_val, mpmath.mpf)

    def test_fallback_accuracy(self):
        with unittest.mock.patch.object(e_module, '_HAS_GMPY2', False):
            e_val = _quiet_e(50)
            result = _e_to_str(e_val, 50)
        # mpmath.nstr may round the last digit differently; verify first 48 digits
        self.assertEqual(result[:50], E_REF[:50])


# ---------------------------------------------------------------------------
# TestCalculateEParallel
# ---------------------------------------------------------------------------

@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
class TestCalculateEParallel(unittest.TestCase):
    """Test parallel calculation path."""

    def test_parallel_2000_digits(self):
        with unittest.mock.patch.object(e_module, '_CPU_COUNT', 4):
            e_val = _quiet_e(2000)
        result = _e_to_str(e_val, 50)
        self.assertEqual(result, E_REF)


# ---------------------------------------------------------------------------
# TestGetTargetDigits
# ---------------------------------------------------------------------------

class TestGetTargetDigits(unittest.TestCase):
    """Tests for get_target_digits."""

    def test_valid_digits(self):
        args = parse_args(["100"])
        self.assertEqual(get_target_digits(args), 100)

    def test_zero_raises(self):
        args = parse_args(["0"])
        with self.assertRaises(ValueError):
            get_target_digits(args)

    def test_negative_raises(self):
        args = parse_args(["-1"])
        with self.assertRaises(ValueError):
            get_target_digits(args)

    def test_large_warning(self):
        args = parse_args(["2000000"])
        buf = io.StringIO()
        with redirect_stdout(buf):
            result = get_target_digits(args)
        self.assertEqual(result, 2000000)
        self.assertIn("Warning", buf.getvalue())

    def test_minimum_one(self):
        args = parse_args(["1"])
        self.assertEqual(get_target_digits(args), 1)


# ---------------------------------------------------------------------------
# TestParseArgs
# ---------------------------------------------------------------------------

class TestParseArgs(unittest.TestCase):
    """Tests for parse_args."""

    def test_no_args(self):
        args = parse_args([])
        self.assertIsNone(args.digits)

    def test_positional(self):
        args = parse_args(["42"])
        self.assertEqual(args.digits, 42)

    def test_invalid_exits(self):
        with self.assertRaises(SystemExit):
            parse_args(["not_a_number"])


# ---------------------------------------------------------------------------
# TestShowEPreview
# ---------------------------------------------------------------------------

class TestShowEPreview(unittest.TestCase):
    """show_e_preview prints a correctly formatted e preview."""

    @classmethod
    def setUpClass(cls):
        cls._e = _quiet_e(50)

    def _capture(self, digits):
        buf = io.StringIO()
        with redirect_stdout(buf):
            from e import show_e_preview
            show_e_preview(self._e, digits)
        return buf.getvalue()

    def test_output_contains_e_equals(self):
        out = self._capture(10)
        self.assertIn("e =", out)

    def test_output_starts_with_2_dot(self):
        out = self._capture(10)
        self.assertIn("2.", out)

    def test_output_mentions_decimal_places(self):
        out = self._capture(10)
        self.assertIn("decimal places", out)

    def test_preview_capped_at_200(self):
        out = self._capture(500)
        self.assertIn("200", out)


# ---------------------------------------------------------------------------
# TestSaveEToFile
# ---------------------------------------------------------------------------

class TestSaveEToFile(unittest.TestCase):
    """save_e_to_file writes a correctly structured output file."""

    @classmethod
    def setUpClass(cls):
        cls._e = _quiet_e(50)

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
        self._path = self._tmp.name
        self._tmp.close()

    def tearDown(self):
        os.unlink(self._path)

    def _save(self, digits=50):
        buf = io.StringIO()
        with redirect_stdout(buf):
            from e import save_e_to_file
            save_e_to_file(self._e, digits, self._path)

    def test_file_is_created(self):
        self._save()
        self.assertTrue(os.path.exists(self._path))

    def test_file_contains_header(self):
        self._save()
        with open(self._path) as f:
            content = f.read()
        self.assertIn("e calculated to", content)

    def test_file_contains_e_digits(self):
        self._save()
        with open(self._path) as f:
            content = f.read()
        self.assertIn("2.71828182845904", content)

    def test_file_contains_footer(self):
        self._save()
        with open(self._path) as f:
            content = f.read()
        self.assertIn("Total decimal places", content)

    def test_file_size_is_nonzero(self):
        self._save()
        self.assertGreater(os.path.getsize(self._path), 0)


class TestETostrEdgeCases(unittest.TestCase):
    """Cover the negative-sign and no-decimal-point branches."""

    def test_mpmath_negative_value_branch(self):
        # Forces the `mantissa.startswith('-')` sign-strip path on the gmpy2 branch
        # by passing a negative mpfr; otherwise stays on mpmath's path.
        if _HAS_GMPY2:
            from e import _gmpy2 as g
            ctx = g.get_context()
            saved = ctx.precision
            ctx.precision = 200
            try:
                neg_e = -g.mpfr("2.718281828")
            finally:
                ctx.precision = saved
            s = _e_to_str(neg_e, 5)
            self.assertTrue(s.startswith("-"))


class TestShowEPreviewNoDecimal(unittest.TestCase):
    """Cover the `else` branch of show_e_preview (input has no '.' character)."""

    def test_no_decimal_point_branch(self):
        from e import show_e_preview

        class FakeE:
            pass

        # Patch _e_to_str to return a string without '.'
        with unittest.mock.patch("e._e_to_str", return_value="3"):
            with redirect_stdout(io.StringIO()) as buf:
                show_e_preview(FakeE(), 1)
        # The "no decimal" branch produces "e = 3." in output.
        self.assertIn("e = 3.", buf.getvalue())


@unittest.skipUnless(_HAS_GMPY2, "gmpy2 not installed")
class TestGmpy2WorkerFunctions(unittest.TestCase):
    """Cover _gmpy2_str_from_PQ and _convert_gmpy2_worker (subprocess-only paths)."""

    def test_gmpy2_str_from_pq_matches_e(self):
        from e import _gmpy2_str_from_PQ, _calculate_e_gmpy2
        with redirect_stdout(io.StringIO()):
            _, P_int, Q_int = _calculate_e_gmpy2(20)
        s = _gmpy2_str_from_PQ(P_int, Q_int, 20)
        self.assertTrue(s.startswith("2.71828182845904523536"))

    def test_convert_gmpy2_worker_dispatches(self):
        from e import _convert_gmpy2_worker, _calculate_e_gmpy2
        with redirect_stdout(io.StringIO()):
            _, P_int, Q_int = _calculate_e_gmpy2(15)
        s = _convert_gmpy2_worker(P_int, Q_int, 15)
        self.assertTrue(s.startswith("2.71828182845904"))


class TestConvertMpmathWorker(unittest.TestCase):
    """Cover _convert_mpmath_worker direct dispatch."""

    def test_returns_string(self):
        import mpmath
        from e import _convert_mpmath_worker
        mpmath.mp.dps = 60
        s = _convert_mpmath_worker(+mpmath.e, 20)
        self.assertTrue(s.startswith("2.71828182845904523536"))


class TestPwriteAllStall(unittest.TestCase):
    """Cover the `n == 0` stall branch of _pwrite_all."""

    def test_stall_raises_oserror(self):
        from e import _pwrite_all

        # Patch os.pwrite to return 0 on first call → triggers stall raise.
        with unittest.mock.patch("e.os.pwrite", return_value=0):
            with self.assertRaises(OSError):
                _pwrite_all(1, b"abc", 0)


class TestSaveEEstimateAndProgress(unittest.TestCase):
    """Cover save_e_to_file's nested estimate_conversion_time and ProgressIndicator
    overrun branch by invoking the function with a tiny digit count."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_estimate_conversion_time_branches(self):
        # Exercise estimate_conversion_time at all four boundary tiers via
        # a tiny call into save_e_to_file with patched ProcessPoolExecutor
        # so the function returns immediately. The point is to evaluate
        # estimate_conversion_time(d) for several d values inline.
        from e import save_e_to_file

        class _FakeFuture:
            def __init__(self, value):
                self._value = value
            def done(self):
                return True
            def result(self):
                return self._value

        class _FakePool:
            def __init__(self, *_, **__):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *_a):
                return False
            def submit(self, fn, *args, **kwargs):
                return _FakeFuture("2.71828\n")

        # Build a fake mpmath value so we take the mpmath-only path
        import mpmath
        mpmath.mp.dps = 30
        e_val = +mpmath.e

        # Run several digit tiers — exercises every branch of estimate_conversion_time
        # in the mpmath path (and the gmpy2 path by bypassing isinstance check).
        for d in (50_000, 500_000, 5_000_000, 50_000_000):
            path = os.path.join(self._tmp, f"e_test_{d}.txt")
            with unittest.mock.patch(
                "e.concurrent.futures.ProcessPoolExecutor", _FakePool
            ), redirect_stdout(io.StringIO()):
                save_e_to_file(e_val, d, path)
            self.assertTrue(os.path.exists(path))
            os.unlink(path)


class TestGetTargetDigitsInteractive(unittest.TestCase):
    """Cover the interactive prompt loop (lines 524-538)."""

    def _ns(self, digits):
        import argparse
        return argparse.Namespace(digits=digits)

    def test_interactive_valid_first_try(self):
        with unittest.mock.patch("builtins.input", side_effect=["100"]), redirect_stdout(io.StringIO()):
            self.assertEqual(get_target_digits(self._ns(None)), 100)

    def test_interactive_zero_then_valid(self):
        with unittest.mock.patch("builtins.input", side_effect=["0", "10"]), redirect_stdout(io.StringIO()):
            self.assertEqual(get_target_digits(self._ns(None)), 10)

    def test_interactive_non_integer_then_valid(self):
        with unittest.mock.patch("builtins.input", side_effect=["abc", "5"]), redirect_stdout(io.StringIO()):
            self.assertEqual(get_target_digits(self._ns(None)), 5)

    def test_interactive_too_large_decline_then_accept(self):
        # >1_000_000 triggers warning + confirmation; user declines, then enters smaller value
        with unittest.mock.patch(
            "builtins.input",
            side_effect=["2000000", "n", "100"],
        ), redirect_stdout(io.StringIO()):
            self.assertEqual(get_target_digits(self._ns(None)), 100)

    def test_interactive_too_large_accept(self):
        # >1_000_000 with confirmation accepted: returns the large value
        with unittest.mock.patch(
            "builtins.input",
            side_effect=["1500000", "y"],
        ), redirect_stdout(io.StringIO()):
            self.assertEqual(get_target_digits(self._ns(None)), 1_500_000)


class TestMain(unittest.TestCase):
    """Cover main() — small-digit display/save branches, large-digit auto-save,
    and the error handlers (ValueError, KeyboardInterrupt, generic Exception)."""

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
        from e import main
        old_argv = sys.argv
        sys.argv = argv
        try:
            with unittest.mock.patch("builtins.input", side_effect=inputs), redirect_stdout(io.StringIO()) as buf:
                main()
            return buf.getvalue()
        finally:
            sys.argv = old_argv

    def test_small_digits_display_branch(self):
        # CLI digits=10: no save_e_to_file (<=10000), user picks "y" to display
        out = self._run(["e.py", "10"], ["y"])
        self.assertIn("2.71828", out)
        self.assertIn("Total digits", out)
        self.assertFalse(any(name.startswith("e_") and name.endswith("_digits.txt") for name in os.listdir(".")))

    def test_small_digits_save_branch(self):
        out = self._run(["e.py", "10"], ["n"])
        self.assertIn("2.71828", out)
        self.assertTrue(os.path.exists("e_10_digits.txt"))

    def test_value_error_path(self):
        # digits=0 → get_target_digits raises ValueError → handled, exit(1)
        from e import main
        sys.argv = ["e.py", "0"]
        try:
            with redirect_stdout(io.StringIO()) as buf:
                with self.assertRaises(SystemExit) as cm:
                    main()
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("Error:", buf.getvalue())
        finally:
            sys.argv = ["e.py"]

    def test_keyboard_interrupt_path(self):
        from e import main
        sys.argv = ["e.py", "10"]
        try:
            with unittest.mock.patch("e.calculate_e", side_effect=KeyboardInterrupt), redirect_stdout(io.StringIO()) as buf:
                with self.assertRaises(SystemExit) as cm:
                    main()
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("interrupted", buf.getvalue())
        finally:
            sys.argv = ["e.py"]

    def test_generic_exception_path(self):
        from e import main
        sys.argv = ["e.py", "10"]
        try:
            with unittest.mock.patch("e.calculate_e", side_effect=RuntimeError("boom")), redirect_stdout(io.StringIO()) as buf:
                with self.assertRaises(SystemExit) as cm:
                    main()
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("Error occurred", buf.getvalue())
        finally:
            sys.argv = ["e.py"]


class TestEntryPointGuard(unittest.TestCase):
    """Cover the `if __name__ == "__main__"` block and main-process guard."""

    def test_module_runs_via_subprocess(self):
        import subprocess
        proc = subprocess.run(
            [sys.executable, e_module.__file__, "5"],
            input="n\n",
            capture_output=True,
            text=True,
            timeout=30,
            cwd=tempfile.gettempdir(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("e", proc.stdout)


if __name__ == "__main__":
    unittest.main()
