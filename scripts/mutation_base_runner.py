#!/usr/bin/env python3
"""Assertion-continuing unittest runner for the per-PR test-weakening check (R11).

Usage (run with the module directory as the working directory):

    mutation_base_runner.py record  <sig.json> <test_file.py>
    mutation_base_runner.py compare <sig.json> <test_file.py>

A plain unittest run stops a test at its first failing assertion, so a mutant that
breaks a later assertion looks identical to the unmutated module. This runner rewrites
every assertion statement so a failure is recorded and execution continues, then
reduces each test to a signature that contains no exception messages:

    {test_id: {"outcome": ..., "sites": [[line, params, nth, exc_type]], "error": [type, line] | null}}

`record` writes the signature of the unmutated module. `compare` exits 1 when a test's
outcome or error differs from the recording, or a failure site absent from the
recording appears; a site that already failed in the recording never counts, whatever
its message. The rewritten tree is compiled under the original filename, so every line
number refers to the base test file.
"""

from __future__ import annotations

import ast
import contextlib
import json
import os
import sys
import textwrap
import traceback
import types
import unittest
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

Signature = dict[str, dict[str, Any]]
Site = tuple[int, str, int, str]

# A test with several parts reports its worst outcome.
OUTCOME_RANK = {
    "pass": 0,
    "skip": 1,
    "expected-failure": 2,
    "unexpected-success": 3,
    "fail": 4,
    "error": 5,
}
# Outcome unittest reports for a test whose failing assertions were all continued.
CONTINUED_FAILURE_OUTCOME = {"pass": "fail", "unexpected-success": "expected-failure"}
MODES = ("record", "compare")
NO_MESSAGE = object()
RUNTIME_NAME = "_mbr_rt"


