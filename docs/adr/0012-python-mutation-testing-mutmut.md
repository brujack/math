# ADR 0012: Python mutation testing with mutmut

- **Date:** 2026-05-18
- **Status:** Accepted

## Context

Python sub-projects reach ≥90% line coverage but coverage alone does not verify that test assertions actually catch behavioral changes. A mutation that swaps `<=` for `<` in a boundary check can be covered (the line runs) but undetected (no assertion distinguishes the two).

Coverage measures whether code executes. Mutation testing measures whether tests detect changes. These are complementary, not redundant. Mathematical functions are particularly vulnerable to this gap: a recurrence relation or boundary condition can be subtly wrong in a way that existing unit tests miss entirely.

## Decision

Add `mutmut` as the Python mutation testing tool. Each Python sub-project gets a `make mutants` target:

```makefile
mutants:
	mutmut run || true
	mutmut results
```

`|| true` makes the recipe non-blocking — surviving mutants surface as output, not a build failure. `mutmut results` runs on its own recipe line regardless of `mutmut run`'s exit code.

**Non-blocking rationale:** Blocking on surviving mutants in CI would prevent merges when mutmut finds gaps that require non-trivial test additions. The goal is to surface information, not to gate every PR.

**CI cadence:** Monthly via `workflow_dispatch` + schedule, not on every PR. Mutation runs are slow (minutes per sub-project). Monthly runs inform which tests need strengthening; results upload as 30-day artifacts.

`mutmut` is added to each sub-project's `install_deps.sh` and each CI workflow's pip install step. Both must be updated when adding a new dependency — CI does not call `install_deps.sh`.

## Consequences

- Monthly runs surface test quality gaps across all Python sub-projects
- Surviving mutants do not block merges — they inform future test additions
- `mutmut` added to `install_deps.sh` for local developer setup
- `mutmut` added to each `*-py.yml` CI workflow pip install step explicitly (CI does not call install_deps.sh)
- Cargo-mutants (Rust) is the equivalent tool for Rust crates — this ADR covers Python only

## Related

- ADR 0013: Hypothesis and proptest for property-based testing
- ADR 0015: Pyright type checking for Python sub-projects
- `.claude/standards/python.md`: mutmut usage and Makefile target pattern
