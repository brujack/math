"""Coverage badges are staged as artifacts by the PR run and published after the merge.

A pull_request run must never push to `coverage-data`: it published whichever PR ran
last, merged or not. Each coverage job instead writes the shields endpoint JSON and
uploads it as `coverage-badge-<project>-<lang>`; `auto-merge.yml` publishes the artifacts
of the merged PR's head SHA through `scripts/publish-coverage-badges.sh`.

The staging step is extracted from the rendered workflows and run under bash with
`python3 -m coverage` stubbed, so nothing outside the temp dir is written.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
STAGE_STEP = "Stage coverage badge"
UPLOAD_SHA = "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"
GIT_PUSH = "git " + "push"

# Stands in for `python3 -m coverage json -o FILE`; every other call reaches python3.
COVERAGE_STUB = """\
#!/usr/bin/env bash
if [[ "$1" == "-m" && "$2" == "coverage" ]]; then
  printf '{"totals":{"percent_covered":%s}}\\n' "${STUB_PCT}" > "$5"
  exit 0
fi
exec "${REAL_PYTHON}" "$@"
"""


def coverage_job(path: pathlib.Path) -> dict:
    data = yaml.safe_load(path.read_text())
    return data["jobs"]["coverage" if path.name.endswith("-rs.yml") else "test"]


def workflow_kind(path: pathlib.Path) -> tuple[str, str]:
    """Return (project, lang) for `<project>-rs.yml` / `<project>-py.yml`."""
    stem = path.name[: -len(".yml")]
    project, suffix = stem.rsplit("-", 1)
    return project, {"rs": "rust", "py": "python"}[suffix]


RENDERED = sorted(
    p
    for p in WORKFLOWS.glob("*.yml")
    if re.fullmatch(r".+-(rs|py)\.yml", p.name) and not p.name.startswith("release-")
)


class TestRenderedCoverageJobs(unittest.TestCase):
    def test_rendered_set_is_not_empty(self):
        self.assertGreaterEqual(len(RENDERED), 20)

    def test_no_coverage_job_pushes_or_configures_git(self):
        for path in RENDERED:
            with self.subTest(workflow=path.name):
                for step in coverage_job(path)["steps"]:
                    run = str(step.get("run", ""))
                    self.assertNotIn(GIT_PUSH, run)
                    self.assertNotIn("git config", run)
                    self.assertNotIn("coverage-data", run)

    def test_coverage_job_only_reads_contents(self):
        for path in RENDERED:
            with self.subTest(workflow=path.name):
                self.assertEqual(
                    coverage_job(path)["permissions"], {"contents": "read"}
                )

    def test_uploads_named_badge_artifact_with_pinned_action(self):
        for path in RENDERED:
            project, lang = workflow_kind(path)
            with self.subTest(workflow=path.name):
                uploads = [
                    s
                    for s in coverage_job(path)["steps"]
                    if str(s.get("uses", "")).startswith(UPLOAD_SHA)
                    and s.get("with", {}).get("name", "").startswith("coverage-badge-")
                ]
                self.assertEqual(len(uploads), 1)
                with_ = uploads[0]["with"]
                self.assertEqual(with_["name"], f"coverage-badge-{project}-{lang}")
                self.assertEqual(with_["retention-days"], 7)
                self.assertEqual(with_["if-no-files-found"], "error")
                self.assertIn("coverage-badge", str(with_["path"]))

    def test_upload_follows_the_stage_step(self):
        for path in RENDERED:
            with self.subTest(workflow=path.name):
                steps = coverage_job(path)["steps"]
                names = [s.get("name", "") for s in steps]
                stage = names.index(STAGE_STEP)
                upload_name = steps[stage + 1].get("with", {}).get("name", "")
                self.assertTrue(upload_name.startswith("coverage-badge-"))


class TestStageStepOutput(unittest.TestCase):
    def stage(self, workflow: str, pct: str, report: dict | None = None) -> dict:
        path = WORKFLOWS / workflow
        project, lang = workflow_kind(path)
        step = next(
            s for s in coverage_job(path)["steps"] if s.get("name") == STAGE_STEP
        )
        real_python = shutil.which("python3")
        self.assertIsNotNone(real_python)
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "bin").mkdir()
            stub = root / "bin" / "python3"
            stub.write_text(COVERAGE_STUB)
            stub.chmod(0o755)
            crate = root / project / f"{project}-rs"
            crate.mkdir(parents=True)
            if report is not None:
                (crate / "tarpaulin-report.json").write_text(json.dumps(report))
            env = {
                "PATH": f"{root / 'bin'}:{os.environ['PATH']}",
                "REAL_PYTHON": str(real_python),
                "STUB_PCT": pct,
                "GITHUB_WORKSPACE": str(root),
                "RUNNER_TEMP": str(root),
                "HOME": str(root),
            }
            cwd = root
            result = subprocess.run(
                [
                    "bash",
                    "--noprofile",
                    "--norc",
                    "-eo",
                    "pipefail",
                    "-c",
                    str(step["run"]),
                ],
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=60,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            out = root / "coverage-badge" / project / f"{lang}.json"
            self.assertTrue(out.is_file(), f"{out} missing")
            return json.loads(out.read_text())

    def test_rust_floor_and_color(self):
        cases = (
            (97.9, "brightgreen"),
            (85.0, "green"),
            (75.2, "yellow"),
            (60.0, "orange"),
            (12.0, "red"),
        )
        for cov, color in cases:
            with self.subTest(cov=cov):
                badge = self.stage("amicable-rs.yml", "0", {"coverage": cov})
                self.assertEqual(
                    badge,
                    {
                        "schemaVersion": 1,
                        "label": "coverage",
                        "message": f"{int(cov)}%",
                        "color": color,
                    },
                )

    def test_python_floor_and_color(self):
        badge = self.stage("amicable-py.yml", "89.99")
        self.assertEqual(badge["message"], "89%")
        self.assertEqual(badge["color"], "green")
        self.assertEqual(self.stage("amicable-py.yml", "90")["color"], "brightgreen")


class TestAutoMergePublishes(unittest.TestCase):
    def merge_step(self) -> str:
        data = yaml.safe_load((WORKFLOWS / "auto-merge.yml").read_text())
        steps = data["jobs"]["auto-merge"]["steps"]
        return str(next(s for s in steps if s.get("name") == "Gate and merge")["run"])

    def test_publish_runs_only_after_merge_in_the_same_chain(self):
        run = self.merge_step()
        self.assertLess(
            run.index("gh pr merge"), run.index("publish-coverage-badges.sh")
        )
        self.assertRegex(
            run,
            r"gh pr merge[^\n]*(?:\\\n)?\s*&&\s*\./scripts/publish-coverage-badges\.sh",
        )

    def test_head_sha_is_read_before_the_merge(self):
        run = self.merge_step()
        self.assertLess(run.index("headRefOid"), run.index("gh pr merge"))
        self.assertRegex(run, r'publish-coverage-badges\.sh "\$\{head_sha\}"')

    def test_job_can_read_actions(self):
        data = yaml.safe_load((WORKFLOWS / "auto-merge.yml").read_text())
        perms = data["jobs"]["auto-merge"]["permissions"]
        self.assertEqual(perms.get("actions"), "read")
        self.assertEqual(perms.get("contents"), "write")


if __name__ == "__main__":
    unittest.main()
