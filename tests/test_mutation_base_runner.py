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
FAILED_LOAD_ID = "unittest.loader._FailedTest.test_mod_base"
RUN_TIMEOUT_S = 120
PASSING_MODULE = "def f(x):\n    return x\n"
NO_PARAMS = "[]"
DIFF = "mutation_base_runner: diff: "
INTERNAL = "mutation_base_runner: internal error: "

HEADER = "import unittest\n\nimport mod\n\n\nclass T(unittest.TestCase):\n"


def make_test_source(body, header=HEADER):
    """Wrap an indented test body in a header and one test method."""
    return (
        header
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

    def run_args(self, args, hash_seed: str | None = "0"):
        env = {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        if hash_seed is not None:
            env["PYTHONHASHSEED"] = hash_seed
        return subprocess.run(
            [sys.executable, str(RUNNER), *args],
            cwd=self.dir,
            env=env,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=RUN_TIMEOUT_S,
            check=False,
        )

    def run_runner(self, mode, hash_seed: str | None = "0"):
        return self.run_args([mode, str(self.sig), TEST_FILE], hash_seed)

    def record(self, module_src, test_src, hash_seed: str | None = "0"):
        self.write(module_src, test_src)
        proc = self.run_runner("record", hash_seed)
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
        sig = self.record(PASSING_MODULE, src)[TEST_ID]
        self.assertEqual(sig["outcome"], "fail")
        self.assertEqual(sig["error"], [])
        by_line = {s[0]: s[3] for s in sig["sites"]}
        self.assertEqual(by_line[line_of(src, "# L1")], "AttributeError")
        self.assertEqual(by_line[line_of(src, "# L2")], "AssertionError")

    def test_failing_assert_raises_block_continues(self):
        src = make_test_source("""\
            with self.assertRaises(ValueError):  # L1
                mod.f(1)
            self.assertEqual(mod.f(1), 99)  # L2
            """)
        sig = self.record(PASSING_MODULE, src)[TEST_ID]
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
        sig = self.record(PASSING_MODULE, src)[TEST_ID]
        self.assertEqual(sig["error"], [])
        self.assertEqual(sig["outcome"], "fail")
        self.assertIn(line_of(src, "# L3"), [s[0] for s in sig["sites"]])
        self.assertEqual(
            {s[3] for s in sig["sites"]},
            {"AssertionError"},
            "reading cm.exception must not raise AttributeError",
        )

    def test_failed_assert_logs_block_binds_every_watcher_attribute(self):
        src = make_test_source("""\
            with self.assertLogs("never-logged") as cm:  # L1
                pass
            seen = (cm.output, cm.records)
            self.assertEqual(1, 2)  # L2
            """)
        sig = self.record(PASSING_MODULE, src)[TEST_ID]
        self.assertEqual(sig["error"], [])
        self.assertEqual(sig["outcome"], "fail")
        self.assertIn(line_of(src, "# L2"), [s[0] for s in sig["sites"]])

    def test_failed_assert_warns_block_binds_warning_attributes(self):
        src = make_test_source("""\
            with self.assertWarns(UserWarning) as cm:  # L1
                pass
            seen = (cm.warning, cm.filename, cm.lineno)
            self.assertEqual(1, 2)  # L2
            """)
        sig = self.record(PASSING_MODULE, src)[TEST_ID]
        self.assertEqual(sig["error"], [])
        self.assertIn(line_of(src, "# L2"), [s[0] for s in sig["sites"]])

    def test_failed_assert_warns_block_binds_warnings_list(self):
        src = make_test_source("""\
            with self.assertWarns(UserWarning) as cm:  # L1
                pass
            seen = cm.warnings
            self.assertEqual(1, 2)  # L2
            """)
        sig = self.record(PASSING_MODULE, src)[TEST_ID]
        self.assertEqual(sig["error"], [])
        self.assertIn(line_of(src, "# L2"), [s[0] for s in sig["sites"]])

    def test_multi_item_with_binds_every_named_item(self):
        src = make_test_source("""\
            with self.assertRaises(ValueError) as a, self.assertRaises(KeyError) as b:  # L1
                mod.f(1)
            seen = (a.exception.args, b.exception.args)
            self.assertEqual(1, 2)  # L2
            """)
        sig = self.record(PASSING_MODULE, src)[TEST_ID]
        self.assertEqual(sig["error"], [])
        self.assertEqual(
            sorted(s[0] for s in sig["sites"]),
            [line_of(src, "# L1"), line_of(src, "# L2")],
        )

    def test_assertion_in_nested_function_is_continued(self):
        src = make_test_source("""\
            def helper():
                self.assertEqual(1, 2)  # L1
            helper()
            self.assertEqual(1, 3)  # L2
            """)
        sig = self.record(PASSING_MODULE, src)[TEST_ID]
        self.assertEqual(
            sorted(s[0] for s in sig["sites"]),
            [line_of(src, "# L1"), line_of(src, "# L2")],
        )

    def test_bare_assert_statement_is_a_site(self):
        src = make_test_source("""\
            assert mod.f(1) == 99  # L1
            self.assertEqual(mod.f(1), 98)  # L2
            """)
        sig = self.record(PASSING_MODULE, src)[TEST_ID]
        self.assertEqual(
            sorted(s[0] for s in sig["sites"]),
            [line_of(src, "# L1"), line_of(src, "# L2")],
        )

    def test_passing_test_has_no_sites(self):
        src = make_test_source("self.assertEqual(mod.f(1), 1)\n")
        sig = self.record(PASSING_MODULE, src)[TEST_ID]
        self.assertEqual(
            sig, {"outcome": "pass", "sites": [], "error": [], "setup_error": False}
        )


class AuthorHandlerTests(RunnerCase):
    def site_lines(self, body):
        src = make_test_source(body)
        sig = self.record(PASSING_MODULE, src)[TEST_ID]
        return src, [s[0] for s in sig["sites"]]

    def test_broad_author_handlers_leave_their_body_unrewritten(self):
        for handler in (
            "except AssertionError:",
            "except Exception:",
            "except BaseException:",
            "except (ValueError, AssertionError):",
            "except:",
        ):
            with self.subTest(handler=handler):
                src, lines = self.site_lines(
                    "try:\n"
                    "    self.assertEqual(1, 2)  # L1\n"
                    f"{handler}\n"
                    "    pass\n"
                    "self.assertEqual(1, 3)  # L2\n"
                )
                self.assertEqual(lines, [line_of(src, "# L2")])

    def test_failure_exception_handlers_leave_their_body_unrewritten(self):
        for handler in (
            "except self.failureException:",
            "except unittest.TestCase.failureException:",
            "except (ValueError, self.failureException):",
            "except builtins.Exception:",
            "except builtins.BaseException:",
        ):
            with self.subTest(handler=handler):
                src, lines = self.site_lines(
                    "import builtins\n"
                    "try:\n"
                    "    self.assertEqual(1, 2)  # L1\n"
                    f"{handler}\n"
                    "    pass\n"
                    "self.assertEqual(1, 3)  # L2\n"
                )
                self.assertEqual(lines, [line_of(src, "# L2")])

    def test_except_star_with_broad_group_protects_its_body(self):
        src, lines = self.site_lines(
            "try:\n"
            "    self.assertEqual(1, 2)  # L1\n"
            "except* AssertionError:\n"
            "    pass\n"
            "self.assertEqual(1, 3)  # L2\n"
        )
        self.assertEqual(lines, [line_of(src, "# L2")])

    def test_except_star_with_narrow_group_still_rewrites_its_body(self):
        src = make_test_source(
            "try:\n    self.assertEqual(1, 2)  # L1\nexcept* ValueError:\n    pass\n"
        )
        sig = self.record(PASSING_MODULE, src)[TEST_ID]
        # nth 1 means the guard recorded it; nth 0 would be unittest's own failure.
        self.assertEqual(
            sig["sites"], [[line_of(src, "# L1"), NO_PARAMS, 1, "AssertionError"]]
        )

    def test_narrow_author_handler_does_not_protect_its_body(self):
        src, lines = self.site_lines(
            "try:\n    self.assertEqual(1, 2)  # L1\nexcept ValueError:\n    pass\n"
        )
        self.assertEqual(lines, [line_of(src, "# L1")])

    def test_assertion_inside_assert_raises_block_is_left_alone(self):
        for ctx in (
            "self.assertRaises(AssertionError)",
            "self.assertRaisesRegex(AssertionError, '.')",
        ):
            with self.subTest(ctx=ctx):
                src, lines = self.site_lines(
                    f"with {ctx}:\n    self.assertEqual(1, 2)  # L1\nself.assertEqual(1, 3)  # L2\n"
                )
                self.assertEqual(lines, [line_of(src, "# L2")])

    def test_assertion_inside_assert_warns_block_is_left_alone(self):
        src, lines = self.site_lines(
            "import warnings\n"
            "with self.assertWarns(UserWarning):  # L0\n"
            "    warnings.warn('w', UserWarning)\n"
            "    self.assertEqual(1, 2)  # L1\n"
            "self.assertEqual(1, 3)  # L2\n"
        )
        # Left alone, the inner failure escapes the block and the OUTER guard records it.
        self.assertEqual(lines, [line_of(src, "# L0"), line_of(src, "# L2")])

    def test_nested_function_inside_protected_try_is_still_rewritten(self):
        src, lines = self.site_lines(
            "try:\n"
            "    def helper():\n"
            "        self.assertEqual(1, 2)  # L1\n"
            "    helper()\n"
            "except Exception:\n"
            "    pass\n"
        )
        self.assertEqual(lines, [line_of(src, "# L1")])


class SiteKeyTests(RunnerCase):
    LOOP_SRC = make_test_source("""\
        for i in (1, 2, 3):
            self.assertEqual(mod.f(i), 0)  # L1
        """)

    def test_later_loop_iteration_failing_is_a_new_site(self):
        self.record("def f(x):\n    return 1 if x == 1 else 0\n", self.LOOP_SRC)
        proc = self.compare(
            "def f(x):\n    return 1 if x in (1, 3) else 0\n", self.LOOP_SRC
        )
        line = line_of(self.LOOP_SRC, "# L1")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(
            proc.stderr.splitlines(),
            [
                f"{DIFF}{TEST_ID}: new failure site {[line, NO_PARAMS, 3, 'AssertionError']}"
            ],
        )

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

    def test_subtest_failure_outside_a_guarded_statement_is_a_site(self):
        src = make_test_source("""\
            with self.subTest(i=7):
                self.fail("x")  # L1
            """)
        sig = self.record(PASSING_MODULE, src)[TEST_ID]
        self.assertEqual(sig["outcome"], "fail")
        self.assertEqual(len(sig["sites"]), 1)
        line, params, nth, exc_type = sig["sites"][0]
        self.assertEqual(
            (line, nth, exc_type), (line_of(src, "# L1"), 0, "AssertionError")
        )
        self.assertIn("7", params)

    def test_params_key_is_stable_across_hash_seeds_and_object_addresses(self):
        src = make_test_source("""\
            for s in ({"a", "b", "c", "d", "e"}, frozenset({"p", "q", "r", "s"})):
                with self.subTest(s=s, o=object()):
                    self.assertEqual(1, 2)  # L1
            """)
        recordings = []
        for _ in range(4):
            self.record(PASSING_MODULE, src, hash_seed=None)
            recordings.append(self.sig.read_text())
        self.assertEqual(len(set(recordings)), 1)
        self.assertNotIn("0x", recordings[0].replace("0x?", ""))

    def record_params(self, subtest_args):
        src = make_test_source(
            "with self.subTest("
            + subtest_args
            + "):\n    self.assertEqual(1, 2)  # L1\n"
        )
        texts = set()
        params = ""
        for _ in range(4):
            sig = self.record(PASSING_MODULE, src, hash_seed=None)[TEST_ID]
            texts.add(self.sig.read_text())
            params = sig["sites"][0][1]
        self.assertEqual(len(texts), 1)
        return params

    def test_set_nested_in_dict_param_is_canonical(self):
        params = self.record_params('p={"k": {"b", "a", "c", "d", "e"}}')
        self.assertIn("{'k': {'a', 'b', 'c', 'd', 'e'}}", params)

    def test_set_nested_in_tuple_param_is_canonical(self):
        params = self.record_params('p=(1, {"b", "a", "c", "d", "e"})')
        self.assertIn("(1, {'a', 'b', 'c', 'd', 'e'})", params)

    def test_set_nested_in_list_param_is_canonical(self):
        params = self.record_params('p=[frozenset({"b", "a", "c", "d", "e"})]')
        self.assertIn("[frozenset({'a', 'b', 'c', 'd', 'e'})]", params)

    def test_single_element_tuple_param_keeps_its_comma(self):
        self.assertIn("(1,)", self.record_params("p=(1,)"))


class ErrorRecordingTests(RunnerCase):
    def test_error_outside_assertion_records_type_and_line_not_message(self):
        src = make_test_source("""\
            mod.boom()  # L1
            self.assertEqual(1, 1)
            """)
        module = "def boom():\n    raise KeyError('secret-message')\n"
        sig = self.record(module, src)[TEST_ID]
        self.assertEqual(sig["outcome"], "error")
        self.assertEqual(sig["error"], [["KeyError", line_of(src, "# L1")]])
        self.assertNotIn("secret-message", self.sig.read_text())

    def test_error_line_is_the_innermost_base_file_frame(self):
        src = (
            HEADER
            + "    def helper(self):\n        mod.boom()  # L1\n\n"
            + "    def test_a(self):\n        self.helper()\n"
        )
        module = "def boom():\n    raise KeyError('x')\n"
        sig = self.record(module, src)[TEST_ID]
        self.assertEqual(sig["error"], [["KeyError", line_of(src, "# L1")]])

    def test_distinct_errors_in_different_subtests_are_all_recorded(self):
        src = make_test_source("""\
            for i in (1, 2, 1):
                with self.subTest(i=i):
                    mod.boom(i)  # L1
            """)
        module = (
            "def boom(i):\n    raise KeyError('x') if i == 1 else ValueError('y')\n"
        )
        sig = self.record(module, src)[TEST_ID]
        line = line_of(src, "# L1")
        self.assertEqual(sig["outcome"], "error")
        self.assertEqual(sig["error"], [["KeyError", line], ["ValueError", line]])

    def test_error_in_expected_failure_test_is_recorded(self):
        src = (
            HEADER
            + "    @unittest.expectedFailure\n    def test_a(self):\n"
            + "        mod.boom()  # L1\n"
        )
        module = "def boom():\n    raise KeyError('x')\n"
        sig = self.record(module, src)[TEST_ID]
        self.assertEqual(sig["outcome"], "expected-failure")
        self.assertEqual(sig["error"], [["KeyError", line_of(src, "# L1")]])


class CompareTests(RunnerCase):
    SRC = make_test_source("self.assertEqual(mod.f(1), 2)  # L1\n")
    TWO_SRC = make_test_source("""\
        self.assertEqual(mod.f(1), 2)  # L1
        self.assertEqual(mod.g(1), 2)  # L2
        """)

    def test_message_only_change_at_known_site_is_invisible(self):
        self.record("def f(x):\n    return 5\n", self.SRC)
        proc = self.compare("def f(x):\n    return 7\n", self.SRC)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stderr, "")

    def test_new_site_beside_known_failure_exits_one_naming_the_site(self):
        self.record(
            "def f(x):\n    return 5\n\ndef g(x):\n    return 2\n", self.TWO_SRC
        )
        proc = self.compare(
            "def f(x):\n    return 5\n\ndef g(x):\n    return 9\n", self.TWO_SRC
        )
        line = line_of(self.TWO_SRC, "# L2")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(
            proc.stderr.splitlines(),
            [
                f"{DIFF}{TEST_ID}: new failure site {[line, NO_PARAMS, 1, 'AssertionError']}"
            ],
        )

    def test_outcome_change_exits_one_with_outcome_and_site_lines(self):
        self.record("def f(x):\n    return 2\n", self.SRC)
        proc = self.compare("def f(x):\n    raise RuntimeError('x')\n", self.SRC)
        line = line_of(self.SRC, "# L1")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(
            proc.stderr.splitlines(),
            [
                f"{DIFF}{TEST_ID}: outcome pass -> fail",
                f"{DIFF}{TEST_ID}: new failure site {[line, NO_PARAMS, 1, 'RuntimeError']}",
            ],
        )

    def test_fixed_failure_exits_one(self):
        self.record("def f(x):\n    return 5\n", self.SRC)
        proc = self.compare("def f(x):\n    return 2\n", self.SRC)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(
            proc.stderr.splitlines(), [f"{DIFF}{TEST_ID}: outcome fail -> pass"]
        )

    def test_error_only_change_at_same_line_exits_one(self):
        src = make_test_source("mod.boom()  # L1\n")
        self.record("def boom():\n    raise KeyError('x')\n", src)
        proc = self.compare("def boom():\n    raise ValueError('x')\n", src)
        line = line_of(src, "# L1")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(
            proc.stderr.splitlines(),
            [
                f"{DIFF}{TEST_ID}: error {[['KeyError', line]]} -> {[['ValueError', line]]}"
            ],
        )

    def test_identical_run_exits_zero(self):
        module = "def f(x):\n    return 2\n"
        self.record(module, self.SRC)
        self.assertEqual(self.compare(module, self.SRC).returncode, 0)

    def test_stderr_never_carries_exception_messages(self):
        self.record("def f(x):\n    return 2\n", self.SRC)
        proc = self.compare(
            "def f(x):\n    raise RuntimeError('leaky-message')\n", self.SRC
        )
        line = line_of(self.SRC, "# L1")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(
            proc.stderr.splitlines(),
            [
                f"{DIFF}{TEST_ID}: outcome pass -> fail",
                f"{DIFF}{TEST_ID}: new failure site {[line, NO_PARAMS, 1, 'RuntimeError']}",
            ],
        )

    def test_import_error_under_compare_changes_the_test_set(self):
        self.record(PASSING_MODULE, self.SRC)
        proc = self.compare(PASSING_MODULE, "import no_such_module_xyz\n")
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(
            set(proc.stderr.splitlines()),
            {
                f"{DIFF}{TEST_ID}: test set changed",
                f"{DIFF}{FAILED_LOAD_ID}: test set changed",
            },
        )

    def test_set_up_class_error_under_compare_changes_the_test_set(self):
        self.record(PASSING_MODULE, self.SRC)
        broken = (
            HEADER
            + "    @classmethod\n    def setUpClass(cls):\n        raise RuntimeError('x')\n\n"
            + "    def test_a(self):\n        pass\n"
        )
        proc = self.compare(PASSING_MODULE, broken)
        self.assertEqual(proc.returncode, 1)
        self.assertIn(f"{DIFF}{TEST_ID}: test set changed", proc.stderr.splitlines())
        self.assertIn(
            f"{DIFF}setUpClass (test_mod_base.T): test set changed",
            proc.stderr.splitlines(),
        )


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
        sig = self.record("", "import no_such_module_xyz\n")
        self.assertEqual(list(sig), [FAILED_LOAD_ID])
        record = sig[FAILED_LOAD_ID]
        self.assertEqual(record["outcome"], "error")
        self.assertEqual(record["error"][0][0], "ModuleNotFoundError")

    def test_skip_test_inside_assert_block_still_skips(self):
        src = make_test_source("""\
            with self.assertRaises(ValueError):
                self.skipTest('r')
            """)
        sig = self.record("", src)[TEST_ID]
        self.assertEqual(sig["outcome"], "skip")

    def test_assertion_in_set_up_class_is_reraised_not_recorded(self):
        src = (
            HEADER
            + "    @classmethod\n    def setUpClass(cls):\n"
            + "        self = cls()\n        self.assertEqual(1, 2)  # L1\n\n"
            + "    def test_a(self):\n        pass\n"
        )
        sig = self.record("", src)
        holder = sig["setUpClass (test_mod_base.T)"]
        self.assertEqual(holder["outcome"], "error")
        self.assertEqual(holder["sites"], [])
        self.assertEqual(holder["error"], [["AssertionError", line_of(src, "# L1")]])


class RelativePathTests(RunnerCase):
    def test_file_dunder_is_absolute_when_the_path_is_relative(self):
        src = make_test_source(
            """\
            self.addCleanup(os.chdir, os.getcwd())
            os.chdir("/")
            self.assertTrue((pathlib.Path(__file__).parent / "mod.py").exists())
            """,
            header="import os\nimport pathlib\nimport unittest\n\n\nclass T(unittest.TestCase):\n",
        )
        sig = self.record(PASSING_MODULE, src)[TEST_ID]
        self.assertEqual(
            sig, {"outcome": "pass", "sites": [], "error": [], "setup_error": False}
        )

    def test_failure_lines_still_match_with_an_absolute_filename(self):
        src = make_test_source("self.assertEqual(1, 2)  # L1\n")
        self.write(PASSING_MODULE, src)
        proc = self.run_args(["record", str(self.sig), str(self.dir / TEST_FILE)])
        self.assertEqual(proc.returncode, 0, proc.stderr)
        sig = json.loads(self.sig.read_text())[TEST_ID]
        self.assertEqual([s[0] for s in sig["sites"]], [line_of(src, "# L1")])


class HypothesisTests(RunnerCase):
    GIVEN_SRC = (
        "import unittest\n\n"
        "from hypothesis import assume, given, settings, strategies as st\n\n\n"
        "class T(unittest.TestCase):\n"
        "    @settings(derandomize=True, database=None, deadline=None)\n"
        "    @given(st.integers(min_value=-5, max_value=5))\n"
        "    def test_a(self, n):\n"
        "        self.assertLess(n, 2)  # L1\n"
        "        with self.assertRaises(ValueError):\n"
        "            assume(n > 0)\n"
        "            raise ValueError\n"
    )

    def test_given_recording_is_deterministic_and_reraises_unsatisfied_assumption(self):
        first = self.record("", self.GIVEN_SRC)[TEST_ID]
        first_text = self.sig.read_text()
        self.record("", self.GIVEN_SRC)
        self.assertEqual(self.sig.read_text(), first_text)
        self.assertEqual(first["outcome"], "fail")
        self.assertEqual(
            {s[0] for s in first["sites"]}, {line_of(self.GIVEN_SRC, "# L1")}
        )
        self.assertEqual(first["error"], [])
        self.assertEqual(self.compare("", self.GIVEN_SRC).returncode, 0)


class SetupErrorTests(RunnerCase):
    """An exception escaping setUp (sync or async) marks the record `setup_error`."""

    def entry(self, source, test_id=TEST_ID):
        return self.record(PASSING_MODULE, source)[test_id]

    def test_setup_calling_a_same_file_helper_is_flagged(self):
        src = (
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def _helper(self):\n        raise KeyError('x')\n"
            "    def setUp(self):\n        self._helper()\n"
            "    def test_a(self):\n        pass\n"
        )
        sig = self.entry(src)
        self.assertTrue(sig["setup_error"])
        self.assertEqual(sig["outcome"], "error")

    def test_setup_reading_a_missing_module_attribute_is_flagged(self):
        src = (
            "import unittest\n\nimport mod\n\n\ndef _prepare():\n    return mod.renamed_away\n\n\n"
            "class T(unittest.TestCase):\n    def setUp(self):\n        _prepare()\n"
            "    def test_a(self):\n        pass\n"
        )
        self.assertTrue(self.entry(src)["setup_error"])

    def test_async_setup_is_flagged(self):
        src = (
            "import unittest\n\n\nclass T(unittest.IsolatedAsyncioTestCase):\n"
            "    async def asyncSetUp(self):\n        raise KeyError('x')\n"
            "    async def test_a(self):\n        pass\n"
        )
        self.assertTrue(self.entry(src)["setup_error"])

    def test_setup_assigned_in_the_class_body_is_flagged(self):
        src = (
            "import unittest\n\n\ndef _s(self):\n    raise KeyError('x')\n\n\n"
            "class T(unittest.TestCase):\n    setUp = _s\n"
            "    def test_a(self):\n        pass\n"
        )
        self.assertTrue(self.entry(src)["setup_error"])

    def test_failing_assert_inside_setup_is_continued_not_a_setup_error(self):
        src = (
            "import unittest\n\nimport mod\n\n\nclass T(unittest.TestCase):\n"
            "    def setUp(self):\n        self.assertEqual(mod.f(1), 2)\n"
            "    def test_a(self):\n        pass\n"
        )
        sig = self.entry(src)
        self.assertFalse(sig["setup_error"])
        self.assertEqual(sig["outcome"], "fail")

    def test_skip_in_setup_is_not_a_setup_error(self):
        src = (
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def setUp(self):\n        self.skipTest('no')\n"
            "    def test_a(self):\n        pass\n"
        )
        sig = self.entry(src)
        self.assertFalse(sig["setup_error"])
        self.assertEqual(sig["outcome"], "skip")

    def test_error_in_the_test_body_is_not_a_setup_error(self):
        src = make_test_source("raise KeyError('x')\n")
        self.assertFalse(self.entry(src)["setup_error"])

    def test_later_tests_are_not_flagged_by_an_earlier_setup_error(self):
        src = (
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def setUp(self):\n        if self._testMethodName == 'test_a':\n"
            "            raise KeyError('x')\n"
            "    def test_a(self):\n        pass\n"
            "    def test_b(self):\n        pass\n"
        )
        sigs = self.record(PASSING_MODULE, src)
        self.assertTrue(sigs["test_mod_base.T.test_a"]["setup_error"])
        self.assertFalse(sigs["test_mod_base.T.test_b"]["setup_error"])

    def test_patched_hooks_are_restored_after_the_run(self):
        probe = (
            "import importlib.util, sys, unittest\n"
            f"spec = importlib.util.spec_from_file_location('r', {str(RUNNER)!r})\n"
            "r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)\n"
            "names = [(c, c.__dict__['_callSetUp']) for c in (unittest.TestCase, unittest.IsolatedAsyncioTestCase)]\n"
            f"r.run_tests({str(self.dir / TEST_FILE)!r})\n"
            "assert all(c.__dict__['_callSetUp'] is f for c, f in names)\n"
        )
        self.write(PASSING_MODULE, make_test_source("pass\n"))
        proc = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=self.dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=RUN_TIMEOUT_S,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_missing_setup_hook_fails_closed_with_exit_three(self):
        self.write(PASSING_MODULE, make_test_source("pass\n"))
        probe = (
            "import importlib.util, sys, unittest\n"
            f"spec = importlib.util.spec_from_file_location('r', {str(RUNNER)!r})\n"
            "r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)\n"
            "del unittest.IsolatedAsyncioTestCase._callSetUp\n"
            f"sys.exit(r.main(['r', 'record', {str(self.sig)!r}, {TEST_FILE!r}]))\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=self.dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=RUN_TIMEOUT_S,
        )
        self.assertEqual(proc.returncode, 3, proc.stderr)

    def test_signature_without_setup_error_is_an_internal_error(self):
        self.write(PASSING_MODULE, make_test_source("pass\n"))
        entry = {"outcome": "pass", "sites": [], "error": []}
        self.sig.write_text(json.dumps({TEST_ID: entry}))
        self.assertEqual(self.run_runner("compare").returncode, 3)

    def test_non_boolean_setup_error_is_an_internal_error(self):
        self.write(PASSING_MODULE, make_test_source("pass\n"))
        entry = {"outcome": "pass", "sites": [], "error": [], "setup_error": 0}
        self.sig.write_text(json.dumps({TEST_ID: entry}))
        self.assertEqual(self.run_runner("compare").returncode, 3)


class CliTests(RunnerCase):
    def test_unknown_mode_exits_two(self):
        self.write("", make_test_source("pass\n"))
        self.assertEqual(self.run_runner("bogus").returncode, 2)

    def test_wrong_argument_count_exits_two(self):
        self.write("", make_test_source("pass\n"))
        for args in (
            [],
            ["record"],
            ["record", str(self.sig)],
            ["record", "a", "b", "c"],
        ):
            with self.subTest(args=args):
                self.assertEqual(self.run_args(args).returncode, 2)

    def test_missing_signature_file_exits_three_with_one_line(self):
        self.write("", make_test_source("pass\n"))
        proc = self.run_runner("compare")
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(len(proc.stderr.splitlines()), 1)

    def test_corrupt_signature_file_exits_three_with_one_line(self):
        self.write("", make_test_source("pass\n"))
        for text in (
            "{not json",
            '{"a": 1}',
            '{"a": {"outcome": "bogus", "sites": [], "error": []}}',
            "[]",
        ):
            with self.subTest(text=text):
                self.sig.write_text(text)
                proc = self.run_runner("compare")
                self.assertEqual(proc.returncode, 3)
                self.assertEqual(len(proc.stderr.splitlines()), 1)

    def test_invalid_signature_is_rejected_before_any_test_code_runs(self):
        marker = self.dir / "marker.txt"
        src = "open('marker.txt', 'w').write('ran')\n" + make_test_source("pass\n")
        self.write("", src)
        self.sig.write_text("{not json")
        proc = self.run_runner("compare")
        self.assertEqual(proc.returncode, 3)
        self.assertFalse(marker.exists())

    def test_malformed_error_field_exits_three(self):
        self.write("", make_test_source("pass\n"))
        for error in (
            "x",
            [["KeyError"]],
            [["KeyError", "x"]],
            [[1, 2]],
            [["KeyError", True]],
            [["K", 1, 2]],
            ["KeyError"],
        ):
            with self.subTest(error=error):
                entry = {
                    "outcome": "pass",
                    "sites": [],
                    "error": error,
                    "setup_error": False,
                }
                self.sig.write_text(json.dumps({TEST_ID: entry}))
                proc = self.run_runner("compare")
                self.assertEqual(proc.returncode, 3)
                self.assertEqual(len(proc.stderr.splitlines()), 1)

    def test_malformed_sites_entry_exits_three(self):
        self.write("", make_test_source("pass\n"))
        for site in (
            [1, "", 1],
            [1, "", 1, "T", 5],
            ["1", "", 1, "T"],
            [1, 2, 1, "T"],
            [1, "", "1", "T"],
            [1, "", 1, 2],
            [True, "", 1, "T"],
            "site",
        ):
            with self.subTest(site=site):
                entry = {
                    "outcome": "fail",
                    "sites": [site],
                    "error": [],
                    "setup_error": False,
                }
                self.sig.write_text(json.dumps({TEST_ID: entry}))
                proc = self.run_runner("compare")
                self.assertEqual(proc.returncode, 3)

    def test_well_formed_signature_is_accepted(self):
        self.write("", make_test_source("pass\n"))
        entry = {"outcome": "pass", "sites": [], "error": [], "setup_error": False}
        self.sig.write_text(json.dumps({TEST_ID: entry}))
        self.assertEqual(self.run_runner("compare").returncode, 0)

    def test_internal_error_line_names_the_type_only(self):
        self.write("", make_test_source("pass\n"))
        self.sig.write_text("{not json")
        proc = self.run_runner("compare")
        self.assertEqual(proc.stderr, INTERNAL + "JSONDecodeError\n")

    def test_missing_test_file_exits_three_not_a_load_error(self):
        self.write("", make_test_source("pass\n"))
        self.record("", make_test_source("pass\n"))
        (self.dir / TEST_FILE).unlink()
        proc = self.run_runner("compare")
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(proc.stderr, INTERNAL + "FileNotFoundError\n")

    def test_existing_unimportable_test_file_is_still_a_load_error(self):
        self.write("", "import no_such_module_xyz\n")
        self.sig.write_text(json.dumps({}))
        proc = self.run_runner("compare")
        self.assertEqual(proc.returncode, 1)

    def test_suite_output_is_not_a_diff_line(self):
        src = make_test_source(
            "print('suite-noise')\nimport sys\nprint('err-noise', file=sys.stderr)\n"
        )
        self.record("", src)
        proc = self.compare("", src)
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn(DIFF, proc.stderr)

    def test_unwritable_signature_path_exits_three_in_record_mode(self):
        self.write("", make_test_source("pass\n"))
        self.sig.mkdir()
        proc = self.run_runner("record")
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(len(proc.stderr.splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
