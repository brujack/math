# Worldclass slice 5: per-PR Rust mutation ratchet

## Problem

Slice 4 (math#203, math#204) brought all 11 Rust crates to 0 missed mutants. Full sweep run
41952665142 at `0d28038` recorded missed 0 in every crate. Nothing holds that line.

`scripts/mutation-classify.sh` scores survivors (cargo-mutants exit 2) green, so the monthly
`mutation-testing.yml` sweep (ADR-0040) never goes red for a new survivor. A crate can drift
from 0 missed back to 30 with no red leg and no issue. This is the Backlog row "Rust mutation
leg has no missed-count ratchet".

One crate appears to have a gate, and it has never tested anything. `mutation-pr.yml` writes
`/tmp/pr.diff` with `git diff origin/<base>...HEAD` at the repo root, so its paths read
`factorial/factorial-rs/src/lib.rs`, then runs
`cargo mutants --in-diff /tmp/pr.diff --timeout 30 --no-shuffle` inside
`factorial/factorial-rs`, where cargo-mutants matches diff paths against `src/lib.rs`. They
never match. Measured 2026-11-05 on a `git archive` copy of factorial-rs with one line of
`sieve` changed, cargo-mutants 27.1.0:

| Diff | Where cargo-mutants runs | Result |
| --- | --- | --- |
| repo-root (`git diff`) | inside the crate | `INFO No mutants to filter`, exit 0 |
| crate-relative (`git diff --relative=factorial/factorial-rs/`) | inside the crate | sieve mutants listed (`replace < with == in sieve`, ...) |
| repo-root, `--dir factorial/factorial-rs` | repo root | `INFO No mutants to filter` |

The workflow's history agrees: runs 40364504789 (math#180, 15 changed lines of
`factorial-rs/src/main.rs`) and 41224291570 (math#187) both logged only
`No mutants to filter` and passed. So no crate has a working per-PR gate, the factorial
step's fixed `--timeout 30` is the form root `CLAUDE.md` forbids (#95), and the only
crate-specific step breaks the operator rule that all crates are treated identically.

The 2026-08-01 spec recorded `INFO No mutants to filter`, exit 0, no `mutants.out/` as "a
`--in-diff` run whose diff contains no mutable lines". The output is identical when the diff's
paths do not match, so that measurement does not distinguish the two. A crate-relative probe
does show the real no-mutable-lines case behaves the same way: a diff adding only a `#[test]`
function to `fib/fib-rs/src/main.rs`'s `mod tests` prints `INFO No mutants to filter`, exits
0 and writes no `mutants.out/` (measured 2026-11-05, same pin).

### Prior decisions this design answers

The 2026-08-01 per-project mutation spec
(`docs/superpowers/specs/2026-08-01-mutation-testing-per-project-design.md`) rejected two
things this slice could resemble:

- **A committed per-crate baseline.** It was rejected because a hand-tuned per-crate number
  (there, expected unviable) drifts with source edits and rustc updates, loosens only
  upward, and its false reds blank a month's `mutation_review` report, since
  `fetch_latest_artifact` reads only successful runs. This design commits no number. The rule
  is "0 missed among mutants of the changed lines", which needs no stored state.
- **Per-PR legs.** They were dropped because they were advisory (no verdict could differ),
  cost 11 `cargo install` runs plus 8 cosmic-ray runs per PR, and the spec deferred "whether
  per-PR mutation coverage is worth having as a real blocking gate" to Phase B, after a first
  completed sweep. This design is blocking, runs only crates the PR changes with one
  `cargo install`, and the precondition is met (ADR-0040; run 41952665142).

The monthly sweep stays exactly as it is, so the report-blanking objection does not arise.

## Design

### Where the ratchet fires

At PR time, on the mutants of lines the PR changes, for every crate whose `src/` the PR
touches. A missed mutant fails `mutation-pr`, which `scripts/ci-gate.sh` already treats as a
required check, so auto-merge holds the PR. Timeouts stay green: the ratchet is on missed
only. Timeout counts are noisy on shared runners (prime-rs and e-rs each record 12) and stay
informational in the monthly sweep.

### What it does not hold

The gate sees only mutants of lines a PR changes. Survivors can still return without one:
a PR that deletes tests (deleted test lines yield no mutants, and `tests/` selects no crate),
a rustc update, or a cargo-mutants bump that adds mutation operators. The monthly sweep still
scores those green (N2). That half stays open as a narrowed Backlog row (R8).

### Components

1. **`mutants-diff` Makefile target.** Added to `scripts/crate_templates/Makefile` and
   rendered into all 11 crates by `scripts/render_crate_files.py --write`. It keeps the
   `mutants` recipe's memory cap (`ulimit -v 8388608`, `MUTANTS_UNCAPPED=1` escape, fail
   closed where the cap cannot be set) and runs
   `cargo mutants --in-diff "$(DIFF)" --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle`.
   It exits 2 with a usage message naming `DIFF` when `DIFF` is unset or not a readable file,
   before invoking cargo-mutants. The target joins the `.PHONY` list.
