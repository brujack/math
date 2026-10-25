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
        self.assertEqual(len(sites), 9, sites)
        pins = {token for _, token in sites}
        self.assertEqual(len(pins), 1, f"pyright pinned inconsistently: {sorted(pins)}")
        (pin,) = pins
        self.assertRegex(pin, r"^pyright==\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
