"""Pin the contract of the master-scoped GMP cache warm workflow.

`gmp-cache.yml` is the only job that saves the gmp-mpfr-sys build; crate jobs
restore it read-only. These tests parse the YAML (never grep raw text, so a
comment cannot fake a directive) and assert the invariants that keep a bad or
partial cache from ever being saved.
"""

import os
import re
import subprocess
import tempfile
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

    def test_save_step_uses_derived_key_and_cache_path(self) -> None:
        save = _uses_step("actions/cache/save@")
        self.assertEqual(save["with"]["key"], "${{ steps.gmpkey.outputs.key }}")
        self.assertEqual(save["with"]["path"], "${{ runner.temp }}/gmp-mpfr-sys")
        self.assertEqual(_step_by_id("restore")["with"]["path"], save["with"]["path"])

    def test_no_job_env_references_runner_context(self) -> None:
        # The runner context is not available at jobs.<id>.env; GitHub rejects it.
        for name, job in _load(WARM_PATH)["jobs"].items():
            for key, value in (job.get("env") or {}).items():
                self.assertNotIn("runner.", str(value), f"{name}.env.{key}")

    def test_key_step_exports_cache_dir_before_key_script(self) -> None:
        run = str(_step_by_id("gmpkey")["run"])
        export = "GMP_MPFR_SYS_CACHE=%s"
        self.assertIn(export, run)
        self.assertIn('"${RUNNER_TEMP}/gmp-mpfr-sys"', run)
        self.assertIn('>> "$GITHUB_ENV"', run)
        self.assertLess(run.index("GITHUB_ENV"), run.index("gmp-cache-key.sh"))

    def test_build_check_and_save_gated_on_cache_miss(self) -> None:
        build = _run_step("cargo build --locked -p gmp-mpfr-sys")
        check = _run_step("libmpc.a")
        save = _uses_step("actions/cache/save@")
        for step in (build, check, save):
            self.assertEqual(step.get("if"), MISS_GATE)

    def test_check_names_all_three_libraries(self) -> None:
        run = str(_run_step("libmpc.a")["run"])
        for lib in ("libgmp.a", "libmpfr.a", "libmpc.a"):
            self.assertIn(lib, run)

    def test_every_action_is_sha_pinned(self) -> None:
        uses = [s["uses"] for s in _steps(WARM_PATH) if "uses" in s]
        self.assertTrue(uses)
        for ref in uses:
            self.assertRegex(ref, PINNED)


LIBS = ("libgmp.a", "libmpfr.a", "libmpc.a")


def _lock_text(version: str | None) -> str:
    if version is None:
        return '[[package]]\nname = "other"\nversion = "0.1.0"\n'
    return f'[[package]]\nname = "gmp-mpfr-sys"\nversion = "{version}"\n'


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _make_repo(root: Path, locks: dict[str, str | None]) -> Path:
    """Fixture git repo with `<crate>/<crate>-rs/Cargo.lock` per entry."""
    repo = root / "repo"
    for crate, version in locks.items():
        lock = repo / crate / f"{crate}-rs" / "Cargo.lock"
        lock.parent.mkdir(parents=True)
        lock.write_text(_lock_text(version))
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "init", "-q"], cwd=repo, env=_clean_env(), check=True)
    subprocess.run([*git, "add", "-A"], cwd=repo, env=_clean_env(), check=True)
    return repo


def _make_cache(root: Path, dirs: dict[str, tuple[str, ...]]) -> Path:
    """Cache tree; file names may carry a subpath such as `c-no-tests/libgmp.a`."""
    cache = root / "cache"
    cache.mkdir()
    for version, files in dirs.items():
        major_minor = version.rsplit(".", 1)[0]
        lib_dir = cache / major_minor / "x86_64-unknown-linux-gnu" / version
        lib_dir.mkdir(parents=True)
        for name in files:
            (lib_dir / name).parent.mkdir(parents=True, exist_ok=True)
            (lib_dir / name).write_text("")
    return cache


