"""The `Publish coverage badge` step is advisory: a coverage-data failure never fails CI.

The step is extracted from the rendered workflows and run under `bash -e` with
`python3`, `git` and `sleep` replaced by stubs on PATH, so nothing reaches a real
remote. The step hard-codes absolute `/tmp/` paths; the test rewrites them into its
own temp dir so nothing is written outside it, and asserts the real ones stay absent.
"""

import os
import pathlib
import subprocess
import tempfile
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
STEP_NAME = "Publish coverage badge"
REAL_PATHS = (pathlib.Path("/tmp/cov-data"), pathlib.Path("/tmp/cov.json"))
UNAVAILABLE = "badge not published"

PYTHON_STUB = """\
#!/usr/bin/env bash
case "$1" in
  -m) exit 0 ;;
  -c) printf '95\\n'; exit 0 ;;
esac
exit 0
"""

GIT_STUB = """\
#!/usr/bin/env bash
printf '%s\\n' "$*" >> "${STUB_LOG}"
case "$1" in
  fetch) exit "${STUB_FETCH_RC:-0}" ;;
  worktree) exit "${STUB_WORKTREE_RC:-0}" ;;
  push) exit "${STUB_PUSH_RC:-0}" ;;
  diff) exit "${STUB_DIFF_RC:-0}" ;;
esac
exit 0
"""

SLEEP_STUB = "#!/usr/bin/env bash\nexit 0\n"


def badge_step(workflow: str) -> str:
    """Return the run script of the badge step in a rendered workflow."""
    data = yaml.safe_load((WORKFLOWS / workflow).read_text())
    for job in data["jobs"].values():
        for step in job["steps"]:
            if step.get("name") == STEP_NAME:
                return str(step["run"])
    raise AssertionError(f"{workflow} has no {STEP_NAME!r} step")


class Shared:
    """Namespace hiding the abstract base from unittest discovery."""

    class BadgeStepCase(unittest.TestCase):
        workflow = ""
        crate_dir = "amicable"

        def run_step(self, **env_rc):
            """Run the step in a sandbox; return (CompletedProcess, git log lines)."""
            existed = [p.exists() for p in REAL_PATHS]
            with tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                bin_dir = root / "bin"
                bin_dir.mkdir()
                for name, body in (
                    ("python3", PYTHON_STUB),
                    ("git", GIT_STUB),
                    ("sleep", SLEEP_STUB),
                ):
                    stub = bin_dir / name
                    stub.write_text(body)
                    stub.chmod(0o755)
                (root / self.crate_dir).mkdir()
                log = root / "git.log"
                script = badge_step(self.workflow).replace("/tmp/", f"{root}/")
                env = {
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                    "HOME": str(root),
                    "STUB_LOG": str(log),
                    **{k: str(v) for k, v in env_rc.items()},
                }
                result = subprocess.run(
                    ["bash", "-e", "-c", script],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    stdin=subprocess.DEVNULL,
                    timeout=60,
                    check=False,
                )
                lines = log.read_text().splitlines() if log.exists() else []
            for path, was_there in zip(REAL_PATHS, existed, strict=True):
                if not was_there:
                    self.assertFalse(path.exists(), f"test leaked a write to {path}")
            return result, lines

        def test_worktree_failure_after_successful_fetch_is_advisory(self):
            result, lines = self.run_step(STUB_FETCH_RC=0, STUB_WORKTREE_RC=1)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(UNAVAILABLE, result.stdout)
            self.assertFalse([ln for ln in lines if ln.startswith(("push", "pull"))])

        def test_orphan_failure_after_failed_fetch_is_advisory(self):
            result, lines = self.run_step(STUB_FETCH_RC=1, STUB_WORKTREE_RC=1)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(UNAVAILABLE, result.stdout)
            self.assertTrue(any("--orphan" in ln for ln in lines))
            self.assertFalse([ln for ln in lines if ln.startswith(("push", "pull"))])

        def test_three_failed_pushes_exit_zero_with_exactly_three_attempts(self):
            result, lines = self.run_step(
                STUB_FETCH_RC=0, STUB_WORKTREE_RC=0, STUB_PUSH_RC=1, STUB_DIFF_RC=1
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len([ln for ln in lines if ln.startswith("push")]), 3)

        def test_clean_run_pushes_once_and_does_not_report_unavailable(self):
            result, lines = self.run_step(STUB_DIFF_RC=1)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(UNAVAILABLE, result.stdout)
            self.assertEqual(len([ln for ln in lines if ln.startswith("push")]), 1)

        def test_unused_loop_variable_is_an_underscore(self):
            step = badge_step(self.workflow)
            self.assertIn("for _ in 1 2 3", step)
            self.assertNotIn("for i in", step)


class TestRustBadgeStep(Shared.BadgeStepCase):
    workflow = "amicable-rs.yml"


class TestPythonBadgeStep(Shared.BadgeStepCase):
    workflow = "amicable-py.yml"


if __name__ == "__main__":
    unittest.main()
