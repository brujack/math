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

# pip-audit's documented exit status when the audit ran and found vulnerabilities.
_VULNS_FOUND = 1
# One retry absorbs a transient PyPI/OSV failure without making an outage green.
_ATTEMPTS = 2


def _escape(message):
    """Escape text for a workflow command, where %, CR and LF are control characters."""
    return message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _error(message):
    print(f"::error::pip-audit: {_escape(message)}")
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


class _AuditFailed(Exception):
    """The audit did not happen or produced nothing trustworthy."""


def _audit_once(args):
    """Run pip-audit once; return (dependencies, audited, vulnerabilities, warnings)."""
    with tempfile.TemporaryDirectory() as tmp:
        report = pathlib.Path(tmp) / "pip-audit.json"
        proc = subprocess.run(
            ["pip-audit", *args, "-f", "json", "-o", str(report)], check=False
        )
        try:
            data = json.loads(report.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise _AuditFailed(
                f"exit {proc.returncode}, no readable JSON report ({exc})"
            ) from exc
    dependencies = data.get("dependencies") if isinstance(data, dict) else None
    if not isinstance(dependencies, list) or not all(
        isinstance(dep, dict) for dep in dependencies
    ):
        raise _AuditFailed("JSON report has no dependencies list of objects")
    if proc.returncode not in (0, _VULNS_FOUND):
        raise _AuditFailed(f"exit {proc.returncode}")
    audited, vulnerabilities, warnings = _summarize(dependencies)
    if audited == 0:
        raise _AuditFailed("audited 0 packages")
    if proc.returncode != 0 and vulnerabilities == 0:
        raise _AuditFailed(f"exit {proc.returncode} with no vulnerabilities reported")
    return dependencies, audited, vulnerabilities, warnings


def _audit_with_retry(args):
    """Return _audit_once's result, retrying once; raise _AuditFailed after that.

    pip-audit queries PyPI and OSV, so one failed attempt may be an outage. After the
    retry it fails closed (ADR-0016 amendment): an audit that did not happen must not
    read as advisory-green.
    """
    for attempt in range(1, _ATTEMPTS):
        try:
            return _audit_once(args)
        except _AuditFailed as exc:
            print(
                f"::warning::pip-audit: attempt {attempt} failed, retrying: "
                f"{_escape(str(exc))}"
            )
    try:
        return _audit_once(args)
    except _AuditFailed as exc:
        raise _AuditFailed(f"{exc} (after {_ATTEMPTS} attempts)") from exc


def run(args):
    try:
        dependencies, audited, vulnerabilities, warnings = _audit_with_retry(args)
    except FileNotFoundError:
        return _error("not installed")
    except _AuditFailed as exc:
        return _error(str(exc))

    for warning in warnings:
        print(f"::warning::pip-audit: {_escape(warning)}")
    skipped = len(dependencies) - audited
    line = (
        f"pip-audit (advisory): {audited} packages audited, "
        f"{vulnerabilities} vulnerabilities, {skipped} skipped"
    )
    print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        # The Actions runner sets GITHUB_STEP_SUMMARY; appending to the file it
        # names is the documented step-summary mechanism, not user input.
        # deepcode ignore PT: runner-provided path, see comment above
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"- {line}\n")
    return 0


def main():
    sys.exit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
