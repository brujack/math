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
        self.assertGreater(len(sites), 40, "scan found too few cargo install lines")
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
