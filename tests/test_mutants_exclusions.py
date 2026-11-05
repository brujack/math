"""Every `.cargo/mutants.toml` `exclude_re` entry must still match a real mutant.

An exclusion embeds a source line number, so an edit above it can leave the regex
matching nothing (stale, silently un-excluding or excluding the wrong mutant) or
make two entries claim one mutant. cargo-mutants lists the mutants it would
generate without running any, so this test compares each entry with that list.
Run by `make test-python` and by pre-push when a crate's `src/` or its
`mutants.toml` changes.
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


class MutantsExclusionsTest(unittest.TestCase):
    def test_crate_set_is_the_expected_eight(self) -> None:
        self.assertEqual(crate_dirs(), EXPECTED)

    def test_each_file_has_a_nonempty_exclude_re_list(self) -> None:
        for crate in sorted(EXPECTED):
            path = REPO_ROOT / crate / ".cargo" / "mutants.toml"
            with self.subTest(crate=crate):
                patterns = tomllib.loads(path.read_text(encoding="utf-8")).get(
                    "exclude_re"
                )
                self.assertIsInstance(patterns, list)
                self.assertTrue(patterns)

    def test_entries_match_listed_mutants(self) -> None:
        if shutil.which("cargo-mutants") is None:
            if os.environ.get("CI") == "true":
                self.fail(f"cargo-mutants missing in CI; install: {INSTALL_HINT}")
            self.skipTest(f"cargo-mutants not installed; run: {INSTALL_HINT}")
        for crate in sorted(EXPECTED):
            path = REPO_ROOT / crate / ".cargo" / "mutants.toml"
            patterns = tomllib.loads(path.read_text(encoding="utf-8"))["exclude_re"]
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
