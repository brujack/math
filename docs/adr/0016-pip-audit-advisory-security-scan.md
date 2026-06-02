# ADR 0016: pip-audit advisory security scan in CI

- **Date:** 2026-05-22
- **Status:** Accepted

## Context

Python dependencies in math sub-projects (gmpy2, hypothesis, mutmut, defusedxml, coverage, ruff, pyright) can have known CVEs. Without a scan, vulnerable transitive dependencies go unnoticed until a tool like Snyk or a manual audit surfaces them — often too late.

`cargo deny check advisories` serves this role for Rust crates. Python needed an equivalent. `pip-audit` queries the Python Packaging Advisory Database (PyPA) and reports CVEs against the installed packages.

## Decision

Add `pip-audit` as an advisory CI step to every Python sub-project workflow (`continue-on-error: true`). Advisory means it surfaces findings but does not block merges.

Placement: run after pip install, before tests. This ensures audit runs against the exact dependency set used in tests.

**Advisory (non-blocking) rationale:** Math dependencies like gmpy2 are C-extension libraries with infrequent releases. A blocking audit would prevent CI from passing if a CVE is published mid-sprint before a fix is available upstream. The goal is visibility, not gatekeeping.

`pip-audit` added to:

1. Each sub-project's `install_deps.sh` — local developer setup
2. Each `*-py.yml` CI workflow's pip install step — CI installs it explicitly (CI does not call `install_deps.sh`)

Both must be updated when adding a new dependency. Updating only `install_deps.sh` causes CI to fail with `ModuleNotFoundError` on any package needed at test time; conversely, updating only CI means local developers lack the tool.

## Consequences

- CVEs in Python dependencies surface in CI job logs as advisory output
- Not a merge gate — `continue-on-error: true` on the pip-audit step
- `pip-audit` installed locally via `install_deps.sh` for developer use
- `pip-audit` in every CI workflow's pip install step
- Future decision: elevate to blocking if a CVE is found in a directly-used, actively-patched package

## Related

- ADR 0015: Pyright type checking for Python sub-projects
- ADR 0017: defusedxml for XXE-safe XML parsing in scripts
- ADR 0006: Per-project CI workflows with test-before-build gate
- `.claude/standards/python.md`: install_deps.sh vs CI pip install pattern
