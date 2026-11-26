"""Tests for scripts/mutation_hypothesis_profile.py (R9 sitecustomize, R10 preflight)."""

import contextlib
import importlib.util
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import hypothesis

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "mutation_hypothesis_profile.py"
MESSAGE = f"hypothesis profile not active (hypothesis {hypothesis.__version__})"

R9_CALLS = (
    'settings.register_profile("mutation-gate", derandomize=True, database=None, '
    "deadline=None, suppress_health_check=list(HealthCheck))"
)

_SPEC = importlib.util.spec_from_file_location("mutation_hypothesis_profile", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
profile = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(profile)


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )


class TestWrite(unittest.TestCase):
    def test_write_creates_sitecustomize_with_r9_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_cli("write", tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            text = (pathlib.Path(tmp) / "sitecustomize.py").read_text()
        self.assertIn(R9_CALLS, text)
        self.assertIn('settings.load_profile("mutation-gate")', text)
        self.assertIn("hypothesis.core.function_digest", text)
        self.assertIn("hashlib.sha384(f.__qualname__.encode()).digest()", text)

    def test_write_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_cli("write", tmp)
            first = (pathlib.Path(tmp) / "sitecustomize.py").read_text()
            result = run_cli("write", tmp)
            second = (pathlib.Path(tmp) / "sitecustomize.py").read_text()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(first, second)

    def test_write_creates_missing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "nested" / "dir"
            result = run_cli("write", str(target))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((target / "sitecustomize.py").is_file())


class TestPreflight(unittest.TestCase):
    def test_preflight_passes_with_written_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_cli("write", tmp)
            result = run_cli("preflight", tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("not active", result.stdout + result.stderr)

    def test_preflight_fails_when_profile_not_loaded(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "sitecustomize.py").write_text("")
            result = run_cli("preflight", tmp)
        self.assertEqual(result.returncode, 1)
        self.assertIn(MESSAGE, result.stdout + result.stderr)

    def test_preflight_fails_when_no_sitecustomize(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_cli("preflight", tmp)
        self.assertEqual(result.returncode, 1)
        self.assertIn(MESSAGE, result.stdout + result.stderr)

    def test_preflight_fails_when_subprocess_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "sitecustomize.py").write_text(
                "import os\nos._exit(7)\n"
            )
            result = run_cli("preflight", tmp)
        self.assertEqual(result.returncode, 1)
        self.assertIn(MESSAGE, result.stdout + result.stderr)

    def test_preflight_fails_when_digest_patch_absent(self):
        # Only the function_digest assignment makes the two bodies share a seed.
        lines = profile.SITECUSTOMIZE.splitlines(keepends=True)
        kept = [ln for ln in lines if "hypothesis.core.function_digest =" not in ln]
        self.assertEqual(len(kept), len(lines) - 1)
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / "sitecustomize.py").write_text("".join(kept))
            result = run_cli("preflight", tmp)
        self.assertEqual(result.returncode, 1)
        self.assertIn(MESSAGE, result.stdout + result.stderr)


class TestParentErrors(unittest.TestCase):
    def _preflight_in_process(self, directory: str) -> tuple[int, str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = profile.main(["preflight", directory])
        return code, err.getvalue()

    def test_oserror_in_parent_is_red_with_message(self):
        with mock.patch.object(
            profile.tempfile, "TemporaryDirectory", side_effect=OSError("no tmp")
        ):
            code, err = self._preflight_in_process("/unused")
        self.assertEqual(code, 1)
        self.assertIn(MESSAGE, err)

    def test_missing_executable_is_red_with_message(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(profile.sys, "executable", "/nonexistent/python"),
        ):
            code, err = self._preflight_in_process(tmp)
        self.assertEqual(code, 1)
        self.assertIn(MESSAGE, err)

    def test_version_unknown_without_hypothesis(self):
        with mock.patch.dict(sys.modules, {"hypothesis": None}):
            self.assertEqual(profile._hypothesis_version(), "unknown")

    def test_version_matches_installed_hypothesis(self):
        self.assertEqual(profile._hypothesis_version(), hypothesis.__version__)


class TestPreflightEnv(unittest.TestCase):
    def test_existing_pythonpath_is_kept_after_dir(self):
        with mock.patch.dict(os.environ, {"PYTHONPATH": "/keep/me"}):
            env = profile._preflight_env(pathlib.Path("/profile"))
        self.assertEqual(env["PYTHONPATH"], "/profile" + os.pathsep + "/keep/me")

    def test_empty_pythonpath_has_no_trailing_separator(self):
        with mock.patch.dict(os.environ, {"PYTHONPATH": ""}):
            env = profile._preflight_env(pathlib.Path("/profile"))
        self.assertEqual(env["PYTHONPATH"], "/profile")

    def test_unset_pythonpath_has_no_trailing_separator(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("PYTHONPATH", None)
            env = profile._preflight_env(pathlib.Path("/profile"))
        self.assertEqual(env["PYTHONPATH"], "/profile")

    def test_hash_seed_and_bytecode_pinned(self):
        env = profile._preflight_env(pathlib.Path("/profile"))
        self.assertEqual(env["PYTHONHASHSEED"], "0")
        self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")


class TestUsage(unittest.TestCase):
    def test_unknown_command_exits_2(self):
        result = run_cli("bogus", "/tmp")
        self.assertEqual(result.returncode, 2)

    def test_missing_directory_argument_exits_2(self):
        result = run_cli("write")
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
