"""R21, R22, R25, R26, R34: items for the mutation-gate-items check (Python and gate)."""

import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mgi: Any = _load("mutation_gate_items", SCRIPTS / "mutation_gate_items.py")
_helper: Any = _load(
    "mutation_gate_clearance_test_helper",
    ROOT / "tests" / "test_mutation_gate_clearance.py",
)
REASON = "reviewed the change by hand"
MAKEFILE = """FLAGS = -x \\
  -y
CAP = $(FLAGS) --cap
.PHONY: mutants lint
lint:
\techo lint
mutants: lint
\trun $(CAP) $$HOME
"""
MUTATION_PR = """name: mutation-pr
jobs:
  mutation-pr:
    steps:
      - uses: taiki-e/install-action@{sha} # {version}
        with:
          tool: x
"""
SHA_OLD = "a" * 40
SHA_NEW = "b" * 40


class ItemsCase(_helper.RepoCase):
    """A repo whose base commit holds a sq/ copy plus the root files the items watch."""

    def setUp(self) -> None:
        super().setUp()
        for name in (
            "sq.py",
            "test_sq.py",
            "cosmic-ray.toml",
            "mutants-equivalent.toml",
        ):
            self.write(f"sq/{name}", (ROOT / "sq" / name).read_text())
        self.write("scripts/mutation-pr-detect.sh", "#!/bin/sh\necho one\n")
        self.write("Makefile", MAKEFILE)
        self.write(
            ".github/workflows/mutation-pr.yml",
            MUTATION_PR.format(sha=SHA_OLD, version="v1"),
        )
        self.write(
            ".github/workflows/other.yml", "name: other\njobs:\n  a:\n    steps: []\n"
        )
        self.write(".github/mutation-gate-allowed-signers", "# none\n")
        self.commit("add fixtures")
        self.base = self.rev("HEAD")

    def items(self, kind: str | None = None) -> list[Any]:
        found = mgi.collect(self.repo, self.base, self.rev("HEAD"))
        return [i for i in found if kind is None or i.kind == kind]

    def run_cli(self, pr: int | None = 7) -> tuple[int, str]:
        return mgi.run(self.repo, self.base, "HEAD", pr, str(self.signers))

    def eq_entry(
        self, fragment: str, operator: str, function: str, col: int, variant: int | None
    ) -> str:
        lines = (self.repo / "sq" / "sq.py").read_text().split("\n")
        index = next(i for i, text in enumerate(lines) if fragment in text)
        above = next(
            lines[j].strip() for j in range(index - 1, -1, -1) if lines[j].strip()
        )
        fields = {
            "operator": operator,
            "function": function,
            "line": lines[index].strip(),
            "col": col,
            "above": above,
        }
        if variant is not None:
            fields["variant"] = variant
        fields["reason"] = "test entry"
        body = "\n".join(f"{k} = {json.dumps(v)}" for k, v in fields.items())
        return f"[[equivalent]]\n{body}\n"

    def number_entry(self, variant: int | None) -> str:
        return self.eq_entry(
            "k = 1", "core/NumberReplacer", "generate_squares", 8, variant
        )

    def and_entry(self, col: int) -> str:
        return self.eq_entry(
            "LARGE_RUN_THRESHOLD is not None and",
            "core/ReplaceAndWithOr",
            "refuse_large_run",
            col,
            None,
        )

    def set_equivalents(self, text: str) -> None:
        self.write("sq/mutants-equivalent.toml", text)
        self.commit("equivalents")


