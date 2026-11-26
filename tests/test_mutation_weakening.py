"""Tests for scripts/mutation_weakening.py judge (R8, R12, R17), over temp git repos."""

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "mutation_weakening.py"
PREFIX = "base suite unjudgeable: "
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}
CONFIGURED = 'test-command = "python3 -m unittest test_sq"'
MODULE = "def square(x):\n    return x * x\n"
GOOD_TEST = (
    "import unittest\n\n\nclass T(unittest.TestCase):\n"
    "    def test_a(self):\n        self.assertEqual(4, 4)\n"
)


def toml(command: str = "python3 -m unittest test_sq", timeout: str = "30.0") -> str:
    return (
        "[cosmic-ray]\n"
        'module-path = "sq.py"\n'
        f"timeout = {timeout}\n"
        f'test-command = "{command}"\n'
    )


def clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_ENV)
    return env


def git(repo: pathlib.Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        env=clean_env(),
    )
    return result.stdout.strip()


def write_tree(root: pathlib.Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / "sq" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


class Fixture:
    """A repo with a base commit and a head work copy of `sq/`."""

    def __init__(self, base: dict[str, str], head: dict[str, str]) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="weakening-test-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        write_tree(self.repo, base)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        self.base = git(self.repo, "rev-parse", "HEAD")
        self.head_dir = self.tmp / "work" / "sq"
        self.head_dir.mkdir(parents=True)
        write_tree(self.tmp / "work", head)
        self.work = self.tmp / "out"

    def close(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def judge(
        self, *extra: str, after_head: bool = True
    ) -> subprocess.CompletedProcess[str]:
        cmd = [
            sys.executable,
            str(SCRIPT),
            "judge",
            "--dir",
            str(self.head_dir),
            "--base",
            self.base,
            "--work",
            str(self.work),
            "--repo",
            str(self.repo),
        ]
        if after_head:
            cmd.append("--after-head")
        return subprocess.run(
            [*cmd, *extra],
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=120,
            env=clean_env(),
        )


class FixtureCase(unittest.TestCase):
    def scratch(self) -> pathlib.Path:
        path = pathlib.Path(tempfile.mkdtemp(prefix="weakening-scratch-"))
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def make(self, base: dict[str, str], head: dict[str, str]) -> Fixture:
        fixture = Fixture(base, head)
        self.addCleanup(fixture.close)
        return fixture

    def standard(
        self, base_test: str = GOOD_TEST, head_test: str = GOOD_TEST
    ) -> Fixture:
        return self.make(
            {"sq.py": MODULE, "test_sq.py": base_test, "cosmic-ray.toml": toml()},
            {"sq.py": MODULE, "test_sq.py": head_test, "cosmic-ray.toml": toml()},
        )


class TestR8(FixtureCase):
    def expected(self) -> str:
        return PREFIX + "test-command must be python3 -m unittest test_sq"

    def test_head_pytest_command_is_red(self) -> None:
        fx = self.make(
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": toml()},
            {
                "sq.py": MODULE,
                "test_sq.py": GOOD_TEST,
                "cosmic-ray.toml": toml("pytest test_sq.py"),
            },
        )
        result = fx.judge()
        self.assertEqual(1, result.returncode)
        self.assertEqual(self.expected(), result.stdout.strip())

    def test_base_pytest_command_is_red(self) -> None:
        fx = self.make(
            {
                "sq.py": MODULE,
                "test_sq.py": GOOD_TEST,
                "cosmic-ray.toml": toml("pytest test_sq.py"),
            },
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": toml()},
        )
        result = fx.judge()
        self.assertEqual(1, result.returncode)
        self.assertEqual(self.expected(), result.stdout.strip())

    def test_missing_base_toml_is_red(self) -> None:
        fx = self.make(
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST},
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": toml()},
        )
        self.assertEqual(self.expected(), fx.judge().stdout.strip())

    def test_unparseable_head_toml_is_red(self) -> None:
        fx = self.make(
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": toml()},
            {
                "sq.py": MODULE,
                "test_sq.py": GOOD_TEST,
                "cosmic-ray.toml": "[cosmic-ray\n",
            },
        )
        self.assertEqual(self.expected(), fx.judge().stdout.strip())

    def test_r8_precedes_r17(self) -> None:
        fx = self.make(
            {
                "sq.py": MODULE,
                "test_sq.py": GOOD_TEST,
                "cosmic-ray.toml": toml("pytest"),
            },
            {"sq.py": MODULE, "cosmic-ray.toml": toml()},
        )
        self.assertEqual(self.expected(), fx.judge().stdout.strip())

    def test_missing_timeout_is_red(self) -> None:
        text = toml().replace("timeout = 30.0\n", "")
        fx = self.make(
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": text},
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": toml()},
        )
        result = fx.judge()
        self.assertEqual(1, result.returncode)
        self.assertTrue(result.stdout.startswith(PREFIX))


class TestR17(FixtureCase):
    def test_deleted_test_file_is_red(self) -> None:
        fx = self.make(
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": toml()},
            {"sq.py": MODULE, "cosmic-ray.toml": toml()},
        )
        result = fx.judge()
        self.assertEqual(1, result.returncode)
        self.assertEqual("test_sq.py deleted", result.stdout.strip())
        self.assertFalse((fx.head_dir / "test_sq_base.py").exists())

    def test_no_base_test_file_is_skipped_with_exit_3(self) -> None:
        fx = self.make(
            {"sq.py": MODULE, "cosmic-ray.toml": toml()},
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": toml()},
        )
        result = fx.judge()
        self.assertEqual(3, result.returncode)
        self.assertEqual(
            "no base test file: weakening check skipped", result.stdout.strip()
        )
        self.assertFalse((fx.work / "base-sig.json").exists())
        self.assertFalse((fx.head_dir / "test_sq_base.py").exists())


class TestUsage(FixtureCase):
    def test_without_after_head_refuses_and_writes_nothing(self) -> None:
        fx = self.standard()
        result = fx.judge(after_head=False)
        self.assertEqual(2, result.returncode)
        self.assertFalse((fx.head_dir / "test_sq_base.py").exists())

    def test_bad_arguments_exit_2(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "judge"],
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=60,
        )
        self.assertEqual(2, result.returncode)


