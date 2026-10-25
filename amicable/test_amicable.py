import io
import os
import tempfile
import unittest
import unittest.mock

from hypothesis import given
from hypothesis import strategies as st

import amicable
from amicable import (
    LARGE_RUN_THRESHOLD,
    SMOKE_SIZE,
    find_amicable_pairs,
    get_exponent,
    main,
    parse_args,
    proper_divisor_sum_sieve,
    refuse_large_run,
)


class TestProperDivisorSumSieve(unittest.TestCase):
    def test_zero_and_one(self):
        s = proper_divisor_sum_sieve(6)
        self.assertEqual(s[0], 0)
        self.assertEqual(s[1], 0)

    def test_small_values(self):
        s = proper_divisor_sum_sieve(10)
        self.assertEqual(s[2], 1)  # only proper divisor of 2 is 1
        self.assertEqual(s[4], 3)  # 1+2
        self.assertEqual(s[6], 6)  # 1+2+3 — perfect number
        self.assertEqual(s[10], 8)  # 1+2+5

    def test_amicable_values(self):
        s = proper_divisor_sum_sieve(285)
        self.assertEqual(s[220], 284)
        self.assertEqual(s[284], 220)

    def test_non_amicable(self):
        s = proper_divisor_sum_sieve(20)
        self.assertEqual(s[12], 16)
        self.assertEqual(s[16], 15)  # s[16] != 12, so (12,16) not amicable

    def test_length(self):
        s = proper_divisor_sum_sieve(10)
        self.assertEqual(len(s), 11)  # indices 0..10 inclusive


class TestFindAmicablePairs(unittest.TestCase):
    def test_no_pairs_small_limit(self):
        self.assertEqual(list(find_amicable_pairs(100)), [])

    def test_first_pair(self):
        pairs = list(find_amicable_pairs(284))
        self.assertEqual(pairs, [(220, 284)])

    def test_b_exceeds_limit_no_pair(self):
        # limit=219: b would be 284 > 219, so no pair
        self.assertEqual(list(find_amicable_pairs(219)), [])

    def test_two_pairs(self):
        pairs = list(find_amicable_pairs(1210))
        self.assertEqual(pairs, [(220, 284), (1184, 1210)])

    def test_perfect_number_excluded(self):
        # s(6)=6 — perfect number, must NOT appear as a pair
        pairs = list(find_amicable_pairs(10))
        self.assertEqual(pairs, [])

    def test_five_pairs_up_to_10000(self):
        pairs = list(find_amicable_pairs(10000))
        self.assertEqual(
            pairs,
            [(220, 284), (1184, 1210), (2620, 2924), (5020, 5564), (6232, 6368)],
        )
        self.assertEqual(pairs, sorted(pairs))


class TestCliContractConstants(unittest.TestCase):
    def test_smoke_size(self):
        self.assertEqual(SMOKE_SIZE, 5)

    def test_large_run_threshold(self):
        self.assertIsNone(LARGE_RUN_THRESHOLD)


class TestParseArgs(unittest.TestCase):
    def test_with_size(self):
        args = parse_args(["3"])
        self.assertEqual(args.size, 3)
        self.assertFalse(args.show)
        self.assertFalse(args.yes)
        self.assertFalse(args.smoke)

    def test_without_size_on_terminal(self):
        with unittest.mock.patch("sys.stdin.isatty", return_value=True):
            args = parse_args([])
        self.assertIsNone(args.size)

    def test_without_size_not_a_terminal_exits_2(self):
        with (
            unittest.mock.patch("sys.stdin.isatty", return_value=False),
            unittest.mock.patch("sys.stderr", new_callable=io.StringIO),
            self.assertRaises(SystemExit) as ctx,
        ):
            parse_args([])
        self.assertEqual(ctx.exception.code, 2)

    def test_show_and_yes_flags(self):
        args = parse_args(["3", "--show", "--yes"])
        self.assertTrue(args.show)
        self.assertTrue(args.yes)

    def test_smoke_sets_size_and_clears_show(self):
        args = parse_args(["--smoke", "--show"])
        self.assertEqual(args.size, SMOKE_SIZE)
        self.assertFalse(args.show)
        self.assertTrue(args.smoke)

    def test_smoke_with_size_exits_2(self):
        with (
            unittest.mock.patch("sys.stderr", new_callable=io.StringIO),
            self.assertRaises(SystemExit) as ctx,
        ):
            parse_args(["3", "--smoke"])
        self.assertEqual(ctx.exception.code, 2)


