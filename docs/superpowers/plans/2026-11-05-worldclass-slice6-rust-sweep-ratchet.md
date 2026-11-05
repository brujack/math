# Worldclass Slice 6: Monthly Rust Sweep Holds 0 Missed Implementation Plan

> **Status: DONE** (math#208, c886752)

spec: docs/superpowers/specs/2026-11-05-worldclass-slice6-rust-sweep-ratchet-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the monthly Rust mutation sweep red on any surviving mutant, make its tracking issue say which mutant and why, and record the timeout-counts-as-caught rule with all 56 timeouts classified.

**Architecture:** `mutation-testing.yml` passes `0 1` to the unchanged classifier. One helper in `scripts/mutation-notify.sh` renders red units (reason line plus a two-space-indented fenced detail block, capped at 20 lines) for both issue bodies. ADR-0042, root `CLAUDE.md` and the Backlog record the rule; V1 measures the 16 unmeasured timeouts for the ADR's table.

**Tech Stack:** bash, bats, Python `unittest` + PyYAML, GitHub Actions, cargo-mutants 27.1.0.

## Global Constraints

- `scripts/mutation-classify.sh` is not modified (N4).
- `scripts/mutation-pr-run.sh` and `.github/workflows/mutation-pr.yml` are not modified; crates still pass only `0` (N1).
- `mutation-testing-python.yml` and `scripts/mutation-python-cell.sh` are not modified (N3).
- No committed per-crate missed count or baseline file (N2).
- Root `CLAUDE.md` stays at or under 30,000 bytes; it is 29,926 now and the sweep line is 400 bytes.
- Shell follows `~/.claude/standards/shell.md`: `#!/usr/bin/env bash`, no `set -e`, `[[ ]]`, `${VAR}`, `printf`, functions `|| return 1`. Read it before Tasks 1 and 3; read `~/.claude/standards/python.md` before Task 2.
- No task runs `cargo mutants`; the orchestrator runs V1 and V3.

## Verification

- Session level: root `make test` passes (bats suite plus `make test-python`, including `tests.test_mutation_workflows`).
- V1 (orchestrator, local, before Task 4): the 16 timeouts re-run by escaped, anchored full name, each with a 1-line `--list` pre-check and `total_mutants` 1 post-check; results go into Task 4's ADR table.
- V3 (orchestrator, local): in a `git archive` copy, delete one killing assertion in `amicable/amicable-rs`, run `make mutants`, then `scripts/mutation-classify.sh "$(cat mutants.out/exit-code)" mutants.out/outcomes.json amicable 0 1`: exit 1, stderr names the survivor.
- V2 (CI, after push): `gh issue list --label mutation-failure --state open` empty; two full `mutation-testing.yml` dispatches on the branch SHA, both green, 11 status lines each with caught ≥ 1 and missed 0; per-crate sorted `missed.txt`/`caught.txt` diffed across both runs and run 41952665142; `nproc` recorded. Any mutant missed in one run and not another stops the slice.
- Edge cases covered by tests: all-timeout crate red under `0 1`; red file with no detail lines (no fence); 25 detail lines truncated to 20; `Vec<u32>` inside the fence; preamble before the first `red` line not printed; missing-status body with RESULT `failure` names each red unit once; both empty-list fallbacks.

---

### Task 1: One red-unit renderer for both issue bodies

```yaml-task
id: 1
description: mutation-notify.sh renders red units with a fenced, capped detail block from one helper used by build_body and build_units_body
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/mutation_notify.bats
    exit_code: 0
  - cmd: shellcheck --severity=warning scripts/mutation-notify.sh tests/scripts/mutation_notify.bats
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-notify.sh, tests/scripts/mutation_notify.bats]
depends_on: []
parallel_group: wave-1
requirements: [R4, R5, R6]
```

New function `render_red_units` (reads `${ARTIFACT_DIR}/status/*`, prints to stdout, empty output when no red file). For each regular file with a line starting `red`:

- [ ] Print `- <basename>: <first red line>`.
- [ ] Lines after that line (not before it) are detail. When there is at least one: print `  ` + three backticks, then up to 20 detail lines each prefixed with two spaces, then `  ... <K> more lines in the run` when K > 0, then `  ` + three backticks. No detail lines, no fence.
- [ ] `build_body` `verdicts-present`: `_names=$(render_red_units)`; fallback stays `- (none flagged; see run log)`.
- [ ] `build_units_body` uses the helper; its fallback stays `- (none)`. Add a 4th parameter `omit_red`; when `1` the `Red <unit>s:` section is not printed.
- [ ] `check_expected_units`: when RESULT is not `success` and `attribute` returns `verdicts-present`, call `build_units_body` with `omit_red=1`; any other cause keeps the red section (its `build_body` has no red list).
- [ ] Tests, each asserting exact multi-line substrings (list item, `  ` fence, `  `-prefixed lines, closing fence): two red units with detail and one green unit; red unit with no detail (no fence); 25 detail lines, one containing `Vec<u32>`, print 20 plus `  ... 5 more lines in the run`; empty-list fallbacks for both builders; missing-status body with RESULT `failure` and two red units names each exactly once (`grep -c` the unit's list line equals 1).
- [ ] Invert the two existing cases: "red units are listed with their first-line reason" now asserts `second line` present inside the fence under `- pi-3: red: pi-3 -- ...`; "a red line that is not the first line ..." now asserts `red: second red` present inside the fence and `note: preamble` absent.

**Interfaces:** Produces `render_red_units` (no args, reads `ARTIFACT_DIR`); `build_units_body <missing> <invalid> <empty> [omit_red]`.

### Task 2: Sweep classifies with max_missed 0 and min_caught 1

```yaml-task
id: 2
description: mutation-testing.yml Run mutants step passes 0 1 to the classifier, pinned by tests/test_mutation_workflows.py
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_workflows -v
    exit_code: 0
  - cmd: ruff check tests/test_mutation_workflows.py
    exit_code: 0
  - cmd: ruff format --check tests/test_mutation_workflows.py
    exit_code: 0
  - cmd: pyright tests/test_mutation_workflows.py
    exit_code: 0
  - cmd: make lint-workflows
    exit_code: 0
max_retries: 3
files_touched: [.github/workflows/mutation-testing.yml, tests/test_mutation_workflows.py]
depends_on: []
parallel_group: wave-1
requirements: [R1, R2]
```

- [ ] Test first: extend `run_crate_job`'s classifier stub to also append `"$4 $5"` to a `classify-args` file and expose it on `JobResult` (as `classifier_argc` is). Rename `test_classifier_gets_exactly_three_arguments` to `test_classifier_gets_limit_zero_and_min_caught_one` asserting `classifier_argc == ["5"]` and the recorded args `== ["0 1"]`; replace its N2 comment with one citing slice 6 / ADR-0042. Run it: fails on the 3-argument workflow.
- [ ] In the `Run mutants` step change the call to `"${GITHUB_WORKSPACE}/scripts/mutation-classify.sh" "${rc}" "${CRATE_DIR}/mutants.out/outcomes.json" "${CRATE_DIR}" 0 1 2>&1`, keeping `|| cls=$?`. Update the step comment: survivors are red (max_missed 0), caught < 1 is red, timeouts green beside a catch (ADR-0042).
- [ ] All other `RustMutantsJobTests` stay unchanged and green (status file format does not change).

**Interfaces:** None consumed or produced.

### Task 3: Classifier cases for the sweep's arguments

```yaml-task
id: 3
description: mutation_classify.bats pins the classifier's existing 0 1 behaviour on the three sweep cases (characterization; N4 forbids changing the classifier, so tdd is replaced by a mutant check)
role: executor
model: haiku
tdd: not-applicable
acceptance:
  - cmd: bats tests/scripts/mutation_classify.bats
    exit_code: 0
  - cmd: shellcheck --severity=warning tests/scripts/mutation_classify.bats
    exit_code: 0
max_retries: 2
files_touched: [tests/scripts/mutation_classify.bats]
depends_on: []
parallel_group: wave-1
requirements: [R3]
```

Add three `@test`s using `_write_outcomes`, each run with args `<exit> <outcomes> prime/prime-rs 0 1`:

- [ ] `{"caught":5,"missed":1,"timeout":0,"unviable":0}`, exit 2, `missed.txt` beside it holding `src/lib.rs:5:5: replace sieve -> Vec<u32> with vec![]`: status 1, output contains `missed=1 exceeds max_missed=0` and that exact `missed.txt` line.
- [ ] caught 5, missed 0, timeout 2, exit 3: status 0, output starts `green: prime/prime-rs`.
- [ ] caught 0, missed 0, timeout 3, exit 3: status 1, output contains `caught=0 below min_caught=1`.
- [ ] Mutant check (report, do not commit): copy `scripts/mutation-classify.sh` to `${TMPDIR}`, delete its `caught -lt min_caught` block, point the third case at the copy by hand, confirm it fails; repeat deleting the `missed -gt max_missed` block for the first case. Report both results.

**Interfaces:** None.

### Task 4: ADR-0042, CLAUDE.md, Backlog

```yaml-task
id: 4
description: ADR-0042 and its index row, the CLAUDE.md sweep rule, and the Backlog changes (docs-only, no behaviour change)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: bash -c 'test "$(wc -c < CLAUDE.md)" -le 30000'
    exit_code: 0
  - cmd: bash -c 'l=$(command grep "^A sweep leg is red when" CLAUDE.md); test -n "$l" && test "$(printf "%s\n" "$l" | wc -c)" -le 400'
    exit_code: 0
  - cmd: bash -c '! command grep -qE "Rust mutation sweep drift the per-PR gate cannot see|Per-PR Rust gate passes an all-timeout run" docs/superpowers/README.md'
    exit_code: 0
  - cmd: command grep -q '0042-' docs/adr/README.md
    exit_code: 0
  - cmd: command grep -qE '1\.99\.1' docs/superpowers/README.md
    exit_code: 0
max_retries: 2
files_touched: [docs/adr/0042-rust-sweep-holds-zero-missed.md, docs/adr/README.md, CLAUDE.md, docs/superpowers/README.md]
depends_on: [1, 2, 3]
requirements: [R7, R8, R9]
```

The orchestrator puts V1's 16-row result table (mutant, result, host, bound) in the dispatch prompt.

- [ ] ADR-0042 (Date, Status Accepted, Context, Decision, Consequences, Related: ADR-0024, ADR-0040, ADR-0041, slice 6 spec): sweep classifies with `0 1`; a timeout counts as caught in the per-PR gate and the sweep; the 56-row timeout table (slice 5's 40 from its spec's Timeout classification plus V1's 16); fix-to-close procedure; cargo-mutants bump procedure; the three no-commit red triggers from the spec's Consequence section.
- [ ] `docs/adr/README.md`: 0042 row; mark 0024 `Partially superseded by 0042`.
- [ ] `CLAUDE.md`: replace the line starting `A sweep leg is red only when` with one starting `A sweep leg is red when`, stating: red on any missed, caught < 1, missing `outcomes.json` or `mutants.out/exit-code`, baseline failure or runner death; timeouts green beside a catch; classifier `0 1` (ADR-0042); keep the trailing `→` pointer. At most 400 bytes.
- [ ] `docs/superpowers/README.md`: delete the two Backlog rows; add `| Rust survivor drift across rustc releases | On the first full sweep after a stable rustc newer than 1.99.1, diff each crate's missed.txt against slice 6's V2 runs to measure whether rustc releases move survivors. See [spec](specs/2026-11-05-worldclass-slice6-rust-sweep-ratchet-design.md). |`.

## Orchestrator steps

- [ ] Create worktree `.worktrees/slice6-sweep-ratchet` on branch `ci/slice6-rust-sweep-ratchet` from `origin/master`.
- [ ] Dispatch wave 1 (Tasks 1-3); at close run root `make test` once, uncontended.
- [ ] V1: download `mutants-output-*` from run 41952665142; take the 16 names from e-rs, prime-rs and pi-rs `timeout.txt` not in slice 5's measured 40; in a `git archive` copy of `0d28038`, escape `\.+*?()|[]{}^$` in each name and run per the spec's V1 command (e-rs: `MALLOC_ARENA_MAX=2` under the `ulimit`, then the `systemd-run --user --scope -p MemoryMax=16G -p MemorySwapMax=0` fallback). A missed result stops for a killing-test task.
- [ ] Dispatch Task 4 with V1's table; then root `make test`.
- [ ] V3 locally.
- [ ] Message the ai-config owner session (`ListAgents`, `SendMessage`) for V4: `math-testing-policy.md` § Mutation green/red and removal of the math cargo-mutants step in `.github/workflows/mutation-review.yml`; land after it answers.
- [ ] Push, `gh pr create --draft`; V2 (two dispatches, diffs); Phase 3; `gh pr ready`.

## Non-goal check

Reviewer run 2026-11-05 (fresh subagent, `nongoal-check.md`): N1 CLEAR, N2 CLEAR, N3 CLEAR, N4 CLEAR; no CONFLICT or UNCLEAR, no plan change. Borderline cases the reviewer checked: Task 4's ADR documents the per-PR timeout rule without touching `mutation-pr-run.sh` or `mutation-pr.yml` (N1); V2's diffs are local and the ADR table classifies timeouts, not a missed baseline (N2); Task 1 changes Python issue-body rendering only, not Python verdict rules (N3); Task 3's mutant check edits an uncommitted copy (N4).
