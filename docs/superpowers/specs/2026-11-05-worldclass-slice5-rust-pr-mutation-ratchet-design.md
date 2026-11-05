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

The monthly sweep's verdict rules stay as they are, so the report-blanking objection does not
arise. Its exit-code source changes (component 1), which can only turn a broken run red.

### Make hides cargo-mutants' exit code

Both workflows pass `make`'s status to the classifier, and GNU make exits 2 whenever a recipe
fails: a recipe ending `exit 4` makes `make` exit 2 (measured 2026-11-05). 2 is in the
classifier's green set, so cargo-mutants' exit 1 (usage), 3 (timeouts), 4 (baseline failed)
and a memory-cap kill all reach it as "survivors found". A run cut short that left a partial
`outcomes.json` with missed 0 would read green with mutants untested. This affects the
monthly sweep today and would affect the new gate.

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

Timeouts are green on the assumption that a timed-out mutant never terminates. A mutant that is
slow but correct would time out on a slow runner and be missed on a faster one, a host-dependent
false red. The 56 sweep timeouts of run 41952665142 are classified below (Timeout
classification) so that the assumption is measured, not assumed.

### Components

1. **`mutants-diff` Makefile target.** Added to `scripts/crate_templates/Makefile` and
   rendered into all 11 crates by `scripts/render_crate_files.py --write`. It keeps the
   `mutants` recipe's memory cap (`ulimit -v 8388608`, `MUTANTS_UNCAPPED=1` escape, fail
   closed where the cap cannot be set) and runs
   `cargo mutants --in-diff "$(DIFF)" --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle`.
   It exits 2 with a usage message naming `DIFF` when `DIFF` is unset or not a readable file,
   before invoking cargo-mutants. The target joins the `.PHONY` list. Both `mutants` and
   `mutants-diff` stop `exec`-ing cargo-mutants: each first removes `mutants.out/` (cargo-mutants
   leaves an existing one untouched when it finds no mutants, so a stale `outcomes.json` would
   otherwise sit beside a fresh `exit-code`), runs it, then writes its exit status to
   `mutants.out/exit-code` (creating `mutants.out/` when cargo-mutants wrote none) and exits
   with that status. Callers classify on the file's value, never on `make`'s status.
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
   A fifth argument, `min_caught` (a non-negative integer, default 0), makes the run red when
   `caught < min_caught`, and red when `outcomes.json` is missing whatever the exit code. The
   canary (component 6) passes `0 1`; the crate loop passes only `0`.
5. **Workflow.** In `mutation-pr.yml`, the inline factorial-only grep and the
   `Run cargo mutants (factorial-rs)` step are replaced:
   - `has_rs` and `rs_dirs` come from `mutation-pr-detect.sh`.
   - A GMP key step and a read-only `actions/cache/restore` step, the same shape as
     `scripts/crate_templates/ci.yml` (`scripts/gmp-cache-key.sh`, non-strict, so a bad key
     degrades to a cold build), run when `has_rs` is true.
   - One step loops over `rs_dirs`: `scripts/mutation-pr-diff.sh origin/<base> <dir> <tmp>`,
     `make -C <dir> mutants-diff DIFF=<tmp>`, then
     `mutation-classify.sh <code> <dir>/mutants.out/outcomes.json <dir> 0`, where `<code>` is
     read from `<dir>/mutants.out/exit-code`. A missing `exit-code` file is red, and so is a
     selected crate whose per-crate diff is empty, since detect has just reported a changed
     `src/*.rs` file in it. It runs every crate
     even after a red one, prints each verdict to `$GITHUB_STEP_SUMMARY`, and exits 1 at the
     end when any crate was red.
   - `timeout-minutes` rises from 30 to 60, since a PR touching several crates now runs
     several in-diff passes in one job. Measured 2026-11-05 for math#203's five crates
     (`cargo mutants --list --in-diff` on each crate-relative diff of `5b1fc1e...821acb1`):
     33, 35, 48, 25 and 8 in-diff mutants against full sweeps of 166, 137, 156, 121 and 43.
     Scaling each crate's sweep job time (13.9, 13.9, 9.9, 5.2, 5.1 min) by that ratio gives
     about 11 min, plus one baseline build and test per crate (about 1 to 2 min each), about
     20 min in all. A PR touching all 11 crates' `src/` could exceed 60; that times out and
     fails closed.
   - `mutation-testing.yml`'s "Run mutants" step reads its code from
     `<crate>/mutants.out/exit-code` the same way, red when the file is missing, and still
     calls the classifier without a limit.
