# ADR-0006: Per-Project CI Workflows with Test-Before-Build Gate

**Date:** 2026-03-21
**Status:** Accepted

## Context

The original CI used a single `build.yml` covering all projects. A failure in one project blocked visibility into the others, badge status was all-or-nothing, and the build step ran even when tests failed. As the number of projects grew (pi-py, pi-rs, prime-rs, fib-py, fib-rs), the monolithic workflow became unwieldy.

## Decision

Replace the single `build.yml` with **one workflow file per project** (e.g., `pi-py.yml`, `pi-rs.yml`). Each workflow:
1. Has a `test` job that runs the project's test suite.
2. Has a `build` job with `needs: [test]` — build only runs if tests pass.
3. Rust build jobs upload the release binary as a 7-day artifact via `actions/upload-artifact@v5`.
4. Each workflow produces its own status badge, added to the top of `README.md`.

## Consequences

- Failures are isolated to the affected project — other projects' CI continues unaffected.
- Per-project badges give immediate visibility into which project is broken.
- Build artifacts are never produced from a commit with failing tests.
- Adding a new project requires creating a new workflow file following the established pattern (documented in `CLAUDE.md`).
- Five workflow files instead of one — more files, but each is small and self-contained.

## Related

- [ADR-0002: Python + Rust dual implementation](0002-python-rust-dual-implementation.md)
