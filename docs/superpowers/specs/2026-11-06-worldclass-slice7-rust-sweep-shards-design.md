# Worldclass slice 7: sharded Rust mutation sweep with a hang guard

- **Date:** 2026-11-06
- **Issue:** #217 (run 42157905568)
- **Operator choices:** approach A (shard + observability) over an exact CI repro first; N = 4 shards for every crate; 25-minute hang deadline.

## Problem

The monthly Rust sweep (`mutation-testing.yml`, one job per crate since ADR-0040) keeps losing hosted runners.
Every loss is the same shape: a crate that finishes in 2 to 16 minutes on a healthy runner is still in `Run mutants` at 48 to 57 minutes, then the job ends with "The hosted runner lost communication with the server".

| Run                      | Commit             | Lost                        | Same crate healthy                                           |
| ------------------------ | ------------------ | --------------------------- | ------------------------------------------------------------ |
| 41769558239 (2026-11-04) | first matrix sweep | collatz, fib, sq at ~48 min | 3-7 min on re-run                                            |
| 42087535763 (2026-11-05) | 81b4602            | pi-rs at 55 min             | 16 min in 42087540288, **same commit, dispatched 2 s later** |
| 42157905568 (2026-11-06) | 70ea2a9            | pi-rs at 57 min             | 14 min in 41952665142                                        |

What is established, and over which population:

- **The job log of a lost runner is gone.** `gh api .../actions/jobs/<id>/logs` returns `BlobNotFound` for both lost pi-rs jobs (127490109735, 127696392504). So nothing names the mutant in flight. Population: those two jobs.
- **It is not a property of the commit.** 81b4602 passed and lost pi-rs on two dispatches 2 s apart.
- **It is not a single runaway file.** math#211's 256 MiB `ulimit -f` cap was in place for 42157905568.
- **Every per-test timeout fires at 42 s in CI**, so ~40 minutes past a healthy finish is time cargo-mutants' own timeout is not bounding.
- **Local repro did not reproduce it.** pi-rs at 70ea2a9 on `claude`, `taskset -c 0-3`, `</dev/null`: 6 min, 166 mutants: 159 caught, 3 unviable, 4 timeouts (cargo-mutants exit 3, make exit 2). A 5 s sampler saw no orphaned `pi` process and a peak child RSS of 2.6 GB (`lib.rs:159:70 + → *`, the `pi 10000000` regression test), killed at the 30 s timeout. Population: one local run on a 4-pinned-CPU Threadripper, not a hosted runner. CI times out 10 pi mutants against 4 locally, so the environments differ in a way not yet named.
- **Orphans exist in CI but are not the pi-rs mechanism on the evidence so far.** GitHub's job-end cleanup terminated 1-3 orphaned test binaries in prime, sq, factorial and collatz jobs across four runs; pi-rs's healthy runs had 0. Population: the healthy jobs of runs 41952665142, 42087535763, 42087540288, 42157905568.

The root cause is unknown. This slice does not claim to fix it. It makes a loss cheap (one quarter of one crate), makes the hang end as a red verdict with logs before the runner dies, and makes a loss that still happens narrow the suspect set.

#217 also has a misleading body: `Cause: verdicts-present` / `Failing crates: (none flagged; see run log)` followed by `Cause: missing-status`. `mutation-notify.sh` prepends `build_body verdicts-present` whenever the run failed and any status file arrived, even when none of them is red.

## Design

### 1. `MUTANT_SHARD` on the Rust `mutants` target (template)

