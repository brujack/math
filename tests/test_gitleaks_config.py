"""The CI secret scan's gitleaks config must extend the built-in ruleset.

A gitleaks config without `[extend] useDefault = true` replaces the default
rules instead of adding to them, so a config holding only an allowlist makes
`gitleaks detect --config .gitleaks.toml` run with no rules at all.

The allowlist must stay the singular `[allowlist]` table: CI pins gitleaks
8.21.2 (auto-merge.yml, secret-scan), and the plural `[[allowlists]]` form is
not read by that release.

Regression test for: gitleaks config did not extend default rules.
"""

import pathlib
import unittest

import tomllib
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / ".gitleaks.toml"
AUTO_MERGE = REPO_ROOT / ".github" / "workflows" / "auto-merge.yml"


def load_config(text):
    """Parse gitleaks TOML config text. Raises tomllib.TOMLDecodeError on bad input."""
    return tomllib.loads(text)


def extends_default_rules(config):
    """Return True only when the config adds to, not replaces, the default rules."""
    extend = config.get("extend")
    return isinstance(extend, dict) and extend.get("useDefault") is True


def pinned_gitleaks_version():
    """Return GITLEAKS_VER from the secret-scan job's Install gitleaks step."""
    workflow = yaml.safe_load(AUTO_MERGE.read_text())
    for step in workflow["jobs"]["secret-scan"]["steps"]:
        env = step.get("env") or {}
        if "GITLEAKS_VER" in env:
            return str(env["GITLEAKS_VER"])
    raise AssertionError("secret-scan has no step setting GITLEAKS_VER")


class TestExtendsDefaultRules(unittest.TestCase):
    def test_allowlist_only_config_does_not_extend(self):
        config = load_config("[allowlist]\npaths = ['''x''']\n")
        self.assertFalse(extends_default_rules(config))

    def test_empty_config_does_not_extend(self):
        self.assertFalse(extends_default_rules(load_config("")))

    def test_use_default_false_does_not_extend(self):
        self.assertFalse(
            extends_default_rules(load_config("[extend]\nuseDefault = false\n"))
        )

    def test_use_default_string_does_not_extend(self):
        # A quoted "true" is a string, not the boolean gitleaks reads.
        self.assertFalse(
            extends_default_rules(load_config('[extend]\nuseDefault = "true"\n'))
        )

    def test_extend_without_use_default_does_not_extend(self):
        config = load_config("[extend]\npath = '''base.toml'''\n")
        self.assertFalse(extends_default_rules(config))

    def test_use_default_true_extends(self):
        self.assertTrue(
            extends_default_rules(load_config("[extend]\nuseDefault = true\n"))
        )

    def test_malformed_toml_raises(self):
        with self.assertRaises(tomllib.TOMLDecodeError):
            load_config("[extend\nuseDefault = true\n")


class TestRepoGitleaksConfig(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(CONFIG.read_text())

    def test_repo_config_extends_default_rules(self):
        self.assertTrue(
            extends_default_rules(self.config),
            ".gitleaks.toml must set [extend] useDefault = true",
        )

    def test_repo_config_keeps_singular_allowlist(self):
        self.assertIn(".gitleaks.toml", self.config["allowlist"]["paths"])

    def test_repo_config_has_no_plural_allowlists(self):
        self.assertEqual(pinned_gitleaks_version(), "8.21.2")
        self.assertNotIn(
            "allowlists",
            self.config,
            "gitleaks 8.21.2 does not read [[allowlists]]; use [allowlist]",
        )

    def test_ci_scan_uses_this_config(self):
        workflow = yaml.safe_load(AUTO_MERGE.read_text())
        runs = [
            str(step.get("run", ""))
            for step in workflow["jobs"]["secret-scan"]["steps"]
        ]
        self.assertTrue(
            any("--config .gitleaks.toml" in run for run in runs),
            "secret-scan no longer passes --config .gitleaks.toml",
        )


if __name__ == "__main__":
    unittest.main()
