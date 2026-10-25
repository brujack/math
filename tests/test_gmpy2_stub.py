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
# Names that refer to the gmpy2 module in e/ and pi/ code and tests.
MODULE_ALIASES = {"gmpy2", "_gmpy2", "g"}


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


def _referenced_gmpy2_names() -> set[str]:
    referenced: set[str] = set()
    for path in SOURCES:
        for node in ast.walk(_parse(path)):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in MODULE_ALIASES
            ):
                referenced.add(node.attr)
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

    def test_scan_sees_known_names(self):
        referenced = _referenced_gmpy2_names()
        for name in ("mpz", "mpfr", "get_context", "sqrt", "version"):
            self.assertIn(name, referenced)


if __name__ == "__main__":
    unittest.main()
