"""Assert renovate.json's github-actions manager scans the rendered-workflow templates.

The Rust and Python workflows are rendered from scripts/crate_templates/, and
test_crate_uniformity.py fails when a rendered workflow drifts from its template.
Renovate's github-actions manager only scans its default paths, so an action bump
edited the rendered files and not the templates (math#178) and could never merge.
These tests pin that every file carrying a ``uses:`` line is in the manager's scope.
"""

import json
import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
RENOVATE_JSON = REPO_ROOT / "renovate.json"
TEMPLATE_DIR = REPO_ROOT / "scripts" / "crate_templates"

# Renovate's documented github-actions managerFilePatterns defaults, used when
# renovate.json does not override them.
_DEFAULT_PATTERNS = [
    r"/(^|/)(workflow-templates|\.(?:github|gitea|forgejo)/(?:workflows|actions))/.+\.ya?ml$/",
    r"/(^|/)action\.ya?ml$/",
]


def _manager_patterns() -> list[re.Pattern[str]]:
    config = json.loads(RENOVATE_JSON.read_text(encoding="utf-8"))
    raw = config.get("github-actions", {}).get("managerFilePatterns", _DEFAULT_PATTERNS)
    compiled = []
    for pattern in raw:
        if not (pattern.startswith("/") and pattern.endswith("/")):
            raise AssertionError(f"not a /regex/ string: {pattern!r}")
        compiled.append(re.compile(pattern[1:-1]))
    return compiled


def _matches(path: pathlib.Path) -> bool:
    rel = path.relative_to(REPO_ROOT).as_posix()
    return any(p.search(rel) for p in _manager_patterns())


def _tracked(globs: list[str]) -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for glob in globs:
        files.extend(sorted(REPO_ROOT.glob(glob)))
    return files


class GithubActionsManagerScopeTest(unittest.TestCase):
    def test_workflows_are_scanned(self) -> None:
        files = _tracked([".github/workflows/*.yml"])
        self.assertTrue(files)
        missing = [f.name for f in files if not _matches(f)]
        self.assertEqual(missing, [])

    def test_composite_actions_are_scanned(self) -> None:
        files = _tracked([".github/actions/*/action.yml"])
        self.assertTrue(files)
        missing = [f.name for f in files if not _matches(f)]
        self.assertEqual(missing, [])

    def test_templates_with_uses_lines_are_scanned(self) -> None:
        files = [
            f
            for f in TEMPLATE_DIR.rglob("*.yml")
            if re.search(r"^\s*-?\s*uses:", f.read_text(encoding="utf-8"), re.MULTILINE)
        ]
        self.assertTrue(files)
        missing = [
            f.relative_to(REPO_ROOT).as_posix() for f in files if not _matches(f)
        ]
        self.assertEqual(missing, [])

    def test_non_workflow_files_are_not_scanned(self) -> None:
        self.assertFalse(
            _matches(REPO_ROOT / "scripts" / "crate_templates" / "Makefile")
        )
        self.assertFalse(_matches(REPO_ROOT / "README.md"))


if __name__ == "__main__":
    unittest.main()
