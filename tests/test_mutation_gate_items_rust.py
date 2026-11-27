"""R21, R23, R34, N4: Rust exclusion items of the mutation-gate-items check.

Every fixture is a copy of the tracked `amicable/amicable-rs` sources inside a throwaway
git repo; nothing here builds a crate. `cargo mutants --list` is the only cargo call the
script makes, and the planted-config tests prove a hostile PR tree leaves no marker file.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
CRATE = "amicable/amicable-rs"
# Captured before RepoCase redirects HOME into its temp dir.
REAL_CARGO_HOME = os.environ.get("CARGO_HOME") or str(Path.home() / ".cargo")
REAL_RUSTUP_HOME = os.environ.get("RUSTUP_HOME") or str(Path.home() / ".rustup")
CARGO_MUTANTS = Path(REAL_CARGO_HOME) / "bin" / "cargo-mutants"
SKIP_REASON = f"cargo-mutants not found at {CARGO_MUTANTS}"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mgi: Any = _load(
    "mutation_gate_items_rust_under_test", SCRIPTS / "mutation_gate_items.py"
)
_helper: Any = _load(
    "mutation_gate_clearance_rust_helper",
    ROOT / "tests" / "test_mutation_gate_clearance.py",
)
EXCLUDE_VEC = (
    'exclude_re = [\n    "src/lib\\\\.rs:3:25: replace / with \\\\*",\n'
    '    "replace proper_divisor_sum_sieve -> Vec<u32> with vec!\\\\[\\\\]",\n]\n'
)


def _tracked_crate_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", CRATE],
        capture_output=True,
        text=True,
        check=True,
        stdin=subprocess.DEVNULL,
    )
    return [p for p in out.stdout.split("\0") if p]


def _require_cargo_mutants() -> None:
    if CARGO_MUTANTS.exists():
        return
    if os.environ.get("CI"):
        raise AssertionError(SKIP_REASON)
    print(f"SKIP test_mutation_gate_items_rust: {SKIP_REASON}", file=sys.stderr)
    raise unittest.SkipTest(SKIP_REASON)


class RustCase(_helper.RepoCase):
    """A repo whose base commit holds a copy of amicable-rs."""

    def setUp(self) -> None:
        _require_cargo_mutants()
        super().setUp()
        os.environ["CARGO_HOME"] = REAL_CARGO_HOME
        os.environ["RUSTUP_HOME"] = REAL_RUSTUP_HOME
        for rel in _tracked_crate_files():
            dest = self.repo / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dest)
        self.commit("add crate")
        self.base = self.rev("HEAD")

    def crate_path(self, rel: str) -> Path:
        return self.repo / CRATE / rel

    def edit(self, rel: str, text: str) -> None:
        self.write(f"{CRATE}/{rel}", text)

    def items(self) -> list[Any]:
        self.commit("change")
        return [
            i
            for i in mgi.collect(self.repo, self.base, self.rev("HEAD"))
            if i.kind == "rust-exclusion"
        ]


class ExclusionItemsTest(RustCase):
    def test_new_exclude_re_is_an_item_keyed_by_the_mutant(self) -> None:
        self.edit(".cargo/mutants.toml", EXCLUDE_VEC)
        found = self.items()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].target, CRATE)
        crate, file, function, genre, description = found[0].key[:5]
        self.assertEqual(
            (crate, file, function, genre),
            (CRATE, "src/lib.rs", "proper_divisor_sum_sieve", "FnValue"),
        )
        self.assertEqual(
            description, "replace proper_divisor_sum_sieve -> Vec<u32> with vec![]"
        )
        self.assertEqual(found[0].key[-1], "0")

    def test_unchanged_exclusions_are_not_items(self) -> None:
        self.edit("src/main.rs", self.crate_path("src/main.rs").read_text() + "\n")
        self.assertEqual(self.items(), [])

    def test_pure_line_shift_is_not_an_item(self) -> None:
        lib = self.crate_path("src/lib.rs").read_text()
        self.edit("src/lib.rs", "// shifted down one line\n" + lib)
        config = self.crate_path(".cargo/mutants.toml").read_text()
        self.edit(
            ".cargo/mutants.toml",
            config.replace("src/lib\\\\.rs:3:25", "src/lib\\\\.rs:4:25"),
        )
        self.assertEqual(self.items(), [])

    def test_exclusion_retargeted_onto_another_operator_is_an_item(self) -> None:
        config = self.crate_path(".cargo/mutants.toml").read_text()
        pattern = '"src/lib\\\\.rs:3:25: replace / with \\\\*"'
        self.assertIn(pattern, config)
        self.edit(
            ".cargo/mutants.toml",
            config.replace(pattern, '"replace \\\\+= with \\\\*="'),
        )
        found = self.items()
        self.assertEqual(
            {i.key[4] for i in found},
            {"replace += with *= in proper_divisor_sum_sieve"},
        )

    def test_additional_cargo_test_args_is_an_item_keyed_by_its_value(self) -> None:
        config = self.crate_path(".cargo/mutants.toml").read_text()
        self.edit(
            ".cargo/mutants.toml", config + 'additional_cargo_test_args = ["--quiet"]\n'
        )
        self.assertEqual(
            [i.key for i in self.items()],
            [(CRATE, "additional_cargo_test_args", json.dumps(["--quiet"]))],
        )

    def test_changed_value_of_a_key_is_a_new_item(self) -> None:
        config = self.crate_path(".cargo/mutants.toml").read_text()
        self.edit(".cargo/mutants.toml", config + "minimum_test_timeout = 10.0\n")
        first = self.items()
        self.edit(".cargo/mutants.toml", config + "minimum_test_timeout = 99.0\n")
        second = self.items()
        self.assertNotEqual(first[0].key, second[0].key)
        self.assertEqual(second[0].key, (CRATE, "minimum_test_timeout", "99.0"))

    def test_crate_without_changes_yields_nothing(self) -> None:
        self.write("README", "changed\n")
        self.assertEqual(self.items(), [])

    def test_symlinked_source_is_an_item_not_a_silent_pass(self) -> None:
        link = self.crate_path("src/lib.rs")
        link.unlink()
        link.symlink_to("/etc/hostname")
        found = self.items()
        self.assertEqual([i.key[1] for i in found], ["tree-not-regular"])
        self.assertEqual(found[0].target, CRATE)

    def test_unlistable_head_is_an_item_keyed_by_the_crate_tree(self) -> None:
        self.edit("Cargo.toml", "this is not toml [\n")
        found = self.items()
        self.assertEqual([i.key[1] for i in found], ["list-failed"])
        self.assertEqual(found[0].key[2], self.git("rev-parse", f"HEAD:{CRATE}"))

    def test_marker_changes_when_any_crate_file_changes(self) -> None:
        self.edit("Cargo.toml", "this is not toml [\n")
        first = self.items()
        self.edit("src/main.rs", self.crate_path("src/main.rs").read_text() + "\n")
        self.assertNotEqual(first[0].key, self.items()[0].key)

    def test_config_items_are_still_raised_when_the_head_is_unlistable(self) -> None:
        self.edit("Cargo.toml", "this is not toml [\n")
        config = self.crate_path(".cargo/mutants.toml").read_text()
        self.edit(".cargo/mutants.toml", config + "minimum_test_timeout = 99.0\n")
        keys = {i.key[1:] for i in self.items()}
        self.assertEqual(
            keys,
            {
                ("list-failed", self.git("rev-parse", f"HEAD:{CRATE}")),
                ("minimum_test_timeout", "99.0"),
            },
        )

    def test_unlistable_base_makes_every_head_exclusion_an_item(self) -> None:
        self.edit("Cargo.toml", "this is not toml [\n")
        self.commit("break base")
        self.base = self.rev("HEAD")
        shutil.copyfile(ROOT / CRATE / "Cargo.toml", self.crate_path("Cargo.toml"))
        found = self.items()
        self.assertEqual(
            [i.key[4] for i in found], ["replace / with * in proper_divisor_sum_sieve"]
        )

    def test_same_description_twice_on_one_line_gets_two_ordinals(self) -> None:
        lib = self.crate_path("src/lib.rs").read_text()
        self.edit(
            "src/lib.rs",
            lib + "\npub fn dup(a: u32, b: u32, c: u32) -> u32 {\n    a + b + c\n}\n",
        )
        self.commit("add dup")
        self.base = self.rev("HEAD")
        config = self.crate_path(".cargo/mutants.toml").read_text()
        self.edit(
            ".cargo/mutants.toml",
            config.replace("]\n", '    "replace \\\\+ with - in dup",\n]\n'),
        )
        found = self.items()
        self.assertEqual(sorted(i.key[-1] for i in found), ["0", "1"])
        self.assertEqual({i.key[2] for i in found}, {"dup"})

    def test_new_crate_lists_its_exclusions_against_an_empty_base(self) -> None:
        self.git("rm", "-r", "-q", CRATE)
        self.commit("remove crate")
        self.base = self.rev("HEAD")
        for rel in _tracked_crate_files():
            dest = self.repo / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, dest)
        found = self.items()
        self.assertEqual(len(found), 1)
        self.assertEqual(
            found[0].key[4], "replace / with * in proper_divisor_sum_sieve"
        )


class PlantedConfigTest(RustCase):
    """N4: a PR tree must not make the listing run any of its code (R21, R34)."""

    def marker(self) -> Path:
        return self.tmp / "marker"

    def plant_script(self, name: str) -> Path:
        script = self.tmp / name
        script.write_text(f'#!/bin/sh\ntouch "{self.marker()}"\nexec "$@"\n')
        script.chmod(0o755)
        return script

    def env_for_control(self) -> dict[str, str]:
        return {
            "PATH": f"{REAL_CARGO_HOME}/bin:/usr/bin:/bin",
            "HOME": str(self.tmp / "home"),
            "RUSTUP_HOME": REAL_RUSTUP_HOME,
            "CARGO_HOME": str(self.tmp / "control-cargo-home"),
            "CARGO_NET_OFFLINE": "true",
        }

    def run_in_tree(self, args: list[str], extra: dict[str, str]) -> None:
        subprocess.run(
            args,
            cwd=self.repo / CRATE,
            env={**self.env_for_control(), **extra},
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )

    def test_rustc_wrapper_leaves_no_marker(self) -> None:
        wrapper = self.plant_script("wrap.sh")
        self.edit(".cargo/config.toml", f'[build]\nrustc-wrapper = "{wrapper}"\n')
        self.run_in_tree(
            ["cargo", "metadata", "--format-version", "1"],
            {"RUSTUP_TOOLCHAIN": "stable"},
        )
        self.assertTrue(self.marker().exists(), "control: plain cargo metadata runs it")
        self.marker().unlink()
        self.items()
        self.assertFalse(self.marker().exists())

    def test_absolute_path_toolchain_leaves_no_marker(self) -> None:
        fake = self.tmp / "fake-toolchain"
        (fake / "bin").mkdir(parents=True)
        script = fake / "bin" / "cargo"
        script.write_text(f'#!/bin/sh\ntouch "{self.marker()}"\nexit 1\n')
        script.chmod(0o755)
        self.edit("rust-toolchain.toml", f'[toolchain]\npath = "{fake}"\n')
        self.run_in_tree(["cargo", "--version"], {})
        self.assertTrue(self.marker().exists(), "control: the pinned path is followed")
        self.marker().unlink()
        self.items()
        self.assertFalse(self.marker().exists())


FX_CRATE = "fx/fx-rs"


class AliasFixtureTest(unittest.TestCase):
    """A dependency-free crate whose `[alias] mutants` runs a marker-writing binary.

    The positive control runs `cargo mutants` with cwd = the tree and proves the marker
    is writable that way; only then does the absence under the collector mean something.
    """

    def setUp(self) -> None:
        _require_cargo_mutants()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.marker = self.tmp / "marker"
        env = {"HOME": str(self.tmp / "home"), "GIT_CONFIG_GLOBAL": "/dev/null"}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ["CARGO_HOME"] = REAL_CARGO_HOME
        os.environ["RUSTUP_HOME"] = REAL_RUSTUP_HOME
        self.repo = self.tmp / "repo"
        crate = self.repo / FX_CRATE
        (crate / "src" / "bin").mkdir(parents=True)
        (crate / ".cargo").mkdir()
        (crate / "Cargo.toml").write_text(
            '[package]\nname = "fx"\nversion = "0.1.0"\nedition = "2024"\n'
        )
        (crate / "src" / "lib.rs").write_text(
            "pub fn f(a: u32) -> u32 {\n    a + 1\n}\n"
        )
        (crate / "src" / "bin" / "evil.rs").write_text(
            f'fn main() {{ std::fs::write("{self.marker}", "x").unwrap(); }}\n'
        )
        self.git("init", "-q", "-b", "master")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD")
        (crate / ".cargo" / "config.toml").write_text(
            '[alias]\nmutants = ["run", "--bin", "evil", "--"]\n'
        )
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "alias")

    def git(self, *args: str) -> str:
        done = subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                *args,
            ],
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
        )
        return done.stdout.strip()

    def test_alias_runs_under_cwd_equal_to_the_tree(self) -> None:
        env = {
            "PATH": f"{REAL_CARGO_HOME}/bin:/usr/bin:/bin",
            "HOME": str(self.tmp / "home"),
            "RUSTUP_HOME": REAL_RUSTUP_HOME,
            "CARGO_HOME": str(self.tmp / "control-cargo-home"),
            "RUSTUP_TOOLCHAIN": "stable",
            "CARGO_NET_OFFLINE": "true",
        }
        subprocess.run(
            ["cargo", "mutants", "--list", "--json", "-d", "."],
            cwd=self.repo / FX_CRATE,
            env=env,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=False,
        )
        self.assertTrue(self.marker.exists(), "control: the alias runs the binary")

    def test_collector_never_runs_the_alias(self) -> None:
        found = mgi.collect(self.repo, self.base, self.git("rev-parse", "HEAD"))
        self.assertFalse(self.marker.exists())
        self.assertEqual([i for i in found if i.key[1] == "list-failed"], [])


class MaterialisationTest(RustCase):
    """N4: cargo config and toolchain files never reach the scratch tree."""

    def listed_trees(self) -> list[list[Path]]:
        trees: list[list[Path]] = []
        real = mgi._list_mutants

        def spy(tree: Path, no_config: bool) -> Any:
            trees.append(
                sorted(p.relative_to(tree) for p in tree.rglob("*") if p.is_file())
            )
            return real(tree, no_config)

        with mock.patch.object(mgi, "_list_mutants", spy):
            self.commit("change")
            mgi.collect(self.repo, self.base, self.rev("HEAD"))
        return trees

    def test_scratch_trees_hold_no_cargo_config_or_toolchain_file(self) -> None:
        self.edit(".cargo/config.toml", '[alias]\nmutants = ["run"]\n')
        self.edit(".cargo/config", '[alias]\nmutants = ["run"]\n')
        self.edit("rust-toolchain.toml", '[toolchain]\nchannel = "stable"\n')
        self.edit("rust-toolchain", "stable\n")
        self.edit("src/lib.rs", self.crate_path("src/lib.rs").read_text() + "\n")
        trees = self.listed_trees()
        self.assertTrue(trees)
        for files in trees:
            names = {str(f) for f in files}
            self.assertIn(".cargo/mutants.toml", names)
            self.assertIn("Cargo.toml", names)
            self.assertEqual(
                {n for n in names if "config" in n.split("/")[-1] and ".cargo" in n},
                set(),
            )
            self.assertEqual(
                {n for n in names if n.startswith("rust-toolchain")}, set()
            )


class InvocationTest(unittest.TestCase):
    """The R21 invocation: pinned toolchain, empty CARGO_HOME, cwd outside the tree."""

    def listing_call(self) -> tuple[list[str], dict[str, str]]:
        _require_cargo_mutants()
        seen: dict[str, Any] = {}

        def fake(args: list[str], extra_env: dict[str, str] | None = None) -> Any:
            seen["args"], seen["env"] = args, extra_env or {}
            return subprocess.CompletedProcess(args, 0, "[]", "")

        with (
            tempfile.TemporaryDirectory() as tree,
            mock.patch.dict(os.environ, {"CARGO_HOME": REAL_CARGO_HOME}),
            mock.patch.object(mgi, "run_tool", fake),
        ):
            mgi._list_mutants(Path(tree), True)
        return seen["args"], seen["env"]

    def test_listing_uses_pinned_toolchain_and_a_fresh_cargo_home(self) -> None:
        _, env = self.listing_call()
        self.assertEqual(env["RUSTUP_TOOLCHAIN"], "stable")
        self.assertNotEqual(env["CARGO_HOME"], REAL_CARGO_HOME)
        self.assertEqual(env["CARGO_NET_OFFLINE"], "true")

    def test_listing_passes_the_tree_with_dash_d_and_no_config(self) -> None:
        args, _ = self.listing_call()
        self.assertEqual(
            args[1:6], ["mutants", "--list", "--json", "--no-config", "-d"]
        )

    def test_run_tool_cwd_is_never_the_last_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tree:
            done = mgi.run_tool(
                [sys.executable, "-c", "import os; print(os.getcwd())", tree]
            )
        self.assertNotEqual(Path(done.stdout.strip()).resolve(), Path(tree).resolve())

    def test_run_tool_path_drops_relative_entries(self) -> None:
        with mock.patch.dict(os.environ, {"PATH": "rel:./x::/usr/bin:/bin"}):
            self.assertEqual(mgi._safe_path_entries(), "/usr/bin:/bin")

    def test_missing_cargo_mutants_is_an_error_not_an_empty_listing(self) -> None:
        _require_cargo_mutants()
        with self.assertRaises(RuntimeError):
            mgi.cargo_tool("cargo-mutants", Path("/nonexistent-cargo-home"))

    def test_normalised_line_collapses_whitespace(self) -> None:
        self.assertEqual(mgi.normalise_line("  a \t  b  "), "a b")

    def test_description_drops_line_and_column(self) -> None:
        self.assertEqual(
            mgi.mutant_description("src/lib.rs:12:7: replace + with -"),
            "replace + with -",
        )


if __name__ == "__main__":
    unittest.main()
