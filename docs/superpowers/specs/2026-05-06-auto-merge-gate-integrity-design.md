# Auto-Merge Gate Integrity — Design Spec

**Date:** 2026-05-06
**Status:** Proposed

## Problem

The `auto-merge` job in `.github/workflows/auto-merge.yml` gates only on `secret-scan`. All
project test workflows (`pi-rs`, `fib-py`, `scripts`, etc.) run independently and their results
do not block the merge. A PR can auto-merge with failing tests. GitHub branch protection cannot
enforce required checks on the free plan.

## Goal

Ensure that a PR only auto-merges when every test workflow relevant to the PR's changed files
has passed. Advisory checks (`snyk-scan`) may fail without blocking the merge.

## Approach

Paths-filtered workflows + external gate script.

1. Add `paths:` triggers to all project workflows so only relevant workflows fire on a PR.
2. Add a `scripts/ci-gate.sh` that polls `gh pr checks` until all triggered checks reach a
   terminal state, then verifies no required check failed.
3. Call the gate script from the `auto-merge` job before merging.
4. Add BATS tests for the gate script and the root Makefile — run fully offline via mocked `gh`.

## Component 1: Paths Filters

Each project workflow gains a `paths:` block scoped to that project's files plus the workflow
file itself. Only `auto-merge.yml` triggers unconditionally (it always needs to run).

| Workflow             | Paths                                                                                                     |
| -------------------- | --------------------------------------------------------------------------------------------------------- |
| `pi-py.yml`          | `pi/*.py`, `pi/install_deps.sh`, `pi/Makefile`, `.github/workflows/pi-py.yml`                             |
| `pi-rs.yml`          | `pi/pi-rs/**`, `.github/workflows/pi-rs.yml`                                                              |
| `fib-py.yml`         | `fib/*.py`, `fib/install_deps.sh`, `fib/Makefile`, `.github/workflows/fib-py.yml`                         |
| `fib-rs.yml`         | `fib/fib-rs/**`, `.github/workflows/fib-rs.yml`                                                           |
| `sq-py.yml`          | `sq/*.py`, `sq/install_deps.sh`, `sq/Makefile`, `.github/workflows/sq-py.yml`                             |
| `sq-rs.yml`          | `sq/sq-rs/**`, `.github/workflows/sq-rs.yml`                                                              |
| `prime-rs.yml`       | `prime/prime-rs/**`, `.github/workflows/prime-rs.yml`                                                     |
| `twin-primes-rs.yml` | `twin-primes/twin-primes-rs/**`, `.github/workflows/twin-primes-rs.yml`                                   |
| `e-py.yml`           | `e/*.py`, `e/install_deps.sh`, `e/Makefile`, `.github/workflows/e-py.yml`                                 |
| `e-rs.yml`           | `e/e-rs/**`, `.github/workflows/e-rs.yml`                                                                 |
| `factorial-py.yml`   | `factorial/*.py`, `factorial/install_deps.sh`, `factorial/Makefile`, `.github/workflows/factorial-py.yml` |
| `factorial-rs.yml`   | `factorial/factorial-rs/**`, `.github/workflows/factorial-rs.yml`                                         |
| `scripts.yml`        | `scripts/**`, `tests/**`, `Makefile`, `.github/workflows/scripts.yml`                                     |

**Consequence:** Docs-only PRs (`docs/**`, root `*.md`, `*.toml`) trigger no project workflows.
The gate sees no required checks and merges immediately. Root `Makefile` changes trigger
`scripts.yml`, which runs BATS tests (including new Makefile target tests).

When a new project is added: create its workflow with a `paths:` block — the gate automatically
requires it for relevant PRs with no other changes needed.

## Component 2: Gate Script (`scripts/ci-gate.sh`)

Called as `./scripts/ci-gate.sh <PR_NUMBER>` from `auto-merge.yml`.

**Advisory checks** (failures do not block merge):

```
snyk-scan
```

**Self-checks** (excluded from evaluation — these are jobs in `auto-merge.yml` itself):

```
secret-scan
auto-merge
```

**Algorithm:**

```
TIMEOUT = 1800s (30 minutes)
POLL_INTERVAL = 30s

loop until timeout:
    checks = gh pr checks <PR> --json name,state
    non-terminal = checks where state in {queued, in_progress, pending, waiting, requested}
    if non-terminal is empty:
        break
    sleep POLL_INTERVAL

if timed out:
    print error, exit 1

required = checks where name not in (advisory ∪ self-checks)
if required is empty:
    exit 0   # docs-only PR, nothing to gate on

failures = required where state not in {success, skipped}
if failures is non-empty:
    print names of failed checks, exit 1

exit 0
```

