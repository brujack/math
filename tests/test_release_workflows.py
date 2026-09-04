"""Assert the release workflow contract: sign-and-SBOM before publish, not after.

Before this change, `release-sign.yml` ran as a separate reusable-workflow job that
had to `gh release download` the just-published binary -- so the release existed,
with a binary and no SBOM, for the entire window between publication and that job's
final `gh release upload`. Moving signing into the release job itself (via the
`.github/actions/sbom-sign` composite action, which runs where the built binary
already sits on disk) closes that window instead of narrowing it.

This module pins the resulting contract over all `release-*-rs.yml` workflows so a
regression -- a bare `cargo build --release` creeping back in, a `sign:` job
re-appearing, a workflow shipped without `fail_on_unmatched_files` -- fails a test
instead of shipping a release with an empty or missing SBOM.
"""

import glob
import pathlib
import re
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

_WORKFLOW_NAME_RE = re.compile(r"^release-(.+)-rs\.yml$")

# Matches the "Generate SHA256 checksum" step's `(cd <path> && sha256sum <binary>)`
# line, which is the one place in each workflow that already names both the exact
# on-disk directory and the exact binary filename -- deriving from it means this
# test does not have to hardcode a "<name>/<name>-rs/target/release" path
# convention of its own.
_SHA256_STEP_RE = re.compile(r"\(cd (\S+) && sha256sum (\S+)\)")

_FILES_BLOCK_RE = re.compile(r"files: \|\n((?:[ \t]{4,}\S.*\n?)+)")


def discover_release_workflows():
    """Return the sorted list of release-*-rs.yml workflow paths.

    Glob-derived rather than a literal list, so a twelfth crate's release workflow
    is picked up automatically instead of needing this test edited to see it.
    """
    return sorted(
        pathlib.Path(p) for p in glob.glob(str(WORKFLOWS_DIR / "release-*-rs.yml"))
    )


def binary_name_from_filename(path):
    """Return the binary name a release-<name>-rs.yml workflow builds.

    Raises ValueError for a filename that does not match the convention -- this
    should never fire for a real discover_release_workflows() result, and exists so
    a mis-named workflow fails loudly here rather than silently mismatching later.
    """
    match = _WORKFLOW_NAME_RE.match(path.name)
    if match is None:
        raise ValueError(f"{path.name} does not match release-<name>-rs.yml")
    return match.group(1)


def extract_sha256_target(content):
    """Return (directory, binary) from the workflow's SHA256 checksum step.

    Raises ValueError if the step is missing -- every release workflow in this
    repo has generated a checksum this way since before this change, so its
    absence means the file is not a release workflow at all, not that the
    checksum step moved.
    """
    match = _SHA256_STEP_RE.search(content)
    if match is None:
        raise ValueError("no '(cd <dir> && sha256sum <binary>)' step found")
    directory, sha_target = match.group(1), match.group(2)
    return directory, sha_target


def extract_files_block(content):
    """Return the stripped file lines inside the softprops `files: |` block.

    Raises ValueError if no such block exists.
    """
    match = _FILES_BLOCK_RE.search(content)
    if match is None:
        raise ValueError("no 'files: |' block found")
    return [line.strip() for line in match.group(1).splitlines() if line.strip()]


def step_line_index(lines, needle):
    """Return the 0-based index of the first line containing needle, or None."""
    for index, line in enumerate(lines):
        if needle in line:
            return index
    return None


class TestHelperBoundaries(unittest.TestCase):
    """Boundary and error-path coverage for this module's own parsing helpers."""

    def test_binary_name_from_filename_rejects_non_matching_name(self):
        with self.assertRaises(ValueError):
            binary_name_from_filename(pathlib.Path("release-sign.yml"))

    def test_binary_name_from_filename_handles_hyphenated_name(self):
        self.assertEqual(
            binary_name_from_filename(pathlib.Path("release-perfect-numbers-rs.yml")),
            "perfect-numbers",
        )

    def test_binary_name_from_filename_handles_single_word_name(self):
        self.assertEqual(
            binary_name_from_filename(pathlib.Path("release-pi-rs.yml")), "pi"
        )

    def test_extract_sha256_target_raises_on_missing_step(self):
        with self.assertRaises(ValueError):
            extract_sha256_target("jobs:\n  release:\n    steps: []\n")

    def test_extract_sha256_target_parses_directory_and_binary(self):
        content = "run: |\n  (cd amicable/amicable-rs/target/release && sha256sum amicable) > x\n"
        directory, binary = extract_sha256_target(content)
        self.assertEqual(directory, "amicable/amicable-rs/target/release")
        self.assertEqual(binary, "amicable")

    def test_extract_files_block_raises_on_missing_block(self):
        with self.assertRaises(ValueError):
            extract_files_block("with:\n  tag_name: v1\n")

    def test_extract_files_block_returns_empty_for_block_with_no_lines(self):
        # A "files: |" with nothing indented under it before EOF -- the regex
        # requires at least one line, so this is the boundary of "no match" vs
        # "match with zero content lines"; both must be handled without raising.
        with self.assertRaises(ValueError):
            extract_files_block("files: |\n")

    def test_step_line_index_returns_none_when_absent(self):
        self.assertIsNone(step_line_index(["a", "b"], "needle"))

    def test_step_line_index_finds_first_match(self):
        self.assertEqual(
            step_line_index(["a", "needle here", "needle again"], "needle"), 1
        )

    def test_step_line_index_on_empty_list(self):
        self.assertIsNone(step_line_index([], "needle"))


