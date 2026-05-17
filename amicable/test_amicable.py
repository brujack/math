import unittest

from amicable import proper_divisor_sum_sieve


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


if __name__ == "__main__":
    unittest.main()
