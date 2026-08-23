#!/usr/bin/env python3
import os
import sys
import time
import unittest
from io import StringIO
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.time_tests import TimingResult, compute_slow, fetch_historical


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
        for ms in result.timings.values():
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


class TestFetchHistoricalErrorPath(unittest.TestCase):
    """fetch_historical had no tests at all and swallowed every exception.

    The assertion that discriminates is the WARNING, not the skip: the previous
    `except Exception: continue` also skipped cleanly and returned [], so a test
    asserting only "returns []" passes identically against the defect. What
    changed is that an unreadable artifact is now reported instead of silently
    shrinking the sample the statistics are computed over.
    """

    def _run_with_unreadable_artifact(self):
        # First gh call lists one artifact id; second "downloads" it and reports
        # success without creating the file, so ZipFile raises FileNotFoundError
        # -- an OSError, one of the types the narrowed except names.
        calls = [
            mock.Mock(returncode=0, stdout="[1]"),
            mock.Mock(returncode=0, stdout=""),
        ]
        buf = StringIO()
        with (
            mock.patch("scripts.time_tests.subprocess.run", side_effect=calls),
            mock.patch("sys.stderr", buf),
        ):
            runs = fetch_historical("math", "test-metrics")
        return runs, buf.getvalue()

    def test_unreadable_artifact_is_skipped_not_fatal(self):
        runs, _ = self._run_with_unreadable_artifact()
        self.assertEqual(runs, [])

    def test_unreadable_artifact_is_reported(self):
        _, err = self._run_with_unreadable_artifact()
        self.assertIn("warning", err)
        self.assertIn("skipping unreadable artifact", err)

    def test_no_artifacts_returns_empty_without_warning(self):
        # Boundary: the empty-list path must not emit a warning, so a quiet run
        # stays quiet and the warning above means something when it appears.
        buf = StringIO()
        with (
            mock.patch(
                "scripts.time_tests.subprocess.run",
                return_value=mock.Mock(returncode=0, stdout="[]"),
            ),
            mock.patch("sys.stderr", buf),
        ):
            self.assertEqual(fetch_historical("math", "test-metrics"), [])
        self.assertEqual(buf.getvalue(), "")
