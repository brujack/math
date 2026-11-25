"""Tests for the zeta results page: fixtures and (later) the generator."""

import os
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "zeta_results"
REFINED_TABLE = FIXTURES / "tr3" / "zeta_1e3.txt"
EXPECTED_DATA_LINES = 649


def _clean_git_env() -> dict[str, str]:
    """Environment with the GIT_* variables a hook or worktree exports removed."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


class TestFixtures(unittest.TestCase):
    def test_refined_table_is_tracked_by_git(self) -> None:
        rel = REFINED_TABLE.relative_to(REPO_ROOT).as_posix()
        result = subprocess.run(
            ["git", "ls-files", rel],
            cwd=REPO_ROOT,
            env=_clean_git_env(),
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), rel)

    def test_refined_table_header_and_row_count(self) -> None:
        lines = REFINED_TABLE.read_text().splitlines()
        self.assertEqual(lines[0], "# n a b t_n w_n")
        self.assertEqual(len(lines) - 1, EXPECTED_DATA_LINES)

    def test_every_run_fixture_has_out_and_err(self) -> None:
        for run_id in ("t2", "t3", "tr3"):
            for name in ("out.txt", "err.txt"):
                self.assertTrue(
                    (FIXTURES / run_id / name).is_file(), f"{run_id}/{name}"
                )


if __name__ == "__main__":
    unittest.main()
