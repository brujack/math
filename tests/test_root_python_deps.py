"""Guard every unguarded third-party import in root-scope Python against a stale
`requirements-dev.txt`.

Population: `git ls-files 'tests/*.py' 'scripts/*.py' '.claude/scripts/*.py'` — the
same scope `pyrightconfig.json` type-checks at the repo root.

Classification is derived by `ast`, never by importing the modules — a runtime
import-error classifier would depend on the very dependency it is trying to verify:

1. Parse each file's AST. Collect top-level module names from `ast.Import` (an
   `import a.b.c` contributes `a`) and `ast.ImportFrom` where `node.level == 0` — a
   relative import (`from . import x`) is first-party by construction and is skipped.
2. A **guarded** import — one whose statement sits in the body of a `try` block that
   has a handler catching `ImportError` or `ModuleNotFoundError` — is excluded. The
   code already has an explicit fallback for that name being absent.
3. A **first-party root** is derived mechanically from `git ls-files` over the whole
   repo: the first path segment of every tracked file with more than one segment,
   plus the stem of any tracked top-level `.py` file. This is not a hardcoded list —
   see `~/.claude/standards/tdd.md`'s Coverage Denominators section for why a
   hand-maintained one would silently stop being true. Without this clause, `scripts`
   (imported by `tests/test_test_metrics.py` and `tests/test_time_tests.py`) would be
   misclassified as third-party and poison `requirements-dev.txt` with a package that
   does not exist.
4. Anything left that is not in `sys.stdlib_module_names` and not a first-party root
   is third-party, and must be declared in `requirements-dev.txt`.

`_IMPORT_TO_DISTRIBUTION` maps the small number of import names that differ from the
PyPI distribution name that provides them (`yaml` ships in the `pyyaml` distribution).
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS_PATH = REPO_ROOT / "requirements-dev.txt"
POPULATION_PATHSPECS = ["tests/*.py", "scripts/*.py", ".claude/scripts/*.py"]

# Import name -> PyPI distribution name, for the rare case they differ. Keep this
# mapping tiny and comment each entry: an import name that already matches its
# distribution needs no entry at all.
_IMPORT_TO_DISTRIBUTION = {
    "yaml": "pyyaml",  # the `pyyaml` distribution installs the `yaml` import name
}


def _clean_git_env() -> dict[str, str]:
    """Strip the repo-location variables git exports into hook environments.

    `cwd=` is not isolation: an inherited GIT_DIR still wins, so a call made from
    a pre-push hook resolves against whatever repository invoked git rather than
    this one (shell.md, "`git -C <dir>` does not override an exported GIT_DIR").
    `make test` runs under that hook, so this path is reachable in normal use.
    """
    env = dict(os.environ)
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
        env.pop(var, None)
    return env


def _git_ls_files(*pathspecs: str) -> list[str]:
    # -z and core.quotePath=false: git otherwise quotes non-ASCII names
    # ("tests/caf\\303\\251.py"), which then match no file on disk.
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false", "ls-files", "-z", *pathspecs],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=_clean_git_env(),
    )
    return [name for name in result.stdout.split("\0") if name]


def _first_party_roots() -> set[str]:
    """Top-level directory names, plus top-level module stems, tracked by git."""
    roots: set[str] = set()
    for rel in _git_ls_files():
        parts = Path(rel).parts
        if len(parts) > 1:
            roots.add(parts[0])
        elif rel.endswith(".py"):
            roots.add(Path(rel).stem)
    return roots


def _handler_catches_import_error(handler: ast.ExceptHandler) -> bool:
    handler_type = handler.type
    names: list[str] = []
    if isinstance(handler_type, ast.Tuple):
        names = [elt.id for elt in handler_type.elts if isinstance(elt, ast.Name)]
    elif isinstance(handler_type, ast.Name):
        names = [handler_type.id]
    return any(name in ("ImportError", "ModuleNotFoundError") for name in names)


def _collect_guarded_import_ids(tree: ast.Module) -> set[int]:
    """id() of every import statement inside a try/except ImportError handler."""
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not any(_handler_catches_import_error(h) for h in node.handlers):
            continue
        for stmt in node.body:
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                guarded.add(id(stmt))
    return guarded


def _top_level_imports_from_tree(tree: ast.Module) -> set[str]:
    """Unguarded, absolute, top-level module names imported in a parsed AST."""
    guarded_ids = _collect_guarded_import_ids(tree)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if id(node) in guarded_ids:
                continue
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level != 0 or id(node) in guarded_ids:
                continue  # relative import: first-party by construction
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def _top_level_imports(path: Path) -> set[str]:
    """Unguarded, absolute, top-level module names imported by `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return _top_level_imports_from_tree(tree)


def _sibling_stems(rel: str, tracked_py: set[str]) -> set[str]:
    """Stems of tracked .py files in the same directory as `rel`.

    Python resolves a plain `import x` from the importing script's own directory
    (sys.path[0]), so a tracked sibling `x.py` is first-party by construction. This
    is what lets fixture tests (e.g. tests/fixtures/cosmic_ray/test_crfix.py) import
    their sibling module plainly without it reading as a PyPI package.
    """
    here = Path(rel).parent
    return {
        Path(other).stem
        for other in tracked_py
        if Path(other).parent == here and other != rel
    }


def _classify_name(
    name: str, first_party: set[str], siblings: set[str], stdlib: frozenset[str]
) -> str:
    if name in first_party or name in siblings:
        return "first-party"
    if name in stdlib:
        return "stdlib"
    return "third-party"


def _classify_repo() -> dict[str, dict[str, str]]:
    """(file -> {import name -> classification}) for every population file."""
    first_party = _first_party_roots()
    stdlib = sys.stdlib_module_names
    tracked_py = set(_git_ls_files("*.py"))
    classification: dict[str, dict[str, str]] = {}
    # Paths come from walking the tree, not from subprocess output (Snyk Code flags
    # that as traversal), but git stays the source of truth for the population.
    # A git pathspec's `*` also matches `/`, so the glob recurses to match, and any
    # tracked file the walk misses is fatal, never skipped: a skip would silently
    # narrow this supply-chain check.
    tracked = set(_git_ls_files(*POPULATION_PATHSPECS))
    walked = {
        p.relative_to(REPO_ROOT).as_posix(): p
        for spec in POPULATION_PATHSPECS
        for p in REPO_ROOT.glob(spec.replace("/*.py", "/**/*.py"))
        if p.is_file()
    }
    missing = sorted(tracked - walked.keys())
    if missing:
        raise AssertionError(f"tracked files the tree walk did not find: {missing}")
    for rel in sorted(tracked):
        path = walked[rel]
        per_file: dict[str, str] = {}
        for name in sorted(_top_level_imports(path)):
            per_file[name] = _classify_name(
                name, first_party, _sibling_stems(rel, tracked_py), stdlib
            )
        classification[rel] = per_file
    return classification


def _third_party_names() -> set[str]:
    return {
        name
        for per_file in _classify_repo().values()
        for name, kind in per_file.items()
        if kind == "third-party"
    }


def _declared_requirements() -> set[str]:
    declared: set[str] = set()
    for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        name = re.split(r"[<>=!~;\[]", stripped, maxsplit=1)[0].strip().lower()
        if name:
            declared.add(name)
    return declared


class TestGuardedImportClassification(unittest.TestCase):
    """The try/except ImportError guard, exercised directly against a synthetic AST.

    No file in the current population contains a guarded import, so this branch of
    `_collect_guarded_import_ids` runs zero times under `TestRootPythonDeps` — both
    branches of the guard (per logic-review.md) require exercise, not just the one
    the real population happens to hit.
    """

    def test_import_error_guard_excludes_the_import(self):
        source = "try:\n    import numpy\nexcept ImportError:\n    numpy = None\n"
        names = _top_level_imports_from_tree(ast.parse(source))
        self.assertNotIn("numpy", names)

    def test_unguarded_import_is_included(self):
        source = "import requests\n"
        names = _top_level_imports_from_tree(ast.parse(source))
        self.assertIn("requests", names)

    def test_guard_on_an_unrelated_exception_does_not_count(self):
        source = "try:\n    import somelib\nexcept ValueError:\n    somelib = None\n"
        names = _top_level_imports_from_tree(ast.parse(source))
        self.assertIn("somelib", names)


class TestSiblingImportClassification(unittest.TestCase):
    def test_sibling_module_is_first_party_and_unknown_is_not(self):
        tracked = {"a/dir/test_x.py", "a/dir/sibling.py", "other/unrelated.py"}
        siblings = _sibling_stems("a/dir/test_x.py", tracked)
        self.assertEqual(siblings, {"sibling"})
        stdlib = sys.stdlib_module_names
        self.assertEqual(
            _classify_name("sibling", set(), siblings, stdlib), "first-party"
        )
        self.assertEqual(
            _classify_name("unrelated", set(), siblings, stdlib), "third-party"
        )
        self.assertEqual(_classify_name("os", set(), siblings, stdlib), "stdlib")

    def test_importer_is_not_its_own_sibling(self):
        self.assertEqual(_sibling_stems("d/x.py", {"d/x.py"}), set())


class TestRootPythonDeps(unittest.TestCase):
    def test_population_is_non_empty(self):
        files = _git_ls_files(*POPULATION_PATHSPECS)
        # Vacuity floor: an AST bug returning an empty population would make every
        # assertion below trivially satisfiable.
        self.assertGreater(
            len(files), 0, "expected at least one file in the population"
        )

    def test_derivation_finds_known_third_party_imports(self):
        third_party = _third_party_names()
        # Vacuity floor: an AST bug that under-detects imports (e.g. missing the
        # ImportFrom branch, or over-classifying as first-party) would return an
        # empty or incomplete third-party set and make the declaration check below
        # pass vacuously. yaml and defusedxml are both known-real third-party
        # imports in the population today.
        self.assertIn("yaml", third_party)
        self.assertIn("defusedxml", third_party)

    def test_every_third_party_import_is_declared(self):
        third_party = _third_party_names()
        declared = _declared_requirements()
        undeclared = {
            name
            for name in third_party
            if _IMPORT_TO_DISTRIBUTION.get(name, name).lower() not in declared
        }
        self.assertEqual(
            undeclared,
            set(),
            f"undeclared third-party imports (not in {REQUIREMENTS_PATH.name}): "
            f"{sorted(undeclared)}",
        )


if __name__ == "__main__":
    unittest.main()