6. **Gate canary.** A change to a file the gate is made of selects no crate by itself, so the
   PR that breaks the gate would merge green. When a PR changes `mutation-pr.yml`,
   `scripts/mutation-pr-detect.sh`, `scripts/mutation-pr-diff.sh`,
   `scripts/mutation-pr-canary.sh`, `scripts/mutation-classify.sh` or
   `scripts/crate_templates/Makefile`, detect prints `rs_canary=true`, and the workflow runs
   `scripts/mutation-pr-canary.sh`. The script appends a trailing space to the single line of
   `amicable/amicable-rs/src/lib.rs` matching `let mut m = 2 * d;` (exit 1 when not exactly
   one line matches), installs an EXIT trap that restores the file, writes the crate-relative
   working-tree diff, runs `make -C amicable/amicable-rs mutants-diff` on it with the edit
   still in place, and classifies with `mutation-classify.sh <code> <outcomes> amicable 0 1`,
   exiting with the classifier's status. The edit must stay in place during the run:
   cargo-mutants refuses a diff whose `+` lines do not match the tree (`ERROR Diff content
   doesn't match source file`, exit 5, measured by two round-3 lenses). With the edit in place
   the diff lists 6 mutants, including `replace * with +` and `replace * with /` on that line.
   amicable-rs's full sweep takes 57 s (run 41952665142).

### Error handling

- A crate whose in-diff mutants are all unviable gives `caught + missed + timeout == 0` with an
  `outcomes.json`, which is red. That fails closed. It needs a diff whose every mutation fails to compile;
  how often that occurs is unmeasured. The red line says "nothing was
  evaluated", so the cause is visible.
- `make` failing for a reason other than survivors (baseline tests fail, memory cap kill) is
  red through the classifier's existing exit-code rule.
- A dependency-only PR (Renovate `Cargo.lock`) changes no `src/` file, selects no crate, and
  skips the Rust step.

### Timeout classification

Measured 2026-11-05 on `claude`: each of the 56 timeout mutants of run 41952665142 was re-run
from a `git archive` copy at `7f9cd29`, filtered by exact name, with `--timeout 180` and the
8 GiB cap. 40 were measured and none came back missed:

| Crate | Timeouts | Re-run result |
| --- | --- | --- |
| collatz-rs | 6 | 6 caught |
| sq-rs | 4 | 4 caught |
| fib-rs | 4 | 3 caught, 1 timeout |
| factorial-rs | 4 | 2 caught, 2 timeout |
| goldbach-rs | 3 | 1 caught, 2 timeout |
| perfect-numbers-rs | 2 | 1 caught, 1 timeout |
| twin-primes-rs | 4 | 4 timeout |
| amicable-rs | 1 | 1 timeout |
| prime-rs | 12 | 10 measured: 6 caught, 4 timeout; run then interrupted |
| pi-rs | 4 | 2 measured: 2 caught; run then interrupted |
| e-rs | 12 | not measured: baseline failed (below) |

