"""Guard the root pyrightconfig.json's mode and file-coverage against silent drift.

Two independent assertions, each with a distinct failure mode:

1. Mode — a parse of the JSON config, asserting typeCheckingMode/reportMissingImports
   have not been silently downgraded. A file-count check alone cannot see this.
2. Coverage — an equality between pyright's own reported filesAnalyzed and an
   independently-derived count of tracked-plus-untracked .py files under the three
   include roots. This is deliberately an equality, not `>=` or a Python glob
   reimplementation of pyright's include/exclude semantics — see ai-config/docs/knowledge/math-testing-policy.md § Root-scope pyright and the
   design notes for why those alternatives were tried and refuted.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "pyrightconfig.json"
INCLUDE_PATHSPECS = ["tests/*.py", "scripts/*.py", ".claude/scripts/*.py"]


def _load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


# `cwd=` alone is not isolation: an exported GIT_DIR (leaked into a pre-push hook when
# pushing from a worktree, per shell.md) still wins over `-C`/`cwd`, silently reading a
# different repository's index. Strip the repo-location vars for every git call so this
# test resolves the worktree it actually runs in, not whatever a leaked hook exported.
_GIT_ENV_STRIP = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")


def _clean_git_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_STRIP}


def _git_ls_files(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", *args, *INCLUDE_PATHSPECS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=_clean_git_env(),
    )
    return [line for line in result.stdout.splitlines() if line]


class TestRootPyrightMode(unittest.TestCase):
    """Assertion 1: the config's type-checking mode has not been silently downgraded."""

    def test_config_exists(self):
        self.assertTrue(CONFIG_PATH.is_file(), f"expected {CONFIG_PATH} to exist")

    def test_type_checking_mode_is_standard(self):
        config = _load_config()
        self.assertEqual(config.get("typeCheckingMode"), "standard")

    def test_report_missing_imports_is_true(self):
        config = _load_config()
        self.assertIs(config.get("reportMissingImports"), True)

    def test_include_and_exclude_are_pinned_by_identity(self):
        # A count-only check (assertion 2 below) pins CARDINALITY, not IDENTITY: it
        # would not notice pyright's default `**/.*` exclude being restored on a day
        # `.claude/scripts` happens to hold as many files as it drops. Pin the actual
        # lists. `**/.*` is deliberately absent from exclude — measured: 10 files
        # analysed with the default exclude absent (today's config), 9 with it
        # restored — because exclude beats include and `.claude/scripts` starts with
        # a dot, so the whole directory (currently one file) would be dropped.
        config = _load_config()
        self.assertEqual(config.get("include"), ["scripts", "tests", ".claude/scripts"])
        self.assertEqual(config.get("exclude"), ["**/node_modules", "**/__pycache__"])


def error_lines(report: dict, root: Path) -> list[str]:
    """One `<repo-relative file>:<line> <rule> <message>` per error diagnostic."""
    lines = []
    for diag in report.get("generalDiagnostics", []):
        if diag.get("severity") != "error":
            continue
        try:
            name = Path(diag["file"]).relative_to(root).as_posix()
        except ValueError:
            name = diag["file"]
        line = diag["range"]["start"]["line"] + 1
        lines.append(f"{name}:{line} {diag.get('rule', '-')} {diag['message']}")
    return lines


SKIP_LINE = (
    "pyright not found; root type errors are unchecked locally (run: make install-deps)"
)


def error_problem(report: dict, root: Path) -> str | None:
    """None when the report has no errors, else a message listing them."""
    if report["summary"]["errorCount"] == 0:
        return None
    return "pyright errors:\n" + "\n".join(error_lines(report, root))


def version_problem(report: dict, pin: str) -> str | None:
    """None when the engine that ran equals the pin, else a message saying why not."""
    actual = report.get("version")
    if not actual:
        return "pyright report has no version field; cannot verify the engine version"
    if actual != pin:
        return (
            f"pyright engine is {actual} but requirements-dev.txt pins {pin}; "
            "run `make install-deps` to install the pinned version"
        )
    return None


