"""`continue-on-error` is allowed only where this file records why.

A step or job with `continue-on-error: true` is green whatever it does. Before this
test, 21 such places existed and three kinds hid real outcomes: a release step whose
rejected CHANGELOG push read as success (ADR-0029), eight "Benchmark (timeout gate)"
steps that could never fail, and nine pip-audit steps where a crash or an empty audit
looked like a clean one. What remains is listed below with its reason, and anything
new must be added here, in review, with one.
"""

import collections
import pathlib
import re
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
ACTIONS_DIR = REPO_ROOT / ".github" / "actions"

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
}

# Rendered from one template, so every Python workflow carries the same step.
for _project in (
    "amicable",
    "collatz",
    "e",
    "factorial",
    "fib",
    "perfect-numbers",
    "pi",
    "sq",
):
    ALLOWED[(f"{_project}-py.yml", "test", "Generate test metrics")] = (
        "informational timing metrics with if: always(); they gate nothing"
    )


# Two lines: the wrapper writes pip-audit-summary.md, then shell appends it, so the
# Python never opens a path taken from the environment (Snyk Code's traversal rule).
WRAPPER_RUN = (
    'python3 "${GITHUB_WORKSPACE}/scripts/pip_audit_advisory.py"\n'
    'cat pip-audit-summary.md >> "$GITHUB_STEP_SUMMARY"'
)
_PIP_AUDIT = re.compile(r"pip[-_]audit")
# Shell command boundaries, including & and command substitution ($(...), `...`).
_COMMAND_SEPARATORS = re.compile(r"&&|\|\||;|\||&|`|\$\(|\)")


def pip_audit_calls(run):
    """Return each shell command in run text that invokes pip-audit.

    A command that installs pip-audit (`pip install ... pip-audit`) is not a call;
    any other command naming pip-audit or pip_audit is, wherever it sits on a line.
    """
    calls = []
    for line in run.splitlines():
        for command in _COMMAND_SEPARATORS.split(line):
            command = command.strip()
            if _PIP_AUDIT.search(command) and not command.startswith("pip install"):
                calls.append(command)
    return calls


def step_lists():
    """Yield (file, job id, steps) for every workflow job and composite action.

    Covers *.yml and *.yaml workflows plus .github/actions/*/action.y*ml, whose
    steps live under runs.steps; a composite action's job id is "<composite>".
    """
    paths = sorted(
        [*WORKFLOWS_DIR.glob("*.yml"), *WORKFLOWS_DIR.glob("*.yaml")]
    ) + sorted(ACTIONS_DIR.glob("*/action.y*ml"))
    for path in paths:
        doc = yaml.safe_load(path.read_text()) or {}
        label = str(path.relative_to(REPO_ROOT / ".github"))
        label = label.removeprefix("workflows/")
        if path.parent.parent == ACTIONS_DIR:
            yield label, "<composite>", None, (doc.get("runs") or {}).get("steps") or []
            continue
        for job_id, job in (doc.get("jobs") or {}).items():
            if isinstance(job, dict):
                yield label, job_id, job, job.get("steps") or []


def step_key(index, step):
    # An unnamed step keys on its position, so it can never share the job's key
    # (None) or another step's.
    return step.get("id") or step.get("name") or f"step[{index}]"


def continue_on_error_sites():
    """Return a Counter of (file, job, step key or None) continue-on-error sites."""
    sites = collections.Counter()
    for label, job_id, job, steps in step_lists():
        if job is not None and job.get("continue-on-error"):
            sites[(label, job_id, None)] += 1
        for index, step in enumerate(steps):
            if isinstance(step, dict) and step.get("continue-on-error"):
                sites[(label, job_id, step_key(index, step))] += 1
    return sites


def workflow_steps():
    for label, job_id, _job, steps in step_lists():
        for step in steps:
            if isinstance(step, dict):
                yield label, job_id, step


