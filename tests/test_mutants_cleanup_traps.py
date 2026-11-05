"""Static pin of the signal handling in every `mutants*` recipe.

The behavioural SIGTERM-twice tests in tests/scripts/makefile.bats prove the
cleanup survives a repeated signal at runtime. These checks are the deterministic
guard: deleting a trap from one recipe must fail here even if timing hides it.
Each recipe is isolated (target line to next blank line) so one recipe cannot
satisfy the check for another.
"""

import pathlib
import re
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import render_crate_files as rcf

CLEANUP_BODY = re.compile(r'cleanup\(\) \{ trap "" TERM HUP INT;')
TRAP_LINE = 'trap cleanup EXIT; trap "exit 143" TERM; trap "exit 129" HUP;'

RUST_RECIPES = ("mutants", "mutants-diff")
PYTHON_RECIPES = ("mutants", "mutants-baseline")


def recipe_text(makefile: str, target: str) -> str:
    """Text of `target`'s recipe with line continuations joined into single spaces."""
    match = re.search(
        rf"^{re.escape(target)}:[^\n]*\n(.*?)(?:\n[ \t]*\n|\Z)",
        makefile,
        re.DOTALL | re.MULTILINE,
    )
    if match is None:
        raise AssertionError(f"recipe {target!r} not found")
    return re.sub(r"[ \t]*\\\n\s*", " ", match.group(1))


def trap_problems(makefile: str, targets: tuple[str, ...]) -> list[str]:
    """Describe each recipe in `targets` that lacks the cleanup body or trap line."""
    problems = []
    for target in targets:
        text = recipe_text(makefile, target)
        if not CLEANUP_BODY.search(text):
            problems.append(
                f'{target}: cleanup body does not begin with trap "" TERM HUP INT;'
            )
        if TRAP_LINE not in text:
            problems.append(f"{target}: missing {TRAP_LINE}")
    return problems


def _rust_makefiles() -> list[pathlib.Path]:
    paths = [REPO_ROOT / rcf.TEMPLATE_DIR / "Makefile"]
    paths += [REPO_ROOT / c / f"{c}-rs" / "Makefile" for c in rcf.CRATES]
    return paths


def _python_makefiles() -> list[pathlib.Path]:
    paths = [REPO_ROOT / rcf.TEMPLATE_DIR / "python" / "Makefile"]
    paths += [REPO_ROOT / p / "Makefile" for p in rcf.PYTHON_PROJECTS]
    return paths


class TestMutantsCleanupTraps(unittest.TestCase):
    def test_rust_makefiles_pin_signal_traps(self):
        files = _rust_makefiles()
        self.assertEqual(len(files), 12)
        for path in files:
            with self.subTest(makefile=str(path.relative_to(REPO_ROOT))):
                self.assertEqual(trap_problems(path.read_text(), RUST_RECIPES), [])

    def test_python_makefiles_pin_signal_traps(self):
        files = _python_makefiles()
        self.assertEqual(len(files), 10)
        for path in files:
            with self.subTest(makefile=str(path.relative_to(REPO_ROOT))):
                self.assertEqual(trap_problems(path.read_text(), PYTHON_RECIPES), [])


class TestTrapProblems(unittest.TestCase):
    """The checker itself must be able to fail, and per recipe."""

    def setUp(self):
        self.rust = (REPO_ROOT / rcf.TEMPLATE_DIR / "Makefile").read_text()
        self.python = (REPO_ROOT / rcf.TEMPLATE_DIR / "python" / "Makefile").read_text()

    def test_removed_term_trap_in_one_rust_recipe_is_reported_for_that_recipe_only(
        self,
    ):
        # Break only the first occurrence (the `mutants` recipe).
        broken = self.rust.replace('trap "exit 143" TERM; ', "", 1)
        problems = trap_problems(broken, RUST_RECIPES)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("mutants:"))

    def test_removed_term_trap_in_mutants_diff_is_reported_for_that_recipe_only(self):
        head, sep, tail = self.rust.partition("mutants-diff:")
        broken = head + sep + tail.replace('trap "exit 143" TERM; ', "", 1)
        problems = trap_problems(broken, RUST_RECIPES)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("mutants-diff:"))

    def test_cleanup_body_without_leading_ignore_trap_is_reported(self):
        broken = self.rust.replace(
            'cleanup() { trap "" TERM HUP INT; ', "cleanup() { ", 1
        )
        problems = trap_problems(broken, RUST_RECIPES)
        self.assertEqual(len(problems), 1)
        self.assertIn("cleanup body", problems[0])

    def test_python_baseline_and_mutants_are_checked_separately(self):
        broken = self.python.replace('trap "exit 129" HUP;', "", 1)
        problems = trap_problems(broken, PYTHON_RECIPES)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("mutants-baseline:"))

    def test_python_multiline_cleanup_body_is_accepted(self):
        self.assertEqual(trap_problems(self.python, PYTHON_RECIPES), [])

    def test_missing_recipe_is_an_error(self):
        with self.assertRaises(AssertionError):
            recipe_text("all:\n\ttrue\n", "mutants")


if __name__ == "__main__":
    unittest.main()
