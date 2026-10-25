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


class TestMainImportsModuleFromWorkingDirectory(unittest.TestCase):
    """The workflows run `python3 <repo>/scripts/time_tests.py --module test_<m>`
    from the project directory. Python puts the script's own directory on
    sys.path, not the working directory, so the test module has to be found
    from the working directory explicitly or every run records one
    `_FailedTest` instead of the suite."""

    _SCRIPT = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts",
        "time_tests.py",
    )

    def _run(self, module):
        import json
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "test_sample.py"), "w") as f:
                f.write(
                    "import unittest\n"
                    "class T(unittest.TestCase):\n"
                    "    def test_a(self):\n        pass\n"
                    "    def test_b(self):\n        pass\n"
                )
            bindir = os.path.join(d, "bin")
            os.mkdir(bindir)
            gh = os.path.join(bindir, "gh")
            with open(gh, "w") as f:
                f.write("#!/bin/sh\nexit 1\n")
            os.chmod(gh, 0o755)
            env = dict(
                os.environ, PATH=bindir + os.pathsep + os.environ.get("PATH", "")
            )
            env.pop("PYTHONPATH", None)
            r = subprocess.run(
                [
                    sys.executable,
                    self._SCRIPT,
                    "--repo",
                    "math",
                    "--run-id",
                    "1",
                    "--module",
                    module,
                ],
                cwd=d,
                env=env,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
            metrics = None
            path = os.path.join(d, "test-metrics.json")
            if os.path.exists(path):
                with open(path) as f:
                    metrics = json.load(f)
            return r, metrics

    def test_module_in_working_directory_is_loaded(self):
        r, metrics = self._run("test_sample")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        assert metrics is not None
        self.assertEqual(metrics["stats"]["total"], 2)
        self.assertFalse(any("_FailedTest" in name for name in metrics["all_timings"]))

    def test_missing_module_fails(self):
        r, metrics = self._run("test_absent")
        self.assertEqual(r.returncode, 1)
        assert metrics is not None
        self.assertEqual(metrics["stats"]["failed"], 1)
