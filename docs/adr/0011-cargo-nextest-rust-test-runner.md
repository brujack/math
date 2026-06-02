# ADR 0011: cargo-nextest as Rust test runner

- **Date:** 2026-05-18
- **Status:** Accepted

## Context

`cargo test` runs tests in a single process pool, provides minimal output, and has no per-test timeout. For a repo with 11 Rust crates each with property tests and long-running algorithms, test isolation and timing matter.

Shared global state between tests in the same binary produces order-dependent failures that are difficult to reproduce. A single hanging test blocks the entire test run with no per-test timeout. Standard `cargo test` output provides no timing information, making it impossible to identify slow tests without external tooling.

## Decision

Replace `cargo test` with `cargo nextest run` in all Makefiles and CI workflows. nextest runs each test in its own process (no shared global state), provides structured output with per-test timing, supports per-test timeout via config, and generates JUnit XML for CI reporting.

Config lives in `.config/nextest.toml` inside each crate — not at repo root. nextest searches for config starting at the workspace root (the directory containing `Cargo.toml`). Each crate in this repo is a standalone workspace, so each needs its own `.config/nextest.toml`. A single file at repo root would be silently ignored.

JUnit output path: `[profile.ci.junit] path = "junit.xml"` writes to `target/nextest/ci/junit.xml` (not workspace root). CI steps reference `--junit target/nextest/ci/junit.xml`.

**Exception:** tarpaulin (coverage) still uses `cargo test` directly — `--engine nextest` is still experimental in tarpaulin. Tarpaulin invocations are not changed.

## Consequences

- Test isolation is guaranteed per test — no shared global state between tests
- Flaky tests are immediately visible via per-test timing and isolation
- JUnit output enables test analytics and future benchmark-action integration
- Each crate requires its own `.config/nextest.toml`
- nextest installed once per developer machine: `cargo install cargo-nextest --locked`
- In `scripts/rust-check.sh`: guard uses `"${CARGO_BIN}" nextest --version` not `command -v cargo-nextest` — BATS tests override cargo via `RUST_CHECK_CARGO_BIN`; a PATH check would miss the mock

## Related

- ADR 0006: Per-project CI workflows with test-before-build gate
- ADR 0009: Criterion benchmarks for performance regression detection
- `.claude/standards/ci.md`: nextest JUnit output path and profile config scope notes
