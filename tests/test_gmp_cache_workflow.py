"""Pin the contract of the master-scoped GMP cache warm workflow.

`gmp-cache.yml` is the only job that saves the gmp-mpfr-sys build; crate jobs
restore it read-only. These tests parse the YAML (never grep raw text, so a
comment cannot fake a directive) and assert the invariants that keep a bad or
partial cache from ever being saved.
"""

import re
import unittest
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WARM_PATH = REPO_ROOT / ".github" / "workflows" / "gmp-cache.yml"
SCRIPTS_PATH = REPO_ROOT / ".github" / "workflows" / "scripts.yml"
MISS_GATE = "steps.restore.outputs.cache-hit != 'true'"
PINNED = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def _load(path: Path) -> dict[Any, Any]:
    assert path.is_file(), f"missing workflow file: {path}"
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict), f"{path} is not a mapping"
    return data


def _steps(path: Path) -> list[dict[str, Any]]:
    return list(_load(path)["jobs"]["warm"]["steps"])


def _step_by_id(step_id: str) -> dict[str, Any]:
    for step in _steps(WARM_PATH):
        if step.get("id") == step_id:
            return step
    raise AssertionError(f"no step with id {step_id!r}")


def _uses_step(prefix: str) -> dict[str, Any]:
    for step in _steps(WARM_PATH):
        if str(step.get("uses", "")).startswith(prefix):
            return step
    raise AssertionError(f"no step using {prefix!r}")


def _run_step(needle: str) -> dict[str, Any]:
    for step in _steps(WARM_PATH):
        if needle in str(step.get("run", "")):
            return step
    raise AssertionError(f"no run step containing {needle!r}")


class WarmWorkflowTests(unittest.TestCase):
    def test_workflow_file_exists(self) -> None:
        self.assertTrue(WARM_PATH.is_file(), f"missing {WARM_PATH}")

    def test_triggers_are_dispatch_and_schedule_only(self) -> None:
        # PyYAML loads the bare key `on` as the boolean True.
        triggers = _load(WARM_PATH)[True]
        self.assertEqual(set(triggers), {"workflow_dispatch", "schedule"})
        self.assertEqual(triggers["schedule"], [{"cron": "0 3 * * 1"}])

    def test_permissions_read_only(self) -> None:
        self.assertEqual(_load(WARM_PATH)["permissions"], {"contents": "read"})

    def test_key_step_is_strict(self) -> None:
        run = str(_step_by_id("gmpkey")["run"])
        self.assertIn("scripts/gmp-cache-key.sh --strict", run)
        self.assertIn("GITHUB_OUTPUT", run)

    def test_restore_has_no_restore_keys(self) -> None:
        step = _step_by_id("restore")
        self.assertTrue(step["uses"].startswith("actions/cache/restore@"))
        self.assertNotIn("restore-keys", step["with"])
        self.assertEqual(set(step["with"]), {"path", "key"})

    def test_save_step_uses_derived_key_and_job_path(self) -> None:
        job = _load(WARM_PATH)["jobs"]["warm"]
        save = _uses_step("actions/cache/save@")
        self.assertEqual(save["with"]["key"], "${{ steps.gmpkey.outputs.key }}")
        self.assertEqual(save["with"]["path"], job["env"]["GMP_MPFR_SYS_CACHE"])

    def test_build_check_and_save_gated_on_cache_miss(self) -> None:
        build = _run_step("cargo build --locked -p gmp-mpfr-sys")
        check = _run_step("libmpc.a")
        save = _uses_step("actions/cache/save@")
        for step in (build, check, save):
            self.assertEqual(step.get("if"), MISS_GATE)

    def test_build_runs_in_each_crate_dir(self) -> None:
        run = str(_run_step("cargo build --locked -p gmp-mpfr-sys")["run"])
        self.assertIn("cd ", run)
        self.assertIn("|| exit 1", run)

    def test_check_names_all_three_libraries(self) -> None:
        run = str(_run_step("libmpc.a")["run"])
        for lib in ("libgmp.a", "libmpfr.a", "libmpc.a"):
            self.assertIn(lib, run)

    def test_every_action_is_sha_pinned(self) -> None:
        uses = [s["uses"] for s in _steps(WARM_PATH) if "uses" in s]
        self.assertTrue(uses)
        for ref in uses:
            self.assertRegex(ref, PINNED)


class ScriptsWorkflowTests(unittest.TestCase):
    def _steps(self) -> list[dict[str, Any]]:
        return list(_load(SCRIPTS_PATH)["jobs"]["test"]["steps"])

    def test_installs_parallel(self) -> None:
        runs = [str(s.get("run", "")) for s in self._steps()]
        self.assertTrue(
            any("apt-get install" in r and "parallel" in r.split() for r in runs)
        )

    def test_runs_bats_with_jobs(self) -> None:
        runs = [str(s.get("run", "")).strip() for s in self._steps()]
        self.assertIn("bats --jobs 8 --recursive tests/", runs)

    def test_paths_include_warm_workflow(self) -> None:
        paths = _load(SCRIPTS_PATH)[True]["pull_request"]["paths"]
        self.assertIn(".github/workflows/gmp-cache.yml", paths)


if __name__ == "__main__":
    unittest.main()
