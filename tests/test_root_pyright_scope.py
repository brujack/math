"""Guard the root pyrightconfig.json's mode and file-coverage against silent drift.

Two independent assertions, each with a distinct failure mode:

1. Mode — a parse of the JSON config, asserting typeCheckingMode/reportMissingImports
   have not been silently downgraded. A file-count check alone cannot see this.
2. Coverage — an equality between pyright's own reported filesAnalyzed and an
   independently-derived count of tracked-plus-untracked .py files under the three
   include roots. This is deliberately an equality, not `>=` or a Python glob
   reimplementation of pyright's include/exclude semantics — see CLAUDE.md and the
   design notes for why those alternatives were tried and refuted.
"""

import json
import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "pyrightconfig.json"
INCLUDE_PATHSPECS = ["tests/*.py", "scripts/*.py", ".claude/scripts/*.py"]


def _load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _git_ls_files(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", *args, *INCLUDE_PATHSPECS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


class TestRootPyrightMode(unittest.TestCase):
    """Assertion 1: the config's type-checking mode has not been silently downgraded."""

    def test_config_exists(self):
        self.assertTrue(CONFIG_PATH.is_file(), f"expected {CONFIG_PATH} to exist")

    def test_type_checking_mode_is_standard(self):
        config = _load_config()
        self.assertEqual(config.get("typeCheckingMode"), "standard")

    def test_report_missing_imports_is_true(self):
        config = _load_config()
        self.assertIs(config.get("reportMissingImports"), True)


class TestRootPyrightCoverage(unittest.TestCase):
    """Assertion 2: pyright's filesAnalyzed equals tracked + untracked .py files."""

    @classmethod
    def setUpClass(cls):
        cls.pyright_bin = shutil.which("pyright")
        if cls.pyright_bin is None and os.environ.get("CI"):
            raise RuntimeError("pyright is required in CI but was not found on PATH")

    def setUp(self):
        if self.pyright_bin is None:
            self.skipTest("pyright not found on PATH")

    def test_files_analyzed_equals_tracked_plus_untracked(self):
        tracked = _git_ls_files()
        untracked = _git_ls_files("-o")
        expected_files = sorted(set(tracked) | set(untracked))

        # Vacuity floor: an empty tracked set would make the equality below
        # trivially satisfiable by an empty pyright run.
        self.assertGreater(
            len(tracked),
            0,
            "expected at least one tracked .py file under the include roots",
        )

        result = subprocess.run(
            [self.pyright_bin, "--outputjson"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        report = json.loads(result.stdout)
        files_analyzed = report["summary"]["filesAnalyzed"]

        self.assertEqual(
            files_analyzed,
            len(expected_files),
            f"pyright analysed {files_analyzed} files; expected "
            f"{len(expected_files)} from tracked+untracked {INCLUDE_PATHSPECS}: "
            f"{expected_files}",
        )


if __name__ == "__main__":
    unittest.main()
