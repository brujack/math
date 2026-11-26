"""Behaviour of scripts/mutation_base_runner.py, the assertion-continuing runner (R11).

Each test builds a tiny module and base test file in a temp dir and runs the runner as a
subprocess with that dir as the working directory, as the weakening driver does.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNNER = REPO_ROOT / "scripts" / "mutation_base_runner.py"
TEST_FILE = "test_mod_base.py"
TEST_ID = "test_mod_base.T.test_a"
RUN_TIMEOUT_S = 120

HEADER = "import unittest\n\nimport mod\n\n\nclass T(unittest.TestCase):\n"


def make_test_source(body):
    """Wrap an indented test body in the standard header and one test method."""
    return (
        HEADER
        + "    def test_a(self):\n"
        + textwrap.indent(textwrap.dedent(body), "        ")
    )


def line_of(source, marker):
    """Return the 1-based line of the one source line containing `marker`."""
    hits = [i for i, text in enumerate(source.splitlines(), 1) if marker in text]
    assert len(hits) == 1, (marker, hits)
    return hits[0]


class RunnerCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = pathlib.Path(self._tmp.name)
        self.sig = self.dir / "sig.json"

    def write(self, module_src, test_src):
        (self.dir / "mod.py").write_text(textwrap.dedent(module_src))
        (self.dir / TEST_FILE).write_text(test_src)

    def run_runner(self, mode):
        env = {**os.environ, "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"}
        return subprocess.run(
            [sys.executable, str(RUNNER), mode, str(self.sig), TEST_FILE],
            cwd=self.dir,
            env=env,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=RUN_TIMEOUT_S,
            check=False,
        )

    def record(self, module_src, test_src):
        self.write(module_src, test_src)
        proc = self.run_runner("record")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(self.sig.read_text())

    def compare(self, module_src, test_src):
        self.write(module_src, test_src)
        return self.run_runner("compare")


class AssertionContinuationTests(RunnerCase):
    def test_both_failing_asserts_are_recorded(self):
        src = make_test_source("""\
            self.assertEqual(mod.f(1), 2)  # L1
            self.assertEqual(mod.f(2), 3)  # L2
            """)
        sig = self.record("def f(x):\n    return x * 10\n", src)[TEST_ID]
        self.assertEqual(sig["outcome"], "fail")
        self.assertEqual(
            sorted(s[0] for s in sig["sites"]),
            [line_of(src, "# L1"), line_of(src, "# L2")],
        )
        self.assertEqual({s[3] for s in sig["sites"]}, {"AssertionError"})

    def test_attribute_error_inside_assertion_is_a_site_and_test_continues(self):
        src = make_test_source("""\
            self.assertEqual(mod.missing.x, 1)  # L1
            self.assertEqual(mod.f(1), 99)  # L2
            """)
        sig = self.record("def f(x):\n    return x\n", src)[TEST_ID]
        self.assertEqual(sig["outcome"], "fail")
        self.assertIsNone(sig["error"])
        by_line = {s[0]: s[3] for s in sig["sites"]}
        self.assertEqual(by_line[line_of(src, "# L1")], "AttributeError")
        self.assertEqual(by_line[line_of(src, "# L2")], "AssertionError")

    def test_failing_assert_raises_block_continues(self):
        src = make_test_source("""\
            with self.assertRaises(ValueError):  # L1
                mod.f(1)
            self.assertEqual(mod.f(1), 99)  # L2
            """)
        sig = self.record("def f(x):\n    return x\n", src)[TEST_ID]
        self.assertEqual(sig["outcome"], "fail")
        self.assertEqual(
            sorted(s[0] for s in sig["sites"]),
            [line_of(src, "# L1"), line_of(src, "# L2")],
        )

    def test_failed_as_block_binds_placeholder_exception(self):
        src = make_test_source("""\
            with self.assertRaises(ValueError) as cm:  # L1
                mod.f(1)
            self.assertEqual(cm.exception.args, ("x",))  # L2
            self.assertEqual(1, 2)  # L3
            """)
        sig = self.record("def f(x):\n    return x\n", src)[TEST_ID]
        self.assertIsNone(sig["error"])
        self.assertEqual(sig["outcome"], "fail")
        lines = sorted(s[0] for s in sig["sites"])
        self.assertIn(line_of(src, "# L3"), lines)
        self.assertEqual(
            {s[3] for s in sig["sites"]},
            {"AssertionError"},
            "reading cm.exception must not raise AttributeError",
        )

    def test_bare_assert_statement_is_a_site(self):
        src = make_test_source("""\
            assert mod.f(1) == 99  # L1
            self.assertEqual(mod.f(1), 98)  # L2
            """)
        sig = self.record("def f(x):\n    return x\n", src)[TEST_ID]
        self.assertEqual(
            sorted(s[0] for s in sig["sites"]),
            [line_of(src, "# L1"), line_of(src, "# L2")],
        )

    def test_passing_test_has_no_sites(self):
        src = make_test_source("self.assertEqual(mod.f(1), 1)\n")
        sig = self.record("def f(x):\n    return x\n", src)[TEST_ID]
        self.assertEqual(sig, {"outcome": "pass", "sites": [], "error": None})


class SiteKeyTests(RunnerCase):
    LOOP_SRC = make_test_source("""\
        for i in (1, 2, 3):
            self.assertEqual(mod.f(i), 0)  # L1
        """)

    def test_later_loop_iteration_failing_is_a_new_site(self):
        self.record(
            "def f(x):\n    return 1 if x == 1 else 0\n",
            self.LOOP_SRC,
        )
        proc = self.compare(
            "def f(x):\n    return 1 if x in (1, 3) else 0\n", self.LOOP_SRC
        )
        self.assertNotEqual(proc.returncode, 0)

    def test_loop_with_same_failures_compares_clean(self):
        module = "def f(x):\n    return 1 if x == 1 else 0\n"
        sig = self.record(module, self.LOOP_SRC)[TEST_ID]
        self.assertEqual([s[2] for s in sig["sites"]], [1])
        self.assertEqual(self.compare(module, self.LOOP_SRC).returncode, 0)

    def test_subtest_params_are_part_of_the_site(self):
        src = make_test_source("""\
            for i in (1, 2):
                with self.subTest(i=i):
                    self.assertEqual(mod.f(i), 0)  # L1
            """)
        sig = self.record("def f(x):\n    return 1 if x == 2 else 0\n", src)[TEST_ID]
        self.assertEqual(len(sig["sites"]), 1)
        params = sig["sites"][0][1]
        self.assertIn("i", params)
        self.assertIn("2", params)

    def test_error_outside_assertion_records_type_and_line_not_message(self):
        src = make_test_source("""\
            mod.boom()  # L1
            self.assertEqual(1, 1)
            """)
        module = "def boom():\n    raise KeyError('secret-message')\n"
        sig = self.record(module, src)[TEST_ID]
        self.assertEqual(sig["outcome"], "error")
        self.assertEqual(sig["error"], ["KeyError", line_of(src, "# L1")])
        self.assertNotIn("secret-message", self.sig.read_text())

    def test_error_line_is_the_innermost_base_file_frame(self):
        src = (
            HEADER
            + "    def helper(self):\n        mod.boom()  # L1\n\n"
            + "    def test_a(self):\n        self.helper()\n"
        )
        module = "def boom():\n    raise KeyError('x')\n"
        sig = self.record(module, src)[TEST_ID]
        self.assertEqual(sig["error"], ["KeyError", line_of(src, "# L1")])


class CompareTests(RunnerCase):
    SRC = make_test_source("self.assertEqual(mod.f(1), 2)  # L1\n")

    def test_message_only_change_at_known_site_is_invisible(self):
        self.record("def f(x):\n    return 5\n", self.SRC)
        proc = self.compare("def f(x):\n    return 7\n", self.SRC)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_new_site_beside_known_failure_exits_nonzero(self):
        src = make_test_source("""\
            self.assertEqual(mod.f(1), 2)  # L1
            self.assertEqual(mod.g(1), 2)  # L2
            """)
        self.record("def f(x):\n    return 5\n\ndef g(x):\n    return 2\n", src)
        proc = self.compare("def f(x):\n    return 5\n\ndef g(x):\n    return 9\n", src)
        self.assertNotEqual(proc.returncode, 0)

    def test_outcome_change_exits_nonzero(self):
        self.record("def f(x):\n    return 2\n", self.SRC)
        proc = self.compare("def f(x):\n    raise RuntimeError('x')\n", self.SRC)
        self.assertNotEqual(proc.returncode, 0)

    def test_fixed_failure_exits_nonzero(self):
        self.record("def f(x):\n    return 5\n", self.SRC)
        proc = self.compare("def f(x):\n    return 2\n", self.SRC)
        self.assertNotEqual(proc.returncode, 0)

    def test_identical_run_exits_zero(self):
        module = "def f(x):\n    return 2\n"
        self.record(module, self.SRC)
        self.assertEqual(self.compare(module, self.SRC).returncode, 0)

    def test_stderr_never_carries_exception_messages(self):
        self.record("def f(x):\n    return 2\n", self.SRC)
        proc = self.compare(
            "def f(x):\n    raise RuntimeError('leaky-message')\n", self.SRC
        )
        self.assertNotIn("leaky-message", proc.stderr)


class OutcomeKindTests(RunnerCase):
    def test_every_outcome_kind_is_recorded(self):
        src = (
            "import unittest\n\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_pass(self):\n        pass\n\n"
            "    def test_fail(self):\n        self.fail('x')\n\n"
            "    def test_error(self):\n        raise RuntimeError('x')\n\n"
            "    @unittest.skip('r')\n    def test_skip(self):\n        pass\n\n"
            "    @unittest.expectedFailure\n    def test_xfail(self):\n        self.fail('x')\n\n"
            "    @unittest.expectedFailure\n    def test_xpass(self):\n        pass\n"
        )
        sig = self.record("", src)
        outcomes = {k.rsplit(".", 1)[1]: v["outcome"] for k, v in sig.items()}
        self.assertEqual(
            outcomes,
            {
                "test_pass": "pass",
                "test_fail": "fail",
                "test_error": "error",
                "test_skip": "skip",
                "test_xfail": "expected-failure",
                "test_xpass": "unexpected-success",
            },
        )

    def test_unrewritten_self_fail_is_a_site(self):
        src = make_test_source("self.fail('x')  # L1\n")
        sig = self.record("", src)[TEST_ID]
        self.assertEqual(sig["outcome"], "fail")
        self.assertEqual([s[0] for s in sig["sites"]], [line_of(src, "# L1")])

    def test_expected_failure_with_caught_assertion_stays_expected_failure(self):
        src = (
            HEADER
            + "    @unittest.expectedFailure\n    def test_a(self):\n"
            + "        self.assertEqual(1, 2)\n"
        )
        sig = self.record("", src)[TEST_ID]
        self.assertEqual(sig["outcome"], "expected-failure")

    def test_import_failure_is_recorded_as_a_failed_test(self):
        src = "import no_such_module_xyz\n"
        sig = self.record("", src)
        self.assertEqual(list(sig), ["unittest.loader._FailedTest.test_mod_base"])
        record = next(iter(sig.values()))
        self.assertEqual(record["outcome"], "error")
        self.assertEqual(record["error"][0], "ModuleNotFoundError")

    def test_skip_test_inside_assert_block_still_skips(self):
        src = make_test_source("""\
            with self.assertRaises(ValueError):
                self.skipTest('r')
            """)
        sig = self.record("", src)[TEST_ID]
        self.assertEqual(sig["outcome"], "skip")


class CliTests(RunnerCase):
    def test_unknown_mode_exits_two(self):
        self.write("", make_test_source("pass\n"))
        proc = self.run_runner("bogus")
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
