"""deny.toml policy guards for all 11 crates, matching etch-cli.

The licence policy is proven by behaviour, not by pinning the file's text: the
tests/fixtures/cargo-deny controls (tests/scripts/cargo_deny_fixtures.bats) show GPL
and un-excepted LGPL crates rejected, and MIT and rug (only through its exception)
accepted. Fixtures cannot see the settings below, so these tests pin them by key:
unsound/unmaintained "all" (cargo-deny's "workspace" default hides transitive
unsound advisories), sources "deny", and the LGPL exception crates the release
notices cover. They also pin the 11-crate list, keep deny.toml the only advisory
ignore list, and make every bats job install cargo-deny.
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


class TestDenyPolicy(unittest.TestCase):
    def _deny(self):
        with (REPO_ROOT / "deny.toml").open("rb") as handle:
            return tomllib.load(handle)

    def test_advisories_cover_transitive_crates(self):
        advisories = self._deny()["advisories"]
        self.assertEqual(advisories.get("unsound"), "all")
        self.assertEqual(advisories.get("unmaintained"), "all")
        # An `ignore` list is the reviewed way to accept an advisory; any other key
        # (yanked, db-urls, ...) could quietly narrow what is checked.
        self.assertLessEqual(set(advisories), {"unsound", "unmaintained", "ignore"})

    def test_unknown_sources_are_denied(self):
        # Exactly these keys: an allow-registry or allow-git list would whitelist
        # a source past the deny settings.
        self.assertEqual(
            self._deny()["sources"],
            {"unknown-registry": "deny", "unknown-git": "deny"},
        )

    def test_lgpl_exceptions_are_exactly_rug_and_gmp_mpfr_sys(self):
        exceptions = self._deny()["licenses"].get("exceptions", [])
        self.assertEqual(
            sorted((e["crate"], tuple(e["allow"])) for e in exceptions),
            [
                ("gmp-mpfr-sys", ("LGPL-3.0-or-later",)),
                ("rug", ("LGPL-3.0-or-later",)),
            ],
        )

    def test_one_ignore_list_no_workflow_has_its_own(self):
        """deny.toml is the only advisory ignore list; no workflow may carry one."""
        files = sorted((REPO_ROOT / ".github" / "workflows").glob("*.y*ml"))
        self.assertTrue(files)
        offenders = [f.name for f in files if "--ignore RUSTSEC" in f.read_text()]
        self.assertEqual(offenders, [])

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
