# ADR-0019: ≥90% Line Coverage Gate Enforced in CI

**Date:** 2026-04-27
**Status:** Accepted

## Context

Initial Rust crate coverage ranged from 56% (prime-rs) to 68% (factorial-rs). No CI gate existed — coverage was aspirational and never enforced. Without a hard gate, coverage drifts down as features are added without corresponding tests: the passing bar is "tests exist", not "tests cover the code".

The injectable I/O pattern (ADR-0018) made ≥90% achievable for all crates: with `run()` unit-testable and `fn main()` excluded, the only uncoverable lines are a small set of structural artifacts in macro expansions and loop control flow.

Running `cargo tarpaulin` locally is slow (~8s per crate) and produces slightly different line counts than Linux ptrace (macOS tarpaulin uses a different instrumentation backend). Making coverage a local gate would produce inconsistent results and slow every local test run. CI on Linux is the single authoritative measurement point.

## Decision

Add `cargo tarpaulin --fail-under 90` to the `test` job in every Rust crate CI workflow. tarpaulin runs on Linux (`ubuntu-latest`) using ptrace instrumentation, which is the authoritative backend.

The pre-push hook does **not** run tarpaulin. CI is the coverage gate.

Linux ptrace counts more lines as coverable than macOS tarpaulin. Three structural patterns require `#[cfg(not(tarpaulin_include))]` exclusion to hold coverage above 90% without gaming the metric:

1. **`fn main()` body** — not invoked by unit tests; excluded unconditionally in all crates.
2. **Multi-line `write!/writeln!` macro calls** — ptrace counts the first and last argument lines as separate coverable probes even when the macro is reached. Fix: keep macros single-line. Add `rustfmt.toml` with `use_small_heuristics = "Max"` to prevent `cargo fmt` from re-expanding them.
3. **`break;` inside `while let` loops** — ptrace counts explicit `break;` as a coverable probe that never fires even when execution reaches the break. Fix: fold into the loop condition using `Option::filter`.

The tarpaulin JUnit output path is `target/nextest/ci/junit.xml` — not workspace root. CI upload steps must reference this path explicitly.

## Consequences

- PRs that drop any crate below 90% fail CI and cannot auto-merge.
- New crates must reach ≥90% before the PR that introduces them can merge.
- Existing crates below 90% are a known gap: every PR that touches an under-covered file must add tests that increase the figure (never decrease it).
- The three structural exclusion patterns are documented in `CLAUDE.md` so future contributors know not to add coverable lines in those positions.
- Generated code, `fn main()` glue, and platform-specific branches unreachable in CI may be excluded with a documented reason.

## Related

- [ADR-0018: Injectable I/O pattern for Rust CLI testability](0018-injectable-io-rust-cli-testability.md)
- [ADR-0006: Per-project CI workflows with test-before-build gate](0006-per-project-ci-workflows-with-test-gate.md)
- [ADR-0011: cargo-nextest as Rust test runner](0011-cargo-nextest-rust-test-runner.md)
