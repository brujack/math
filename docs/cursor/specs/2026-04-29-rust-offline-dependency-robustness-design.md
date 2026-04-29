# Rust Offline Dependency Robustness Design

Date: 2026-04-29  
Status: Approved

## Goal

Make Rust lint/test workflows in `math` resilient when cargo cannot freely use the default global cache paths or online index access, so environmental limitations do not produce false-negative bugfix signals.

## Problem Statement

During bugfix verification, Rust subprojects can fail before code-level checks run due to environmental constraints:

- inability to write under default cargo home/registry paths
- inability to update/download crates index in restricted environments
- inconsistent behavior between local runs, worktrees, and CI

These failures hide actual code quality signals and slow bugfix iteration.

## Scope

In scope:

- Rust project lint/test command strategy (`make lint`, `make test`) for `pi-rs`, `prime-rs`, `fib-rs`, `sq-rs`, `twin-primes-rs`, `e-rs`, `factorial-rs`
- shared guidance in repo docs and scripts for deterministic cargo environment
- fallback behavior definition when network/cache constraints are present

Out of scope:

- changing algorithmic code
- replacing cargo with alternate build systems
- introducing vendoring unless required by final approach

## Requirements

1. **Deterministic Cargo Paths**
   - Rust checks must support an explicit writable cargo home/target directory strategy.
   - Worktree and sandbox runs must not assume unrestricted writes to global cache locations.

2. **Offline-Friendly Behavior**
   - When dependencies are already available, checks should run without forced index refresh.
   - Failure messaging should distinguish environment/setup failure from code failure.

3. **Clear Failure Classification**
   - Output should clearly indicate whether failure is:
     - dependency/cache environment issue
     - lint/test code issue

4. **Consistent Across Subprojects**
   - Same behavior contract across all Rust crates in this monorepo.

## Candidate Approaches

### A) Scripted cargo env wrapper (recommended)

Create a shared shell wrapper used by Rust Makefiles:

- sets deterministic cargo env (`CARGO_HOME`, optional `CARGO_TARGET_DIR`)
- supports `--offline` mode when appropriate
- emits explicit diagnostics for cache/index write failures

Pros:

- consistent and centralized
- minimal changes to each crate
- easy to test

Cons:

- adds one more layer in execution path

### B) Per-Makefile direct env settings

Set cargo env vars independently in each Rust project Makefile.

Pros:

- straightforward per-project edits

Cons:

- duplicated logic
- high drift risk across seven crates

### C) Vendor dependencies into repo

Use vendored crates and source replacement.

Pros:

- strongest offline guarantees

Cons:

- large repo churn and maintenance overhead
- more operational complexity

## Recommendation

Use **Approach A** (shared wrapper) first.

If A still fails in your most constrained environments, evaluate selective vendoring for high-friction crates as a follow-up spec.

## Design Outline

1. Add shared Rust command wrapper under `scripts/` with:
   - deterministic env setup
   - mode flags (`lint`, `test`, optional `offline`)
   - standardized error classification messages
2. Update Rust Makefiles to call the wrapper.
3. Update `README.md` and `CLAUDE.md` Rust testing guidance with:
   - expected environment vars
   - troubleshooting section for cache/index permission failures
4. Add tests (where practical) for wrapper behavior and output classification.

## Validation Plan

- Run Rust lint/test for each crate in:
  - normal local environment
  - worktree environment
  - constrained/sandbox-like environment (or simulated with unwritable cargo path)
- Confirm failures are classified correctly and actionable.
- Ensure existing CI remains green and unchanged semantically for code failures.

## Risks and Mitigations

- Risk: wrapper introduces hidden behavior changes.  
  Mitigation: keep wrapper transparent, log key env values in debug mode, and use pass-through exit codes.

- Risk: offline mode masks missing lockfile/dependency drift.  
  Mitigation: keep CI online/default; use offline mode as local resilience path, not CI default.

## Success Criteria

- Rust verification no longer fails prematurely due to avoidable cargo path/index assumptions.
- Developers can run lint/test reliably in worktrees and constrained environments.
- Failure messages clearly separate environment setup issues from actual code defects.
