"""Behaviour of scripts/pip_audit_advisory.py against a fake `pip-audit`.

pip-audit stays advisory (ADR-0016), but `continue-on-error: true` made every outcome
green: a crash, a run that audited nothing, and a run that found CVEs all looked the
same as a clean audit. The wrapper keeps findings non-blocking while making them
visible, and fails only when the audit itself did not happen.

The fake writes the JSON shapes pip-audit 2.10.1 produces (measured 2026-10-24): a
vulnerable package carries `vulns`, an unresolvable one carries `skip_reason` with exit
status 0, and a usage error exits 2 without writing the output file.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "pip_audit_advisory.py"

FAKE_PIP_AUDIT = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >> "${FAKE_CALLS}"
out=""
while [[ $# -gt 0 ]]; do
    [[ "$1" == "-o" || "$1" == "--output" ]] && out="$2"
    shift
done
if [[ -n "${FAKE_JSON+set}" && -n "${out}" ]]; then
    printf '%s' "${FAKE_JSON}" > "${out}"
fi
exit "${FAKE_RC:-0}"
"""

CLEAN = {
    "dependencies": [{"name": "ruff", "version": "0.16.4", "vulns": []}],
    "fixes": [],
}
VULNERABLE = {
    "dependencies": [
        {"name": "ruff", "version": "0.16.4", "vulns": []},
        {
            "name": "requests",
            "version": "2.19.0",
            "vulns": [
                {
                    "id": "PYSEC-2018-28",
                    "fix_versions": ["2.20.0"],
                    "aliases": ["CVE-2018-18074"],
                }
            ],
        },
    ],
    "fixes": [],
}
SKIPPED = {
    "dependencies": [
        {"name": "ruff", "version": "0.16.4", "vulns": []},
        {
            "name": "localpkg",
            "skip_reason": "Dependency not found on PyPI and could not be audited",
        },
    ],
    "fixes": [],
}


class Run:
    def __init__(self, returncode, output, summary, calls):
        self.returncode = returncode
        self.output = output
        self.summary = summary
        self.calls = calls


def run_advisory(env, args=()):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "pip-audit"
        fake.write_text(FAKE_PIP_AUDIT)
        fake.chmod(0o755)
        summary = tmp_path / "summary"
        summary.touch()
        calls = tmp_path / "calls"
        calls.touch()
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=tmp,
            env={
                "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                "GITHUB_STEP_SUMMARY": str(summary),
                "FAKE_CALLS": str(calls),
                **env,
            },
            capture_output=True,
            text=True,
            check=False,
        )
        return Run(
            proc.returncode,
            proc.stdout + proc.stderr,
            summary.read_text(),
            calls.read_text(),
        )


class TestPipAuditAdvisory(unittest.TestCase):
    def test_clean_audit_passes_and_records_the_count(self):
        result = run_advisory({"FAKE_JSON": json.dumps(CLEAN)})
        self.assertEqual(result.returncode, 0, result.output)
        self.assertNotIn("::warning", result.output)
        self.assertIn(
            "1 packages audited, 0 vulnerabilities, 0 skipped", result.summary
        )

    def test_vulnerabilities_warn_but_do_not_fail(self):
        result = run_advisory({"FAKE_JSON": json.dumps(VULNERABLE), "FAKE_RC": "1"})
        self.assertEqual(result.returncode, 0, result.output)
        self.assertIn("::warning", result.output)
        self.assertIn("requests 2.19.0 PYSEC-2018-28", result.output)
        self.assertIn("2.20.0", result.output)
        self.assertIn("1 vulnerabilities", result.summary)

    def test_skipped_dependency_warns(self):
        # pip-audit exits 0 here and prints "No known vulnerabilities found".
        result = run_advisory({"FAKE_JSON": json.dumps(SKIPPED)})
        self.assertEqual(result.returncode, 0, result.output)
        self.assertIn("::warning", result.output)
        self.assertIn("localpkg", result.output)
        self.assertIn("1 skipped", result.summary)

    def test_crash_without_output_fails(self):
        result = run_advisory({"FAKE_RC": "2"})
        self.assertNotEqual(result.returncode, 0, result.output)
        self.assertIn("::error", result.output)

    def test_success_exit_without_output_fails(self):
        result = run_advisory({"FAKE_RC": "0"})
        self.assertNotEqual(result.returncode, 0, result.output)
        self.assertIn("::error", result.output)

    def test_malformed_output_fails(self):
        result = run_advisory({"FAKE_JSON": "{not json", "FAKE_RC": "1"})
        self.assertNotEqual(result.returncode, 0, result.output)
        self.assertIn("::error", result.output)

    def test_output_without_dependencies_list_fails(self):
        result = run_advisory({"FAKE_JSON": json.dumps({"fixes": []})})
        self.assertNotEqual(result.returncode, 0, result.output)

    def test_failure_exit_with_no_vulnerabilities_fails(self):
        # Non-zero with nothing found means pip-audit failed for another reason.
        result = run_advisory({"FAKE_JSON": json.dumps(CLEAN), "FAKE_RC": "1"})
        self.assertNotEqual(result.returncode, 0, result.output)
        self.assertIn("::error", result.output)

    def test_empty_dependency_list_fails(self):
        # An audit of zero packages measured nothing.
        result = run_advisory(
            {"FAKE_JSON": json.dumps({"dependencies": [], "fixes": []})}
        )
        self.assertNotEqual(result.returncode, 0, result.output)

    def test_non_dict_dependency_entry_fails_with_an_error(self):
        data = {
            "dependencies": [CLEAN["dependencies"][0], "garbage", None],
            "fixes": [],
        }
        result = run_advisory({"FAKE_JSON": json.dumps(data)})
        self.assertEqual(result.returncode, 1, result.output)
        self.assertIn("::error", result.output)
        self.assertNotIn("Traceback", result.output)

    def test_unexpected_exit_code_fails_even_with_vulnerabilities(self):
        # pip-audit exits 1 for "vulnerabilities found"; anything else is a failure.
        result = run_advisory({"FAKE_JSON": json.dumps(VULNERABLE), "FAKE_RC": "2"})
        self.assertNotEqual(result.returncode, 0, result.output)
        self.assertIn("::error", result.output)

    def test_annotation_text_is_escaped(self):
        # A raw newline or % in a workflow command truncates or corrupts it.
        data = {
            "dependencies": [
                CLEAN["dependencies"][0],
                {"name": "odd", "skip_reason": "100% broken\nsecond line\rthird"},
            ],
            "fixes": [],
        }
        result = run_advisory({"FAKE_JSON": json.dumps(data)})
        self.assertEqual(result.returncode, 0, result.output)
        self.assertIn("100%25 broken%0Asecond line%0Dthird", result.output)

    def test_missing_pip_audit_fails(self):
        result = run_advisory({"PATH": "/nonexistent"})
        self.assertNotEqual(result.returncode, 0, result.output)
        self.assertIn("::error", result.output)

    def test_extra_arguments_reach_pip_audit_with_json_output(self):
        result = run_advisory({"FAKE_JSON": json.dumps(CLEAN)}, args=["-r", "req.txt"])
        self.assertEqual(result.returncode, 0, result.output)
        self.assertIn("-r req.txt", result.calls)
        self.assertIn("-f json", result.calls)


if __name__ == "__main__":
    unittest.main()
