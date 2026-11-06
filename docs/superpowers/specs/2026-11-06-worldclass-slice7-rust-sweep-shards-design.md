# Worldclass slice 7: a 4 GiB mutation memory cap and a sharded Rust sweep

- **Date:** 2026-11-06
- **Issue:** #217 (run 42157905568)
- **Operator choices:** approach A (shard + evidence) over an exact CI repro first; N = 4 shards for every crate; after round-1 review, bound memory by lowering `ulimit -v` to 4 GiB (option a) rather than bounding the prompt tests' writers (option b). The round-1 design's 25-minute hang deadline and resource sampler are withdrawn (see Rejected alternatives).

## Problem

The monthly Rust sweep (`mutation-testing.yml`, one job per crate since ADR-0040) keeps losing hosted runners with "The hosted runner lost communication with the server ... starves it for CPU/Memory". GitHub keeps no job log for a lost runner (`gh api .../actions/jobs/<id>/logs` returns `BlobNotFound` for 127490109735 and 127696392504).

### When the runner actually dies

The job's wall-clock end (48 to 57 min) is when GitHub _declared_ the loss, about 44 minutes after the runner went silent. Step timestamps (`gh api repos/brujack/math/actions/jobs/<id> --jq '.steps[]'`):

| Job                           | Crate            | `Run mutants` start → end                 | Job declared lost              | Lag                          |
| ----------------------------- | ---------------- | ----------------------------------------- | ------------------------------ | ---------------------------- |
| 127456651743 (42087535763 a1) | pi               | 18:48:11 → `cancelled` 18:59:34 (+11m23s) | 19:44:09                       | 44.6 min                     |
| 127490109735 (42087535763 a2) | pi               | 19:47:46 → `cancelled` 19:58:03 (+10m17s) | 20:42:16                       | 44.2 min                     |
| 127696392504 (42157905568)    | pi               | 03:41:02 → no end                         | 04:37:07                       | (≈ +12 min if the lag holds) |
| 41769558239 a1, three jobs    | collatz, sq, fib | 03:51:35-44 → no end                      | 04:38:36 / 04:38:41 / 04:40:42 | (≈ +3 to +5 min)             |

A healthy pi `Run mutants` takes 14.4 min (job 127456659105). So the runner dies **before** a healthy finish, not after a long hang. fib also lost its runner in 41952665142 a1 (job 127000079226) and 42087540288 a1 (job 127456659937): fib lost in 3 of 5 sweeps, pi in 3.

### What kills it

In a healthy pi run (42087540288), summing `outcomes.json` phase durations in order puts the 10-11 minute mark at mutants #147 `src/main.rs:197:5: replace read_line_from -> io::Result<String> with Ok("xyzzy".into())` (Caught at 42.1 s, the timeout) and #149 `src/main.rs:213:5: replace confirm_large_digits_with -> io::Result<bool> with Ok(false)` (Timeout). Both turn `prompt_digits_with`'s retry `loop` into an endless write into the test's in-memory writer.

Measured on `claude` (4 pinned CPUs, `cargo mutants -F "read_line_from|confirm_large_digits_with"`, 0.2 s per-process sampler), population: pi-rs only, one machine:

| Cap           | Result           | Test harness peak RSS | peak VSZ |
| ------------- | ---------------- | --------------------- | -------- |
| 8 GiB (today) | 4 caught in 60 s | 5,447 MB              | 7,469 MB |
| 4 GiB         | 4 caught in 39 s | 2,721 MB              | 4,069 MB |

So today's cap lets one mutant hold ~5.4 GB resident while it runs to the cap, and in CI (slower cores) it is still growing when the 42 s timeout fires. That is a third of a 16 GB runner in one process, on an image (`ubuntu-latest` → Ubuntu 26.04 from 2026-10-19) whose losses all date from after that migration. This is a strong suspect, not a proven cause: no CI measurement exists of the runner's free memory at that moment. The same prompt-loop shape exists in the other crates' `prompt_*_with` functions, which fits fib, sq and collatz losing runners too.

ADR-0024 (2026-08-01) set the 8 GiB cap after uncapped mutants exhausted the runner; it did not measure how close to the runner's limit a capped mutant gets.