2. **Per-crate diff.** `scripts/mutation-pr-diff.sh <base-ref> <crate-dir> <out-file>`
   writes `git diff --relative=<crate-dir>/ <base-ref>...HEAD -- <crate-dir>` to `<out-file>`,
   so every path reads `src/...` as cargo-mutants expects when it runs inside the crate. It
   exits 2 on a wrong argument count or a `<crate-dir>` with no `Cargo.toml`, and 1 when
   `git diff` fails. A local repro is
   `scripts/mutation-pr-diff.sh origin/master <crate> /tmp/d.diff && make -C <crate> mutants-diff DIFF=/tmp/d.diff`.
3. **Crate detection.** `scripts/mutation-pr-detect.sh` also prints `rs_dirs=<sorted crate
dirs>` and `has_rs=true|false`. A crate dir `<p>/<p>-rs` is selected when the PR changes a
   path matching `<p>/<p>-rs/src/*.rs` (any depth under `src/`). The crate list is derived
   from `git ls-files '*/*-rs/Cargo.toml'`, not a hardcoded list. The existing Python outputs
   are unchanged.
4. **Classifier limit.** `scripts/mutation-classify.sh` accepts an optional fourth argument,
   `max_missed` (a non-negative integer). With no fourth argument, behaviour is byte-for-byte
   today's. With it, a run that would be green is red when `missed > max_missed`, and the red
   line names each survivor from `mutants.out/missed.txt` beside `outcomes.json`. A
   non-integer `max_missed` is red with a message naming the argument. No `outcomes.json` with
   exit 0 stays green in both modes; with the crate-relative diff of component 2 that is the
   measured no-mutable-lines case (Problem). The "nothing was evaluated" guard differs by mode:
   without a limit it stays `caught + missed == 0`; with a limit it is
   `caught + missed + timeout == 0`, because some lines yield only timeout mutants that the
   tests do catch. In run 41952665142 every mutant of `collatz_next` (`collatz-rs`
   `src/lib.rs:9`) and the `read_line_from` replacements in the prompt retry loops timed out,
   so a PR touching only such a line would otherwise go red with nothing to fix.
5. **Workflow.** In `mutation-pr.yml`, the inline factorial-only grep and the
   `Run cargo mutants (factorial-rs)` step are replaced:
   - `has_rs` and `rs_dirs` come from `mutation-pr-detect.sh`.
   - A GMP key step and a read-only `actions/cache/restore` step, the same shape as
     `scripts/crate_templates/ci.yml` (`scripts/gmp-cache-key.sh`, non-strict, so a bad key
     degrades to a cold build), run when `has_rs` is true.
   - One step loops over `rs_dirs`: `scripts/mutation-pr-diff.sh origin/<base> <dir> <tmp>`,
     `make -C <dir> mutants-diff DIFF=<tmp>`, then
     `mutation-classify.sh <rc> <dir>/mutants.out/outcomes.json <dir> 0`. It runs every crate
     even after a red one, prints each verdict to `$GITHUB_STEP_SUMMARY`, and exits 1 at the
     end when any crate was red.
   - `timeout-minutes` rises from 30 to 60, since a PR touching several crates now runs
     several in-diff passes in one job.

### Error handling

- A crate whose in-diff mutants are all unviable gives `caught + missed + timeout == 0` with an
  `outcomes.json`, which is red. That fails closed. It needs a diff whose every mutation fails to compile;
  how often that occurs is unmeasured. The red line says "nothing was
  evaluated", so the cause is visible.
- `make` failing for a reason other than survivors (baseline tests fail, memory cap kill) is
  red through the classifier's existing exit-code rule.
- A dependency-only PR (Renovate `Cargo.lock`) changes no `src/` file, selects no crate, and
  skips the Rust step.

