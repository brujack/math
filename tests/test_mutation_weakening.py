"""Tests for scripts/mutation_weakening.py judge (R8, R12, R17), over temp git repos."""

import contextlib
import importlib.util
import io
import json
import os
import pathlib
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from cosmic_ray.work_db import WorkDB, use_db
from cosmic_ray.work_item import (
    MutationSpec,
    TestOutcome,
    WorkerOutcome,
    WorkItem,
    WorkResult,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "mutation_weakening.py"
PREFIX = "base suite unjudgeable: "
_SPEC = importlib.util.spec_from_file_location("mutation_weakening", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
weakening = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(weakening)
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


SURVIVORS: list[
    int
] = []  # pids still alive when their test finished; see tearDownModule


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def reap(pid_log: pathlib.Path, *, escaped: bool = False) -> None:
    """Kill every pid a test recorded in `pid_log`.

    A pid still alive is noted in SURVIVORS unless `escaped`: a test that builds a
    process outside the judge's group on purpose expects it to outlive the judge.
    """
    if not pid_log.exists():
        return
    for line in pid_log.read_text().split():
        pid = int(line)
        if pid_alive(pid) and not escaped:
            SURVIVORS.append(pid)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            continue


def tearDownModule() -> None:
    if SURVIVORS:
        raise AssertionError(
            f"processes started by the suite outlived their tests: {SURVIVORS}"
        )


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
    def pid_log(self, *, escaped: bool = False) -> pathlib.Path:
        """A file child processes append their pids to; reaped when the test ends."""
        log = self.scratch() / "pids.log"
        self.addCleanup(reap, log, escaped=escaped)
        return log

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

    def test_r8_applies_when_base_has_a_test_file_even_if_head_deleted_it(self) -> None:
        fx = self.make(
            {
                "sq.py": MODULE,
                "test_sq.py": GOOD_TEST,
                "cosmic-ray.toml": toml("pytest"),
            },
            {"sq.py": MODULE, "cosmic-ray.toml": toml()},
        )
        self.assertEqual(self.expected(), fx.judge().stdout.strip())

    def test_new_subproject_without_base_toml_or_test_skips_instead_of_r8(self) -> None:
        fx = self.make(
            {"other.py": "x = 1\n"},
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": toml()},
        )
        result = fx.judge()
        self.assertEqual(3, result.returncode)
        self.assertEqual(
            "no base test file: weakening check skipped", result.stdout.strip()
        )

    def test_missing_timeout_is_red(self) -> None:
        text = toml().replace("timeout = 30.0\n", "")
        fx = self.make(
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": text},
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": toml()},
        )
        result = fx.judge()
        self.assertEqual(1, result.returncode)
        self.assertTrue(result.stdout.startswith(PREFIX))


class TestTomlTimeout(FixtureCase):
    def assert_bad_timeout(self, value: str) -> None:
        text = toml(timeout=value)
        fx = self.make(
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": text},
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": toml()},
        )
        result = fx.judge()
        self.assertEqual(1, result.returncode)
        self.assertEqual(
            PREFIX + "merge-base cosmic-ray.toml has no positive numeric timeout",
            result.stdout.strip(),
        )

    def test_boolean_timeout_is_red(self) -> None:
        self.assert_bad_timeout("true")

    def test_zero_timeout_is_red(self) -> None:
        self.assert_bad_timeout("0")

    def test_negative_timeout_is_red(self) -> None:
        self.assert_bad_timeout("-1.5")

    def test_string_timeout_is_red(self) -> None:
        self.assert_bad_timeout('"30"')


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
        log = self.pid_log()
        source = (
            "import os\nimport subprocess\nimport sys\nimport time\nimport unittest\n\n\n"
            "class T(unittest.TestCase):\n    def test_a(self):\n"
            f"        open({str(log)!r}, 'a').write(f'{{os.getpid()}}\\n')\n"
            "        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            f"        open({str(log)!r}, 'a').write(f'{{child.pid}}\\n')\n"
            "        time.sleep(30)\n"
        )
        result = self.judge_red(source, timeout="2.0")
        self.assertIn(PREFIX + "base suite timed out after 2s", result.stdout)
        pids = [int(p) for p in log.read_text().split()]
        self.assertEqual(2, len(pids))
        for pid in pids:
            self.assertTrue(self.is_gone(pid), f"process {pid} survived")

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

    def test_failed_first_recording_skips_the_second_run(self) -> None:
        fx = self.standard()
        (fx.work / "base-sig-1.json").mkdir(parents=True)
        fx.judge()
        self.assertFalse((fx.work / "base-sig-2.json").exists())

    def test_set_up_class_skip_is_not_red(self) -> None:
        source = (
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    @classmethod\n    def setUpClass(cls):\n        raise unittest.SkipTest('x')\n"
            "    def test_a(self):\n        pass\n"
        )
        fx = self.make(
            {"sq.py": MODULE, "test_sq.py": source, "cosmic-ray.toml": toml()},
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": toml()},
        )
        self.assertEqual(0, fx.judge().returncode)

    def test_set_up_helper_error_is_red(self) -> None:
        source = (
            "import unittest\n\nimport sq\n\n\ndef _prepare():\n    return sq.renamed_away\n\n\n"
            "class T(unittest.TestCase):\n    def setUp(self):\n        _prepare()\n"
            "    def test_a(self):\n        pass\n"
        )
        result = self.judge_red(source)
        self.assertIn(PREFIX + "per-test setUp error", result.stdout)
        self.assertIn("test_sq_base.T.test_a", result.stdout)

    def test_async_set_up_error_is_red(self) -> None:
        source = (
            "import unittest\n\n\nclass T(unittest.IsolatedAsyncioTestCase):\n"
            "    async def asyncSetUp(self):\n        raise RuntimeError('x')\n"
            "    async def test_a(self):\n        pass\n"
        )
        result = self.judge_red(source)
        self.assertIn(PREFIX + "per-test setUp error", result.stdout)

    def test_id_present_only_in_second_recording_is_red(self) -> None:
        marker = self.scratch() / "marker"
        source = (
            "import os\nimport unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def test_a(self):\n        pass\n\n\n"
            "class U(unittest.TestCase):\n    def test_extra(self):\n        pass\n\n\n"
            "def load_tests(loader, tests, pattern):\n"
            "    suite = unittest.TestSuite()\n"
            "    suite.addTests(loader.loadTestsFromTestCase(T))\n"
            f"    marker = {str(marker)!r}\n"
            "    if os.path.exists(marker):\n"
            "        suite.addTests(loader.loadTestsFromTestCase(U))\n"
            "    open(marker, 'w').close()\n"
            "    return suite\n"
        )
        result = self.judge_red(source)
        self.assertIn(PREFIX + "two recordings differ", result.stdout)
        self.assertIn("test_sq_base.U.test_extra", result.stdout)

    def test_passing_suite_leaves_no_process_behind(self) -> None:
        log = self.pid_log()
        source = (
            "import subprocess\nimport unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def test_a(self):\n"
            "        child = subprocess.Popen(['sleep', '30'])\n"
            f"        open({str(log)!r}, 'a').write(f'{{child.pid}}\\n')\n"
        )
        fx = self.make(
            {"sq.py": MODULE, "test_sq.py": source, "cosmic-ray.toml": toml()},
            {"sq.py": MODULE, "test_sq.py": GOOD_TEST, "cosmic-ray.toml": toml()},
        )
        self.assertEqual(0, fx.judge().returncode)
        pids = [int(p) for p in log.read_text().split()]
        self.assertEqual(2, len(pids))  # one per recording
        for pid in pids:
            self.assertTrue(self.is_gone(pid), f"process {pid} survived")

    def test_detached_descendant_cannot_hang_a_timed_out_judge(self) -> None:
        log = self.pid_log(escaped=True)
        source = (
            "import subprocess\nimport sys\nimport time\nimport unittest\n\n\n"
            "class T(unittest.TestCase):\n    def test_a(self):\n"
            "        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(25)'],\n"
            "                                 start_new_session=True)\n"
            f"        open({str(log)!r}, 'a').write(f'{{child.pid}}\\n')\n"
            "        time.sleep(30)\n"
        )
        started = time.monotonic()
        result = self.judge_red(source, timeout="2.0")
        self.assertLess(time.monotonic() - started, 20)
        self.assertIn("timed out", result.stdout)


class TestInfrastructure(FixtureCase):
    def test_unknown_base_sha_exits_4(self) -> None:
        fx = self.standard()
        fx.base = "0" * 40
        result = fx.judge()
        self.assertEqual(4, result.returncode)
        self.assertTrue(
            result.stdout.startswith(PREFIX + "infrastructure: "), result.stdout
        )

    def test_malformed_signature_after_runner_success_exits_4(self) -> None:
        fx = self.standard()
        stub = fx.tmp / "stub_runner.py"
        stub.write_text("import sys\nopen(sys.argv[2], 'w').write('[1, 2]')\n")
        with mock.patch.object(weakening, "RUNNER", stub):
            args = weakening.build_parser().parse_args(
                [
                    "judge",
                    "--dir",
                    str(fx.head_dir),
                    "--base",
                    fx.base,
                    "--work",
                    str(fx.work),
                    "--repo",
                    str(fx.repo),
                    "--after-head",
                ]
            )
            with mock.patch("builtins.print") as printed:
                code = weakening.judge(args)
        self.assertEqual(4, code)
        printed.assert_called_with(PREFIX + "infrastructure: malformed base signature")

    def test_signature_entry_without_setup_error_exits_4(self) -> None:
        fx = self.standard()
        stub = fx.tmp / "stub_runner.py"
        stub.write_text(
            "import sys\n"
            "open(sys.argv[2], 'w').write("
            '\'{"a": {"outcome": "pass", "sites": [], "error": []}}\')\n'
        )
        with mock.patch.object(weakening, "RUNNER", stub):
            args = weakening.build_parser().parse_args(
                [
                    "judge",
                    "--dir",
                    str(fx.head_dir),
                    "--base",
                    fx.base,
                    "--work",
                    str(fx.work),
                    "--repo",
                    str(fx.repo),
                    "--after-head",
                ]
            )
            with mock.patch("builtins.print"):
                self.assertEqual(4, weakening.judge(args))


MUL_ADD = "core/ReplaceBinaryOperator_Mul_Add"
STRONG_TEST = (
    "import unittest\n\nfrom sq import square\n\n\n"
    "class T(unittest.TestCase):\n"
    "    def test_a(self):\n        self.assertEqual(9, square(3))\n"
)
WEAK_TEST = (
    "import unittest\n\nfrom sq import square\n\n\n"
    "class T(unittest.TestCase):\n"
    "    def test_a(self):\n        self.assertEqual(4, square(2))\n"
)
DIFF = "--- sq.py\n+++ sq.py\n@@ -1,2 +1,2 @@\n-    return x * x\n+    return x + x"


def make_session(
    path: pathlib.Path, jobs: dict[str, str], planned_extra: int = 0
) -> None:
    """A real cosmic-ray sqlite session: job id -> test outcome ('survived'/'killed')."""
    with use_db(str(path), WorkDB.Mode.create) as db:
        for number, (job_id, outcome) in enumerate(jobs.items()):
            spec = MutationSpec(
                module_path=pathlib.Path("sq.py"),
                operator_name=MUL_ADD,
                occurrence=number,
                start_pos=(2, 11),
                end_pos=(2, 16),
            )
            db.add_work_item(WorkItem.single(job_id, spec))
            db.set_result(
                job_id,
                WorkResult(
                    worker_outcome=WorkerOutcome.NORMAL,
                    test_outcome=TestOutcome(outcome),
                    diff=DIFF,
                    output="",
                ),
            )
        for number in range(planned_extra):
            db.add_work_item(
                WorkItem.single(
                    f"pending-{number}",
                    MutationSpec(pathlib.Path("sq.py"), MUL_ADD, 0, (2, 11), (2, 16)),
                )
            )


def verdict_of(command: str) -> pathlib.Path:
    parts = shlex.split(command)
    return pathlib.Path(parts[parts.index("--verdict") + 1])


def result(test: str | None, output: str = "", worker: str = "normal") -> WorkResult:
    return WorkResult(
        worker_outcome=WorkerOutcome(worker),
        test_outcome=TestOutcome(test) if test else None,
        output=output,
        diff="",
    )


class FakeMutate:
    """A mutate_and_test seam: `script(command, timeout)` returns a WorkResult."""

    def __init__(self, script, auto_verdict: bool = True) -> None:
        self.script = script
        self.auto_verdict = auto_verdict
        self.calls: list[tuple[str, float]] = []

    @staticmethod
    def record_verdict(command: str, outcome: WorkResult) -> None:
        """What the real wrapper records for a non-timeout kill or survival."""
        path = verdict_of(command)
        if path.exists() or outcome.output == "timeout" or outcome.test_outcome is None:
            return
        path.write_text("1" if outcome.test_outcome == TestOutcome.KILLED else "0")

    def __call__(self, mutations, command, timeout):
        self.calls.append((command, timeout))
        outcome = self.script(command, timeout)
        if self.auto_verdict and is_base(command):
            self.record_verdict(command, outcome)
        return outcome


def is_base(command: str) -> bool:
    return "compare-wrapper" in command


def base_only_kills(command: str, timeout: float) -> WorkResult:
    """The base runner kills every mutant; the head tests never do."""
    return result("killed") if is_base(command) else result("survived")


class ReplayCase(FixtureCase):
    def setup_replay(
        self, jobs: dict[str, str], planned: int | None = None, extra: int = 0
    ):
        fx = self.standard(WEAK_TEST, WEAK_TEST)
        fx.work.mkdir(parents=True, exist_ok=True)
        session = self.scratch() / "session.sqlite"
        make_session(session, jobs, extra)
        self.session = session
        self.fx = fx
        self.planned = len(jobs) + extra if planned is None else planned
        return fx

    def argv(self, *extra: str) -> list[str]:
        return [
            "replay",
            "--dir",
            str(self.fx.head_dir),
            "--session",
            str(self.session),
            "--shard",
            "1/2",
            "--planned",
            str(self.planned),
            "--base",
            self.fx.base,
            "--work",
            str(self.fx.work),
            "--repo",
            str(self.fx.repo),
            *extra,
        ]

    def run_replay(
        self, script, *extra: str, auto_verdict: bool = True
    ) -> tuple[int, str, FakeMutate]:
        fake = FakeMutate(script, auto_verdict)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = weakening.main(self.argv(*extra), fake)
        return code, out.getvalue(), fake


class TestReplayVerdicts(ReplayCase):
    def test_base_survives_is_green(self) -> None:
        self.setup_replay({"j1": "survived"})
        code, out, fake = self.run_replay(lambda c, t: result("survived"))
        self.assertEqual((0, ""), (code, out))
        self.assertEqual(1, len(fake.calls))

    def test_killed_by_base_is_weakened_with_exact_block(self) -> None:
        fx = self.setup_replay({"j1": "survived"})
        code, out, fake = self.run_replay(base_only_kills)
        self.assertEqual(1, code)
        expected = (
            "weakened: 1 mutants killed by base tests survive head tests\n"
            f"  operator: {MUL_ADD}\n"
            "  occurrence: 0\n"
            f"{DIFF}\n"
            f"  repro: make -C sq mutants-weakening BASE={fx.base} JOB={MUL_ADD}@0\n"
        )
        self.assertEqual(expected, out)
        self.assertEqual(30.0, fake.calls[0][1])
        self.assertTrue(is_base(fake.calls[0][0]))

    def test_head_killed_jobs_are_not_replayed(self) -> None:
        self.setup_replay({"j1": "killed", "j2": "survived"})
        code, _, fake = self.run_replay(lambda c, t: result("survived"))
        self.assertEqual(0, code)
        self.assertEqual(1, len(fake.calls))

    def test_incompetent_is_replay_failed(self) -> None:
        self.setup_replay({"j1": "survived"})
        code, out, _ = self.run_replay(lambda c, t: result("incompetent"))
        self.assertEqual(1, code)
        self.assertIn(
            "replay failed: incompetent\n  mutant core/ReplaceBinaryOperator_Mul_Add@0\n",
            out,
        )

    def test_no_test_worker_outcome_is_replay_failed(self) -> None:
        self.setup_replay({"j1": "survived"})
        code, out, _ = self.run_replay(lambda c, t: result(None, worker="no-test"))
        self.assertEqual(1, code)
        self.assertIn(
            "replay failed: no-test\n  mutant core/ReplaceBinaryOperator_Mul_Add@0\n",
            out,
        )

    def test_exception_is_replay_failed(self) -> None:
        self.setup_replay({"j1": "survived"})

        def boom(command: str, timeout: float) -> WorkResult:
            raise RuntimeError("boom")

        code, out, _ = self.run_replay(boom)
        self.assertEqual(1, code)
        self.assertIn(
            "replay failed: exception\n  mutant core/ReplaceBinaryOperator_Mul_Add@0\n",
            out,
        )

    def test_runner_fault_is_never_a_kill(self) -> None:
        self.setup_replay({"j1": "survived"})

        def fault(command: str, timeout: float) -> WorkResult:
            verdict_of(command).write_text("fault:runner exit 3")
            return result("killed")

        code, out, _ = self.run_replay(fault)
        self.assertEqual(1, code)
        self.assertIn(
            "replay failed: runner fault\n  mutant core/ReplaceBinaryOperator_Mul_Add@0\n",
            out,
        )
        self.assertNotIn("weakened", out)

    def test_missing_verdict_is_runner_fault_not_kill(self) -> None:
        self.setup_replay({"j1": "survived"})
        code, out, _ = self.run_replay(
            lambda c, t: result("killed"), auto_verdict=False
        )
        self.assertEqual(1, code)
        self.assertIn(
            "replay failed: runner fault\n  mutant core/ReplaceBinaryOperator_Mul_Add@0\n",
            out,
        )
        self.assertNotIn("weakened", out)

    def test_verdict_disagreeing_with_outcome_is_runner_fault(self) -> None:
        self.setup_replay({"j1": "survived", "j2": "survived"})

        def script(command: str, timeout: float) -> WorkResult:
            kill = verdict_of(command).name == "runner-verdict"
            verdict_of(command).write_text("0")  # killed outcome, survived verdict
            return result("killed") if kill else result("survived")

        code, out, _ = self.run_replay(script)
        self.assertEqual(1, code)
        self.assertEqual(2, out.count("replay failed: runner fault"))

    def test_survived_with_kill_verdict_is_runner_fault(self) -> None:
        self.setup_replay({"j1": "survived"})

        def script(command: str, timeout: float) -> WorkResult:
            verdict_of(command).write_text("1")
            return result("survived")

        code, out, _ = self.run_replay(script)
        self.assertEqual(1, code)
        self.assertIn("replay failed: runner fault", out)

    def test_two_survivors_count_only_the_base_kill(self) -> None:
        self.setup_replay({"j1": "survived", "j2": "survived"})
        calls: list[str] = []

        def script(command: str, timeout: float) -> WorkResult:
            calls.append(command)
            if len(calls) <= 3:
                return result("killed") if is_base(command) else result("survived")
            return result("survived")

        code, out, _ = self.run_replay(script)
        self.assertEqual(1, code)
        self.assertTrue(out.startswith("weakened: 1 mutants killed"))
        self.assertIn(f"JOB={MUL_ADD}@0\n", out)
        self.assertNotIn("@1", out)
        self.assertNotIn("j1", out)

    def test_replay_forces_head_env_without_leaking(self) -> None:
        self.setup_replay({"j1": "survived"})
        seen: dict[str, str | None] = {}

        def script(command: str, timeout: float) -> WorkResult:
            seen["hash"] = os.environ.get("PYTHONHASHSEED")
            seen["bytecode"] = os.environ.get("PYTHONDONTWRITEBYTECODE")
            return result("survived")

        with mock.patch.dict(os.environ, {"PYTHONHASHSEED": "7"}):
            os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
            self.run_replay(script)
            self.assertEqual("7", os.environ["PYTHONHASHSEED"])
            self.assertNotIn("PYTHONDONTWRITEBYTECODE", os.environ)
        self.assertEqual({"hash": "0", "bytecode": "1"}, seen)

    def test_stale_verdict_does_not_poison_next_job(self) -> None:
        self.setup_replay({"j1": "survived", "j2": "survived"})
        calls: list[str] = []

        def script(command: str, timeout: float) -> WorkResult:
            calls.append(command)
            if len(calls) == 1:
                verdict_of(command).write_text("fault:runner exit 3")
            return result("survived")

        code, out, _ = self.run_replay(script)
        self.assertEqual(1, code)
        self.assertEqual(1, out.count("replay failed"))
        self.assertIn(
            "shard incomplete: ran 2 of 2 jobs, replayed 1 of 2 survivors", out
        )


class TestTimeoutRerun(ReplayCase):
    def test_base_timeout_head_survives_at_double_is_counted(self) -> None:
        self.setup_replay({"j1": "survived"})

        def script(command: str, timeout: float) -> WorkResult:
            if timeout == 30.0:
                return result("killed", "timeout")
            return result("killed") if is_base(command) else result("survived")

        code, out, fake = self.run_replay(script)
        self.assertEqual(1, code)
        self.assertIn("weakened: 1 mutants", out)
        timeouts = [t for _, t in fake.calls]
        self.assertEqual([30.0, 60.0, 60.0], timeouts)
        self.assertIn("python3 -m unittest test_sq", fake.calls[1][0])
        self.assertFalse(is_base(fake.calls[1][0]))
        self.assertTrue(is_base(fake.calls[2][0]))

    def test_head_also_kills_at_double_is_flaky(self) -> None:
        self.setup_replay({"j1": "survived"})

        def script(command: str, timeout: float) -> WorkResult:
            if timeout == 30.0:
                return result("killed", "timeout")
            return result("killed", "timeout")

        code, out, _ = self.run_replay(script)
        self.assertEqual((0, f"flaky: {MUL_ADD}@0\n"), (code, out))

    def test_base_survives_at_double_is_flaky(self) -> None:
        self.setup_replay({"j1": "survived"})

        def script(command: str, timeout: float) -> WorkResult:
            if timeout == 30.0:
                return result("killed", "timeout")
            return result("survived")

        code, out, _ = self.run_replay(script)
        self.assertEqual((0, f"flaky: {MUL_ADD}@0\n"), (code, out))

    def test_rerun_failure_is_replay_failed(self) -> None:
        self.setup_replay({"j1": "survived"})

        def script(command: str, timeout: float) -> WorkResult:
            if timeout == 30.0:
                return result("killed", "timeout")
            return result("incompetent")

        code, out, _ = self.run_replay(script)
        self.assertEqual(1, code)
        self.assertIn("replay failed: incompetent", out)

    def test_base_alone_fails_at_double_is_replay_failed(self) -> None:
        self.setup_replay({"j1": "survived"})

        def script(command: str, timeout: float) -> WorkResult:
            if timeout == 30.0:
                return result("killed", "timeout")
            return result("incompetent") if is_base(command) else result("survived")

        code, out, _ = self.run_replay(script)
        self.assertEqual(1, code)
        self.assertIn(
            "replay failed: incompetent\n  mutant core/ReplaceBinaryOperator_Mul_Add@0\n",
            out,
        )
        self.assertNotIn("weakened", out)

    def test_ordinary_kill_confirms_at_the_same_timeout(self) -> None:
        self.setup_replay({"j1": "survived"})
        _, _, fake = self.run_replay(base_only_kills)
        self.assertEqual([30.0, 30.0, 30.0], [t for _, t in fake.calls])


class TestConfirmation(ReplayCase):
    """Every base kill is replayed once more under both arms (R14)."""

    def scripted(self, *steps: str):
        """A mutate script answering call n with steps[n]: 'kill' or 'survive'."""
        calls: list[str] = []

        def script(command: str, timeout: float) -> WorkResult:
            step = steps[len(calls)]
            calls.append(command)
            return result("killed" if step == "kill" else "survived")

        return script

    def test_kill_twice_head_survives_twice_is_weakened(self) -> None:
        self.setup_replay({"j1": "survived"})
        script = self.scripted("kill", "survive", "kill")
        code, out, fake = self.run_replay(script)
        self.assertEqual(1, code)
        self.assertTrue(out.startswith("weakened: 1 mutants"))
        self.assertNotIn("flaky", out)
        self.assertEqual(
            [True, False, True], [is_base(command) for command, _ in fake.calls]
        )
        self.assertEqual([30.0, 30.0, 30.0], [t for _, t in fake.calls])

    def test_base_kills_then_survives_is_flaky_and_green(self) -> None:
        self.setup_replay({"j1": "survived"})
        code, out, _ = self.run_replay(self.scripted("kill", "survive", "survive"))
        self.assertEqual((0, f"flaky: {MUL_ADD}@0\n"), (code, out))

    def test_head_survives_then_kills_is_flaky(self) -> None:
        self.setup_replay({"j1": "survived"})
        code, out, _ = self.run_replay(self.scripted("kill", "kill", "kill"))
        self.assertEqual((0, f"flaky: {MUL_ADD}@0\n"), (code, out))

    def test_flaky_mutant_is_not_counted_beside_a_weakened_one(self) -> None:
        self.setup_replay({"j1": "survived", "j2": "survived"})
        steps = ("kill", "survive", "survive", "kill", "survive", "kill")
        code, out, _ = self.run_replay(self.scripted(*steps))
        self.assertEqual(1, code)
        self.assertIn(f"flaky: {MUL_ADD}@0\n", out)
        self.assertIn("weakened: 1 mutants", out)
        self.assertIn(f"JOB={MUL_ADD}@1\n", out)

    def test_timeout_kill_confirms_at_double_timeout(self) -> None:
        self.setup_replay({"j1": "survived"})

        def script(command: str, timeout: float) -> WorkResult:
            if timeout == 30.0:
                return result("killed", "timeout")
            return result("killed") if is_base(command) else result("survived")

        code, out, fake = self.run_replay(script)
        self.assertEqual(1, code)
        self.assertIn("weakened: 1 mutants", out)
        self.assertEqual([30.0, 60.0, 60.0], [t for _, t in fake.calls])

    def test_runner_fault_on_confirmation_is_replay_failed(self) -> None:
        self.setup_replay({"j1": "survived"})
        calls: list[str] = []

        def script(command: str, timeout: float) -> WorkResult:
            calls.append(command)
            if len(calls) == 3:
                verdict_of(command).write_text("fault:runner exit 3")
            return result("killed" if is_base(command) else "survived")

        code, out, _ = self.run_replay(script)
        self.assertEqual(1, code)
        self.assertIn("replay failed: runner fault\n  mutant ", out)
        self.assertNotIn("weakened", out)

    def test_head_failure_on_confirmation_is_replay_failed(self) -> None:
        self.setup_replay({"j1": "survived"})
        calls: list[str] = []

        def script(command: str, timeout: float) -> WorkResult:
            calls.append(command)
            if len(calls) == 2:
                return result("incompetent")
            return result("killed")

        code, out, _ = self.run_replay(script)
        self.assertEqual(1, code)
        self.assertIn("replay failed: incompetent", out)

    def test_base_survival_is_not_confirmed(self) -> None:
        self.setup_replay({"j1": "survived"})
        _, _, fake = self.run_replay(lambda c, t: result("survived"))
        self.assertEqual(1, len(fake.calls))


class TestCompleteness(ReplayCase):
    def test_skipped_job_is_shard_incomplete(self) -> None:
        self.setup_replay({"j1": "survived"}, planned=2)
        code, out, _ = self.run_replay(lambda c, t: result("survived"))
        self.assertEqual(1, code)
        self.assertEqual(
            "shard incomplete: ran 1 of 2 jobs, replayed 1 of 1 survivors\n", out
        )

    def test_job_without_result_is_not_counted_as_ran(self) -> None:
        self.setup_replay({"j1": "survived"}, extra=1)
        code, out, _ = self.run_replay(lambda c, t: result("survived"))
        self.assertEqual(1, code)
        self.assertIn("ran 1 of 2 jobs", out)

    def test_planned_slice_with_no_survivors_is_green(self) -> None:
        self.setup_replay({"j1": "killed", "j2": "killed"})
        code, out, fake = self.run_replay(lambda c, t: result("survived"))
        self.assertEqual((0, "", []), (code, out, fake.calls))

    def test_more_jobs_than_planned_is_incomplete(self) -> None:
        self.setup_replay({"j1": "killed", "j2": "killed"}, planned=1)
        code, out, _ = self.run_replay(lambda c, t: result("survived"))
        self.assertEqual(1, code)
        self.assertIn("ran 2 of 1 jobs", out)


class TestNoClearance(ReplayCase):
    def test_removed_clearance_flags_are_usage_errors(self) -> None:
        self.setup_replay({"j1": "survived"})
        for name, value in (("pr", "7"), ("head", "abc")):
            with self.subTest(flag=name), contextlib.redirect_stderr(io.StringIO()):
                argv = [*self.argv(), f"--{name}", value]
                mutate = FakeMutate(lambda c, t: result("killed"))
                self.assertEqual(2, weakening.main(argv, mutate))


class TestReplayUsage(ReplayCase):
    def test_bad_shard_is_usage_error(self) -> None:
        self.setup_replay({"j1": "survived"})
        argv = self.argv()
        argv[argv.index("--shard") + 1] = "x"
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(
                2, weakening.main(argv, FakeMutate(lambda c, t: result("survived")))
            )

    def test_missing_session_is_red(self) -> None:
        self.setup_replay({"j1": "survived"})
        self.session = self.scratch() / "absent.sqlite"
        code, out, _ = self.run_replay(lambda c, t: result("survived"))
        self.assertEqual(1, code)
        self.assertIn("replay failed: session unreadable", out)

    def test_merge_base_without_timeout_is_red(self) -> None:
        self.setup_replay({"j1": "survived"})
        toml_path = self.fx.repo / "sq" / "cosmic-ray.toml"
        toml_path.write_text(toml(timeout="0"))
        git(self.fx.repo, "add", "-A")
        git(self.fx.repo, "commit", "-q", "-m", "t")
        self.fx.base = git(self.fx.repo, "rev-parse", "HEAD")
        code, out, fake = self.run_replay(lambda c, t: result("survived"))
        self.assertEqual(1, code)
        self.assertIn("no positive numeric timeout", out)
        self.assertEqual([], fake.calls)


class TestRealMutateAndTest(FixtureCase):
    """The wrapper's exit mapping under the real cosmic_ray.mutating.mutate_and_test."""

    def prepare(self, base_test: str) -> ReplayCase:
        case = ReplayCase()
        fx = self.make(
            {"sq.py": MODULE, "test_sq.py": base_test, "cosmic-ray.toml": toml()},
            {"sq.py": MODULE, "test_sq.py": WEAK_TEST, "cosmic-ray.toml": toml()},
        )
        fx.work.mkdir(parents=True, exist_ok=True)
        session = self.scratch() / "session.sqlite"
        make_session(session, {"j1": "survived"})
        case.fx, case.session, case.planned = fx, session, 1
        self.assertEqual(0, fx.judge().returncode)
        return case

    def replay(self, case: ReplayCase) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = weakening.main(case.argv())
        return code, out.getvalue()

    def test_base_kill_is_weakened(self) -> None:
        case = self.prepare(STRONG_TEST)
        code, out = self.replay(case)
        self.assertEqual(1, code)
        self.assertIn(
            "weakened: 1 mutants killed by base tests survive head tests", out
        )
        self.assertEqual(MODULE, (case.fx.head_dir / "sq.py").read_text())

    def test_base_survival_is_green(self) -> None:
        case = self.prepare(WEAK_TEST)
        self.assertEqual((0, ""), self.replay(case))

    def test_runner_exit_3_is_runner_fault_not_kill(self) -> None:
        case = self.prepare(STRONG_TEST)
        (case.fx.work / "base-sig.json").write_text("not json")
        code, out = self.replay(case)
        self.assertEqual(1, code)
        self.assertIn(
            "replay failed: runner fault\n  mutant core/ReplaceBinaryOperator_Mul_Add@0\n",
            out,
        )
        self.assertNotIn("weakened", out)

    def replay_with_command(self, case: ReplayCase, rewrite) -> tuple[int, str]:
        def mutate(mutations, command, timeout):
            return weakening.mutate_and_test(mutations, rewrite(command), timeout)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = weakening.main(case.argv(), mutate)
        return code, out.getvalue()

    def assert_runner_fault(self, code: int, out: str) -> None:
        self.assertEqual(1, code)
        self.assertIn(
            "replay failed: runner fault\n  mutant core/ReplaceBinaryOperator_Mul_Add@0\n",
            out,
        )
        self.assertNotIn("weakened", out)

    def test_missing_work_dir_is_runner_fault(self) -> None:
        case = self.prepare(STRONG_TEST)
        shutil.rmtree(case.fx.work)
        self.assert_runner_fault(*self.replay(case))

    def test_wrapper_usage_error_is_runner_fault(self) -> None:
        case = self.prepare(STRONG_TEST)
        self.assert_runner_fault(
            *self.replay_with_command(
                case, lambda c: c.replace("compare-wrapper", "compare-wrapper --bogus")
            )
        )

    def test_wrapper_import_error_exit_1_is_runner_fault(self) -> None:
        case = self.prepare(STRONG_TEST)
        crash = shlex.join(
            [sys.executable, "-c", "import module_that_does_not_exist_xyz"]
        )
        self.assert_runner_fault(*self.replay_with_command(case, lambda c: crash))

    def test_unwritable_verdict_path_is_runner_fault(self) -> None:
        case = self.prepare(STRONG_TEST)
        self.assert_runner_fault(
            *self.replay_with_command(
                case,
                lambda c: c.replace(
                    str(case.fx.work / "runner-verdict"), "/nonexistent-dir/verdict"
                ),
            )
        )

    def test_wrapper_runs_runner_with_pinned_env_and_null_stdin(self) -> None:
        fx = self.make({"sq.py": MODULE}, {"sq.py": MODULE})
        stub = fx.tmp / "stub_runner.py"
        dump = fx.tmp / "dump.json"
        stub.write_text(
            "import json, os, sys\n"
            f"json.dump({{'hash': os.environ.get('PYTHONHASHSEED'),"
            " 'bytecode': os.environ.get('PYTHONDONTWRITEBYTECODE'),"
            " 'null': os.fstat(0).st_rdev == os.stat(os.devnull).st_rdev},"
            f" open({str(dump)!r}, 'w'))\n"
        )
        args = weakening.build_parser().parse_args(
            ["compare-wrapper", "--verdict", str(fx.tmp / "v"), "sig", "t"]
        )
        env = {"PYTHONHASHSEED": "5", "PYTHONDONTWRITEBYTECODE": ""}
        with (
            mock.patch.object(weakening, "RUNNER", stub),
            mock.patch.dict(os.environ, env),
        ):
            self.assertEqual(0, weakening.compare_wrapper(args))
        self.assertEqual(
            {"hash": "0", "bytecode": "1", "null": True}, json.loads(dump.read_text())
        )

    def test_wrapper_maps_exit_codes(self) -> None:
        fx = self.make({"sq.py": MODULE}, {"sq.py": MODULE})
        stub = fx.tmp / "stub_runner.py"
        stub.write_text("import sys\nsys.exit(int(sys.argv[3]))\n")
        for code, want, fault in (
            (0, 0, False),
            (1, 1, False),
            (2, 3, True),
            (3, 3, True),
        ):
            verdict = fx.tmp / f"verdict-{code}"
            args = weakening.build_parser().parse_args(
                ["compare-wrapper", "--verdict", str(verdict), "sig", str(code)]
            )
            with mock.patch.object(weakening, "RUNNER", stub):
                self.assertEqual(want, weakening.compare_wrapper(args), code)
            text = verdict.read_text()
            self.assertEqual(fault, text.startswith("fault:"), code)
            self.assertEqual(
                str(code) if not fault else "fault:runner exit " + str(code), text
            )


if __name__ == "__main__":
    unittest.main()
