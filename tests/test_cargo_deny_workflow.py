"""The cargo-deny workflow must run with a read-only token."""

import unittest
from pathlib import Path

import yaml

WORKFLOW = (
    Path(__file__).resolve().parent.parent / ".github" / "workflows" / "cargo-deny.yml"
)


class CargoDenyWorkflowTest(unittest.TestCase):
    def test_permissions_are_contents_read_only(self) -> None:
        data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.assertEqual(data.get("permissions"), {"contents": "read"})


if __name__ == "__main__":
    unittest.main()
