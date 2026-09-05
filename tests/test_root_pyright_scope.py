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


# `cwd=` alone is not isolation: an exported GIT_DIR (leaked into a pre-push hook when
# pushing from a worktree, per shell.md) still wins over `-C`/`cwd`, silently reading a
# different repository's index. Strip the repo-location vars for every git call so this
# test resolves the worktree it actually runs in, not whatever a leaked hook exported.
_GIT_ENV_STRIP = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")


def _clean_git_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_STRIP}


def _git_ls_files(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", *args, *INCLUDE_PATHSPECS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=_clean_git_env(),
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

    def test_include_and_exclude_are_pinned_by_identity(self):
        # A count-only check (assertion 2 below) pins CARDINALITY, not IDENTITY: it
        # would not notice pyright's default `**/.*` exclude being restored on a day
        # `.claude/scripts` happens to hold as many files as it drops. Pin the actual
        # lists. `**/.*` is deliberately absent from exclude — measured: 10 files
        # analysed with the default exclude absent (today's config), 9 with it
        # restored — because exclude beats include and `.claude/scripts` starts with
        # a dot, so the whole directory (currently one file) would be dropped.
        config = _load_config()
        self.assertEqual(config.get("include"), ["scripts", "tests", ".claude/scripts"])
        self.assertEqual(config.get("exclude"), ["**/node_modules", "**/__pycache__"])


class TestRootPyrightCoverage(unittest.TestCase):
    """Assertion 2: pyright's filesAnalyzed equals tracked + untracked .py files."""

    @classmethod
    def setUpClass(cls):
        cls.pyright_bin = shutil.which("pyright")
        # Presence, not truthiness: GitHub Actions sets CI=true, but a set-and-falsy
        # value (CI="", CI=0) must still fail closed rather than silently skip — only
        # a wholly UNSET CI means "not running under a CI runner at all".
        if cls.pyright_bin is None and "CI" in os.environ:
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

        pyright_bin = self.pyright_bin
        if pyright_bin is None:
            self.fail("pyright not found on PATH")  # unreachable: setUp already skipped
        result = subprocess.run(
            [pyright_bin, "--outputjson"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            # A crash or a bad flag empties stdout; a bare JSONDecodeError here names
            # neither the return code nor pyright's own diagnosis, and points a
            # reader at the file-count denominator when the fault is pyright itself.
            self.fail(
                f"pyright --outputjson produced no JSON (rc={result.returncode}): "
                f"{result.stderr[:500]}"
            )
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