def is_self_assert_call(node: ast.AST) -> bool:
    """True for a call of the form `self.assert...(...)`."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        and node.func.attr.startswith("assert")
    )


def guard(node: ast.stmt, bound_names: list[str]) -> list[ast.stmt]:
    """Wrap `node` so an Exception inside it is recorded and execution continues."""
    handler = [f"{RUNTIME_NAME}.fail({node.lineno}, _mbr_e)"]
    handler += [f"{name} = {RUNTIME_NAME}.placeholder()" for name in bound_names]
    source = (
        f"{RUNTIME_NAME}.enter({node.lineno})\n"
        "try:\n    pass\n"
        "except Exception as _mbr_e:\n" + textwrap.indent("\n".join(handler), "    ")
    )
    template = ast.parse(source).body
    for statement in template:
        for child in ast.walk(statement):
            ast.copy_location(child, node)
    try_node = template[1]
    assert isinstance(try_node, ast.Try)
    try_node.body = [node]
    return template


def assert_with_names(node: ast.With) -> list[str]:
    """Names bound by `with self.assert...(...) as name` items of `node`."""
    return [
        item.optional_vars.id
        for item in node.items
        if is_self_assert_call(item.context_expr)
        and isinstance(item.optional_vars, ast.Name)
    ]


class AssertionRewriter(ast.NodeTransformer):
    """Rewrite assertion statements into record-and-continue blocks."""

    def visit_Expr(self, node: ast.Expr) -> ast.stmt | list[ast.stmt]:
        self.generic_visit(node)
        return guard(node, []) if is_self_assert_call(node.value) else node

    def visit_Assert(self, node: ast.Assert) -> list[ast.stmt]:
        self.generic_visit(node)
        return guard(node, [])

    def visit_With(self, node: ast.With) -> ast.stmt | list[ast.stmt]:
        self.generic_visit(node)
        if any(is_self_assert_call(item.context_expr) for item in node.items):
            return guard(node, assert_with_names(node))
        return node


@dataclass
class TestRecord:
    """Mutable per-test accumulator behind one signature entry."""

    __test__ = False  # not a test class, despite the name

    outcome: str | None = None
    sites: set[Site] = field(default_factory=set)
    error: tuple[str, int] | None = None

    def note(self, outcome: str) -> None:
        if self.outcome is None or OUTCOME_RANK[outcome] > OUTCOME_RANK[self.outcome]:
            self.outcome = outcome

    def finalize(self) -> dict[str, Any]:
        outcome = self.outcome or "pass"
        if self.sites:
            outcome = CONTINUED_FAILURE_OUTCOME.get(outcome, outcome)
        error = list(self.error) if self.error else None
        return {
            "outcome": outcome,
            "sites": sorted(list(s) for s in self.sites),
            "error": error,
        }


class Recorder(unittest.TestResult):
    """TestResult that also serves as the runtime of the rewritten test module."""

    def __init__(self, filename: str) -> None:
        super().__init__()
        self.filename = filename
        self.records: dict[str, TestRecord] = {}
        self._current: TestRecord | None = None
        self._counts: dict[int, int] = {}
        self._params: list[dict[str, object]] = []

    # --- runtime used by rewritten code -------------------------------------------
    def enter(self, line: int) -> None:
        self._counts[line] = self._counts.get(line, 0) + 1

    def fail(self, line: int, exc: Exception) -> None:
        if isinstance(exc, unittest.SkipTest) or self._current is None:
            raise exc
        nth = self._counts[line]
        self._current.sites.add(
            (line, self.params_key(self._params), nth, type_name(exc))
        )

    @staticmethod
    def placeholder() -> types.SimpleNamespace:
        return types.SimpleNamespace(exception=PlaceholderError("placeholder"))

    @staticmethod
    def params_key(frames: list[dict[str, object]]) -> str:
        merged: dict[str, object] = {}
        for frame in frames:
            merged.update(frame)
        return repr(sorted((k, repr(v)) for k, v in merged.items()))

    def push_params(self, params: dict[str, object]) -> None:
        self._params.append(params)

    def pop_params(self) -> None:
        self._params.pop()

    # --- unittest result protocol -------------------------------------------------
    def _record(self, test: unittest.case.TestCase) -> TestRecord:
        return self.records.setdefault(test.id(), TestRecord())

    def startTest(self, test: unittest.case.TestCase) -> None:
        super().startTest(test)
        self._current = self._record(test)
        self._counts = {}
        self._params = []

    def stopTest(self, test: unittest.case.TestCase) -> None:
        super().stopTest(test)
        self._current = None

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        self._record(test).note("pass")

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        self._record(test).note("skip")

    def addExpectedFailure(self, test: unittest.case.TestCase, err: Any) -> None:
        self._record(test).note("expected-failure")

    def addUnexpectedSuccess(self, test: unittest.case.TestCase) -> None:
        self._record(test).note("unexpected-success")

    def addFailure(self, test: unittest.case.TestCase, err: Any) -> None:
        self.note_failure(self._record(test), err, "")

    def addError(self, test: unittest.case.TestCase, err: Any) -> None:
        self.note_error(self._record(test), err)

    def addSubTest(self, test: Any, subtest: Any, err: Any) -> None:
        if err is None:
            return
        record = self._record(test)
        if issubclass(err[0], test.failureException):
            self.note_failure(record, err, self.params_key([dict(subtest.params)]))
        else:
            self.note_error(record, err)

    def note_failure(self, record: TestRecord, err: Any, params: str) -> None:
        record.note("fail")
        record.sites.add((self.innermost_line(err[2]), params, 0, type_name(err[1])))

    def note_error(self, record: TestRecord, err: Any) -> None:
        record.note("error")
        if record.error is None:
            record.error = (type_name(err[1]), self.innermost_line(err[2]))

    def innermost_line(self, tb: types.TracebackType | None) -> int:
        """Line of the deepest traceback frame inside the base test file, else 0."""
        line = 0
        for frame, lineno in traceback.walk_tb(tb):
            if frame.f_code.co_filename == self.filename:
                line = lineno
        return line

    def record_load_error(self, stem: str, exc: Exception) -> None:
        """Record a failure to load the test file as unittest's `_FailedTest` would."""
        record = self.records.setdefault(
            f"unittest.loader._FailedTest.{stem}", TestRecord()
        )
        self.note_error(record, (type(exc), exc, exc.__traceback__))


