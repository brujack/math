"""The snyk-scan job installs a pinned, checksum-verified Snyk CLI.

It used to download `cli/latest/snyk-linux` with no checksum and run it with the
repository's SNYK_TOKEN: whatever static.snyk.io served that minute ran in CI.
Same rule as ci-002 and the pinned shellcheck in scripts.yml: a directly
downloaded binary pins its version and verifies a sha256 before it is executed.
"""

import pathlib
import re
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
AUTO_MERGE = REPO_ROOT / ".github" / "workflows" / "auto-merge.yml"


def install_step():
    steps = yaml.safe_load(AUTO_MERGE.read_text())["jobs"]["snyk-scan"]["steps"]
    matches = [s for s in steps if s.get("name") == "Install Snyk CLI"]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one 'Install Snyk CLI' step, found {len(matches)}"
        )
    return matches[0]


class TestSnykCliPinned(unittest.TestCase):
    def setUp(self):
        self.step = install_step()
        self.env = self.step.get("env") or {}
        self.run_text = str(self.step.get("run") or "")

    def test_version_is_an_exact_stable_release(self):
        self.assertRegex(str(self.env.get("SNYK_VER", "")), r"^\d+\.\d+\.\d+$")

    def test_sha256_is_pinned(self):
        self.assertRegex(str(self.env.get("SNYK_SHA256", "")), r"^[0-9a-f]{64}$")

    def test_download_names_the_pinned_version_not_latest(self):
        self.assertNotIn("latest", self.run_text)
        self.assertIn("/cli/v${SNYK_VER}/snyk-linux", self.run_text)
        self.assertIn("curl -fsSL", self.run_text)

    def test_checksum_is_verified_before_install(self):
        lines = [line.strip() for line in self.run_text.splitlines()]
        check = next(
            (i for i, line in enumerate(lines) if "sha256sum -c" in line), None
        )
        install = next(
            (i for i, line in enumerate(lines) if "/usr/local/bin/snyk" in line), None
        )
        if check is None or install is None:
            self.fail(f"missing checksum or install line: {lines}")
        self.assertIn('echo "${SNYK_SHA256}  ', lines[check])
        self.assertLess(check, install)

    def test_installed_version_is_asserted(self):
        self.assertTrue(
            re.search(r'snyk --version \| grep -qx "\$\{SNYK_VER\}"', self.run_text),
            self.run_text,
        )


if __name__ == "__main__":
    unittest.main()
