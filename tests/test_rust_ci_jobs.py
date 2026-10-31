"""The Rust CI workflows run tests and coverage as parallel jobs.

Coverage (tarpaulin instruments and rebuilds the crate) used to run after the tests
inside one job, so wall time was the sum. Splitting it into its own job lets the two
run side by side; the build job still waits only on `test` (core rule ci-020), and
`scripts/ci-gate.sh` gates merge on every non-advisory check run, so `Coverage
<crate>-rs` blocks merge like `Test <crate>-rs` does.
"""

import pathlib
import sys
import unittest

import tomllib
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import render_crate_files as rcf

# Spec R20: 15 s period x 3 = 45 s per test before nextest terminates it.
SLOW_TIMEOUT = {"period": "15s", "terminate-after": 3}
COVERAGE_TIMEOUT_MINUTES = 30
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


class TestRustTimeBounds(unittest.TestCase):
    def nextest(self, crate):
        path = REPO_ROOT / crate / f"{crate}-rs" / ".config" / "nextest.toml"
        return tomllib.loads(path.read_text())["profile"]

    def test_every_crate_bounds_a_single_test(self):
        for crate in rcf.CRATES:
            with self.subTest(crate=crate):
                self.assertEqual(
                    self.nextest(crate)["default"]["slow-timeout"], SLOW_TIMEOUT
                )

    def test_ci_profile_inherits_the_bound(self):
        # nextest's ci profile inherits default for any key it does not set, so the
        # bound reaches CI only while ci stays silent on slow-timeout.
        for crate in rcf.CRATES:
            with self.subTest(crate=crate):
                self.assertNotIn("slow-timeout", self.nextest(crate)["ci"])

    def test_coverage_job_is_time_bounded(self):
        for path in CI_WORKFLOWS:
            with self.subTest(workflow=path.name):
                self.assertEqual(
                    jobs_of(path)["coverage"]["timeout-minutes"],
                    COVERAGE_TIMEOUT_MINUTES,
                )


CACHE_DIR = "gmp-mpfr-sys"
CACHE_JOBS = ("test", "coverage", "build")
RESTORE_USES = "actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9"


def uses_of(step):
    return str(step.get("uses", ""))


def cache_jobs():
    """Every (workflow, job name, job) the GMP cache applies to."""
    return [
        (path, name, jobs_of(path)[name])
        for path in CI_WORKFLOWS
        for name in CACHE_JOBS
    ]


class TestGmpCacheRestore(unittest.TestCase):
    """Crate jobs restore the GMP/MPFR build cache read-only and fail open."""

    def find(self, path, name, job, label, predicate):
        for index, step in enumerate(job["steps"]):
            if predicate(step):
                return index, step
        self.fail(f"{path.name} job {name}: no step matching {label}")

    def key_step(self, path, name, job):
        return self.find(
            path, name, job, "id gmpkey", lambda s: s.get("id") == "gmpkey"
        )

    def restore_step(self, path, name, job):
        return self.find(
            path,
            name,
            job,
            "actions/cache/restore",
            lambda s: "actions/cache/restore@" in uses_of(s),
        )

    def test_eleven_workflows_times_three_jobs(self):
        self.assertEqual(len(cache_jobs()), 33)

    def test_no_job_env_uses_runner_context(self):
        # The runner context is not available at jobs.<id>.env; GitHub rejects the file.
        for path, name, job in cache_jobs():
            with self.subTest(workflow=path.name, job=name):
                for key, value in job.get("env", {}).items():
                    self.assertNotIn("runner.", str(value), f"env {key}")

    def test_key_step_exports_cache_dir_before_the_key_script(self):
        export = f'printf \'GMP_MPFR_SYS_CACHE=%s\\n\' "${{RUNNER_TEMP}}/{CACHE_DIR}" >> "$GITHUB_ENV"'
        for path, name, job in cache_jobs():
            with self.subTest(workflow=path.name, job=name):
                _, step = self.key_step(path, name, job)
                self.assertIn(export, step["run"])
                self.assertLess(
                    step["run"].index(export),
                    step["run"].index("scripts/gmp-cache-key.sh"),
                )

    def test_key_step_is_fail_open_and_writes_outputs(self):
        for path, name, job in cache_jobs():
            with self.subTest(workflow=path.name, job=name):
                _, step = self.key_step(path, name, job)
                self.assertIn("scripts/gmp-cache-key.sh", step["run"])
                self.assertIn('>> "$GITHUB_OUTPUT"', step["run"])
                self.assertNotIn("--strict", step["run"])
                self.assertEqual(step["working-directory"], "${{ github.workspace }}")

    def test_restore_step_is_pinned_guarded_and_keyed(self):
        for path, name, job in cache_jobs():
            with self.subTest(workflow=path.name, job=name):
                _, step = self.restore_step(path, name, job)
                self.assertEqual(uses_of(step).split(" ")[0], RESTORE_USES)
                self.assertEqual(step["if"], "steps.gmpkey.outputs.enabled == 'true'")
                self.assertEqual(step["with"]["key"], "${{ steps.gmpkey.outputs.key }}")
                self.assertEqual(
                    step["with"]["restore-keys"], "${{ steps.gmpkey.outputs.prefix }}"
                )
                self.assertEqual(
                    step["with"]["path"], f"${{{{ runner.temp }}}}/{CACHE_DIR}"
                )

    def test_cache_steps_precede_cargo_and_make(self):
        for path, name, job in cache_jobs():
            with self.subTest(workflow=path.name, job=name):
                key_index, _ = self.key_step(path, name, job)
                restore_index, _ = self.restore_step(path, name, job)
                self.assertLess(key_index, restore_index)
                build_index, _ = self.find(
                    path,
                    name,
                    job,
                    "run containing cargo or make",
                    lambda s: (
                        "cargo" in str(s.get("run", ""))
                        or "make" in str(s.get("run", ""))
                    ),
                )
                self.assertLess(restore_index, build_index)

    def test_crate_jobs_never_save(self):
        for path, name, job in cache_jobs():
            with self.subTest(workflow=path.name, job=name):
                for step in job["steps"]:
                    self.assertNotIn("actions/cache@", uses_of(step))
                    self.assertNotIn("actions/cache/save@", uses_of(step))


if __name__ == "__main__":
    unittest.main()
