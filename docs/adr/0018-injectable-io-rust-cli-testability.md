# ADR-0018: Injectable I/O Pattern for Rust CLI Testability

**Date:** 2026-04-26
**Status:** Accepted

## Context

Each math Rust crate is a CLI binary that writes to stdout/stderr. The initial implementations had `fn main()` directly calling format logic and `println!`/`eprintln!`. This made unit testing impossible — there was no way to capture output or inject a failure path without forking a process.

`cargo tarpaulin` (coverage) counts `fn main()` body lines as coverable on Linux ptrace, so an untestable `fn main()` dragged coverage below the ≥90% gate introduced alongside this change. Without a way to unit-test `run()`, reaching 90% would require extensive integration tests that are slower and harder to maintain.

Options considered:

- **Process-based integration tests only**: covers the binary end-to-end but is slow (~1–2s per case), brittle on CI, and tarpaulin does not instrument subprocess execution — coverage from integration tests does not count.
- **Generic writer injection**: all logic moves to a `run<W: Write, E: Write>()` function; `fn main()` becomes a two-line dispatcher. Unit tests inject `Vec<u8>` writers in memory. Fast, deterministic, and tarpaulin-visible.

## Decision

Extract all logic from `fn main()` into a `run<W: Write, E: Write>(stdout: &mut W, stderr: &mut E, ...) -> io::Result<()>` function. `fn main()` becomes a thin dispatcher that passes locked stdout/stderr and calls `process::exit(1)` on error. Mark `fn main()` with `#[cfg(not(tarpaulin_include))]` to exclude it from coverage measurement.

Unit tests inject `Vec<u8>` as the stdout/stderr writer. Integration tests in `tests/cli.rs` use `env!("CARGO_BIN_EXE_<name>")` + `tempfile::tempdir()` to test the compiled binary end-to-end.

Add an `R: BufRead` parameter when stdin is needed.

Use `io::Error::other("msg")` — not `io::Error::new(io::ErrorKind::Other, ...)` — to satisfy `clippy::io_other_error` (fires on the old form in Rust 1.74+).

Applied to all Rust crates across PRs #25–#32 (sq, fib, e, pi, prime, twin-primes, factorial, collatz, goldbach, amicable, perfect-numbers).

## Consequences

- All crates reach ≥90% tarpaulin coverage via unit tests on the `run()` function.
- `fn main()` is excluded from tarpaulin in all crates via `#[cfg(not(tarpaulin_include))]`.
- Each `Cargo.toml` needs `[lints.rust] unexpected_cfgs = { level = "warn", check-cfg = ['cfg(tarpaulin_include)'] }` to suppress the unknown-cfg warning from clippy.
- Integration tests validate the full binary end-to-end but do not contribute to tarpaulin coverage — tarpaulin instruments the library under test, not subprocess execution.
- The `run()` signature is the canonical extension point for new arguments: add parameters to `run()`, not to `main()`.

## Related

- [ADR-0006: Per-project CI workflows with test-before-build gate](0006-per-project-ci-workflows-with-test-gate.md)
- [ADR-0019: ≥90% line coverage gate enforced in CI](0019-90-percent-coverage-gate-ci.md)
