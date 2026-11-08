"""Every `<project>/mutants-equivalent.toml` must keep its layout and still match.

An entry names a cosmic-ray mutant by operator, function, source line text, column
and the non-blank line above it. An edit to the module can leave an entry matching
nothing (stale) or several mutants (ambiguous). `cosmic_ray_prune.py equivalents`
resolves every entry against a freshly initialised session and exits 1 on either
problem, so this test runs `cosmic-ray init` (no execution) in a temp copy and then
that subcommand with `--full-run`. Run by `make test-python`, by pre-push when an
equivalents file or a Python module changes, and by `scripts.yml` in CI.
"""

import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

import tomllib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PRUNE = REPO_ROOT / "scripts" / "cosmic_ray_prune.py"
PROJECTS = (
    "amicable",
    "collatz",
    "e",
    "factorial",
    "fib",
    "perfect-numbers",
    "pi",
    "sq",
    "triangle",
)
HEADER = "[[equivalent]]"
INSTALL_HINT = "pip install cosmic-ray==8.7.0 hypothesis==6.168.5"


def layout_problems(text: str) -> list[str]:
    """Return layout violations: any table header other than `[[equivalent]]` at
    column 0, or any top-level key; an empty file is valid."""
    problems = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.startswith("[") and line.rstrip() != HEADER:
            problems.append(f"line {number}: only {HEADER} headers allowed: {line!r}")
    parsed = tomllib.loads(text)
    extra = sorted(set(parsed) - {"equivalent"})
    if extra:
        problems.append(f"unexpected top-level keys or tables: {extra}")
    return problems


def module_path(project_dir: pathlib.Path) -> str:
    """Return the module file name that `cosmic-ray.toml` mutates."""
    config = tomllib.loads((project_dir / "cosmic-ray.toml").read_text("utf-8"))
    return str(config["cosmic-ray"]["module-path"])


def run_equivalents(project: str) -> subprocess.CompletedProcess[str]:
    """Init a session in a temp copy, then run `prune equivalents --full-run`."""
    project_dir = REPO_ROOT / project
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    with tempfile.TemporaryDirectory() as tmp:
        work = pathlib.Path(tmp)
        for name in (module_path(project_dir), "cosmic-ray.toml"):
            shutil.copy(project_dir / name, work / name)
        shutil.copy(
            project_dir / "mutants-equivalent.toml", work / "mutants-equivalent.toml"
        )
        init = subprocess.run(
            ["cosmic-ray", "init", "cosmic-ray.toml", "session.sqlite"],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        if init.returncode != 0:
            return init
        return subprocess.run(
            [
                "python3",
                str(PRUNE),
                "equivalents",
                "session.sqlite",
                "mutants-equivalent.toml",
                "--full-run",
            ],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )


class LayoutProblemsTest(unittest.TestCase):
    ENTRY = f'{HEADER}\noperator = "x"\n'

    def test_empty_file_is_valid(self) -> None:
        self.assertEqual(layout_problems(""), [])

    def test_equivalent_entries_are_valid(self) -> None:
        self.assertEqual(layout_problems(self.ENTRY + "\n" + self.ENTRY), [])

    def test_other_table_header_is_rejected(self) -> None:
        problems = layout_problems(self.ENTRY + "[other]\nk = 1\n")
        self.assertEqual(len(problems), 2)
        self.assertIn("line 3", problems[0])

    def test_single_bracket_equivalent_header_is_rejected(self) -> None:
        problems = layout_problems("[equivalent]\nk = 1\n")
        self.assertIn("line 1", problems[0])

    def test_top_level_key_is_rejected(self) -> None:
        problems = layout_problems('title = "x"\n' + self.ENTRY)
        self.assertEqual(problems, ["unexpected top-level keys or tables: ['title']"])

    def test_invalid_toml_raises(self) -> None:
        with self.assertRaises(tomllib.TOMLDecodeError):
            layout_problems("[[equivalent]\n")


class MutantsEquivalentFilesTest(unittest.TestCase):
    def test_every_project_has_a_file_with_the_strict_layout(self) -> None:
        for project in PROJECTS:
            path = REPO_ROOT / project / "mutants-equivalent.toml"
            with self.subTest(project=project):
                self.assertTrue(path.is_file(), f"{path} missing")
                self.assertEqual(layout_problems(path.read_text("utf-8")), [])

    def test_project_set_matches_the_cosmic_ray_configs(self) -> None:
        found = {p.parent.name for p in REPO_ROOT.glob("*/mutants-equivalent.toml")}
        self.assertEqual(found, set(PROJECTS))

    def test_entries_resolve_against_a_fresh_session(self) -> None:
        if shutil.which("cosmic-ray") is None:
            if os.environ.get("CI") == "true":
                self.fail(f"cosmic-ray missing in CI; install: {INSTALL_HINT}")
            self.skipTest(f"cosmic-ray not installed; run: {INSTALL_HINT}")
        for project in PROJECTS:
            with self.subTest(project=project):
                result = run_equivalents(project)
                self.assertEqual(
                    result.returncode, 0, f"{result.stdout}\n{result.stderr}"
                )

    def test_declared_counts_match_the_entries(self) -> None:
        if shutil.which("cosmic-ray") is None:
            self.skipTest(f"cosmic-ray not installed; run: {INSTALL_HINT}")
        for project in ("pi", "e"):
            path = REPO_ROOT / project / "mutants-equivalent.toml"
            declared = len(tomllib.loads(path.read_text("utf-8"))["equivalent"])
            with self.subTest(project=project):
                result = run_equivalents(project)
                self.assertRegex(result.stdout, rf"^excluded {declared} of \d+$")


if __name__ == "__main__":
    unittest.main()
