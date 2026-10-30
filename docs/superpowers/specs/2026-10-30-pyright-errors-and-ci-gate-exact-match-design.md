# Root pyright errors on the push path, and an exact-name ci-gate exclusion

- **Date:** 2026-10-30
- **Status:** Draft
- **Related:**
  - Backlog P2 row "Root pyright type errors are caught only in CI";
  - Backlog P2 row "ci-gate excludes any check whose name is a substring of an excluded name";
  - math#177 (three pyright errors pushed past a green local gate).

## Problem

### Root pyright errors reach CI unchecked

math#177 pushed three pyright errors in `tests/test_tool_pins.py` past a green local
`make test` and pre-push. Root pyright currently reports none: `pyright` from the repo root
exits 0 in about 4 s (measured 2026-10-30 on `claude`, master `a9ca097`).

`tests/test_root_pyright_scope.py` already runs `pyright --outputjson` under
`make test-python`, which pre-push runs for pushes that touch `scripts/`, `tests/`,
`typings/`, `.claude/scripts/` or `pyrightconfig.json`. That test asserts the config's mode,
its include and exclude lists, and `summary.filesAnalyzed`. It never reads the error count.
So the only check that fails on a type error is the `Run pyright` step in `scripts.yml`,
which runs only in CI.

### ci-gate drops any check whose name is a substring of an excluded name

`scripts/ci-gate.sh` removes advisory and self checks with jq `select([.name] | inside($excl) | not)`
at three sites: the non-terminal poll (line 48), the required list (63) and the failures
list (72). For strings, `inside` tests for a substring, so
`jq -n '["scan"] | inside(["snyk-scan"])'` prints `true` (measured 2026-10-30, jq 1.7.1).
A required check named `scan`, `merge` or `secret` would be treated as `snyk-scan`,
`auto-merge` or `secret-scan` and would never gate. No current check name collides, so the
defect is latent.

The exact-match form `.name as $n | $excl | any(. == $n) | not` keeps `scan` and drops
`snyk-scan` (measured with the same jq).

## Design

1. **Error count in the existing pyright test.** `test_root_pyright_scope.py` gains a test
   that runs `pyright --outputjson` the same way and asserts `summary.errorCount == 0`. On
   failure the message lists each error diagnostic as `<file>:<line> <rule> <message>`, with
   file paths relative to the repo root. It reuses the class's existing setup: it skips when
   pyright is absent outside CI and fails when it is absent in CI. The pyright subprocess
   runs once per class (`setUpClass`), and both tests read that one report, so `make test`
   gains no second pyright run.
2. **Exact-name exclusion in ci-gate.** All three `inside($excl)` filters become
   `.name as $n | $excl | any(. == $n) | not`.

## Testing

- pyright: a test runs the error-count assertion's message builder against a report holding
  one error diagnostic and checks the exact message line. A second test runs pyright in a
  temporary directory holding a copy of the root `pyrightconfig.json` and one `scripts/` file
  with a seeded type error, and asserts the same report reader returns at least one error,
  so the gate is shown to fire on a real pyright run, not only on a hand-built report.
- ci-gate: a `tests/scripts/ci_gate.bats` case where a required check named `scan` fails
  and `snyk-scan` is excluded: the gate exits non-zero and names `scan`. A second case where
  a check named `scan` is still running keeps the gate polling. Both use `tests/mocks/gh`.

## Out of scope

- Adding pyright to `make lint`: the test already runs pyright on the same pre-push path,
  and a second invocation doubles the cost for no new coverage.
- Sub-project pyright (each `<dir>/pyrightconfig.json`): it stays CI-only, as today.

## Requirements

- **R1.** `[PR1]` `tests/test_root_pyright_scope.py` fails when root `pyright --outputjson` reports `summary.errorCount` above 0, and its failure message lists each error as `<file>:<line> <rule> <message>` with repo-relative paths.
- **R2.** `[PR1]` `test_root_pyright_scope.py` runs pyright at most once per `make test-python`, shared by the file-count and error-count assertions.
- **R3.** `[PR1]` A test runs pyright in a temporary directory with a copy of the root `pyrightconfig.json` and one seeded type error under `scripts/`, and shows the test's report reader finds at least one error.
- **R4.** `[PR1]` `scripts/ci-gate.sh` excludes a check only when its name exactly equals an entry in the exclusion list, at all three filter sites.
- **R5.** `[PR1]` `tests/scripts/ci_gate.bats` has a case where a failing required check named `scan` is reported as failed while `snyk-scan` is excluded, and a case where a running `scan` keeps the gate polling.
- **R6.** `[PR1]` The Backlog loses the two P2 rows this spec closes.
- **R7.** `[PR1]` Root `CLAUDE.md`'s `test_root_pyright_scope.py` line states that the test fails on any root pyright error.
- **V1.** On the PR, the `scripts` CI job and the auto-merge `ci-gate` job are green.
- **N1.** No change to `pyrightconfig.json`'s mode, include or exclude.
- **N2.** No pyright invocation added to `make lint`.
- **N3.** No change to which check names `ci-gate.sh` excludes.