### Headroom for legitimate work under 4 GiB

Every crate built from cold (including `gmp-mpfr-sys` compiling GMP and MPFR) and passed `cargo test --locked` under `ulimit -v 4194304`, each pinned to 4 CPUs (`taskset`) with its own target dir: amicable 16, collatz 26, e 80, factorial 58, fib 51, goldbach 27, perfect-numbers 27, pi 73, prime 69, sq 45, twin-primes 49 tests passed, 0 failed. Population: all 11 crates at origin/master 5b63b4f, one machine. pi's built suite also passed under 1 GiB, so the test half has wide margin; the build half was measured only at 4 GiB.

### #217's misleading body

#217 reads `Cause: verdicts-present` / `Failing crates: (none flagged; see run log)` and then `Cause: missing-status`. `mutation-notify.sh` (lines 197-207) prepends `build_body` whenever the run failed and any status file arrived, even when none of them is red.

## Design

### 1. 4 GiB address-space cap (template)

`scripts/crate_templates/Makefile`'s `MUTANTS_SETUP` changes `ulimit -v 8388608` to `ulimit -v 4194304`, and its error text keeps saying the platform cannot enforce the cap. `mutants` and `mutants-diff` share `MUTANTS_SETUP` (ADR-0024's "one definition of the budget"), so the PR gate gets the same cap. Rendered to all 11 crates. The Python template's 8 GiB cap is unchanged: no Python sweep has lost a runner.

### 2. `MUTANT_SHARD` on the Rust `mutants` target (template)

`mutants` accepts an optional `MUTANT_SHARD=k/n`, the Python template's variable name. When set and well-formed it appends `--shard k/n --sharding slice`. `slice` (cargo-mutants' default, spelled out so a default change cannot move it) keeps consecutive mutants together, so a loss localises to one contiguous range: pi's suspect mutants #146-155 land in one shard instead of 2-3 in every shard under round-robin.
A malformed value (not two non-negative integers, `n < 1`, `k >= n`) prints `error: MUTANT_SHARD must be k/n with 0 <= k < n, got <value>` and exits 1 before `MUTANTS_SETUP`, so no `mutants.out/exit-code` is written and the workflow's missing-exit-code rule reports it red. Unset, the `cargo mutants` argv is unchanged. `mutants-diff` does not take it.

### 3. `mutation-testing.yml`: crate × shard matrix

- `setup` builds `include` entries `{crate, slug, shard}` for every crate and shard `0..3`; `slug` = crate with `/` as `-`, then `-<shard>`. `units` is every slug (44 for a full sweep, 4 for a `crate` input). The count is one `SHARDS=4` assignment, applied to every crate.
- `mutants` job name `Mutation <crate> <shard>/4`; `Run mutants` calls `make -C "${CRATE_DIR}" mutants MUTANT_SHARD="${SHARD}/4" || true`. The rest of the step (exit-code reader, classifier `0 1`, status file) is unchanged.
- A `Runner capacity` step before `Run mutants` prints `nproc` and `free -m`, so every surviving job's log records the runner's real memory. Today nothing records it.

Per-shard `0 1` is safe: `cargo mutants --list --shard k/4` over all 11 crates gives a smallest shard of 5 (amicable), and mapping 42157905568's outcomes onto shards gives every shard at least 4 caught (round-1 Risk lens; to be re-checked for `slice`, V4).

### 4. `mutation-notify.sh` body

When the cause is `verdicts-present` and `render_red_units` returns nothing, the expected-units path does not prepend `build_body`: the `missing-status` body stands alone. With a red unit present the body is unchanged.

### 5. Docs