class PlaceholderError(Exception):
    """Stands in for the exception a failed `assertRaises` block never captured."""


def type_name(exc: BaseException) -> str:
    return type(exc).__qualname__


@contextlib.contextmanager
def tracked_subtests(recorder: Recorder) -> Iterator[None]:
    """Patch TestCase.subTest so the recorder knows the active parameters."""
    original = unittest.TestCase.subTest

    @contextlib.contextmanager
    def sub_test(
        self: unittest.TestCase, msg: object = NO_MESSAGE, **params: object
    ) -> Iterator[None]:
        recorder.push_params(params)
        try:
            args = () if msg is NO_MESSAGE else (msg,)
            with original(self, *args, **params):
                yield
        finally:
            recorder.pop_params()

    setattr(unittest.TestCase, "subTest", sub_test)  # noqa: B010 - pyright rejects assigning a method
    try:
        yield
    finally:
        setattr(unittest.TestCase, "subTest", original)  # noqa: B010 - restores the patch above


def load_suite(path: str, recorder: Recorder) -> unittest.TestSuite:
    """Rewrite and load the test file; a load failure is recorded, not raised."""
    stem = Path(path).stem
    module = types.ModuleType(stem)
    module.__file__ = path
    setattr(module, RUNTIME_NAME, recorder)
    sys.modules[stem] = module
    try:
        tree = AssertionRewriter().visit(ast.parse(Path(path).read_text(), path))
        code = compile(ast.fix_missing_locations(tree), path, "exec")
        exec(code, module.__dict__)  # noqa: S102 - running the base test file is the purpose
    except Exception as exc:  # noqa: BLE001 - the load failure is the recorded signature
        recorder.record_load_error(stem, exc)
        return unittest.TestSuite()
    return unittest.defaultTestLoader.loadTestsFromModule(module)


def run_tests(path: str) -> Signature:
    """Run every test in `path` and return its signature."""
    recorder = Recorder(path)
    suite = load_suite(path, recorder)
    with tracked_subtests(recorder):
        suite.run(recorder)
    return {
        test_id: record.finalize()
        for test_id, record in sorted(recorder.records.items())
    }


def diff_test(test_id: str, old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Differences that make a test count as changed; never mentions a message."""
    diffs = []
    if old["outcome"] != new["outcome"]:
        diffs.append(f"{test_id}: outcome {old['outcome']} -> {new['outcome']}")
    if old["error"] != new["error"]:
        diffs.append(f"{test_id}: error {old['error']} -> {new['error']}")
    new_sites = {tuple(s) for s in new["sites"]} - {tuple(s) for s in old["sites"]}
    diffs += [f"{test_id}: new failure site {list(site)}" for site in sorted(new_sites)]
    return diffs


def compare_signatures(recorded: Signature, current: Signature) -> list[str]:
    diffs = []
    for test_id in sorted(set(recorded) | set(current)):
        if test_id not in recorded or test_id not in current:
            diffs.append(f"{test_id}: test set changed")
        else:
            diffs += diff_test(test_id, recorded[test_id], current[test_id])
    return diffs


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in MODES:
        print(
            f"usage: {argv[0]} record|compare <sig.json> <test_file.py>",
            file=sys.stderr,
        )
        return 2
    mode, sig_path, test_path = argv[1:]
    sys.path.insert(0, os.getcwd())
    current = run_tests(test_path)
    if mode == "record":
        Path(sig_path).write_text(json.dumps(current, indent=1, sort_keys=True) + "\n")
        return 0
    diffs = compare_signatures(json.loads(Path(sig_path).read_text()), current)
    for diff in diffs:
        print(diff, file=sys.stderr)
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
