# Mutation-notify Mock Isolation and Per-Workflow Labels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `tests/mocks/gh` able to fail one call at a time so three unpinned error-propagation guards gain killing tests, and replace `mutation-notify.sh`'s hardcoded `mutation-failure` label with a per-workflow `ISSUE_LABEL` so the Rust workflow can no longer close the Python workflow's tracking issue.

**Architecture:** Two independent components in one PR. The mock gains a subcommand-derived exit-code key with a fallback to the existing `MOCK_GH_EXIT`, so `ci_gate.bats` is untouched. The notify script reads its label from the workflow step `env:` instead of hardcoding it; Rust keeps the incumbent `mutation-failure` so nothing needs migrating, and only Python gets a new label.

**Tech Stack:** bash, bats-core, GitHub Actions YAML, `gh` CLI.

Spec: [`2026-09-01-mutation-notify-mock-isolation-and-labels-design.md`](../specs/2026-09-01-mutation-notify-mock-isolation-and-labels-design.md) @ `8ea4033`.

## Global Constraints

- `MOCK_GH_EXIT` MUST keep working as the all-calls-fail fallback. `tests/scripts/ci_gate.bats:65` depends on it and MUST NOT be edited. Its passing unchanged is the regression check for the mock change.
- Rust's label stays **`mutation-failure`** (incumbent). Only Python gets **`mutation-failure-python`**. Do not rename Rust's — the asymmetry is deliberate and removes a manual migration step.
- The guards at `mutation-notify.sh:115` (`gh issue comment`, red path) and `:119` (`gh issue create`) are **equivalent mutants** — each is the last statement of `main()`, so stripping `|| return 1` returns 4 instead of 1 and no `status -ne 0` oracle can discriminate. Do NOT write tests for them and do NOT invent exact-rc assertions to manufacture a kill.
- Only three guards are killable, all three **verified red**. **Derive their line numbers at run time — do NOT hardcode them.** They have already shifted twice in this branch (Task 1's plan correction, then Task 2 adding a guard line), and `mutation-notify.sh:82-83` states the convention: no line range, since it would rot. Anchor on content:
  ```bash
  LOOKUP=$(grep -n "jq '.\[0\].number // empty') || return 1" scripts/mutation-notify.sh | cut -d: -f1)
  COMMENT=$(grep -n 'Green as of' scripts/mutation-notify.sh | cut -d: -f1)
  CLOSE=$(grep -n 'gh issue close' scripts/mutation-notify.sh | cut -d: -f1)
  ```
  Each strip yields **31 ok / 1 not-ok**, killing a *different* test each time. The two equivalent mutants — the red-path `gh issue comment` and `gh issue create` — yield **0**, measured by two reviewers.
- Baseline measured at `8ea4033`: `mutation_notify.bats` 29 ok / 0 not-ok; `ci_gate.bats` 10 ok / 0 not-ok.
- `bats` is required (`brew install bats-core` / `apt-get install -y bats`).
- **Pre-merge step, required — ALREADY DONE 2026-09-02.** `mutation-failure-python` exists
  (`#B60205`, "Monthly mutation run failed"), created by the operator before the plan was
  dispatched. Task 4's check should confirm it rather than discover it. Re-running the
  command below is harmless but unnecessary. It was required because it is idempotent
  and needs no ordering against the merge. The script's `gh label create ... || true` is the
  fallback, not the plan — if it were relied on, a swallowed failure would surface one line
  later as a red `notify` job that filed nothing, on the Python workflow's first red run,
  which is the one run where the tracking issue is the product.

  ```bash
  gh label create mutation-failure-python --repo brujack/math \
    --color B60205 --description "Monthly mutation run failed"
  ```

## Verification Planning

**Session-level command:** `make test-hooks` from the repo root.

**Expected observable:** all bats suites green, with `mutation_notify.bats` risen from 29 cases to 33 and `ci_gate.bats` still at 10.

**Edge cases that must be exercised:**

1. Each of the three killable guards, stripped one at a time, turns the suite red (Tasks 1, 4).
2. Neutering the mock's per-key lookup turns _only_ the new propagation tests red — the control for the control (Task 4).
3. `ci_gate.bats` passes with no edit, proving the `MOCK_GH_EXIT` fallback survives (Tasks 1, 4).
4. An unset `ISSUE_LABEL` fails visibly rather than querying an empty label (Task 2).

---

### Task 1: Per-call exit keys in the gh mock, with their killing tests

```yaml-task
id: 1
description: Derive MOCK_GH_EXIT_<SUBCOMMAND>_<VERB> from the first two args with a MOCK_GH_EXIT fallback, and add killing tests for the three killable propagation guards
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/mutation_notify.bats
    exit_code: 0
  - cmd: 'bash -c "[ $(grep -c ''^@test'' tests/scripts/mutation_notify.bats) -eq 32 ]"'
    exit_code: 0
  - cmd: bats tests/scripts/ci_gate.bats
    exit_code: 0
max_retries: 3
files_touched:
  - tests/mocks/gh
  - tests/scripts/mutation_notify.bats
depends_on: []
```

**Merged from the original Tasks 1 and 2 at pre-flight.** They were split, and the split was
unworkable: the mock change's only possible RED test lives in the bats file, which was outside
the mock task's `files_touched`, and both of that task's gates passed unchanged on the base
tree. Together they are one red-green cycle with a gate that genuinely fails on base (29 cases,
not 32).

**Files:** `tests/mocks/gh` (22 lines today), `tests/scripts/mutation_notify.bats` (29 `@test`
cases → 32).

**RED first.** Write the three tests below, run `bats tests/scripts/mutation_notify.bats`, and
confirm they fail against the *unmodified* mock. They will — the unmodified mock ignores
`MOCK_GH_EXIT_ISSUE_LIST` entirely, so `main` returns 0 and the `-ne 0` assertion fails. Do not
commit this RED state: `scripts/pre-commit` runs `make lint` and a failing suite blocks it. Verify
RED by running bats directly, then implement, then make one combined commit.

```bash
@test "a failing issue lookup propagates and files nothing" {
    export RESULT="failure"
    export MOCK_GH_EXIT_ISSUE_LIST=4
    run main
    [ "${status}" -ne 0 ]
    run ! grep -q "gh issue create" "${MOCK_CALLS_FILE}"
    run ! grep -q "gh issue comment" "${MOCK_CALLS_FILE}"
}

@test "a failing green-path comment propagates and does not close the issue" {
    export RESULT="success"
    export MOCK_GH_ISSUE_LIST="98"
    export MOCK_GH_EXIT_ISSUE_COMMENT=4
    run main
    [ "${status}" -ne 0 ]
    run ! grep -q "gh issue close" "${MOCK_CALLS_FILE}"
}

@test "a failing issue close propagates rather than reporting success" {
    export RESULT="success"
    export MOCK_GH_ISSUE_LIST="98"
    export MOCK_GH_EXIT_ISSUE_CLOSE=4
    run main
    [ "${status}" -ne 0 ]
    grep -q "gh issue comment 98 --repo" "${MOCK_CALLS_FILE}"
}
```

The third case asserts the **positive** (`comment` did happen) as well as the failure, so it
cannot pass on an empty call log.

**Do NOT add cases for `:115` or `:119`.** They are equivalent mutants — see Global Constraints.
Add a comment above the three cases recording that, so a later reader does not "complete the set".

**GREEN.** In `tests/mocks/gh`, replace the unconditional `MOCK_GH_EXIT` check at line 4 with a
derived lookup. Keep the `printf` call-log line at line 2 **before** it, so failing calls are
still logged. Add no other output to `MOCK_CALLS_FILE` — `assert_all_gh_calls_carry_repo` counts
`grep -c '^gh '` and a new line risks the count.

```bash
# Failure is selectable per subcommand via MOCK_GH_EXIT_<SUBCOMMAND>_<VERB>, derived
# from "$1_$2" upper-cased with non-alphanumerics stripped: `gh issue close` reads
# MOCK_GH_EXIT_ISSUE_CLOSE, `gh label create` reads MOCK_GH_EXIT_LABEL_CREATE.
# MOCK_GH_EXIT remains the all-calls-fail fallback (ci_gate.bats relies on it).
_key="MOCK_GH_EXIT_$(printf '%s_%s' "${1:-}" "${2:-}" \
    | tr 'a-z-' 'A-Z_' | tr -cd '[:alnum:]_')"
_rc="${!_key:-${MOCK_GH_EXIT:-0}}"
if [[ "${_rc}" -ne 0 ]]; then
    exit "${_rc}"
fi
```

Commit message: use this EXACT message. Do NOT invoke `caveman:caveman-commit`:

`test(mocks): fail one gh call at a time`

**Interfaces:**

- Produces: env-var contract `MOCK_GH_EXIT_ISSUE_LIST`, `MOCK_GH_EXIT_ISSUE_COMMENT`,
  `MOCK_GH_EXIT_ISSUE_CLOSE`, `MOCK_GH_EXIT_ISSUE_CREATE`, `MOCK_GH_EXIT_LABEL_CREATE`, and the
  case count 32. Consumed by Tasks 2, 3 and 4.
- Preserves: `MOCK_GH_EXIT` (all calls), `MOCK_GH_ISSUE_LIST`, `MOCK_GH_CHECK_RUNS_N`,
  `MOCK_GH_PR_SHA`.

---

### Task 2: ISSUE_LABEL replaces the hardcoded label in mutation-notify.sh

```yaml-task
id: 2
description: Read the issue label from ISSUE_LABEL with a :? guard instead of hardcoding mutation-failure at three call sites
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: "! command grep -q 'mutation-failure' scripts/mutation-notify.sh"
    exit_code: 0
  - cmd: bats tests/scripts/mutation_notify.bats
    exit_code: 0
  - cmd: shellcheck scripts/mutation-notify.sh
    exit_code: 0
max_retries: 3
files_touched:
  - scripts/mutation-notify.sh
  - tests/scripts/mutation_notify.bats
depends_on: [1]
```

**Files:** `scripts/mutation-notify.sh`, `tests/scripts/mutation_notify.bats`.

Three literal occurrences change (`:99` lookup, `:117` label create, `:119` issue create), plus a new guard beside the existing three:

```bash
    : "${RESULT:?}"
    : "${REPO:?}"
    : "${ISSUE_TITLE:?}"
    : "${ISSUE_LABEL:?}"
```

`: "${ISSUE_LABEL:?}"` fires on unset **and** empty, so `--label ""` is unreachable. No `export` is needed — unlike the rejected `env.ISSUE_TITLE` jq design, the value is passed to `gh` as an argument, not read from the process environment by a child.

**`setup()` MUST export `ISSUE_LABEL`.** Without it the new `:?` guard fails **8** pre-existing cases. Add beside the existing `ISSUE_TITLE` export at `:20`:

```bash
    export ISSUE_LABEL="mutation-failure"
```

Add one case, mirroring the three existing unset-guard tests:

```bash
@test "main fails visibly when ISSUE_LABEL is unset" {
    export RESULT="success"
    export MOCK_GH_ISSUE_LIST=""
    unset ISSUE_LABEL
    run main
    [ "${status}" -ne 0 ]
}
```

**Add a comment above the final `if/else` recording that its two `|| return 1` guards are
decorative *by position*.** Each is currently the last statement of its branch, so stripping it
returns 4 instead of 1 — both non-zero, so no `status -ne 0` oracle can discriminate, which is
why Task 2 writes no test for them. Appending anything after `gh issue create` changes that:
guarded and stripped then return 1 vs 0, the appended statement runs only in the stripped
version, and the guard becomes load-bearing with nothing covering it. The comment goes beside
the code because the next editor will read the function, not the spec.

**Do not touch `:314` or `:333`.** They assert `--label mutation-failure` as part of a whole-call literal, and Rust keeps that label, so both stand unchanged. This is what the asymmetric naming buys.

**Interfaces:**

- Consumes: nothing from earlier tasks at runtime; sequenced after Task 2 so the case count is stable.
- Produces: `ISSUE_LABEL` as a required env var, consumed by Task 4's workflow blocks.

---

### Task 3: Workflow env blocks and CLAUDE.md

```yaml-task
id: 3
description: Set ISSUE_LABEL per workflow and correct the mock-variable name CLAUDE.md records
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'bash -c "[ $(grep -c ''ISSUE_LABEL: mutation-failure$'' .github/workflows/mutation-testing.yml) -eq 1 ]"'
    exit_code: 0
  - cmd: 'bash -c "[ $(grep -c ''ISSUE_LABEL: mutation-failure-python$'' .github/workflows/mutation-testing-python.yml) -eq 1 ]"'
    exit_code: 0
  - cmd: "! command grep -q 'MOCK_GH_PR_CHECKS' CLAUDE.md"
    exit_code: 0
  - cmd: bats tests/scripts/mutation_notify.bats
    exit_code: 0
max_retries: 3
files_touched:
  - .github/workflows/mutation-testing.yml
  - .github/workflows/mutation-testing-python.yml
  - CLAUDE.md
depends_on: [2]
```

**TDD waiver:** configuration and documentation only — two YAML env entries and a prose correction. No behaviour to test beyond the greps above; the script's use of `ISSUE_LABEL` is covered by Task 3.

**Files:**

`.github/workflows/mutation-testing.yml` — add to the notify step's `env:` block, beside `ISSUE_TITLE`:

```yaml
ISSUE_LABEL: mutation-failure
```

`.github/workflows/mutation-testing-python.yml` — same position:

```yaml
ISSUE_LABEL: mutation-failure-python
```

`CLAUDE.md:477` currently reads ``gh`(sequential JSON responses via`MOCK_GH_PR_CHECKS_N`, exits `$MOCK_GH_EXIT`)`. That variable **does not exist in the code** — the live name is `MOCK_GH_CHECK_RUNS_N`. Correct it and document the new family:

```
`gh` (sequential JSON responses via `MOCK_GH_CHECK_RUNS_N`, exits `$MOCK_GH_EXIT`, or
`$MOCK_GH_EXIT_<SUBCOMMAND>_<VERB>` to fail a single call — e.g. `MOCK_GH_EXIT_ISSUE_CLOSE`)
```

Also add a clause to `CLAUDE.md:381` naming Python's separate label. The existing sentence stays true for Rust and must not be rewritten.

**Interfaces:**

- Consumes: `ISSUE_LABEL` contract from Task 3; the derived-key name shape from Task 1.

---

### Task 4: Prove the gates by mutation

```yaml-task
id: 4
description: Run the four mutations from the spec and record that three go red and the control turns only the new tests red
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: make test-hooks
    exit_code: 0
  - cmd: bats tests/scripts/ci_gate.bats
    exit_code: 0
max_retries: 2
files_touched:
  - docs/superpowers/plans/2026-09-01-mutation-notify-mock-isolation-and-labels.md
depends_on: [3]
```

**TDD waiver:** verification-only. Writes no production code; mutates, measures, reverts, and records.

For each mutation: apply it, run `bats tests/scripts/mutation_notify.bats`, record the not-ok count, then `git checkout --` the file before the next one. Confirm `git status --porcelain` is clean at the end.

| #   | mutation                                                                        | expect                                 |
| --- | ------------------------------------------------------------------------------- | -------------------------------------- |
| V3  | strip `\|\| return 1` from the `gh issue list` guard (derive `LOOKUP`; it is the **continuation** line, not the `gh issue list` line itself)                              | **red**                                |
| V4  | strip `\|\| return 1` from `gh issue close` (derive `CLOSE`)                                                | **red**                                |
| V5  | strip `\|\| return 1` from `gh issue comment` green path (derive `COMMENT`)                    | **red**                                |
| V6  | in `tests/mocks/gh`, replace the derived lookup with `_rc="${MOCK_GH_EXIT:-0}"` | **red, and only Task 2's three cases** |

V6 is the control for the control: without it, Task 2's cases passing is consistent both with a working per-key mock and with one that ignores the keys but fails anyway.

**If V3, V4 or V5 comes back green, STOP and report a blocker** — the test does not pin what it claims, and manufacturing an assertion to force red is the failure this plan exists to avoid.

**Do NOT run mutations on `:115` or `:119`.** They are equivalent mutants; a green result there is expected and is not a finding.

Record the four results as a table in this plan file under a `## Mutation results` heading,
with the not-ok counts.

**Also confirm the pre-merge label step is done** — `gh label list --repo brujack/math | grep
mutation-failure-python` must return a row. If it does not, report it in the task result: the
change is still safe to merge, but Python's first red run then depends on the fallback
`gh label create` path, which has never executed in this repo.

---

## Self-Review

1. **Spec coverage.** §1 labels → Tasks 2, 3. §2 mock → Task 1. §3 docs → Task 3. §4 tests → Tasks 1, 2. V1/V2 → Task 4's `make test-hooks`. V3–V6 → Task 4. V7 → Task 2's gate. V8 → Task 3's gates. No gaps.
2. **Placeholder scan.** None; every code block is literal.
3. **Type consistency.** `ISSUE_LABEL`, `MOCK_GH_EXIT_<SUBCOMMAND>_<VERB>` spelled identically across Tasks 1–4.
4. **YAML blocks.** Present on all 5 tasks; `cmd:` values containing `": "` are single-quoted.
5. **TDD `files_touched` includes the test file.** Tasks 2 and 3 both list `tests/scripts/mutation_notify.bats`.
6. **Token budget.** Each block under 2KB.
7. **ADR significance.** No new Phase 3 gate, HOLD-capable check, or storage choice — no ADR needed.
8. **`files_touched` matches the prose.** Task 4 lists all three files its body edits.

**Gate falsifiability, measured at `8ea4033` rather than reasoned about:**

| gate                                                      | base tree                               | verdict                                                              |
| --------------------------------------------------------- | --------------------------------------- | -------------------------------------------------------------------- |
| `! grep -q 'mutation-failure' scripts/mutation-notify.sh` | rc **1** (3 occurrences, grep ran fine) | real gate                                                            |
| `grep -c 'ISSUE_LABEL: mutation-failure$' …` `-eq 1`      | count 0, rc 1                           | real gate                                                            |
| `! grep -q 'MOCK_GH_PR_CHECKS' CLAUDE.md`                 | rc 1 (present at `:477`)                | real gate                                                            |
| case count `-eq 32`                                       | 29 today                                | real gate                                                            |
| `bats tests/scripts/ci_gate.bats`                         | 10 ok — passes on base                  | **not a gate; a regression check.** Named as such, kept deliberately |

An earlier draft used `! grep -q 'mutation-failure-python' scripts/mutation-notify.sh`, which
exits **0** on the base tree — that literal never appears in the script in either state,
because Python's label lives in workflow YAML. Corrected in the spec at `8ea4033`.

**What wrong implementation still passes these gates?** A mock that honours the derived keys
but breaks `MOCK_GH_ISSUE_LIST` would pass Tasks 1–3 and fail Task 4's V6 shape. A test that
asserts only `status -ne 0` without the call-log assertion would pass Task 2's gate — which is
why each case carries an absence or presence assertion on `MOCK_CALLS_FILE`, and why Task 4's
mutation runs are a task rather than advice.
