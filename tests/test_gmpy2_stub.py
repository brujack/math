"""Guards for the vendored gmpy2 type stub (typings/gmpy2/__init__.pyi).

gmpy2 ships no .pyi, so the Python sub-projects type-check against this stub.
It must parse, must not use ``Any`` (which would hide the types it exists to
provide), and must define every gmpy2 attribute the sub-projects reference.
"""

import ast
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STUB = REPO_ROOT / "typings" / "gmpy2" / "__init__.pyi"
SOURCES = sorted(
    p for project in ("e", "pi") for p in (REPO_ROOT / project).glob("*.py")
)
# Names that always refer to the gmpy2 module; further aliases are derived
# from each module's own bindings (see _module_aliases).
BASE_ALIASES = {"gmpy2", "_gmpy2"}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _stub_top_level_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def _module_aliases(tree: ast.Module) -> set[str]:
    """Names bound to the gmpy2 module anywhere in ``tree``.

    Counts ``import gmpy2 [as X]``, ``from ... import gmpy2 [as X]``,
    ``X = gmpy2`` / ``X = _gmpy2`` and ``X = _require_gmpy2()``, so a rename of
    a local alias cannot hide attribute uses from the scan.
    """
    aliases = set(BASE_ALIASES)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "gmpy2":
                    aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "gmpy2":
                    aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            value = node.value
            is_module = isinstance(value, ast.Name) and value.id in BASE_ALIASES
            is_require = (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "_require_gmpy2"
            )
            if is_module or is_require:
                aliases.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return aliases


def _gmpy2_names_in(tree: ast.Module) -> set[str]:
    aliases = _module_aliases(tree)
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in aliases
    }


def _referenced_gmpy2_names() -> set[str]:
    referenced: set[str] = set()
    for path in SOURCES:
        referenced |= _gmpy2_names_in(_parse(path))
    return referenced


class TestGmpy2Stub(unittest.TestCase):
    def test_stub_exists_and_parses(self):
        self.assertTrue(STUB.is_file(), f"missing {STUB}")
        self.assertIsInstance(_parse(STUB), ast.Module)

    def test_stub_contains_no_any(self):
        offenders = []
        for node in ast.walk(_parse(STUB)):
            if isinstance(node, ast.Name) and node.id == "Any":
                offenders.append(node.lineno)
            elif isinstance(node, ast.Attribute) and node.attr == "Any":
                offenders.append(node.lineno)
            elif isinstance(node, ast.alias) and node.name.split(".")[-1] == "Any":
                offenders.append(getattr(node, "lineno", 0))
        self.assertEqual(offenders, [], f"Any used in stub at lines {offenders}")

    def test_every_referenced_attribute_is_defined(self):
        defined = _stub_top_level_names(_parse(STUB))
        referenced = _referenced_gmpy2_names()
        self.assertTrue(referenced, "no gmpy2 references found; scan is broken")
        self.assertEqual(sorted(referenced - defined), [])

    def test_scan_follows_require_gmpy2_alias(self):
        tree = ast.parse(
            "def f():\n    gm = _require_gmpy2()\n    return gm.not_in_stub\n"
        )
        referenced = _gmpy2_names_in(tree)
        defined = _stub_top_level_names(_parse(STUB))
        self.assertEqual(sorted(referenced - defined), ["not_in_stub"])

    def test_scan_follows_import_and_assignment_aliases(self):
        src = "import gmpy2 as a\nb = _gmpy2\nfrom x import gmpy2 as c\na.p; b.q; c.r\n"
        self.assertEqual(_gmpy2_names_in(ast.parse(src)), {"p", "q", "r"})

    def test_scan_sees_known_names(self):
        referenced = _referenced_gmpy2_names()
        for name in ("mpz", "mpfr", "get_context", "sqrt", "version"):
            self.assertIn(name, referenced)


if __name__ == "__main__":
    unittest.main()
