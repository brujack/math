"""End-to-end test of the Python PR mutation gate on a real sq repo (spec R12, R13).

Builds a throwaway git repo from `git archive HEAD sq scripts`, commits a change,
then runs the gate's own scripts unmodified: plan, `make mutants-diff` for shard
0/1, verdict. Green case: a trailing space on sq.py line 18 keeps 13 of 164
mutants and all are killed. Red case: an untested branch whose mutants survive.

Real cosmic-ray runs take minutes, so this runs only when CI=true. Under CI=true
a missing cosmic-ray is a failure, never a skip.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TIMEOUT_S = 900
GIT_ENV_UNSET = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
IN_CI = os.environ.get("CI") == "true"
SKIP_REASON = "needs CI=true (real cosmic-ray runs take minutes; requires cosmic-ray)"

# Line 18 of sq.py is `    limit = 10**max_digits`; the red case inserts after it.
SQ_LIMIT_LINE = 18
RED_INSERT = ("    if max_digits == 123457:\n", "        return 0\n")
# A verdict survivor block is the status file indented four spaces.
SURVIVOR_RE = re.compile(
    r'^\s*sq\.py:[0-9]+ col [0-9]+ \S+ function "[^"]*"$', re.MULTILINE
)


def clean_env(home: Path) -> dict[str, str]:
    """Environment for every child: no inherited git state, HOME inside the fixture."""
    env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_UNSET}
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def run(
    args: list[str], cwd: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S,
        check=False,
    )


@unittest.skipUnless(IN_CI, SKIP_REASON)
class MutationPrPythonE2E(unittest.TestCase):
    def setUp(self) -> None:
        if shutil.which("cosmic-ray") is None:
            self.fail("cosmic-ray is not on PATH; CI=true requires it")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.root / "home").mkdir()
        self.env = clean_env(self.root / "home")
        self._build_base()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            self.repo,
            self.env,
        )
        self.assertEqual(result.returncode, 0, f"git {args} failed: {result.stderr}")
        return result

    def _build_base(self) -> None:
        archive = subprocess.run(
            ["git", "archive", "HEAD", "sq", "scripts"],
            cwd=REPO_ROOT,
            env=clean_env(self.root / "home"),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=TIMEOUT_S,
            check=True,
        )
        subprocess.run(
            ["tar", "-x", "-C", str(self.repo)],
            input=archive.stdout,
            env=self.env,
            capture_output=True,
            timeout=TIMEOUT_S,
            check=True,
        )
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD").stdout.strip()

    def _edit_sq(self, edit: str) -> None:
        sq = self.repo / "sq" / "sq.py"
        lines = sq.read_text().splitlines(keepends=True)
        if edit == "green":
            lines[SQ_LIMIT_LINE - 1] = lines[SQ_LIMIT_LINE - 1].rstrip("\n") + " \n"
        else:
            lines[SQ_LIMIT_LINE:SQ_LIMIT_LINE] = list(RED_INSERT)
        sq.write_text("".join(lines))
        self.git("add", "sq/sq.py")
        self.git("commit", "-q", "-m", edit)

    def _plan(self) -> Path:
        out = self.root / "plan"
        env = {**self.env, "PLAN_OUT": str(out)}
        result = run(
            ["scripts/mutation-pr-plan-python.sh", self.base, "sq"], self.repo, env
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return out / "plan.txt"

    def _diff(self) -> Path:
        diff = self.root / "sq.diff"
        result = run(
            ["scripts/mutation-pr-diff.sh", self.base, "sq", str(diff)],
            self.repo,
            self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return diff

    def _exec(self, diff: Path) -> Path:
        status_dir = self.root / "status"
        status_dir.mkdir()
        run(
            [
                "make",
                "-C",
                "sq",
                "mutants-diff",
                f"DIFF={diff}",
                "MUTANT_SHARD=0/1",
                f"STATUS_OUT={status_dir / 'sq-0'}",
            ],
            self.repo,
            self.env,
        )
        return status_dir

    def _verdict(
        self, plan: Path, status_dir: Path
    ) -> subprocess.CompletedProcess[str]:
        return run(
            [
                "scripts/mutation-pr-verdict-python.sh",
                "--expected-dirs",
                "sq",
                str(plan),
                str(status_dir),
            ],
            self.repo,
            self.env,
        )

    def test_green_trailing_space_keeps_13_and_all_killed(self) -> None:
        self._edit_sq("green")
        diff = self._diff()
        prune = run(
            ["make", "-C", "sq", "mutants-diff-plan", f"DIFF={diff}"],
            self.repo,
            self.env,
        )
        self.assertEqual(prune.returncode, 0, prune.stderr)
        self.assertIn("kept 13 of 164 (lines 1)", prune.stdout)

        plan = self._plan()
        self.assertEqual(plan.read_text(), "sq\tgreen\t13 mutants in 1 shards\n")

        verdict = self._verdict(plan, self._exec(diff))
        self.assertEqual(verdict.returncode, 0, verdict.stdout + verdict.stderr)
        self.assertIn("sq: green: 1 shards, 0 surviving, 13 killed", verdict.stdout)

    def test_red_untested_branch_reports_full_key_survivor(self) -> None:
        self._edit_sq("red")
        diff = self._diff()
        plan = self._plan()
        self.assertRegex(plan.read_text(), r"^sq\tgreen\t[0-9]+ mutants in 1 shards\n$")

        verdict = self._verdict(plan, self._exec(diff))
        self.assertEqual(verdict.returncode, 1, verdict.stdout + verdict.stderr)
        self.assertIn("sq: red:", verdict.stdout)
        self.assertRegex(verdict.stdout, SURVIVOR_RE)
        self.assertIn("MUTANT_SHARD=0/1", verdict.stdout)


if __name__ == "__main__":
    unittest.main()
