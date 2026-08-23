#!/usr/bin/env python3
"""Error-path coverage for scripts/test_metrics.py.

scripts/test_metrics.py and scripts/time_tests.py carry a `fetch_historical`
that is byte-identical apart from a default argument, and neither had any test
before this file. Both had their blind `except Exception: continue` narrowed in
the same change, so both need the same error-path test -- covering one and not
the other would leave the asymmetry that gets found later.

The duplication itself is recorded in docs/superpowers/README.md's Backlog
rather than fixed here: merging two scripts is its own change with its own
callers to check.
"""

import os
import sys
import unittest
from io import StringIO
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from scripts.test_metrics import fetch_historical


class TestFetchHistoricalErrorPath(unittest.TestCase):
    def _run_with_unreadable_artifact(self):
        calls = [
            mock.Mock(returncode=0, stdout="[1]"),
            mock.Mock(returncode=0, stdout=""),
        ]
        buf = StringIO()
        with (
            mock.patch("scripts.test_metrics.subprocess.run", side_effect=calls),
            mock.patch("sys.stderr", buf),
        ):
            runs = fetch_historical("math")
        return runs, buf.getvalue()

    def test_unreadable_artifact_is_skipped_not_fatal(self):
        runs, _ = self._run_with_unreadable_artifact()
        self.assertEqual(runs, [])

    def test_unreadable_artifact_is_reported(self):
        # The discriminating assertion: the previous blind except also returned
        # [] here, so only the warning distinguishes fixed from broken.
        _, err = self._run_with_unreadable_artifact()
        self.assertIn("skipping unreadable artifact", err)

    def test_no_artifacts_returns_empty_without_warning(self):
        buf = StringIO()
        with (
            mock.patch(
                "scripts.test_metrics.subprocess.run",
                return_value=mock.Mock(returncode=0, stdout="[]"),
            ),
            mock.patch("sys.stderr", buf),
        ):
            self.assertEqual(fetch_historical("math"), [])
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
