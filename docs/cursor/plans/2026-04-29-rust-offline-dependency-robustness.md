# Rust Offline Dependency Robustness Plan

Date: 2026-04-29  
Status: In Progress  
Spec: `docs/cursor/specs/2026-04-29-rust-offline-dependency-robustness-design.md`

## Objective

Implement Approach A: add a shared Rust wrapper script that standardizes cargo environment behavior across Rust subprojects, improves diagnostics for cache/index failures, and keeps CI semantics unchanged.

## Scope

- In scope: `pi-rs`, `prime-rs`, `fib-rs`, `sq-rs`, `twin-primes-rs`, `e-rs`, `factorial-rs` lint/test command paths.
- Out of scope: algorithmic changes, dependency vendoring, CI architecture redesign.

## Implementation Steps

1. **Create shared wrapper**
   - Add `scripts/rust-check.sh` at repo root.
   - Support subcommands: `lint`, `test`.
   - Standardize env:
     - `CARGO_HOME` (default to writable repo-local path when unset in constrained contexts)
     - optional `CARGO_TARGET_DIR` passthrough
   - Add mode handling:
     - online default
     - optional offline behavior via env flag (for local resilience only).
   - Ensure wrapper exits with underlying cargo exit code.

2. **Add clear diagnostics**
   - Detect common cargo cache/index permission failures.
   - Print actionable guidance:
     - how to set writable cargo home
     - when to retry with offline mode
     - distinction between environment/setup failure and lint/test code failure.

3. **Wire all Rust Makefiles**
   - Update each Rust subproject Makefile `lint`/`test` targets to call shared wrapper.
   - Keep existing target names unchanged to preserve developer workflows and hooks.

4. **Preserve CI semantics**
   - Keep CI running online default behavior.
   - Avoid changing required checks topology in this plan.
   - Confirm no regressions in workflow command compatibility.

5. **Documentation updates**
   - Update top-level `README.md` Rust troubleshooting section.
   - Update `CLAUDE.md` with wrapper usage and environment troubleshooting notes.
   - Add concise local-run examples for constrained environments.

6. **Validation**
   - Run per-crate `make lint` and `make test` for all Rust subprojects in:
     - standard local environment
     - worktree environment
   - Simulate constrained write path (for example read-only/unwritable cargo home) and confirm diagnostics.
   - Confirm wrapper emits clear classification messages.

## Verification Checklist

- [ ] Wrapper exists and is executable.
- [ ] All Rust Makefiles use wrapper for lint/test.
- [ ] Standard local runs pass where dependencies are available.
- [ ] Constrained environment failure produces actionable guidance.
- [ ] `README.md` and `CLAUDE.md` updated.
- [ ] No CI workflow breakage from command changes.

## Risks and Mitigations

- **Risk:** Wrapper adds hidden coupling across projects.  
  **Mitigation:** Keep interface minimal (`lint`/`test` only), document behavior, and avoid project-specific branching.

- **Risk:** Offline mode causes stale dependency assumptions.  
  **Mitigation:** Keep CI online; local offline mode remains opt-in via env flag.

- **Risk:** Inconsistent environment behavior between Python and Rust subprojects confuses users.  
  **Mitigation:** Reuse messaging style from Python serial-fallback work and document clearly in `README.md`.

## Exit Criteria

- Rust checks no longer fail prematurely due to avoidable cargo path/index assumptions in constrained local environments.
- Worktree and root checkout behavior are both reliable.
- Developers get immediate actionable diagnostics for environment-related failures.