class PythonEquivalentTest(ItemsCase):
    def test_new_entry_is_an_item_keyed_by_its_content(self) -> None:
        self.set_equivalents(self.number_entry(0))
        (item,) = self.items("python-equivalent")
        self.assertEqual(item.target, "sq")
        self.assertEqual(
            item.key,
            (
                "sq",
                "core/NumberReplacer",
                "generate_squares",
                "k = 1",
                "limit = 10**max_digits",
                "2",
            ),
        )

    def test_unchanged_equivalents_are_not_items(self) -> None:
        self.write("sq/mutants-equivalent.toml", self.number_entry(0))
        self.commit("entry")
        self.base = self.rev("HEAD")
        self.write("README", "y\n")
        self.commit("unrelated")
        self.assertEqual(self.items(), [])

    def test_variant_change_is_an_item(self) -> None:
        self.write("sq/mutants-equivalent.toml", self.number_entry(0))
        self.commit("entry")
        self.base = self.rev("HEAD")
        self.set_equivalents(self.number_entry(1))
        (item,) = self.items("python-equivalent")
        self.assertEqual(item.key[-1], "3")

    def test_added_duplicate_of_an_entry_is_an_item(self) -> None:
        self.write("sq/mutants-equivalent.toml", self.number_entry(0))
        self.commit("entry")
        self.base = self.rev("HEAD")
        self.set_equivalents(self.number_entry(0) + "\n" + self.number_entry(0))
        (item,) = self.items("python-equivalent")
        self.assertEqual(item.key[-1], "duplicate-entry")

    def test_pure_line_shift_is_not_an_item(self) -> None:
        self.write("sq/mutants-equivalent.toml", self.number_entry(0))
        self.commit("entry")
        self.base = self.rev("HEAD")
        self.write(
            "sq/mutants-equivalent.toml",
            "# a comment\n\n# another\n" + self.number_entry(0),
        )
        self.commit("shift entry")
        self.write(
            "sq/sq.py", "# shifted\n# down\n" + (self.repo / "sq/sq.py").read_text()
        )
        self.commit("shift module")
        self.assertEqual(self.items(), [])

    def test_edited_entry_line_does_not_crash(self) -> None:
        self.write("sq/mutants-equivalent.toml", self.number_entry(0))
        self.commit("entry")
        self.base = self.rev("HEAD")
        edited = self.number_entry(0).replace('"k = 1"', '"k = 2"')
        self.set_equivalents(edited)
        self.assertEqual(self.items("python-equivalent"), [])

    def test_retarget_onto_an_equal_operator_elsewhere_is_an_item(self) -> None:
        self.write("sq/mutants-equivalent.toml", self.and_entry(39))
        self.commit("entry")
        self.base = self.rev("HEAD")
        self.set_equivalents(self.and_entry(71))
        (item,) = self.items("python-equivalent")
        self.assertEqual(item.key[1], "core/ReplaceAndWithOr")
        self.assertEqual(item.key[-1], "2")

    def test_unparseable_head_toml_is_an_item(self) -> None:
        self.set_equivalents("[[equivalent]\nnot toml\n")
        (item,) = self.items("python-equivalent")
        self.assertEqual(item.key[1], "unparseable")

    def test_gitattributes_export_ignore_does_not_hide_the_file(self) -> None:
        self.write(".gitattributes", "sq/mutants-equivalent.toml export-ignore\n")
        self.write("sq/mutants-equivalent.toml", self.number_entry(0))
        self.commit("entry with export-ignore")
        self.assertEqual(len(self.items("python-equivalent")), 1)

    def test_planted_pr_code_never_runs(self) -> None:
        marker = self.tmp / "ran"
        payload = f"from pathlib import Path\nPath({str(marker)!r}).write_text('x')\n"
        for path in (
            "sq/parso.py",
            "sq/sitecustomize.py",
            "parso.py",
            "sitecustomize.py",
        ):
            self.write(path, payload)
        self.write("sq/mutants-equivalent.toml", self.number_entry(0))
        self.commit("entry with planted files")
        self.assertEqual(len(self.items("python-equivalent")), 1)
        self.assertFalse(marker.exists())

    def test_tools_run_outside_the_repo_in_an_empty_directory(self) -> None:
        out = mgi.run_tool(["pwd"]).stdout.strip()
        self.assertNotIn(str(self.repo), out)
        self.assertNotEqual(Path(out), ROOT)


