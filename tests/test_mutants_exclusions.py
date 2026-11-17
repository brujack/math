"""Every `.cargo/mutants.toml` `exclude_re` entry must still match a real mutant.

An exclusion embeds a source line number, so an edit above it can leave the regex
matching nothing (stale, silently un-excluding or excluding the wrong mutant) or
make two entries claim one mutant. cargo-mutants lists the mutants it would
generate without running any, so this test compares each entry with that list.
Run by `make test-python` and by pre-push when a crate's `src/` or its
`mutants.toml` changes.

A crate's `mutants.toml` may instead hold only `additional_cargo_test_args`: that
selects which tests run and excludes no mutants, so `check_config` allows it.
descartes-rs sets it and `exclude_re` both, so it is checked like any other crate.
"""

import os
import pathlib
import re
import shutil
import subprocess
import unittest
from typing import ClassVar

import tomllib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
EXPECTED = {
    "amicable/amicable-rs",
    "descartes/descartes-rs",
    "e/e-rs",
    "factorial/factorial-rs",
    "goldbach/goldbach-rs",
    "perfect-numbers/perfect-numbers-rs",
    "pi/pi-rs",
    "prime/prime-rs",
    "twin-primes/twin-primes-rs",
}
INSTALL_HINT = "cargo install cargo-mutants --locked --version 27.1.0"


def check_exclusions(patterns: list[str], listed: list[str]) -> list[str]:
    """Return problems: an empty list, a stale entry, or a mutant claimed twice."""
    if not patterns:
        return ["exclude_re is empty"]
    problems = []
    claimed: dict[str, list[str]] = {}
    for pattern in patterns:
        hits = [line for line in listed if re.search(pattern, line)]
        if not hits:
            problems.append(f"stale entry matches no listed mutant: {pattern}")
        for line in hits:
            claimed.setdefault(line, []).append(pattern)
    for line, owners in claimed.items():
        if len(owners) > 1:
            problems.append(f"mutant matched by {len(owners)} entries: {line}")
    return problems


def check_config(config: dict) -> list[str]:
    """Return problems with one parsed `mutants.toml`.

    `exclude_re` is required, with one exception: a config whose single key is
    `additional_cargo_test_args` only selects which tests run (a crate whose
    excluded test, like descartes-rs' Python parity test, cannot run in
    cargo-mutants' crate-only copy).
    """
    if set(config) == {"additional_cargo_test_args"}:
        return []
    patterns = config.get("exclude_re")
    if not isinstance(patterns, list) or not patterns:
        return ["exclude_re must be a non-empty list"]
    return []


def exclusion_patterns(config: dict) -> list[str]:
    """The `exclude_re` list of a parsed config, empty for a test-selection-only one."""
    return config.get("exclude_re", [])


def crate_dirs() -> set[str]:
    """Crate directories (relative to the repo root) that carry a mutants.toml."""
    return {
        p.parent.parent.relative_to(REPO_ROOT).as_posix()
        for p in REPO_ROOT.glob("*/*-rs/.cargo/mutants.toml")
    }


class CheckExclusionsTest(unittest.TestCase):
    LISTED: ClassVar[list[str]] = [
        "src/lib.rs:1:1: replace a",
        "src/lib.rs:2:1: replace b",
    ]

    def test_clean_entries_pass(self) -> None:
        self.assertEqual(
            check_exclusions([r"lib\.rs:1:1", r"lib\.rs:2:1"], self.LISTED), []
        )

    def test_one_entry_may_match_several_mutants(self) -> None:
        self.assertEqual(check_exclusions([r"src/lib\.rs"], self.LISTED), [])

    def test_stale_entry_fails(self) -> None:
        problems = check_exclusions([r"lib\.rs:1:1", r"lib\.rs:99:1"], self.LISTED)
        self.assertEqual(len(problems), 1)
        self.assertIn("stale", problems[0])

    def test_shared_mutant_fails(self) -> None:
        problems = check_exclusions([r"lib\.rs:1:1", r"replace a"], self.LISTED)
        self.assertEqual(len(problems), 1)
        self.assertIn("matched by 2", problems[0])

    def test_empty_pattern_list_fails(self) -> None:
        self.assertEqual(check_exclusions([], self.LISTED), ["exclude_re is empty"])

    def test_no_listed_mutants_makes_every_entry_stale(self) -> None:
        self.assertEqual(len(check_exclusions([r"x"], [])), 1)


class CheckConfigTest(unittest.TestCase):
    def test_exclude_re_list_passes(self) -> None:
        self.assertEqual(check_config({"exclude_re": ["x"]}), [])

    def test_test_selection_only_file_passes(self) -> None:
        self.assertEqual(check_config({"additional_cargo_test_args": ["--lib"]}), [])

    def test_file_with_neither_key_fails(self) -> None:
        self.assertEqual(
            check_config({"timeout_multiplier": 2.0}),
            ["exclude_re must be a non-empty list"],
        )

    def test_empty_file_fails(self) -> None:
        self.assertEqual(check_config({}), ["exclude_re must be a non-empty list"])

    def test_empty_exclude_re_fails(self) -> None:
        self.assertEqual(
            check_config({"exclude_re": []}), ["exclude_re must be a non-empty list"]
        )

    def test_extra_key_beside_test_args_still_needs_exclude_re(self) -> None:
        config = {"additional_cargo_test_args": ["--lib"], "timeout_multiplier": 2.0}
        self.assertEqual(check_config(config), ["exclude_re must be a non-empty list"])

    def test_exclusion_patterns_of_selection_only_file_is_empty(self) -> None:
        self.assertEqual(
            exclusion_patterns({"additional_cargo_test_args": ["--lib"]}), []
        )


class MutantsExclusionsTest(unittest.TestCase):
    def test_crate_set_is_the_expected_nine(self) -> None:
        self.assertEqual(crate_dirs(), EXPECTED)

    def test_each_file_has_a_nonempty_exclude_re_list_or_only_test_args(self) -> None:
        for crate in sorted(EXPECTED):
            path = REPO_ROOT / crate / ".cargo" / "mutants.toml"
            with self.subTest(crate=crate):
                config = tomllib.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(check_config(config), [])

    def test_entries_match_listed_mutants(self) -> None:
        if shutil.which("cargo-mutants") is None:
            if os.environ.get("CI") == "true":
                self.fail(f"cargo-mutants missing in CI; install: {INSTALL_HINT}")
            self.skipTest(f"cargo-mutants not installed; run: {INSTALL_HINT}")
        for crate in sorted(EXPECTED):
            path = REPO_ROOT / crate / ".cargo" / "mutants.toml"
            patterns = exclusion_patterns(
                tomllib.loads(path.read_text(encoding="utf-8"))
            )
            if not patterns:
                continue
            with self.subTest(crate=crate):
                result = subprocess.run(
                    [
                        "cargo",
                        "mutants",
                        "--list",
                        "--no-config",
                        "-d",
                        str(REPO_ROOT / crate),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    stdin=subprocess.DEVNULL,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                listed = [ln for ln in result.stdout.splitlines() if ln.strip()]
                self.assertTrue(listed, "cargo mutants --list produced no output")
                self.assertEqual(check_exclusions(patterns, listed), [])


if __name__ == "__main__":
    unittest.main()
