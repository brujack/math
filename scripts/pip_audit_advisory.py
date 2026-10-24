#!/usr/bin/env python3
"""Run pip-audit as an advisory check whose findings are visible, not just logged.

Usage: pip_audit_advisory.py [pip-audit args...]

pip-audit is advisory by ADR-0016: a CVE must not block a merge. It used to run under
`continue-on-error: true`, which made every outcome green -- a crash, an audit of
nothing, and a run that found CVEs all looked like a clean audit.

Exit 0: the audit ran. Each vulnerability and each dependency pip-audit could not
        audit becomes a `::warning` annotation, and one summary line goes to
        $GITHUB_STEP_SUMMARY.
Exit 1: the audit did not happen or cannot be trusted: pip-audit is missing, wrote no
        readable JSON, audited zero packages, or exited non-zero with nothing found.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile


def _error(message):
    print(f"::error::pip-audit: {message}")
    return 1


def _summarize(dependencies):
    """Return (audited, vulnerabilities, warnings) from pip-audit's dependency list."""
    audited = 0
    vulnerabilities = 0
    warnings = []
    for dep in dependencies:
        if "skip_reason" in dep:
            warnings.append(f"{dep.get('name')} not audited: {dep['skip_reason']}")
            continue
        audited += 1
        for vuln in dep.get("vulns", []):
            vulnerabilities += 1
            fixes = ", ".join(vuln.get("fix_versions", [])) or "none"
            aliases = ", ".join(vuln.get("aliases", []))
            warnings.append(
                f"{dep.get('name')} {dep.get('version')} {vuln.get('id')}"
                f"{f' ({aliases})' if aliases else ''}, fixed in: {fixes}"
            )
    return audited, vulnerabilities, warnings


def run(args):
    with tempfile.TemporaryDirectory() as tmp:
        report = pathlib.Path(tmp) / "pip-audit.json"
        try:
            proc = subprocess.run(
                ["pip-audit", *args, "-f", "json", "-o", str(report)], check=False
            )
        except FileNotFoundError:
            return _error("not installed")
        try:
            data = json.loads(report.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            return _error(f"exit {proc.returncode}, no readable JSON report ({exc})")
    dependencies = data.get("dependencies") if isinstance(data, dict) else None
    if not isinstance(dependencies, list):
        return _error("JSON report has no dependencies list")

    audited, vulnerabilities, warnings = _summarize(dependencies)
    if audited == 0:
        return _error("audited 0 packages")
    if proc.returncode != 0 and vulnerabilities == 0:
        return _error(f"exit {proc.returncode} with no vulnerabilities reported")

    for warning in warnings:
        print(f"::warning::pip-audit: {warning}")
    skipped = len(dependencies) - audited
    line = (
        f"pip-audit (advisory): {audited} packages audited, "
        f"{vulnerabilities} vulnerabilities, {skipped} skipped"
    )
    print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"- {line}\n")
    return 0


def main():
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
