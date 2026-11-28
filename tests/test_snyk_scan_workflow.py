"""Pins the snyk-scan job wiring: gate membership, scan step and judge step (ADR-0049)."""

import os
import pathlib
import subprocess
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "auto-merge.yml"
GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")


def load_jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def snyk_steps() -> list[dict]:
    return load_jobs()["snyk-scan"]["steps"]


def step_by_id(step_id: str) -> dict:
    found = [s for s in snyk_steps() if s.get("id") == step_id]
    assert len(found) == 1, f"expected one step with id {step_id}, got {len(found)}"
    return found[0]


def step_by_name(name: str) -> dict:
    found = [s for s in snyk_steps() if s.get("name") == name]
    assert len(found) == 1, f"expected one step named {name}, got {len(found)}"
    return found[0]


class SnykScanWorkflowTests(unittest.TestCase):
    def test_auto_merge_needs_snyk_scan(self):
        self.assertIn("snyk-scan", load_jobs()["auto-merge"]["needs"])

    def test_no_continue_on_error_on_job_or_steps(self):
        job = load_jobs()["snyk-scan"]
        self.assertNotIn("continue-on-error", job)
        for step in job["steps"]:
            self.assertNotIn("continue-on-error", step, step.get("name"))

    def test_checkout_fetches_two_commits(self):
        checkout = snyk_steps()[0]
        self.assertTrue(checkout["uses"].startswith("actions/checkout@"))
        self.assertEqual(checkout["with"]["fetch-depth"], 2)

    def test_token_only_in_the_scan_step(self):
        holders = [s for s in snyk_steps() if "SNYK_TOKEN" in s.get("env", {})]
        self.assertEqual([s.get("id") for s in holders], ["scan"])

    def test_scan_step_run(self):
        lines = [
            ln.strip() for ln in step_by_id("scan")["run"].splitlines() if ln.strip()
        ]
        self.assertEqual(
            lines,
            [
                "set +e",
                (
                    'snyk code test --sarif-file-output="${RUNNER_TEMP}/snyk.sarif"'
                    ' > "${RUNNER_TEMP}/snyk.txt"'
                ),
                "rc=$?",
                'if [ "${rc}" -gt 1 ]; then',
                'echo "::error::snyk-scan: scanner error (exit ${rc})"',
                'cat "${RUNNER_TEMP}/snyk.txt"',
                "exit 1",
                "fi",
                "exit 0",
            ],
        )

    def test_judge_step(self):
        step = step_by_name("Judge findings against the files this PR changes")
        self.assertEqual(
            step["if"], "${{ !cancelled() && steps.scan.outcome == 'success' }}"
        )
        lines = [ln.strip() for ln in step["run"].splitlines() if ln.strip()]
        self.assertEqual(
            lines,
            [
                "set +e",
                (
                    'python3 -I scripts/snyk_file_touch.py < "${RUNNER_TEMP}/snyk.sarif"'
                    ' > "${RUNNER_TEMP}/judge.txt"'
                ),
                "rc=$?",
                'cat "${RUNNER_TEMP}/judge.txt"',
                'grep -v \'^::error\' "${RUNNER_TEMP}/judge.txt" >> "${GITHUB_STEP_SUMMARY}"',
                'exit "${rc}"',
            ],
        )

    def test_no_snyk_policy_files_tracked(self):
        env = {k: v for k, v in os.environ.items() if k not in GIT_ENV_VARS}
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            check=True,
        ).stdout.decode()
        banned = [
            p for p in out.split("\0") if os.path.basename(p) in (".snyk", ".dcignore")
        ]
        self.assertEqual(banned, [])


if __name__ == "__main__":
    unittest.main()
