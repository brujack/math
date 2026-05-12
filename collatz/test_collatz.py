import array
import unittest

from collatz import collatz_length, collatz_next


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


if __name__ == "__main__":
    unittest.main()
