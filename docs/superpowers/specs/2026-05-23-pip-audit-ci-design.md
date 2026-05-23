# Spec: pip-audit in CI for Python Sub-projects

## Goal

Add `pip-audit` as an advisory security step to every Python CI workflow in the math repo. Catches known CVEs in installed Python dependencies. Fills the gap that exists for Python (Rust already has `cargo deny`/`cargo audit`).

## Scope

9 workflows: `amicable-py.yml`, `collatz-py.yml`, `e-py.yml`, `fib-py.yml`, `perfect-numbers-py.yml`, `pi-py.yml`, `sq-py.yml`, `factorial-py.yml`, `scripts.yml`.

## Design

### Per-workflow changes (identical pattern for all 9)

**1. Append `pip-audit` to the existing pip install step:**

```yaml
# Before
run: pip install ruff coverage hypothesis pyright

# After
run: pip install ruff coverage hypothesis pyright pip-audit
```

**2. Add pip-audit step after tests, before coverage:**

```yaml
- name: Run pip-audit
  run: pip-audit
  continue-on-error: true
```

`continue-on-error: true` makes the step advisory — a CVE finding surfaces in CI output but does not fail the job or block auto-merge.

No `working-directory` override needed: pip-audit scans the Python environment, not the filesystem, so the working directory is irrelevant.

### Why scan the installed environment

Each CI job runs in a fresh Ubuntu environment. Only the packages explicitly installed via `pip install` (plus their transitive dependencies) are present. Scanning the installed environment therefore precisely mirrors each sub-project's actual dependency surface with zero extra configuration.

### Advisory rationale

pip-audit failures should not block PRs because:

- CVEs in dev tools (ruff, coverage, hypothesis) have no production impact
- A sudden advisory on a transient dep would create noise on unrelated PRs
- The fix action (pinning or upgrading) requires human judgment

Findings are visible in the CI job log and can be acted on in a dedicated follow-up PR.

## CLAUDE.md Standard

The math repo `CLAUDE.md` must document pip-audit as required for every new Python sub-project:

> Every Python sub-project CI workflow must include `pip-audit` in the pip install step and a `Run pip-audit` step with `continue-on-error: true` after the test step.

## Out of Scope

- Requirements files or lockfiles (not used in this repo)
- Blocking on CVEs (advisory only)
- Pinned dep versions or automated upgrade PRs
