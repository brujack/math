#!/usr/bin/env python3
"""Unit tests for sq.py."""

import argparse
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st

import sq as sq_module
from sq import generate_squares, get_exponent, main, parse_args, refuse_large_run


class TestGenerateSquares(unittest.TestCase):
    def test_zero_max_digits_empty(self):
        # max_digits=0: limit=10^0=1, k=1, k*k=1 >= 1 → yields nothing
        self.assertEqual(list(generate_squares(0)), [])

    def test_one_digit_squares(self):
        # max_digits=1: limit=10, yields (1,1), (4,2), (9,3)
        self.assertEqual(list(generate_squares(1)), [(1, 1), (4, 2), (9, 3)])

    def test_two_digit_count(self):
        # max_digits=2: limit=100, k=1..9
        self.assertEqual(len(list(generate_squares(2))), 9)

    def test_two_digit_last_value(self):
        sq, root = list(generate_squares(2))[-1]
        self.assertEqual(sq, 81)
        self.assertEqual(root, 9)

    def test_two_digit_excludes_100(self):
        squares = [sq for sq, _ in generate_squares(2)]
        self.assertNotIn(100, squares)

    def test_each_is_perfect_square(self):
        for sq, root in generate_squares(3):
            self.assertEqual(root * root, sq)

    def test_strictly_increasing(self):
        result = [sq for sq, _ in generate_squares(3)]
        for i in range(1, len(result)):
            self.assertGreater(result[i], result[i - 1])

    def test_ten_digit_count(self):
        # max_digits=10: k=1..99999 → exactly 99,999 squares
        self.assertEqual(sum(1 for _ in generate_squares(10)), 99_999)

    def test_ten_digit_last_value(self):
        sq, root = list(generate_squares(10))[-1]
        self.assertEqual(sq, 99_999 * 99_999)
        self.assertEqual(root, 99_999)

    def test_ten_digit_excludes_100000_squared(self):
        squares = [sq for sq, _ in generate_squares(10)]
        self.assertNotIn(100_000 * 100_000, squares)

    def test_idempotent_same_input(self):
        result1 = list(generate_squares(2))
        result2 = list(generate_squares(2))
        self.assertEqual(result1, result2)


