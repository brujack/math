"""deny.toml is the licence, advisory, ban and source policy for all 11 crates.

The whole file is compared to one EXPECTED dict, so any added, removed or changed
key fails here and the policy cannot drift unreviewed. The second test pins the
crate list that `cargo deny` is run over to exactly the 11 rendered crates.
"""

import os
import pathlib
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
    "advisories": {"unmaintained": "all"},
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


if __name__ == "__main__":
    unittest.main()