## Testing

The suite must be able to fail when the gate measures nothing, since every per-crate verdict
below is green on an empty run. Two cases pin a non-empty measurement: the diff-path test and
the mutant-listing test.

- `tests/scripts/mutation_pr_detect.bats`: a `src/` change selects its crate; a nested
  `src/a/b.rs` change selects it; a crate `Cargo.toml`, `.cargo/mutants.toml` or `tests/`
  change selects nothing; two crates sort; no Rust change prints `has_rs=false` and an empty
  `rs_dirs`; `has_rs=true` never appears with an empty `rs_dirs`; Python outputs unchanged.
- `tests/scripts/mutation_pr_diff.bats` (fixture git repo): a change to
  `<crate>/src/lib.rs` yields a diff whose `+++` line is exactly `+++ b/src/lib.rs`; a change
  in another crate yields an empty diff; bad arguments exit 2.
- `tests/test_mutation_pr_diff_lists_mutants.py`: on a `git archive` copy of factorial-rs in
  a temp git repo, change one line of `sieve`, build the diff with
  `scripts/mutation-pr-diff.sh`, run `cargo mutants --list --in-diff` inside the copy, and
  require at least one listed mutant naming `sieve`. It prints a skip line when
  `cargo-mutants` is absent outside CI and fails when absent under `CI=true` (`scripts.yml`
  already installs `cargo-mutants@27.1.0`).
- `tests/scripts/mutation_classify.bats`: with `max_missed 0`, missed 0 is green, missed 1 is
  red and names the survivor from `missed.txt`, caught 0 missed 0 timeout 1 is green, caught 0
  missed 0 timeout 0 with an `outcomes.json` is red, missing `outcomes.json` with exit 0 is
  green, a non-integer limit is red; with no fourth argument missed 3 is green and caught 0
  missed 0 timeout 1 is red, as today.
- `tests/scripts/makefile.bats`: all 11 crates' `mutants-diff` carry the cap, the multiplier
  pair, `--in-diff`, no fixed `--timeout`, and exit 2 naming `DIFF` when it is unset.
- `tests/test_mutation_workflows.py`: the Rust step calls `mutants-diff`, passes `0` as the
  classifier limit, contains no `--timeout ` flag, and the factorial-only step is gone.
- `tests/test_crate_uniformity.py` keeps the 11 Makefiles identical to the template.

## Requirements

- **R1.** `scripts/crate_templates/Makefile` has a `mutants-diff` target, rendered into all 11 crate `Makefile`s and listed in `.PHONY`, that keeps the `mutants` recipe's `ulimit -v 8388608` cap and `MUTANTS_UNCAPPED` escape and runs `cargo mutants --in-diff "$(DIFF)" --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle`.
- **R2.** `make mutants-diff` exits 2 with a message naming `DIFF` when `DIFF` is unset or not a readable file, without invoking cargo-mutants.
- **R3.** `scripts/mutation-pr-detect.sh` prints `rs_dirs=` (sorted crate dirs, derived from `git ls-files '*/*-rs/Cargo.toml'`) and `has_rs=`, selecting a crate only when a changed path is a `.rs` file under that crate's `src/`.
- **R4.** `scripts/mutation-classify.sh` with no fourth argument behaves as before; with a fourth argument `max_missed` it reports red when `missed > max_missed`, naming each survivor from `mutants.out/missed.txt`, reports red on a non-integer `max_missed`, and in that mode treats `caught + missed + timeout == 0` as nothing evaluated.
- **R5.** `mutation-pr.yml` runs `scripts/mutation-pr-diff.sh` then `make -C <dir> mutants-diff` on that per-crate diff for every dir in `rs_dirs`, classifies each with limit `0`, continues past a red crate, and fails the step when any crate is red.
- **R6.** `mutation-pr.yml` no longer contains the factorial-only detection grep, the `Run cargo mutants (factorial-rs)` step, or any fixed `--timeout` flag for cargo-mutants.
- **R7.** `mutation-pr.yml` restores the GMP/MPFR build cache read-only via `scripts/gmp-cache-key.sh` when `has_rs` is true, and its job `timeout-minutes` is 60.
- **R8.** Root `CLAUDE.md` and the math knowledge entries that describe `mutation-pr.yml` describe the per-PR gate and the local repro in the same change, and the Backlog row "Rust mutation leg has no missed-count ratchet" is rewritten to cover only drift the per-PR gate cannot see (deleted tests, rustc or cargo-mutants updates).
- **R9.** `scripts/mutation-pr-diff.sh <base-ref> <crate-dir> <out-file>` writes `git diff --relative=<crate-dir>/ <base-ref>...HEAD -- <crate-dir>`, so every path in it starts `src/`, and exits 2 on a wrong argument count or a crate dir without `Cargo.toml`.
- **R10.** A test builds a diff with `scripts/mutation-pr-diff.sh` from a one-line `sieve` change in a copy of factorial-rs and requires `cargo mutants --list --in-diff` to list at least one `sieve` mutant; it skips when cargo-mutants is absent outside CI and fails when absent under `CI=true`.
- **V1.** Positive control, before the slice PR is marked ready: a throwaway draft PR built on the slice branch, adding an untested branch to one crate's `src/`, shows `mutation-pr` red naming that mutant; the PR is then closed and its branch deleted.
- **V2.** Negative control: this slice's own PR, which changes no crate `src/` file, shows `mutation-pr` green with the Rust step skipped (its `mutation-pr.yml` change still selects every Python dir, as today).
- **N1.** No committed per-crate missed, timeout or unviable baseline file.
- **N2.** The monthly `mutation-testing.yml` sweep's classification does not change: it calls `mutation-classify.sh` without a fourth argument.
- **N3.** The local pre-push hook evaluates no mutants: nothing on the push path runs `cargo mutants` without `--list`.
- **N4.** No change to the Python mutation path in `mutation-pr.yml` or elsewhere.