class BuildStepTests(unittest.TestCase):
    def test_cargo_runs_once_in_each_gmp_crate_dir_only(self) -> None:
        run = str(_run_step("cargo build --locked -p gmp-mpfr-sys")["run"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = _make_repo(root, {"a": "1.7.1", "b": None, "c": "1.7.0"})
            bindir = root / "bin"
            bindir.mkdir()
            log = root / "cargo.log"
            fake = bindir / "cargo"
            fake.write_text(f'#!/bin/sh\nprintf \'%s|%s\\n\' "$PWD" "$*" >> "{log}"\n')
            fake.chmod(0o755)
            env = _clean_env()
            env["PATH"] = f"{bindir}:{env['PATH']}"
            proc = subprocess.run(
                ["bash", "-c", run],
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            calls = sorted(log.read_text().splitlines())
            repo_real = repo.resolve()
            self.assertEqual(
                calls,
                [
                    f"{repo_real}/a/a-rs|build --locked -p gmp-mpfr-sys",
                    f"{repo_real}/c/c-rs|build --locked -p gmp-mpfr-sys",
                ],
            )

    def test_cargo_failure_fails_the_step(self) -> None:
        run = str(_run_step("cargo build --locked -p gmp-mpfr-sys")["run"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = _make_repo(root, {"a": "1.7.1"})
            bindir = root / "bin"
            bindir.mkdir()
            fake = bindir / "cargo"
            fake.write_text("#!/bin/sh\nexit 7\n")
            fake.chmod(0o755)
            env = _clean_env()
            env["PATH"] = f"{bindir}:{env['PATH']}"
            proc = subprocess.run(
                ["bash", "-c", run],
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
        self.assertEqual(proc.returncode, 1)


class CheckStepTests(unittest.TestCase):
    """Execute the check step's shell against fixture cache trees."""

    def _run_check(
        self,
        cache_dirs: dict[str, tuple[str, ...]],
        locks: dict[str, str | None] | None = None,
    ) -> tuple[int, str]:
        run = str(_run_step("libmpc.a")["run"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = _make_repo(root, locks or {"e": "1.7.0", "f": "1.7.1"})
            env = _clean_env()
            env["GMP_MPFR_SYS_CACHE"] = str(_make_cache(root, cache_dirs))
            proc = subprocess.run(
                ["bash", "-c", run],
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
        return proc.returncode, proc.stderr.replace(tmp, "<tmp>")

    def test_newer_patch_dir_alone_satisfies_older_lock(self) -> None:
        code, err = self._run_check({"1.7.1": LIBS})
        self.assertEqual(code, 0, err)

    def test_lock_without_gmp_is_skipped(self) -> None:
        # 6 of the 11 crates lock no gmp-mpfr-sys; they must not fail the check.
        code, err = self._run_check({"1.7.1": LIBS}, {"e": "1.7.0", "b": None})
        self.assertEqual((code, err), (0, ""))

    def test_only_older_patch_dir_reports_no_cache_dir(self) -> None:
        code, err = self._run_check({"1.7.0": LIBS})
        self.assertEqual(code, 1)
        self.assertEqual(
            err,
            "no cache dir for gmp-mpfr-sys 1.7.1 at patch >= 1 (found 1.7.0)"
            " (f/f-rs/Cargo.lock)\n",
        )

    def test_missing_library_is_named(self) -> None:
        code, err = self._run_check({"1.7.1": ("libgmp.a", "libmpfr.a")})
        self.assertEqual(code, 1)
        self.assertEqual(
            err,
            "missing libmpc.a for gmp-mpfr-sys 1.7.0 in "
            "<tmp>/cache/1.7/x86_64-unknown-linux-gnu/1.7.1 (e/e-rs/Cargo.lock)\n",
        )

    def test_different_minor_does_not_satisfy(self) -> None:
        code, err = self._run_check({"1.8.0": LIBS})
        self.assertEqual(code, 1)
        self.assertEqual(
            err,
            "no cache dir for gmp-mpfr-sys 1.7.0 at patch >= 0 (found none)"
            " (e/e-rs/Cargo.lock)\n",
        )

    def test_patch_compare_is_numeric_not_lexical(self) -> None:
        code, err = self._run_check({"1.7.10": LIBS}, {"e": "1.7.9"})
        self.assertEqual(code, 0, err)

    def test_older_numeric_patch_does_not_satisfy_newer_lock(self) -> None:
        code, err = self._run_check({"1.7.9": LIBS}, {"e": "1.7.10"})
        self.assertEqual(code, 1)
        self.assertIn("no cache dir for gmp-mpfr-sys 1.7.10 at patch >= 10", err)

    def test_library_under_subdirectory_does_not_count(self) -> None:
        nested = tuple(f"c-no-tests/{lib}" for lib in LIBS)
        code, err = self._run_check({"1.7.1": nested}, {"e": "1.7.1"})
        self.assertEqual(code, 1)
        self.assertIn("missing libgmp.a libmpfr.a libmpc.a", err)


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
