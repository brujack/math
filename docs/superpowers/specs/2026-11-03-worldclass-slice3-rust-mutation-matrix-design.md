# Worldclass slice 3: one job per crate in the Rust mutation sweep

- **Date:** 2026-11-03
- **Status:** Draft
- **Scope:** `.github/workflows/mutation-testing.yml`, `tests/test_mutation_workflows.py`, root `CLAUDE.md` (two lines), a new ADR, `docs/superpowers/README.md`
- **Revised:** 2026-11-03 after Step 8 round 1 (operator chose to re-aggregate `mutants-output` in `notify`)

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

It writes two outputs, both derived from one slug function (the directory with `/`
replaced by `-`, so `pi/pi-rs` becomes `pi-pi-rs`, the name the status file already
uses):

- `matrix={"include":[{"crate":"<dir>","slug":"<slug>"}, ...]}`, built with `jq -c`
  rather than string concatenation. Each directory comes from the git listing; a
  validated `crate` input is matched against that list first.
- `units=<slug> <slug> ...`.

The slug travels in the matrix because the crate jobs need it in places a shell cannot
reach: artifact names are `${{ }}` expressions, expressions have no string replace, and
artifact names may not contain `/` (actions/toolkit
`path-and-artifact-name-validation.ts`). Every later use reads `matrix.slug`.

### mutants job

`strategy.matrix` comes from `fromJSON(needs.setup.outputs.matrix)` (an `include`
list of `crate`/`slug` pairs), with
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
   `mutants-output-<slug>` (`<crate>/mutants.out/` and `marker/`). The second path is
   there on purpose: upload-artifact roots an artifact at the paths' common ancestor,
   so a lone `<crate>/mutants.out/` would lose its crate prefix, and eleven of them
   would collide when merged.

The crate directory and slug reach every `run:` step through `env:`, never by
expression interpolation inside `run:`.

When a runner is lost, no further step runs on it: the run of 2026-11-03 shows
`Upload mutants output` (`if: always()`) as `skipped`. So for that case neither the
`cancelled()` step nor the uploads fire, and the crate is named only by `notify`'s
`EXPECTED_STATUS_UNITS` check, which lists a unit with no `status/<slug>` as missing.
The `cancelled()` step covers the other cases: the 60-minute timeout and a manual
cancel.

### notify job

`needs: [setup, mutants]`, `if: always()`. It downloads `pattern: mutants-status-*` with
`merge-multiple: true` into `artifact`. The step keeps `continue-on-error: true`, which
`tests/test_workflow_continue_on_error.py` already allows for this site. It passes
`EXPECTED_STATUS_UNITS: ${{ needs.setup.outputs.units }}` alongside the existing
environment (`RESULT`, `DL_OUTCOME`, `ARTIFACT_DIR`, `FULL_SWEEP` and the rest).
`scripts/mutation-notify.sh` is unchanged.

`notify` also keeps the single `mutants-output` artifact alive. ai-config's monthly
`mutation-review.yml` runs `mutation_review.py --workflow mutation-testing.yml
--artifact mutants-output`, which downloads that exact name; its 2026-11-02 run read
it. A rename would stop Rust mutation-review PRs while that job stays green. So
`notify` downloads `pattern: mutants-output-*` with `merge-multiple: true` into
`outputs` (never into `artifact`: `mutation-notify.sh` reads any extra root entry there
as a different attestation cause) and uploads it as `mutants-output` (30-day
retention, unchanged, `overwrite: true` so a re-run attempt cannot 409 on the name),
with the same `<crate>/mutants.out/` layout as today minus `status/`, which the
consumer does not read (it `rglob`s `outcomes.json`).

Step order matters, because filing the issue is the one thing `notify` must not skip:
the tracking-issue step gets `if: always()`, and both output steps come after it, each
with `if: always()`. Neither gets `continue-on-error`. A failed re-aggregation then
fails `notify` visibly without stopping the issue.

### What changes in practice

- **Wall-clock:** about 20 min instead of about 70 (the slowest crate plus setup).
- **A lost runner:** it costs one crate, which `EXPECTED_STATUS_UNITS` names in the
  tracking issue as missing.
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
  classifier. A red crate fails the step and writes its status. A green crate passes
  and writes `status/<slug>` with the green verdict, asserted by content, since a step
  that writes nothing on green would make `notify` report every crate missing.
- **Cancelled step:** run in a sandbox, it writes the `did not finish` line when no
  status exists and leaves an existing status untouched.
- **Slugs:** the matrix `include` slugs equal `units`, and each equals its crate with
  `/` replaced by `-`.
- **Structure:** `fail-fast: false`, the 60-minute timeout, the `cancelled()` step, both
  upload names (from `matrix.slug`), the output artifact's extra `marker/` path, the
  status download pattern with `merge-multiple`, `EXPECTED_STATUS_UNITS` wired from
  `setup`, the re-aggregated `mutants-output` upload (`overwrite: true`, from
  `outputs`), and step order in `notify`: the tracking-issue step has `if: always()`
  and precedes both output steps, which also have `if: always()`.

## Requirements

