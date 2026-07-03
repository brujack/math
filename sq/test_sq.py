#!/usr/bin/env python3
"""Unit tests for sq.py."""

import argparse
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import sq as sq_module
from sq import generate_squares, parse_args, get_exponent, main

from hypothesis import given
from hypothesis import strategies as st


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
    """Cover the interactive prompt branch (args.exponent is None)."""

    def _args_none(self):
        return argparse.Namespace(exponent=None)

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
    """Cover main() — file is always written; user is prompted to also display."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def _run_main(self, argv, inputs):
        old_argv = sys.argv
        sys.argv = argv
        try:
            with (
                patch("builtins.input", side_effect=inputs),
                redirect_stdout(io.StringIO()) as buf,
            ):
                main()
            return buf.getvalue()
        finally:
            sys.argv = old_argv

    def test_main_writes_file_and_skips_display_on_no(self):
        out = self._run_main(["sq.py", "1"], ["n"])
        self.assertIn("Perfect Square", out)
        self.assertTrue(os.path.exists("sq_1e1.txt"))
        with open("sq_1e1.txt") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[0], "1 | 1")
        self.assertEqual(lines[-1], "9999800001 | 99999")
        # display branch was NOT taken — squares not echoed to stdout
        self.assertNotIn("9999800001 | 99999", out)

    def test_main_writes_file_and_displays_on_yes(self):
        out = self._run_main(["sq.py", "1"], ["y"])
        self.assertTrue(os.path.exists("sq_1e1.txt"))
        # Display branch echoed the buffer to stdout
        self.assertIn("1 | 1", out)
        self.assertIn("9999800001 | 99999", out)

    def test_main_idempotent_overwrites_file(self):
        # First run
        self._run_main(["sq.py", "1"], ["n"])
        first_size = os.path.getsize("sq_1e1.txt")
        # Second run with same args produces an identical file
        self._run_main(["sq.py", "1"], ["n"])
        self.assertEqual(os.path.getsize("sq_1e1.txt"), first_size)

    def test_main_reports_correct_count(self):
        # main() prints "Found N,NNN perfect squares" — assert exact count so
        # mutations to count initialisation (0→1/-1) or increment (+=1→+=0/2)
        # are detected.
        out = self._run_main(["sq.py", "1"], ["n"])
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
        old_argv = sys.argv
        sys.argv = ["sq.py", "1"]
        try:
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
                    main()
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("Error", buf.getvalue())
        finally:
            sys.argv = old_argv


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
        old_argv = sys.argv
        sys.argv = ["sq.py", "1"]
        try:
            buf = io.StringIO()
            with (
                patch("sq.generate_squares", side_effect=KeyboardInterrupt),
                redirect_stdout(buf),
            ):
                with self.assertRaises(SystemExit) as cm:
                    main()
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("interrupted", buf.getvalue())
        finally:
            sys.argv = old_argv


class TestEntryPoint(unittest.TestCase):
    """Cover the `if __name__ == "__main__"` guard."""

    def test_module_runs_via_subprocess(self):
        import subprocess

        proc = subprocess.run(
            [sys.executable, sq_module.__file__, "1"],
            input="n\n",
            capture_output=True,
            text=True,
            timeout=10,
            cwd=tempfile.gettempdir(),
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
        for n, root in generate_squares(max_digits):
            self.assertGreater(n, 0)

    @given(st.integers(min_value=1, max_value=6))
    def test_strictly_increasing(self, max_digits):
        seq = [n for n, _ in generate_squares(max_digits)]
        for i in range(1, len(seq)):
            self.assertGreater(seq[i], seq[i - 1])


if __name__ == "__main__":
    unittest.main()
