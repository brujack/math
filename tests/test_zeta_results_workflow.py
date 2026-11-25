"""Pin the zeta results deploy workflow contract (spec R11, R12, R17).

Every assertion parses the YAML rather than searching raw text, so a comment cannot
fake a directive.
"""

import re
import unittest
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
SHA_RE = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")
CHECKOUT = "actions/checkout@"


def _load(name: str) -> dict[Any, Any]:
    loaded = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    # PyYAML (YAML 1.1) reads the bare key `on` as boolean True.
    raw = workflow["on"] if "on" in workflow else workflow[True]
    assert isinstance(raw, dict)
    return raw


def _run_text(job: dict[str, Any]) -> str:
    return "\n".join(str(step["run"]) for step in job["steps"] if "run" in step)


class ZetaResultsPagesWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = _load("zeta-results-pages.yml")
        jobs = self.workflow["jobs"]
        self.assertEqual(len(jobs), 1)
        self.job = next(iter(jobs.values()))

    def test_trigger_is_workflow_dispatch_only(self) -> None:
        self.assertEqual(set(_triggers(self.workflow)), {"workflow_dispatch"})

    def test_job_runs_only_from_master(self) -> None:
        self.assertEqual(self.job["if"], "github.ref == 'refs/heads/master'")

    def test_permissions_contents_write(self) -> None:
        self.assertEqual(self.job["permissions"], {"contents": "write"})

    def test_concurrency_group_gh_pages_without_cancel(self) -> None:
        self.assertEqual(
            self.job["concurrency"],
            {"group": "gh-pages", "cancel-in-progress": False},
        )

    def test_every_uses_is_sha_pinned(self) -> None:
        uses = [s["uses"] for s in self.job["steps"] if "uses" in s]
        self.assertGreaterEqual(len(uses), 2)
        for ref in uses:
            self.assertRegex(ref, SHA_RE)

    def test_checkout_sha_matches_benchmarks(self) -> None:
        bench = _load("benchmarks.yml")["jobs"]["benchmark"]["steps"][0]["uses"]
        checkouts = [
            s["uses"]
            for s in self.job["steps"]
            if str(s.get("uses", "")).startswith(CHECKOUT)
        ]
        self.assertEqual(len(checkouts), 2)
        for ref in checkouts:
            self.assertEqual(ref, bench)

    def test_gh_pages_is_checked_out(self) -> None:
        refs = [
            s["with"]["ref"]
            for s in self.job["steps"]
            if str(s.get("uses", "")).startswith(CHECKOUT)
            and "ref" in s.get("with", {})
        ]
        self.assertEqual(refs, ["gh-pages"])

    def test_no_force_push(self) -> None:
        text = _run_text(self.job)
        self.assertNotIn("--force", text)
        self.assertNotRegex(text, r"git push\b[^\n]*\s-f\b")
        self.assertIn("git -C gh-pages push", text)

    def test_replaces_only_zeta_and_runs_guard_before_push(self) -> None:
        text = _run_text(self.job)
        self.assertIn("rm -rf gh-pages/zeta", text)
        self.assertIn("cp -R zeta/results/site gh-pages/zeta", text)
        self.assertIn("scripts/gh-pages-zeta-guard.sh gh-pages", text)
        self.assertLess(
            text.index("gh-pages-zeta-guard.sh"), text.index("git -C gh-pages push")
        )

    def test_marker_file_is_not_published(self) -> None:
        text = _run_text(self.job)
        copy_at = text.index("cp -R zeta/results/site")
        removal = re.search(r"rm -f gh-pages/zeta/\.zeta-results", text)
        self.assertIsNotNone(removal)
        assert removal is not None
        self.assertGreater(removal.start(), copy_at)

    def test_deployed_from_written_from_sha(self) -> None:
        text = _run_text(self.job)
        self.assertIn("gh-pages/zeta/deployed-from.txt", text)
        self.assertIn("github.sha", str(self.job["steps"]))

    def test_push_only_when_something_changed(self) -> None:
        push_step = next(
            step
            for step in self.job["steps"]
            if "git -C gh-pages status --porcelain" in str(step.get("run", ""))
        )
        lines = [line.strip() for line in str(push_step["run"]).splitlines()]
        test_at = next(
            i
            for i, line in enumerate(lines)
            if "git -C gh-pages status --porcelain" in line
        )
        exit_at = next(i for i, line in enumerate(lines) if line == "exit 0")
        commit_at = next(i for i, line in enumerate(lines) if "commit -m" in line)
        fi_at = next(i for i, line in enumerate(lines) if line == "fi")
        self.assertTrue(lines[test_at].startswith("if [[ -z "))
        self.assertLess(test_at, exit_at)
        self.assertLess(exit_at, fi_at)
        self.assertLess(fi_at, commit_at)


class BenchmarksConcurrencyTest(unittest.TestCase):
    def test_benchmark_job_shares_gh_pages_group(self) -> None:
        job = _load("benchmarks.yml")["jobs"]["benchmark"]
        self.assertEqual(
            job["concurrency"],
            {"group": "gh-pages", "cancel-in-progress": False},
        )


class ScriptsWorkflowPathsTest(unittest.TestCase):
    def test_paths_include_zeta_results(self) -> None:
        paths = _triggers(_load("scripts.yml"))["pull_request"]["paths"]
        self.assertIn("zeta/results/**", paths)


if __name__ == "__main__":
    unittest.main()
