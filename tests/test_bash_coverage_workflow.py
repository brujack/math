"""The bash-coverage gate must surface why a red bats suite failed."""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

WORKFLOW = (
    Path(__file__).resolve().parent.parent / ".github" / "workflows" / "auto-merge.yml"
)
STEP_NAME = "Run bash coverage (bootstrap gate)"


def _step_script() -> str:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for step in data["jobs"]["bash-coverage"]["steps"]:
        if step.get("name") == STEP_NAME:
            return step["run"]
    raise AssertionError(f"step {STEP_NAME!r} not found")


def _failure_branch() -> str:
    """The `|| { ... }` group that runs when `make bash-coverage` fails."""
    match = re.search(
        r"make bash-coverage[^\n]*\|\| \{\n(.*?)\n\s*\}\n", _step_script(), re.DOTALL
    )
    assert match, "failure branch of make bash-coverage not found"
    return match.group(1)


class BashCoverageFailureBranchTest(unittest.TestCase):
    def test_failure_branch_reads_bats_log_and_still_exits_1(self) -> None:
        branch = _failure_branch()
        self.assertIn("coverage/bats_run.log", branch)
        self.assertRegex(branch, r"(?m)^\s*exit 1\s*$")

    def test_failure_branch_guards_on_log_existence(self) -> None:
        self.assertRegex(_failure_branch(), r"\[ -f coverage/bats_run\.log \]")

    def test_awk_prints_only_the_failing_block(self) -> None:
        match = re.search(r"awk '[^']*' coverage/bats_run\.log", _failure_branch())
        self.assertIsNotNone(match, "awk command over bats_run.log not found")
        assert match is not None
        log = (
            "ok 1 first passes\n"
            "# passing diagnostic\n"
            "not ok 2 second fails\n"
            "# (in test file t.bats, line 9)\n"
            "#   `false' failed\n"
            "ok 3 third passes\n"
            "# trailing diagnostic\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "bats_run.log"
            fixture.write_text(log, encoding="utf-8")
            cmd = match.group(0).replace("coverage/bats_run.log", str(fixture))
            out = subprocess.run(
                ["bash", "-c", cmd], capture_output=True, text=True, check=True
            ).stdout
        self.assertEqual(
            out,
            "not ok 2 second fails\n"
            "# (in test file t.bats, line 9)\n"
            "#   `false' failed\n",
        )


if __name__ == "__main__":
    unittest.main()
