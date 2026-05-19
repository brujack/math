import io
import os
import tempfile
import unittest
import unittest.mock

from amicable import (
    find_amicable_pairs,
    get_exponent,
    main,
    parse_args,
    proper_divisor_sum_sieve,
)

from hypothesis import given
from hypothesis import strategies as st


class TestProperDivisorSumSieve(unittest.TestCase):
    def test_zero_and_one(self):
        s = proper_divisor_sum_sieve(6)
        self.assertEqual(s[0], 0)
        self.assertEqual(s[1], 0)

    def test_small_values(self):
        s = proper_divisor_sum_sieve(10)
        self.assertEqual(s[2], 1)   # only proper divisor of 2 is 1
        self.assertEqual(s[4], 3)   # 1+2
        self.assertEqual(s[6], 6)   # 1+2+3 — perfect number
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


class TestParseArgs(unittest.TestCase):
    def test_with_n(self):
        args = parse_args(["3"])
        self.assertEqual(args.N, 3)

    def test_without_n(self):
        args = parse_args([])
        self.assertIsNone(args.N)


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
        args = parse_args([])
        with unittest.mock.patch("builtins.input", return_value="3"):
            self.assertEqual(get_exponent(args), 3)


class TestMain(unittest.TestCase):
    def test_n3_writes_file_and_stdout(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            os.chdir(d)
            try:
                with unittest.mock.patch("sys.argv", ["amicable.py", "3"]):
                    with unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                        main()
                        output = mock_out.getvalue()
                self.assertIn("220 284", output)
                with open("amicable_1e3.txt") as f:
                    self.assertEqual(f.read(), "220 284\n")
            finally:
                os.chdir(old)

    def test_n1_empty_output(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.getcwd()
            os.chdir(d)
            try:
                with unittest.mock.patch("sys.argv", ["amicable.py", "1"]):
                    with unittest.mock.patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                        main()
                        self.assertEqual(mock_out.getvalue(), "")
                with open("amicable_1e1.txt") as f:
                    self.assertEqual(f.read(), "")
            finally:
                os.chdir(old)

    def test_permission_error_exits(self):
        with unittest.mock.patch("sys.argv", ["amicable.py", "1"]):
            with unittest.mock.patch("builtins.open", side_effect=PermissionError):
                with self.assertRaises(SystemExit):
                    main()


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
        for a, b in find_amicable_pairs(limit):
            self.assertLessEqual(b, limit)


if __name__ == "__main__":
    unittest.main()
