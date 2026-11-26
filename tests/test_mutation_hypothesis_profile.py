"""Tests for scripts/mutation_hypothesis_profile.py (R9 sitecustomize, R10 preflight)."""

import pathlib
import subprocess
import sys
import tempfile
import unittest

import hypothesis

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "mutation_hypothesis_profile.py"
MESSAGE = f"hypothesis profile not active (hypothesis {hypothesis.__version__})"

R9_CALLS = (
    'settings.register_profile("mutation-gate", derandomize=True, database=None, '
    "deadline=None, suppress_health_check=list(HealthCheck))"
)


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


class TestUsage(unittest.TestCase):
    def test_unknown_command_exits_2(self):
        result = run_cli("bogus", "/tmp")
        self.assertEqual(result.returncode, 2)

    def test_missing_directory_argument_exits_2(self):
        result = run_cli("write")
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
