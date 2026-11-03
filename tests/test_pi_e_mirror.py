"""Guard the functions deliberately duplicated between pi/pi.py and e/e.py.

cosmic-ray's `module-path` names one file per project, so a shared module
would drop these functions from mutation scope. They are therefore mirrored,
and this test fails if the two copies drift apart.
"""

import ast
import copy
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PI_PATH = ROOT / "pi" / "pi.py"
E_PATH = ROOT / "e" / "e.py"

MIRRORED = (
    "_io_workers",
    "estimate_conversion_time",
    "render_conversion_tick",
    "render_write_progress",
    "render_bar",
    "_format_mantissa",
)


def _top_level_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def mirror_mismatches(pi_tree: ast.Module, e_tree: ast.Module) -> list[str]:
    """Return mirrored names whose AST differs or that either tree lacks."""
    pi_funcs = _top_level_functions(pi_tree)
    e_funcs = _top_level_functions(e_tree)
    mismatches: list[str] = []
    for name in MIRRORED:
        pi_node = pi_funcs.get(name)
        e_node = e_funcs.get(name)
        if pi_node is None or e_node is None or ast.dump(pi_node) != ast.dump(e_node):
            mismatches.append(name)
    return mismatches


def _has_module_assign(tree: ast.Module, name: str) -> bool:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return True
    return False


class TestPiEMirror(unittest.TestCase):
    def setUp(self) -> None:
        self.pi_tree = ast.parse(PI_PATH.read_text(encoding="utf-8"))
        self.e_tree = ast.parse(E_PATH.read_text(encoding="utf-8"))

    def test_real_files_match(self) -> None:
        self.assertEqual(mirror_mismatches(self.pi_tree, self.e_tree), [])

    def test_changed_constant_is_reported(self) -> None:
        pi_copy = copy.deepcopy(self.pi_tree)
        render_bar = _top_level_functions(pi_copy)["render_bar"]
        constants = [n for n in ast.walk(render_bar) if isinstance(n, ast.Constant)]
        self.assertTrue(constants, "render_bar has no constant to alter")
        value = constants[0].value
        constants[0].value = value + 1 if isinstance(value, int) else f"{value}x"
        self.assertEqual(mirror_mismatches(pi_copy, self.e_tree), ["render_bar"])

    def test_missing_function_is_reported(self) -> None:
        e_copy = copy.deepcopy(self.e_tree)
        e_copy.body = [
            n
            for n in e_copy.body
            if not (isinstance(n, ast.FunctionDef) and n.name == "_format_mantissa")
        ]
        self.assertEqual(mirror_mismatches(self.pi_tree, e_copy), ["_format_mantissa"])

    def test_glyphs_are_module_constants(self) -> None:
        for tree in (self.pi_tree, self.e_tree):
            self.assertTrue(_has_module_assign(tree, "_BAR_FULL"))
            self.assertTrue(_has_module_assign(tree, "_BAR_EMPTY"))


if __name__ == "__main__":
    unittest.main()
