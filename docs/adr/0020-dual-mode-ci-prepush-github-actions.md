# ADR-0020: Dual-Mode CI — Permanent Pre-Push Hook + PR-Only GitHub Actions

**Date:** 2026-04-21
**Status:** Accepted

## Context

Early CI ran on every push to any branch via `push:` triggers. Problems: every commit to a feature branch triggered a full CI run on GitHub, consuming Actions minutes for work-in-progress commits. The feedback loop was slow (2–5 minutes waiting for GitHub) even for small changes.

But removing the branch-push trigger entirely left no gate before merge. PR-only CI catches regressions before merge but gives no local feedback during development.

Options considered:

- **Branch-push CI only**: all branches get full CI. Expensive in Actions minutes; feedback still requires waiting for GitHub runners.
- **PR-only CI**: no branch-push triggers. No feedback during feature development until a PR is opened.
- **Dual-mode**: a local pre-push hook provides fast feedback on every push; GitHub Actions runs only on PRs as the merge gate.

## Decision

Two permanent, complementary gates:

**Local pre-push hook** (`scripts/pre-push`, installed via `make install-hooks`):

- Runs on every `git push` for any branch before bytes leave the machine.
- Filters to pushes that touch source files (`.py`, `.rs`, etc.) — doc-only and config-only pushes are skipped.
- Runs the relevant sub-project test suites locally (~10–30s per suite).
- Worktree-aware: uses `git rev-parse --git-common-dir` to find the repo root, not `--show-toplevel` (the latter returns the worktree path, not the main checkout where the Makefile lives).
- Drains the full stdin loop before acting — a single `git push` can send multiple refs; exiting on the first deletion ref would skip testing the real push.
- Redirects stdin from `/dev/null` for `make test` to prevent deadlock with Python's `multiprocessing.resource_tracker` (which inherits the git pipe as stdin and blocks on EOF).
- Skips local tests when >6 sub-projects are changed — cross-cutting changes (e.g. adding a Makefile target across all projects) exceed the macOS `ProcessPoolExecutor` semaphore limit; CI handles those instead.
- The hook is a **copy**, not a symlink. After editing `scripts/pre-push`, re-run `make install-hooks` — the installed `.git/hooks/pre-push` does not pick up changes automatically.

**GitHub Actions** (`.github/workflows/*.yml`):

- Triggers only on `pull_request` targeting master — never on bare `push:`.
- Runs full test + lint + coverage + audit suite on Linux (`ubuntu-latest`).
- Is the merge gate — PRs cannot auto-merge without CI passing.
- Linux is the authoritative environment for coverage measurement (tarpaulin ptrace).

Both gates are permanent. The pre-push hook header documents this explicitly to prevent future removal.

## Consequences

- Most branch pushes get local test feedback without consuming GitHub Actions minutes.
- Actions minutes are consumed only on PRs, not on intermediate branch commits.
- Pre-push hook isolates test runs to changed sub-projects — cross-cutting changes fall through to CI.
- `GIT_DIR` leaks from the git hook environment into subprocess when pushing from a worktree; push from the main repo directory (`git -C /main/repo push origin branch`) to avoid this.
- The hook tests the checked-out working tree, not the pushed branch — when pushing a feature branch fix, push from the worktree so the hook exercises the feature branch code.

## Related

- [ADR-0006: Per-project CI workflows with test-before-build gate](0006-per-project-ci-workflows-with-test-gate.md)
- [ADR-0019: ≥90% line coverage gate enforced in CI](0019-90-percent-coverage-gate-ci.md)