## Multi-Lens Review

Reviewed at commit: `31fb15f` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: The gate as designed sees zero mutants on every PR. The workflow writes a repo-root diff (`factorial/factorial-rs/src/lib.rs`) and cargo-mutants runs inside the crate, matching `src/lib.rs`; a `git archive` probe printed `No mutants to filter` with the root diff and listed sieve mutants with `git diff --relative`. The existing factorial step has done the same since it landed (runs 41224291570, 40364504789). Secondary: the per-PR gate covers only changed lines; deleted tests, a rustc update or a cargo-mutants bump can bring survivors back and the sweep still scores them green, so the Backlog row should narrow rather than close. Verdicts: 4 green and 2 red in the classifier cases, and none fails on an empty run.
Assumption: that a crate-relative diff touching only a `#[test]` function yields `No mutants to filter` and exit 0 rather than an error. Confirmed by the orchestrator 2026-11-05: a test-only hunk in `fib-rs/src/main.rs` printed `INFO No mutants to filter`, exit 0, no `mutants.out/`.
Disposition: Addressed (operator, 2026-11-05): per-crate relative diff (R9), a listing test that needs at least one mutant (R10), V1 before the slice PR is ready; Backlog row narrowed to sweep drift (R8, "What it does not hold").

### Ergonomics

Finding: The `caught + missed == 0` guard reds a PR whose changed lines yield only timeout mutants that the tests catch (`collatz_next`, `read_line_from` retry loops, sieve `+=` swaps in run 41952665142), with no fix but a drifting `exclude_re`. Smaller: no case for `has_rs=true` with an empty `rs_dirs`; the loop is serial; there is no local repro command.
Assumption: that a test-only or excluded-line diff exits 0 with no `mutants.out/`. Test-only half confirmed by the orchestrator (see Goal-Fit); the excluded-line half was not probed.
Disposition: Addressed (operator, 2026-11-05): with a limit the guard is `caught + missed + timeout == 0` (R4); empty-loop test and local repro added; serial loop accepted.

### Risk

Finding: Same load-bearing defect as Goal-Fit, found independently: the root-relative diff never matches inside the crate, `--dir` does not help (orchestrator-confirmed), so the design would copy a dead gate to 11 crates; the "measured no-mutable-lines case" was the path mismatch. Verdicts: 11 of 18 cases expect green and no unit test fails on a vacuous run; only V1 would catch it. Not raised: host-dependent flakes (changed lines only), `exclude_re` drift (caught pre-push), timeouts green and the 60-minute limit.
Assumption: whether `cargo mutants --dir <crate>` from the root resolves root-relative paths. Refuted by the orchestrator 2026-11-05: `No mutants to filter`.
Disposition: Addressed (operator, 2026-11-05): as Goal-Fit.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.

