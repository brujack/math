# Worldclass slice 3: one job per crate in the Rust mutation sweep

- **Date:** 2026-11-03
- **Status:** Draft
- **Scope:** `.github/workflows/mutation-testing.yml`, `tests/test_mutation_workflows.py`, `tests/scripts/mutation_notify.bats` (one comment), root `CLAUDE.md` (one line), a new ADR, `docs/superpowers/README.md`

## Problem

`mutation-testing.yml` runs all 11 Rust crates one after another in a single job. Two
measured runs on the same workload:

| Run         | Date       | Outcome                                                                                                                                                                                                                   |
| ----------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 41271402669 | 2026-11-01 | Job ran 70 min (04:01 to 05:11). All 11 real crates green; the longest were `e-rs` 18 min, `pi-rs` 14 min, `prime-rs` 10 min. The only reds were the six cargo-deny fixture crates, which math#200 removed from the list. |
| 41720704930 | 2026-11-03 | `Run mutants` was cancelled at 78 min with the annotation `The hosted runner lost communication with the server`. GitHub kept no job log (the logs API returns `BlobNotFound`).                                           |

The 360-minute timeout was not reached, and the Nov 1 run finished the same work in less
time on one runner. The evidence points to a transient runner loss, not a reproducible
resource fault. A single job still makes any loss total: one dead runner discards every
crate's result, and `notify` can only report `no-attestation` for the whole run. It
cannot say which crate was running.

The Aug-01 spec (`2026-08-01-mutation-testing-per-project-design.md`, "Scope: Phase A
only") deferred a per-crate matrix as "Phase B". Its trigger was "one successful full run
of `mutation-testing.yml` on master". Run 36937484307 (2026-10-01) was that run, so the
trigger is met. The same spec noted that "per-crate attribution on a dead runner requires
one runner per crate — which is the matrix".

`mutation-testing-python.yml` already runs as setup → matrix → notify (ADR-0033), and
`scripts/mutation-notify.sh` already supports a matrix through `EXPECTED_STATUS_UNITS`
(`tests/scripts/mutation_notify.bats` covers it).

## Design

### setup job

A new `setup` job holds the crate-list logic that today sits in the `List crates` step,
unchanged in substance:

- The crate list comes from `git ls-files '*/*-rs/Cargo.toml'`.
- A dispatch `crate` input must match one listed directory, or the job fails naming it.
- An empty list fails the job rather than reporting green.

It writes two outputs:

- `matrix={"crate":[<dir>, ...]}`, valid JSON. Each directory comes from the git
  listing, never from raw input; a validated `crate` input is matched against that
  list first.
- `units=<slug> <slug> ...`, where a slug is the directory with `/` replaced by `-`
  (`pi/pi-rs` becomes `pi-pi-rs`). That is the name the status file already uses
  (`status/<slug>`).

### mutants job

`strategy.matrix` comes from `fromJSON(needs.setup.outputs.matrix)`, with
`fail-fast: false` and `timeout-minutes: 60`. 60 is a little over three times the slowest
measured crate (18 min). Each job:

1. checks out, writes `marker/job-began`, sets up the toolchain and installs
   `cargo-mutants` (`--locked --version 27.1.0`, unchanged);
2. runs `make -C <crate> mutants`, captures its exit code, runs
   `scripts/mutation-classify.sh` on it, and writes the verdict to `status/<slug>` and the
   step summary, exiting non-zero on a red verdict (the existing capture-before-pipe and
   `|| cls=$?` handling is kept);
3. on `cancelled()`, writes `red: <slug> — did not finish (cancelled or timed out)` to
   `status/<slug>` if no status exists;
4. always uploads `mutants-status-<slug>` (`status/`, `marker/`) and
   `mutants-output-<slug>` (`<crate>/mutants.out/`).

The crate directory reaches the run step through `env:`, never by expression
interpolation inside `run:`.

### notify job

`needs: [setup, mutants]`, `if: always()`. It downloads `pattern: mutants-status-*` with
`merge-multiple: true` into `artifact`. The step keeps `continue-on-error: true`, which
`tests/test_workflow_continue_on_error.py` already allows for this site. It passes
`EXPECTED_STATUS_UNITS: ${{ needs.setup.outputs.units }}` alongside the existing
environment (`RESULT`, `DL_OUTCOME`, `ARTIFACT_DIR`, `FULL_SWEEP` and the rest).
`scripts/mutation-notify.sh` is unchanged.

### What changes in practice

- **Wall-clock:** about 20 min instead of about 70 (the slowest crate plus setup).
- **A lost runner:** it costs one crate. The cancelled step, or the missing status for
  `EXPECTED_STATUS_UNITS`, names that crate in the tracking issue.
- **Runner minutes:** rise by roughly 11 `cargo install cargo-mutants` runs (a few
  minutes each). The repo is public, so this has no billing effect.

## Testing

The Rust tests in `tests/test_mutation_workflows.py` are rebuilt on the shape the Python
tests already use (`SetupJobTests`, `MutantsJobTests`, `NotifyJobTests`):

- **Setup behaviour** (runs the setup script in a sandbox with a fake `GITHUB_OUTPUT`):
  - an empty input yields 11 units, equal to the slugged `git ls-files` list;
  - a known crate yields exactly one unit;
  - an unknown crate fails and names it;
  - an input with a newline fails and writes no output;
  - an empty listing fails and writes no output;
  - the `matrix` output parses as JSON and its `crate` list matches the units.
- **Mutants behaviour:** the per-crate run step runs in a sandbox with a fake `make` and
  classifier. A red crate fails the step and writes its status; a green crate passes.
- **Structure:** `fail-fast: false`, the 60-minute timeout, the `cancelled()` step, both
  upload names, the download pattern with `merge-multiple`, and `EXPECTED_STATUS_UNITS`
  wired from `setup`.

## Requirements

- **R1.** `mutation-testing.yml` has a `setup` job whose outputs `matrix` and `units` come from `git ls-files '*/*-rs/Cargo.toml'`; it fails, naming the input, on an unknown or newline-bearing `crate`, and fails on an empty list.
- **R2.** The `mutants` job runs one matrix job per crate from `fromJSON(needs.setup.outputs.matrix)` with `fail-fast: false` and `timeout-minutes: 60`, and each job runs `make -C <crate> mutants` and `scripts/mutation-classify.sh` into `status/<slug>`.
- **R3.** A step with `if: cancelled()` writes a `red: <slug> — did not finish` status when the crate has none.
- **R4.** Each crate job uploads `mutants-status-<slug>` (status and marker) and `mutants-output-<slug>` (mutants.out) with `if: always()`.
- **R5.** `notify` needs `setup` and `mutants`, downloads `pattern: mutants-status-*` with `merge-multiple: true`, and passes `EXPECTED_STATUS_UNITS` from `needs.setup.outputs.units` to `scripts/mutation-notify.sh`.
- **R6.** Tests run the setup script and the per-crate run step in a sandbox and pin the behaviours listed under Testing, including 11 units on the real tree.
- **R7.** A new ADR records one job per crate and supersedes ADR-0038's single-job wording; the root `CLAUDE.md` mutation-CI line describes the matrix without growing the file.
- **V1.** After merge, dispatch a full sweep: 11 crate jobs run, `notify` sees 11 statuses, and #195 closes on an all-green sweep.
- **N1.** No change to any crate `Makefile` `mutants` target, `scripts/mutation-classify.sh`, `scripts/mutation-notify.sh`, `mutation-pr.yml` or `mutation-testing-python.yml`.
- **N2.** No GMP build cache in the mutants jobs.
- **N3.** No change to the cargo-mutants version or the monthly cron.
