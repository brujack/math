"""The Rust CI workflows run tests and coverage as parallel jobs.

Coverage (tarpaulin instruments and rebuilds the crate) used to run after the tests
inside one job, so wall time was the sum. Splitting it into its own job lets the two
run side by side; the build job still waits only on `test` (core rule ci-020), and
`scripts/ci-gate.sh` gates merge on every non-advisory check run, so `Coverage
<crate>-rs` blocks merge like `Test <crate>-rs` does.
"""

import pathlib
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CI_WORKFLOWS = sorted(
    p
    for p in (REPO_ROOT / ".github" / "workflows").glob("*-rs.yml")
    if not p.name.startswith("release-")
)


def jobs_of(path):
    return yaml.safe_load(path.read_text())["jobs"]


def step_text(job):
    return "\n".join(
        str(s.get("run", "")) + str(s.get("with", "")) + str(s.get("name", ""))
        for s in job["steps"]
    )


class TestRustCiJobSplit(unittest.TestCase):
    def test_eleven_ci_workflows_found(self):
        self.assertEqual(len(CI_WORKFLOWS), 11)

    def test_jobs_are_test_coverage_build(self):
        for path in CI_WORKFLOWS:
            with self.subTest(workflow=path.name):
                self.assertEqual(set(jobs_of(path)), {"test", "coverage", "build"})

    def test_coverage_job_runs_in_parallel_with_test(self):
        for path in CI_WORKFLOWS:
            with self.subTest(workflow=path.name):
                job = jobs_of(path)["coverage"]
                self.assertNotIn("needs", job)
                self.assertEqual(job["name"], f"Coverage {path.stem}")

    def test_build_still_depends_only_on_test(self):
        for path in CI_WORKFLOWS:
            with self.subTest(workflow=path.name):
                self.assertEqual(jobs_of(path)["build"]["needs"], ["test"])

    def test_tarpaulin_and_badge_live_only_in_coverage(self):
        for path in CI_WORKFLOWS:
            with self.subTest(workflow=path.name):
                jobs = jobs_of(path)
                cov, test = step_text(jobs["coverage"]), step_text(jobs["test"])
                self.assertIn("cargo tarpaulin --out Json --fail-under 90", cov)
                self.assertIn("cargo-tarpaulin@", cov)
                self.assertIn("Publish coverage badge", cov)
                self.assertNotIn("tarpaulin", test)
                self.assertNotIn("coverage", test.lower())

    def test_test_job_keeps_nextest_and_metrics(self):
        for path in CI_WORKFLOWS:
            with self.subTest(workflow=path.name):
                test = step_text(jobs_of(path)["test"])
                for needle in ("cargo-nextest@", "make test", "test_metrics.py"):
                    self.assertIn(needle, test)

    def test_only_coverage_job_may_write_contents(self):
        for path in CI_WORKFLOWS:
            with self.subTest(workflow=path.name):
                jobs = jobs_of(path)
                self.assertEqual(jobs["coverage"]["permissions"], {"contents": "write"})
                self.assertEqual(jobs["test"]["permissions"], {"contents": "read"})

    def test_coverage_job_has_its_own_toolchain_setup(self):
        for path in CI_WORKFLOWS:
            with self.subTest(workflow=path.name):
                uses = [
                    str(s.get("uses", "")).split("@")[0]
                    for s in jobs_of(path)["coverage"]["steps"]
                ]
                for action in (
                    "actions/checkout",
                    "dtolnay/rust-toolchain",
                    "Swatinem/rust-cache",
                    "taiki-e/install-action",
                ):
                    self.assertIn(action, uses)


if __name__ == "__main__":
    unittest.main()
