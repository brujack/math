"""Every CI and installer tool install names an exact version, one per tool.

`cargo install --locked` bounds a tool's dependency tree but not the tool itself,
and a bare `pyright` takes whatever PyPI serves, so a bad upstream release used to
land on every PR at once. The pins live in workflow `run:` text and the
`install_deps.sh` installers; this test reads both and requires a single version
per tool across the repo, so a bump is one decision applied everywhere.
"""

import pathlib
import re
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
INSTALLERS = sorted(REPO_ROOT.glob("*/install_deps.sh")) + sorted(
    REPO_ROOT.glob("*/*/install_deps.sh")
)

_CARGO_INSTALL = re.compile(r"\bcargo install\s+(?P<rest>[^\n]*)")
_PIP_INSTALL = re.compile(r"\bpip3? install\s+(?P<rest>[^\n]*)")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def cargo_installs():
    """Yield (file, crate, version or None, locked) for every `cargo install` line."""
    for path in [*WORKFLOWS, *INSTALLERS]:
        for match in _CARGO_INSTALL.finditer(path.read_text()):
            tokens = match.group("rest").split()
            crate = next((t for t in tokens if not t.startswith("-")), None)
            version = None
            if "--version" in tokens:
                index = tokens.index("--version")
                version = tokens[index + 1] if index + 1 < len(tokens) else ""
            yield (
                path.relative_to(REPO_ROOT).as_posix(),
                crate,
                version,
                "--locked" in tokens,
            )


INSTALL_ACTION = "taiki-e/install-action@"
AUDITABLE = "cargo-auditable"
RUST_INSTALLERS = sorted(REPO_ROOT.glob("*/*-rs/install_deps.sh"))
_ACTION_SHA = re.compile(r"^taiki-e/install-action@(?P<sha>[0-9a-f]{40})$")
_TOOL_SPEC = re.compile(r"^(?P<name>[a-z][a-z0-9_-]*)@(?P<version>\d+\.\d+\.\d+)$")


def install_action_steps(workflows=None):
    """Yield (file, step) for every `taiki-e/install-action` step in the workflows."""
    for path in workflows if workflows is not None else WORKFLOWS:
        doc = yaml.safe_load(path.read_text())
        for job in (doc.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                if str(step.get("uses", "")).startswith(INSTALL_ACTION):
                    yield path.name, step


def has_fallback_none(step):
    """True when an install-action step sets `fallback: none` (no cargo-install fallback)."""
    return (step.get("with") or {}).get("fallback") == "none"


def action_tools(step):
    """Return the comma-separated `tool:` entries of an install-action step."""
    raw = str((step.get("with") or {}).get("tool", ""))
    return [t.strip() for t in raw.split(",") if t.strip()]


def installer_pins():
    """Map crate -> set of `--version` pins across the Rust install_deps.sh files."""
    pins = {}
    for path in RUST_INSTALLERS:
        for match in _CARGO_INSTALL.finditer(path.read_text()):
            tokens = match.group("rest").split()
            if "--version" in tokens:
                crate = next(t for t in tokens if not t.startswith("-"))
                pins.setdefault(crate, set()).add(tokens[tokens.index("--version") + 1])
    return pins


def pyright_installs():
    """Yield (file, requirement token) for every pip-installed pyright."""
    for path in [*WORKFLOWS, *INSTALLERS]:
        for match in _PIP_INSTALL.finditer(path.read_text()):
            for token in match.group("rest").split():
                if re.match(r"^pyright(\W|$)", token):
                    yield path.relative_to(REPO_ROOT).as_posix(), token


PYTHON_INSTALLERS = sorted(REPO_ROOT.glob("*/install_deps.sh"))
PYTHON_WORKFLOWS = sorted((REPO_ROOT / ".github" / "workflows").glob("*-py.yml"))
_REQUIREMENT = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>\d+\.\d+\.\d+)$")


def pip_installs():
    """Yield (file, argument) for every `pip install` argument in the 8 Python
    installers and the 8 `*-py.yml` workflows (both rendered from one template).
    """
    for path in [*PYTHON_INSTALLERS, *PYTHON_WORKFLOWS]:
        for match in _PIP_INSTALL.finditer(path.read_text()):
            for token in match.group("rest").split("||")[0].split():
                if not token.startswith("-"):
                    yield path.relative_to(REPO_ROOT).as_posix(), token


