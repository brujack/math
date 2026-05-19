import argparse
import io
import os
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout

from perfect_numbers import (
    generate_perfect_numbers,
    get_exponent,
    is_prime,
    lucas_lehmer,
    main,
    verify_perfect,
)

from hypothesis import given
from hypothesis import strategies as st

PERFECT_NUMBERS = {
    2: 6,
    3: 28,
    5: 496,
    7: 8128,
    13: 33550336,
    17: 8589869056,
    19: 137438691328,
}


class TestIsPrime(unittest.TestCase):
    def test_zero_not_prime(self):
        self.assertFalse(is_prime(0))

    def test_one_not_prime(self):
        self.assertFalse(is_prime(1))

    def test_negative_not_prime(self):
        self.assertFalse(is_prime(-7))

    def test_two_is_prime(self):
        self.assertTrue(is_prime(2))

    def test_even_composite_not_prime(self):
        self.assertFalse(is_prime(4))

    def test_small_primes(self):
        for p in [3, 5, 7, 11, 13, 17, 19, 23, 29, 31]:
            with self.subTest(p=p):
                self.assertTrue(is_prime(p))

    def test_small_composites(self):
        for n in [6, 8, 9, 10, 15, 25, 49]:
            with self.subTest(n=n):
                self.assertFalse(is_prime(n))

    def test_89_is_prime(self):
        self.assertTrue(is_prime(89))

    def test_91_is_composite(self):
        self.assertFalse(is_prime(91))  # 7 * 13


class TestLucasLehmer(unittest.TestCase):
    def test_p2_mersenne(self):
        self.assertTrue(lucas_lehmer(2))

    def test_known_mersenne_prime_exponents(self):
        for p in [3, 5, 7, 13, 17, 19, 31, 61, 89]:
            with self.subTest(p=p):
                self.assertTrue(lucas_lehmer(p), f"p={p} should be Mersenne prime")

    def test_known_non_mersenne_prime_exponents(self):
        for p in [11, 23, 29, 37, 41]:
            with self.subTest(p=p):
                self.assertFalse(lucas_lehmer(p), f"p={p} should not be Mersenne prime")


class TestVerifyPerfect(unittest.TestCase):
    def test_known_exponents_verify(self):
        for p in [2, 3, 5, 7, 13, 17, 19]:
            with self.subTest(p=p):
                self.assertTrue(verify_perfect(p))

    def test_sigma_equals_2n(self):
        for p in [2, 3, 5, 7]:
            mp = (1 << p) - 1
            n = (1 << (p - 1)) * mp
            sigma = mp * (mp + 1)
            self.assertEqual(sigma, 2 * n)


class TestGeneratePerfectNumbers(unittest.TestCase):
    def test_limit_below_6_yields_empty(self):
        self.assertEqual(list(generate_perfect_numbers(5)), [])

    def test_limit_1_yields_6(self):
        result = list(generate_perfect_numbers(10 ** 1))
        self.assertEqual(result, [(2, 6)])

    def test_limit_n4_yields_first_4(self):
        result = list(generate_perfect_numbers(10 ** 4))
        self.assertEqual([n for _, n in result], [6, 28, 496, 8128])

    def test_limit_n8_yields_5_numbers(self):
        result = list(generate_perfect_numbers(10 ** 8))
        self.assertEqual(len(result), 5)
        self.assertEqual(result[4][0], 13)

    def test_limit_n54_yields_all_10(self):
        result = list(generate_perfect_numbers(10 ** 54))
        self.assertEqual(len(result), 10)
        last_p, last_n = result[-1]
        self.assertEqual(last_p, 89)
        self.assertEqual(
            last_n,
            191561942608236107294793378084303638130997321548169216,
        )

    def test_results_in_ascending_order(self):
        result = list(generate_perfect_numbers(10 ** 20))
        ns = [n for _, n in result]
        self.assertEqual(ns, sorted(ns))


class TestGetExponent(unittest.TestCase):
    def _ns(self, exponent):
        return argparse.Namespace(exponent=exponent)

    def test_valid_minimum(self):
        self.assertEqual(get_exponent(self._ns(1)), 1)

    def test_valid_maximum(self):
        self.assertEqual(get_exponent(self._ns(54)), 54)

    def test_valid_mid(self):
        self.assertEqual(get_exponent(self._ns(10)), 10)

    def test_zero_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._ns(0))

    def test_55_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._ns(55))

    def test_negative_exits(self):
        with self.assertRaises(SystemExit):
            get_exponent(self._ns(-1))

    def test_interactive_valid_first_try(self):
        with unittest.mock.patch("builtins.input", return_value="8"):
            self.assertEqual(get_exponent(self._ns(None)), 8)

    def test_interactive_invalid_then_valid(self):
        with unittest.mock.patch("builtins.input", side_effect=["0", "abc", "5"]), \
             unittest.mock.patch("builtins.print"):
            self.assertEqual(get_exponent(self._ns(None)), 5)


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

    def test_n1_creates_file_with_6(self):
        with unittest.mock.patch("sys.argv", ["perfect_numbers.py", "1"]), \
             redirect_stdout(io.StringIO()):
            main()
        with open("perfect-numbers_1e1.txt") as f:
            self.assertEqual(f.read().splitlines(), ["6"])

    def test_n4_creates_file_with_4_numbers(self):
        with unittest.mock.patch("sys.argv", ["perfect_numbers.py", "4"]), \
             redirect_stdout(io.StringIO()):
            main()
        with open("perfect-numbers_1e4.txt") as f:
            self.assertEqual(f.read().splitlines(), ["6", "28", "496", "8128"])

    def test_keyboard_interrupt_exits_1(self):
        with unittest.mock.patch("sys.argv", ["perfect_numbers.py", "1"]), \
             unittest.mock.patch(
                 "perfect_numbers.lucas_lehmer", side_effect=KeyboardInterrupt
             ), \
             redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 1)

    def test_permission_error_exits_1(self):
        with unittest.mock.patch("sys.argv", ["perfect_numbers.py", "1"]), \
             unittest.mock.patch(
                 "builtins.open",
                 side_effect=PermissionError("Permission denied"),
             ), \
             redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                main()
        self.assertEqual(cm.exception.code, 1)


class TestPerfectNumbersProperties(unittest.TestCase):

    @given(st.integers(min_value=2, max_value=500))
    def test_even_composites_not_prime(self, n):
        self.assertFalse(is_prime(n * 2))

    @given(st.integers(min_value=0, max_value=500))
    def test_perfect_numbers_below_limit(self, limit):
        for _p, num in generate_perfect_numbers(limit):
            self.assertLess(num, limit)

    @given(st.integers(min_value=0, max_value=500))
    def test_perfect_numbers_positive(self, limit):
        for _p, num in generate_perfect_numbers(limit):
            self.assertGreater(num, 0)


if __name__ == "__main__":
    unittest.main()