class PythonConfigTest(ItemsCase):
    def set_timeout(self, value: str) -> None:
        path = self.repo / "sq" / "cosmic-ray.toml"
        text = re.sub(r"timeout = [0-9.]+", f"timeout = {value}", path.read_text())
        self.write("sq/cosmic-ray.toml", text)
        self.commit(f"timeout {value}")

    def test_timeout_change_is_keyed_by_its_new_value(self) -> None:
        self.set_timeout("120.0")
        (item,) = self.items("python-config")
        self.assertEqual(item.key, ("sq", "cosmic-ray.timeout", "120.0"))
        self.assertEqual(item.target, "sq")

    def test_a_further_change_gives_a_new_key(self) -> None:
        self.set_timeout("120.0")
        first = self.items("python-config")
        self.set_timeout("180.0")
        self.assertNotEqual(first, self.items("python-config"))

    def test_removed_key_is_an_item(self) -> None:
        path = self.repo / "sq" / "cosmic-ray.toml"
        self.write(
            "sq/cosmic-ray.toml", path.read_text().replace("timeout = 60.0\n", "")
        )
        self.commit("drop timeout")
        (item,) = self.items("python-config")
        self.assertEqual(item.key, ("sq", "cosmic-ray.timeout", mgi.CONFIG_REMOVED))

    def test_unparseable_config_is_an_item(self) -> None:
        self.write("sq/cosmic-ray.toml", "[cosmic-ray\n")
        self.commit("broken")
        (item,) = self.items("python-config")
        self.assertEqual(item.key[1], "unparseable")


class GateItemTest(ItemsCase):
    def blob(self, path: str) -> str:
        return self.git("rev-parse", f"HEAD:{path}")

    def test_changed_detect_script_is_a_gate_item(self) -> None:
        self.write("scripts/mutation-pr-detect.sh", "#!/bin/sh\necho two\n")
        self.commit("edit script")
        (item,) = self.items("gate")
        self.assertEqual(item.target, "gate")
        self.assertEqual(
            item.key,
            (
                "scripts/mutation-pr-detect.sh",
                self.blob("scripts/mutation-pr-detect.sh"),
            ),
        )

    def test_changed_allowed_signers_file_is_a_gate_item(self) -> None:
        self.write(".github/mutation-gate-allowed-signers", "# changed\n")
        self.commit("signers")
        (item,) = self.items("gate")
        self.assertEqual(item.key[0], ".github/mutation-gate-allowed-signers")

    def test_weakening_fixture_and_python_script_are_gate_items(self) -> None:
        self.write("tests/fixtures/mutation_weakening/a/x.py", "x = 1\n")
        self.write("scripts/mutation_other.py", "x = 1\n")
        self.write("scripts/unrelated.py", "x = 1\n")
        self.commit("more")
        paths = sorted(i.key[0] for i in self.items("gate"))
        self.assertEqual(
            paths,
            ["scripts/mutation_other.py", "tests/fixtures/mutation_weakening/a/x.py"],
        )

    def test_mutants_recipe_change_is_a_gate_item(self) -> None:
        self.write("Makefile", MAKEFILE.replace("run $(CAP)", "run --new $(CAP)"))
        self.commit("recipe")
        (item,) = self.items("gate")
        self.assertEqual(item.key[0], "Makefile")

    def test_referenced_variable_change_is_a_gate_item(self) -> None:
        self.write("Makefile", MAKEFILE.replace("-y", "-z"))
        self.commit("variable")
        self.assertEqual([i.key[0] for i in self.items("gate")], ["Makefile"])

    def test_non_recipe_makefile_change_is_not_an_item(self) -> None:
        self.write("Makefile", MAKEFILE.replace("echo lint", "echo lint now"))
        self.commit("lint recipe")
        self.assertEqual(self.items(), [])

    def test_other_workflow_with_job_mutation_pr_is_a_gate_item(self) -> None:
        self.write(
            ".github/workflows/other.yml",
            "name: other\njobs:\n  mutation-pr:\n    steps: []\n",
        )
        self.commit("impostor")
        (item,) = self.items("gate")
        self.assertEqual(item.key[0], ".github/workflows/other.yml")

    def test_other_workflow_named_secret_scan_is_a_gate_item(self) -> None:
        self.write(
            ".github/workflows/other.yml",
            "name: other\njobs:\n  a:\n    name: secret-scan\n    steps: []\n",
        )
        self.commit("impostor name")
        self.assertEqual(len(self.items("gate")), 1)

    def test_unrelated_workflow_change_is_not_an_item(self) -> None:
        self.write(
            ".github/workflows/other.yml", "name: other\njobs:\n  b:\n    steps: []\n"
        )
        self.commit("benign")
        self.assertEqual(self.items(), [])

    def test_sha_and_comment_bump_is_not_an_item(self) -> None:
        self.write(
            ".github/workflows/mutation-pr.yml",
            MUTATION_PR.format(sha=SHA_NEW, version="v2"),
        )
        self.commit("bump")
        self.assertEqual(self.items(), [])

    def test_bump_that_also_changes_another_line_is_an_item(self) -> None:
        text = MUTATION_PR.format(sha=SHA_NEW, version="v2").replace(
            "tool: x", "tool: y"
        )
        self.write(".github/workflows/mutation-pr.yml", text)
        self.commit("bump and edit")
        self.assertEqual(len(self.items("gate")), 1)

    def test_bump_to_another_action_is_an_item(self) -> None:
        text = MUTATION_PR.format(sha=SHA_NEW, version="v2").replace("taiki-e", "evil")
        self.write(".github/workflows/mutation-pr.yml", text)
        self.commit("swap action")
        self.assertEqual(len(self.items("gate")), 1)


