#!/usr/bin/env python3
import json
import math
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.time_tests import TimingResult, compute_slow


class TestTimingResult(unittest.TestCase):
    def _suite(self):
        class Fast(unittest.TestCase):
            def test_quick(self):
                pass

        class Slow(unittest.TestCase):
            def test_slow(self):
                time.sleep(0.01)

        class Fail(unittest.TestCase):
            def test_fail(self):
                self.fail("intentional")

        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        suite.addTest(loader.loadTestsFromTestCase(Fast))
        suite.addTest(loader.loadTestsFromTestCase(Slow))
        suite.addTest(loader.loadTestsFromTestCase(Fail))
        return suite

    def test_records_timing_per_test(self):
        result = TimingResult()
        self._suite().run(result)
        self.assertGreater(len(result.timings), 0)
        for name, ms in result.timings.items():
            self.assertIsInstance(ms, float)
            self.assertGreaterEqual(ms, 0.0)

    def test_slow_test_has_higher_timing(self):
        result = TimingResult()
        self._suite().run(result)
        timings = result.timings
        slow_key = next((k for k in timings if "slow" in k), None)
        fast_key = next((k for k in timings if "quick" in k), None)
        if slow_key and fast_key:
            self.assertGreater(timings[slow_key], timings[fast_key])

    def test_counts_failures(self):
        result = TimingResult()
        self._suite().run(result)
        self.assertEqual(len(result.failures), 1)

    def test_total_tests_run(self):
        result = TimingResult()
        self._suite().run(result)
        self.assertEqual(result.testsRun, 3)


class TestComputeSlow(unittest.TestCase):
    def test_no_history_returns_empty(self):
        self.assertEqual(compute_slow({"a": 500.0}, []), [])

    def test_detects_slow_test(self):
        hist = [{"all_timings": {"a": 100.0}} for _ in range(5)]
        result = compute_slow({"a": 600.0}, hist)
        self.assertEqual(len(result), 1)
        self.assertGreaterEqual(result[0]["z_score"], 2.0)

    def test_normal_test_not_flagged(self):
        hist = [{"all_timings": {"a": ms}} for ms in [100, 102, 98, 101, 100]]
        result = compute_slow({"a": 103.0}, hist)
        self.assertEqual(result, [])

    def test_insufficient_history_skipped(self):
        hist = [{"all_timings": {"a": 100.0}}, {"all_timings": {"a": 200.0}}]
        self.assertEqual(compute_slow({"a": 9999.0}, hist), [])


if __name__ == "__main__":
    unittest.main()
