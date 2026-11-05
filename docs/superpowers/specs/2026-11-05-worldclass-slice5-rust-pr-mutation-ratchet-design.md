# Worldclass slice 5: per-PR Rust mutation ratchet

## Problem

Slice 4 (math#203, math#204) brought all 11 Rust crates to 0 missed mutants. Full sweep run
41952665142 at `0d28038` recorded missed 0 in every crate. Nothing holds that line.

`scripts/mutation-classify.sh` scores survivors (cargo-mutants exit 2) green, so the monthly
`mutation-testing.yml` sweep (ADR-0040) never goes red for a new survivor. A crate can drift
from 0 missed back to 30 with no red leg and no issue. This is the Backlog row "Rust mutation
leg has no missed-count ratchet".

One crate already has a gate. `mutation-pr.yml` runs
`cargo mutants --in-diff /tmp/pr.diff --timeout 30 --no-shuffle` for `factorial/factorial-rs`
only, and a missed mutant there fails the PR. The other 10 crates have no per-PR gate. That
asymmetry breaks the operator rule that all crates are treated identically, and the fixed
`--timeout 30` is the form root `CLAUDE.md` forbids (#95).

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

### Components

1. **`mutants-diff` Makefile target.** Added to `scripts/crate_templates/Makefile` and
   rendered into all 11 crates by `scripts/render_crate_files.py --write`. It keeps the
   `mutants` recipe's memory cap (`ulimit -v 8388608`, `MUTANTS_UNCAPPED=1` escape, fail
   closed where the cap cannot be set) and runs
   `cargo mutants --in-diff "$(DIFF)" --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle`.
   It exits 2 with a usage message naming `DIFF` when `DIFF` is unset or not a readable file,
   before invoking cargo-mutants. The target joins the `.PHONY` list.
2. **Crate detection.** `scripts/mutation-pr-detect.sh` also prints `rs_dirs=<sorted crate
dirs>` and `has_rs=true|false`. A crate dir `<p>/<p>-rs` is selected when the PR changes a
   path matching `<p>/<p>-rs/src/*.rs` (any depth under `src/`). The crate list is derived
   from `git ls-files '*/*-rs/Cargo.toml'`, not a hardcoded list. The existing Python outputs
   are unchanged.
3. **Classifier limit.** `scripts/mutation-classify.sh` accepts an optional fourth argument,
   `max_missed` (a non-negative integer). With no fourth argument, behaviour is byte-for-byte
   today's. With it, a run that would be green is red when `missed > max_missed`, and the red
   line names each survivor from `mutants.out/missed.txt` beside `outcomes.json`. A
   non-integer `max_missed` is red with a message naming the argument. The existing rules hold
   in both modes: no `outcomes.json` with exit 0 is green (the measured `--in-diff` no-mutable-
   lines case: `INFO No mutants to filter`, exit 0, no `mutants.out/`), and
   `caught + missed == 0` with an `outcomes.json` present is red.
4. **Workflow.** In `mutation-pr.yml`, the inline factorial-only grep and the
   `Run cargo mutants (factorial-rs)` step are replaced:
   - `has_rs` and `rs_dirs` come from `mutation-pr-detect.sh`.
   - A GMP key step and a read-only `actions/cache/restore` step, the same shape as
     `scripts/crate_templates/ci.yml` (`scripts/gmp-cache-key.sh`, non-strict, so a bad key
     degrades to a cold build), run when `has_rs` is true.
   - One step loops over `rs_dirs`: `make -C <dir> mutants-diff DIFF=/tmp/pr.diff`, then
     `mutation-classify.sh <rc> <dir>/mutants.out/outcomes.json <dir> 0`. It runs every crate
     even after a red one, prints each verdict to `$GITHUB_STEP_SUMMARY`, and exits 1 at the
     end when any crate was red.
   - `timeout-minutes` rises from 30 to 60, since a PR touching several crates now runs
     several in-diff passes in one job.

### Error handling

- A crate whose in-diff mutants are all unviable gives `caught + missed == 0` with an
  `outcomes.json`, which is red. That fails closed. It needs a diff whose every mutation fails to compile;
  how often that occurs is unmeasured. The red line says "nothing was
  evaluated", so the cause is visible.
- `make` failing for a reason other than survivors (baseline tests fail, memory cap kill) is
  red through the classifier's existing exit-code rule.
- A dependency-only PR (Renovate `Cargo.lock`) changes no `src/` file, selects no crate, and
  skips the Rust step.

## Testing

- `tests/scripts/mutation_pr_detect.bats`: a `src/` change selects its crate; a nested
  `src/a/b.rs` change selects it; a crate `Cargo.toml`, `.cargo/mutants.toml` or `tests/`
  change selects nothing; two crates sort; no Rust change prints `has_rs=false` and an empty
  `rs_dirs`; Python outputs unchanged.
- `tests/scripts/mutation_classify.bats`: with `max_missed 0`, missed 0 is green, missed 1 is
  red and names the survivor from `missed.txt`, timeouts with missed 0 are green, missing
  `outcomes.json` with exit 0 is green, a non-integer limit is red; with no fourth argument
  missed 3 is green, as today.
- `tests/scripts/makefile.bats`: all 11 crates' `mutants-diff` carry the cap, the multiplier
  pair, `--in-diff`, no fixed `--timeout`, and exit 2 naming `DIFF` when it is unset.
- `tests/test_mutation_workflows.py`: the Rust step calls `mutants-diff`, passes `0` as the
  classifier limit, contains no `--timeout ` flag, and the factorial-only step is gone.
- `tests/test_crate_uniformity.py` keeps the 11 Makefiles identical to the template.

## Requirements

- **R1.** `scripts/crate_templates/Makefile` has a `mutants-diff` target, rendered into all 11 crate `Makefile`s and listed in `.PHONY`, that keeps the `mutants` recipe's `ulimit -v 8388608` cap and `MUTANTS_UNCAPPED` escape and runs `cargo mutants --in-diff "$(DIFF)" --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle`.
- **R2.** `make mutants-diff` exits 2 with a message naming `DIFF` when `DIFF` is unset or not a readable file, without invoking cargo-mutants.
- **R3.** `scripts/mutation-pr-detect.sh` prints `rs_dirs=` (sorted crate dirs, derived from `git ls-files '*/*-rs/Cargo.toml'`) and `has_rs=`, selecting a crate only when a changed path is a `.rs` file under that crate's `src/`.
- **R4.** `scripts/mutation-classify.sh` with no fourth argument behaves as before; with a fourth argument `max_missed` it reports red when `missed > max_missed`, naming each survivor from `mutants.out/missed.txt`, and reports red on a non-integer `max_missed`.
- **R5.** `mutation-pr.yml` runs `make -C <dir> mutants-diff DIFF=/tmp/pr.diff` for every dir in `rs_dirs`, classifies each with limit `0`, continues past a red crate, and fails the step when any crate is red.
- **R6.** `mutation-pr.yml` no longer contains the factorial-only detection grep, the `Run cargo mutants (factorial-rs)` step, or any fixed `--timeout` flag for cargo-mutants.
- **R7.** `mutation-pr.yml` restores the GMP/MPFR build cache read-only via `scripts/gmp-cache-key.sh` when `has_rs` is true, and its job `timeout-minutes` is 60.
- **R8.** Root `CLAUDE.md`, the math knowledge entries that describe `mutation-pr.yml`, and the Backlog row "Rust mutation leg has no missed-count ratchet" are updated in the same change: the row is removed and the per-PR gate is described.
- **V1.** Positive control: a throwaway draft PR adding an untested branch to one crate's `src/` shows `mutation-pr` red naming that mutant; the PR is then closed and its branch deleted.
- **V2.** Negative control: this slice's own PR, which changes no crate `src/` file, shows `mutation-pr` green with the Rust step skipped (its `mutation-pr.yml` change still selects every Python dir, as today).
- **N1.** No committed per-crate missed, timeout or unviable baseline file.
- **N2.** The monthly `mutation-testing.yml` sweep's classification does not change: it calls `mutation-classify.sh` without a fourth argument.
- **N3.** No mutation testing in the local pre-push hook.
- **N4.** No change to the Python mutation path in `mutation-pr.yml` or elsewhere.
