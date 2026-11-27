"""R21, R22, R25, R26, R34: items for the mutation-gate-items check (Python and gate)."""

import ast
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


class RepoCase(unittest.TestCase):
    """A throwaway repo and home; the real git config is never touched."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        env = {
            "HOME": str(self.tmp / "home"),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        }
        (self.tmp / "home").mkdir()
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "master")
        self.write("README", "x\n")
        self.commit("base")
        self.base = self.rev("HEAD")

    def git(self, *args: str) -> str:
        cmd = ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args]
        result = subprocess.run(
            cmd,
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
        )
        return result.stdout.strip()

    def write(self, rel: str, text: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def rev(self, ref: str) -> str:
        return self.git("rev-parse", ref)

    def commit(self, *messages: str) -> str:
        self.git("add", "-A")
        args = ["commit", "-q", "--allow-empty"]
        for message in messages:
            args += ["-m", message]
        self.git(*args)
        return self.rev("HEAD")


class ItemsCase(RepoCase):
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
        self.commit("add fixtures")
        self.base = self.rev("HEAD")

    def items(self, kind: str | None = None) -> list[Any]:
        found = mgi.collect(self.repo, self.base, self.rev("HEAD"))
        return [i for i in found if kind is None or i.kind == kind]

    def run_cli(self) -> tuple[int, str]:
        return mgi.run(self.repo, self.base, "HEAD")

    def eq_entry(
        self,
        fragment: str,
        mutant: tuple[str, str],
        col: int,
        variant: int | None,
        directory: str = "sq",
    ) -> str:
        module = self.repo / directory / f"{directory.replace('-', '_')}.py"
        lines = module.read_text().split("\n")
        index = next(i for i, text in enumerate(lines) if fragment in text)
        above = next(
            lines[j].strip() for j in range(index - 1, -1, -1) if lines[j].strip()
        )
        operator, function = mutant
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
            "k = 1", ("core/NumberReplacer", "generate_squares"), 8, variant
        )

    def and_entry(self, col: int) -> str:
        return self.eq_entry(
            "LARGE_RUN_THRESHOLD is not None and",
            ("core/ReplaceAndWithOr", "refuse_large_run"),
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
                "0",
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
        self.assertEqual(item.key[-1], "1")

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
        self.assertEqual(item.key[-1], "1")

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

    def test_required_checks_mirror_and_ci_gate_are_gate_items(self) -> None:
        self.write(".github/required-status-checks", "secret-scan\n")
        self.write("scripts/ci-gate.sh", "#!/bin/sh\nexit 0\n")
        self.write("scripts/ci-other.sh", "#!/bin/sh\nexit 0\n")
        self.commit("drop a required check")
        keys = sorted(i.key for i in self.items("gate"))
        self.assertEqual(
            keys,
            [
                (
                    ".github/required-status-checks",
                    self.blob(".github/required-status-checks"),
                ),
                ("scripts/ci-gate.sh", self.blob("scripts/ci-gate.sh")),
            ],
        )

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
        self.write("Makefile", MAKEFILE.replace("echo run", "echo run now"))
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
    def test_variables_are_hashed_whether_or_not_a_recipe_uses_them(self) -> None:
        text = "A = $(B)\nB = deep \\\n  value\nC = unused\nmutants-x:\n\tuse $(A)\n"
        out = mgi.make_scope_text(text)
        for word in ("deep", "value", "unused", "use $(A)"):
            self.assertIn(word, out)

    def test_unreachable_recipe_is_left_out_and_reachable_one_kept(self) -> None:
        out = mgi.make_scope_text("mutants: dep\n\tgo\ndep:\n\tdepcmd\nrun:\n\tother\n")
        self.assertIn("depcmd", out)
        self.assertNotIn("other", out)

    def test_sub_make_call_reaches_its_target(self) -> None:
        out = mgi.make_scope_text("mutants:\n\t$(MAKE) -s inner\ninner:\n\tdeep\n")
        self.assertIn("deep", out)

    def test_define_body_lines_are_never_recipes(self) -> None:
        out = mgi.make_scope_text("define BODY\n\techo in\nendef\nrun:\n\tx\n")
        self.assertIn("echo in", out)

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


class RunTest(ItemsCase):
    """R26: any item is red, every item is listed, and nothing clears it in band."""

    def change_timeout(self, value: str) -> None:
        path = self.repo / "sq" / "cosmic-ray.toml"
        text = path.read_text()
        self.write(
            "sq/cosmic-ray.toml",
            re.sub(r"timeout = [0-9.]+", f"timeout = {value}", text),
        )
        self.commit(f"timeout {value}")

    def test_red_output_lists_the_item_and_names_the_operator(self) -> None:
        self.change_timeout("120.0")
        code, text = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(
            text.split("\n"),
            [
                "uncleared item: sq python-config sq | cosmic-ray.timeout | 120.0",
                mgi.OPERATOR_LINE,
            ],
        )

    def test_every_item_is_listed(self) -> None:
        self.change_timeout("120.0")
        self.write("scripts/mutation-pr-detect.sh", "x\n")
        self.commit("gate change")
        _, text = self.run_cli()
        self.assertEqual(text.count("uncleared item: "), 2)
        self.assertIn("uncleared item: gate gate scripts/mutation-pr-detect.sh", text)

    def test_no_items_is_green(self) -> None:
        self.write("README", "z\n")
        self.commit("docs")
        self.assertEqual(self.run_cli(), (0, "mutation-gate-items: no uncleared items"))

    def test_output_has_no_clearance_command(self) -> None:
        self.change_timeout("120.0")
        _, text = self.run_cli()
        self.assertNotIn("commit --allow-empty", text)


class ItemsGateReminderTest(ItemsCase):
    """R4, R5, N1: an items-gate file item gets the draft-and-label hold line."""

    def test_each_items_gate_file_adds_the_hold_line_before_operator_line(
        self,
    ) -> None:
        paths = (
            "scripts/mutation_gate_items.py",
            "scripts/mutation-gate-items.sh",
            ".github/workflows/mutation-gate-items.yml",
            "scripts/cosmic_ray_prune.py",
        )
        for path in paths:
            with self.subTest(path=path):
                self.git("reset", "-q", "--hard", self.base)
                self.write(path, "x\n")
                self.commit(f"change {path}")
                code, text = self.run_cli()
                lines = text.split("\n")
                self.assertEqual(code, 1)
                self.assertEqual(text.count(mgi.ITEMS_GATE_LINE), 1)
                self.assertEqual(lines[-1], mgi.OPERATOR_LINE)
                self.assertEqual(lines[-2], mgi.ITEMS_GATE_LINE)
                self.assertTrue(lines[-3].startswith("uncleared item: "))

    def test_other_gate_file_has_no_hold_line(self) -> None:
        self.write(
            ".github/workflows/mutation-pr.yml",
            MUTATION_PR.format(sha=SHA_OLD, version="v1").replace("tool: x", "tool: y"),
        )
        self.commit("change tool")
        code, text = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn(
            "uncleared item: gate gate .github/workflows/mutation-pr.yml", text
        )
        self.assertNotIn(mgi.ITEMS_GATE_LINE, text)

    def test_non_gate_item_has_no_hold_line(self) -> None:
        path = self.repo / "sq" / "cosmic-ray.toml"
        self.write(
            "sq/cosmic-ray.toml",
            re.sub(r"timeout = [0-9.]+", "timeout = 120.0", path.read_text()),
        )
        self.commit("timeout")
        code, text = self.run_cli()
        self.assertEqual(code, 1)
        self.assertIn("uncleared item: sq python-config", text)
        self.assertNotIn(mgi.ITEMS_GATE_LINE, text)

    def test_no_items_stays_green(self) -> None:
        self.write("README", "z\n")
        self.commit("docs")
        self.assertEqual(self.run_cli(), (0, "mutation-gate-items: no uncleared items"))

    def test_paths_cover_every_load_sibling_target(self) -> None:
        tree = ast.parse((ROOT / "scripts" / "mutation_gate_items.py").read_text())
        names: set[str] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_load_sibling"
            ):
                self.assertEqual(len(node.args), 1)
                self.assertEqual(node.keywords, [])
                arg = node.args[0]
                self.assertIsInstance(arg, ast.Constant)
                assert isinstance(arg, ast.Constant)
                self.assertIsInstance(arg.value, str)
                names.add(str(arg.value))
        self.assertEqual(
            set(mgi.ITEMS_GATE_PATHS),
            {
                "scripts/mutation_gate_items.py",
                "scripts/mutation-gate-items.sh",
                ".github/workflows/mutation-gate-items.yml",
            }
            | {f"scripts/{n}.py" for n in names},
        )


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

    def test_pr_flag_is_gone(self) -> None:
        result = self.cli(self.base, "HEAD", "--pr", "7", "--repo", str(self.repo))
        self.assertEqual(result.returncode, 2)

    def test_bad_sha_is_red_not_green(self) -> None:
        result = self.cli("0" * 40, "1" * 40, "--repo", str(self.repo))
        self.assertEqual(result.returncode, 3)
        self.assertIn("mutation-gate-items: infra error: RuntimeError:", result.stderr)


class ModesTest(ItemsCase):
    """Only regular blobs count: git show of a symlink is its target text (N4)."""

    def link(self, rel: str, target: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
        os.symlink(target, path)

    def test_symlinked_module_with_a_new_entry_is_an_item(self) -> None:
        self.write("sq/sq_real.py", (self.repo / "sq" / "sq.py").read_text())
        entry = self.number_entry(0)
        self.link("sq/sq.py", "sq_real.py")
        self.write("sq/mutants-equivalent.toml", entry)
        self.commit("symlink module and new entry")
        (item,) = self.items("python-equivalent")
        self.assertEqual(item.key[:2], ("sq", "module-not-regular"))

    def test_missing_module_with_entries_is_an_item(self) -> None:
        entry = self.number_entry(0)
        (self.repo / "sq" / "sq.py").unlink()
        self.write("sq/mutants-equivalent.toml", entry)
        self.commit("drop module and add entry")
        (item,) = self.items("python-equivalent")
        self.assertEqual(item.key, ("sq", "module-not-regular", mgi.DELETED))

    def test_symlinked_equivalents_toml_is_an_item(self) -> None:
        self.write("sq/real.toml", self.number_entry(0))
        self.link("sq/mutants-equivalent.toml", "real.toml")
        self.commit("symlink toml")
        (item,) = self.items("python-equivalent")
        self.assertEqual(item.key[:2], ("sq", "toml-not-regular"))

    def test_symlinked_cosmic_ray_toml_is_an_item(self) -> None:
        self.write("sq/real.toml", "[cosmic-ray]\n")
        self.link("sq/cosmic-ray.toml", "real.toml")
        self.commit("symlink config")
        (item,) = self.items("python-config")
        self.assertEqual(item.key[:2], ("sq", "config-not-regular"))

    def test_materialise_tree_writes_regular_files_as_bytes(self) -> None:
        self.write("crate/src/a.rs", "fn a() {}\n")
        (self.repo / "crate" / "data.bin").write_bytes(b"\xff\x00\xfe")
        self.commit("crate")
        ctx = mgi.Context(self.repo, self.base, "HEAD", [], self.tmp / "scr")
        root = ctx.materialise_tree("HEAD", "crate", self.tmp / "scr")
        self.assertEqual(root, self.tmp / "scr" / "crate")
        self.assertEqual((root / "src" / "a.rs").read_text(), "fn a() {}\n")
        self.assertEqual((root / "data.bin").read_bytes(), b"\xff\x00\xfe")

    def test_materialise_tree_refuses_a_symlink(self) -> None:
        self.write("crate/src/a.rs", "fn a() {}\n")
        self.link("crate/src/b.rs", "a.rs")
        self.commit("crate with link")
        ctx = mgi.Context(self.repo, self.base, "HEAD", [], self.tmp / "scr")
        with self.assertRaises(mgi.NotRegularError):
            ctx.materialise_tree("HEAD", "crate", self.tmp / "scr")


class MergeBaseTest(ItemsCase):
    def test_master_moving_after_the_branch_point_is_not_an_item(self) -> None:
        self.git("checkout", "-q", "-b", "pr")
        self.write("README", "pr\n")
        self.commit("pr work")
        self.git("checkout", "-q", "master")
        self.write("scripts/mutation-pr-detect.sh", "moved on master\n")
        self.commit("master moves")
        code, text = mgi.run(self.repo, self.rev("master"), "pr")
        self.assertEqual((code, text), (0, "mutation-gate-items: no uncleared items"))

    def test_unknown_commit_is_an_error_not_green(self) -> None:
        with self.assertRaises(RuntimeError):
            mgi.run(self.repo, "0" * 40, "HEAD")


class MakefileScopeTest(ItemsCase):
    """Everything outside a recipe is hashed; recipes only when `mutants*` reaches them."""

    PRELUDE = ".PHONY: mutants lint run\nmutants: lint\n\ttool\nlint:\n\techo lint\nrun:\n\techo run\n"

    def change(self, old: str, new: str) -> list[Any]:
        self.write("Makefile", old + self.PRELUDE)
        self.commit("old makefile")
        self.base = self.rev("HEAD")
        self.write("Makefile", new + self.PRELUDE)
        self.commit("new makefile")
        return self.items("gate")

    def test_prerequisite_recipe_change_is_an_item(self) -> None:
        old = self.PRELUDE
        self.write("Makefile", old)
        self.commit("old")
        self.base = self.rev("HEAD")
        self.write("Makefile", old.replace("echo lint", "echo changed"))
        self.commit("new")
        self.assertEqual(len(self.items("gate")), 1)

    def test_unrelated_target_recipe_is_not_an_item(self) -> None:
        self.write("Makefile", self.PRELUDE)
        self.commit("old")
        self.base = self.rev("HEAD")
        self.write("Makefile", self.PRELUDE.replace("echo run", "echo other"))
        self.commit("new")
        self.assertEqual(self.items("gate"), [])

    def test_conditional_selector_change_is_an_item(self) -> None:
        cond = "ifeq ($(MODE),{m})\nX = 1\nendif\n"
        self.assertEqual(len(self.change(cond.format(m="a"), cond.format(m="b"))), 1)

    def test_shell_change_is_an_item(self) -> None:
        self.assertEqual(
            len(self.change("SHELL = /bin/sh\n", "SHELL = /bin/bash\n")), 1
        )

    def test_export_change_is_an_item(self) -> None:
        old, new = "export CELL_LABEL = a\n", "export CELL_LABEL = b\n"
        self.assertEqual(len(self.change(old, new)), 1)

    def test_export_line_added_is_an_item(self) -> None:
        self.assertEqual(len(self.change("A = 1\n", "A = 1\nexport CELL_LABEL\n")), 1)

    def test_conditional_assignment_change_is_an_item(self) -> None:
        self.assertEqual(len(self.change("CELL_LABEL ?= a\n", "CELL_LABEL ?= b\n")), 1)

    def test_define_body_change_is_an_item(self) -> None:
        define = "define BODY\n\techo {x}\nendef\n"
        self.assertEqual(
            len(self.change(define.format(x="a"), define.format(x="b"))), 1
        )

    def test_added_include_is_an_item(self) -> None:
        self.assertEqual(len(self.change("A = 1\n", "A = 1\ninclude extra.mk\n")), 1)

    def test_pattern_rule_recipe_change_is_an_item(self) -> None:
        rule = "%.o: %.c\n\tcc {x}\n"
        self.assertEqual(len(self.change(rule.format(x="a"), rule.format(x="b"))), 1)

    def test_comment_only_change_is_not_an_item(self) -> None:
        self.assertEqual(self.change("# one\n", "# two\n"), [])

    def test_transitive_prerequisite_recipe_is_reached(self) -> None:
        chain = "mutants-a: mid\n\tx\nmid: leaf\n\ty\nleaf:\n\t{x}\n"
        self.assertEqual(len(self.change(chain.format(x="1"), chain.format(x="2"))), 1)


class WorkflowNameTest(ItemsCase):
    def set_base_other(self, text: str) -> None:
        self.write(".github/workflows/other.yml", text)
        self.commit("other at base")
        self.base = self.rev("HEAD")

    def test_expression_name_counts_as_declaring(self) -> None:
        self.write(
            ".github/workflows/other.yml",
            "name: other\njobs:\n  a:\n    name: ${{ matrix.n }}\n    steps: []\n",
        )
        self.commit("expression name")
        self.assertEqual(len(self.items("gate")), 1)

    def test_deleting_a_job_that_declared_a_gate_name_is_an_item(self) -> None:
        self.set_base_other("name: other\njobs:\n  mutation-pr:\n    steps: []\n")
        self.write(
            ".github/workflows/other.yml", "name: other\njobs:\n  a:\n    steps: []\n"
        )
        self.commit("delete the job")
        self.assertEqual(len(self.items("gate")), 1)

    def test_deleting_the_workflow_file_is_an_item(self) -> None:
        self.set_base_other("name: other\njobs:\n  secret-scan:\n    steps: []\n")
        (self.repo / ".github/workflows/other.yml").unlink()
        self.commit("delete the file")
        (item,) = self.items("gate")
        self.assertEqual(item.key, (".github/workflows/other.yml", mgi.DELETED))

    def test_yaml_error_is_an_item(self) -> None:
        self.write(".github/workflows/other.yml", "name: [unclosed\njobs: {\n")
        self.commit("broken yaml")
        self.assertEqual(len(self.items("gate")), 1)

    def test_indentation_only_change_of_a_uses_line_is_an_item(self) -> None:
        text = MUTATION_PR.format(sha=SHA_OLD, version="v1").replace(
            "      - uses", "    - uses"
        )
        self.write(".github/workflows/mutation-pr.yml", text)
        self.commit("reindent")
        self.assertEqual(len(self.items("gate")), 1)

    def test_comment_glued_to_the_sha_is_an_item(self) -> None:
        text = (
            MUTATION_PR.format(sha=SHA_NEW, version="v2")
            .replace("# v2", "#v2")
            .replace(f"{SHA_NEW} #", f"{SHA_NEW}#")
        )
        self.write(".github/workflows/mutation-pr.yml", text)
        self.commit("glued comment")
        self.assertEqual(len(self.items("gate")), 1)


class ErrorHandlingTest(ItemsCase):
    def test_unexpected_exception_is_an_infra_error_exit_3(self) -> None:
        err = io.StringIO()
        with (
            mock.patch.object(mgi, "collect", side_effect=ValueError("boom")),
            contextlib.redirect_stderr(err),
        ):
            code = mgi.main([self.base, "HEAD", "--repo", str(self.repo)])
        self.assertEqual(code, 3)
        self.assertEqual(
            err.getvalue().strip(), "mutation-gate-items: infra error: ValueError: boom"
        )

    def test_binary_cosmic_ray_toml_is_an_unparseable_item(self) -> None:
        (self.repo / "sq" / "cosmic-ray.toml").write_bytes(b"\xff\xfe\x00[\x80")
        self.commit("binary config")
        (item,) = self.items("python-config")
        self.assertEqual(item.key[:2], ("sq", "unparseable"))

    def test_show_returns_text_for_non_utf8_bytes(self) -> None:
        (self.repo / "bin.dat").write_bytes(b"\xff\xfe")
        self.commit("binary")
        ctx = mgi.Context(self.repo, self.base, "HEAD", [], self.tmp)
        self.assertIsInstance(ctx.show("HEAD", "bin.dat"), str)

    def test_failing_git_diff_is_an_infra_error_exit_3(self) -> None:
        real_git = mgi._git

        def fake_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
            if args[0] == "diff":
                return subprocess.CompletedProcess(args, 128, "", "fatal: bad object\n")
            return real_git(repo, args)

        err = io.StringIO()
        with (
            mock.patch.object(mgi, "_git", side_effect=fake_git),
            contextlib.redirect_stderr(err),
        ):
            code = mgi.main([self.base, "HEAD", "--repo", str(self.repo)])
        self.assertEqual(code, 3)
        self.assertIn("git diff", err.getvalue())
        self.assertIn("infra error: RuntimeError", err.getvalue())


class WriteUnderTest(unittest.TestCase):
    def test_path_escaping_the_root_is_refused_and_nothing_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            with self.assertRaises(RuntimeError):
                mgi._write_under(root, "../x", b"")
            self.assertFalse((Path(tmp) / "x").exists())


class NonAsciiDirTest(ItemsCase):
    def test_astral_plane_dir_name_still_resolves_entries(self) -> None:
        directory = "sq\U0001f600"
        self.write(
            f"{directory}/{directory}.py", (self.repo / "sq" / "sq.py").read_text()
        )
        self.write(
            f"{directory}/cosmic-ray.toml",
            (self.repo / "sq" / "cosmic-ray.toml").read_text(),
        )
        self.write(
            f"{directory}/mutants-equivalent.toml",
            self.eq_entry(
                "k = 1", ("core/NumberReplacer", "generate_squares"), 8, 0, directory
            ),
        )
        self.commit("non-ascii dir")
        found = self.items("python-equivalent")
        self.assertEqual([i.key[0] for i in found], [directory])


class OrdinalTest(ItemsCase):
    def test_unrelated_literal_added_earlier_does_not_change_the_key(self) -> None:
        self.write("sq/mutants-equivalent.toml", self.number_entry(1))
        self.commit("entry")
        before = self.items("python-equivalent")
        module = (self.repo / "sq" / "sq.py").read_text()
        self.write("sq/sq.py", "_UNRELATED = 5\n" + module)
        self.commit("unrelated literal earlier in the module")
        self.assertEqual(self.items("python-equivalent"), before)
        self.assertEqual(before[0].key[-1], "1")


class N4Test(ItemsCase):
    def test_module_import_side_effect_never_runs(self) -> None:
        marker = self.tmp / "imported"
        module = (self.repo / "sq" / "sq.py").read_text()
        payload = f"from pathlib import Path\nPath({str(marker)!r}).write_text('x')\n"
        self.write("sq/sq.py", payload + module)
        self.write("sq/mutants-equivalent.toml", self.number_entry(0))
        self.commit("module with import side effect")
        self.assertEqual(len(self.items("python-equivalent")), 1)
        self.assertFalse(marker.exists())

    def captured_env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = {"PATH": ".:rel:/usr/bin:", "SECRET_X": "1", "GIT_DIR": "/nope"}
        with (
            mock.patch.dict(os.environ, env),
            mock.patch.object(mgi.subprocess, "run") as run,
        ):
            mgi.run_tool(["true"], extra)
        return run.call_args.kwargs["env"]

    def test_env_is_scrubbed_not_inherited(self) -> None:
        env = self.captured_env()
        self.assertEqual(env["PATH"], "/usr/bin")
        self.assertEqual(env["PYTHONSAFEPATH"], "1")
        self.assertEqual(
            set(env),
            {
                "PATH",
                "HOME",
                "LANG",
                "PYTHONDONTWRITEBYTECODE",
                "PYTHONSAFEPATH",
                "PYTHONNOUSERSITE",
            },
        )

    def test_callers_can_pass_rustup_and_cargo_variables(self) -> None:
        extra = {"RUSTUP_HOME": "/r", "RUSTUP_TOOLCHAIN": "1.90", "CARGO_HOME": "/c"}
        env = self.captured_env(extra)
        for key, value in extra.items():
            self.assertEqual(env[key], value)
        self.assertNotIn("SECRET_X", env)

    def test_each_collector_gets_its_own_scratch_directory(self) -> None:
        seen: dict[str, Path] = {}

        def spy(name: str) -> Any:
            def collector(ctx: Any) -> list[Any]:
                seen[name] = ctx.scratch
                return []

            return collector

        with mock.patch.dict(mgi._COLLECTORS, clear=False):
            mgi.register("spy-a", spy("a"))
            mgi.register("spy-b", spy("b"))
            self.items()
        self.assertNotEqual(seen["a"], seen["b"])
        self.assertEqual(seen["a"].parent, seen["b"].parent)


if __name__ == "__main__":
    unittest.main()
