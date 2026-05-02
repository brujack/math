#!/usr/bin/env python3
"""Tests for scripts/rust-check.sh."""

from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WRAPPER = REPO_ROOT / "scripts" / "rust-check.sh"


class RustCheckWrapperTests(unittest.TestCase):
    def _run_wrapper(self, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(WRAPPER), *args],
            cwd=REPO_ROOT / "pi" / "pi-rs",
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def _make_fake_cargo(self, script_body: str) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        cargo_path = Path(temp_dir.name) / "fake-cargo.sh"
        cargo_path.write_text(script_body, encoding="utf-8")
        cargo_path.chmod(0o755)
        return cargo_path

    def test_sets_repo_local_cargo_home_by_default(self) -> None:
        # Print CARGO_HOME once per invocation; lint calls cargo twice (fmt + clippy),
        # so assert the expected path appears in stdout rather than exact equality.
        fake_cargo = self._make_fake_cargo(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail
                printf '%s\\n' "${CARGO_HOME}"
                """
            )
        )
        env = os.environ.copy()
        env.pop("CARGO_HOME", None)
        env["RUST_CHECK_CARGO_BIN"] = str(fake_cargo)
        result = self._run_wrapper(["lint"], env)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        expected = str(REPO_ROOT / ".cache" / "cargo-home")
        self.assertIn(expected, result.stdout.splitlines())

    def test_passes_offline_flag_when_enabled(self) -> None:
        fake_cargo = self._make_fake_cargo(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail
                printf '%s\\n' "$@"
                """
            )
        )
        env = os.environ.copy()
        env["RUST_CHECK_CARGO_BIN"] = str(fake_cargo)
        env["RUST_CHECK_OFFLINE"] = "1"
        result = self._run_wrapper(["test"], env)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("--offline", result.stdout)

    def test_classifies_environment_failures(self) -> None:
        fake_cargo = self._make_fake_cargo(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail
                echo "Operation not permitted"
                exit 101
                """
            )
        )
        env = os.environ.copy()
        env["RUST_CHECK_CARGO_BIN"] = str(fake_cargo)
        result = self._run_wrapper(["lint"], env)
        self.assertEqual(result.returncode, 101)
        self.assertIn("Environment/setup failure", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