class TestContinueOnErrorAllowList(unittest.TestCase):
    def test_every_continue_on_error_is_allow_listed(self):
        unlisted = [site for site in continue_on_error_sites() if site not in ALLOWED]
        self.assertEqual(unlisted, [], "continue-on-error without a recorded reason")

    def test_each_allow_list_entry_matches_exactly_once(self):
        # A second step with the same name or id in the same job must not inherit
        # an existing entry's reason.
        sites = continue_on_error_sites()
        counts = {entry: sites[entry] for entry in ALLOWED}
        self.assertEqual(counts, dict.fromkeys(ALLOWED, 1))

    def test_sites_scan_sees_jobs_and_steps(self):
        # Positive control: an empty scan would pass both tests above.
        sites = continue_on_error_sites()
        self.assertIn(("auto-merge.yml", "snyk-scan", None), sites)
        self.assertIn(("mutation-testing.yml", "notify", "dl"), sites)

    def test_scan_reaches_composite_actions(self):
        labels = {label for label, *_ in step_lists()}
        self.assertIn("actions/sbom-sign/action.yml", labels)

    def test_unnamed_step_does_not_collide_with_the_job_key(self):
        self.assertEqual(step_key(3, {"uses": "x/y@v1"}), "step[3]")
        self.assertNotEqual(step_key(0, {}), None)


class TestPipAuditRunsThroughTheAdvisoryWrapper(unittest.TestCase):
    def test_every_pip_audit_call_is_exactly_the_wrapper(self):
        audit_steps = []
        for label, job_id, step in workflow_steps():
            run = str(step.get("run") or "")
            # An audit action (uses: pypa/gh-action-pip-audit) has no run text, so it
            # can never equal the wrapper and fails below.
            if (
                pip_audit_calls(run)
                or _PIP_AUDIT.search(str(step.get("uses", "")))
                or step.get("name") == "Run pip-audit"
            ):
                audit_steps.append((label, job_id, step.get("name"), run.strip()))
        self.assertEqual(
            len(audit_steps),
            9,
            f"{audit_steps}"
            "; when adding a Python sub-project, update this count with its workflow",
        )
        for label, _job, step_name, run in audit_steps:
            with self.subTest(workflow=label, step=step_name):
                self.assertEqual(run, WRAPPER_RUN)

    def test_detector_finds_evasive_calls(self):
        cases = {
            "python3 -m pip_audit": ["python3 -m pip_audit"],
            "pip install x && pip-audit": ["pip-audit"],
            "pip-audit || true": ["pip-audit"],
            "true; pip-audit -r req.txt": ["pip-audit -r req.txt"],
            "pip install x & pip-audit": ["pip-audit"],
            "echo $(pip-audit)": ["pip-audit"],
            "pip install ruff pip-audit pytest": [],
            # The summary append names the file, so it is a "call" too; the step
            # must still equal WRAPPER_RUN exactly.
            WRAPPER_RUN: WRAPPER_RUN.splitlines(),
        }
        for run, expected in cases.items():
            with self.subTest(run=run):
                self.assertEqual(pip_audit_calls(run), expected)


SETUP_PYTHON = "actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0"


class TestPipAuditAuditsAProjectInterpreter(unittest.TestCase):
    def test_setup_python_precedes_every_pip_audit_step(self):
        # Without it, pip install and pip-audit run against the runner's system
        # Python: measured 2026-10-24, ~107 packages with 95 vulnerabilities and 11
        # skipped, all from apt-installed packages, burying the project's own.
        checked = 0
        for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
            workflow = yaml.safe_load(path.read_text()) or {}
            for job_id, job in (workflow.get("jobs") or {}).items():
                steps = [
                    s for s in (job or {}).get("steps") or [] if isinstance(s, dict)
                ]
                names = [s.get("name") for s in steps]
                if "Run pip-audit" not in names:
                    continue
                checked += 1
                with self.subTest(workflow=path.name, job=job_id):
                    setup = [
                        i
                        for i, s in enumerate(steps)
                        if str(s.get("uses", "")).startswith(SETUP_PYTHON)
                    ]
                    self.assertEqual(len(setup), 1, "one pinned setup-python step")
                    self.assertEqual(
                        str(steps[setup[0]].get("with", {}).get("python-version")),
                        "3.14",
                    )
                    self.assertLess(
                        setup[0], names.index("Install Python dependencies")
                    )
        self.assertEqual(
            checked,
            9,
            "when adding a Python sub-project, update this count with its workflow",
        )


class TestNoBenchmarkStepInPythonWorkflows(unittest.TestCase):
    def test_no_benchmark_timeout_gate_step_remains(self):
        # The step was removed in favour of the CLI contract's --smoke run; a
        # return would be a second, unmasked-or-masked benchmark path.
        names = [
            name
            for name, _, step in workflow_steps()
            if step.get("name") == "Benchmark (timeout gate)"
        ]
        self.assertEqual(names, [])


if __name__ == "__main__":
    unittest.main()
