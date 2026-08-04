#!/usr/bin/env python3
"""Unit tests for fib.py."""

import argparse
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st

import fib
from fib import generate_fibonacci, get_exponent, main, parse_args


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

    def test_out_of_range_exit_code_is_1(self):
        # sys.exit(1) must use code 1 specifically, not 0 or 2.
        with self.assertRaises(SystemExit) as cm:
            get_exponent(self._args(6))
        self.assertEqual(cm.exception.code, 1)


class TestGetExponentInteractive(unittest.TestCase):
    """Cover the interactive prompt branch of get_exponent (args.exponent is None)."""

    def _args_none(self):
        return argparse.Namespace(exponent=None)

    def test_interactive_valid_first_try(self):
        with patch("builtins.input", side_effect=["3"]), redirect_stdout(io.StringIO()):
            self.assertEqual(get_exponent(self._args_none()), 3)

    def test_interactive_low_boundary(self):
        with patch("builtins.input", side_effect=["1"]), redirect_stdout(io.StringIO()):
            self.assertEqual(get_exponent(self._args_none()), 1)

    def test_interactive_high_boundary(self):
        with patch("builtins.input", side_effect=["5"]), redirect_stdout(io.StringIO()):
            self.assertEqual(get_exponent(self._args_none()), 5)

    def test_interactive_out_of_range_then_valid(self):
        with (
            patch("builtins.input", side_effect=["6", "2"]),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(get_exponent(self._args_none()), 2)

    def test_interactive_zero_then_valid(self):
        with (
            patch("builtins.input", side_effect=["0", "1"]),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(get_exponent(self._args_none()), 1)

    def test_interactive_non_integer_then_valid(self):
        with (
            patch("builtins.input", side_effect=["abc", "3"]),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(get_exponent(self._args_none()), 3)


class TestMain(unittest.TestCase):
    """Cover main() — small-output branch (X<=2), large-output streaming (X==3),
    and the X>=4 confirmation prompt (both yes and no paths)."""

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

    def test_small_x_display_branch(self):
        # X=1, user chooses "y" → display all values, do not write file
        out = self._run_main(["fib.py", "1"], ["y"])
        self.assertIn("Fibonacci", out)
        self.assertIn("1\n1\n2\n3\n5\n8", out)
        self.assertFalse(os.path.exists("fib_1e1.txt"))

    def test_small_x_save_branch(self):
        # X=2 → max_digits=10^2=100. User chooses "n" → file is written.
        self._run_main(["fib.py", "2"], ["n"])
        self.assertTrue(os.path.exists("fib_1e2.txt"))
        with open("fib_1e2.txt") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[:3], ["1", "1", "2"])
        self.assertLess(int(lines[-1]), 10**100)

    def test_small_x_save_count_reported(self):
        # x=2 → max_digits=10^2=100 → limit=10^100; exactly 480 Fibonacci numbers
        # have fewer than 100 decimal digits.
        # Verifies max_digits=10**x and count increment are both correct.
        out = self._run_main(["fib.py", "2"], ["n"])
        self.assertIn("Found 480", out)

    def test_small_x_uses_buffered_branch_for_x2(self):
        # x=2 must take the small (buffered) branch, not the streaming branch.
        # The streaming (large) branch prints "Saving to fib_1e2.txt..." (with ellipsis)
        # before writing; the small branch never prints that string.
        out = self._run_main(["fib.py", "2"], ["n"])
        self.assertNotIn("Saving to fib_1e2.txt...", out)

    def test_streaming_branch_x3(self):
        # X=3 → streaming-to-file path, no warning, no input prompts
        self._run_main(["fib.py", "3"], [])
        self.assertTrue(os.path.exists("fib_1e3.txt"))
        with open("fib_1e3.txt") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[0], "1")
        # last value must have <= 1000 digits
        self.assertLessEqual(len(lines[-1]), 1000)

    def test_streaming_x3_count_reported(self):
        # x=3 → max_digits=10^3=1000 → limit=10^1000; exactly 4,786 Fibonacci numbers
        # have fewer than 1,000 decimal digits.
        # Verifies count init (=0) and count increment (+=1) in the streaming branch.
        out = self._run_main(["fib.py", "3"], [])
        self.assertIn("Found 4,786", out)

    def test_large_x_warning_aborts_on_no(self):
        # X=4 → warning + confirmation; "n" returns without writing a file
        out = self._run_main(["fib.py", "4"], ["n"])
        self.assertIn("Warning", out)
        self.assertFalse(os.path.exists("fib_1e4.txt"))

    def test_large_x_warning_aborts_on_blank(self):
        # X=4 → warning, blank confirmation also returns
        out = self._run_main(["fib.py", "5"], [""])
        self.assertIn("Warning", out)
        self.assertFalse(os.path.exists("fib_1e5.txt"))


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
        sys.argv = ["fib.py", "1"]
        try:
            buf = io.StringIO()
            with (
                patch("builtins.input", return_value="n"),
                patch(
                    "builtins.open",
                    side_effect=PermissionError(
                        "[Errno 13] Permission denied: 'fib_1e1.txt'"
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
        sys.argv = ["fib.py", "1"]
        try:
            buf = io.StringIO()
            with (
                patch("fib.generate_fibonacci", side_effect=KeyboardInterrupt),
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
        # Invoking fib.py as a script triggers the entry-point guard.
        import subprocess

        proc = subprocess.run(
            [sys.executable, fib.__file__, "1"],
            input="n\n",
            capture_output=True,
            text=True,
            timeout=10,
            cwd=tempfile.gettempdir(),
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("Fibonacci", proc.stdout)


class TestFibonacciProperties(unittest.TestCase):
    @given(st.integers(min_value=1, max_value=6))
    def test_recurrence_holds(self, max_digits):
        seq = list(generate_fibonacci(max_digits))
        for i in range(2, len(seq)):
            self.assertEqual(seq[i], seq[i - 1] + seq[i - 2])

    @given(st.integers(min_value=1, max_value=6))
    def test_all_elements_positive(self, max_digits):
        for n in generate_fibonacci(max_digits):
            self.assertGreater(n, 0)

    @given(st.integers(min_value=2, max_value=6))
    def test_strictly_increasing_after_first_two(self, max_digits):
        seq = list(generate_fibonacci(max_digits))
        for i in range(2, len(seq)):
            self.assertGreater(seq[i], seq[i - 1])


if __name__ == "__main__":
    unittest.main()