class TestJudgeable(FixtureCase):
    def test_good_suite_writes_signature_and_base_file(self) -> None:
        fx = self.standard()
        result = fx.judge()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        sig = json.loads((fx.work / "base-sig.json").read_text())
        self.assertEqual(["test_sq_base.T.test_a"], list(sig))
        self.assertEqual("pass", sig["test_sq_base.T.test_a"]["outcome"])
        self.assertEqual(GOOD_TEST, (fx.head_dir / "test_sq_base.py").read_text())

    def test_base_file_comes_from_merge_base_not_head(self) -> None:
        head = GOOD_TEST.replace("test_a", "test_head_only")
        fx = self.standard(head_test=head)
        self.assertEqual(0, fx.judge().returncode)
        sig = json.loads((fx.work / "base-sig.json").read_text())
        self.assertEqual(["test_sq_base.T.test_a"], list(sig))

    def test_failing_assertion_alone_is_judgeable(self) -> None:
        failing = GOOD_TEST.replace("assertEqual(4, 4)", "assertEqual(4, 5)")
        fx = self.standard(base_test=failing)
        self.assertEqual(0, fx.judge().returncode)


class TestR12(FixtureCase):
    def judge_red(
        self, base_test: str, *, timeout: str = "30.0"
    ) -> subprocess.CompletedProcess[str]:
        fx = self.make(
            {
                "sq.py": MODULE,
                "test_sq.py": base_test,
                "cosmic-ray.toml": toml(timeout=timeout),
            },
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": toml()},
        )
        result = fx.judge()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertFalse((fx.work / "base-sig.json").exists())
        return result

    def test_import_failure_is_red_with_failed_test_id(self) -> None:
        result = self.judge_red("from sq import renamed_away\n")
        self.assertIn(PREFIX + "test file failed to import", result.stdout)
        self.assertIn("unittest.loader._FailedTest.test_sq_base", result.stdout)

    def test_set_up_class_error_is_red(self) -> None:
        source = (
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    @classmethod\n    def setUpClass(cls):\n        raise RuntimeError('x')\n"
            "    def test_a(self):\n        pass\n"
        )
        result = self.judge_red(source)
        self.assertIn(PREFIX + "class or module setUp error", result.stdout)
        self.assertIn("setUpClass (test_sq_base.T)", result.stdout)

    def test_set_up_module_error_is_red(self) -> None:
        source = (
            "import unittest\n\n\ndef setUpModule():\n    raise RuntimeError('x')\n\n\n"
            "class T(unittest.TestCase):\n    def test_a(self):\n        pass\n"
        )
        result = self.judge_red(source)
        self.assertIn(PREFIX + "class or module setUp error", result.stdout)
        self.assertIn("setUpModule (test_sq_base)", result.stdout)

    def test_per_test_set_up_error_is_red_with_test_id(self) -> None:
        source = (
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def setUp(self):\n        raise RuntimeError('x')\n"
            "    def test_a(self):\n        pass\n"
        )
        result = self.judge_red(source)
        self.assertIn(PREFIX + "per-test setUp error", result.stdout)
        self.assertIn("test_sq_base.T.test_a", result.stdout)

    def test_error_outside_set_up_is_judgeable(self) -> None:
        source = (
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def setUp(self):\n        self.v = 1\n"
            "    def test_a(self):\n        raise RuntimeError('x')\n"
        )
        fx = self.make(
            {"sq.py": MODULE, "test_sq.py": source, "cosmic-ray.toml": toml()},
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": toml()},
        )
        self.assertEqual(0, fx.judge().returncode)

    def test_differing_recordings_are_red(self) -> None:
        marker = self.scratch() / "marker"
        source = (
            "import os\nimport unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def test_a(self):\n"
            f"        marker = {str(marker)!r}\n"
            "        first = not os.path.exists(marker)\n"
            "        open(marker, 'w').close()\n"
            "        self.assertEqual(1, 2 if first else 1)\n"
        )
        result = self.judge_red(source)
        self.assertIn(PREFIX + "two recordings differ", result.stdout)
        self.assertIn("test_sq_base.T.test_a", result.stdout)

    def test_timeout_is_red_and_leaves_no_process(self) -> None:
        pid_dir = self.scratch()
        source = (
            "import os\nimport subprocess\nimport sys\nimport time\nimport unittest\n\n\n"
            "class T(unittest.TestCase):\n    def test_a(self):\n"
            f"        open({str(pid_dir / 'self.pid')!r}, 'w').write(str(os.getpid()))\n"
            "        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
            f"        open({str(pid_dir / 'child.pid')!r}, 'w').write(str(child.pid))\n"
            "        time.sleep(300)\n"
        )
        result = self.judge_red(source, timeout="2.0")
        self.assertIn(PREFIX + "base suite timed out after 2s", result.stdout)
        for name in ("self.pid", "child.pid"):
            pid = int((pid_dir / name).read_text())
            self.assertTrue(self.is_gone(pid), f"{name} process {pid} survived")

    @staticmethod
    def is_gone(pid: int) -> bool:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            time.sleep(0.1)
        return False

    def test_syntax_error_in_base_file_is_red_as_failed_import(self) -> None:
        result = self.judge_red("def broken(:\n")
        self.assertIn(PREFIX + "test file failed to import", result.stdout)

    def test_runner_exit_3_is_red_with_its_message(self) -> None:
        fx = self.standard()
        (fx.work / "base-sig-1.json").mkdir(parents=True)  # unwritable signature path
        result = fx.judge()
        self.assertEqual(1, result.returncode, result.stdout + result.stderr)
        self.assertTrue(
            result.stdout.startswith(PREFIX + "base runner exited 3"), result.stdout
        )
        self.assertFalse((fx.work / "base-sig.json").exists())


if __name__ == "__main__":
    unittest.main()
