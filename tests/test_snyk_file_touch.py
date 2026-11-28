"""R5, R6, R9: the snyk-scan file-touch judge (touch decision, header, failure modes)."""

import contextlib
import importlib.util
import io
import json
import re
import sys
import unittest
from pathlib import Path
from typing import Any

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


def result(
    uri: str | None = "a.py", line: int | None = 3, **extra: Any
) -> dict[str, Any]:
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


def judge(
    doc: object,
    changed: set[str] | None = None,
    tracked: list[str] | None = None,
) -> tuple[list[str], int]:
    return sft.judge(
        doc,
        changed or set(),
        tracked if tracked is not None else ["a.py", "b.py", "c d.py"],
        {},
        lambda _p: 1,
        lambda _p: "",
    )


class TouchDecision(unittest.TestCase):
    def test_no_touched_result_exits_0(self) -> None:
        lines, code = judge(sarif(result("a.py")), changed={"b.py"})
        self.assertEqual(code, 0)
        self.assertEqual(lines, ["snyk: 0 touched, 1 untouched; "])

    def test_no_results_exits_0(self) -> None:
        lines, code = judge(sarif())
        self.assertEqual((lines, code), (["snyk: 0 touched, 0 untouched; "], 0))

    def test_touched_location(self) -> None:
        lines, code = judge(sarif(result("a.py", 7)), changed={"a.py"})
        self.assertEqual(code, 1)
        self.assertEqual(lines[0], "snyk: 1 touched, 0 untouched; ")
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
        self.assertEqual(lines[0], "snyk: 1 touched, 1 untouched; ")

    def test_missing_fields_print_question_mark(self) -> None:
        lines, code = judge(sarif({}), changed=set())
        self.assertEqual(code, 0)
        self.assertEqual(lines, ["snyk: 0 touched, 1 untouched; "])
        lines, code = judge(
            sarif(
                {
                    "locations": [
                        {"physicalLocation": {"artifactLocation": {"uri": "ghost.py"}}}
                    ]
                }
            )
        )
        self.assertEqual(code, 1)
        self.assertTrue(
            lines[1].startswith("touched: ? ? ghost.py:? — ? [changed: none]")
        )

    def test_missing_location_is_unjudgeable_as_untouched(self) -> None:
        # No uri at all: nothing to compare, so it is counted untouched.
        lines, code = judge(sarif(result(None)))
        self.assertEqual((lines[0], code), ("snyk: 0 touched, 1 untouched; ", 0))

    def test_changed_lists_each_path_once(self) -> None:
        doc = sarif(result("a.py", codeFlows=flow("a.py", "b.py", "b.py")))
        lines, _ = judge(doc, changed={"a.py", "b.py"})
        self.assertTrue(lines[1].endswith("[changed: a.py, b.py]"))


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
                io.StringIO(stdin), run_git, read_manifest, lambda _p: 1, lambda _p: ""
            )
        return code, out.getvalue(), err.getvalue(), calls

    def test_clean_exit_0(self) -> None:
        code, out, err, _ = self._main(
            json.dumps(sarif(result("a.py"))), diff=b"b.py\0"
        )
        self.assertEqual((code, out, err), (0, "snyk: 0 touched, 1 untouched; \n", ""))

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

    def test_nul_split_ignores_trailing_empty(self) -> None:
        code, _, _, _ = self._main(
            json.dumps(sarif(result("b.py"))), diff=b"a.py\0b.py\0", ls=b"a.py\0b.py\0"
        )
        self.assertEqual(code, 1)

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


if __name__ == "__main__":
    unittest.main()