`scripts/crate_templates/Makefile`'s `mutants` target accepts an optional `MUTANT_SHARD=k/n`, the same variable name as the Python template.
When set and well-formed it appends `--shard k/n --sharding round-robin` to the `cargo mutants` command.
Round-robin, not cargo-mutants' default `slice`, spreads one function's consecutive expensive mutants (pi's `compute_pi`) across shards.
A malformed value (not two non-negative integers, `n < 1`, `k >= n`) prints `error: MUTANT_SHARD must be k/n with 0 <= k < n, got <value>` and exits 1 before `MUTANTS_SETUP`, so no `mutants.out/exit-code` is written and the workflow's existing missing-exit-code rule reports it red.
Unset, the command is byte-identical to today's. `mutants-diff` does not take it.
Rendered to all 11 crates by `scripts/render_crate_files.py --write`; `tests/test_crate_uniformity.py` already fails on drift.

### 2. `scripts/mutation-deadline.sh`

`mutation-deadline.sh <minutes> <command> [args...]` runs the command in a new session (`setsid`) and waits for it.

- Command exits before the deadline: the script exits with the command's code.
- Deadline passes: it sends `TERM` to every process in the session (`pkill -TERM -s <sid>`), waits up to 60 s, sends `KILL` to any survivor, and exits **124**.

The session, not the process group, is the kill unit: cargo-mutants puts each test run in its own process group (that is how it kills a timed-out test tree), so a group signal from the wrapper would miss exactly the test processes most likely to be the ones running away. A session contains them all.
Non-integer or non-positive minutes, or no command, exit 2 with a usage line.

### 3. `scripts/mutation-sampler.sh`

`mutation-sampler.sh <out-file> [interval-seconds]` (default 30) appends, every interval until killed: a UTC timestamp, `free -m`'s `Mem:` line, `df -h` for the workspace filesystem, and the 10 processes with the largest RSS (`ps -eo pid,ppid,pgid,rss,etime,pcpu,comm --sort=-rss`).
The workflow starts it in the background before `Run mutants` and stops it in an `always()` step. Its file goes in `diag/`, uploaded with the status artifact.
It is evidence only when the job survives, which the deadline makes the common case. No off-runner channel: that needs `issues: write` on 44 matrix jobs, more permission than a diagnostic justifies.

### 4. `mutation-testing.yml`: crate × shard matrix

- `setup` builds `include` entries of `{crate, slug, shard}` for every crate and `shard` in `0..3`, `slug` = `<crate with / as ->-<shard>`. `units` is every slug (44 for a full sweep). The `crate` dispatch input still selects one crate, now 4 cells. The shard count is one `SHARDS=4` assignment in `setup`, applied to every crate.
- `mutants` job name `Mutation <crate> <shard>/4`, `timeout-minutes: 60` unchanged (the deadline sits inside it).
- `Run mutants` runs `bash scripts/mutation-deadline.sh 25 make -C "${CRATE_DIR}" mutants MUTANT_SHARD="${SHARD}/4"`, captures its code, and when it is 124 writes `red: <slug> — hung past 25 min; last log line: <final line of <crate>/mutants.out/log, or "none">` to `status/<slug>` and the step summary, and fails the step. Any other code takes today's path unchanged (exit-code file, classifier `0 1`).
- `diag/` joins `status/` and `marker/` in the status artifact.

Per-shard classification stays `0 1`: any missed mutant is red, a shard with zero catches is red. The smallest shard is amicable's 5 mutants (20 / 4); a shard that catches nothing is a real red, not noise.

### 5. `mutation-notify.sh` body

When the cause is `verdicts-present` and `render_red_units` returns nothing, the expected-units path does not prepend `build_body`: the `missing-status` body stands alone. A red unit present keeps today's prepend and its `_omit_red` behaviour.

### 6. Docs

ADR-0043 "Sharded Rust mutation sweep with a hang guard" (amends ADR-0040 decisions 1, 2 and 5), root `CLAUDE.md` mutation lines, the Backlog's runner-loss row rewritten to point at this spec, plan index row.

## Testing

- **Template:** `tests/scripts/makefile.bats` renders a crate Makefile and, with a PATH-mocked `cargo`, asserts the argv for unset `MUTANT_SHARD` (no `--shard`), `MUTANT_SHARD=2/4` (`--shard 2/4 --sharding round-robin`, each its own argument), and refusals for `4/4`, `a/4`, `1/0`, `1`, `-1/4` (exit 1, message, cargo never called, no `mutants.out/exit-code`).
- **Deadline:** `tests/scripts/mutation_deadline.bats` with fractional-minute support via an env override for the unit (`MUTATION_DEADLINE_UNIT_SECONDS`, default 60) so tests run in seconds: command exits 0 / 3 before deadline (code passed through); a command that sleeps past the deadline gives 124; a grandchild that moved to its own process group (same session, as cargo-mutants' test runs do) is dead after the wrapper returns (checked by pid); a TERM-ignoring child is KILLed after the grace period (grace also env-overridable); usage errors exit 2.
- **Sampler:** bats runs it at a 1 s interval for ~2.5 s and asserts ≥2 timestamped blocks each with a `Mem:` line and a process table header; a missing out-file directory exits non-zero.
- **Workflow:** `tests/test_mutation_workflows.py` asserts `setup` emits 4 × crates cells with distinct slugs, `units` equals the slug list, the run step invokes `mutation-deadline.sh 25` and passes `MUTANT_SHARD`, a 124 path writes a `hung past 25 min` status, and `diag/` is in the status artifact.
- **Notify:** `tests/scripts/mutation_notify.bats`: failed run, all arriving statuses green, one unit missing → body starts with `Cause: missing-status` and contains no `verdicts-present`; with one red unit present → today's prepended body unchanged.

## Requirements

- **R1.** `[PR1]` The rendered Rust `make mutants` with `MUTANT_SHARD=k/n` (0 <= k < n, n >= 1) passes `--shard k/n --sharding round-robin` to `cargo mutants`; without `MUTANT_SHARD` the `cargo mutants` argv is unchanged from master.
- **R2.** `[PR1]` A malformed `MUTANT_SHARD` makes `make mutants` exit 1 with `MUTANT_SHARD must be k/n` on stderr, without running `cargo` and without writing `mutants.out/exit-code`.
- **R3.** `[PR1]` All 11 crate Makefiles are the rendered template (`tests/test_crate_uniformity.py` green).
- **R4.** `[PR1]` `scripts/mutation-deadline.sh <minutes> <cmd...>` exits with the command's code when it finishes in time, and exits 124 after the deadline having signalled every process in the command's session, KILLing any still alive after the grace period (default 60 s); `MUTATION_DEADLINE_UNIT_SECONDS` (default 60) and `MUTATION_DEADLINE_GRACE_SECONDS` (default 60) override the minute length and grace for tests.
- **R5.** `[PR1]` `scripts/mutation-deadline.sh` exits 2 with a usage line for missing or non-positive-integer minutes or a missing command.
- **R6.** `[PR1]` `scripts/mutation-sampler.sh <file> [seconds]` appends a timestamp, the `free -m` `Mem:` line, `df -h` of the working directory and the top 10 RSS processes every interval (default 30 s).
- **R7.** `[PR1]` `mutation-testing.yml` `setup` emits one matrix cell per crate and shard 0-3 (44 for a full sweep, 4 for a `crate` input), with slug `<crate-slug>-<shard>`, and `units` equal to the cell slugs.
- **R8.** `[PR1]` `Run mutants` runs `scripts/mutation-deadline.sh 25 make -C <crate> mutants MUTANT_SHARD=<shard>/4`; on exit 124 it writes `red: <slug> — hung past 25 min; last log line: <line or none>` to `status/<slug>` and the step summary and fails.
- **R9.** `[PR1]` The sampler runs during `Run mutants` and its output in `diag/` is part of the `mutants-status-<slug>` artifact.
- **R10.** `[PR1]` `mutation-notify.sh` omits the `verdicts-present` prefix when no arriving status is red, so the body starts `Cause: missing-status`; with a red status the body is unchanged from master.
- **R11.** `[PR1]` ADR-0043 records the shard count, sharding mode, deadline and the session-kill rationale, and ADR-0040's status line names it.
- **R12.** `[PR1]` Root `CLAUDE.md` states the monthly Rust sweep runs 4 round-robin shards per crate under a 25-minute deadline; it stays under 30,000 bytes.
- **V1.** One full `workflow_dispatch` sweep on the merged master: 44 cells, record each cell's duration, verdict, and any runner loss with its shard's `cargo mutants --list --shard k/4 --sharding round-robin` set.
- **V2.** If V1 or a later sweep loses a cell, "Re-run failed jobs" recovers it and `notify` closes or comments as for ADR-0040's V2.
- **V3.** The deadline path is exercised once for real: a dispatch on a throwaway branch with the deadline lowered to 1 minute on one crate yields the `hung past` status, an uploaded `mutants.out/log` and a non-empty `diag/` file. Not merged.
- **N1.** No crate gets a different shard count, sharding mode or deadline from the others.
- **N2.** `mutants-diff`, `mutation-pr.yml` and the Python mutation workflow are unchanged.
- **N3.** No matrix job gains a permission beyond `contents: read`.
- **N4.** The classifier thresholds (`0 1`) and `scripts/mutation-classify.sh` are unchanged.
