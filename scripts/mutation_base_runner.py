#!/usr/bin/env python3
"""Assertion-continuing unittest runner for the per-PR test-weakening check (R11).

Usage (run with the module directory as the working directory):

    mutation_base_runner.py record  <sig.json> <test_file.py>
    mutation_base_runner.py compare <sig.json> <test_file.py>

A plain unittest run stops a test at its first failing assertion, so a mutant that
breaks a later assertion looks identical to the unmutated module. This runner rewrites
every assertion statement so a failure is recorded and execution continues, then
reduces each test to a signature that contains no exception messages:

    {test_id: {"outcome": ..., "sites": [[line, params, nth, exc_type], ...],
               "error": [[exc_type, line], ...], "setup_error": bool}}

- `outcome` is one of pass, fail, error, skip, expected-failure, unexpected-success.
- `sites` is the sorted set of failure sites; `nth` is the n-th execution of that line
  in the test (0 for a failure not raised inside a rewritten statement).
- `error` is the sorted list of distinct (type, innermost base-file line) pairs for
  errors raised outside assertion statements; empty when there were none.
- `setup_error` is true when an exception other than SkipTest escaped `setUp` or
  `asyncSetUp` (a failing `self.assert*` in setUp is continued, so it does not count).

The test file is loaded under its absolute path, so `__file__` is usable and every line
number refers to the base test file.

Known limit: `cm = self.assertRaises(X)` followed by `with cm:` is not recognised as an
exception-expecting block, so assertions in its body are rewritten and a failure there is
recorded as a site (only the inline `with self.assert*(...)` form is understood).

The usage error (exit 2) prints a `usage:` line. Every other stderr line of the runner starts
with `mutation_base_runner: diff: ` (a change) or `mutation_base_runner: internal error:
<ExceptionType>` (exit 3); the suite's own output carries neither prefix.

Exit codes: 0 = record written, or compare found no change; 1 = compare found a test
whose outcome or error differs (except a test whose new outcome is skip, or whose
recorded outcome is error: those never count), a test that appeared or disappeared, or a failure site
absent from the recording (a site that already failed in the recording never counts,
whatever its message); 2 = usage error; 3 = internal error (unreadable or invalid
signature file, unwritable output, runner crash), with one line on stderr.
"""

from __future__ import annotations

import ast
import contextlib
import json
import os
import re
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
EXIT_CHANGED = 1
EXIT_USAGE = 2
EXIT_INTERNAL = 3
DIFF_PREFIX = "mutation_base_runner: diff: "
INTERNAL_PREFIX = "mutation_base_runner: internal error: "
NO_MESSAGE = object()
RUNTIME_NAME = "_mbr_rt"
# An author handler naming one of these also catches the failure of an assertion.
BROAD_EXCEPTIONS = frozenset(
    {"AssertionError", "Exception", "BaseException", "failureException"}
)
# Context managers whose body is expected to raise: their body is left unrewritten.
EXPECTING_PREFIXES = ("assertRaises", "assertWarns")
SITE_SHAPE = (int, str, int, str)
ERROR_SHAPE = (str, int)
ADDRESS = re.compile(r" at 0x[0-9a-fA-F]+")


class SignatureError(ValueError):
    """The signature file is missing its shape."""


class PlaceholderError(Exception):
    """Stands in for the exception a failed `assertRaises` block never captured."""


class PlaceholderWarning(Warning):
    """Stands in for the warning a failed `assertWarns` block never captured."""