class MakeParsingTest(unittest.TestCase):
    def test_text_covers_recipe_continuations_and_transitive_variables(self) -> None:
        text = "A = $(B)\nB = deep \\\n  value\nC = unused\nmutants-x:\n\tuse $(A)\n"
        out = mgi.mutants_text(text)
        self.assertIn("deep", out)
        self.assertIn("value", out)
        self.assertNotIn("unused", out)

    def test_shell_dollar_dollar_is_not_a_make_reference(self) -> None:
        out = mgi.mutants_text("HOME2 = x\nmutants:\n\techo $$(HOME2)\n")
        self.assertNotIn("HOME2 =", out)

    def test_no_mutants_target_gives_stable_text(self) -> None:
        self.assertEqual(
            mgi.mutants_text("lint:\n\techo\n"), mgi.mutants_text("lint:\n\tother\n")
        )

    def test_only_uses_bumps_rejects_added_lines(self) -> None:
        old = f"- uses: a/b@{SHA_OLD} # v1\n"
        self.assertTrue(mgi.only_uses_bumps(old, f"- uses: a/b@{SHA_NEW} # v2\n"))
        self.assertFalse(mgi.only_uses_bumps(old, old + "- run: x\n"))


class RegistryTest(ItemsCase):
    def test_registered_collector_runs(self) -> None:
        extra = mgi.Item("sq", "extra", ("k",))
        with mock.patch.dict(mgi._COLLECTORS, clear=False):
            mgi.register("extra", lambda ctx: [extra])
            self.assertIn(extra, self.items())

    def test_context_exposes_paths_and_show(self) -> None:
        seen: list[Any] = []

        def spy(ctx: Any) -> list[Any]:
            seen.append((ctx.changed, ctx.show(ctx.head, "README"), ctx.base))
            return []

        self.write("README", "changed\n")
        self.commit("readme")
        with mock.patch.dict(mgi._COLLECTORS, clear=False):
            mgi.register("spy", spy)
            self.items()
        self.assertEqual(seen, [(["README"], "changed\n", self.base)])


