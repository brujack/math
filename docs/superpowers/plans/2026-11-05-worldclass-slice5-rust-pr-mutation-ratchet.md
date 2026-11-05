# Worldclass Slice 5: Per-PR Rust Mutation Ratchet Implementation Plan

> **Status: DONE** (math#206, 20a2b5b)

spec: docs/superpowers/specs/2026-11-05-worldclass-slice5-rust-pr-mutation-ratchet-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `mutation-pr` fail any PR that leaves a missed mutant on a changed line of any of the 11 Rust crates, and make both mutation workflows classify on cargo-mutants' own exit code.

**Architecture:** A crate-relative diff script feeds a new `mutants-diff` Makefile target (rendered into all 11 crates). A loop script runs the target per selected crate and classifies with a missed limit of 0. `mutation-pr.yml` calls the loop script for the crates the detect script selects, plus an amicable-rs canary when a gate file changes. Both `mutants` targets record the exit status in `mutants.out/exit-code`, so `make`'s exit 2 no longer masks failures.

**Tech Stack:** bash, bats, GNU make, cargo-mutants 27.1.0, Python `unittest` + PyYAML, GitHub Actions.

## Global Constraints

- No committed per-crate missed, timeout or unviable baseline file (N1).
- `mutation-testing.yml` calls `mutation-classify.sh` with no fourth argument; only its exit-code source changes (N2, R11).
- Nothing on the pre-push path runs `cargo mutants` without `--list` (N3).
- No change to the Python mutation path in `mutation-pr.yml` or elsewhere (N4): `py_dirs`/`has_py` output, the GMP apt step, the pip line and the `mutants-baseline` loop stay byte-identical. The shared job's `timeout-minutes: 60` is required by R7 and only lengthens the budget; the Skip step's added `rs_canary == 'false'` clause changes nothing when Python files change.
- Crate Makefiles are rendered: edit `scripts/crate_templates/Makefile`, then `python3 scripts/render_crate_files.py --write`; never edit one crate's copy.
- Every cargo-mutants call keeps `--timeout-multiplier 5 --minimum-test-timeout 30`; never a fixed `--timeout` (math#95).
- Root `CLAUDE.md` stays at or under 30,000 bytes. It is at 29,996 now, so every addition must be paid for by a cut in the same task.
- Shell follows `~/.claude/standards/shell.md`: `#!/usr/bin/env bash`, no `set -e`, sourcing guard before `main`, `[[ ]]`, `${VAR}`, `printf`, functions `|| return 1`.
- bats fixture repos: `unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE` and `export HOME="${BATS_TEST_TMPDIR}"` in `setup()`; commit with `git -c user.name=t -c user.email=t@t`; never `git config`.
- Read `~/.claude/standards/rust.md` before Task 7 and `~/.claude/standards/shell.md` before Tasks 1-5.

## Verification

- Session level: root `make test` passes; `make -C e/e-rs test` and `make -C pi/pi-rs test` pass; `python3 -m unittest tests.test_crate_uniformity tests.test_mutation_workflows tests.test_mutation_pr_diff_lists_mutants -v` passes with the cargo-mutants test running (not skipped) on `claude`.
- Real end-to-end, local, before push: from the slice worktree, `scripts/mutation-pr-run.sh origin/master e/e-rs pi/pi-rs` exits 0 and prints a green verdict for both crates (their R14 test edits sit in `src/main.rs`, so each diff is non-empty), and `scripts/mutation-pr-run.sh origin/master fib/fib-rs` exits 1 with `selected but diff empty`.
- V1 (positive control, CI): before `gh pr ready`, open a throwaway draft PR stacked on the slice branch that adds an untested branch to `fib/fib-rs/src/lib.rs`; `mutation-pr` must go red naming that mutant. Close it and delete its branch.
- V2 (CI): the slice PR's own `mutation-pr` run shows the amicable-rs canary green with caught at least 1 and missed 0 in the step summary; e-rs and pi-rs are selected (R14 lines are in `src/main.rs`).
- Edge cases covered by tests: empty per-crate diff (red), missing `exit-code` (red), stale `mutants.out` (removed before the run), timeout-only line (green in limit mode), all-unviable (red), canary line count 0 or 2 (red).

---

### Task 1: Classifier missed limit and min_caught

```yaml-task
id: 1
description: mutation-classify.sh takes optional max_missed and min_caught arguments; no fourth argument keeps today's behaviour
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/mutation_classify.bats
    exit_code: 0
  - cmd: shellcheck --severity=warning scripts/mutation-classify.sh tests/scripts/mutation_classify.bats
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-classify.sh, tests/scripts/mutation_classify.bats]
depends_on: []
parallel_group: wave-1
requirements: [R4]
```

Signature: `mutation-classify.sh <exit_code> <outcomes.json> <label> [max_missed [min_caught]]`. Keep all existing tests passing unchanged.

- [ ] A 4th or 5th argument not matching `^[0-9]+$` prints `red: <label> - max_missed '<v>' is not a non-negative integer` (or `min_caught`) to stderr, returns 1.
- [ ] Missing `outcomes.json`: with a 5th argument, red `red: <label> - no outcomes.json (min_caught <N> needs a measured run)` whatever the exit code; otherwise today's rule.
- [ ] Nothing-evaluated guard: `caught + missed + timeout == 0` when a 4th argument is given, else `caught + missed == 0`.
- [ ] After the existing exit-code check passes: when `missed > max_missed`, red `red: <label> - missed=<m> exceeds max_missed=<k> (caught=… timeout=… unviable=…)`, then one stderr line `  missed: <line>` per line of `$(dirname outcomes)/missed.txt`, or `  missed.txt not found` when absent.
- [ ] When `caught < min_caught`, red `red: <label> - caught=<c> below min_caught=<n>`.
- [ ] Tests (spec Testing list): limit 0 with missed 0 green; missed 1 red naming the survivor from `missed.txt`; caught 0 missed 0 timeout 1 exit 3 green; all zero with outcomes red; missing outcomes exit 0 green; `abc` limit red; no 4th arg missed 3 exit 2 green and caught 0 timeout 1 red; `0 1` missing outcomes exit 0 red, caught 0 timeout 1 red, caught 1 missed 0 green.

**Interfaces:** Produces the 5-argument CLI used by Task 5.

### Task 2: Crate-relative diff script

```yaml-task
id: 2
description: scripts/mutation-pr-diff.sh writes a diff whose paths are relative to the crate dir
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/mutation_pr_diff.bats
    exit_code: 0
  - cmd: shellcheck --severity=warning scripts/mutation-pr-diff.sh tests/scripts/mutation_pr_diff.bats
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-pr-diff.sh, tests/scripts/mutation_pr_diff.bats]
depends_on: []
parallel_group: wave-1
requirements: [R9]
```

- [ ] Usage `mutation-pr-diff.sh <base-ref> <crate-dir> <out-file>`, run from the repo root. Strip one trailing `/` from `<crate-dir>`.
- [ ] Exit 2 with a usage line on an argument count other than 3, or when `<crate-dir>/Cargo.toml` is not a file.
- [ ] Run `env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git diff --relative="<crate-dir>/" "<base-ref>...HEAD" -- "<crate-dir>" > "<out-file>"`; exit 1 when git fails.
- [ ] Executable bit set (`git add --chmod=+x` if needed; check `git ls-files -s`).
- [ ] bats with a fixture repo holding `a/a-rs/{Cargo.toml,src/lib.rs}` and `b/b-rs/{Cargo.toml,src/lib.rs}`: change to `a/a-rs/src/lib.rs` gives a diff whose `+++` line is exactly `+++ b/src/lib.rs`; with only `b/b-rs` changed the out-file for `a/a-rs` is empty and exit 0; a commit on the base branch after the fork is absent (three-dot); 2 and 4 arguments exit 2; a dir without `Cargo.toml` exits 2; an unknown base ref exits 1.

**Interfaces:** Produces `scripts/mutation-pr-diff.sh <base-ref> <crate-dir> <out-file>` for Tasks 5 and 6.

### Task 3: mutants-diff target and exit-code file

```yaml-task
id: 3
description: Template Makefile gains mutants-diff and both mutants targets write mutants.out/exit-code; rendered to 11 crates
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/makefile.bats
    exit_code: 0
  - cmd: python3 -m unittest tests.test_crate_uniformity
    exit_code: 0
  - cmd: python3 scripts/render_crate_files.py --check
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/Makefile, tests/scripts/makefile.bats, pi/pi-rs/Makefile, prime/prime-rs/Makefile, fib/fib-rs/Makefile, sq/sq-rs/Makefile, twin-primes/twin-primes-rs/Makefile, e/e-rs/Makefile, factorial/factorial-rs/Makefile, perfect-numbers/perfect-numbers-rs/Makefile, collatz/collatz-rs/Makefile, goldbach/goldbach-rs/Makefile, amicable/amicable-rs/Makefile]
depends_on: []
parallel_group: wave-1
requirements: [R1, R2]
```

- [ ] `.PHONY` gains `mutants-diff`. Both recipes run under one `bash -c`: (`mutants-diff` only) `d="$(DIFF)"`, and if `d` is empty or not a readable regular file, print `usage: make mutants-diff DIFF=<readable diff file> (DIFF unset or unreadable)` to stderr and `exit 2` before anything else; `rm -rf mutants.out`; the existing cap block unchanged; then `cargo mutants [--in-diff "$${d}"] --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle; rc=$$?; mkdir -p mutants.out && printf "%s\n" "$${rc}" > mutants.out/exit-code; exit "$${rc}"`. No `exec`.
- [ ] Render with `--write`; all 11 Makefiles change identically.
- [ ] Extend the fixed-`--timeout` test: each of the 11 Makefiles has `^mutants-diff:`, `mutants-diff` in `.PHONY`, `--in-diff`, and `ulimit -v 8388608` inside the `mutants-diff` recipe.
- [ ] Behavioural bats on a copy of `fib/fib-rs/Makefile` with a stub `cargo` on PATH logging `$*` and `$(ulimit -v)` and exiting `STUB_CARGO_RC`: `mutants` and `mutants-diff DIFF=<file>` with rc 4 leave `mutants.out/exit-code` = `4` and make exits non-zero; rc 0 leaves `0` and make exits 0; argv carries `--in-diff <file> --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle`; cargo runs under `ulimit=8388608`; a pre-seeded `mutants.out/outcomes.json` is gone after a run whose stub writes none; `DIFF` unset and `DIFF=/nonexistent` exit non-zero with output naming `DIFF` and no cargo call. Use `env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS make -C`.

**Interfaces:** Produces `make -C <crate> mutants-diff DIFF=<abs path>` writing `<crate>/mutants.out/exit-code`, for Tasks 5 and 8.

### Task 4: Rust crate and canary detection

```yaml-task
id: 4
description: mutation-pr-detect.sh also prints rs_dirs, has_rs and rs_canary
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/mutation_pr_detect.bats
    exit_code: 0
  - cmd: shellcheck --severity=warning scripts/mutation-pr-detect.sh tests/mocks/git tests/scripts/mutation_pr_detect.bats
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-pr-detect.sh, tests/mocks/git, tests/scripts/mutation_pr_detect.bats]
depends_on: []
parallel_group: wave-1
requirements: [R3, R12]
```

- [ ] `tests/mocks/git`: add an `ls-files` branch printing `${MOCK_GIT_LS_FILES:-}`, placed before the `diff` branch.
- [ ] `main` also runs `env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git ls-files '*/*-rs/Cargo.toml'` (exit 1 on failure) and passes the crate dirs (dirname of each) to `detect`.
- [ ] A crate dir `c` is selected when a changed path matches `c/src/*.rs` at any depth. `rs_dirs=` is sorted, unique, space-joined; `has_rs=true` only when it is non-empty.
- [ ] `rs_canary=true` when any changed path equals one of: `.github/workflows/mutation-pr.yml`, `scripts/mutation-pr-detect.sh`, `scripts/mutation-pr-diff.sh`, `scripts/mutation-pr-run.sh`, `scripts/mutation-classify.sh`, `scripts/crate_templates/Makefile`, `amicable/amicable-rs/src/lib.rs`; else `false`.
- [ ] The three Rust lines print after the Python lines in both the select-all and per-dir branches; Python output unchanged.
- [ ] bats (set `MOCK_GIT_LS_FILES` to two or three crate `Cargo.toml` paths): `src/lib.rs` selects; `src/a/b.rs` selects; `Cargo.toml`, `.cargo/mutants.toml`, `tests/cli.rs`, `src/notes.txt` select nothing; two crates sort; no Rust change gives `has_rs=false` and `rs_dirs=`; across every case `has_rs=true` never pairs with empty `rs_dirs`; a loop over the seven trigger paths each gives `rs_canary=true`; `README.md` gives `rs_canary=false`; existing Python tests still pass; ls-files failure exits non-zero.

**Interfaces:** Produces GITHUB_OUTPUT lines `rs_dirs=`, `has_rs=`, `rs_canary=` for Task 8.

### Task 5: Loop script

```yaml-task
id: 5
description: scripts/mutation-pr-run.sh runs mutants-diff per crate and owns every red rule
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/mutation_pr_run.bats tests/scripts/mutation_classify.bats tests/scripts/mutation_pr_diff.bats
    exit_code: 0
  - cmd: shellcheck --severity=warning scripts/mutation-pr-run.sh tests/scripts/mutation_pr_run.bats
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation-pr-run.sh, tests/scripts/mutation_pr_run.bats]
depends_on: [1, 2]
parallel_group: wave-2
requirements: [R5]
```

- [ ] Usage `mutation-pr-run.sh <base-ref> [--min-caught N] <crate-dir>...`, run from the repo root. Exit 2 with usage on no base ref, no crate dirs, or a non-integer `N`.
- [ ] Locate siblings via `$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)`. Make a temp dir with `mktemp -d || exit 1` and an `EXIT` trap removing it.
- [ ] Per crate: diff to `<tmp>/<n>.diff` via `mutation-pr-diff.sh`; its failure is red `red: <dir> - diff failed`; an empty file is red `red: <dir> - selected but diff empty`. Else `make -C "<dir>" mutants-diff DIFF="<abs diff>" || true`; no `<dir>/mutants.out/exit-code` is red `red: <dir> - no mutants.out/exit-code`; a non-integer value is red. Else run `mutation-classify.sh <code> <dir>/mutants.out/outcomes.json <dir> 0 [N] 2>&1`.
- [ ] Every verdict goes to stdout. Continue past a red crate; exit 1 if any red, else 0.
- [ ] bats: fixture repo with `a/a-rs` and `b/b-rs`; a stub `make` first on PATH that logs `-C <dir>` and `DIFF=<path>`, copies the diff's `+++` line to the log, and writes `<dir>/mutants.out/{exit-code,outcomes.json,missed.txt}` from a per-crate config the test writes. Cases from the spec Testing list: empty diff red; missing `exit-code` red; red first crate still runs the second, exit 1; two green exit 0; `--min-caught 1` with caught 0 red; no args, base only, and `--min-caught x` exit 2; stub runs exactly once per crate; `DIFF` is absolute and its `+++` line starts `+++ b/src/`.

**Interfaces:** Produces `scripts/mutation-pr-run.sh` for Task 8.

### Task 6: In-diff mutant listing test

```yaml-task
id: 6
description: A Python test proves the crate-relative diff makes cargo-mutants list sieve mutants
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_pr_diff_lists_mutants -v
    exit_code: 0
  - cmd: ruff check tests/test_mutation_pr_diff_lists_mutants.py
    exit_code: 0
  - cmd: ruff format --check tests/test_mutation_pr_diff_lists_mutants.py
    exit_code: 0
  - cmd: pyright tests/test_mutation_pr_diff_lists_mutants.py
    exit_code: 0
max_retries: 3
files_touched: [tests/test_mutation_pr_diff_lists_mutants.py]
depends_on: [2]
parallel_group: wave-2
requirements: [R10]
```

- [ ] Skip with a printed reason when `shutil.which("cargo")` or `shutil.which("cargo-mutants")` is None and `os.environ.get("CI") != "true"`; fail with a message under `CI=true`.
- [ ] In a `TemporaryDirectory`: `git archive HEAD factorial/factorial-rs | tar -x` (GIT_* stripped from env), `git init`, commit, append one space to the single line `    while p * p <= n {` of `factorial/factorial-rs/src/lib.rs` (assert exactly one match first), commit, run `scripts/mutation-pr-diff.sh HEAD~1 factorial/factorial-rs <tmp>/d.diff` with cwd at the temp root.
- [ ] Assert the diff's `+++` line is `+++ b/src/lib.rs`; then `cargo mutants --list --in-diff <tmp>/d.diff` in the crate copy (timeout 600) exits 0 and some output line contains `sieve`.
- [ ] Negative control in the same file: a root-relative diff of the same change (`git diff HEAD~1 -- factorial/factorial-rs`) makes `cargo mutants --list --in-diff` list no `sieve` line. This proves the positive test discriminates.

### Task 7: Shrink the 64-thread write tests

```yaml-task
id: 7
description: e-rs and pi-rs default-chunk tests use a 4-thread pool and a 3-byte input (test-only change, so tdd is not-applicable; a cargo-mutants run proves the tests still kill)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: make -C e/e-rs test
    exit_code: 0
  - cmd: make -C pi/pi-rs test
    exit_code: 0
max_retries: 3
files_touched: [e/e-rs/src/main.rs, pi/pi-rs/src/main.rs, e/e-rs/CLAUDE.md, pi/pi-rs/CLAUDE.md]
depends_on: []
parallel_group: wave-1
requirements: [R14]
```

- [ ] `test_write_e_file_default_chunk_when_threads_exceed_bytes`: `num_threads(4)`, input `"2.7"` with digits 1, `assert!("2.7".len() < 4)`, expected `expected_e_file("2.7", 1)`; update the comment (4 threads, 3 bytes, `len / threads == 0`).
- [ ] pi twin: same with `"3.1"`, digits 1, expected string built inline as today.
- [ ] Before and after the edit, run in each crate `cargo mutants --file src/main.rs --re 'write_(e|pi)_file' --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle` under `ulimit -v 8388608`; both runs must report missed 0. Report the caught counts.
- [ ] Crate `CLAUDE.md` tables: "default chunk with a 64-thread pool" becomes "default chunk with a 4-thread pool and 3-byte input".

### Task 8: Workflows

```yaml-task
id: 8
description: mutation-pr.yml runs the loop script and canary for Rust; mutation-testing.yml reads mutants.out/exit-code
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_workflows tests.test_gmp_cache_workflow tests.test_rust_workflows_no_system_gmp tests.test_workflow_continue_on_error tests.test_tool_pins
    exit_code: 0
  - cmd: make lint-workflows
    exit_code: 0
max_retries: 3
files_touched: [.github/workflows/mutation-pr.yml, .github/workflows/mutation-testing.yml, tests/test_mutation_workflows.py]
depends_on: [3, 4, 5]
requirements: [R5, R6, R7, R11, R13]
```

`mutation-pr.yml`:

- [ ] Detect step runs only `scripts/mutation-pr-detect.sh "origin/${GITHUB_BASE_REF}" >> "${GITHUB_OUTPUT}"`; delete the inline grep, `Get PR diff (for Rust)` and `Run cargo mutants (factorial-rs)`.
- [ ] Add `GMP cache key` (id `gmpkey`) and `Restore GMP/MPFR build cache` copied from `scripts/crate_templates/ci.yml`, each with `if: steps.detect.outputs.has_rs == 'true' || steps.detect.outputs.rs_canary == 'true'` (restore also needs `steps.gmpkey.outputs.enabled == 'true'`).
- [ ] Step `Run Rust mutants on changed crates`, `if: has_rs == 'true'`, env `RS_DIRS`, `GITHUB_BASE_REF`: `rc=0; scripts/mutation-pr-run.sh "origin/${GITHUB_BASE_REF}" ${RS_DIRS} > "${RUNNER_TEMP}/rs.log" 2>&1 || rc=$?; cat "${RUNNER_TEMP}/rs.log" | tee -a "${GITHUB_STEP_SUMMARY}"; exit "${rc}"`.
- [ ] Step `Gate canary (amicable-rs)`, `if: rs_canary == 'true'`, after it: `f=amicable/amicable-rs/src/lib.rs`; red unless `grep -c 'let mut m = 2 \* d;' "$f"` is `1`; `sed -i 's/let mut m = 2 \* d;$/& /' "$f"`; `git -c user.name=ci -c user.email=ci@localhost commit -q -m canary -- "$f"`; then the run script with `HEAD~1 --min-caught 1 amicable/amicable-rs`, same log/tee/status shape.
- [ ] Update the Skip step's condition to include `rs_canary == 'false'`; `timeout-minutes: 60`; rewrite the comment above it.

`mutation-testing.yml` "Run mutants": keep `make -C "${CRATE_DIR}" mutants || true`. If `${CRATE_DIR}/mutants.out/exit-code` is absent, write `red: ${CRATE_DIR} - no mutants.out/exit-code` to `status/${SLUG}` and the summary and exit 1. Otherwise classify on the file's value, still with no 4th argument, keeping the existing capture-before-pipe shape.

Tests (execute run blocks as `run_crate_job` does): canary step in a fixture repo with a stub `scripts/mutation-pr-run.sh` logging args and `git diff --name-only HEAD~1` — commits only `$f`, args `HEAD~1 --min-caught 1 amicable/amicable-rs`; 0 or 2 matching lines exit non-zero with no stub call; stub exit 1 fails the step. Rust step passes `origin/${GITHUB_BASE_REF}` and its exit status. No `--timeout ` followed by a digit and no `factorial-rs` step remain. Sweep step: make stub writes `exit-code` 4 while exiting 2, classifier stub receives `rc=4`; missing file is red. Update `test_detect_calls_script` and `test_matrix_job_settings`-style timeout pins as needed.

### Task 9: Docs, ADR, Backlog

```yaml-task
id: 9
description: CLAUDE.md, ADR-0041 and Backlog describe the per-PR gate (docs-only, no behaviour change)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: bash -c 'test "$(wc -c < CLAUDE.md)" -le 30000'
    exit_code: 0
  - cmd: bash -c '! command grep -q "not main glue" CLAUDE.md'
    exit_code: 0
  - cmd: command grep -q 'mutation-pr-run.sh' CLAUDE.md
    exit_code: 0
  - cmd: command grep -q 'killing test' CLAUDE.md
    exit_code: 0
  - cmd: bash -c '! command grep -q "Add a committed per-crate missed baseline" docs/superpowers/README.md'
    exit_code: 0
max_retries: 2
files_touched: [CLAUDE.md, docs/adr/0041-per-pr-rust-mutation-ratchet.md, docs/adr/README.md, docs/superpowers/README.md]
depends_on: [8]
requirements: [R8]
```

- [ ] `CLAUDE.md` Mutation testing (Rust): one rule naming `mutation-pr.yml`'s per-PR gate (`scripts/mutation-pr-run.sh`, missed limit 0 on changed lines of every selected crate, amicable-rs canary on gate-file changes) and the local repro `scripts/mutation-pr-diff.sh origin/master <crate> /tmp/d.diff && make -C <crate> mutants-diff DIFF=/tmp/d.diff`; the green/red rule says verdicts read `mutants.out/exit-code`; replace "investigate surviving mutants in logic code, not main glue" with "every missed mutant on a changed line gets a killing test, glue included; `exclude_re` only for true equivalents". Pay for the bytes by moving detail behind existing `→` pointers; final size ≤ 30,000.
- [ ] ADR-0041 (Context/Decision/Consequences/Related; relates ADR-0040, spec) and its `docs/adr/README.md` row.
- [ ] Backlog row "Rust mutation leg has no missed-count ratchet" rewritten to cover only drift the per-PR gate cannot see (deleted tests, rustc or cargo-mutants updates), pointing at the slice 5 spec.

## Orchestrator steps

- [ ] Create worktree `.worktrees/slice5-rust-ratchet` on branch `ci/slice5-rust-pr-mutation-ratchet` from `origin/master`.
- [ ] After wave 1 closes: root `make test` once, uncontended.
- [ ] After Task 9: root `make test`, `make -C e/e-rs test`, `make -C pi/pi-rs test`, then the local end-to-end from Verification.
- [ ] Message the ai-config owner session (`ListAgents`, `SendMessage`) before editing `ai-config/docs/knowledge/math-ci.md` (mutation-pr row) and `math-testing-policy.md` (green/red, notification) to match R8; land those after it answers.
- [ ] Push, `gh pr create --draft`; run V1 on a stacked draft PR; check V2 in the slice PR's summary; Phase 3; `gh pr ready`.

## Non-goal check

Reviewer run 2026-11-05 (fresh Opus subagent, `nongoal-check.md`): N1 CLEAR, N3 CLEAR, N2 UNCLEAR, N4 UNCLEAR, no CONFLICT.

- **N2 UNCLEAR.** Quote: Task 8 makes the monthly sweep exit 1 "if `${CRATE_DIR}/mutants.out/exit-code` is absent". Resolution: no plan change. R11 itself says "red when the file is missing", and N2 names R11 as the permitted exit-code-source change, so failing closed on a missing source is part of R11. The classifier's verdict rules and its arguments are unchanged.
- **N4 UNCLEAR.** Quote: Task 8 sets "`timeout-minutes: 60`" and updates "the Skip step's condition". Resolution: the Python baseline does run in the same job. The timeout comes from R7 and only lengthens the budget. The Skip step only prints a message and is not part of the Python mutation path. Global Constraints line before: "No change to the Python mutation path ... stay byte-identical." After: same text plus "The shared job's `timeout-minutes: 60` is required by R7 and only lengthens the budget; the Skip step's added `rs_canary == 'false'` clause changes nothing when Python files change."