class TestRefuseLargeRun(unittest.TestCase):
    def test_no_threshold_never_refuses(self):
        refuse_large_run(7, False)
        refuse_large_run(7, True)

    def test_at_threshold_without_yes_exits_1(self):
        with (
            unittest.mock.patch.object(amicable, "LARGE_RUN_THRESHOLD", 5),
            unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as err,
            self.assertRaises(SystemExit) as ctx,
        ):
            refuse_large_run(5, False)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("--yes", err.getvalue())

    def test_at_threshold_with_yes_proceeds(self):
        with unittest.mock.patch.object(amicable, "LARGE_RUN_THRESHOLD", 5):
            refuse_large_run(5, True)

    def test_below_threshold_proceeds(self):
        with unittest.mock.patch.object(amicable, "LARGE_RUN_THRESHOLD", 5):
            refuse_large_run(4, False)


class TestGetExponent(unittest.TestCase):
    def test_valid_min(self):
        args = parse_args(["1"])
        self.assertEqual(get_exponent(args), 1)

    def test_valid_max(self):
        args = parse_args(["7"])
        self.assertEqual(get_exponent(args), 7)

    def test_zero_exits(self):
        args = parse_args(["0"])
        with self.assertRaises(SystemExit):
            get_exponent(args)

    def test_too_large_exits(self):
        args = parse_args(["8"])
        with self.assertRaises(SystemExit):
            get_exponent(args)

    def test_negative_exits(self):
        args = parse_args(["-1"])
        with self.assertRaises(SystemExit):
            get_exponent(args)

    def test_interactive_prompt(self):
        with unittest.mock.patch("sys.stdin.isatty", return_value=True):
            args = parse_args([])
        with unittest.mock.patch("builtins.input", return_value="3"):
            self.assertEqual(get_exponent(args), 3)

    def test_interactive_eof_exits_1_with_contract_message(self):
        with unittest.mock.patch("sys.stdin.isatty", return_value=True):
            args = parse_args([])
        with (
            unittest.mock.patch("builtins.input", side_effect=EOFError),
            unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as err,
            self.assertRaises(SystemExit) as ctx,
        ):
            get_exponent(args)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn(
            "no input; pass SIZE as an argument (e.g. python3 amicable.py 5)",
            err.getvalue(),
        )

    def test_interactive_non_integer_exits_1(self):
        with unittest.mock.patch("sys.stdin.isatty", return_value=True):
            args = parse_args([])
        with (
            unittest.mock.patch("builtins.input", return_value="abc"),
            unittest.mock.patch("sys.stderr", new_callable=io.StringIO) as err,
            self.assertRaises(SystemExit) as ctx,
        ):
            get_exponent(args)
        self.assertEqual(ctx.exception.code, 1)
        self.assertIn("Invalid input", err.getvalue())


