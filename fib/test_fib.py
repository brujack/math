"""Unit tests for fib.py."""

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

import fib
from fib import (
    LARGE_RUN_THRESHOLD,
    SMOKE_SIZE,
    generate_fibonacci,
    get_exponent,
    main,
    parse_args,
    refuse_large_run,
)

assert LARGE_RUN_THRESHOLD is not None
_LARGE: int = LARGE_RUN_THRESHOLD


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
    def test_no_args_on_tty(self):
        with patch("sys.stdin.isatty", return_value=True):
            args = parse_args([])
        self.assertIsNone(args.size)
        self.assertFalse(args.show)
        self.assertFalse(args.yes)

    def test_with_valid_arg(self):
        self.assertEqual(parse_args(["3"]).size, 3)

    def test_flags_parse(self):
        args = parse_args(["3", "--show", "--yes"])
        self.assertTrue(args.show)
        self.assertTrue(args.yes)

    def test_invalid_non_integer_arg_exits(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parse_args(["abc"])

    def test_bare_non_tty_run_exits_2(self):
        with (
            patch("sys.stdin.isatty", return_value=False),
            redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as cm,
        ):
            parse_args([])
        self.assertEqual(cm.exception.code, 2)

    def test_smoke_sets_size_and_clears_show(self):
        args = parse_args(["--smoke", "--show"])
        self.assertEqual(args.size, SMOKE_SIZE)
        self.assertFalse(args.show)

    def test_smoke_with_size_exits_2(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            parse_args(["--smoke", "3"])
        self.assertEqual(cm.exception.code, 2)


class TestCliContractConstants(unittest.TestCase):
    def test_smoke_size(self):
        self.assertEqual(SMOKE_SIZE, 3)

    def test_large_run_threshold(self):
        self.assertEqual(LARGE_RUN_THRESHOLD, 4)


class TestRefuseLargeRun(unittest.TestCase):
    def test_one_below_threshold_passes(self):
        refuse_large_run(_LARGE - 1, False)

    def test_at_threshold_without_yes_exits_1_naming_yes(self):
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            refuse_large_run(_LARGE, False)
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("--yes", err.getvalue())

    def test_at_threshold_with_yes_passes(self):
        refuse_large_run(_LARGE, True)


class TestGetExponent(unittest.TestCase):
    def _args(self, size, yes=False):
        return argparse.Namespace(size=size, yes=yes)

    def test_valid_low_boundary(self):
        self.assertEqual(get_exponent(self._args(1)), 1)

    def test_valid_high_boundary(self):
        self.assertEqual(get_exponent(self._args(5, yes=True)), 5)

    def test_valid_midrange(self):
        self.assertEqual(get_exponent(self._args(3)), 3)

    def test_large_without_yes_exits_1(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            get_exponent(self._args(4))
        self.assertEqual(cm.exception.code, 1)

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
    """Cover the interactive prompt branch of get_exponent (args.size is None)."""

    def _args_none(self):
        return argparse.Namespace(size=None)

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
    """main(): buffered (X<=2), streaming (X==3), --show, and the large-run gate."""

    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.mkdtemp()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        for f in os.listdir(self._tmp):
            os.unlink(os.path.join(self._tmp, f))
        os.rmdir(self._tmp)

    def _run_main(self, argv, inputs=()):
        with (
            patch("builtins.input", side_effect=list(inputs)),
            redirect_stdout(io.StringIO()) as buf,
        ):
            main(argv)
        return buf.getvalue()

    def test_small_x_writes_file_without_prompt(self):
        out = self._run_main(["1"])
        with open("fib_1e1.txt") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[:6], ["1", "1", "2", "3", "5", "8"])
        self.assertNotIn(lines[-1], out.splitlines())

    def test_small_x_show_prints_each_line_and_still_writes(self):
        out = self._run_main(["1", "--show"])
        with open("fib_1e1.txt") as f:
            lines = f.read().splitlines()
        self.assertIn("\n".join(lines) + "\n", out)
        self.assertGreater(len(lines), 6)

    def test_small_x_file_content(self):
        self._run_main(["2"])
        with open("fib_1e2.txt") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[:3], ["1", "1", "2"])
        self.assertLess(int(lines[-1]), 10**100)

    def test_small_x_count_reported(self):
        # exactly 480 Fibonacci numbers have fewer than 100 decimal digits.
        out = self._run_main(["2"])
        self.assertIn("Found 480", out)

    def test_small_x_uses_buffered_branch_for_x2(self):
        out = self._run_main(["2"])
        self.assertNotIn("Saving to fib_1e2.txt...", out)

    def test_streaming_branch_x3(self):
        self._run_main(["3"])
        with open("fib_1e3.txt") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[0], "1")
        self.assertLessEqual(len(lines[-1]), 1000)

    def test_streaming_x3_count_reported(self):
        # exactly 4,786 Fibonacci numbers have fewer than 1,000 decimal digits.
        out = self._run_main(["3"])
        self.assertIn("Found 4,786", out)

    def test_streaming_x3_show_prints_longest_line(self):
        out = self._run_main(["3", "--show"])
        with open("fib_1e3.txt") as f:
            longest = max(f.read().splitlines(), key=len)
        self.assertIn(longest, out.splitlines())

    def test_streaming_x3_without_show_hides_longest_line(self):
        out = self._run_main(["3"])
        with open("fib_1e3.txt") as f:
            longest = max(f.read().splitlines(), key=len)
        self.assertNotIn(longest, out.splitlines())

    def test_smoke_runs_at_smoke_size(self):
        self._run_main(["--smoke"])
        self.assertTrue(os.path.exists(f"fib_1e{SMOKE_SIZE}.txt"))

    def test_x4_writes_numbers_past_python_int_str_limit(self):
        # Python 3.11+ refuses str() on ints over 4,300 digits unless main() lifts
        # the cap. One 5,000-digit value stands in for a real X=4 run's output.
        big = 10**4999 + 7
        self.addCleanup(sys.set_int_max_str_digits, sys.get_int_max_str_digits())
        sys.set_int_max_str_digits(4300)
        with patch.object(fib, "generate_fibonacci", return_value=iter([1, big])):
            self._run_main(["4", "--yes"])
        with open("fib_1e4.txt") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines, ["1", str(big)])
        self.assertEqual(len(lines[-1]), 5000)

    def test_large_x_with_yes_proceeds_without_prompting(self):
        with patch.object(
            fib, "generate_fibonacci", return_value=iter([1, 1, 2])
        ) as gen:
            self._run_main([str(_LARGE), "--yes"])
        gen.assert_called_once_with(10**_LARGE)
        with open(f"fib_1e{_LARGE}.txt") as f:
            self.assertEqual(f.read().split(), ["1", "1", "2"])

    def test_large_x_without_yes_exits_1_and_does_not_generate(self):
        with (
            patch.object(fib, "generate_fibonacci") as gen,
            redirect_stderr(io.StringIO()) as err,
            self.assertRaises(SystemExit) as cm,
        ):
            self._run_main([str(_LARGE)])
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("--yes", err.getvalue())
        gen.assert_not_called()
        self.assertEqual(os.listdir("."), [])

    def test_threshold_boundary_x5_also_refused(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self._run_main(["5"])
        self.assertEqual(os.listdir("."), [])

    def test_interactive_large_x_warns_and_aborts_on_no(self):
        with (
            patch.object(fib, "generate_fibonacci") as gen,
            patch("sys.stdin.isatty", return_value=True),
        ):
            out = self._run_main([], ["4", "n"])
        self.assertIn("Warning", out)
        gen.assert_not_called()
        self.assertFalse(os.path.exists("fib_1e4.txt"))

    def test_interactive_large_x_aborts_on_blank(self):
        with (
            patch.object(fib, "generate_fibonacci") as gen,
            patch("sys.stdin.isatty", return_value=True),
        ):
            out = self._run_main([], ["5", ""])
        self.assertIn("Warning", out)
        gen.assert_not_called()
        self.assertFalse(os.path.exists("fib_1e5.txt"))

    def test_refusal_happens_before_any_file_write(self):
        with (
            patch("builtins.open") as opened,
            patch.object(fib, "generate_fibonacci") as gen,
            redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            main([str(_LARGE)])
        opened.assert_not_called()
        gen.assert_not_called()

    def test_small_x_show_echo_precedes_summary(self):
        out = self._run_main(["1", "--show"])
        self.assertLess(out.index("\n1\n1\n2\n"), out.index("Found "))

    def test_interactive_large_x_proceeds_on_yes(self):
        with (
            patch.object(fib, "generate_fibonacci", return_value=iter([1, 1, 2])),
            patch("sys.stdin.isatty", return_value=True),
        ):
            self._run_main([], ["4", "y"])
        self.assertTrue(os.path.exists("fib_1e4.txt"))

    def test_rerun_overwrites_file(self):
        self._run_main(["1"])
        with open("fib_1e1.txt", "a") as f:
            f.write("junk\n")
        self._run_main(["1"])
        with open("fib_1e1.txt") as f:
            self.assertNotIn("junk", f.read())


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
                    "[Errno 13] Permission denied: 'fib_1e1.txt'"
                ),
            ),
            redirect_stdout(buf),
            self.assertRaises(SystemExit) as cm,
        ):
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
            patch("fib.generate_fibonacci", side_effect=KeyboardInterrupt),
            redirect_stdout(buf),
            self.assertRaises(SystemExit) as cm,
        ):
            main(["1"])
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("interrupted", buf.getvalue())


