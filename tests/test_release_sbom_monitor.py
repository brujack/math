"""Run release-sbom-monitor.yml's shell steps against a fake `gh`.

The monitor used to exit 0 with only an `echo` both when no release matched a crate's
tag prefix and when a release had no SBOM asset, so a job that scanned nothing was
indistinguishable from one that scanned and found nothing. Until the first per-crate
releases on 2026-10-24 that was every job, every month.

These tests execute each step's real `run` text under `bash -e {0}` (the shell GitHub
Actions uses for a step with no `shell:` key, which has no pipefail) with a fake `gh`
first on PATH. The fake applies the step's own `--jq` filter to canned release JSON, so
the tag-prefix match is exercised rather than stubbed.
"""

import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from typing import ClassVar

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MONITOR = REPO_ROOT / ".github" / "workflows" / "release-sbom-monitor.yml"

FAKE_GH = r"""#!/usr/bin/env bash
if [[ "$1 $2" == "release list" ]]; then
    [[ "${FAKE_GH_LIST_RC:-0}" -ne 0 ]] && exit "${FAKE_GH_LIST_RC}"
    expr="."
    limit=30
    while [[ $# -gt 0 ]]; do
        [[ "$1" == "--jq" ]] && expr="$2"
        [[ "$1" == "--limit" || "$1" == "-L" ]] && limit="$2"
        shift
    done
    # gh truncates to --limit (default 30) before applying --jq.
    printf '%s' "${FAKE_RELEASES_JSON:-[]}" | jq -r --argjson n "${limit}" ".[:\$n] | ${expr}"
    exit $?
fi
if [[ "$1 $2" == "release download" ]]; then
    exit "${FAKE_GH_DOWNLOAD_RC:-0}"
fi
exit 99
"""


def monitor_step(name):
    steps = yaml.safe_load(MONITOR.read_text())["jobs"]["monitor"]["steps"]
    for step in steps:
        if step.get("name") == name:
            return step
    raise AssertionError(f"no step named {name!r} in {MONITOR.name}")


def releases(*tags):
    return json.dumps([{"tagName": tag} for tag in tags])


class StepRun:
    def __init__(self, returncode, stdout, outputs, summary):
        self.returncode = returncode
        self.stdout = stdout
        self.outputs = outputs
        self.summary = summary


def run_step(name, env):
    """Run one monitor step's `run` text as Actions would; return its observable effects."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "gh"
        fake.write_text(FAKE_GH)
        fake.chmod(0o755)
        script = tmp_path / "step.sh"
        script.write_text(monitor_step(name)["run"])
        output_file = tmp_path / "output"
        summary_file = tmp_path / "summary"
        output_file.touch()
        summary_file.touch()
        full_env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HOME": tmp,
            "GITHUB_OUTPUT": str(output_file),
            "GITHUB_STEP_SUMMARY": str(summary_file),
            **env,
        }
        proc = subprocess.run(
            ["bash", "-e", str(script)],
            cwd=tmp,
            env=full_env,
            capture_output=True,
            text=True,
            check=False,
        )
        outputs = dict(
            line.split("=", 1)
            for line in output_file.read_text().splitlines()
            if "=" in line
        )
        return StepRun(
            proc.returncode,
            proc.stdout + proc.stderr,
            outputs,
            summary_file.read_text(),
        )


RESOLVE = "Resolve latest matching release tag"
DOWNLOAD = "Download SBOM asset"


class TestResolveLatestRelease(unittest.TestCase):
    def test_matching_release_sets_tag(self):
        result = run_step(
            RESOLVE,
            {
                "TAG_PATTERN": "sq-v",
                "FAKE_RELEASES_JSON": releases("pi-v0.1.0", "sq-v0.2.0", "sq-v0.1.0"),
            },
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.outputs.get("found"), "true")
        self.assertEqual(result.outputs.get("tag"), "sq-v0.2.0")
        self.assertNotIn("::warning", result.stdout)

    def test_no_matching_release_warns_and_writes_summary(self):
        result = run_step(
            RESOLVE,
            {
                "TAG_PATTERN": "sq-v",
                "FAKE_RELEASES_JSON": releases("v0.1.0", "pi-v0.1.0"),
            },
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.outputs.get("found"), "false")
        self.assertIn("::warning", result.stdout)
        self.assertIn("sq-v", result.summary)

    def test_no_releases_at_all_warns(self):
        result = run_step(RESOLVE, {"TAG_PATTERN": "sq-v", "FAKE_RELEASES_JSON": "[]"})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.outputs.get("found"), "false")
        self.assertIn("::warning", result.stdout)

    def test_prefix_is_not_a_substring_match(self):
        # "e-v" must not match "twin-primes-v..." style tags that merely contain it.
        result = run_step(
            RESOLVE,
            {
                "TAG_PATTERN": "e-v",
                "FAKE_RELEASES_JSON": releases("twin-primes-v0.1.0"),
            },
        )
        self.assertEqual(result.outputs.get("found"), "false")

    def test_release_list_failure_fails_the_step(self):
        # Without pipefail, `gh release list ... | head -1` hides gh's exit status and
        # an API failure would read as "no release": a warning instead of a red job.
        result = run_step(
            RESOLVE,
            {"TAG_PATTERN": "sq-v", "FAKE_GH_LIST_RC": "1"},
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotEqual(result.outputs.get("found"), "false")

    def test_lists_more_than_fifty_releases(self):
        # 11 crates outgrow a 50-release window after a few versions each, and the
        # oldest crate's latest release would then read as "no release".
        tags = [f"pi-v0.{n}.0" for n in range(60, 0, -1)] + ["sq-v0.1.0"]
        result = run_step(
            RESOLVE, {"TAG_PATTERN": "sq-v", "FAKE_RELEASES_JSON": releases(*tags)}
        )
        self.assertEqual(result.outputs.get("tag"), "sq-v0.1.0", result.stdout)


class TestDownloadSbom(unittest.TestCase):
    ENV: ClassVar[dict[str, str]] = {"LATEST_TAG": "sq-v0.1.0", "BINARY_NAME": "sq"}

    def test_present_sbom_sets_present(self):
        result = run_step(DOWNLOAD, dict(self.ENV))
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.outputs.get("present"), "true")

    def test_missing_sbom_fails_the_step_with_an_error_and_summary(self):
        result = run_step(DOWNLOAD, {**self.ENV, "FAKE_GH_DOWNLOAD_RC": "1"})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("::error", result.stdout)
        self.assertIn("sq-v0.1.0", result.summary)
        self.assertNotEqual(result.outputs.get("present"), "true")


if __name__ == "__main__":
    unittest.main()
