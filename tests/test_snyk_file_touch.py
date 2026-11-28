"""R5-R9: the snyk-scan file-touch judge (touch, coverage, presence, suppression)."""

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "snyk_file_touch.py"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sft: Any = _load("snyk_file_touch", SCRIPT)

DIFF_ARGV = [
    "git", "-c", "core.quotePath=false", "diff", "--name-only", "-z",
    "--no-renames", "HEAD^1", "HEAD",
]  # fmt: skip
LS_ARGV = ["git", "ls-files", "-z"]


def result(uri: Any = "a.py", line: int | None = 3, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "ruleId": "py/Sqli",
        "level": "error",
        "message": {"text": "bad"},
    }
    if uri is not None:
        region = {"startLine": line} if line is not None else {}
        out["locations"] = [
            {"physicalLocation": {"artifactLocation": {"uri": uri}, "region": region}}
        ]
    out.update(extra)
    return out


def flow(*uris: str) -> list[dict[str, Any]]:
    steps = [
        {"location": {"physicalLocation": {"artifactLocation": {"uri": u}}}}
        for u in uris
    ]
    return [{"threadFlows": [{"locations": steps}]}]


def run(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {"results": results, "properties": {"coverage": []}}


def sarif(*results: dict[str, Any]) -> dict[str, Any]:
    return {"runs": [run(list(results))]}


EXTS = [".py", ".html", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue"]


def phrase(sep: str) -> str:
    """Suppression text built by a call, so neither source nor .pyc holds it."""
    prefix = "deep"
    return f"{prefix}code{sep}ignore"


SUPPRESSION = phrase(" ")


def header(touched: int, untouched: int, **cov: str) -> str:
    """The expected header; each compared extension reads `0/0` unless overridden."""
    parts = [f"coverage {e} {cov.get(e[1:], '0/0')}" for e in EXTS]
    return f"snyk: {touched} touched, {untouched} untouched; " + ", ".join(parts)


def coverage(lang: str, files: Any, kind: str = "SUPPORTED") -> dict[str, Any]:
    return {"lang": lang, "files": files, "type": kind}


def _expected_counts(doc: Any, tracked: list[str]) -> dict[str, int]:
    """Default manifest for tests that do not care about presence.

    This only aligns the manifest with the results so unrelated assertions stay
    quiet; it is not an oracle for the judge's presence logic.
    """
    counts: dict[str, int] = {}
    try:
        for each_run in doc["runs"]:
            for res in each_run["results"]:
                uri = unquote(
                    res["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
                )
                if uri in tracked and not any(c.isspace() for c in uri):
                    counts[uri] = counts.get(uri, 0) + 1
    except (KeyError, IndexError, TypeError):
        return {}
    return counts


class Fs(NamedTuple):
    """The two filesystem callbacks of a Checkout, passed by keyword."""

    size_of: Callable[[str], int | None]
    read_text: Callable[[str], str]


EMPTY_FS = Fs(size_of=lambda _p: 0, read_text=lambda _p: "")


def judge(
    doc: object,
    changed: set[str] | None = None,
    tracked: list[str] | None = None,
    manifest: Mapping[str, int] | None = None,
    fs: Fs = EMPTY_FS,
) -> tuple[list[str], int]:
    """Judge with every tracked file empty and a manifest that matches the results."""
    files = tracked if tracked is not None else ["a.py", "b.py", "c d.py"]
    checkout = sft.Checkout(
        changed=frozenset(changed or set()),
        tracked=tuple(files),
        size_of=fs.size_of,
        read_text=fs.read_text,
    )
    if manifest is None:
        manifest = _expected_counts(doc, files)
    return sft.judge(doc, checkout, manifest)


class TouchDecision(unittest.TestCase):
    def test_no_touched_result_exits_0(self) -> None:
        lines, code = judge(sarif(result("a.py")), changed={"b.py"})
        self.assertEqual(code, 0)
        self.assertEqual(lines, [header(0, 1)])

    def test_no_results_exits_0(self) -> None:
        lines, code = judge(sarif())
        self.assertEqual((lines, code), ([header(0, 0)], 0))

    def test_touched_location(self) -> None:
        lines, code = judge(sarif(result("a.py", 7)), changed={"a.py"})
        self.assertEqual(code, 1)
        self.assertEqual(lines[0], header(1, 0))
        self.assertEqual(
            lines[1], "touched: error py/Sqli a.py:7 — bad [changed: a.py]"
        )
        self.assertEqual(
            lines[2],
            "::error::snyk-scan: 1 finding(s) in files this PR changes; "
            "0 coverage mismatch(es); 0 presence difference(s); 0 suppression(s)",
        )
        self.assertEqual(len(lines), 3)

    def test_flow_step_in_second_file_only(self) -> None:
        doc = sarif(result("a.py", codeFlows=flow("a.py", "b.py")))
        lines, code = judge(doc, changed={"b.py"})
        self.assertEqual(code, 1)
        self.assertTrue(lines[1].endswith("[changed: b.py]"))

    def test_flow_step_in_second_code_flow_only(self) -> None:
        doc = sarif(result("a.py", codeFlows=flow("a.py") + flow("b.py")))
        lines, code = judge(doc, changed={"b.py"})
        self.assertEqual(code, 1)
        self.assertTrue(lines[1].endswith("[changed: b.py]"))

    def test_flow_step_in_second_thread_flow_only(self) -> None:
        threads = flow("a.py")[0]["threadFlows"] + flow("b.py")[0]["threadFlows"]
        doc = sarif(result("a.py", codeFlows=[{"threadFlows": threads}]))
        lines, code = judge(doc, changed={"b.py"})
        self.assertEqual(code, 1)
        self.assertTrue(lines[1].endswith("[changed: b.py]"))

    def test_added_file_is_changed(self) -> None:
        lines, code = judge(sarif(result("b.py")), changed={"b.py"})
        self.assertEqual(code, 1)
        self.assertIn("b.py:3", lines[1])

    def test_deleted_file_is_changed_but_untracked(self) -> None:
        lines, code = judge(sarif(result("gone.py")), changed={"gone.py"})
        self.assertEqual(code, 1)
        self.assertEqual(
            lines[1],
            "touched: error py/Sqli gone.py:3 — bad [changed: gone.py]"
            " [untracked uri: gone.py]",
        )

    def test_rename_listed_under_both_paths(self) -> None:
        old = judge(
            sarif(result("old.py")), changed={"old.py", "new.py"}, tracked=["new.py"]
        )
        self.assertEqual(old[1], 1)
        self.assertTrue(old[0][1].endswith("[changed: old.py] [untracked uri: old.py]"))
        new = judge(
            sarif(result("new.py")), changed={"old.py", "new.py"}, tracked=["new.py"]
        )
        self.assertEqual(new[1], 1)
        self.assertTrue(new[0][1].endswith("[changed: new.py]"))

    def test_encoded_uri_is_decoded(self) -> None:
        lines, code = judge(sarif(result("c%20d.py")), changed={"c d.py"})
        self.assertEqual(code, 1)
        self.assertIn(" c d.py:3 ", lines[1])

    def test_untracked_uri_is_touched(self) -> None:
        lines, code = judge(sarif(result("ghost.py")), changed=set())
        self.assertEqual(code, 1)
        self.assertTrue(lines[1].endswith("[changed: none] [untracked uri: ghost.py]"))

    def test_untracked_flow_uri_is_listed(self) -> None:
        doc = sarif(result("a.py", codeFlows=flow("ghost.py")))
        lines, code = judge(doc)
        self.assertEqual(code, 1)
        self.assertTrue(lines[1].endswith("[changed: none] [untracked uri: ghost.py]"))

    def test_whitespace_path_is_touched(self) -> None:
        lines, code = judge(
            sarif(result("c%20d.py")), changed=set(), tracked=["c d.py"]
        )
        self.assertEqual(code, 1)
        self.assertTrue(lines[1].endswith("[changed: none]"))

    def test_whitespace_in_flow_path_is_not_a_trigger(self) -> None:
        doc = sarif(result("a.py", codeFlows=flow("c d.py")))
        self.assertEqual(judge(doc)[1], 0)

    def test_result_in_second_run(self) -> None:
        doc = {"runs": [run([result("a.py")]), run([result("b.py")])]}
        lines, code = judge(doc, changed={"b.py"})
        self.assertEqual(code, 1)
        self.assertEqual(lines[0], header(1, 1))

    def test_missing_fields_print_question_mark_and_fail_closed(self) -> None:
        lines, code = judge(sarif({}))
        self.assertEqual(code, 1)
        self.assertEqual(lines[0], header(1, 0))
        self.assertEqual(
            lines[1],
            "touched: ? ? ?:? \u2014 ? [changed: none] [untracked uri: ?]",
        )

    def test_missing_first_uri_is_touched(self) -> None:
        for res in (result(None), {"locations": []}, {"locations": [{}]}):
            with self.subTest(res=res):
                lines, code = judge(sarif(res))
                self.assertEqual(code, 1)
                self.assertTrue(lines[1].endswith("[untracked uri: ?]"))

    def test_non_string_first_uri_is_touched(self) -> None:
        lines, code = judge(sarif(result(5)))
        self.assertEqual(code, 1)
        self.assertIn(" ?:3 ", lines[1])
        self.assertTrue(lines[1].endswith("[untracked uri: ?]"))

    def test_non_string_flow_uri_is_touched(self) -> None:
        bad = flow("a.py")
        bad[0]["threadFlows"][0]["locations"][0]["location"]["physicalLocation"][
            "artifactLocation"
        ]["uri"] = 7
        lines, code = judge(sarif(result("a.py", codeFlows=bad)))
        self.assertEqual(code, 1)
        self.assertTrue(lines[1].endswith("[changed: none] [untracked uri: ?]"))

    def test_flow_step_without_uri_is_touched(self) -> None:
        for step in ({"location": {}}, {}, {"location": {"physicalLocation": {}}}):
            with self.subTest(step=step):
                flows = [{"threadFlows": [{"locations": [step]}]}]
                lines, code = judge(sarif(result("a.py", codeFlows=flows)))
                self.assertEqual(code, 1)
                self.assertTrue(lines[1].endswith("[changed: none] [untracked uri: ?]"))

    def test_changed_lists_each_path_once(self) -> None:
        doc = sarif(result("a.py", codeFlows=flow("a.py", "b.py", "b.py")))
        lines, _ = judge(doc, changed={"a.py", "b.py"})
        self.assertTrue(lines[1].endswith("[changed: a.py, b.py]"))


class UnusablePredicate(unittest.TestCase):
    def test_presence_path_is_none_exactly_when_unusable(self) -> None:
        tracked = {"a.py", "b.py", "c d.py"}
        bad_step = flow("a.py")
        bad_step[0]["threadFlows"][0]["locations"][0]["location"]["physicalLocation"][
            "artifactLocation"
        ]["uri"] = 7
        cases: list[tuple[dict[str, Any], bool]] = [
            (result("a.py"), False),
            (result("a.py", codeFlows=flow("a.py", "b.py")), False),
            (result("c%20d.py"), True),
            (result("a.py", codeFlows=flow("c d.py")), False),
            (result("ghost.py"), True),
            (result("a.py", codeFlows=flow("ghost.py")), True),
            (result("a.py", codeFlows=bad_step), True),
            (result(None), True),
            (result(5), True),
            ({}, True),
        ]
        for res, unusable in cases:
            with self.subTest(res=res):
                self.assertIs(sft._unusable(res, tracked), unusable)
                path = sft._presence_path(res, tracked)
                self.assertEqual(path is None, unusable)
                if not unusable:
                    self.assertEqual(path, sft._first_uri(res))


class LineBreakEscaping(unittest.TestCase):
    """Text from SARIF or git must not start a new log line (workflow commands)."""

    def _assert_one_line_each(self, lines: list[str]) -> None:
        for line in lines:
            self.assertNotIn("\n", line)
            self.assertNotIn("\r", line)
        for line in lines[:-1]:
            self.assertFalse(line.startswith("::"), line)
        self.assertTrue(lines[-1].startswith("::error::"), lines[-1])

    def test_message_line_breaks_are_escaped(self) -> None:
        for raw, shown in (
            ("m\n::warning::x", "m\\n::warning::x"),
            ("m\r::warning::x", "m\\r::warning::x"),
            ("m\r\n::warning::x", "m\\r\\n::warning::x"),
        ):
            with self.subTest(raw=raw):
                doc = sarif(result("a.py", message={"text": raw}))
                lines, code = judge(doc, changed={"a.py"})
                self.assertEqual(code, 1)
                self._assert_one_line_each(lines)
                self.assertIn(f" \u2014 {shown} [changed", lines[1])

    def test_level_and_rule_line_breaks_are_escaped(self) -> None:
        doc = sarif(result("a.py", level="e\n::notice::l", ruleId="r\n::notice::r"))
        lines, _ = judge(doc, changed={"a.py"})
        self._assert_one_line_each(lines)
        self.assertTrue(
            lines[1].startswith("touched: e\\n::notice::l r\\n::notice::r ")
        )

    def test_uri_line_break_is_escaped_in_untracked_and_location(self) -> None:
        lines, code = judge(sarif(result("a.py%0A::notice::y")))
        self.assertEqual(code, 1)
        self._assert_one_line_each(lines)
        self.assertIn("a.py\\n::notice::y:3", lines[1])
        self.assertTrue(lines[1].endswith("[untracked uri: a.py\\n::notice::y]"))

    def test_changed_path_line_break_is_escaped(self) -> None:
        name = "a\n::notice::c.py"
        lines, code = judge(
            sarif(result("a%0A::notice::c.py")), changed={name}, tracked=[name]
        )
        self.assertEqual(code, 1)
        self._assert_one_line_each(lines)
        self.assertIn("[changed: a\\n::notice::c.py]", lines[1])

    def test_presence_path_line_break_is_escaped(self) -> None:
        name = "p\n::notice::q.py"
        lines, code = judge(sarif(), tracked=[name], manifest={name: 1})
        self.assertEqual(code, 1)
        self._assert_one_line_each(lines)
        self.assertTrue(lines[1].startswith("snyk-scan: p\\n::notice::q.py has 0"))

    def test_suppression_path_line_break_is_escaped(self) -> None:
        name = "s\n::notice::t.py"
        fs = Fs(size_of=lambda _p: 1, read_text=lambda _p: SUPPRESSION)
        lines, code = judge(sarif(), tracked=[name], manifest={}, fs=fs)
        self.assertEqual(code, 1)
        self._assert_one_line_each(lines)
        self.assertTrue(
            any(ln.startswith("snyk-scan: s\\n::notice::t.py contains") for ln in lines)
        )

    def test_coverage_lang_line_break_is_escaped(self) -> None:
        doc = {
            "runs": [
                {
                    "results": [],
                    "properties": {"coverage": [coverage(".x\n::notice::z", 1)]},
                }
            ]
        }
        lines, code = judge(doc, tracked=[])
        self.assertEqual(code, 1)
        self._assert_one_line_each(lines)

    def test_stderr_reason_line_break_is_escaped(self) -> None:
        def unreadable(_path: str) -> str:
            raise OSError("boom")

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = sft.main(
                io.StringIO(json.dumps(sarif())),
                lambda argv: b"" if argv == DIFF_ARGV else b"p\n::notice::q.py\0",
                lambda: "",
                lambda _p: 1,
                unreadable,
            )
        self.assertEqual(code, 2)
        self.assertEqual(len(err.getvalue().splitlines()), 1)
        self.assertIn("p\\n::notice::q.py", err.getvalue())


class FailureModes(unittest.TestCase):
    def test_not_a_dict(self) -> None:
        for bad in ([], "x", None, {}, {"runs": []}, {"runs": "x"}):
            with self.subTest(bad=bad), self.assertRaises(sft.JudgeError):
                judge(bad)

    def test_run_without_results(self) -> None:
        with self.assertRaises(sft.JudgeError):
            judge({"runs": [{"properties": {"coverage": []}}]})

    def test_run_results_not_list(self) -> None:
        with self.assertRaises(sft.JudgeError):
            judge({"runs": [{"results": {}, "properties": {"coverage": []}}]})

    def test_run_without_coverage(self) -> None:
        for props in ({}, {"coverage": {}}):
            with self.subTest(props=props), self.assertRaises(sft.JudgeError):
                judge({"runs": [{"results": [], "properties": props}]})
        with self.assertRaises(sft.JudgeError):
            judge({"runs": [{"results": []}]})

    def test_non_list_shapes(self) -> None:
        bad_flows = [{"threadFlows": 1}, {"threadFlows": [{"locations": 1}]}]
        cases: list[Any] = [
            result("a.py", codeFlows=1),
            result("a.py", locations=1),
            result("a.py", codeFlows=[bad_flows[0]]),
            result("a.py", codeFlows=[bad_flows[1]]),
        ]
        cases += [
            result("a.py", codeFlows=["b.py"]),
            result("a.py", codeFlows=[{"threadFlows": [["x"]]}]),
            result("a.py", codeFlows=[{"threadFlows": [{"locations": ["x"]}]}]),
            "not a dict",
        ]
        for res in cases:
            with self.subTest(res=res), self.assertRaises(sft.JudgeError):
                judge(sarif(res))

    def test_second_run_is_validated_too(self) -> None:
        bad = {"runs": [run([]), {"properties": {"coverage": []}}]}
        with self.assertRaises(sft.JudgeError):
            judge(bad)

    def test_run_not_a_dict(self) -> None:
        with self.assertRaises(sft.JudgeError):
            judge({"runs": ["x"]})


class ParseManifest(unittest.TestCase):
    def test_parses_and_skips_blank_and_comments(self) -> None:
        text = "# header\n\na.py 3\nb/c.py 0\n"
        self.assertEqual(sft.parse_manifest(text), {"a.py": 3, "b/c.py": 0})

    def test_empty(self) -> None:
        self.assertEqual(sft.parse_manifest(""), {})

    def test_malformed_line(self) -> None:
        for bad in ("a.py", "a.py x", "a.py 1 2", "a.py  1", "a.py -1"):
            with self.subTest(bad=bad), self.assertRaises(sft.JudgeError):
                sft.parse_manifest(bad + "\n")

    def test_repeated_path(self) -> None:
        with self.assertRaises(sft.JudgeError):
            sft.parse_manifest("a.py 1\na.py 2\n")

    def test_whitespace_only_line_is_skipped(self) -> None:
        self.assertEqual(sft.parse_manifest("   \n\t\na.py 1\n"), {"a.py": 1})

    def test_indented_comment_is_malformed(self) -> None:
        with self.assertRaises(sft.JudgeError):
            sft.parse_manifest("  # x\n")


class Main(unittest.TestCase):
    def _main(
        self,
        stdin: str,
        diff: bytes = b"",
        ls: bytes = b"a.py\0b.py\0",
        manifest: Any = "",
    ) -> tuple[int, str, str, list[list[str]]]:
        calls: list[list[str]] = []

        def run_git(argv: list[str]) -> bytes:
            calls.append(argv)
            if isinstance(diff, Exception):
                raise diff
            return diff if argv == DIFF_ARGV else ls

        def read_manifest() -> str:
            if isinstance(manifest, Exception):
                raise manifest
            return manifest

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sft.main(
                io.StringIO(stdin), run_git, read_manifest, lambda _p: 0, lambda _p: ""
            )
        return code, out.getvalue(), err.getvalue(), calls

    def test_clean_exit_0(self) -> None:
        code, out, err, _ = self._main(
            json.dumps(sarif(result("a.py"))), diff=b"b.py\0", manifest="a.py 1\n"
        )
        self.assertEqual((code, out, err), (0, header(0, 1) + "\n", ""))

    def test_touched_exit_1_with_stdout(self) -> None:
        code, out, err, _ = self._main(
            json.dumps(sarif(result("a.py"))), diff=b"a.py\0"
        )
        self.assertEqual(code, 1)
        self.assertIn("touched: error py/Sqli a.py:3", out)
        self.assertEqual(err, "")

    def test_git_argv_exact(self) -> None:
        _, _, _, calls = self._main(json.dumps(sarif()))
        self.assertEqual(calls, [DIFF_ARGV, LS_ARGV])
        self.assertEqual(sft.GIT_DIFF_ARGV, DIFF_ARGV)
        self.assertEqual(sft.GIT_LS_FILES_ARGV, LS_ARGV)

    def test_nul_separated_paths_are_split(self) -> None:
        code, _, _, _ = self._main(
            json.dumps(sarif(result("b.py"))), diff=b"a.py\0b.py\0", ls=b"a.py\0b.py\0"
        )
        self.assertEqual(code, 1)

    def test_trailing_nul_adds_no_empty_tracked_path(self) -> None:
        code, out, _, _ = self._main(json.dumps(sarif(result(""))))
        self.assertEqual(code, 1)
        self.assertIn("[untracked uri: ]", out)

    def test_undecodable_git_path_exits_2(self) -> None:
        code, out, err, _ = self._main(json.dumps(sarif()), ls=b"\xff.py\0")
        self.assertEqual((code, out), (2, ""))
        self.assertTrue(err.startswith("snyk_file_touch: "), err)

    def test_exit_2_messages(self) -> None:
        good = json.dumps(sarif())
        cases = [
            ("invalid json", {"stdin": "{nope"}, "stdin is not JSON"),
            ("no runs", {"stdin": '{"runs": []}'}, "SARIF has no runs"),
            ("huge integer", {"stdin": "1" * 5000}, "stdin is not usable JSON"),
            (
                "missing manifest",
                {"stdin": good, "manifest": FileNotFoundError("x")},
                ".snyk-files is missing",
            ),
            (
                "directory manifest",
                {"stdin": good, "manifest": IsADirectoryError("x")},
                ".snyk-files is unreadable",
            ),
            (
                "unreadable manifest",
                {"stdin": good, "manifest": PermissionError("x")},
                ".snyk-files is unreadable",
            ),
            (
                "malformed manifest",
                {"stdin": good, "manifest": "garbage\n"},
                "malformed line",
            ),
            (
                "second run invalid",
                {"stdin": json.dumps({"runs": [run([]), {"properties": {}}]})},
                "SARIF run has no results list",
            ),
        ]
        for name, kwargs, expected in cases:
            with self.subTest(name):
                code, out, err, _ = self._main(**kwargs)
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(
                    err.startswith("snyk_file_touch: ") and expected in err, err
                )

    def test_exit_2_cases(self) -> None:
        cases = {
            "invalid json": {"stdin": "{nope"},
            "empty object": {"stdin": "{}"},
            "no runs": {"stdin": '{"runs": []}'},
            "no results": {"stdin": '{"runs": [{"properties": {"coverage": []}}]}'},
            "no coverage": {"stdin": '{"runs": [{"results": []}]}'},
            "missing manifest": {
                "stdin": json.dumps(sarif()),
                "manifest": FileNotFoundError("no .snyk-files"),
            },
            "malformed manifest": {
                "stdin": json.dumps(sarif()),
                "manifest": "garbage\n",
            },
            "repeated manifest path": {
                "stdin": json.dumps(sarif()),
                "manifest": "a.py 1\na.py 1\n",
            },
            "int codeFlows": {"stdin": json.dumps(sarif(result(codeFlows=1)))},
            "int locations": {"stdin": json.dumps(sarif(result(locations=1)))},
            "int threadFlows": {
                "stdin": json.dumps(sarif(result(codeFlows=[{"threadFlows": 1}])))
            },
            "unreadable manifest": {
                "stdin": json.dumps(sarif()),
                "manifest": PermissionError("denied"),
            },
            "second run invalid": {
                "stdin": json.dumps(
                    {"runs": [run([]), {"properties": {"coverage": []}}]}
                )
            },
            "huge integer": {"stdin": "1" * 5000},
            "deep nesting": {"stdin": "[" * 100000},
            "git failure": {
                "stdin": json.dumps(sarif()),
                "diff": sft.JudgeError("git failed"),
            },
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                code, out, err, _ = self._main(**kwargs)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertTrue(err.startswith("snyk_file_touch: "), err)
                self.assertTrue(err.endswith("\n"))


class UndecodableStdin(io.StringIO):
    def read(self, size: int | None = -1) -> str:
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")


class StdinDecode(unittest.TestCase):
    def test_undecodable_stdin_exits_2(self) -> None:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = sft.main(
                UndecodableStdin(),
                lambda _a: b"",
                lambda: "",
                lambda _p: 0,
                lambda _p: "",
            )
        self.assertEqual(code, 2)
        self.assertTrue(err.getvalue().startswith("snyk_file_touch: "))


class Source(unittest.TestCase):
    def test_no_write_mode_open(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"open\([^)]*[\"'][rb]*[wax+][^\"']*[\"']", text))

    def test_stdlib_only(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for line in re.findall(r"^(?:import|from) (\w+)", text, re.MULTILINE):
            self.assertIn(line, sys.stdlib_module_names)


class RealGit(unittest.TestCase):
    def test_default_run_git_raises_on_nonzero(self) -> None:
        with self.assertRaises(sft.JudgeError):
            sft.default_run_git(["git", "definitely-not-a-subcommand"])

    def test_default_run_git_returns_bytes(self) -> None:
        self.assertIsInstance(sft.default_run_git(["git", "--version"]), bytes)

    def test_default_run_git_missing_binary(self) -> None:
        with self.assertRaises(sft.JudgeError):
            sft.default_run_git(["no-such-binary-xyz"])

    def test_default_run_git_non_executable_binary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prog = Path(tmp) / "prog"
            prog.write_text("#!/bin/sh\n", encoding="utf-8")
            prog.chmod(0o644)
            with self.assertRaises(sft.JudgeError) as ctx:
                sft.default_run_git([str(prog)])
        self.assertIn("cannot run", str(ctx.exception))

    def test_default_run_git_returns_stdout_only(self) -> None:
        argv = ["sh", "-c", "echo out; echo err >&2"]
        self.assertEqual(sft.default_run_git(argv), b"out\n")


def _sizes(table: dict[str, int | None]) -> Callable[[str], int | None]:
    return lambda path: table.get(path, 0)


class Coverage(unittest.TestCase):
    def _judge(
        self,
        cov: list[Any],
        tracked: list[str],
        sizes: dict[str, int | None] | None = None,
        changed: set[str] | None = None,
    ) -> tuple[list[str], int]:
        doc = {"runs": [{"results": [], "properties": {"coverage": cov}}]}
        sizes = sizes if sizes is not None else dict.fromkeys(tracked, 1)
        return judge(
            doc,
            changed,
            tracked,
            {},
            Fs(size_of=_sizes(sizes), read_text=lambda _p: ""),
        )

    def test_equal_counts_are_clean(self) -> None:
        lines, code = self._judge([coverage(".py", 2)], ["a.py", "b.py"])
        self.assertEqual((lines, code), ([header(0, 0, py="2/2")], 0))

    def test_analysed_above_tracked(self) -> None:
        lines, code = self._judge([coverage(".py", 3)], ["a.py", "b.py"])
        self.assertEqual(code, 1)
        self.assertEqual(lines[0], header(0, 0, py="3/2"))
        self.assertEqual(
            lines[1],
            "snyk-scan: Snyk analysed 3 .py files but 2 non-empty ones are tracked; "
            "a file is hidden from the scan (changed .py files: none)",
        )
        self.assertEqual(
            lines[2],
            "::error::snyk-scan: 0 finding(s) in files this PR changes; "
            "1 coverage mismatch(es); 0 presence difference(s); 0 suppression(s)",
        )

    def test_analysed_below_tracked_lists_changed_files_sorted(self) -> None:
        lines, code = self._judge(
            [coverage(".py", 1)],
            ["a.py", "b.py", "x.js"],
            changed={"b.py", "a.py", "x.js"},
        )
        self.assertEqual(code, 1)
        self.assertEqual(
            lines[1],
            "snyk-scan: Snyk analysed 1 .py files but 2 non-empty ones are tracked; "
            "a file is hidden from the scan (changed .py files: a.py, b.py)",
        )

    def test_empty_file_is_not_counted(self) -> None:
        lines, code = self._judge(
            [coverage(".py", 1)], ["a.py", "e.py"], {"a.py": 5, "e.py": 0}
        )
        self.assertEqual((lines, code), ([header(0, 0, py="1/1")], 0))

    def test_symlink_and_directory_are_not_counted(self) -> None:
        lines, code = self._judge(
            [coverage(".py", 1)], ["a.py", "link.py"], {"a.py": 5, "link.py": None}
        )
        self.assertEqual((lines, code), ([header(0, 0, py="1/1")], 0))

    def test_missing_entry_counts_zero(self) -> None:
        lines, code = self._judge([], ["a.py"])
        self.assertEqual(code, 1)
        self.assertEqual(lines[0], header(0, 0, py="0/1"))
        self.assertIn("analysed 0 .py files but 1 non-empty", lines[1])

    def test_no_files_and_no_entry_is_clean(self) -> None:
        self.assertEqual(self._judge([], [])[1], 0)

    def test_untracked_extension_is_not_compared(self) -> None:
        lines, code = self._judge([coverage(".rs", 5, "UNSUPPORTED")], ["m.rs"])
        self.assertEqual((lines, code), ([header(0, 0)], 0))

    def test_extra_supported_extension_is_compared(self) -> None:
        lines, code = self._judge(
            [coverage(".rb", 1), coverage(".go", 2)], ["a.rb", "b.go", "c.go"]
        )
        self.assertEqual(code, 0)
        self.assertTrue(lines[0].endswith("coverage .go 2/2, coverage .rb 1/1"))

    def test_extra_supported_extension_mismatch(self) -> None:
        lines, code = self._judge([coverage(".rb", 1)], ["a.rb", "b.rb"])
        self.assertEqual(code, 1)
        self.assertIn("analysed 1 .rb files but 2 non-empty", lines[1])

    def test_not_supported_entry_counts_zero(self) -> None:
        lines, code = self._judge(
            [coverage(".py", 3, "NOT_SUPPORTED")], ["a.py", "b.py", "c.py"]
        )
        self.assertEqual(code, 1)
        self.assertEqual(lines[0], header(0, 0, py="0/3"))
        self.assertIn("analysed 0 .py files but 3 non-empty", lines[1])

    def test_entry_without_type_counts_zero(self) -> None:
        entry = {"lang": ".py", "files": 1}
        lines, code = self._judge([entry], ["a.py"])
        self.assertEqual(code, 1)
        self.assertEqual(lines[0], header(0, 0, py="0/1"))

    def test_not_supported_entry_adds_no_extra_extension(self) -> None:
        lines, code = self._judge([coverage(".rb", 1, "NOT_SUPPORTED")], [])
        self.assertEqual((lines, code), ([header(0, 0)], 0))

    def test_not_supported_entry_beside_supported_one_is_ignored(self) -> None:
        cov = [coverage(".py", 2), coverage(".py", 5, "NOT_SUPPORTED")]
        lines, code = self._judge(cov, ["a.py", "b.py"])
        self.assertEqual((lines, code), ([header(0, 0, py="2/2")], 0))

    def test_analysed_above_tracked_lists_changed_file(self) -> None:
        lines, code = self._judge(
            [coverage(".py", 3)], ["a.py", "b.py"], changed={"a.py", "n.js"}
        )
        self.assertEqual(code, 1)
        self.assertEqual(
            lines[1],
            "snyk-scan: Snyk analysed 3 .py files but 2 non-empty ones are tracked; "
            "a file is hidden from the scan (changed .py files: a.py)",
        )

    def test_analysed_below_tracked_with_no_changed_file(self) -> None:
        lines, code = self._judge(
            [coverage(".py", 1)], ["a.py", "b.py"], changed={"n.js"}
        )
        self.assertEqual(code, 1)
        self.assertEqual(
            lines[1],
            "snyk-scan: Snyk analysed 1 .py files but 2 non-empty ones are tracked; "
            "a file is hidden from the scan (changed .py files: none)",
        )

    def test_counts_sum_over_runs(self) -> None:
        doc = {
            "runs": [
                {"results": [], "properties": {"coverage": [coverage(".py", 1)]}},
                {"results": [], "properties": {"coverage": [coverage(".py", 2)]}},
            ]
        }
        lines, code = judge(
            doc,
            None,
            ["a.py", "b.py", "c.py"],
            {},
            Fs(
                size_of=_sizes({"a.py": 1, "b.py": 1, "c.py": 1}),
                read_text=lambda _p: "",
            ),
        )
        self.assertEqual((lines, code), ([header(0, 0, py="3/3")], 0))

    def test_malformed_entries_exit_2(self) -> None:
        bad: list[Any] = [
            "x",
            {},
            {"lang": 5, "files": 1},
            {"lang": ".py", "files": "1"},
            {"lang": ".py", "files": -1},
            {"lang": ".py", "files": True},
            {"lang": ".py"},
        ]
        for entry in bad:
            with self.subTest(entry=entry), self.assertRaises(sft.JudgeError):
                self._judge([entry], [])


class Presence(unittest.TestCase):
    def _judge(
        self,
        results: list[dict[str, Any]],
        manifest: dict[str, int],
        changed: set[str] | None = None,
        tracked: list[str] | None = None,
    ) -> tuple[list[str], int]:
        return judge(
            sarif(*results), changed, tracked or ["a.py", "b.py", "c d.py"], manifest
        )

    def test_equal_is_clean(self) -> None:
        lines, code = self._judge([result("a.py"), result("a.py")], {"a.py": 2})
        self.assertEqual((lines, code), ([header(0, 2)], 0))

    def test_count_up_unchanged_file_is_labelled(self) -> None:
        lines, code = self._judge([result("a.py"), result("a.py")], {"a.py": 1})
        self.assertEqual(code, 1)
        self.assertEqual(
            lines[1],
            "snyk-scan: a.py has 2 results; .snyk-files says 1"
            " (file unchanged by this PR: Snyk drift, a master-side change, or an"
            " effect of this PR's edits elsewhere)",
        )

    def test_count_down_unchanged_file_is_labelled(self) -> None:
        lines, code = self._judge([result("a.py")], {"a.py": 2})
        self.assertEqual(code, 1)
        self.assertTrue(
            lines[1].startswith(
                "snyk-scan: a.py has 1 results; .snyk-files says 2 (file unchanged"
            )
        )

    def test_file_appearing_is_a_difference(self) -> None:
        lines, code = self._judge([result("b.py")], {})
        self.assertEqual(code, 1)
        self.assertTrue(
            lines[1].startswith("snyk-scan: b.py has 1 results; .snyk-files says 0 (")
        )

    def test_file_vanishing_is_a_difference(self) -> None:
        lines, code = self._judge([], {"a.py": 3})
        self.assertEqual(code, 1)
        self.assertTrue(
            lines[1].startswith("snyk-scan: a.py has 0 results; .snyk-files says 3 (")
        )

    def test_changed_file_count_up_has_no_label(self) -> None:
        lines, code = self._judge(
            [result("a.py"), result("a.py")], {"a.py": 1}, changed={"a.py"}
        )
        self.assertEqual(code, 1)
        self.assertIn("snyk-scan: a.py has 2 results; .snyk-files says 1", lines)

    def test_changed_file_count_down_has_no_label(self) -> None:
        lines, code = self._judge([result("a.py")], {"a.py": 2}, changed={"a.py"})
        self.assertEqual(code, 1)
        self.assertIn("snyk-scan: a.py has 1 results; .snyk-files says 2", lines)

    def test_changed_file_appearing_has_no_label(self) -> None:
        lines, code = self._judge([result("b.py")], {}, changed={"b.py"})
        self.assertEqual(code, 1)
        self.assertIn("snyk-scan: b.py has 1 results; .snyk-files says 0", lines)

    def test_flow_step_without_uri_is_not_counted(self) -> None:
        flows = [{"threadFlows": [{"locations": [{"location": {}}]}]}]
        lines, code = self._judge([result("a.py", codeFlows=flows)], {})
        self.assertEqual(code, 1)
        self.assertFalse(any("results; .snyk-files" in ln for ln in lines))

    def test_changed_file_has_no_label(self) -> None:
        lines, code = self._judge([], {"a.py": 3}, changed={"a.py"})
        self.assertEqual(code, 1)
        self.assertEqual(lines[1], "snyk-scan: a.py has 0 results; .snyk-files says 3")

    def test_sorted_by_path(self) -> None:
        lines, _ = self._judge([result("b.py")], {"a.py": 1}, changed={"a.py"})
        self.assertEqual(lines[1], "snyk-scan: a.py has 0 results; .snyk-files says 1")
        self.assertTrue(
            lines[2].startswith("snyk-scan: b.py has 1 results; .snyk-files says 0")
        )

    def test_error_line_counts_presence(self) -> None:
        lines, _ = self._judge([result("b.py")], {"a.py": 1}, changed={"a.py"})
        self.assertTrue(
            lines[-1].endswith(
                "0 coverage mismatch(es); 2 presence difference(s); 0 suppression(s)"
            )
        )

    def test_untracked_whitespace_and_unusable_uris_are_not_counted(self) -> None:
        results = [
            result("ghost.py"),
            result("c%20d.py"),
            result(None),
            result("a.py", codeFlows=flow("ghost.py")),
        ]
        lines, code = self._judge(results, {})
        self.assertEqual(code, 1)
        self.assertEqual(sum(ln.startswith("touched:") for ln in lines), 4)
        self.assertFalse(any("results; .snyk-files" in ln for ln in lines))

    def test_count_keyed_by_decoded_path(self) -> None:
        lines, code = self._judge(
            [result("c%2Bd.py")], {"c+d.py": 1}, tracked=["c+d.py"]
        )
        self.assertEqual((lines, code), ([header(0, 1)], 0))


class Suppression(unittest.TestCase):
    def _judge(
        self,
        texts: dict[str, str],
        sizes: dict[str, int | None] | None = None,
        tracked: list[str] | None = None,
    ) -> tuple[list[str], int]:
        files = tracked if tracked is not None else list(texts)
        sizes = sizes if sizes is not None else dict.fromkeys(files, 1)
        doc = {
            "runs": [
                {
                    "results": [],
                    "properties": {
                        "coverage": [
                            coverage(
                                ".py", len([f for f in files if f.endswith(".py")])
                            )
                        ]
                    },
                }
            ]
        }
        return judge(
            doc,
            None,
            files,
            {},
            Fs(size_of=_sizes(sizes), read_text=lambda p: texts.get(p, "")),
        )

    def test_matches_in_any_case_and_whitespace(self) -> None:
        variants = [
            SUPPRESSION,
            SUPPRESSION.upper(),
            phrase("\t"),
            phrase("  \t "),
        ]
        for text in variants:
            with self.subTest(text=text):
                lines, code = self._judge({"a.py": f"# {text} PythonX: why\n"})
                self.assertEqual(code, 1)
                self.assertEqual(
                    lines[1],
                    f"snyk-scan: a.py contains an inline Snyk suppression ({SUPPRESSION})",
                )
                self.assertTrue(
                    lines[2].endswith(
                        "0 coverage mismatch(es); 0 presence difference(s); 1 suppression(s)"
                    )
                )

    def test_clean_file_and_near_misses(self) -> None:
        text = "deep" + "code" + "ignore"
        lines, code = self._judge({"a.py": "x = 1\n", "b.py": text})
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)

    def test_ls_files_order(self) -> None:
        text = f"# {SUPPRESSION}"
        lines, _ = self._judge({"z.py": text, "a.py": text}, tracked=["z.py", "a.py"])
        self.assertEqual([ln.split()[1] for ln in lines[1:3]], ["z.py", "a.py"])

    def test_empty_and_non_regular_files_are_not_read(self) -> None:
        text = f"# {SUPPRESSION}"
        lines, code = self._judge(
            {"e.py": text, "l.py": text},
            sizes={"e.py": 0, "l.py": None},
        )
        self.assertEqual(code, 1)  # coverage says 1, tracked non-empty is 0
        self.assertFalse(any("suppression (" in ln for ln in lines))

    def test_non_compared_extension_is_not_read(self) -> None:
        lines, code = self._judge({"a.rs": f"// {SUPPRESSION}"})
        self.assertEqual((lines, code), ([header(0, 0)], 0))

    def test_read_failure_exits_2(self) -> None:
        def boom(_p: str) -> str:
            raise PermissionError("denied")

        checkout = sft.Checkout(frozenset(), ("a.py",), lambda _p: 1, boom)
        doc = sarif()
        doc["runs"][0]["properties"]["coverage"] = [coverage(".py", 1)]
        with self.assertRaises(sft.JudgeError):
            sft.judge(doc, checkout, {})

    def test_source_does_not_hold_the_phrase(self) -> None:
        for path in (SCRIPT, Path(__file__)):
            text = path.read_text(encoding="utf-8")
            self.assertIsNone(re.search("deep" + r"code[ \t]+ignore", text))


class DefaultHelpers(unittest.TestCase):
    def test_size_of(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "full.txt").write_text("abc", encoding="utf-8")
            (root / "empty.txt").write_text("", encoding="utf-8")
            os.symlink(root / "full.txt", root / "link.txt")
            (root / "dir").mkdir()
            self.assertEqual(sft.default_size_of(str(root / "full.txt")), 3)
            self.assertEqual(sft.default_size_of(str(root / "empty.txt")), 0)
            self.assertIsNone(sft.default_size_of(str(root / "link.txt")))
            self.assertIsNone(sft.default_size_of(str(root / "dir")))
            self.assertIsNone(sft.default_size_of(str(root / "missing")))

    def test_read_text_replaces_invalid_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.txt"
            path.write_bytes(b"ok\xff\xfe!")
            self.assertEqual(sft.default_read_text(str(path)), "ok\ufffd\ufffd!")

    def test_read_manifest_reads_cwd_file(self) -> None:
        old = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, ".snyk-files").write_text("a.py 2\n", encoding="utf-8")
            os.chdir(tmp)
            try:
                self.assertEqual(sft.default_read_manifest(), "a.py 2\n")
            finally:
                os.chdir(old)

    def test_read_manifest_missing_file(self) -> None:
        old = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with self.assertRaises(FileNotFoundError):
                    sft.default_read_manifest()
            finally:
                os.chdir(old)


class RealTree(unittest.TestCase):
    def test_real_tree_has_no_suppression(self) -> None:
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        raw = subprocess_output(["git", "ls-files", "-z"], env)
        tracked = tuple(p for p in raw.decode("utf-8").split("\0") if p)
        checkout = sft.Checkout(
            frozenset(),
            tracked,
            lambda p: sft.default_size_of(str(ROOT / p)),
            lambda p: sft.default_read_text(str(ROOT / p)),
        )
        eligible = sft._eligible(checkout, sft.COMPARED_EXTS)
        self.assertGreater(len(eligible), 0)
        self.assertEqual(sft._suppression_lines(eligible, checkout), [])

    def test_live_manifest_has_the_bootstrap_lines(self) -> None:
        manifest = sft.parse_manifest(
            (ROOT / ".snyk-files").read_text(encoding="utf-8")
        )
        self.assertEqual(
            manifest,
            {
                "scripts/mutation_gate_items.py": 3,
                "scripts/mutation_weakening.py": 8,
                "scripts/zeta_results.py": 4,
                "tests/test_mutation_weakening.py": 1,
                "tests/test_mutation_weakening_e2e.py": 1,
            },
        )


FIXTURES = ROOT / "tests" / "fixtures" / "snyk"


class Replay(unittest.TestCase):
    def test_replay_262(self) -> None:
        sarif = json.loads((FIXTURES / "sarif-262.json").read_text(encoding="utf-8"))
        uris = {
            u
            for run in sarif["runs"]
            for res in run["results"]
            for u in sft._decoded_uris(res)
            if u is not None
        }
        checkout = sft.Checkout(
            frozenset({"scripts/pip_audit_advisory.py"}),
            tuple(sorted(uris)),
            lambda _p: 1,
            lambda _p: "",
        )
        lines, code = sft.judge(sarif, checkout, {})
        touched = [ln for ln in lines if ln.startswith("touched:")]
        self.assertEqual(len(touched), 1)
        self.assertTrue(
            touched[0].startswith(
                "touched: warning python/CommandInjection "
                "scripts/pip_audit_advisory.py:147 "
            ),
            touched[0],
        )
        self.assertEqual(code, 1)

    def test_replay_d3ef01e(self) -> None:
        sarif = json.loads(
            (FIXTURES / "sarif-d3ef01e.json").read_text(encoding="utf-8")
        )
        sizes: dict[str, int] = {}
        tsv = (FIXTURES / "files-d3ef01e.tsv").read_text(encoding="utf-8")
        for row in tsv.splitlines():
            size, path = row.split("\t", 1)
            sizes[path] = int(size)
        checkout = sft.Checkout(
            frozenset(),
            tuple(sizes),
            sizes.get,
            lambda _p: "",
        )
        manifest = {
            "scripts/mutation_gate_items.py": 3,
            "scripts/mutation_weakening.py": 8,
            "scripts/zeta_results.py": 4,
            "tests/test_mutation_weakening.py": 1,
            "tests/test_mutation_weakening_e2e.py": 1,
        }
        lines, code = sft.judge(sarif, checkout, manifest)
        self.assertIn("coverage .py 118/118, coverage .html 1/1", lines[0])
        self.assertIn("0 touched, 17 untouched", lines[0])
        self.assertFalse([ln for ln in lines if "snyk-scan:" in ln], lines)
        self.assertEqual(code, 0)


def subprocess_output(argv: list[str], env: dict[str, str]) -> bytes:
    return subprocess.run(
        argv, cwd=ROOT, env=env, capture_output=True, check=True
    ).stdout


if __name__ == "__main__":
    unittest.main()