class TestEntryPoint(unittest.TestCase):
    """Cover the `if __name__ == "__main__"` guard."""

    def test_module_runs_via_subprocess(self):
        # Invoking fib.py as a script triggers the entry-point guard.
        import subprocess

        proc = subprocess.run(
            [sys.executable, fib.__file__, "1"],
            stdin=subprocess.DEVNULL,
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


class TestClosedStdin(unittest.TestCase):
    """Run non-interactively (stdin closed, as in CI) the CLI must not traceback."""

    def _run(self, *args):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, fib.__file__, *args],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=tmp,
                check=False,
            )
            files = sorted(os.listdir(tmp))
        return proc, files

    def test_small_x_needs_no_stdin_and_saves(self):
        proc, files = self._run("2")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(files, ["fib_1e2.txt"])

    def test_large_x_without_yes_is_refused_not_prompted(self):
        proc, files = self._run("4")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("--yes", proc.stderr)
        self.assertEqual(files, [])

    def test_bare_run_exits_2(self):
        proc, files = self._run()
        self.assertEqual(proc.returncode, 2, proc.stdout)
        self.assertEqual(files, [])

    def test_exponent_prompt_eof_exits_1_with_a_remedy(self):
        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("builtins.input", side_effect=EOFError),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()) as err,
            self.assertRaises(SystemExit) as ctx,
        ):
            main([])
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn(
            f"pass SIZE as an argument (e.g. python3 fib.py {SMOKE_SIZE})",
            err.getvalue(),
        )

    def test_exponent_prompt_eof_after_a_bad_answer_still_exits(self):
        with (
            patch("builtins.input", side_effect=["abc", EOFError]),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as ctx,
        ):
            get_exponent(argparse.Namespace(size=None))
        self.assertEqual(ctx.exception.code, 1)


