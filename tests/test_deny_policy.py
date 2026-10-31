"""deny.toml is the licence, advisory, ban and source policy for all 11 crates.

The whole file is compared to one EXPECTED dict, so any added, removed or changed
key fails here and the policy cannot drift unreviewed. The second test pins the
crate list that `cargo deny` is run over to exactly the 11 rendered crates.
"""

import os
import pathlib
import re
import subprocess
import sys
import unittest

import tomllib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import render_crate_files as rcf

EXPECTED = {
    "licenses": {
        "allow": [
            "MIT",
            "Apache-2.0",
            "Apache-2.0 WITH LLVM-exception",
            "BSD-2-Clause",
            "Unlicense",
            "Zlib",
            "Unicode-3.0",
        ],
        "exceptions": [
            {"crate": "rug", "allow": ["LGPL-3.0-or-later"]},
            {"crate": "gmp-mpfr-sys", "allow": ["LGPL-3.0-or-later"]},
        ],
    },
    "advisories": {"unmaintained": "all", "unsound": "all"},
    "bans": {"multiple-versions": "warn"},
    "sources": {"unknown-registry": "deny", "unknown-git": "deny"},
}


class TestDenyPolicy(unittest.TestCase):
    def test_deny_toml_equals_expected_policy(self):
        with (REPO_ROOT / "deny.toml").open("rb") as handle:
            self.assertEqual(tomllib.load(handle), EXPECTED)

    def test_tracked_crate_manifests_are_exactly_the_eleven_crates(self):
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
        }
        result = subprocess.run(
            ["git", "ls-files", "*/*-rs/Cargo.toml"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        expected = sorted(f"{c}/{c}-rs/Cargo.toml" for c in rcf.CRATES)
        self.assertEqual(len(expected), 11)
        self.assertEqual(sorted(result.stdout.split()), expected)


_BATS_SUITE = re.compile(r"\bbats\b|\bbash-coverage\b|\btest-hooks\b")


def _runs_bats_suite(step):
    # Matches installing bats (any job that installs it runs the suite), running
    # it directly, and the root make targets that reach it. A crate's own
    # `make test` runs cargo or pytest, not bats, so it is not matched.
    run = step.get("run") or ""
    return bool(_BATS_SUITE.search(run))


def _installs_cargo_deny(step):
    uses = step.get("uses") or ""
    tool = str((step.get("with") or {}).get("tool", ""))
    return uses.startswith("taiki-e/install-action@") and tool.startswith("cargo-deny@")


class TestBatsJobsInstallCargoDeny(unittest.TestCase):
    """The cargo-deny fixture tests fail closed when CI is set and cargo-deny is
    absent, so every CI job that runs the bats suite must install it. The
    bash-coverage job in auto-merge.yml ran the suite without it and failed."""

    def test_every_job_running_bats_installs_cargo_deny(self):
        import yaml

        checked = 0
        for path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")):
            doc = yaml.safe_load(path.read_text())
            for job_name, job in (doc.get("jobs") or {}).items():
                steps = job.get("steps") or []
                if not any(_runs_bats_suite(s) for s in steps):
                    continue
                checked += 1
                with self.subTest(workflow=path.name, job=job_name):
                    self.assertTrue(
                        any(_installs_cargo_deny(s) for s in steps),
                        f"{path.name}:{job_name} runs bats but installs no cargo-deny",
                    )
        self.assertGreaterEqual(checked, 2, "expected scripts.yml and auto-merge.yml")


if __name__ == "__main__":
    unittest.main()
