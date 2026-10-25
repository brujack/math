import argparse
import array
import io
import os
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout

from hypothesis import given
from hypothesis import strategies as st

import collatz
from collatz import (
    collatz_length,
    collatz_next,
    generate_records,
    get_exponent,
    main,
    parse_args,
    refuse_large_run,
)


class TestCollatzNext(unittest.TestCase):
    def test_even_input(self):
        self.assertEqual(collatz_next(6), 3)

    def test_odd_input(self):
        self.assertEqual(collatz_next(3), 10)

    def test_n2_yields_1(self):
        self.assertEqual(collatz_next(2), 1)


class TestCollatzLength(unittest.TestCase):
    def _make_cache(self, size: int) -> array.array:
        cache = array.array("I", [0] * size)
        cache[1] = 1
        return cache

    def test_n1_is_zero(self):
        self.assertEqual(collatz_length(1, self._make_cache(10)), 0)

    def test_n2_is_one(self):
        self.assertEqual(collatz_length(2, self._make_cache(10)), 1)

    def test_n3_is_seven(self):
        self.assertEqual(collatz_length(3, self._make_cache(100)), 7)

    def test_n27_is_111(self):
        self.assertEqual(collatz_length(27, self._make_cache(10_000)), 111)

    def test_cache_hit_returns_same(self):
        cache = self._make_cache(100)
        collatz_length(3, cache)
        self.assertNotEqual(cache[3], 0)
        self.assertEqual(collatz_length(3, cache), 7)

    def test_value_exceeds_limit(self):
        # n=3's chain passes through 10, 16, 8 — all > limit=5.
        # They count toward chain length but are not stored in cache.
        cache = self._make_cache(6)  # indices 0..5, limit = 5
        self.assertEqual(collatz_length(3, cache), 7)


class TestGenerateRecords(unittest.TestCase):
    def test_limit_1_yields_one_record(self):
        self.assertEqual(list(generate_records(1)), [(1, 0)])

    def test_limit_10_known_records(self):
        self.assertEqual(
            list(generate_records(10)),
            [(1, 0), (2, 1), (3, 7), (6, 8), (7, 16), (9, 19)],
        )

    def test_ascending_n_order(self):
        records = list(generate_records(10))
        ns = [r[0] for r in records]
        self.assertEqual(ns, sorted(ns))

    def test_ascending_length_order(self):
        records = list(generate_records(10))
        lengths = [r[1] for r in records]
        self.assertEqual(lengths, sorted(lengths))


class TestGetExponent(unittest.TestCase):
    def _ns(self, exponent):
        return argparse.Namespace(size=exponent)

    def test_valid_minimum(self):
        self.assertEqual(get_exponent(self._ns(1)), 1)

    def test_valid_mid(self):
        self.assertEqual(get_exponent(self._ns(7)), 7)

    def test_valid_maximum(self):
        self.assertEqual(get_exponent(self._ns(12)), 12)

    def test_zero_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._ns(0))

    def test_13_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._ns(13))

    def test_negative_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._ns(-1))

    def test_interactive_valid(self):
        with unittest.mock.patch("builtins.input", return_value="5"):
            self.assertEqual(get_exponent(self._ns(None)), 5)

    def test_interactive_eof_exits_1_with_contract_message(self):
        err = io.StringIO()
        out = io.StringIO()
        with (
            unittest.mock.patch("builtins.input", side_effect=EOFError),
            unittest.mock.patch("sys.stderr", err),
            redirect_stdout(out),
            self.assertRaises(SystemExit) as cm,
        ):
            get_exponent(self._ns(None))
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(out.getvalue(), "\n")
        self.assertEqual(
            err.getvalue().strip(),
            "Error: no input; pass SIZE as an argument (e.g. python3 collatz.py 5).",
        )

    def test_interactive_warns_above_7(self):
        out = io.StringIO()
        with (
            unittest.mock.patch("builtins.input", return_value="8"),
            redirect_stdout(out),
        ):
            self.assertEqual(get_exponent(self._ns(None)), 8)
        self.assertIn("Warning: N=8", out.getvalue())

    def test_arg_above_7_warns_on_stderr(self):
        err = io.StringIO()
        with unittest.mock.patch("sys.stderr", err):
            self.assertEqual(get_exponent(self._ns(8)), 8)
        self.assertIn("Warning: N=8", err.getvalue())

    def test_interactive_invalid_then_valid(self):
        with (
            unittest.mock.patch("builtins.input", side_effect=["0", "abc", "3"]),
            unittest.mock.patch("builtins.print"),
        ):
            self.assertEqual(get_exponent(self._ns(None)), 3)


