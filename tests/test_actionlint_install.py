"""Every CI job that runs the bats suite installs a pinned actionlint.

`make lint-workflows` fails closed under CI when actionlint is absent, so the
jobs that reach it (scripts.yml and auto-merge.yml's bash-coverage) must install
the pinned, checksummed binary right after shellcheck, and scripts.yml must run
when any workflow changes.
"""

import pathlib
import re
import sys
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
sys.path.append(str(REPO_ROOT / "tests"))

import workflow_jobs

AL_VER = "1.7.12"
AL_SHA256 = "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"


def _installs_actionlint(step):
    return "actionlint" in (step.get("run") or "") and "sha256sum -c" in (
        step.get("run") or ""
    )


def _installs_shellcheck(step):
    return "shellcheck" in (step.get("name") or "").lower()


def _bats_jobs():
    for path in sorted(WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(path.read_text())
        for job_name, job in (doc.get("jobs") or {}).items():
            steps = job.get("steps") or []
            if any(workflow_jobs.runs_bats_suite(s) for s in steps):
                yield path.name, job_name, steps


class TestBatsJobsInstallActionlint(unittest.TestCase):
    def test_every_bats_job_installs_pinned_actionlint_after_shellcheck(self):
        checked = 0
        for wf, job, steps in _bats_jobs():
            checked += 1
            with self.subTest(workflow=wf, job=job):
                al = [i for i, s in enumerate(steps) if _installs_actionlint(s)]
                sc = [i for i, s in enumerate(steps) if _installs_shellcheck(s)]
                self.assertTrue(al, f"{wf}:{job} installs no actionlint")
                self.assertTrue(sc, f"{wf}:{job} has no shellcheck step")
                self.assertGreater(al[0], sc[0], "actionlint must follow shellcheck")
                env = steps[al[0]].get("env") or {}
                self.assertEqual(str(env.get("AL_VER")), AL_VER)
                self.assertEqual(str(env.get("AL_SHA256")), AL_SHA256)
        self.assertGreaterEqual(checked, 2, "expected scripts.yml and auto-merge.yml")


class TestMakefileVersionMatchesPin(unittest.TestCase):
    def test_every_makefile_actionlint_version_equals_workflow_pin(self):
        text = (REPO_ROOT / "Makefile").read_text()
        versions = re.findall(
            r"actionlint (\d+\.\d+\.\d+)|releases/tag/v(\d+\.\d+\.\d+)", text
        )
        found = [a or b for a, b in versions]
        self.assertGreaterEqual(len(found), 2, "expected both Makefile messages")
        self.assertEqual(set(found), {AL_VER})


class TestScriptsWorkflowPaths(unittest.TestCase):
    def test_paths_cover_every_workflow(self):
        doc = yaml.safe_load((WORKFLOWS / "scripts.yml").read_text())
        # PyYAML parses the bare key `on` as boolean True.
        paths = doc[True]["pull_request"]["paths"]
        self.assertIn(".github/workflows/**", paths)


if __name__ == "__main__":
    unittest.main()
