# Worldclass Slice 7: No Core Dumps From Mutation Runs Implementation Plan

> **Status: DONE** (math#218, 8fb61f3; V1 sweep pending)

spec: docs/superpowers/specs/2026-11-06-worldclass-slice7-mutant-core-dumps-design.md
scope: PR1

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop mutation runs from writing core dumps, so capped-out mutants no longer stream multi-GB images to `systemd-coredump` and take down hosted runners; fix #217's misleading issue body.

**Architecture:** One `ulimit -c 0` line in the Rust template's `MUTANTS_SETUP` and the Python template's `MUTANTS_CAP`, rendered to every crate and project by `scripts/render_crate_files.py --write`. Bats tests observe the limit from mocked `cargo`/`cosmic-ray` after raising the parent limit. `mutation-notify.sh` stops prepending an empty `verdicts-present` body on the expected-units path. ADR-0043, root `CLAUDE.md` and the Backlog record the cause.

**Tech Stack:** GNU make recipes run under `bash -c`, bats-core, bash.

## Global Constraints

- Rust template line goes after `ulimit -f 262144` and before the `MUTANTS_UNCAPPED` branch; Python template likewise in `MUTANTS_CAP`.
- Failure line, both templates, verbatim: `error: cannot disable core dumps (ulimit -c 0).` then exit 1.
- Use bare `ulimit -c 0` (lowers soft and hard; the lock is intended), never `ulimit -Sc 0`.
- `ulimit -v 8388608` is unchanged (N1); `mutation-testing.yml` unchanged (N2); cargo-mutants flags unchanged (N3).
- Edit templates only, then `python3 scripts/render_crate_files.py --write`; never hand-edit a rendered Makefile (N4).
- Root `CLAUDE.md` must stay at or under 30,000 bytes (it is 29,997 before this plan).

## Verification

- Session-level: `make test` green on the branch (bats + root Python, includes `tests/test_crate_uniformity.py`).
- Each new core-limit test fails on the base tree (records `core=unlimited`) and passes after the template change; Task 1 and 2 implementers show both runs.
- After merge (spec V1, outside this plan): one full 11-crate `mutation-testing.yml` dispatch with no lost leg; then the Backlog row is removed citing that run.

---

### Task 1: Rust template disables core dumps

```yaml-task
id: 1
description: Add ulimit -c 0 to the Rust template MUTANTS_SETUP, render all 11 crates, and add bats tests observing core=0 from mocked cargo
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R4]
acceptance:
  - cmd: 'bats -f "no core dumps" tests/scripts/makefile.bats'
    exit_code: 0
    stdout_match: '^ok '
  - cmd: 'test "$(grep -c "@test .*no core dumps" tests/scripts/makefile.bats)" -ge 4'
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/Makefile, pi/pi-rs/Makefile, prime/prime-rs/Makefile, fib/fib-rs/Makefile, sq/sq-rs/Makefile, twin-primes/twin-primes-rs/Makefile, e/e-rs/Makefile, factorial/factorial-rs/Makefile, perfect-numbers/perfect-numbers-rs/Makefile, collatz/collatz-rs/Makefile, goldbach/goldbach-rs/Makefile, amicable/amicable-rs/Makefile, tests/scripts/makefile.bats]
depends_on: []
```

**Steps:**

- [ ] In `tests/scripts/makefile.bats` `_rs_stub_setup`'s cargo stub (after the `fsize=` line, ~455) add `printf 'core=%s\n' "$(ulimit -c)" >> "${CALLS}"`.
- [ ] Add a helper above the Rust tests:

```bash
# Both dev boxes run with a soft core limit of 0, so a test inheriting it would see 0
# without the fix. Raise the soft limit to the hard one first; a zero hard limit cannot
# test anything, which is a failure in CI and a skip elsewhere.
_raise_core_limit() {
    local hard
    hard="$(ulimit -Hc)"
    if [ "${hard}" = "0" ]; then
        [ "${CI:-}" = "true" ] && { printf 'hard core limit is 0 in CI\n' >&2; return 1; }
        skip "hard core limit is 0; the parent limit cannot be raised"
    fi
    ulimit -Sc "${hard}"
}
```

- [ ] Add four tests, each `_rs_stub_setup; _raise_core_limit; <run>; [ "${status}" -eq 0 ]; grep -qxF 'core=0' "${CALLS}"` (a missing record line fails the grep):
  - `@test "make mutants runs cargo with no core dumps"` — `run _rs_make mutants`
  - `@test "make mutants runs cargo with no core dumps even with MUTANTS_UNCAPPED set"` — `MUTANTS_UNCAPPED=1 run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS make -C "${CRATE}" mutants`
  - `@test "make mutants-diff runs cargo with no core dumps"` — write `${BATS_TEST_TMPDIR}/pr.diff`, `run _rs_make mutants-diff DIFF=...`
  - `@test "make mutants-diff runs cargo with no core dumps even with MUTANTS_UNCAPPED set"`
- [ ] Run `bats -f "no core dumps" tests/scripts/makefile.bats`: all four FAIL (stub records `core=unlimited`). Paste the output.
- [ ] In `scripts/crate_templates/Makefile` `MUTANTS_SETUP`, immediately after the `ulimit -f 262144 ... exit 1; };` clause, add `ulimit -c 0 2>/dev/null || { printf "error: cannot disable core dumps (ulimit -c 0).\n" >&2; exit 1; };` on the same continued line, before `cleanup() {`. Update the comment above `MUTANTS_SETUP` to say it also disables core dumps (hosted runners pipe them to systemd-coredump; ADR-0043).
- [ ] `python3 scripts/render_crate_files.py --write`; `git diff --stat` shows the template plus 11 crate Makefiles.
- [ ] Re-run the four tests: PASS. Run `make test`: green.
- [ ] Commit (message via `caveman:caveman-commit`).

### Task 2: Python template disables core dumps

```yaml-task
id: 2
description: Add ulimit -c 0 to the Python template MUTANTS_CAP, render all 9 Python projects, and add bats tests observing core=0 from mocked cosmic-ray
role: executor
model: sonnet
tdd: required
requirements: [R3, R4]
acceptance:
  - cmd: 'bats -f "python .*no core dumps" tests/scripts/makefile.bats'
    exit_code: 0
    stdout_match: '^ok '
  - cmd: 'test "$(grep -c "@test \"python .*no core dumps" tests/scripts/makefile.bats)" -ge 4'
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/python/Makefile, pi/Makefile, fib/Makefile, sq/Makefile, e/Makefile, factorial/Makefile, perfect-numbers/Makefile, collatz/Makefile, amicable/Makefile, triangle/Makefile, tests/scripts/makefile.bats]
depends_on: [1]
```

**Steps:**

- [ ] Confirm the 9 rendered Python Makefiles: `git ls-files '*/Makefile' | xargs grep -l '^MUTANTS_CAP ='` (excluding the template). If the list differs from `files_touched`, stop and report.
- [ ] In `_py_stub_setup`'s cosmic-ray stub (after the `fsize=` line, ~1266) add `printf '%s core=%s\n' "$1" "$(ulimit -c)" >> "${CALLS}.env"`.
- [ ] Add four tests using `_raise_core_limit` from Task 1. Each asserts at least one `core=` line exists and every one is `core=0`:

```bash
    run _py_make mutants-baseline     # or: mutants
    [ "${status}" -eq 0 ]
    grep -qE '^[a-z-]+ core=0$' "${CALLS}.env"
    run grep -E ' core=' "${CALLS}.env"
    [ "${status}" -eq 0 ]
    run grep -vE ' core=0$' <(grep -E ' core=' "${CALLS}.env")
    [ "${status}" -eq 1 ]
```

Names: `"python mutants-baseline runs cosmic-ray with no core dumps"`, `"python mutants-baseline runs cosmic-ray with no core dumps even with MUTANTS_UNCAPPED set"` (`MUTANTS_UNCAPPED=1 run _py_make mutants-baseline`), and the same two for `mutants`.

- [ ] Run `bats -f "python .*no core dumps" tests/scripts/makefile.bats`: all four FAIL. Paste the output.
- [ ] In `scripts/crate_templates/python/Makefile` `MUTANTS_CAP`, after the `ulimit -f 262144 ... exit 1; };` clause and before `if [ -n "$${MUTANTS_UNCAPPED}" ]`, add `ulimit -c 0 2>/dev/null || { printf "error: cannot disable core dumps (ulimit -c 0).\n" >&2; exit 1; };`. Extend the comment above it the same way as Task 1.
- [ ] `python3 scripts/render_crate_files.py --write`; re-run the four tests (PASS) and `make test` (green).
- [ ] Commit.

### Task 3: Notify omits an empty verdicts-present body

```yaml-task
id: 3
description: On the EXPECTED_STATUS_UNITS path, do not prepend build_body when the cause is verdicts-present and no status file is red; update the test pinning the old body
role: executor
model: sonnet
tdd: required
requirements: [R5, R6]
acceptance:
  - cmd: 'bats tests/scripts/mutation_notify.bats'
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-notify.sh, tests/scripts/mutation_notify.bats]
depends_on: [2]
```

**Steps:**

- [ ] Rewrite the test at `tests/scripts/mutation_notify.bats:680` ("RESULT=failure with a missing unit carries both ...", pi green, fib missing) to the new contract and rename it `"EXPECTED_STATUS_UNITS: RESULT=failure with no red unit posts the missing-status body alone"`: keep `[ "${status}" -eq 1 ]`, `Missing crates:`, `- fib`; assert the posted body starts `Cause: missing-status` and `run ! grep -qF -- "verdicts-present" "${MOCK_CALLS_FILE}"`.
- [ ] Add `"EXPECTED_STATUS_UNITS: RESULT=failure with a red unit keeps the verdicts-present body first"`: `pi` status `red: pi - exit code 2`, `fib` missing; assert `Cause: verdicts-present` precedes `Cause: missing-status` in `${MOCK_CALLS_FILE}`, `- pi: red: pi - exit code 2` appears exactly once (`grep -c`), and `- fib` appears.
- [ ] Run the file: the rewritten test FAILS, the new one passes on master behaviour. Paste output.
- [ ] In `scripts/mutation-notify.sh` (the block at ~200-207):

```bash
    _omit_red=0
    _cause=""
    if [[ "${RESULT}" != "success" ]]; then
        _cause=$(attribute) || return 2
        # verdicts-present with no red file has nothing to say ("none flagged"),
        # so the missing-status body stands alone instead of under a misleading prefix.
        if [[ "${_cause}" == "verdicts-present" ]]; then
            if [[ -n "$(render_red_units)" ]]; then _omit_red=1; else _cause=""; fi
        fi
    fi
    _body=$(build_units_body "${_missing%$'\n'}" "${_invalid%$'\n'}" "${_empty}" "${_omit_red}") || return 2
    if [[ -n "${_cause}" ]]; then
        _body="$(build_body "${_cause}")"$'\n\n'"${_body}"
    fi
```

Update the comment above the block to match.

- [ ] Re-run the file (green) and `make test` (green). Commit.

### Task 4: ADR-0043, CLAUDE.md, Backlog and plan index

```yaml-task
id: 4
description: Write ADR-0043 and its index row, amend the CLAUDE.md cap line within the byte budget, rewrite the runner-loss Backlog row, and add the slice 7 plan-index row (docs-only, no behaviour change, so tdd not applicable)
role: executor
model: sonnet
tdd: not-applicable
requirements: [R7, R8, R9]
acceptance:
  - cmd: 'test -f docs/adr/0043-mutation-runs-disable-core-dumps.md && grep -q 42314053243 docs/adr/0043-mutation-runs-disable-core-dumps.md && grep -q 42321581538 docs/adr/0043-mutation-runs-disable-core-dumps.md'
    exit_code: 0
  - cmd: 'grep -qF "(0043-mutation-runs-disable-core-dumps.md)" docs/adr/README.md'
    exit_code: 0
  - cmd: 'grep -qF "ulimit -c 0" CLAUDE.md && test "$(wc -c < CLAUDE.md)" -le 30000'
    exit_code: 0
  - cmd: 'grep -E "^\| Hosted runners lost mid-sweep" docs/superpowers/README.md | grep -q "awaiting V1"'
    exit_code: 0
  - cmd: 'grep -qF "plans/2026-11-06-worldclass-slice7-mutant-core-dumps.md" docs/superpowers/README.md'
    exit_code: 0
max_retries: 3
files_touched: [docs/adr/0043-mutation-runs-disable-core-dumps.md, docs/adr/README.md, CLAUDE.md, docs/superpowers/README.md]
depends_on: [3]
```

**Steps:**

- [ ] ADR-0043 (format of `docs/adr/0042-*.md`: `**Date:** 2026-11-06`, `**Status:** Accepted`, Context / Decision / Consequences / Related). Context: the spec's "Cause, measured" section — core_pattern pipes to systemd-coredump with `ulimit -c unlimited` on `ubuntu-latest`; capped-out mutants stream 4-6 GB dumps and pile up; run 42314053243 (collatz shutdown, fib lost, swap full, `mem.full` 76 %) vs 42321581538 (`ulimit -c 0`: 5/5 green, 0 dump samples, swap 0). Decision: `ulimit -c 0` in both templates, before the uncapped branch; amends ADR-0024 (the cap bounds memory only with dumps off). Consequences: earlier timeout counts on this image partly reflect dump stalls; V1 may surface real MISSED mutants (e-rs, factorial-rs), which need killing tests. Related: ADR-0024, ADR-0042, spec path, issue #217.
- [ ] `docs/adr/README.md`: add the 0043 row after 0042 (`Accepted`); change 0024's status cell to `Partially superseded by 0042; amended by 0043`.
- [ ] Root `CLAUDE.md` "Keep `ulimit -v 8388608` (8 GiB) in Rust `MUTANTS_SETUP`..." line: name `ulimit -c 0` (no core dumps, ADR-0043) and that both templates set it. Stay ≤ 30,000 bytes by tightening this same line (e.g. drop "(8 GiB)"); before cutting any other fact, grep `../ai-config/docs/knowledge/math-*.md` for it and keep it if it lives nowhere else.
- [ ] `docs/superpowers/README.md`: rewrite the "Hosted runners lost mid-sweep on fib-rs/pi-rs" row: cause is capped-out mutants' core dumps piped to systemd-coredump (probe runs 42314053243 / 42321581538); fixed by `ulimit -c 0` (this slice, ADR-0043); "awaiting V1: remove after a full sweep with no lost leg"; issue #217. Add the plan-index row after slice 6: `| 2026-11-06 | [worldclass-slice7-mutant-core-dumps](plans/2026-11-06-worldclass-slice7-mutant-core-dumps.md) | [spec](specs/2026-11-06-worldclass-slice7-mutant-core-dumps-design.md) | In progress |`.
- [ ] Run the acceptance commands; commit.

## Non-goal check

Fresh reviewer, `nongoal-check.md`, against N1-N4 (2026-11-06): N1 CLEAR, N2 CLEAR, N3 CLEAR, N4 CLEAR. No CONFLICT or UNCLEAR, so no plan revision or amendment.
