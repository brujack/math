"""Prove the crate-relative PR diff makes cargo-mutants select mutants.

cargo-mutants runs inside the crate dir and matches `--in-diff` paths against paths
relative to it. `scripts/mutation-pr-diff.sh` writes such a diff; a repo-root-relative
diff of the same change selects nothing, which the negative control pins so the
positive test cannot pass vacuously.
"""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "mutation-pr-diff.sh"
CRATE = "factorial/factorial-rs"
LIB = "src/lib.rs"
EDIT_LINE = "    while p * p <= n {"
CARGO_TIMEOUT_S = 600
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
GIT_IDENTITY = ("-c", "user.name=t", "-c", "user.email=t@t")


def clean_git_env():
    """Return os.environ minus the GIT_* vars a worktree hook exports."""
    return {k: v for k, v in os.environ.items() if k not in GIT_ENV_VARS}


def run(cmd, cwd, timeout=CARGO_TIMEOUT_S):
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=clean_git_env(),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )


def run_ok(cmd, cwd):
    proc = run(cmd, cwd)
    if proc.returncode != 0:
        raise AssertionError(f"{cmd} failed: {proc.stderr}")
    return proc


def git(tmp, *args):
    return run_ok(["git", *GIT_IDENTITY, *args], tmp)


def tools_missing():
    return [t for t in ("cargo", "cargo-mutants") if shutil.which(t) is None]


class InDiffListsMutantsTests(unittest.TestCase):
    def setUp(self):
        missing = tools_missing()
        if missing:
            message = f"{', '.join(missing)} not installed"
            if os.environ.get("CI") == "true":
                self.fail(message)
            self.skipTest(message)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = pathlib.Path(self._tmp.name)
        self.crate = self.tmp / CRATE
        self._build_repo()

    def _build_repo(self):
        archive = subprocess.run(
            ["git", "archive", "HEAD", CRATE],
            cwd=REPO_ROOT,
            env=clean_git_env(),
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=True,
        )
        subprocess.run(
            ["tar", "-x"],
            cwd=self.tmp,
            input=archive.stdout,
            capture_output=True,
            check=True,
        )
        git(self.tmp, "init", "-q")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-q", "-m", "base")
        lib = self.crate / LIB
        text = lib.read_text()
        self.assertEqual(text.count(EDIT_LINE + "\n"), 1)
        lib.write_text(text.replace(EDIT_LINE + "\n", EDIT_LINE + " \n"))
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-q", "-m", "touch sieve loop")

    def _list_in_diff(self, diff):
        return run(["cargo", "mutants", "--list", "--in-diff", str(diff)], self.crate)

    def test_crate_relative_diff_lists_sieve_mutants(self):
        diff = self.tmp / "d.diff"
        run_ok(["bash", str(SCRIPT), "HEAD~1", CRATE, str(diff)], self.tmp)
        plus_lines = [
            ln for ln in diff.read_text().splitlines() if ln.startswith("+++")
        ]
        self.assertEqual(plus_lines, [f"+++ b/{LIB}"])
        proc = self._list_in_diff(diff)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(
            any("sieve" in ln for ln in proc.stdout.splitlines()), proc.stdout
        )

    def test_root_relative_diff_lists_no_sieve_mutants(self):
        diff = self.tmp / "root.diff"
        proc = git(self.tmp, "diff", "--no-color", "HEAD~1", "--", CRATE)
        diff.write_text(proc.stdout)
        self.assertIn(f"+++ b/{CRATE}/{LIB}", diff.read_text())
        listed = self._list_in_diff(diff)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertFalse(
            any("sieve" in ln for ln in listed.stdout.splitlines()), listed.stdout
        )


if __name__ == "__main__":
    unittest.main()
