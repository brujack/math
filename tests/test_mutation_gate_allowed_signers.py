"""R28: the allowed-signers file lists only hardware-touch FIDO keys."""

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "mutation_gate_clearance", ROOT / "scripts" / "mutation_gate_clearance.py"
)
assert _SPEC is not None and _SPEC.loader is not None
_MOD: Any = importlib.util.module_from_spec(_SPEC)
sys.modules["mutation_gate_clearance"] = _MOD
_SPEC.loader.exec_module(_MOD)
check_allowed_signers = _MOD.check_allowed_signers
SIGNERS = ROOT / ".github" / "mutation-gate-allowed-signers"
GOOD = 'who namespaces="git" sk-ssh-ed25519@openssh.com AAAAGnNrLXNzaC1lZDI1NTE5'


class CheckAllowedSignersTest(unittest.TestCase):
    def test_good_sk_line_has_no_problem(self) -> None:
        self.assertEqual(check_allowed_signers(GOOD + "\n"), [])

    def test_empty_and_comment_only_text_has_no_problem(self) -> None:
        self.assertEqual(check_allowed_signers(""), [])
        self.assertEqual(check_allowed_signers("# note\n\n   \n"), [])

    def test_plain_ed25519_is_a_problem(self) -> None:
        line = 'who namespaces="git" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5'
        problems = check_allowed_signers(line)
        self.assertEqual(len(problems), 1)
        self.assertIn("ssh-ed25519", problems[0])

    def test_no_touch_required_is_a_problem(self) -> None:
        line = 'who namespaces="git",no-touch-required sk-ssh-ed25519@openssh.com AAAA'
        problems = check_allowed_signers(line)
        self.assertEqual(len(problems), 1)
        self.assertIn("no-touch-required", problems[0])

    def test_no_touch_required_in_a_comment_is_not_flagged(self) -> None:
        self.assertEqual(
            check_allowed_signers("# no-touch-required is banned\n" + GOOD), []
        )

    def test_each_bad_line_is_reported_with_its_number(self) -> None:
        text = GOOD + "\nbad ssh-rsa AAAA\n"
        problems = check_allowed_signers(text)
        self.assertEqual(len(problems), 1)
        self.assertTrue(problems[0].startswith("line 2:"))

    def test_line_without_a_key_type_is_a_problem(self) -> None:
        self.assertEqual(len(check_allowed_signers("lonely\n")), 1)

    def test_committed_file_passes(self) -> None:
        self.assertEqual(check_allowed_signers(SIGNERS.read_text()), [])


if __name__ == "__main__":
    unittest.main()