class TestCargoInstallPins(unittest.TestCase):
    def test_every_cargo_install_is_locked_and_versioned(self):
        sites = list(cargo_installs())
        self.assertGreater(len(sites), 30, "scan found too few cargo install lines")
        for name, crate, version, locked in sites:
            with self.subTest(file=name, crate=crate):
                self.assertTrue(locked, "missing --locked")
                self.assertIsNotNone(version, "missing --version")
                self.assertRegex(version or "", _VERSION)

    def test_one_version_per_crate(self):
        versions = {}
        for name, crate, version, _ in cargo_installs():
            versions.setdefault(crate, {}).setdefault(version, []).append(name)
        split = {c: v for c, v in versions.items() if len(v) > 1}
        self.assertEqual(split, {}, "a crate is pinned to more than one version")


class TestInstallActionPins(unittest.TestCase):
    """Prebuilt-binary installs via taiki-e/install-action are pinned like cargo installs."""

    def _write(self, tmp, tool, fallback="none"):
        path = pathlib.Path(tmp) / "fixture.yml"
        with_block = {"tool": tool}
        if fallback is not None:
            with_block["fallback"] = fallback
        path.write_text(
            yaml.safe_dump(
                {
                    "jobs": {
                        "t": {
                            "steps": [
                                {"uses": INSTALL_ACTION + "abc", "with": with_block}
                            ]
                        }
                    }
                }
            )
        )
        return [path]

    def test_scan_finds_the_ci_template_steps(self):
        steps = list(install_action_steps())
        names = {n for n, _ in steps}
        self.assertEqual(len(names), 22, "ci and release workflow per Rust crate")
        self.assertEqual(
            len([n for n in names if n.startswith("release-")]), 11, sorted(names)
        )

    def test_every_tool_entry_is_name_at_exact_version(self):
        for name, step in install_action_steps():
            for entry in action_tools(step):
                with self.subTest(file=name, tool=entry):
                    self.assertRegex(entry, _TOOL_SPEC)

    def test_fixture_unpinned_entries_are_rejected(self):
        import tempfile

        for bad in ("cargo-nextest", "cargo-nextest@latest", "cargo-nextest@0.9"):
            with tempfile.TemporaryDirectory() as tmp:
                ((_, step),) = install_action_steps(self._write(tmp, bad))
                self.assertIsNone(_TOOL_SPEC.match(action_tools(step)[0]), bad)

    def test_every_step_sets_fallback_none(self):
        for name, step in install_action_steps():
            with self.subTest(file=name):
                self.assertTrue(has_fallback_none(step))

    def test_fixture_missing_fallback_is_flagged(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            ((_, missing),) = install_action_steps(
                self._write(tmp, "x@1.2.3", fallback=None)
            )
            ((_, wrong),) = install_action_steps(
                self._write(tmp, "x@1.2.3", fallback="cargo-binstall")
            )
            ((_, good),) = install_action_steps(self._write(tmp, "x@1.2.3"))
        self.assertFalse(has_fallback_none(missing))
        self.assertFalse(has_fallback_none(wrong))
        self.assertTrue(has_fallback_none(good))

    def test_every_step_is_pinned_by_one_full_commit_sha(self):
        shas = set()
        for name, step in install_action_steps():
            with self.subTest(file=name):
                match = _ACTION_SHA.match(step["uses"])
                self.assertIsNotNone(match, step["uses"])
                shas.add(match["sha"])
        self.assertEqual(len(shas), 1, shas)

    def test_fixture_tag_pin_is_rejected(self):
        for bad in ("v2", "v2.1.0", "abc1234", "A" * 40, "a" * 39):
            self.assertIsNone(_ACTION_SHA.match(INSTALL_ACTION + bad), bad)
        self.assertIsNotNone(_ACTION_SHA.match(INSTALL_ACTION + "a" * 40))

    def test_every_step_keeps_checksum_verification_on(self):
        for name, step in install_action_steps():
            with self.subTest(file=name):
                value = (step.get("with") or {}).get("checksum", True)
                self.assertIn(value, (True, "true"))

    def test_fixture_checksum_false_is_rejected(self):
        import tempfile

        for bad in (False, "false", "no"):
            with tempfile.TemporaryDirectory() as tmp:
                path = self._write(tmp, "x@1.2.3")[0]
                doc = yaml.safe_load(path.read_text())
                doc["jobs"]["t"]["steps"][0]["with"]["checksum"] = bad
                path.write_text(yaml.safe_dump(doc))
                ((_, step),) = install_action_steps([path])
            self.assertNotIn(step["with"]["checksum"], (True, "true"), bad)

    def test_action_versions_match_installer_pins(self):
        pins = installer_pins()
        seen = set()
        for name, step in install_action_steps():
            for entry in action_tools(step):
                match = _TOOL_SPEC.match(entry)
                if not match:
                    continue  # reported by the exact-version test
                seen.add(match["name"])
                if match["name"] == AUDITABLE:
                    continue  # release-only: no local installer to agree with
                with self.subTest(file=name, tool=entry):
                    self.assertEqual(pins.get(match["name"]), {match["version"]})
        self.assertEqual(
            seen, {"cargo-nextest", "cargo-machete", "cargo-tarpaulin", AUDITABLE}
        )

    def test_release_only_tool_has_one_version(self):
        versions = {
            _TOOL_SPEC.match(entry)["version"]
            for _, step in install_action_steps()
            for entry in action_tools(step)
            if entry.startswith(AUDITABLE + "@")
        }
        self.assertEqual(len(versions), 1, versions)


class TestPyrightPins(unittest.TestCase):
    def test_every_pyright_install_is_pinned_to_one_version(self):
        sites = list(pyright_installs())
        self.assertEqual(len(sites), 17, sites)  # 9 workflow sites + 8 installers
        pins = {token for _, token in sites}
        self.assertEqual(len(pins), 1, f"pyright pinned inconsistently: {sorted(pins)}")
        (pin,) = pins
        self.assertRegex(pin, r"^pyright==\d+\.\d+\.\d+$")


class TestPythonInstallerPins(unittest.TestCase):
    """Scope: the 8 Python `install_deps.sh` files and the 8 `*-py.yml` workflows."""

    def test_every_installer_pip_argument_is_pinned(self):
        sites = list(pip_installs())
        self.assertEqual(
            len({n for n, _ in sites}),
            16,
            "an installer or workflow has no pip install",
        )
        for name, token in sites:
            with self.subTest(file=name, arg=token):
                self.assertRegex(token, _REQUIREMENT)

    def test_one_version_per_package_across_installers_and_workflows(self):
        versions = {}
        for _, token in pip_installs():
            match = _REQUIREMENT.match(token)
            if match:
                versions.setdefault(match["name"], set()).add(match["version"])
        split = {p: sorted(v) for p, v in versions.items() if len(v) > 1}
        self.assertEqual(split, {}, "a package is pinned to more than one version")

    def test_every_installer_installs_the_full_set(self):
        expected = {
            "mpmath",
            "gmpy2",
            "coverage",
            "cosmic-ray",
            "hypothesis",
            "pytest",
            "pytest-cov",
            "ruff",
            "pyright",
            "pip-audit",
        }
        by_file = {}
        for name, token in pip_installs():
            by_file.setdefault(name, set()).add(token.split("==")[0])
        for name, packages in by_file.items():
            with self.subTest(file=name):
                self.assertEqual(packages, expected)

    def test_installer_ruff_and_pyright_match_the_workflow_pins(self):
        installer = {t for _, t in pip_installs() if re.match(r"^(ruff|pyright)==", t)}
        workflow = set()
        for path in WORKFLOWS:
            for match in _PIP_INSTALL.finditer(path.read_text()):
                workflow.update(
                    t
                    for t in match.group("rest").split()
                    if re.match(r"^(ruff|pyright)==", t)
                )
        self.assertEqual(installer, workflow)


if __name__ == "__main__":
    unittest.main()
