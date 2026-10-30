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
   file paths relative to the repo root. The repo-root pyright subprocess runs once per class
   (`setUpClass`), and both the file-count and error-count tests read that one report. A run
   that yields no JSON stays a failure carrying the return code and stderr, never a skip.
2. **A pinned local pyright.** `requirements-dev.txt` gains `pyright==1.1.411`, the version
   every other install site pins, so `make install-deps` installs the gate's tool. When
   pyright is absent outside CI the class still skips, but first writes one line to stderr:
   `pyright not found; root type errors are unchecked locally (run: make install-deps)`.
   When the installed `pyright --version` differs from the pin in `requirements-dev.txt`,
   the class fails with the same remedy, because a different pyright can report a different
   error set from CI's.
3. **Exact-name exclusion in ci-gate.** All three `inside($excl)` filters become
   `.name as $n | $excl | any(. == $n) | not`.

## Testing

- pyright: a test runs the error-count assertion's message builder against a report holding
  one error diagnostic and checks the exact message line. A second test runs pyright in a
  temporary directory holding a copy of the root `pyrightconfig.json` and one import-free
  `scripts/` file whose line 2 assigns a `str` to an `int` variable, and asserts the report
  reader returns exactly one error, rule `reportAssignmentType`, on that line. A stray
  import error would make the count 2 and fail it.
- pyright version: a test feeds the version check a pin and a different reported version
  and asserts the failure message names `make install-deps`; a matching pair passes.
- ci-gate: a `tests/scripts/ci_gate.bats` case where a required check named `scan` fails
  and `snyk-scan` is excluded: the gate exits non-zero and names `scan`. A second case where
  a check named `scan` is still running keeps the gate polling until it times out, asserting
  the `Timeout: checks did not complete` message. Both use `tests/mocks/gh`.

## Out of scope

- Adding pyright to `make lint`: the test already runs pyright on the same pre-push path,
  and a second invocation doubles the cost for no new coverage.
- Sub-project pyright (each `<dir>/pyrightconfig.json`): it stays CI-only, as today.

## Requirements

- **R1.** `[PR1]` `tests/test_root_pyright_scope.py` fails when root `pyright --outputjson` reports `summary.errorCount` above 0, and its failure message lists each error as `<file>:<line> <rule> <message>` with repo-relative paths.
- **R2.** `[PR1]` `test_root_pyright_scope.py` runs pyright over the repo root once per `make test-python`, and that one report feeds both the file-count and error-count assertions; a run with no JSON output fails with the return code and stderr.
- **R3.** `[PR1]` A test runs pyright in a temporary directory with a copy of the root `pyrightconfig.json` and one import-free `scripts/` file seeded with a type error, and shows the report reader returns exactly one error, rule `reportAssignmentType`, on the seeded line.
- **R4.** `[PR1]` `scripts/ci-gate.sh` excludes a check only when its name exactly equals an entry in the exclusion list, at all three filter sites.
- **R5.** `[PR1]` `tests/scripts/ci_gate.bats` has a case where a failing required check named `scan` is reported as failed while `snyk-scan` is excluded, and a case where a running `scan` keeps the gate polling until the `Timeout: checks did not complete` message.
- **R6.** `[PR1]` The Backlog loses the two P2 rows this spec closes.
- **R7.** `[PR1]` Root `CLAUDE.md`'s `test_root_pyright_scope.py` line states that the test fails on any root pyright error.
- **R8.** `[PR1]` `requirements-dev.txt` pins `pyright==1.1.411`; with pyright absent outside CI the test class writes `pyright not found; root type errors are unchecked locally (run: make install-deps)` to stderr before skipping, and with an installed version different from that pin it fails naming `make install-deps`.
- **R9.** `[PR1]` Root `CLAUDE.md`'s `requirements-dev.txt` line lists `pyright==1.1.411`.
- **V1.** On the PR, the `scripts` CI job and the auto-merge `ci-gate` job are green.
- **N1.** No change to `pyrightconfig.json`'s mode, include or exclude.
- **N2.** No pyright invocation added to `make lint`.
- **N3.** No change to which check names `ci-gate.sh` excludes.

## Multi-Lens Review

Reviewed at commit: `1df0864` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: worth building; premise verified (`scripts/pre-push:141` runs root `make test` for
`tests/`, `scripts/`, `typings/`, `.claude/scripts/`, `pyrightconfig.json`; `scripts.yml:69-70`
is the only error gate). R2 ("at most once") contradicts R3's second, seeded run.
Assumption: no uncertain assumption found (closest: every pushing machine has pyright, true on `claude`).
Disposition: Addressed (operator, 2026-10-30): R2 reworded to one repo-root run (R2 amended in place before approval).

### Ergonomics

Finding: on a machine set up as documented (`make install-deps`, fresh venv) pyright is absent,
so the new assertion skips with one `s` and pre-push reads green, which is math#177 again; local
pyright is also unpinned and may disagree with CI's 1.1.411. R2/R3 contradiction as above.
Assumption: a local pyright reports the same errors as CI's pinned one.
Disposition: Addressed (operator, 2026-10-30): pin `pyright==1.1.411` in `requirements-dev.txt`,
visible stderr line on skip, failure on a version mismatch (Design 2, R8, R9).

### Risk

Finding: R2/R3 contradiction; R3's "at least one error" passes on a stray `reportMissingImports`
(a probe returned errorCount 2); moving the run to `setUpClass` loses `self.fail`, so the no-JSON
case must stay a failure; the polling bats case should assert the timeout message. jq replacement
verified equal to `inside` on every non-colliding name and stricter on substrings and `""`.
Assumption: no uncertain assumption found (checked: root pyright with a bare `--pythonpath` still 0 errors).
Disposition: Addressed (operator, 2026-10-30): R3 pinned to exactly one `reportAssignmentType`
error from an import-free file; no-JSON failure stated in R2; polling case asserts the timeout message.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
