"""Unit tests for scripts/cli_contract.py, run against stub programs.

Each bad stub in tests/fixtures/cli_contract/ breaks exactly one rule of the
CLI contract, so a test per stub proves the matching harness case can fail.
A harness that only ever passes would be indistinguishable from no harness.
"""

import contextlib
import io
import pathlib
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import cli_contract

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "cli_contract"

# silent_reader can only fail by timeout; keep that fast in the suite.
SHORT_TIMEOUT = 1


def _failures_naming(failures: list[str], case: int) -> list[str]:
    return [f for f in failures if f.startswith(f"case {case} ")]


class TestLoadConstants(unittest.TestCase):
    def test_reads_threshold_stub(self):
        self.assertEqual(
            cli_contract.load_constants(FIXTURES / "conforming.py"), (2, 5)
        )

    def test_reads_none_threshold(self):
        self.assertEqual(
            cli_contract.load_constants(FIXTURES / "conforming_no_threshold.py"),
            (2, None),
        )

    def test_missing_constant_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            bare = pathlib.Path(tmp) / "bare.py"
            bare.write_text("X = 1\n")
            with self.assertRaises(ValueError):
                cli_contract.load_constants(bare)


class TestRunCase(unittest.TestCase):
    def test_collects_exit_code_streams_and_files(self):
        result = cli_contract.run_case(FIXTURES / "conforming.py", ["2", "--show"])
        self.assertEqual(result.returncode, 0)
        self.assertFalse(result.timed_out)
        self.assertIn("out.txt", result.files)
        self.assertIn("result 1", result.stdout)

    def test_stdin_is_open_and_carries_the_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            echo = pathlib.Path(tmp) / "echo.py"
            echo.write_text(
                "import sys\nprint('got:' + sys.stdin.readline().strip())\n"
            )
            result = cli_contract.run_case(echo, [], stdin_text="y\n")
        self.assertEqual(result.stdout.strip(), "got:y")

    def test_open_stdin_with_no_text_blocks_until_timeout(self):
        # An EOF-reading program would exit at once; the open pipe makes it block.
        result = cli_contract.run_case(
            FIXTURES / "silent_reader.py", ["2"], timeout=SHORT_TIMEOUT
        )
        self.assertTrue(result.timed_out)

    def test_each_case_gets_a_fresh_directory(self):
        first = cli_contract.run_case(FIXTURES / "conforming.py", ["2"])
        second = cli_contract.run_case(FIXTURES / "conforming.py", ["3"])
        self.assertEqual(first.files["out.txt"].count("\n"), 2)
        self.assertEqual(second.files["out.txt"].count("\n"), 3)


class TestRunMatrixPasses(unittest.TestCase):
    def test_conforming_with_threshold_has_no_failures(self):
        self.assertEqual(cli_contract.run_matrix(FIXTURES / "conforming.py"), [])

    def test_conforming_without_threshold_has_no_failures(self):
        self.assertEqual(
            cli_contract.run_matrix(FIXTURES / "conforming_no_threshold.py"), []
        )


class TestRunMatrixCanFail(unittest.TestCase):
    def test_prompting_program_fails_case_1(self):
        failures = cli_contract.run_matrix(FIXTURES / "prompts.py")
        self.assertTrue(_failures_naming(failures, 1), failures)

    def test_program_writing_no_file_fails_case_1(self):
        failures = cli_contract.run_matrix(FIXTURES / "writes_nothing.py")
        self.assertTrue(_failures_naming(failures, 1), failures)

    def test_program_writing_an_empty_file_fails_case_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = pathlib.Path(tmp) / "empty.py"
            empty.write_text(
                textwrap.dedent(
                    """\
                    SMOKE_SIZE = 2
                    LARGE_RUN_THRESHOLD = None
                    if __name__ == "__main__":
                        open("out.txt", "w").close()
                    """
                )
            )
            failures = cli_contract.run_matrix(empty)
        self.assertTrue(_failures_naming(failures, 1), failures)

    def test_silent_stdin_reader_fails_by_timeout(self):
        with mock.patch.object(cli_contract, "CASE_TIMEOUT", SHORT_TIMEOUT):
            failures = cli_contract.run_matrix(FIXTURES / "silent_reader.py")
        timed_out = [f for f in failures if "timed out" in f]
        self.assertTrue(_failures_naming(timed_out, 1), failures)
        self.assertTrue(_failures_naming(timed_out, 3), failures)

    def test_program_ignoring_its_threshold_fails_case_5(self):
        failures = cli_contract.run_matrix(FIXTURES / "no_refusal.py")
        self.assertTrue(_failures_naming(failures, 5), failures)

    def test_program_rejecting_yes_fails_case_5(self):
        failures = cli_contract.run_matrix(FIXTURES / "rejects_yes.py")
        self.assertTrue(_failures_naming(failures, 5), failures)

    def test_failure_message_names_case_and_label(self):
        failures = cli_contract.run_matrix(FIXTURES / "prompts.py")
        self.assertIn("case 1 (SIZE)", failures[0])


class TestMain(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli_contract.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_conforming_exits_0_and_says_so(self):
        code, out, _ = self._run([str(FIXTURES / "conforming.py")])
        self.assertEqual(code, 0)
        self.assertIn("cli_contract: conforming.py: all cases pass", out)

    def test_failing_program_exits_1_and_prints_each_failure(self):
        code, out, err = self._run([str(FIXTURES / "writes_nothing.py")])
        self.assertEqual(code, 1)
        self.assertIn("case 1", out + err)

    def test_no_arguments_is_a_usage_error(self):
        self.assertEqual(self._run([])[0], 2)

    def test_too_many_arguments_is_a_usage_error(self):
        self.assertEqual(self._run(["a.py", "b.py"])[0], 2)

    def test_nonexistent_path_is_a_usage_error(self):
        self.assertEqual(self._run([str(FIXTURES / "does_not_exist.py")])[0], 2)

    def test_program_without_constants_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bare = pathlib.Path(tmp) / "bare.py"
            bare.write_text("X = 1\n")
            self.assertEqual(self._run([str(bare)])[0], 2)


if __name__ == "__main__":
    unittest.main()
