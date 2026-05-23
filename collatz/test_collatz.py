import argparse
import array
import io
import os
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout

from collatz import collatz_length, collatz_next, generate_records, get_exponent, main

from hypothesis import given
from hypothesis import strategies as st


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
        cache = self._make_cache(6)   # indices 0..5, limit = 5
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
        return argparse.Namespace(exponent=exponent)

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

    def test_interactive_invalid_then_valid(self):
        with unittest.mock.patch("builtins.input", side_effect=["0", "abc", "3"]), \
             unittest.mock.patch("builtins.print"):
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
        with unittest.mock.patch("sys.argv", ["collatz.py", "1"]), \
             redirect_stdout(io.StringIO()):
            main()
        with open("collatz_1e1.txt") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines, ["1 0", "2 1", "3 7", "6 8", "7 16", "9 19"])

    def test_n3_file_contains_27(self):
        with unittest.mock.patch("sys.argv", ["collatz.py", "3"]), \
             redirect_stdout(io.StringIO()):
            main()
        with open("collatz_1e3.txt") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines[0], "1 0")
        self.assertIn("27 111", lines)

    def test_keyboard_interrupt_exits_1(self):
        with unittest.mock.patch("sys.argv", ["collatz.py", "1"]), \
             unittest.mock.patch(
                 "collatz.generate_records", side_effect=KeyboardInterrupt
             ), \
             redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 1)

    def test_permission_error_exits_1(self):
        with unittest.mock.patch("sys.argv", ["collatz.py", "1"]), \
             unittest.mock.patch(
                 "builtins.open", side_effect=PermissionError("Permission denied")
             ), \
             redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 1)


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
            [sys.executable, str(module_path), "4"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=tempfile.gettempdir(),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("6171", proc.stdout)