class TestMain(unittest.TestCase):
    def _run_in_tmp(self, argv):
        """Run main(argv) in a temp dir; return (stdout, file contents or None)."""
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            os.chdir(d)
            try:
                with unittest.mock.patch(
                    "sys.stdout", new_callable=io.StringIO
                ) as mock_out:
                    main(argv)
                out = mock_out.getvalue()
                name = f"amicable_1e{argv[0]}.txt"
                content = None
                if os.path.exists(name):
                    with open(name) as f:
                        content = f.read()
                return out, content
            finally:
                os.chdir(old)

    def test_n3_writes_file_without_echoing_pairs(self):
        out, content = self._run_in_tmp(["3"])
        self.assertEqual(content, "220 284\n")
        self.assertNotIn("220 284", out.splitlines())
        self.assertIn("Found 1 amicable pairs up to 10^3", out)
        self.assertIn("Saved to amicable_1e3.txt", out)

    def test_n3_show_echoes_pair_verbatim(self):
        out, content = self._run_in_tmp(["3", "--show"])
        self.assertEqual(content, "220 284\n")
        self.assertIn("220 284", out.splitlines())

    def test_n1_empty_output(self):
        out, content = self._run_in_tmp(["1"])
        self.assertEqual(content, "")
        self.assertIn("Found 0 amicable pairs up to 10^1", out)

    def test_n1_show_prints_no_pair_lines(self):
        out, _ = self._run_in_tmp(["1", "--show"])
        self.assertEqual(len(out.splitlines()), 2)

    def test_smoke_runs_at_smoke_size(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            os.chdir(d)
            try:
                with unittest.mock.patch("sys.stdout", new_callable=io.StringIO):
                    main(["--smoke"])
                self.assertTrue(os.path.exists("amicable_1e5.txt"))
            finally:
                os.chdir(old)

    def test_rerun_overwrites_file(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            os.chdir(d)
            try:
                with open("amicable_1e3.txt", "w") as f:
                    f.write("stale\n")
                with unittest.mock.patch("sys.stdout", new_callable=io.StringIO):
                    main(["3"])
                with open("amicable_1e3.txt") as f:
                    self.assertEqual(f.read(), "220 284\n")
            finally:
                os.chdir(old)

    def test_refusal_happens_before_any_file_write(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            os.chdir(d)
            try:
                with (
                    unittest.mock.patch.object(amicable, "LARGE_RUN_THRESHOLD", 3),
                    unittest.mock.patch("sys.stderr", new_callable=io.StringIO),
                    self.assertRaises(SystemExit) as ctx,
                ):
                    main(["3"])
                self.assertEqual(ctx.exception.code, 1)
                self.assertEqual(os.listdir("."), [])
            finally:
                os.chdir(old)

    def test_permission_error_exits(self):
        with (
            unittest.mock.patch("builtins.open", side_effect=PermissionError),
            unittest.mock.patch("sys.stderr", new_callable=io.StringIO),
            self.assertRaises(SystemExit) as ctx,
        ):
            main(["1"])
        self.assertEqual(ctx.exception.code, 1)


class TestAmicableProperties(unittest.TestCase):
    @given(st.integers(min_value=4, max_value=500))
    def test_sieve_nonnegative(self, limit):
        sieve = proper_divisor_sum_sieve(limit)
        self.assertTrue(all(s >= 0 for s in sieve))

    @given(st.integers(min_value=4, max_value=500))
    def test_sieve_length(self, limit):
        sieve = proper_divisor_sum_sieve(limit)
        # sieve is indexed 0..limit inclusive, so length is limit + 1
        self.assertEqual(len(sieve), limit + 1)

    @given(st.integers(min_value=300, max_value=2_000))
    def test_pairs_ordered(self, limit):
        for a, b in find_amicable_pairs(limit):
            self.assertLess(a, b)

    @given(st.integers(min_value=300, max_value=2_000))
    def test_pairs_within_limit(self, limit):
        for _a, b in find_amicable_pairs(limit):
            self.assertLessEqual(b, limit)


if __name__ == "__main__":
    unittest.main()


class TestEntryPointGuard(unittest.TestCase):
    """Cover the `if __name__ == "__main__"` block."""

    def test_module_runs_via_subprocess(self):
        import pathlib
        import subprocess
        import sys

        module_path = pathlib.Path(__file__).parent / "amicable.py"
        proc = subprocess.run(
            [sys.executable, str(module_path), "3", "--show"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            cwd=tempfile.gettempdir(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("220", proc.stdout)