class ClearanceTest(ItemsCase):
    def change_timeout(self, value: str) -> None:
        path = self.repo / "sq" / "cosmic-ray.toml"
        text = path.read_text()
        self.write(
            "sq/cosmic-ray.toml",
            re.sub(r"timeout = [0-9.]+", f"timeout = {value}", text),
        )
        self.commit(f"timeout {value}")

    def review(self, *targets: str, pr: int = 7, key: Path | None = None) -> str:
        trailers = [self.trailer(pr, t) for t in targets]
        return self.commit(
            "chore: mutation gate review", *trailers, key=key or self.key
        )

    def test_red_output_carries_the_remedy_command(self) -> None:
        self.change_timeout("120.0")
        code, text = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn(
            "uncleared item: sq python-config sq | cosmic-ray.timeout | 120.0", text
        )
        self.assertIn("commit --allow-empty -S -m 'chore: mutation gate review'", text)
        self.assertIn("Mutation-Gate-Reviewed: #7 sq: <reason>", text)
        self.assertIn(f"key::{self.pub(self.key).split(' ', 1)[0]} ", text)

    def test_one_remedy_command_covers_every_uncleared_target(self) -> None:
        self.change_timeout("120.0")
        self.write("scripts/mutation-pr-detect.sh", "x\n")
        self.commit("gate change")
        _, text = self.run_cli()
        self.assertIn("#7 sq: <reason>", text)
        self.assertIn("#7 gate: <reason>", text)
        self.assertEqual(text.count("chore: mutation gate review"), 1)

    def test_without_a_pr_nothing_is_cleared(self) -> None:
        self.change_timeout("120.0")
        self.review("sq")
        code, text = self.run_cli(pr=None)
        self.assertEqual(code, 1)
        self.assertIn("#<pr> sq: <reason>", text)

    def test_no_items_is_green(self) -> None:
        self.write("README", "z\n")
        self.commit("docs")
        self.assertEqual(self.run_cli()[0], 0)

    def test_verified_commit_with_the_items_key_in_its_tree_clears(self) -> None:
        self.change_timeout("120.0")
        self.review("sq")
        self.assertEqual(self.run_cli()[0], 0)

    def test_verified_commit_whose_tree_holds_an_earlier_value_does_not_clear(
        self,
    ) -> None:
        self.change_timeout("120.0")
        self.review("sq")
        self.change_timeout("180.0")
        code, text = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn("180.0", text)

    def test_unsigned_trailer_does_not_clear_and_is_reported(self) -> None:
        self.change_timeout("120.0")
        sha = self.commit("review", self.trailer(7, "sq"))
        code, text = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn(f"trailer ignored: {sha}: unsigned", text)

    def test_another_target_or_another_pr_does_not_clear(self) -> None:
        self.change_timeout("120.0")
        self.review("gate")
        self.assertEqual(self.run_cli()[0], 1)
        self.review("sq", pr=8)
        self.assertEqual(self.run_cli()[0], 1)

    def test_key_outside_the_signers_file_does_not_clear(self) -> None:
        self.change_timeout("120.0")
        self.review("sq", key=self.other_key)
        self.assertEqual(self.run_cli()[0], 1)

    def test_one_commit_with_two_trailer_lines_clears_two_targets(self) -> None:
        self.change_timeout("120.0")
        self.write("scripts/mutation-pr-detect.sh", "changed\n")
        self.commit("changes")
        self.assertEqual(self.run_cli()[0], 1)
        self.review("sq", "gate")
        self.assertEqual(self.run_cli()[0], 0)

    def test_signers_come_from_the_base_branch_when_no_override(self) -> None:
        self.change_timeout("120.0")
        self.review("sq")
        code, _ = mgi.run(self.repo, self.base, "HEAD", 7, None)
        self.assertEqual(code, 1)


class CliTest(ItemsCase):
    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPTS / "mutation-gate-items.sh"), *args],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
            env={
                "PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin",
                "HOME": str(self.tmp / "home"),
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_SYSTEM": "/dev/null",
                "MUTATION_GATE_SIGNERS": str(self.signers),
            },
        )

    def test_usage_error_exits_2(self) -> None:
        self.assertEqual(self.cli("only-one").returncode, 2)

    def test_green_and_red_exit_codes(self) -> None:
        head = self.rev("HEAD")
        green = self.cli(self.base, head, "--repo", str(self.repo))
        self.assertEqual(
            (green.returncode, green.stdout.strip()),
            (0, "mutation-gate-items: no uncleared items"),
        )
        self.write("scripts/mutation-pr-detect.sh", "changed\n")
        self.commit("edit")
        red = self.cli(self.base, self.rev("HEAD"), "--repo", str(self.repo))
        self.assertEqual(red.returncode, 1)
        self.assertIn(
            "uncleared item: gate gate scripts/mutation-pr-detect.sh", red.stdout
        )

    def test_bad_sha_is_red_not_green(self) -> None:
        result = self.cli("0" * 40, "1" * 40, "--repo", str(self.repo))
        self.assertEqual(result.returncode, 1)
        self.assertIn("error", result.stderr)


if __name__ == "__main__":
    unittest.main()