class TestAskYes(unittest.TestCase):
    def _ask(self, side_effect):
        with (
            patch("builtins.input", side_effect=side_effect),
            redirect_stdout(io.StringIO()) as out,
        ):
            return fib.ask_yes("Q? "), out.getvalue()

    def test_eof_reads_as_no_and_ends_the_prompt_line(self):
        self.assertEqual(self._ask(EOFError), (False, "\n"))

    def test_yes_answers(self):
        for answer in ("y", "Y", " yes ", "YES"):
            with self.subTest(answer=answer):
                self.assertTrue(self._ask([answer])[0])

    def test_keyboard_interrupt_still_propagates(self):
        # main() turns Ctrl-C into exit 1; ask_yes must not swallow it as "no".
        with (
            patch("builtins.input", side_effect=KeyboardInterrupt),
            self.assertRaises(KeyboardInterrupt),
        ):
            fib.ask_yes("Q? ")

    def test_eof_at_exponent_prompt_ends_the_prompt_line_on_stdout(self):
        with (
            patch("builtins.input", side_effect=EOFError),
            redirect_stdout(io.StringIO()) as out,
            redirect_stderr(io.StringIO()) as err,
            self.assertRaises(SystemExit),
        ):
            fib.get_exponent(argparse.Namespace(size=None))
        self.assertEqual(out.getvalue(), "\n")
        self.assertTrue(err.getvalue().startswith("Error: no input"))

    def test_other_answers_are_no(self):
        for answer in ("", "n", "no", "yep", "y es"):
            with self.subTest(answer=answer):
                self.assertFalse(self._ask([answer])[0])


if __name__ == "__main__":
    unittest.main()