**`gh` call:** `gh pr checks "$PR" --json name,state` returns a JSON array of objects with
`name` and `state` fields. The script uses `jq` to parse.

**Check name format:** `gh pr checks --json name` returns the job `name:` field value (e.g.
`"Test pi-rs"`, `"secret-scan"`). The advisory and self-check lists must use these exact
strings. The implementer must verify names against actual PR check output before hardcoding
them — run `gh pr checks <PR> --json name,state` on a live PR to confirm.

**Terminal states:** `success`, `failure`, `skipped`, `cancelled`, `timed_out`.

**Offline/local compatibility:** The script uses only `gh` and `jq`. Both are mocked in the
BATS test suite so tests run without a GitHub token.

## Component 3: `auto-merge.yml` Changes

The `auto-merge` job gains one step between checkout and merge:

```yaml
- name: Run gate check
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    PR=$(gh pr list --head "${{ github.head_ref }}" --json number --jq '.[0].number')
    ./scripts/ci-gate.sh "${PR}"
```

If the gate exits 1, the job fails — the PR stays open with a visible red check in GitHub.
`needs: [secret-scan]` is retained unchanged.

## Component 4: BATS Tests

### `tests/scripts/ci_gate.bats`

Uses a new `gh` mock in `tests/mocks/gh`. Real `jq` is used — it is a data transformation
tool that is safe in tests and available in CI. The `gh` mock reads `MOCK_GH_PR_CHECKS_1`,
`MOCK_GH_PR_CHECKS_2`, … from the environment on sequential calls (using a counter file in
`$BATS_TEST_TMPDIR`), allowing polling behaviour to be simulated.

Test cases:

- All required checks `success` → exit 0
- One required check `failure` → exit 1, message names the failed check
- Advisory check (`snyk-scan`) `failure`, all required `success` → exit 0
- First poll returns in-progress checks, second poll returns all terminal and passing → exit 0
  (verifies polling loop)
- Timeout reached before terminal state → exit 1 with timeout message
- No checks triggered (empty check list, docs-only PR scenario) → exit 0
- PR number argument missing → exit 1 with usage message

### `tests/scripts/makefile.bats`

Uses the existing `make` mock (PATH-injected). Tests root `Makefile` targets by sourcing the
Makefile's logic or calling `make -f Makefile <target>` with mocked sub-commands.

Test cases:

- `make install-hooks` invokes `ln -sf` for pre-commit and pre-push hooks
- `make test-hooks` calls `bats --recursive tests/`
- Both targets present in `.PHONY`

## Files Changed

| File                                   | Change                                   |
| -------------------------------------- | ---------------------------------------- |
| `.github/workflows/pi-py.yml`          | Add `paths:` block                       |
| `.github/workflows/pi-rs.yml`          | Add `paths:` block                       |
| `.github/workflows/fib-py.yml`         | Add `paths:` block                       |
| `.github/workflows/fib-rs.yml`         | Add `paths:` block                       |
| `.github/workflows/sq-py.yml`          | Add `paths:` block                       |
| `.github/workflows/sq-rs.yml`          | Add `paths:` block                       |
| `.github/workflows/prime-rs.yml`       | Add `paths:` block                       |
| `.github/workflows/twin-primes-rs.yml` | Add `paths:` block                       |
| `.github/workflows/e-py.yml`           | Add `paths:` block                       |
| `.github/workflows/e-rs.yml`           | Add `paths:` block                       |
| `.github/workflows/factorial-py.yml`   | Add `paths:` block                       |
| `.github/workflows/factorial-rs.yml`   | Add `paths:` block                       |
| `.github/workflows/scripts.yml`        | Add `paths:` block (includes `Makefile`) |
| `.github/workflows/auto-merge.yml`     | Add gate step before merge               |
| `scripts/ci-gate.sh`                   | New gate script                          |
| `tests/mocks/gh`                       | New mock for `gh` CLI                    |
| `tests/scripts/ci_gate.bats`           | New BATS tests for gate script           |
| `tests/scripts/makefile.bats`          | New BATS tests for root Makefile         |
| `CLAUDE.md`                            | Update CI table, document gate script    |
| `docs/cursor/README.md`                | Add entry to All Plans table             |
| `docs/superpowers/README.md`           | Add entry to All Plans table             |

## Out of Scope

- Changing advisory status of `snyk-scan` (separate decision)
- GitHub branch protection (requires paid plan)
- Per-PR override of the required check list