ADR-0043 "4 GiB mutation cap and sharded Rust sweep" (amends ADR-0024's cap value and ADR-0040 decisions 1, 2 and 5); root `CLAUDE.md` mutation lines; the Backlog runner-loss row rewritten to point here; plan index row.

## Rejected alternatives

- **25-minute hang deadline (`setsid` + `pkill -s`) and a 30 s resource sampler** (round-1 design). The runner dies 3-12 minutes into the step, so a 25-minute deadline never fires; a sampler's file exists only in jobs that survive; and a session kill with a wrong sid can kill the runner itself. Withdrawn.
- **Bound the prompt tests' writers** (option b). Closer to the cause but crate source changes across several crates, and it leaves every other allocation-unbounded mutant at 8 GiB.
- **Round-robin sharding.** Balances cost but scatters a contiguous suspect cluster over every shard.
- **Step-level `timeout-minutes`.** Same defect as the deadline: the runner is gone before it fires.

## Testing

- **Cap:** `tests/scripts/makefile.bats`' existing cap assertions change from `ulimit=8388608` to `ulimit=4194304` for the Rust `mutants` and `mutants-diff` targets (the mock records the cap it ran under); the uniformity check at line 330 asserts `ulimit -v 4194304` in every crate's `MUTANTS_SETUP`. The Python cap assertions keep `8388608`.
- **Shard:** with the PATH-mocked `cargo`, unset `MUTANT_SHARD` gives no `--shard`; `MUTANT_SHARD=2/4` gives `--shard`, `2/4`, `--sharding`, `slice` as separate arguments; `4/4`, `a/4`, `1/0`, `1`, `-1/4` exit 1 with the message, never call `cargo`, and leave no `mutants.out/exit-code`.
- **Workflow:** `tests/test_mutation_workflows.py` runs `setup`'s plan script with a stubbed `git ls-files` and asserts 4 × crates cells, distinct slugs, `units` equal to the slugs, and a `crate` input giving exactly 4 cells; asserts the run step passes `MUTANT_SHARD` and the `Runner capacity` step precedes `Run mutants`.
- **Notify:** `tests/scripts/mutation_notify.bats`: failed run, every arriving status green, one unit missing → body starts `Cause: missing-status` and contains no `verdicts-present`; one red unit present → body as on master.

## Requirements

- **R1.** `[PR1]` Every rendered Rust crate Makefile's `MUTANTS_SETUP` sets `ulimit -v 4194304`, so `make mutants` and `make mutants-diff` run `cargo mutants` under a 4 GiB address-space cap.
- **R2.** `[PR1]` The Python template's mutation cap stays `ulimit -v 8388608`.
- **R3.** `[PR1]` The rendered Rust `make mutants` with `MUTANT_SHARD=k/n` (0 <= k < n, n >= 1) passes `--shard k/n --sharding slice` to `cargo mutants`; without `MUTANT_SHARD` the `cargo mutants` argv is unchanged from master.
- **R4.** `[PR1]` A malformed `MUTANT_SHARD` makes `make mutants` exit 1 with `MUTANT_SHARD must be k/n` on stderr, without running `cargo` and without writing `mutants.out/exit-code`.
- **R5.** `[PR1]` All 11 crate Makefiles are the rendered template (`tests/test_crate_uniformity.py` green).
- **R6.** `[PR1]` `mutation-testing.yml` `setup` emits one matrix cell per crate and shard 0-3 (44 for a full sweep, 4 for a `crate` input), slug `<crate-slug>-<shard>`, and `units` equal to the cell slugs.
- **R7.** `[PR1]` `Run mutants` runs `make -C <crate> mutants MUTANT_SHARD=<shard>/4`, with the exit-code reader and `mutation-classify.sh ... 0 1` unchanged.
- **R8.** `[PR1]` A `Runner capacity` step before `Run mutants` prints `nproc` and `free -m`.
- **R9.** `[PR1]` `mutation-notify.sh` omits the `verdicts-present` prefix when no arriving status is red, so the body starts `Cause: missing-status`; with a red status the body is unchanged from master.
- **R10.** `[PR1]` ADR-0043 records the 4 GiB cap with this spec's measurements, the shard count and `slice` mode, and the withdrawn deadline; ADR-0024's and ADR-0040's status lines name it.
- **R11.** `[PR1]` Root `CLAUDE.md` states the Rust mutation cap is 4 GiB (Python 8 GiB) and that the monthly Rust sweep runs 4 slice shards per crate; it stays under 30,000 bytes.
- **V1.** One full `workflow_dispatch` sweep on the merged master: 44 cells; record each cell's duration and verdict, the `free -m` total from a surviving cell, and any runner loss with its shard's `cargo mutants --list --shard k/4` set.
- **V2.** Three full sweeps (V1 plus two) lose no pi or fib cell. Before this change pi lost in 3 of 5 sweeps and fib in 3 of 5; zero losses in 3 is evidence for the memory cause, not proof.
- **V3.** If a sweep loses a cell, "Re-run failed jobs" recovers it and `notify` closes or comments as for ADR-0040's V2.
- **V4.** Before merge, `cargo mutants --list --shard k/4 --sharding slice` for all 11 crates and every shard has at least one mutant, and mapping 42157905568's outcomes onto those shards gives every shard caught ≥ 1.
- **N1.** No Rust crate gets a different cap, shard count or sharding mode from the others.
- **N2.** `mutation-pr.yml`, `mutants-diff`'s arguments and the Python mutation workflow are unchanged (the cap reaches `mutants-diff` only through the shared `MUTANTS_SETUP`).
- **N3.** No matrix job gains a permission beyond `contents: read`.
- **N4.** `scripts/mutation-classify.sh` and its `0 1` thresholds are unchanged.
- **N5.** No crate source (`src/**/*.rs`) changes.

## Verification records

- V4: Done 2026-11-06 at 5b63b4f. `cargo mutants --list --shard k/4 --sharding slice` in all 11 crates; outcomes mapped from run 42157905568 (9 crates) and 42087540288 (pi, collatz, whose 42157905568 cells uploaded nothing). Smallest shard 5 mutants (amicable, each shard 5/5 caught); smallest caught count 5 (sq shard 2/4, amicable). pi's four `read_line_from` / `confirm_large_digits_with` mutants all fall in shard 3/4.

## Multi-Lens Review

Reviewed at commit: `5b63b4f` (round 1, against the deadline + sampler design)

### Goal-Fit

Finding: Premise false: the runner goes silent 10-11 min into `Run mutants` (jobs 127456651743, 127490109735 `cancelled` at +11m23s / +10m17s) and the 48-57 min figure is GitHub's ~44 min detection lag, so the 25-min deadline cannot fire and the sampler only writes in surviving jobs. Shards and the notify fix pass the reads-it test; deadline and sampler do not. No verification case fails if the deadline never fires on a real loss.
Assumption: The runner stays alive more than 25 min after the problem starts. Refuted by the step timestamps above.
Disposition: Addressed — operator chose to bound memory (option a, 4 GiB cap); deadline and sampler withdrawn.

### Ergonomics

Finding: `mutants.out/log` is a directory, so the hung status's "last log line" would abort under `bash -e` or always read `none`; the deadline bats grandchild case passes if the grandchild never started. Also: the spec table omitted two fib losses (fib lost 3 of 5 sweeps).
Assumption: A re-run after an uploaded `mutants-status-<slug>` does not collide (immutable artifact names, no `overwrite: true`). The deadline would have made upload-then-re-run the normal path; without it, a lost cell still uploads nothing, as today.
Disposition: Addressed — the deadline is withdrawn, which removes the log-line field and the upload-then-re-run path; the fib losses are in the Problem table.

### Risk

Finding: (1) Premise false, as Goal-Fit, with the likely mechanism: pi mutants #147/#149 turn the prompt loop into an endless write up to the 8 GiB cap. (2) Round-robin scatters that contiguous cluster over all four shards. (3) `pkill -s` on a wrong sid can kill the runner itself. (4) `mutants.out/log` is a directory. (5) Exit-code capture under `bash -e` untested. (6) The sampler cannot see a seconds-long spike. (7) Minor: 44 × `cargo install` and cold baselines.
Assumption: The losses are the endless-prompt mutants' memory fill. Local measurement: 5,447 MB RSS / 7,469 MB VSZ at 8 GiB, 2,721 MB / 4,069 MB at 4 GiB; a CI confirmation is V2.
Disposition: Addressed — 4 GiB cap (option a) and `slice` sharding; deadline and sampler withdrawn; (5) still applies to the unchanged `|| true` step and is kept as is; (7) accepted as before (public repo, no minute cost).

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