class TestMain(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_n1_creates_file(self):
        with (
            redirect_stdout(io.StringIO()),
        ):
            main(["1"])
        with open("collatz_1e1.txt") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines, ["1 0", "2 1", "3 7", "6 8", "7 16", "9 19"])

    def test_n3_file_contains_27(self):
        with (
            redirect_stdout(io.StringIO()),
        ):
            main(["3"])
        with open("collatz_1e3.txt") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[0], "1 0")
        self.assertIn("27 111", lines)

    def test_keyboard_interrupt_exits_1(self):
        with (
            unittest.mock.patch(
                "collatz.generate_records", side_effect=KeyboardInterrupt
            ),
            redirect_stdout(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as cm:
                main(["1"])
        self.assertEqual(cm.exception.code, 1)

    def test_permission_error_exits_1(self):
        with (
            unittest.mock.patch(
                "builtins.open", side_effect=PermissionError("Permission denied")
            ),
            redirect_stdout(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as cm:
                main(["1"])
        self.assertEqual(cm.exception.code, 1)

    def test_without_show_does_not_echo_records(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main(["1"])
        self.assertNotIn("9 19", out.getvalue().splitlines())
        self.assertIn("Saved 6 records to collatz_1e1.txt", out.getvalue())

    def test_show_echoes_each_record_verbatim(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main(["1", "--show"])
        lines = out.getvalue().splitlines()
        for rec in ["1 0", "2 1", "3 7", "6 8", "7 16", "9 19"]:
            self.assertIn(rec, lines)

    def test_rerun_overwrites_file(self):
        with redirect_stdout(io.StringIO()):
            main(["1"])
            main(["1"])
        with open("collatz_1e1.txt") as f:
            self.assertEqual(len(f.read().splitlines()), 6)

    def test_refusal_happens_before_any_file_write(self):
        with (
            unittest.mock.patch.object(collatz, "LARGE_RUN_THRESHOLD", 2),
            unittest.mock.patch("sys.stderr", io.StringIO()),
            redirect_stdout(io.StringIO()),
            self.assertRaises(SystemExit) as cm,
        ):
            main(["2"])
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(os.listdir("."), [])

    def test_smoke_runs_at_smoke_size(self):
        with redirect_stdout(io.StringIO()):
            main(["--smoke"])
        self.assertTrue(os.path.exists(f"collatz_1e{collatz.SMOKE_SIZE}.txt"))

    def test_out_of_range_size_exits_1_without_file(self):
        with (
            unittest.mock.patch("sys.stderr", io.StringIO()),
            redirect_stdout(io.StringIO()),
            self.assertRaises(SystemExit) as cm,
        ):
            main(["0"])
        self.assertEqual(cm.exception.code, 1)
        self.assertEqual(os.listdir("."), [])


class TestParseArgs(unittest.TestCase):
    def test_size_parsed(self):
        args = parse_args(["4"])
        self.assertEqual(args.size, 4)
        self.assertFalse(args.show)
        self.assertFalse(args.yes)

    def test_show_flag(self):
        self.assertTrue(parse_args(["4", "--show"]).show)

    def test_smoke_sets_size_and_clears_show(self):
        args = parse_args(["--smoke", "--show"])
        self.assertEqual(args.size, collatz.SMOKE_SIZE)
        self.assertFalse(args.show)

    def test_smoke_with_size_exits_2(self):
        with (
            unittest.mock.patch("sys.stderr", io.StringIO()),
            self.assertRaises(SystemExit) as cm,
        ):
            parse_args(["--smoke", "3"])
        self.assertEqual(cm.exception.code, 2)

    def test_bare_non_tty_exits_2(self):
        with (
            unittest.mock.patch("sys.stdin.isatty", return_value=False),
            unittest.mock.patch("sys.stderr", io.StringIO()),
            self.assertRaises(SystemExit) as cm,
        ):
            parse_args([])
        self.assertEqual(cm.exception.code, 2)

    def test_bare_tty_allowed(self):
        with unittest.mock.patch("sys.stdin.isatty", return_value=True):
            self.assertIsNone(parse_args([]).size)


class TestCliContractConstants(unittest.TestCase):
    def test_smoke_size(self):
        self.assertEqual(collatz.SMOKE_SIZE, 5)

    def test_large_run_threshold(self):
        self.assertIsNone(collatz.LARGE_RUN_THRESHOLD)


class TestRefuseLargeRun(unittest.TestCase):
    def test_no_threshold_never_refuses(self):
        refuse_large_run(12, False)

    def test_threshold_refuses_without_yes(self):
        with (
            unittest.mock.patch.object(collatz, "LARGE_RUN_THRESHOLD", 8),
            unittest.mock.patch("sys.stderr", io.StringIO()) as err,
            self.assertRaises(SystemExit) as cm,
        ):
            refuse_large_run(8, False)
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("--yes", err.getvalue())

    def test_threshold_one_below_allowed(self):
        with unittest.mock.patch.object(collatz, "LARGE_RUN_THRESHOLD", 8):
            refuse_large_run(7, False)

    def test_threshold_with_yes_allowed(self):
        with unittest.mock.patch.object(collatz, "LARGE_RUN_THRESHOLD", 8):
            refuse_large_run(8, True)


class TestCollatzProperties(unittest.TestCase):
    @given(st.integers(min_value=1, max_value=5_000))
    def test_next_even(self, n):
        even = n * 2
        self.assertEqual(collatz_next(even), even // 2)

    @given(st.integers(min_value=0, max_value=5_000))
    def test_next_odd(self, n):
        odd = n * 2 + 1
        self.assertEqual(collatz_next(odd), 3 * odd + 1)

    @given(st.integers(min_value=2, max_value=10_000))
    def test_length_positive(self, n):
        cache = array.array("I", [0] * (n + 1))
        cache[1] = 1
        self.assertGreaterEqual(collatz_length(n, cache), 1)


if __name__ == "__main__":
    unittest.main()


class TestEntryPointGuard(unittest.TestCase):
    """Cover the `if __name__ == "__main__"` block."""

    def test_module_runs_via_subprocess(self):
        import pathlib
        import subprocess
        import sys

        module_path = pathlib.Path(__file__).parent / "collatz.py"
        proc = subprocess.run(
            [sys.executable, str(module_path), "4", "--show"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=tempfile.gettempdir(),
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("6171", proc.stdout)
