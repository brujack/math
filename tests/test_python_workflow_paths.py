"""Pin the shared inputs every Python CLI workflow must watch (spec R16).

The 8 `*-py.yml` workflows each run the shared harness `scripts/cli_contract.py`
against their own program and type-check against the vendored `typings/` stubs,
so a change to either must trigger every one of them. Parsed with
`yaml.safe_load`, not text search, so a comment or a mis-indented line cannot
satisfy the check.
"""

import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PROJECTS = (
    "amicable",
    "collatz",
    "e",
    "factorial",
    "fib",
    "perfect-numbers",
    "pi",
    "sq",
)
SHARED_PATHS = ("scripts/cli_contract.py", "typings/**")


def pull_request_paths(project: str) -> list[str]:
    workflow = REPO_ROOT / ".github" / "workflows" / f"{project}-py.yml"
    parsed = yaml.safe_load(workflow.read_text(encoding="utf-8"))
    # PyYAML (YAML 1.1) parses the bare key `on` as the boolean True.
    return parsed[True]["pull_request"]["paths"]


class PythonWorkflowPathsTest(unittest.TestCase):
    def test_every_python_workflow_watches_shared_inputs(self) -> None:
        for project in PROJECTS:
            paths = pull_request_paths(project)
            for shared in SHARED_PATHS:
                with self.subTest(project=project, path=shared):
                    self.assertIn(shared, paths)

    def test_existing_entries_are_kept(self) -> None:
        for project in PROJECTS:
            paths = pull_request_paths(project)
            with self.subTest(project=project):
                self.assertIn(f"{project}/*.py", paths)
                self.assertIn(f".github/workflows/{project}-py.yml", paths)

    def test_there_are_eight_python_workflows(self) -> None:
        found = sorted(
            p.name for p in (REPO_ROOT / ".github" / "workflows").glob("*-py.yml")
        )
        self.assertEqual(found, sorted(f"{p}-py.yml" for p in PROJECTS))


if __name__ == "__main__":
    unittest.main()
