"""Tests for scripts/claude_md_budget.py: the CLAUDE.md byte-ceiling gate."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "claude_md_budget.py"
CEILING = 30_000
ADR_PATH = "docs/adr/0028-claude-md-size-ceiling.md"
_GIT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_VARS}
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    return env


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        env=_env(),
        check=True,
        capture_output=True,
        stdin=subprocess.DEVNULL,
    )


class BudgetTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        _git(self.repo, "init", "-q")

    def commit(self, claude_md: bytes | None) -> None:
        if claude_md is None:
            (self.repo / "other.txt").write_text("x")
            _git(self.repo, "add", "other.txt")
        else:
            (self.repo / "CLAUDE.md").write_bytes(claude_md)
            _git(self.repo, "add", "CLAUDE.md")
        _git(self.repo, "commit", "-q", "-m", "c")

    def run_script(
        self, *args: str, cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=cwd or self.repo,
            env=_env(),
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )

    def test_exactly_at_ceiling_allowed(self) -> None:
        self.commit(b"a" * CEILING)
        self.assertEqual(self.run_script("HEAD").returncode, 0)

    def test_one_over_ceiling_refused(self) -> None:
        self.commit(b"a" * (CEILING + 1))
        result = self.run_script("HEAD")
        self.assertEqual(result.returncode, 1)
        self.assertIn("30001", result.stderr)
        self.assertIn("30000", result.stderr)
        self.assertIn(ADR_PATH, result.stderr)
        self.assertIn("ai-config/docs/knowledge/math-", result.stderr)

    def test_no_claude_md_allowed(self) -> None:
        self.commit(None)
        self.assertEqual(self.run_script("HEAD").returncode, 0)

    def test_unknown_revision_exits_2(self) -> None:
        self.commit(b"a")
        result = self.run_script("no-such-rev")
        self.assertEqual(result.returncode, 2)
        self.assertTrue(result.stderr.strip())

    def test_counts_bytes_not_characters(self) -> None:
        text = "é" * 15_001  # 15,001 characters, 30,002 bytes
        self.commit(text.encode("utf-8"))
        result = self.run_script("HEAD")
        self.assertEqual(result.returncode, 1)
        self.assertIn("30002", result.stderr)

    def test_no_argument_exits_2(self) -> None:
        self.commit(b"a")
        self.assertEqual(self.run_script().returncode, 2)

    def test_extra_argument_exits_2(self) -> None:
        self.commit(b"a")
        self.assertEqual(self.run_script("HEAD", "extra").returncode, 2)

    def test_subdirectory_run_sees_root_claude_md(self) -> None:
        self.commit(b"a" * (CEILING + 1))
        sub = self.repo / "sub"
        sub.mkdir()
        self.assertEqual(self.run_script("HEAD", cwd=sub).returncode, 1)

    def test_subdirectory_run_absent_allowed(self) -> None:
        self.commit(None)
        sub = self.repo / "sub"
        sub.mkdir()
        self.assertEqual(self.run_script("HEAD", cwd=sub).returncode, 0)

    def test_unreadable_claude_md_blob_exits_2(self) -> None:
        # ls-tree lists the dangling gitlink; git show of it then fails.
        self.commit(None)
        _git(
            self.repo,
            "update-index",
            "--add",
            "--cacheinfo",
            "160000,1111111111111111111111111111111111111111,CLAUDE.md",
        )
        _git(self.repo, "commit", "-q", "-m", "gitlink")
        self.assertEqual(self.run_script("HEAD").returncode, 2)


if __name__ == "__main__":
    unittest.main()