class TestParseArgs(unittest.TestCase):
    def test_size_given(self):
        args = parse_args(["1"])
        self.assertEqual(args.size, 1)
        self.assertFalse(args.show)
        self.assertFalse(args.yes)
        self.assertFalse(args.smoke)

    def test_no_args_on_terminal_leaves_size_unset(self):
        with patch("sys.stdin.isatty", return_value=True):
            self.assertIsNone(parse_args([]).size)

    def test_no_args_without_terminal_exits_2(self):
        with (
            patch("sys.stdin.isatty", return_value=False),
            redirect_stderr(io.StringIO()) as err,
            self.assertRaises(SystemExit) as ctx,
        ):
            parse_args([])
        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("SIZE is required", err.getvalue())

    def test_invalid_non_integer_exits_2(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            parse_args(["abc"])
        self.assertEqual(ctx.exception.code, 2)

    def test_show_flag(self):
        self.assertTrue(parse_args(["1", "--show"]).show)

    def test_yes_flag_is_accepted(self):
        self.assertTrue(parse_args(["1", "--yes"]).yes)

    def test_smoke_sets_size_and_clears_show(self):
        args = parse_args(["--smoke", "--show"])
        self.assertEqual(args.size, sq_module.SMOKE_SIZE)
        self.assertFalse(args.show)

    def test_smoke_with_size_exits_2(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            parse_args(["--smoke", "1"])
        self.assertEqual(ctx.exception.code, 2)


class TestCliContractConstants(unittest.TestCase):
    def test_smoke_size(self):
        self.assertEqual(sq_module.SMOKE_SIZE, 1)

    def test_no_large_run_threshold(self):
        self.assertIsNone(sq_module.LARGE_RUN_THRESHOLD)


class TestRefuseLargeRun(unittest.TestCase):
    def test_no_threshold_never_refuses(self):
        refuse_large_run(10**9, False)

    def test_threshold_refuses_at_boundary_without_yes(self):
        with (
            patch.object(sq_module, "LARGE_RUN_THRESHOLD", 5),
            redirect_stderr(io.StringIO()) as err,
            self.assertRaises(SystemExit) as ctx,
        ):
            refuse_large_run(5, False)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("--yes", err.getvalue())

    def test_threshold_allows_one_below_and_yes(self):
        with patch.object(sq_module, "LARGE_RUN_THRESHOLD", 5):
            refuse_large_run(4, False)
            refuse_large_run(5, True)


class TestGetExponent(unittest.TestCase):
    def _args(self, size):
        return argparse.Namespace(size=size)

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

    def test_zero_exits_with_code_1(self):
        with self.assertRaises(SystemExit) as cm:
            get_exponent(self._args(0))
        self.assertEqual(cm.exception.code, 1)

    def test_too_high_exits_with_code_1(self):
        with self.assertRaises(SystemExit) as cm:
            get_exponent(self._args(2))
        self.assertEqual(cm.exception.code, 1)

    def test_negative_exits_with_code_1(self):
        with self.assertRaises(SystemExit) as cm:
            get_exponent(self._args(-1))
        self.assertEqual(cm.exception.code, 1)


class TestGetExponentInteractive(unittest.TestCase):
    """Cover the interactive prompt branch (args.size is None)."""

    def _args_none(self):
        return argparse.Namespace(size=None)

    def test_interactive_valid_first_try(self):
        with patch("builtins.input", side_effect=["1"]), redirect_stdout(io.StringIO()):
            self.assertEqual(get_exponent(self._args_none()), 1)

    def test_interactive_too_high_then_valid(self):
        with (
            patch("builtins.input", side_effect=["2", "1"]),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(get_exponent(self._args_none()), 1)

    def test_interactive_zero_then_valid(self):
        with (
            patch("builtins.input", side_effect=["0", "1"]),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(get_exponent(self._args_none()), 1)

    def test_interactive_non_integer_then_valid(self):
        with (
            patch("builtins.input", side_effect=["abc", "1"]),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(get_exponent(self._args_none()), 1)


class TestMain(unittest.TestCase):
    """Cover main(): the file is always written; --show echoes it to stdout."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def _run_main(self, argv):
        with (
            patch("builtins.input", side_effect=AssertionError("must not prompt")),
            redirect_stdout(io.StringIO()) as buf,
        ):
            main(argv)
        return buf.getvalue()

    def test_main_writes_file_without_echoing_squares(self):
        out = self._run_main(["1"])
        self.assertIn("Perfect Square", out)
        with open("sq_1e1.txt") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[0], "1 | 1")
        self.assertEqual(lines[-1], "9999800001 | 99999")
        self.assertNotIn("9999800001 | 99999", out.splitlines())

    def test_show_prints_every_line_as_written(self):
        out = self._run_main(["1", "--show"])
        with open("sq_1e1.txt") as f:
            written = f.read().splitlines()
        shown = [ln for ln in out.splitlines() if " | " in ln]
        self.assertEqual(shown, written)

    def test_smoke_writes_the_file(self):
        self._run_main(["--smoke"])
        self.assertTrue(os.path.exists("sq_1e1.txt"))

    def test_invalid_size_exits_1_and_writes_nothing(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            self._run_main(["2"])
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(os.listdir("."), [])

    def test_main_idempotent_overwrites_file(self):
        self._run_main(["1"])
        first_size = os.path.getsize("sq_1e1.txt")
        self._run_main(["1"])
        self.assertEqual(os.path.getsize("sq_1e1.txt"), first_size)

    def test_main_reports_correct_count(self):
        # Exact count kills mutations to count initialisation or increment.
        out = self._run_main(["1"])
        self.assertIn("Found 99,999 perfect squares", out)


class TestFileWritePermissionError(unittest.TestCase):
    """main() handles PermissionError when the output file cannot be written."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_exits_nonzero_on_permission_error(self):
        buf = io.StringIO()
        with (
            patch(
                "builtins.open",
                side_effect=PermissionError(
                    "[Errno 13] Permission denied: 'sq_1e1.txt'"
                ),
            ),
            redirect_stdout(buf),
        ):
            with self.assertRaises(SystemExit) as cm:
                main(["1"])
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Error", buf.getvalue())


class TestKeyboardInterrupt(unittest.TestCase):
    """main() handles KeyboardInterrupt during generation."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def test_exits_nonzero_on_keyboard_interrupt(self):
        buf = io.StringIO()
        with (
            patch("sq.generate_squares", side_effect=KeyboardInterrupt),
            redirect_stdout(buf),
        ):
            with self.assertRaises(SystemExit) as cm:
                main(["1"])
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("interrupted", buf.getvalue())


class TestEntryPoint(unittest.TestCase):
    """Cover the `if __name__ == "__main__"` guard."""

    def test_module_runs_via_subprocess(self):
        import subprocess

        proc = subprocess.run(
            [sys.executable, sq_module.__file__, "1"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=tempfile.gettempdir(),
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Perfect Square", proc.stdout)


class TestSquaresProperties(unittest.TestCase):
    @given(st.integers(min_value=1, max_value=6))
    def test_all_perfect_squares(self, max_digits):
        for n, root in generate_squares(max_digits):
            self.assertEqual(root * root, n)

    @given(st.integers(min_value=1, max_value=6))
    def test_all_positive(self, max_digits):
        for n, _root in generate_squares(max_digits):
            self.assertGreater(n, 0)

    @given(st.integers(min_value=1, max_value=6))
    def test_strictly_increasing(self, max_digits):
        seq = [n for n, _ in generate_squares(max_digits)]
        for i in range(1, len(seq)):
            self.assertGreater(seq[i], seq[i - 1])


class TestClosedStdin(unittest.TestCase):
    """Run non-interactively (stdin closed, as in CI) the CLI must not traceback."""

    def _run(self, *args):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, sq_module.__file__, *args],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=tmp,
                check=False,
            )
            files = sorted(os.listdir(tmp))
        return proc, files

    def test_size_argument_runs_without_reading_stdin(self):
        proc, files = self._run("1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(files, ["sq_1e1.txt"])
        self.assertNotIn("9999800001 | 99999", proc.stdout.splitlines())

    def test_bare_run_without_terminal_exits_2(self):
        proc, files = self._run()
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("SIZE is required", proc.stderr)
        self.assertEqual(files, [])

    def test_exponent_prompt_eof_after_a_bad_answer_still_exits(self):
        with (
            patch("builtins.input", side_effect=["abc", EOFError]),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as ctx,
        ):
            get_exponent(argparse.Namespace(size=None))
        self.assertEqual(ctx.exception.code, 1)


class TestEofAtSizePrompt(unittest.TestCase):
    def test_eof_at_size_prompt_exits_1_naming_the_remedy(self):
        with (
            patch("builtins.input", side_effect=EOFError),
            redirect_stdout(io.StringIO()) as out,
            redirect_stderr(io.StringIO()) as err,
            self.assertRaises(SystemExit) as ctx,
        ):
            get_exponent(argparse.Namespace(size=None))
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(out.getvalue(), "\n")
        self.assertIn("pass SIZE as an argument", err.getvalue())
        self.assertIn("python3 sq.py 1", err.getvalue())


if __name__ == "__main__":
    unittest.main()
