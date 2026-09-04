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

Every per-workflow assertion below parses the file with `yaml.safe_load` and asserts
on the resulting structure rather than searching raw file text. Two independent
review rounds found the same class of defect in a text/substring-based first draft:

- A raw `"needle" in content` check is satisfied by a needle sitting inside a
  YAML *comment*, or re-indented into an adjacent block-scalar value where GitHub
  reads it as data rather than as the key it looks like. Both leave the real
  workflow broken while every assertion stays green.
- The inverse defect is just as real: the same raw-text check can go RED on a
  *correct* edit -- e.g. a comment mentioning "release-sign.yml" as history, or
  the string "cargo build --release" appearing inside an unrelated comment --
  because the check cannot distinguish "this text is a directive" from "this text
  is human prose that happens to contain the directive's words".

Parsing first and asserting on the parsed value fixes both directions at once:
a comment is not part of any parsed field, so it can neither fake a directive nor
break on prose that mentions one.
"""

import glob
import pathlib
import re
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

_WORKFLOW_NAME_RE = re.compile(r"^release-(.+)-rs\.yml$")

# Matches the "Generate SHA256 checksum" step's `(cd <path> && sha256sum <binary>)`
# text, which is the one place in each workflow that already names both the exact
# on-disk directory and the exact binary filename -- deriving from it means this
# test does not have to hardcode a "<name>/<name>-rs/target/release" path
# convention of its own. Applied to that ONE step's parsed `run` value, not to the
# whole file, so a comment elsewhere in the file cannot feed it a false match.
_SHA256_STEP_RE = re.compile(r"\(cd (\S+) && sha256sum (\S+)\)")


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


def parse_workflow(content):
    """Parse workflow YAML text into its structure. Raises yaml.YAMLError on malformed input."""
    return yaml.safe_load(content)


def load_workflow(path):
    """Read and parse a workflow file."""
    return parse_workflow(path.read_text())


def release_steps(workflow):
    """Return the `jobs.release.steps` list of a parsed workflow."""
    return workflow["jobs"]["release"]["steps"]


def find_step_index_by_uses_prefix(steps, prefix):
    """Return the index of the first step whose `uses` starts with prefix, or None."""
    for index, step in enumerate(steps):
        if isinstance(step, dict) and str(step.get("uses", "")).startswith(prefix):
            return index
    return None


def find_step_index_by_name(steps, name):
    """Return the index of the first step whose `name` equals name, or None."""
    for index, step in enumerate(steps):
        if isinstance(step, dict) and step.get("name") == name:
            return index
    return None


def require_index(index, message):
    """Return index, or raise AssertionError(message) if it is None.

    A plain `raise` -- unlike `self.assertIsNotNone` -- is a control-flow
    terminator pyright understands, so every call site gets back a real `int`
    rather than `int | None`.
    """
    if index is None:
        raise AssertionError(message)
    return index


def sha256_checksum_target(steps):
    """Return (directory, binary) parsed from the SHA256 checksum step's run text.

    Raises ValueError if the step is missing, or if its run text does not match
    the expected `(cd <dir> && sha256sum <binary>)` shape -- every release
    workflow in this repo has generated a checksum this way since before this
    change, so either absence means something more fundamental moved.
    """
    index = find_step_index_by_name(steps, "Generate SHA256 checksum")
    if index is None:
        raise ValueError("no 'Generate SHA256 checksum' step found")
    run_text = steps[index].get("run") or ""
    match = _SHA256_STEP_RE.search(run_text)
    if match is None:
        raise ValueError(
            "'Generate SHA256 checksum' step's run text does not match "
            "'(cd <dir> && sha256sum <binary>)'"
        )
    return match.group(1), match.group(2)


def files_field_as_list(with_block):
    """Return the softprops `files:` input as a flat list of stripped entries.

    Accepts either YAML shape -- a literal block scalar (parsed as one string with
    embedded newlines) or a flow sequence (parsed as a list) -- so a syntactically
    valid rewrite of the input never raises; it just produces the wrong list, which
    the caller's own equality assertion reports cleanly.
    """
    files_value = with_block.get("files")
    if isinstance(files_value, str):
        return [line.strip() for line in files_value.splitlines() if line.strip()]
    if isinstance(files_value, list):
        return [str(item).strip() for item in files_value if str(item).strip()]
    return []


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

    def test_parse_workflow_raises_on_malformed_yaml(self):
        with self.assertRaises(yaml.YAMLError):
            parse_workflow("jobs:\n  release:\n  steps: [\n")

    def test_parse_workflow_ignores_comments(self):
        workflow = parse_workflow(
            "# a comment mentioning cargo build --release\njobs: {}\n"
        )
        self.assertEqual(workflow, {"jobs": {}})

    def test_release_steps_returns_the_steps_list(self):
        workflow = {"jobs": {"release": {"steps": [{"name": "a"}]}}}
        self.assertEqual(release_steps(workflow), [{"name": "a"}])

    def test_find_step_index_by_uses_prefix_on_empty_list(self):
        self.assertIsNone(find_step_index_by_uses_prefix([], "foo"))

    def test_find_step_index_by_uses_prefix_finds_match(self):
        steps = [{"run": "x"}, {"uses": "foo/bar@1"}]
        self.assertEqual(find_step_index_by_uses_prefix(steps, "foo/bar"), 1)

    def test_find_step_index_by_uses_prefix_skips_step_with_no_uses(self):
        steps = [{"run": "x"}]
        self.assertIsNone(find_step_index_by_uses_prefix(steps, "foo"))

    def test_find_step_index_by_name_on_empty_list(self):
        self.assertIsNone(find_step_index_by_name([], "Build"))

    def test_find_step_index_by_name_finds_match(self):
        steps = [{"name": "Checkout"}, {"name": "Build"}]
        self.assertEqual(find_step_index_by_name(steps, "Build"), 1)

    def test_find_step_index_by_name_skips_step_with_no_name(self):
        steps = [{"uses": "actions/checkout@v7"}]
        self.assertIsNone(find_step_index_by_name(steps, "Build"))

    def test_require_index_raises_on_none(self):
        with self.assertRaises(AssertionError):
            require_index(None, "missing step")

    def test_require_index_returns_zero(self):
        # 0 is falsy but a legitimate index -- must not be treated as "missing".
        self.assertEqual(require_index(0, "missing step"), 0)

    def test_sha256_checksum_target_raises_on_missing_step(self):
        with self.assertRaises(ValueError):
            sha256_checksum_target([{"name": "Other step", "run": "echo hi"}])

    def test_sha256_checksum_target_raises_on_unrecognized_run_shape(self):
        steps = [{"name": "Generate SHA256 checksum", "run": "echo not-a-checksum"}]
        with self.assertRaises(ValueError):
            sha256_checksum_target(steps)

    def test_sha256_checksum_target_parses_directory_and_binary(self):
        steps = [
            {
                "name": "Generate SHA256 checksum",
                "run": "(cd amicable/amicable-rs/target/release && sha256sum amicable) > x\n",
            }
        ]
        directory, binary = sha256_checksum_target(steps)
        self.assertEqual(directory, "amicable/amicable-rs/target/release")
        self.assertEqual(binary, "amicable")

    def test_files_field_as_list_on_missing_key(self):
        self.assertEqual(files_field_as_list({}), [])

    def test_files_field_as_list_handles_block_scalar_string(self):
        self.assertEqual(
            files_field_as_list({"files": "a/b\na/b.sha256\n"}), ["a/b", "a/b.sha256"]
        )

    def test_files_field_as_list_handles_flow_sequence(self):
        # A syntactically valid alternative to the block-scalar form the real
        # workflows use -- must not raise, per the reviewer's F4 finding.
        self.assertEqual(
            files_field_as_list({"files": ["a/b", "a/b.sha256"]}), ["a/b", "a/b.sha256"]
        )

    def test_files_field_as_list_drops_blank_lines(self):
        self.assertEqual(
            files_field_as_list({"files": "a/b\n\n\na/b.sha256\n"}),
            ["a/b", "a/b.sha256"],
        )


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
                steps = release_steps(load_workflow(path))
                build_index = require_index(
                    find_step_index_by_name(steps, "Build release binary"),
                    f"{path.name} missing 'Build release binary' step",
                )
                build_run = (steps[build_index].get("run") or "").strip()
                self.assertEqual(
                    build_run,
                    "cargo auditable build --release",
                    f"{path.name} 'Build release binary' step must run "
                    "'cargo auditable build --release' exactly",
                )
                for index, step in enumerate(steps):
                    run_value = (
                        (step.get("run") or "").strip()
                        if isinstance(step, dict)
                        else ""
                    )
                    self.assertNotEqual(
                        run_value,
                        "cargo build --release",
                        f"{path.name} step {index} runs bare 'cargo build --release'",
                    )

    def test_installs_cargo_auditable(self):
        for path in self.workflows:
            with self.subTest(workflow=path.name):
                steps = release_steps(load_workflow(path))
                install_index = require_index(
                    find_step_index_by_name(steps, "Install cargo-auditable"),
                    f"{path.name} missing 'Install cargo-auditable' step",
                )
                build_index = require_index(
                    find_step_index_by_name(steps, "Build release binary"),
                    f"{path.name} missing 'Build release binary' step",
                )
                install_run = (steps[install_index].get("run") or "").strip()
                self.assertEqual(
                    install_run,
                    "cargo install cargo-auditable --locked",
                    f"{path.name} 'Install cargo-auditable' step must run the "
                    "exact locked install command",
                )
                self.assertLess(
                    install_index,
                    build_index,
                    f"{path.name} must install cargo-auditable BEFORE building",
                )

    def test_references_sbom_sign_composite_action(self):
        for path in self.workflows:
            with self.subTest(workflow=path.name):
                steps = release_steps(load_workflow(path))
                require_index(
                    find_step_index_by_uses_prefix(
                        steps, "./.github/actions/sbom-sign"
                    ),
                    f"{path.name} must invoke the sbom-sign composite action",
                )

    def test_no_release_sign_reusable_workflow_or_sign_job(self):
        for path in self.workflows:
            with self.subTest(workflow=path.name):
                workflow = load_workflow(path)
                self.assertNotIn(
                    "sign",
                    workflow.get("jobs", {}),
                    f"{path.name} must not declare a separate 'sign:' job",
                )
                for index, step in enumerate(release_steps(workflow)):
                    uses = str(step.get("uses", "")) if isinstance(step, dict) else ""
                    self.assertNotIn(
                        "release-sign.yml",
                        uses,
                        f"{path.name} step {index} still references the retired "
                        "release-sign.yml",
                    )

    def test_fail_on_unmatched_files_is_set(self):
        for path in self.workflows:
            with self.subTest(workflow=path.name):
                steps = release_steps(load_workflow(path))
                release_index = require_index(
                    find_step_index_by_uses_prefix(
                        steps, "softprops/action-gh-release"
                    ),
                    f"{path.name} missing the softprops/action-gh-release step",
                )
                with_block = steps[release_index].get("with") or {}
                self.assertIs(
                    with_block.get("fail_on_unmatched_files"),
                    True,
                    f"{path.name} must set fail_on_unmatched_files: true on the "
                    "release upload -- that input defaults to false, so a "
                    "commented-out or misindented key silently publishes a "
                    "partial release",
                )

    def test_files_block_carries_all_four_artifacts(self):
        # The four-artifact set is hardcoded deliberately. Deriving it from the composite
        # action's inputs or from scripts/sbom-sign.sh's output filenames would be circular --
        # the test would agree with whatever those produce.
        # INVALIDATING CONDITION: a fifth artifact (an attestation, a second signature format)
        # added to the eleven workflows leaves this test green while asserting an incomplete set.
        for path in self.workflows:
            with self.subTest(workflow=path.name):
                steps = release_steps(load_workflow(path))
                release_index = require_index(
                    find_step_index_by_uses_prefix(
                        steps, "softprops/action-gh-release"
                    ),
                    f"{path.name} missing the softprops/action-gh-release step",
                )
                with_block = steps[release_index].get("with") or {}
                directory, binary = sha256_checksum_target(steps)
                expected = {
                    f"{directory}/{binary}",
                    f"{directory}/{binary}.sha256",
                    f"{directory}/{binary}.sbom.spdx.json",
                    f"{directory}/{binary}.bundle",
                }
                actual = set(files_field_as_list(with_block))
                self.assertEqual(
                    expected & actual,
                    expected,
                    f"{path.name} files: entry missing artifacts; "
                    f"expected {sorted(expected)}, found {sorted(actual)}",
                )

    def test_sbom_sign_inputs_match_this_workflows_binary(self):
        # A drift-detector for the copy-paste class eleven near-identical files
        # invite: binary_path/binary_name are the only per-file-varying values the
        # sbom-sign step introduces. Cross-checked against TWO independent sources
        # -- the filename (binary_name_from_filename) and the pre-existing SHA256
        # step (sha256_checksum_target) -- neither of which this step's own `with:`
        # block can influence, so a copy-paste error from a sibling workflow cannot
        # satisfy both checks at once.
        for path in self.workflows:
            with self.subTest(workflow=path.name):
                steps = release_steps(load_workflow(path))
                sbom_index = require_index(
                    find_step_index_by_uses_prefix(
                        steps, "./.github/actions/sbom-sign"
                    ),
                    f"{path.name} missing sbom-sign step",
                )
                sbom_with = steps[sbom_index].get("with") or {}
                expected_binary = binary_name_from_filename(path)
                expected_directory, sha_binary = sha256_checksum_target(steps)
                self.assertEqual(
                    sha_binary,
                    expected_binary,
                    f"{path.name} SHA256 step binary ({sha_binary!r}) disagrees "
                    f"with the filename-derived binary ({expected_binary!r})",
                )
                self.assertEqual(
                    sbom_with.get("binary_name"),
                    expected_binary,
                    f"{path.name} sbom-sign binary_name must match this "
                    f"workflow's own binary ({expected_binary!r})",
                )
                self.assertEqual(
                    sbom_with.get("binary_path"),
                    expected_directory,
                    f"{path.name} sbom-sign binary_path must match the SHA256 "
                    f"step's own target directory ({expected_directory!r})",
                )

    def test_tag_creation_happens_after_sbom_sign(self):
        for path in self.workflows:
            with self.subTest(workflow=path.name):
                steps = release_steps(load_workflow(path))
                sbom_index = require_index(
                    find_step_index_by_uses_prefix(
                        steps, "./.github/actions/sbom-sign"
                    ),
                    f"{path.name} missing sbom-sign step",
                )
                tag_index = require_index(
                    find_step_index_by_name(steps, "Create and push tag"),
                    f"{path.name} missing 'Create and push tag' step",
                )
                self.assertGreater(
                    tag_index,
                    sbom_index,
                    f"{path.name} must create the tag AFTER sbom-sign, not before "
                    "-- a signing failure must not leave a pushed tag with no "
                    "release",
                )


class TestNoRepoWideReleaseSignReferences(unittest.TestCase):
    def test_no_workflow_references_release_sign(self):
        offenders = []
        for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
            if path.name == "release-sign.yml":
                continue
            workflow = parse_workflow(path.read_text())
            jobs = workflow.get("jobs", {}) if isinstance(workflow, dict) else {}
            for job in jobs.values():
                if isinstance(job, dict) and "release-sign.yml" in str(
                    job.get("uses", "")
                ):
                    offenders.append(path.name)
                for step in job.get("steps", []) if isinstance(job, dict) else []:
                    if isinstance(step, dict) and "release-sign.yml" in str(
                        step.get("uses", "")
                    ):
                        offenders.append(path.name)
        self.assertEqual(
            offenders,
            [],
            f"these workflows still reference the retired release-sign.yml: {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
