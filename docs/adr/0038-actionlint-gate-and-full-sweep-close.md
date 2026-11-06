# ADR-0038: actionlint is a CI-enforced lint gate; only a full mutation sweep closes its issue

**Date:** 2026-11-03
**Status:** Accepted

## Context

A worldclass audit on 2026-11-03 found three CI monitors that misreported:

- **Crate discovery.** `mutation-testing.yml` found crates with `find . -name Cargo.toml`,
  which also swept the six cargo-deny fixture crates under `tests/fixtures/`. The
  2026-11-01 sweep filed #195 naming exactly those six.
- **Single-unit close.** `mutation-notify.sh` closed the open tracking issue on any green
  run, so a one-crate `workflow_dispatch` could close an issue about crates it never ran
  (#100).
- **No workflow linter.** actionlint ran nowhere. Run once with shellcheck 0.11.0 on PATH,
  it reported 41 findings. 40 were in one coverage-badge step rendered into 20
  workflows, and one was in the mutation workflow.

Spec: `docs/superpowers/specs/2026-11-03-worldclass-slice1-ci-monitors-design.md`.

## Decision

1. **Crates come from git, not the filesystem.** A `List crates` step derives the list
   with `git ls-files '*/*-rs/Cargo.toml'`, the derivation `scripts/cargo-deny-all.sh`
   already used. It rejects a dispatch input that is not one of those directories, and
   writes one `crate_dirs=` line to `GITHUB_OUTPUT`.
2. **Only a full sweep closes the tracking issue.** Both mutation workflows pass
   `FULL_SWEEP` (`"true"` exactly when their unit input is empty). `mutation-notify.sh`
   refuses a missing or invalid value. On a green single-unit run it comments on an open
   issue without closing it.
3. **actionlint is a lint gate that CI enforces.** Root `make lint` runs `lint-workflows`.
   When actionlint is missing it skips locally and fails under `CI=true`. Every CI job that
   runs the bats suite installs actionlint 1.7.12, version-pinned with a sha256 check, and a
   test pins that rule the same way `tests/test_deny_policy.py` pins cargo-deny. A fixture
   with a known SC2086 finding proves that both actionlint and its shellcheck integration
   ran.
4. **There is no local pre-push trigger for workflow-only pushes.** The development
   machines do not install actionlint, so a local branch would only print a skip line. The
   operator chose to enforce it in CI only.
5. **The badge step stays advisory.** If a `coverage-data` worktree cannot be created, the
   step prints a message and exits 0 instead of turning a coverage job red.
   Superseded: coverage jobs no longer push badges. They upload `coverage-badge-*` artifacts and
   `scripts/publish-coverage-badges.sh` publishes them after the merge, failing visibly.

## Consequences

- The monthly Rust sweep tests the 11 real crates only. An unknown or newline-bearing
  dispatch input fails before anything is installed.
- A green single-crate re-dispatch leaves a trace on the issue but never closes it. #195
  and future issues close on the next green full sweep.
- Any workflow edit runs the `scripts` job (its paths now include `.github/workflows/**`),
  and that job fails on an actionlint finding. A new bats-suite job without the actionlint
  install fails `tests/test_actionlint_install.py`.
- A workflow-only push gets actionlint feedback only from CI (Backlog row "Workflow-only
  push runs no local actionlint").
- Coverage badges can still go stale silently when a push fails, and they reflect PR
  branches. Both are in the Backlog row "Coverage badges reflect the last PR branch, not
  master".

## Related

- ADR-0033 (Python mutation fails closed and runs sharded)
- ADR-0037 (CI supply-chain guardrails)
- core.md ci-002, shell-004
- ADR-0040 (Decision 1's single `List crates` step and `crate_dirs=` output are superseded by it)
