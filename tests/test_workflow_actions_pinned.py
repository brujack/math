"""Every remote action a workflow or composite action uses is pinned to a commit SHA.

A tag or branch ref (`@v1`) can be moved by the action's owner, so the code that
runs with this repo's token is whatever that ref points at on the day of the run.
A 40-hex commit SHA cannot move. Local refs (`./...`) are this repo's own code and
are exempt. Anything else, including `docker://`, fails closed.

Parsed with yaml.safe_load rather than grepped, so a `uses:` inside a comment or a
`run:` block can neither satisfy nor trip the check.

Regression test for audit 2026-11-16 F1.
"""

import pathlib
import re
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
ACTIONS_DIR = REPO_ROOT / ".github" / "actions"

_PINNED_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}$")


def is_pinned_or_local(ref):
    """Return True when a `uses:` value is a local path or a remote ref pinned to a SHA."""
    if ref.startswith("./"):
        return True
    return _PINNED_RE.match(ref) is not None


def uses_refs(document):
    """Return every `uses:` value in a parsed workflow or composite action.

    Covers step-level `uses` in each job, job-level `uses` (reusable workflow
    calls) and step-level `uses` in a composite action's `runs.steps`.
    """
    refs = []
    if not isinstance(document, dict):
        return refs
    jobs = document.get("jobs") or {}
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        if "uses" in job:
            refs.append(str(job["uses"]))
        refs.extend(_step_refs(job.get("steps")))
    runs = document.get("runs")
    if isinstance(runs, dict):
        refs.extend(_step_refs(runs.get("steps")))
    return refs


def _step_refs(steps):
    return [
        str(step["uses"])
        for step in steps or []
        if isinstance(step, dict) and "uses" in step
    ]


def workflow_and_action_files():
    """Return every workflow and composite action definition file, sorted."""
    files = list(WORKFLOWS_DIR.glob("*.yml")) + list(WORKFLOWS_DIR.glob("*.yaml"))
    files += list(ACTIONS_DIR.glob("*/action.yml"))
    files += list(ACTIONS_DIR.glob("*/action.yaml"))
    return sorted(files)


class TestIsPinnedOrLocal(unittest.TestCase):
    def test_full_sha_is_pinned(self):
        self.assertTrue(is_pinned_or_local("actions/checkout@" + "a" * 40))

    def test_sub_path_action_with_sha_is_pinned(self):
        self.assertTrue(is_pinned_or_local("github/codeql-action/init@" + "0" * 40))

    def test_local_path_is_exempt(self):
        self.assertTrue(is_pinned_or_local("./.github/actions/sbom-sign"))

    def test_major_tag_is_rejected(self):
        self.assertFalse(
            is_pinned_or_local("benchmark-action/github-action-benchmark@v1")
        )

    def test_exact_version_tag_is_rejected(self):
        self.assertFalse(is_pinned_or_local("actions/checkout@v7.0.1"))

    def test_branch_ref_is_rejected(self):
        self.assertFalse(is_pinned_or_local("owner/repo@main"))

    def test_sha_one_char_short_is_rejected(self):
        self.assertFalse(is_pinned_or_local("owner/repo@" + "a" * 39))

    def test_sha_one_char_long_is_rejected(self):
        self.assertFalse(is_pinned_or_local("owner/repo@" + "a" * 41))

    def test_uppercase_hex_is_rejected(self):
        self.assertFalse(is_pinned_or_local("owner/repo@" + "A" * 40))

    def test_missing_ref_is_rejected(self):
        self.assertFalse(is_pinned_or_local("owner/repo"))

    def test_docker_ref_fails_closed(self):
        self.assertFalse(is_pinned_or_local("docker://alpine:3"))

    def test_empty_string_is_rejected(self):
        self.assertFalse(is_pinned_or_local(""))


class TestUsesRefs(unittest.TestCase):
    def test_non_mapping_document_yields_nothing(self):
        self.assertEqual(uses_refs(None), [])
        self.assertEqual(uses_refs([]), [])

    def test_collects_step_job_and_composite_refs(self):
        document = yaml.safe_load(
            """
jobs:
  a:
    steps:
      - uses: o/step@v1
      - run: 'echo "uses: o/in-run@v1"'
  b:
    uses: o/reusable/.github/workflows/x.yml@v2
  c: not-a-mapping
runs:
  steps:
    - uses: o/composite@v3
"""
        )
        self.assertEqual(
            uses_refs(document),
            ["o/step@v1", "o/reusable/.github/workflows/x.yml@v2", "o/composite@v3"],
        )

    def test_comment_is_not_a_ref(self):
        document = yaml.safe_load(
            "jobs:\n  a:\n    steps:\n      - run: x # uses: o/r@v1\n"
        )
        self.assertEqual(uses_refs(document), [])

    def test_non_mapping_steps_are_skipped(self):
        # A null step and a bare string that contains "uses" are not steps;
        # neither may be indexed as a mapping or counted as a ref.
        document = {"jobs": {"a": {"steps": [None, "uses: o/r@v1"]}}}
        self.assertEqual(uses_refs(document), [])


class TestRepoActionsArePinned(unittest.TestCase):
    def test_discovery_finds_workflows_and_composites(self):
        files = workflow_and_action_files()
        self.assertIn(WORKFLOWS_DIR / "benchmarks.yml", files)
        self.assertIn(ACTIONS_DIR / "sbom-sign" / "action.yml", files)

    def test_every_remote_action_is_pinned_to_a_sha(self):
        for path in workflow_and_action_files():
            document = yaml.safe_load(path.read_text())
            for ref in uses_refs(document):
                with self.subTest(file=path.name, uses=ref):
                    self.assertTrue(
                        is_pinned_or_local(ref),
                        f"{path.relative_to(REPO_ROOT)}: {ref} is not pinned to a 40-hex SHA",
                    )


if __name__ == "__main__":
    unittest.main()
