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
    result = subprocess.run(
        ["git", "ls-files", *pathspecs],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=_clean_git_env(),
    )
    return [line for line in result.stdout.splitlines() if line]


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


def _classify_repo() -> dict[str, dict[str, str]]:
    """(file -> {import name -> classification}) for every population file."""
    first_party = _first_party_roots()
    stdlib = sys.stdlib_module_names
    classification: dict[str, dict[str, str]] = {}
    for rel in _git_ls_files(*POPULATION_PATHSPECS):
        per_file: dict[str, str] = {}
        for name in sorted(_top_level_imports(REPO_ROOT / rel)):
            if name in first_party:
                per_file[name] = "first-party"
            elif name in stdlib:
                per_file[name] = "stdlib"
            else:
                per_file[name] = "third-party"
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