def self_assert_name(node: ast.AST) -> str | None:
    """Name `X` of a call `self.X(...)` with X starting `assert`, else None."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
        and node.func.attr.startswith("assert")
    ):
        return node.func.attr
    return None


def is_broad_exception(node: ast.expr | None) -> bool:
    """True for a handler type that catches AssertionError (a bare handler is None)."""
    if node is None:
        return True
    if isinstance(node, ast.Tuple):
        return any(is_broad_exception(element) for element in node.elts)
    name = node.id if isinstance(node, ast.Name) else getattr(node, "attr", "")
    return name in BROAD_EXCEPTIONS


def catches_assertions(node: ast.Try | ast.TryStar) -> bool:
    return any(is_broad_exception(handler.type) for handler in node.handlers)


def expects_exception(node: ast.With) -> bool:
    names = (self_assert_name(item.context_expr) or "" for item in node.items)
    return any(name.startswith(EXPECTING_PREFIXES) for name in names)


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
        if self_assert_name(item.context_expr)
        and isinstance(item.optional_vars, ast.Name)
    ]


class AssertionRewriter(ast.NodeTransformer):
    """Rewrite assertion statements into record-and-continue blocks.

    A statement whose failure the test author handles or expects stays unrewritten:
    inside the body of a `try` with a handler that catches AssertionError, and inside
    a `with self.assertRaises*` / `assertWarns*` block.
    """

    def __init__(self) -> None:
        self.protected = 0

    def visit_block(self, statements: list[ast.stmt], protect: bool) -> list[ast.stmt]:
        """Visit `statements`, flattening the lists a rewritten statement returns."""
        self.protected += protect
        try:
            result: list[ast.stmt] = []
            for statement in statements:
                visited = self.visit(statement)
                result.extend(visited if isinstance(visited, list) else [visited])
            return result
        finally:
            self.protected -= protect

    def visit_Expr(self, node: ast.Expr) -> ast.stmt | list[ast.stmt]:
        self.generic_visit(node)
        if self.protected or not self_assert_name(node.value):
            return node
        return guard(node, [])

    def visit_Assert(self, node: ast.Assert) -> ast.stmt | list[ast.stmt]:
        self.generic_visit(node)
        return node if self.protected else guard(node, [])

    def visit_With(self, node: ast.With) -> ast.stmt | list[ast.stmt]:
        body, node.body = node.body, []
        self.generic_visit(node)
        node.body = self.visit_block(body, expects_exception(node))
        if self.protected or not any(
            self_assert_name(i.context_expr) for i in node.items
        ):
            return node
        return guard(node, assert_with_names(node))

    def visit_Try(self, node: ast.Try | ast.TryStar) -> ast.stmt:
        body, node.body = node.body, []
        self.generic_visit(node)
        node.body = self.visit_block(body, catches_assertions(node))
        return node

    def visit_TryStar(self, node: ast.TryStar) -> ast.stmt:
        return self.visit_Try(node)

    def visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.stmt:
        """A nested function is judged on its own, outside any enclosing protection."""
        saved, self.protected = self.protected, 0
        self.generic_visit(node)
        self.protected = saved
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.stmt:
        return self.visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.stmt:
        return self.visit_function(node)


def canonical_repr(value: object) -> str:
    """`repr` that does not depend on hash order or object addresses."""
    if isinstance(value, (set, frozenset)):
        body = ", ".join(sorted(canonical_repr(element) for element in value))
        if not value:
            return "set()" if isinstance(value, set) else "frozenset()"
        return f"{{{body}}}" if isinstance(value, set) else f"frozenset({{{body}}})"
    if isinstance(value, dict):
        items = (f"{canonical_repr(k)}: {canonical_repr(v)}" for k, v in value.items())
        return "{" + ", ".join(items) + "}"
    if isinstance(value, (list, tuple)):
        inner = ", ".join(canonical_repr(element) for element in value)
        if isinstance(value, list):
            return f"[{inner}]"
        return f"({inner},)" if len(value) == 1 else f"({inner})"
    return ADDRESS.sub(" at 0x?", repr(value))


def params_key(frames: list[dict[str, object]]) -> str:
    """Canonical text of the subTest parameters active in `frames`."""
    merged: dict[str, object] = {}
    for frame in frames:
        merged.update(frame)
    return repr(sorted((name, canonical_repr(value)) for name, value in merged.items()))


def type_name(exc: BaseException) -> str:
    return type(exc).__qualname__


def reraised_types() -> tuple[type[BaseException], ...]:
    """Exceptions that control the test run and must never be recorded as a site."""
    try:
        from hypothesis.errors import UnsatisfiedAssumption
    except ImportError:
        return (unittest.SkipTest,)
    return (unittest.SkipTest, UnsatisfiedAssumption)


@dataclass
class TestRecord:
    """Mutable per-test accumulator behind one signature entry."""

    __test__ = False  # not a test class, despite the name

    outcome: str | None = None
    sites: set[Site] = field(default_factory=set)
    errors: set[tuple[str, int]] = field(default_factory=set)
    setup_error: bool = False

    def note(self, outcome: str) -> None:
        if self.outcome is None or OUTCOME_RANK[outcome] > OUTCOME_RANK[self.outcome]:
            self.outcome = outcome

    def finalize(self) -> dict[str, Any]:
        outcome = self.outcome or "pass"
        if self.sites:
            outcome = CONTINUED_FAILURE_OUTCOME.get(outcome, outcome)
        return {
            "outcome": outcome,
            "sites": sorted(list(s) for s in self.sites),
            "error": sorted(list(e) for e in self.errors),
            "setup_error": self.setup_error,
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
        if isinstance(exc, reraised_types()) or self._current is None:
            raise exc
        site = (line, params_key(self._params), self._counts[line], type_name(exc))
        self._current.sites.add(site)

    @staticmethod
    def placeholder() -> types.SimpleNamespace:
        """Stand-in for the watcher a failed `with self.assert* as name` never bound."""
        return types.SimpleNamespace(
            exception=PlaceholderError("placeholder"),
            output=[],
            records=[],
            warning=PlaceholderWarning("placeholder"),
            warnings=[],
            filename="",
            lineno=0,
        )

    def mark_setup_error(self) -> None:
        """An exception escaped setUp (sync or async) for the running test."""
        if self._current is not None:
            self._current.setup_error = True

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
        record = self._record(test)
        record.note("expected-failure")
        if issubclass(err[0], test.failureException):
            self.add_site(record, err, "")
        else:
            self.add_error(record, err)

    def addUnexpectedSuccess(self, test: unittest.case.TestCase) -> None:
        self._record(test).note("unexpected-success")

    def addFailure(self, test: unittest.case.TestCase, err: Any) -> None:
        record = self._record(test)
        record.note("fail")
        self.add_site(record, err, "")

    def addError(self, test: unittest.case.TestCase, err: Any) -> None:
        record = self._record(test)
        record.note("error")
        self.add_error(record, err)

    def addSubTest(self, test: Any, subtest: Any, err: Any) -> None:
        if err is None:
            return
        record = self._record(test)
        if issubclass(err[0], test.failureException):
            record.note("fail")
            self.add_site(record, err, params_key([dict(subtest.params)]))
        else:
            record.note("error")
            self.add_error(record, err)

    def add_site(self, record: TestRecord, err: Any, params: str) -> None:
        record.sites.add((self.innermost_line(err[2]), params, 0, type_name(err[1])))

    def add_error(self, record: TestRecord, err: Any) -> None:
        record.errors.add((type_name(err[1]), self.innermost_line(err[2])))

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
        record.note("error")
        self.add_error(record, (type(exc), exc, exc.__traceback__))


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


SETUP_HOOK_OWNERS = (unittest.TestCase, unittest.IsolatedAsyncioTestCase)


@contextlib.contextmanager
def tracked_setup(recorder: Recorder) -> Iterator[None]:
    """Wrap each class's own `_callSetUp` so an exception escaping setUp is recorded.

    `IsolatedAsyncioTestCase` overrides `_callSetUp` to run `asyncSetUp`, so both owners
    are wrapped. A missing hook raises KeyError (exit 3): fail closed.
    """
    originals = {cls: cls.__dict__["_callSetUp"] for cls in SETUP_HOOK_OWNERS}

    def wrap(original: Any) -> Any:
        def call_set_up(self: unittest.TestCase) -> Any:
            try:
                return original(self)
            except unittest.SkipTest:
                raise
            except Exception:
                recorder.mark_setup_error()
                raise

        return call_set_up

    for cls, original in originals.items():
        setattr(cls, "_callSetUp", wrap(original))  # noqa: B010 - pyright rejects assigning a method
    try:
        yield
    finally:
        for cls, original in originals.items():
            setattr(cls, "_callSetUp", original)  # noqa: B010 - restores the patch above


def load_suite(path: str, recorder: Recorder) -> unittest.TestSuite:
    """Rewrite and load the test file at absolute `path`; a load failure is recorded."""
    stem = Path(path).stem
    module = types.ModuleType(stem)
    module.__file__ = path
    setattr(module, RUNTIME_NAME, recorder)
    sys.modules[stem] = module
    source = Path(path).read_text()  # unreadable file: internal error, not a load error
    try:
        tree = AssertionRewriter().visit(ast.parse(source, path))
        code = compile(ast.fix_missing_locations(tree), path, "exec")
        exec(code, module.__dict__)  # noqa: S102 - running the base test file is the purpose
    except Exception as exc:  # noqa: BLE001 - the load failure is the recorded signature
        recorder.record_load_error(stem, exc)
        return unittest.TestSuite()
    return unittest.defaultTestLoader.loadTestsFromModule(module)


def run_tests(path: str) -> Signature:
    """Run every test in `path` and return its signature."""
    path = os.path.abspath(path)
    recorder = Recorder(path)
    suite = load_suite(path, recorder)
    with tracked_subtests(recorder), tracked_setup(recorder):
        suite.run(recorder)
    return {
        test_id: record.finalize()
        for test_id, record in sorted(recorder.records.items())
    }


def has_shape(item: object, shape: tuple[type, ...]) -> bool:
    """True when `item` is a list of exactly the types in `shape` (bool is not int)."""
    return (
        isinstance(item, list)
        and len(item) == len(shape)
        and all(type(value) is kind for value, kind in zip(item, shape, strict=True))
    )


def validate_entry(test_id: str, entry: object) -> None:
    ok = (
        isinstance(entry, dict)
        and entry.get("outcome") in OUTCOME_RANK
        and isinstance(entry.get("sites"), list)
        and all(has_shape(site, SITE_SHAPE) for site in entry["sites"])
        and isinstance(entry.get("error"), list)
        and all(has_shape(error, ERROR_SHAPE) for error in entry["error"])
        and type(entry.get("setup_error")) is bool
    )
    if not ok:
        raise SignatureError(f"invalid signature entry for {test_id!r}")


def load_signature(path: str) -> Signature:
    """Read and validate a recorded signature file."""
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict):
        raise SignatureError("signature file is not a JSON object")
    for test_id, entry in data.items():
        validate_entry(test_id, entry)
    return data


def diff_test(test_id: str, old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Differences that make a test count as changed; never mentions a message.

    A test that now skips, or whose recorded outcome is `error`, never counts: a skip
    is not evidence of weaker tests, and an errored base test is obsolete, so what a
    mutant changes in it is noise.
    """
    if new["outcome"] == "skip" or old["outcome"] == "error":
        return []
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


def execute(mode: str, sig_path: str, test_path: str) -> int:
    """Run `mode`; raises OSError, ValueError or SignatureError on internal errors."""
    recorded = load_signature(sig_path) if mode == "compare" else None
    sys.path.insert(0, os.getcwd())
    current = run_tests(test_path)
    if recorded is None:
        Path(sig_path).write_text(json.dumps(current, indent=1, sort_keys=True) + "\n")
        return 0
    diffs = compare_signatures(recorded, current)
    for diff in diffs:
        print(DIFF_PREFIX + diff, file=sys.stderr)
    return EXIT_CHANGED if diffs else 0


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in MODES:
        print(
            f"usage: {argv[0]} record|compare <sig.json> <test_file.py>",
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        return execute(*argv[1:])
    except Exception as exc:  # noqa: BLE001 - any internal error must exit 3, never 1
        print(f"{INTERNAL_PREFIX}{type_name(exc)}", file=sys.stderr)
        return EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main(sys.argv))