- **R1.** `mutation-testing.yml` has a `setup` job whose outputs come from `git ls-files '*/*-rs/Cargo.toml'` through one slug function: `matrix` is a `jq`-built `include` list of `crate`/`slug` pairs and `units` lists the same slugs; it fails, naming the input, on an unknown or newline-bearing `crate`, and fails on an empty list.
- **R2.** The `mutants` job runs one matrix job per crate from `fromJSON(needs.setup.outputs.matrix)` with `fail-fast: false` and `timeout-minutes: 60`, and each job runs `make -C <crate> mutants` and `scripts/mutation-classify.sh` into `status/<slug>`.
- **R3.** A step with `if: cancelled()` writes a `red: <slug> — did not finish` status when the crate has none.
- **R4.** Each crate job uploads `mutants-status-<slug>` (status and marker) and `mutants-output-<slug>` (`<crate>/mutants.out/` and marker) with `if: always()`, the names taken from `matrix.slug`.
- **R5.** `notify` needs `setup` and `mutants`, downloads `pattern: mutants-status-*` with `merge-multiple: true`, and passes `EXPECTED_STATUS_UNITS` from `needs.setup.outputs.units` to `scripts/mutation-notify.sh`.
- **R6.** Tests run the setup script and the per-crate run step in a sandbox and pin the behaviours listed under Testing, including 11 units on the real tree.
- **R7.** A new ADR records one job per crate and supersedes ADR-0038's single-job wording; the root `CLAUDE.md` mutation-CI line and notify line (`needs: [mutants]`) describe the matrix without growing the file.
- **R8.** After its tracking-issue step (which runs `if: always()`), `notify` downloads `pattern: mutants-output-*` with `merge-multiple: true` into `outputs` and uploads it as one `mutants-output` artifact (`overwrite: true`) with `<crate>/mutants.out/` paths, both steps `if: always()`, so ai-config's `mutation-review.yml` keeps reading it.
- **V1.** After merge, dispatch a full sweep: 11 crate jobs run, `notify` sees 11 statuses, the `mutants-output` artifact holds 11 `<crate>/mutants.out/` trees, and #195 closes on an all-green sweep.
- **V2.** Settle whether "Re-run failed jobs" on a matrix run lets `notify` see the first attempt's green `mutants-status-*` artifacts: record the result in the ADR, and if it does not, record that recovery from a lost runner needs a full re-dispatch.
- **N1.** No change to any crate `Makefile` `mutants` target, `scripts/mutation-classify.sh`, `scripts/mutation-notify.sh`, `mutation-pr.yml` or `mutation-testing-python.yml`.
- **N2.** No GMP build cache in the mutants jobs.
- **N3.** No change to the cargo-mutants version or the monthly cron.

## Multi-Lens Review

Reviewed at commit: `64310ed` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: Worth building (a port of the working Python pattern), but the motivating case is credited to the wrong mechanism: run 41720704930 shows `Upload mutants output` (`if: always()`) `skipped` after the runner loss, so neither the `cancelled()` step nor the uploads run on a lost runner; only `EXPECTED_STATUS_UNITS` in `notify` names the crate. The attribution changes the response only if "Re-run failed jobs" lets `notify` see the first attempt's green artifacts; wall-clock has no consumer for a monthly cron.
Assumption: That a "Re-run failed jobs" `notify` sees attempt-1 artifacts merged with the re-run crate's. Settle with a deliberate cancel-and-rerun after merge, or the download-artifact docs on attempt scoping.
Disposition: Addressed — the lost-runner wording now credits `EXPECTED_STATUS_UNITS`; the re-run question became V2.

### Ergonomics

Finding: Load-bearing: ai-config's `mutation-review.yml` downloads the exact artifact name `mutants-output` (verified: its 2026-11-02 run read run 36937484307's artifact). Per-crate artifacts would silently stop Rust mutation-review PRs while that job stays green; the Python consumer is already broken the same way since sharding. Smaller: root `CLAUDE.md` needs two lines changed (139 and 147), not one, at exactly 30000 bytes.
Assumption: That the Rust mutation-review consumer is still wanted. Settled by the operator: keep it working.
Disposition: Addressed — operator chose to re-aggregate in `notify`: R8 downloads `mutants-output-*` and re-uploads one `mutants-output` with the same layout; R7 names both `CLAUDE.md` lines.

### Risk

Finding: Load-bearing: the spec never said where `<slug>` comes from inside a crate job; expressions cannot replace `/`, and artifact names may not contain `/` (actions/toolkit validation), so naming per-crate artifacts needs the slug in the matrix. Otherwise the slug is recomputed in three places and drift makes every green crate read as missing. Test gap: "a green crate passes" did not assert that `status/<slug>` is written; the `cancelled()` step was only checked for structure.
Assumption: Same re-run-failed-jobs question as Goal-Fit.
Disposition: Addressed — setup emits a `jq`-built `include` list of `crate`/`slug`; every later use reads `matrix.slug`; tests assert the green status content, the cancelled step's behaviour, and slug equality with `units`. Also found while revising: a lone `<crate>/mutants.out/` upload loses its crate prefix, so the output artifact adds `marker/` to keep paths.

### Risk (round 2, scoped re-review at `c92e537`)

Sections reviewed: setup outputs, mutants uploads, notify re-aggregation, Testing, R1, R4, R7, R8, V1, V2. Finding: the new output steps could skip the tracking-issue step (it had no `if: always()` and only `dl` may carry `continue-on-error`), so a digest mismatch or a re-run 409 on `mutants-output` would stop the issue being filed; the output download directory was unnamed. Verified: the least-common-ancestor claim holds and the consumer `rglob`s `outcomes.json`; an empty pattern download is benign.
Assumption: That attempt-1 artifacts are visible to, and name-conflict in, a "Re-run failed jobs" attempt. V2 settles it after merge.
Disposition:

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