def pinned_pyright(requirements_text: str) -> str:
    """The X.Y.Z of the `pyright==X.Y.Z` line in requirements-dev.txt."""
    match = re.search(r"^pyright==(\d+\.\d+\.\d+)\s*$", requirements_text, re.MULTILINE)
    if match is None:
        raise ValueError("requirements-dev.txt has no pinned pyright==X.Y.Z line")
    return match.group(1)


def _run_pyright(pyright_bin: str, cwd: Path) -> dict:
    result = subprocess.run(
        [pyright_bin, "--outputjson"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        # A crash or a bad flag empties stdout; a bare JSONDecodeError would name
        # neither the return code nor pyright's own diagnosis.
        raise RuntimeError(
            f"pyright --outputjson produced no JSON (rc={result.returncode}): "
            f"{result.stderr[:500]}"
        ) from None


_REAL_REPORT = {
    "version": "1.1.411",
    "summary": {"filesAnalyzed": 1, "errorCount": 0},
    "generalDiagnostics": [],
}


class TestPyrightHelpers(unittest.TestCase):
    def test_error_lines_formats_one_error_and_skips_warnings(self):
        report = {
            "generalDiagnostics": [
                {
                    "file": str(REPO_ROOT / "tests" / "a.py"),
                    "severity": "error",
                    "rule": "reportAssignmentType",
                    "message": "bad",
                    "range": {"start": {"line": 1, "character": 0}},
                },
                {
                    "file": str(REPO_ROOT / "tests" / "b.py"),
                    "severity": "warning",
                    "rule": "reportX",
                    "message": "meh",
                    "range": {"start": {"line": 4, "character": 0}},
                },
            ]
        }
        self.assertEqual(
            error_lines(report, REPO_ROOT),
            ["tests/a.py:2 reportAssignmentType bad"],
        )

    def test_error_lines_empty_when_no_diagnostics(self):
        self.assertEqual(error_lines(_REAL_REPORT, REPO_ROOT), [])

    def test_version_problem_match(self):
        self.assertIsNone(version_problem(_REAL_REPORT, "1.1.411"))

    def test_version_problem_mismatch_names_install_deps(self):
        message = version_problem(_REAL_REPORT, "1.1.400")
        self.assertIsNotNone(message)
        self.assertIn("make install-deps", message or "")
        self.assertIn("1.1.411", message or "")

    def test_version_problem_missing_is_distinct(self):
        for report in ({}, {"version": ""}):
            message = version_problem(report, "1.1.411")
            self.assertIn("no version field", message or "")
            self.assertNotIn("make install-deps", message or "")

    def test_pinned_pyright_reads_line(self):
        self.assertEqual(pinned_pyright("a==1.0.0\npyright==1.2.3\n"), "1.2.3")

    def test_pinned_pyright_missing_raises(self):
        with self.assertRaises(ValueError):
            pinned_pyright("defusedxml==0.7.1\n")

    def test_requirements_dev_pins_pyright(self):
        text = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
        self.assertRegex(pinned_pyright(text), r"^\d+\.\d+\.\d+$")


class TestSkipPath(unittest.TestCase):
    def _setup(self, env_has_ci: bool):
        class Probe(TestRootPyrightCoverage):
            pass

        env = {"CI": "true"} if env_has_ci else {}
        buf = StringIO()
        with (
            mock.patch("shutil.which", return_value=None),
            mock.patch.dict(os.environ, env),
            redirect_stderr(buf),
        ):
            if not env_has_ci:
                os.environ.pop("CI", None)
            try:
                Probe.setUpClass()
            except RuntimeError as exc:
                return Probe, buf.getvalue(), exc
        return Probe, buf.getvalue(), None

    def test_absent_pyright_outside_ci_writes_exact_line_and_skips(self):
        probe, err, exc = self._setup(env_has_ci=False)
        self.assertIsNone(exc)
        self.assertEqual(err, SKIP_LINE + "\n")
        self.assertIsNone(probe.pyright_bin)
        self.assertNotIn("report", vars(probe))
        with self.assertRaises(unittest.SkipTest):
            probe("test_no_pyright_errors").setUp()

    def test_absent_pyright_in_ci_raises(self):
        _, err, exc = self._setup(env_has_ci=True)
        self.assertIsInstance(exc, RuntimeError)
        self.assertEqual(err, "")


class TestRootPyrightCoverage(unittest.TestCase):
    """pyright's file count, error count and engine version at the repo root."""

    report: dict | None = None
    failure: str | None = None
    pyright_bin: str | None = None

    @classmethod
    def setUpClass(cls):
        cls.pyright_bin = shutil.which("pyright")
        # Presence, not truthiness: GitHub Actions sets CI=true, but a set-and-falsy
        # value (CI="", CI=0) must still fail closed rather than silently skip — only
        # a wholly UNSET CI means "not running under a CI runner at all".
        if cls.pyright_bin is None:
            if "CI" in os.environ:
                raise RuntimeError(
                    "pyright is required in CI but was not found on PATH"
                )
            sys.stderr.write(SKIP_LINE + "\n")
            return
        try:
            cls.report = _run_pyright(cls.pyright_bin, REPO_ROOT)
        except RuntimeError as exc:
            # self.fail is unavailable here; store and raise per test.
            cls.failure = str(exc)

    def setUp(self):
        if self.pyright_bin is None:
            self.skipTest("pyright not found on PATH")
        if self.failure is not None:
            self.fail(self.failure)

    def _report(self) -> dict:
        report = self.report
        if report is None:
            self.fail("no pyright report")
        return report

    def test_files_analyzed_equals_tracked_plus_untracked(self):
        tracked = _git_ls_files()
        untracked = _git_ls_files("-o")
        expected_files = sorted(set(tracked) | set(untracked))

        # Vacuity floor: an empty tracked set would make the equality below
        # trivially satisfiable by an empty pyright run.
        self.assertGreater(
            len(tracked),
            0,
            "expected at least one tracked .py file under the include roots",
        )
        files_analyzed = self._report()["summary"]["filesAnalyzed"]

        self.assertEqual(
            files_analyzed,
            len(expected_files),
            f"pyright analysed {files_analyzed} files; expected "
            f"{len(expected_files)} from tracked+untracked {INCLUDE_PATHSPECS}: "
            f"{expected_files}",
        )

    def test_no_pyright_errors(self):
        problem = error_problem(self._report(), REPO_ROOT)
        self.assertIsNone(problem, problem)

    def test_engine_version_matches_pin(self):
        text = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
        problem = version_problem(self._report(), pinned_pyright(text))
        self.assertIsNone(problem, problem)


class TestErrorProblem(unittest.TestCase):
    def test_zero_errors_is_none(self):
        self.assertIsNone(error_problem(_REAL_REPORT, REPO_ROOT))

    def test_one_error_exact_message(self):
        report = {
            "summary": {"errorCount": 1},
            "generalDiagnostics": [
                {
                    "file": str(REPO_ROOT / "tests" / "a.py"),
                    "severity": "error",
                    "rule": "reportAssignmentType",
                    "message": "bad",
                    "range": {"start": {"line": 1, "character": 0}},
                }
            ],
        }
        self.assertEqual(
            error_problem(report, REPO_ROOT),
            "pyright errors:\ntests/a.py:2 reportAssignmentType bad",
        )


class TestSeededPyrightError(unittest.TestCase):
    """R3: the gate can fail. A seeded type error yields exactly one error."""

    def test_seeded_assignment_error_is_reported(self):
        pyright_bin = shutil.which("pyright")
        if pyright_bin is None:
            if "CI" in os.environ:
                self.fail("pyright is required in CI but was not found on PATH")
            self.skipTest("pyright not found on PATH")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy(CONFIG_PATH, root / "pyrightconfig.json")
            (root / "scripts").mkdir()
            (root / "scripts" / "seeded.py").write_text(
                '\nx: int = "s"\n', encoding="utf-8"
            )
            report = _run_pyright(pyright_bin, root)
            self.assertEqual(report["summary"]["errorCount"], 1, report)
            diag = report["generalDiagnostics"][0]
            self.assertEqual(diag["rule"], "reportAssignmentType")
            self.assertEqual(diag["range"]["start"]["line"] + 1, 2)
            self.assertEqual(len(error_lines(report, root.resolve())), 1)
            problem = error_problem(report, root.resolve())
            self.assertIn("reportAssignmentType", problem or "")


if __name__ == "__main__":
    unittest.main()
