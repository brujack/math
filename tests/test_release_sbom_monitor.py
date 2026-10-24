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
    # Real gh exits 1 ("no assets to download") when the pattern matches no asset
    # of that release, so succeed only for a "<tag>/<asset>" listed in FAKE_ASSETS.
    tag="$3" pattern=""
    while [[ $# -gt 0 ]]; do
        [[ "$1" == "--pattern" || "$1" == "-p" ]] && pattern="$2"
        shift
    done
    for asset in ${FAKE_ASSETS:-}; do
        [[ "${asset}" == "${tag}/${pattern}" ]] && exit 0
    done
    echo "no assets to download" >&2
    exit 1
fi
if [[ "$1 $2" == "issue list" ]]; then
    printf '%s\n' "${FAKE_EXISTING_ISSUE:-}"
    exit 0
fi
if [[ "$1 $2" == "issue create" ]]; then
    args="$*"
    printf '%s\n' "${args//$'\n'/ }" >> "${FAKE_GH_LOG}"  # one line per call
    exit 0
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
    def __init__(self, returncode, stdout, outputs, summary, gh_log):
        self.gh_log = gh_log
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
        gh_log = tmp_path / "gh.log"
        output_file.touch()
        summary_file.touch()
        gh_log.touch()
        full_env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "HOME": tmp,
            "GITHUB_OUTPUT": str(output_file),
            "GITHUB_STEP_SUMMARY": str(summary_file),
            "FAKE_GH_LOG": str(gh_log),
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
            gh_log.read_text(),
        )


RESOLVE = "Resolve latest matching release tag"
DOWNLOAD = "Download SBOM asset"
FILTER = "Filter Critical/High and file issues"


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
        result = run_step(
            DOWNLOAD,
            {**self.ENV, "FAKE_ASSETS": "sq-v0.1.0/sq sq-v0.1.0/sq.sbom.spdx.json"},
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.outputs.get("present"), "true")

    def test_missing_sbom_fails_the_step_with_an_error_and_summary(self):
        result = run_step(DOWNLOAD, {**self.ENV, "FAKE_ASSETS": "sq-v0.1.0/sq"})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("::error", result.stdout)
        self.assertIn("sq-v0.1.0", result.summary)
        self.assertNotEqual(result.outputs.get("present"), "true")

    def test_sbom_on_a_different_release_does_not_count(self):
        result = run_step(
            DOWNLOAD, {**self.ENV, "FAKE_ASSETS": "sq-v0.0.9/sq.sbom.spdx.json"}
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)


def scan_json(tmp, *matches):
    path = pathlib.Path(tmp) / "scan.json"
    path.write_text(json.dumps({"matches": list(matches)}))
    return str(path)


def match(cve, severity):
    return {
        "vulnerability": {
            "id": cve,
            "severity": severity,
            "fix": {"versions": ["1.2.4"]},
        },
        "artifact": {"name": "libfoo", "version": "1.2.3"},
    }


class TestFilterFindings(unittest.TestCase):
    ENV: ClassVar[dict[str, str]] = {"LATEST_TAG": "sq-v0.1.0", "BINARY_NAME": "sq"}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_scan_files_nothing_and_records_the_scan(self):
        result = run_step(FILTER, {**self.ENV, "SCAN_JSON": scan_json(self.tmp)})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.gh_log, "")
        self.assertIn("sq-v0.1.0", result.summary)
        self.assertIn("scanned", result.summary)

    def test_high_finding_files_one_issue(self):
        path = scan_json(self.tmp, match("CVE-1", "High"), match("CVE-2", "Low"))
        result = run_step(FILTER, {**self.ENV, "SCAN_JSON": path})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(len(result.gh_log.splitlines()), 1, result.gh_log)
        self.assertIn("CVE-1 in sq sq-v0.1.0", result.gh_log)

    def test_already_open_issue_is_not_duplicated(self):
        path = scan_json(self.tmp, match("CVE-1", "Critical"))
        result = run_step(
            FILTER, {**self.ENV, "SCAN_JSON": path, "FAKE_EXISTING_ISSUE": "7"}
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.gh_log, "")

    def test_missing_scan_output_fails_the_step(self):
        # Without pipefail, `jq ... missing-file | while` exits 0 with zero findings:
        # a scan that produced nothing would read as a clean scan.
        missing = str(pathlib.Path(self.tmp) / "absent.json")
        result = run_step(FILTER, {**self.ENV, "SCAN_JSON": missing})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("::error", result.stdout)

    def test_empty_scan_output_path_fails_the_step(self):
        result = run_step(FILTER, {**self.ENV, "SCAN_JSON": ""})
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_malformed_scan_output_fails_the_step(self):
        path = pathlib.Path(self.tmp) / "bad.json"
        path.write_text("{not json")
        result = run_step(FILTER, {**self.ENV, "SCAN_JSON": str(path)})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(result.gh_log, "")


if __name__ == "__main__":
    unittest.main()
