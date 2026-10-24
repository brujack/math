"""`continue-on-error` is allowed only where this file records why.

A step or job with `continue-on-error: true` is green whatever it does. Before this
test, 21 such places existed and three kinds hid real outcomes: a release step whose
rejected CHANGELOG push read as success (ADR-0029), eight "Benchmark (timeout gate)"
steps that could never fail, and nine pip-audit steps where a crash or an empty audit
looked like a clean one. What remains is listed below with its reason, and anything
new must be added here, in review, with one.
"""

import pathlib
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# (workflow file, job id, step id or name, or None for the job itself) -> reason
ALLOWED = {
    ("auto-merge.yml", "snyk-scan", None): (
        "advisory SAST, not in the auto-merge gate (CLAUDE.md); a finding must not block"
    ),
    ("mutation-testing.yml", "notify", "dl"): (
        "the artifact is absent when the mutants job died early; notify reads "
        "steps.dl.outcome and the breadcrumb to report that cause"
    ),
    ("mutation-testing-python.yml", "notify", "dl"): (
        "same as mutation-testing.yml: notify reports a missing artifact itself"
    ),
    ("factorial-py.yml", "test", "Generate test metrics"): (
        "informational timing metrics with if: always(); they gate nothing"
    ),
}


def continue_on_error_sites():
    """Yield (file, job, step key or None) for every continue-on-error in a workflow."""
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        workflow = yaml.safe_load(path.read_text()) or {}
        for job_id, job in (workflow.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            if job.get("continue-on-error"):
                yield path.name, job_id, None
            for step in job.get("steps") or []:
                if isinstance(step, dict) and step.get("continue-on-error"):
                    yield path.name, job_id, step.get("id") or step.get("name")


def workflow_steps():
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        workflow = yaml.safe_load(path.read_text()) or {}
        for job_id, job in (workflow.get("jobs") or {}).items():
            for step in (job or {}).get("steps") or []:
                if isinstance(step, dict):
                    yield path.name, job_id, step


class TestContinueOnErrorAllowList(unittest.TestCase):
    def test_every_continue_on_error_is_allow_listed(self):
        unlisted = [site for site in continue_on_error_sites() if site not in ALLOWED]
        self.assertEqual(unlisted, [], "continue-on-error without a recorded reason")

    def test_every_allow_list_entry_still_exists(self):
        sites = set(continue_on_error_sites())
        stale = [entry for entry in ALLOWED if entry not in sites]
        self.assertEqual(
            stale, [], "allow-list entries that no longer match a workflow"
        )

    def test_sites_scan_sees_jobs_and_steps(self):
        # Positive control: an empty scan would pass both tests above.
        sites = set(continue_on_error_sites())
        self.assertIn(("auto-merge.yml", "snyk-scan", None), sites)
        self.assertIn(("mutation-testing.yml", "notify", "dl"), sites)


class TestPipAuditRunsThroughTheAdvisoryWrapper(unittest.TestCase):
    def test_no_step_runs_bare_pip_audit(self):
        audit_steps = []
        for name, _job_id, step in workflow_steps():
            run = step.get("run") or ""
            if step.get("name") == "Run pip-audit" or (
                "pip-audit" in run and "pip install" not in run
            ):
                audit_steps.append((name, _job_id, step.get("name"), run.strip()))
        self.assertEqual(len(audit_steps), 9, audit_steps)
        for name, _job, step_name, run in audit_steps:
            with self.subTest(workflow=name, step=step_name):
                self.assertIn("scripts/pip_audit_advisory.py", run)


class TestBenchmarkGatesCanFail(unittest.TestCase):
    def test_benchmark_steps_exist_and_are_not_masked(self):
        found = [
            (name, step)
            for name, _, step in workflow_steps()
            if step.get("name") == "Benchmark (timeout gate)"
        ]
        self.assertEqual(len(found), 8, [n for n, _ in found])
        for name, step in found:
            with self.subTest(workflow=name):
                self.assertFalse(step.get("continue-on-error"))


if __name__ == "__main__":
    unittest.main()