Most "caught" results are nextest's own 45 s `slow-timeout` kill reported as a test failure, so
those mutants are loops, caught by a different clock. The population is the sweep's timeout set
on one host; the 16 unmeasured mutants (e-rs 12, prime-rs 2, pi-rs 2) remain unclassified. The
e-rs baseline failed because `test_write_e_file_default_chunk_when_threads_exceed_bytes`
(math#204) could not build its 64-thread pool under the cap on a 48-core host:
`ThreadPoolBuildError { kind: IOError(Os { code: 11, kind: WouldBlock }) }`. The same test passes
alone under the cap with `cargo test` and with nextest, so it is load-dependent; R14 shrinks the
test (and its pi-rs twin, where the failure was not observed) to a 4-thread pool.

## Testing

The suite must be able to fail when the gate measures nothing, since every per-crate verdict
below is green on an empty run. Two cases pin a non-empty measurement: the diff-path test and
the mutant-listing test.

- `tests/scripts/mutation_pr_detect.bats`: a `src/` change selects its crate; a nested
  `src/a/b.rs` change selects it; a crate `Cargo.toml`, `.cargo/mutants.toml` or `tests/`
  change selects nothing; two crates sort; no Rust change prints `has_rs=false` and an empty
  `rs_dirs`; `has_rs=true` never appears with an empty `rs_dirs`; each of the five gate files
  prints `rs_canary=true` and an unrelated file prints `rs_canary=false`; Python outputs
  unchanged.
- `tests/scripts/mutation_pr_canary.bats` (fixture copy of the crate, PATH-stubbed `make`):
  when the stub `make` runs, the source line still carries the trailing space and the diff it
  receives has one `-`/`+` pair on the matching line; after the script exits (green, red, or
  killed by the stub exiting non-zero) the file is byte-identical; zero or two matching lines
  exit 1 before `make` runs.
- `tests/scripts/makefile.bats`: a stub `cargo` exiting 4 leaves `mutants.out/exit-code`
  containing `4` for both `mutants` and `mutants-diff`, and `make` exits non-zero.
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
  missed 0 timeout 1 is red, as today; with `0 1`, a missing `outcomes.json` with exit 0 is
  red, caught 0 timeout 1 is red, and caught 1 missed 0 is green.
- `tests/scripts/makefile.bats`: all 11 crates' `mutants-diff` carry the cap, the multiplier
  pair, `--in-diff`, no fixed `--timeout`, and exit 2 naming `DIFF` when it is unset.
- `tests/test_mutation_workflows.py`: the Rust step calls `scripts/mutation-pr-diff.sh` and
  passes its output file as `DIFF=` to `mutants-diff`, passes `0` as the classifier limit,
  reads `mutants.out/exit-code`, contains no `--timeout ` flag, and the factorial-only step is
  gone; `mutation-testing.yml` reads `mutants.out/exit-code` and passes no limit.
- `tests/test_crate_uniformity.py` keeps the 11 Makefiles identical to the template.

## Requirements

- **R1.** `scripts/crate_templates/Makefile` has a `mutants-diff` target, rendered into all 11 crate `Makefile`s and listed in `.PHONY`, that keeps the `mutants` recipe's `ulimit -v 8388608` cap and `MUTANTS_UNCAPPED` escape and runs `cargo mutants --in-diff "$(DIFF)" --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle`; both `mutants` and `mutants-diff` write cargo-mutants' exit status to `mutants.out/exit-code` and exit with it.
- **R2.** `make mutants-diff` exits 2 with a message naming `DIFF` when `DIFF` is unset or not a readable file, without invoking cargo-mutants.
- **R3.** `scripts/mutation-pr-detect.sh` prints `rs_dirs=` (sorted crate dirs, derived from `git ls-files '*/*-rs/Cargo.toml'`) and `has_rs=`, selecting a crate only when a changed path is a `.rs` file under that crate's `src/`.
- **R4.** `scripts/mutation-classify.sh` with no fourth argument behaves as before; with a fourth argument `max_missed` it reports red when `missed > max_missed`, naming each survivor from `mutants.out/missed.txt`, reports red on a non-integer `max_missed`, and in that mode treats `caught + missed + timeout == 0` as nothing evaluated; an optional fifth argument `min_caught` makes the run red when `caught < min_caught` or when `outcomes.json` is missing.
- **R5.** `mutation-pr.yml` runs `scripts/mutation-pr-diff.sh` then `make -C <dir> mutants-diff` on that per-crate diff for every dir in `rs_dirs`, classifies each with limit `0` using the code from `mutants.out/exit-code`, treats a missing `exit-code` file or an empty per-crate diff as red, continues past a red crate, and fails the step when any crate is red.
- **R6.** `mutation-pr.yml` no longer contains the factorial-only detection grep, the `Run cargo mutants (factorial-rs)` step, or any fixed `--timeout` flag for cargo-mutants.
- **R7.** `mutation-pr.yml` restores the GMP/MPFR build cache read-only via `scripts/gmp-cache-key.sh` when `has_rs` is true, and its job `timeout-minutes` is 60.
- **R8.** Root `CLAUDE.md` and the math knowledge entries that describe `mutation-pr.yml` describe the per-PR gate and the local repro in the same change, and the Backlog row "Rust mutation leg has no missed-count ratchet" is rewritten to cover only drift the per-PR gate cannot see (deleted tests, rustc or cargo-mutants updates).
- **R9.** `scripts/mutation-pr-diff.sh <base-ref> <crate-dir> <out-file>` writes `git diff --relative=<crate-dir>/ <base-ref>...HEAD -- <crate-dir>`, so every path in it starts `src/`, and exits 2 on a wrong argument count or a crate dir without `Cargo.toml`.
- **R10.** A test builds a diff with `scripts/mutation-pr-diff.sh` from a one-line `sieve` change in a copy of factorial-rs and requires `cargo mutants --list --in-diff` to list at least one `sieve` mutant; it skips when cargo-mutants is absent outside CI and fails when absent under `CI=true`.
- **R11.** `mutation-testing.yml` classifies each crate on the code in `mutants.out/exit-code`, red when the file is missing, still with no limit argument.
- **R12.** `scripts/mutation-pr-detect.sh` prints `rs_canary=true` when the PR changes `mutation-pr.yml`, `scripts/mutation-pr-detect.sh`, `scripts/mutation-pr-diff.sh`, `scripts/mutation-pr-canary.sh`, `scripts/mutation-classify.sh` or `scripts/crate_templates/Makefile`, and `mutation-pr.yml` then runs `scripts/mutation-pr-canary.sh`, failing the step when it exits non-zero.
- **R13.** `scripts/mutation-pr-canary.sh` writes a one-line crate-relative diff from a trailing space appended to the single `let mut m = 2 * d;` line of `amicable/amicable-rs/src/lib.rs`, keeps the edit in place while it runs `make -C amicable/amicable-rs mutants-diff` on that diff and classifies with `max_missed 0` and `min_caught 1`, restores the file byte-for-byte in an EXIT trap, and exits 1 before running anything unless exactly one line matches.
- **R14.** The default-chunk write tests in `e/e-rs/src/main.rs` and `pi/pi-rs/src/main.rs` use a 4-thread pool and an input shorter than 4 bytes, so `len / threads` is still 0 and the zero-chunk mutant still fails them, without building a 64-thread pool.
- **V1.** Positive control, before the slice PR is marked ready: a throwaway draft PR built on the slice branch, adding an untested branch to one crate's `src/`, shows `mutation-pr` red naming that mutant; the PR is then closed and its branch deleted.
- **V2.** This slice's own PR changes gate files, so `mutation-pr` runs the amicable-rs canary green with caught at least 1 and missed 0 shown in the step summary; its R14 test-only changes select e-rs and pi-rs, which report `No mutants to filter` or caught-only results (its `mutation-pr.yml` change still selects every Python dir, as today).
- **N1.** No committed per-crate missed, timeout or unviable baseline file.
- **N2.** The monthly `mutation-testing.yml` sweep's verdict rules do not change: it calls `mutation-classify.sh` without a fourth argument, and only the source of the exit code it passes changes (R11).
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

### Round 2 (commit `b860b21`, all three lenses re-run after design changes)

- Goal-Fit (r2). Finding: `make` exits 2 for any failed recipe and 2 is green, so cargo-mutants' 1/3/4 and a cap kill reach the classifier as survivors; a partial `outcomes.json` with missed 0 would read green. Orchestrator confirmed: a recipe `exit 4` gives `make` 2. Assumption: an all-excluded changed line exits 0 without `outcomes.json`. Partly probed by the orchestrator (pi-rs `106:50`: the excluded mutant was dropped, the line's 3 other mutants ran, 3 caught) and by Ergonomics (e-rs `main.rs:129`: the enclosing function's replacement mutant still lists). Disposition: Addressed (operator, 2026-11-05, "Fix both now"): both recipes write `mutants.out/exit-code` and both workflows classify on it (R1, R5, R11; N2 amended).
- Ergonomics (r2). Finding: a change to the gate's own files selects no crate, so the PR that breaks the gate merges green and V2 never exercises the new path. Assumption: the loop keeps producing a non-empty measurement after V1. Disposition: Addressed (operator, 2026-11-05): gate-file changes run the amicable-rs canary (component 6, R12, R13); V2 now expects the canary green.
- Risk (r2). Finding: an empty diff file gives `Diff file is empty`, exit 0, so a detect/diff mismatch reads green; unit tests do not cover the wiring. Assumption: every in-scope timeout mutant never terminates. Disposition: Addressed (operator, 2026-11-05): selected crate with an empty diff is red, workflow test pins the wiring (R5); timeouts classified now (operator: "Classify timeouts now"), see Timeout classification.


### Round 3 (commit `97cd4ff`, all three lenses)

- Goal-Fit (r3). Finding: the canary's caught-at-least-1 check sat in untested workflow shell; routed through the classifier with limit 0, a canary that measured nothing would read green. Minor: R14 claimed pi-rs EAGAIN, which was not observed. Assumption: 60 minutes covers a multi-crate PR. Disposition: Addressed (operator, 2026-11-05): classifier `min_caught` with bats cases (R4, component 4); R14 now shrinks both tests; time budget measured (component 5: about 20 min for math#203's five crates).
- Ergonomics (r3). Finding: the canary restored `lib.rs` before cargo-mutants ran, so cargo-mutants refused the diff (`Diff content doesn't match source file`, exit 5) and every gate-file PR, V2 included, would be red. Smaller: the local repro needs committed work; no `concurrency: cancel-in-progress`. Assumption: as Goal-Fit. Disposition: Addressed (operator, 2026-11-05): the canary script runs `mutants-diff` with the edit in place and restores in an EXIT trap (component 6, R13). The repro note and `cancel-in-progress` were not chosen.
- Risk (r3). Finding: same canary ordering defect, found independently; the detector was missing from the canary's trigger list; a stale `outcomes.json` survives a no-mutant run; the new exit code makes a load-dependent baseline failure red in the monthly sweep. Assumption: CI core counts keep the 64-thread tests under the cap. Disposition: Addressed (operator, 2026-11-05): detector added (R12); recipes remove `mutants.out/` first (component 1); the 64-thread tests shrink to 4 threads (R14), which removes the assumption.
