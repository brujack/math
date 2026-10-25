"""Unit tests for scripts/cli_contract.py, run against stub programs.

Each bad stub in tests/fixtures/cli_contract/ breaks exactly one rule of the
CLI contract, so a test per stub proves the matching harness case can fail.
A harness that only ever passes would be indistinguishable from no harness.
"""

import contextlib
import io
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import cli_contract

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "cli_contract"

# silent_reader can only fail by timeout; keep that fast in the suite.
SHORT_TIMEOUT = 1


def _process_alive(pid: int) -> bool:
    """True while pid is a live process; a zombie awaiting reaping is dead."""
    done = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=False,
    )
    state = done.stdout.strip()
    return bool(state) and not state.startswith("Z")


def _open_fd_count() -> int:
    return len(os.listdir("/dev/fd"))


def _mutant(directory: pathlib.Path, edits: list[tuple[str, str]]) -> pathlib.Path:
    """Write conforming.py with one defect introduced, and return its path."""
    source = (FIXTURES / "conforming.py").read_text()
    for old, new in edits:
        assert old in source, old
        source = source.replace(old, new)
    path = directory / "mutant.py"
    path.write_text(source)
    return path


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
            with self.assertRaises(cli_contract.ContractConfigError):
                cli_contract.load_constants(bare)

    def test_import_failure_is_a_config_error_naming_the_cause(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = pathlib.Path(tmp) / "broken.py"
            broken.write_text("import cli_contract_no_such_module\n")
            with self.assertRaises(cli_contract.ContractConfigError) as caught:
                cli_contract.load_constants(broken)
        self.assertIn("broken.py: importing to read", str(caught.exception))
        self.assertIn("ModuleNotFoundError", str(caught.exception))


class TestRunCase(unittest.TestCase):
    def _own_pid_file(self, tag: str) -> pathlib.Path:
        """Own the pid file a sleeper fixture writes; kill and remove it on cleanup.

        The fixture names the file from its parent pid (this process) and a fixed
        tag, so no environment input reaches open(). The cleanup is registered
        before run_case so a failing or raising test cannot leak a sleeper
        (tdd-007: an inert failure mode).
        """
        pid_file = (
            pathlib.Path(tempfile.gettempdir())
            / f"cli_contract_{os.getpid()}_{tag}.pid"
        )
        pid_file.unlink(missing_ok=True)
        self.addCleanup(pid_file.unlink, missing_ok=True)

        def kill_sleeper() -> None:
            try:
                os.kill(int(pid_file.read_text()), signal.SIGKILL)
            except (FileNotFoundError, ProcessLookupError, ValueError):
                pass

        self.addCleanup(kill_sleeper)
        return pid_file

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
        self.assertIsNone(result.returncode)

    def test_each_case_gets_a_fresh_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = pathlib.Path(tmp) / "writer.py"
            writer.write_text("import sys\nopen(sys.argv[1], 'w').write('x')\n")
            first = cli_contract.run_case(writer, ["leftover.txt"])
            second = cli_contract.run_case(writer, ["other.txt"])
        self.assertIn("leftover.txt", first.files)
        self.assertEqual(list(second.files), ["other.txt"])

    def test_non_utf8_output_is_replaced_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            noisy = pathlib.Path(tmp) / "noisy.py"
            noisy.write_text("import sys\nsys.stdout.buffer.write(b'\\xff\\n')\n")
            result = cli_contract.run_case(noisy, [])
        self.assertEqual(result.returncode, 0)
        self.assertIn("\ufffd", result.stdout)

    def test_timeout_kills_the_whole_process_group(self):
        pid_file = self._own_pid_file("reader")
        start = time.monotonic()
        result = cli_contract.run_case(
            FIXTURES / "grandchild_reader.py", [], timeout=SHORT_TIMEOUT
        )
        elapsed = time.monotonic() - start
        self.assertTrue(result.timed_out)
        self.assertIsNone(result.returncode)
        self.assertLess(elapsed, SHORT_TIMEOUT + 5)
        grandchild = int(pid_file.read_text())
        for _ in range(50):
            if not _process_alive(grandchild):
                break
            time.sleep(0.1)
        self.assertFalse(_process_alive(grandchild), "grandchild survived the timeout")

    def test_group_is_reaped_after_a_passing_run(self):
        pid_file = self._own_pid_file("leftover")
        result = cli_contract.run_case(FIXTURES / "leaves_grandchild.py", [])
        self.assertEqual(result.returncode, 0)
        grandchild = int(pid_file.read_text())
        for _ in range(50):
            if not _process_alive(grandchild):
                break
            time.sleep(0.1)
        self.assertFalse(
            _process_alive(grandchild), "grandchild outlived a passing run"
        )

    def test_drain_timeout_returns_timed_out_with_partial_output(self):
        self._own_pid_file("escaped")
        before = _open_fd_count()
        procs: list[subprocess.Popen[str]] = []
        real_popen = subprocess.Popen

        def spy(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            procs.append(proc)  # keeps the pipes alive so only an explicit close shows
            return proc

        with (
            mock.patch.object(cli_contract, "_DRAIN_TIMEOUT", SHORT_TIMEOUT),
            mock.patch.object(cli_contract.subprocess, "Popen", spy),
        ):
            result = cli_contract.run_case(
                FIXTURES / "escaped_grandchild.py", [], timeout=SHORT_TIMEOUT
            )
        self.assertTrue(result.timed_out)
        self.assertIsNone(result.returncode)
        self.assertIn("partial output", result.stdout)
        self.assertEqual(len(procs), 1)
        self.assertTrue(procs[0].stdout is not None and procs[0].stdout.closed)
        self.assertTrue(procs[0].stderr is not None and procs[0].stderr.closed)
        self.assertEqual(
            _open_fd_count(), before, "pipes left open after the drain gave up"
        )

    def test_interrupt_kills_the_child_and_propagates(self):
        started: list[int] = []
        procs: list[subprocess.Popen[str]] = []
        real_popen = subprocess.Popen

        watchdog_fired: list[bool] = []

        def release_hung_child() -> None:
            # Without this, a harness that fails to kill the child on interrupt
            # hangs in proc.wait() forever instead of failing the test.
            watchdog_fired.append(True)
            os.kill(started[0], signal.SIGKILL)

        watchdog = threading.Timer(3, release_hung_child)
        watchdog.daemon = True
        self.addCleanup(watchdog.cancel)

        def spy(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            started.append(proc.pid)
            procs.append(proc)
            watchdog.start()
            return proc

        with (
            mock.patch.object(cli_contract.subprocess, "Popen", spy),
            mock.patch.object(real_popen, "communicate", side_effect=KeyboardInterrupt),
            self.assertRaises(KeyboardInterrupt),
        ):
            cli_contract.run_case(FIXTURES / "silent_reader.py", ["2"])
        watchdog.cancel()
        self.assertEqual(watchdog_fired, [], "harness left the child running")
        self.assertFalse(_process_alive(started[0]), "child survived the interrupt")
        for proc in procs:
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()


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


class TestRunCaseReleasesResources(unittest.TestCase):
    def test_normal_path_leaks_no_descriptors(self):
        before = _open_fd_count()
        cli_contract.run_case(FIXTURES / "conforming.py", ["2"])
        self.assertEqual(_open_fd_count(), before)

    def test_timeout_path_leaks_no_descriptors(self):
        before = _open_fd_count()
        cli_contract.run_case(
            FIXTURES / "silent_reader.py", ["2"], timeout=SHORT_TIMEOUT
        )
        self.assertEqual(_open_fd_count(), before)

    def test_popen_failure_leaks_no_descriptors_or_directory(self):
        before = _open_fd_count()
        with tempfile.TemporaryDirectory() as scratch:
            with (
                mock.patch.object(tempfile, "tempdir", scratch),
                mock.patch.object(sys, "executable", "/nonexistent/python"),
                self.assertRaises(FileNotFoundError),
            ):
                cli_contract.run_case(FIXTURES / "conforming.py", ["2"])
            self.assertEqual(os.listdir(scratch), [])
        self.assertEqual(_open_fd_count(), before)

    def test_directory_is_removed_after_a_normal_run(self):
        with tempfile.TemporaryDirectory() as scratch:
            with mock.patch.object(tempfile, "tempdir", scratch):
                cli_contract.run_case(FIXTURES / "conforming.py", ["2"])
            self.assertEqual(os.listdir(scratch), [])


class TestEachCheckHasAFailingMutant(unittest.TestCase):
    """One single-defect program per check; the exact problem text is asserted."""

    def _failures(self, edits: list[tuple[str, str]]) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            return cli_contract.run_matrix(_mutant(pathlib.Path(tmp), edits))

    def test_question_mark_alone_is_a_prompt(self):
        failures = self._failures(
            [('    print(f"Wrote', '    print("Done, continue?")\n    print(f"Wrote')]
        )
        self.assertIn(
            "case 1 (SIZE): stdout line looks like a prompt: 'Done, continue?'",
            failures,
        )

    def test_y_n_marker_alone_is_a_prompt(self):
        failures = self._failures(
            [('    print(f"Wrote', '    print("Continue (y/n)")\n    print(f"Wrote')]
        )
        self.assertIn(
            "case 1 (SIZE): stdout line looks like a prompt: 'Continue (y/n)'", failures
        )

    def test_refusal_that_writes_a_file_fails_case_5(self):
        failures = self._failures(
            [
                (
                    "        sys.exit(1)",
                    '        open("partial.txt", "w").close()\n        sys.exit(1)',
                )
            ]
        )
        self.assertIn(
            "case 5 (THRESHOLD without --yes): wrote files before confirmation: "
            "['partial.txt']",
            failures,
        )

    def test_refusal_not_naming_yes_fails_case_5(self):
        failures = self._failures([("; pass --yes to proceed.", ".")])
        self.assertIn(
            "case 5 (THRESHOLD without --yes): refusal does not name --yes", failures
        )

    def test_refusal_exiting_2_fails_case_5(self):
        failures = self._failures([("        sys.exit(1)", "        sys.exit(2)")])
        self.assertIn("case 5 (THRESHOLD without --yes): exit 2, expected 1", failures)

    def test_nonzero_exit_after_writing_fails_case_1(self):
        failures = self._failures(
            [('    print(f"Wrote {len(lines)} results to out.txt")', "    sys.exit(3)")]
        )
        self.assertIn("case 1 (SIZE): exit 3, expected 0", failures)

    def test_echoing_longest_line_without_show_fails_case_1(self):
        failures = self._failures([("if args.show:", "if True:")])
        self.assertIn(
            "case 1 (SIZE): stdout echoes the longest result line without --show",
            failures,
        )

    def test_ignoring_show_fails_case_2(self):
        failures = self._failures([("if args.show:", "if False:")])
        self.assertIn(
            "case 2 (SIZE --show): --show did not print the longest result line",
            failures,
        )

    def test_show_that_writes_no_file_fails_case_2(self):
        # Blank stdout line == the empty "longest" of a missing file, so only the
        # explicit "no non-empty output file" branch can flag this program.
        failures = self._failures(
            [
                (
                    '    with open("out.txt", "w") as handle:\n'
                    '        handle.write("".join(line + "\\n" for line in lines))\n'
                    "    if args.show:\n"
                    '        print("\\n".join(lines))\n',
                    "    if args.show:\n"
                    '        print("")\n'
                    "    else:\n"
                    '        with open("out.txt", "w") as handle:\n'
                    '            handle.write("".join(line + "\\n" for line in lines))\n',
                )
            ]
        )
        self.assertIn("case 2 (SIZE --show): wrote no non-empty output file", failures)

    def test_exit_0_with_no_arguments_fails_case_6(self):
        failures = self._failures(
            [
                (
                    '        parser.error("SIZE is required when stdin is not a terminal")',
                    "        args.size = SMOKE_SIZE",
                )
            ]
        )
        self.assertIn("case 6 (no arguments): exit 0, expected 2", failures)

    def test_echo_only_after_y_on_stdin_fails_only_case_4(self):
        failures = self._failures(
            [
                ("import sys\n", "import select\nimport sys\n"),
                (
                    "    if args.show:",
                    "    if select.select([sys.stdin], [], [], 0.5)[0]:\n"
                    '        if sys.stdin.readline().strip() == "y":\n'
                    "            print(lines[0])\n"
                    "    if args.show:",
                ),
            ]
        )
        self.assertEqual(
            failures,
            [
                "case 4 (y on stdin): stdout echoes the longest result line without --show"
            ],
        )


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

    def test_program_failing_to_import_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = pathlib.Path(tmp) / "broken.py"
            broken.write_text("import cli_contract_no_such_module\n")
            code, _, err = self._run([str(broken)])
        self.assertEqual(code, 2)
        self.assertIn("ModuleNotFoundError", err)

    def test_program_without_constants_is_a_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            bare = pathlib.Path(tmp) / "bare.py"
            bare.write_text("X = 1\n")
            self.assertEqual(self._run([str(bare)])[0], 2)


if __name__ == "__main__":
    unittest.main()