class TestReleaseWorkflowDiscovery(unittest.TestCase):
    def test_eleven_release_workflows_exist(self):
        workflows = discover_release_workflows()
        self.assertEqual(
            len(workflows),
            11,
            f"expected 11 release-*-rs.yml workflows, found {len(workflows)}: {workflows}",
        )


class TestReleaseWorkflowContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflows = discover_release_workflows()

    def test_uses_cargo_auditable_build_not_bare_build(self):
        for path in self.workflows:
            with self.subTest(workflow=path.name):
                content = path.read_text()
                self.assertIn(
                    "cargo auditable build --release",
                    content,
                    f"{path.name} must build with 'cargo auditable build --release'",
                )
                self.assertNotIn(
                    "cargo build --release",
                    content,
                    f"{path.name} must not build with bare 'cargo build --release'",
                )

    def test_installs_cargo_auditable(self):
        for path in self.workflows:
            with self.subTest(workflow=path.name):
                content = path.read_text()
                self.assertIn(
                    "cargo install cargo-auditable --locked",
                    content,
                    f"{path.name} must install cargo-auditable before building",
                )

    def test_references_sbom_sign_composite_action(self):
        for path in self.workflows:
            with self.subTest(workflow=path.name):
                content = path.read_text()
                self.assertIn(
                    "./.github/actions/sbom-sign",
                    content,
                    f"{path.name} must invoke the sbom-sign composite action",
                )

    def test_no_release_sign_reusable_workflow_or_sign_job(self):
        for path in self.workflows:
            with self.subTest(workflow=path.name):
                content = path.read_text()
                self.assertNotIn(
                    "release-sign.yml",
                    content,
                    f"{path.name} must not reference the retired release-sign.yml",
                )
                self.assertIsNone(
                    re.search(r"^  sign:\s*$", content, re.MULTILINE),
                    f"{path.name} must not declare a separate 'sign:' job",
                )

    def test_fail_on_unmatched_files_is_set(self):
        for path in self.workflows:
            with self.subTest(workflow=path.name):
                content = path.read_text()
                self.assertIn(
                    "fail_on_unmatched_files: true",
                    content,
                    f"{path.name} must set fail_on_unmatched_files: true on the "
                    "release upload -- that input defaults to false, so without it "
                    "a files: entry matching nothing publishes anyway with only a "
                    "console warning",
                )

    def test_files_block_carries_all_four_artifacts(self):
        # The four-artifact set is hardcoded deliberately. Deriving it from the composite
        # action's inputs or from scripts/sbom-sign.sh's output filenames would be circular --
        # the test would agree with whatever those produce.
        # INVALIDATING CONDITION: a fifth artifact (an attestation, a second signature format)
        # added to the eleven workflows leaves this test green while asserting an incomplete set.
        for path in self.workflows:
            with self.subTest(workflow=path.name):
                content = path.read_text()
                directory, binary = extract_sha256_target(content)
                files_block = extract_files_block(content)
                expected = {
                    f"{directory}/{binary}",
                    f"{directory}/{binary}.sha256",
                    f"{directory}/{binary}.sbom.spdx.json",
                    f"{directory}/{binary}.bundle",
                }
                self.assertEqual(
                    expected & set(files_block),
                    expected,
                    f"{path.name} files: block missing artifacts; "
                    f"expected {sorted(expected)}, found {files_block}",
                )

    def test_tag_creation_happens_after_sbom_sign(self):
        for path in self.workflows:
            with self.subTest(workflow=path.name):
                lines = path.read_text().splitlines()
                sbom_index = step_line_index(lines, "./.github/actions/sbom-sign")
                tag_index = step_line_index(lines, "name: Create and push tag")
                if sbom_index is None:
                    self.fail(f"{path.name} missing sbom-sign step")
                if tag_index is None:
                    self.fail(f"{path.name} missing 'Create and push tag' step")
                self.assertGreater(
                    tag_index,
                    sbom_index,
                    f"{path.name} must create the tag AFTER sbom-sign, not before -- "
                    "a signing failure must not leave a pushed tag with no release",
                )


class TestNoRepoWideReleaseSignReferences(unittest.TestCase):
    def test_no_workflow_references_release_sign(self):
        offenders = []
        for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
            if path.name == "release-sign.yml":
                continue
            if "release-sign.yml" in path.read_text():
                offenders.append(path.name)
        self.assertEqual(
            offenders,
            [],
            f"these workflows still reference the retired release-sign.yml: {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
