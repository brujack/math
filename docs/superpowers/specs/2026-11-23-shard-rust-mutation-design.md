# Shard the Rust mutation runs (per-PR gate and monthly sweep)

- **Status:** Draft
- **Date:** 2026-11-23

## Context

Both Rust mutation runs give one crate one job:

- `mutation-pr.yml` job `mutation-rs` runs `scripts/mutation-pr-run.sh` serially over every
  changed crate's diff-scoped mutants, then the amicable-rs gate canary, then the Python
  baselines, all in one job with `timeout-minutes: 60`.
- `mutation-testing.yml` (monthly, ADR-0040) runs one 60-minute `mutants` job per crate.

zeta PR 3 (math#246) broke the per-PR job. Its diff has 339 mutants
(`cargo mutants --list --json --in-diff`). `mutation-rs` was cancelled at 60 minutes, then at
120 minutes after a raise to 120 (run of 2026-11-24, which also ran the canary because the
raise touched `mutation-pr.yml`). The job writes the run log to a file and prints it only at
the end, so a cancelled run shows no progress at all.

Measured cost per mutant, CI (`ubuntu-latest`, 4 vCPU):

| Population                                           | Mutants                | `Run mutants` time               | s per mutant      | Source                                                                     |
| ---------------------------------------------------- | ---------------------- | -------------------------------- | ----------------- | -------------------------------------------------------------------------- |
| 11 crates, full sweep, run 42328612206 (sha 9313b1a) | 20–166 each, 947 total | 1.0–8.9 min each, 46.1 min total | 1.5–5.0, mean 2.9 | job step timestamps; counts from `cargo mutants --list --json` on that sha |
| zeta-rs PR 3 diff                                    | 339 listed             | more than 120 min (cancelled)    | more than 21      | run of 2026-11-24                                                          |

The zeta figure is a lower bound from a cancelled job on CI, so a zeta shard may run longer than
the 26 minutes estimated in Design 1; V1 and V2 measure it. A local run of the same diff on
`claude` pinned to 4 CPUs (`taskset -c 0-3`) took 4553 s: 313 mutants with outcomes, 234 caught,
55 unviable, 24 timeouts at about 61 s each, 0 missed. That is one machine and one diff; it shows
the timeouts cost about 25 minutes, not what CI costs per mutant. zeta-rs has 748 mutants as a
whole crate, so its first monthly sweep will also exceed a 60-minute job.

The Python PR gate already solved this shape (ADR-0044): a plan job counts the work, emits
units `{dir, k, n}` with `n = min(10, max(1, ceil(K/150)))`, a matrix runs one unit per job
with `MUTANT_SHARD=k/n`, and the aggregator `mutation-pr` stays the required check.

## Decision summary

Shard both Rust runs the way ADR-0044 shards Python, sized by mutant count with one shard size
for every crate, and stream the per-PR run log live. A new ADR records it.

## Design

### 1. Shard size

`n = min(16, max(1, ceil(K / 75)))`, where K is the crate's mutant count from
`cargo mutants --list --json` (for the PR gate, with `--in-diff <crate diff>`). Listing does not
build and took under 1 s for zeta's 339 diff mutants and its 748-mutant crate on `claude`.

75 is set by the slowest crate: at zeta's more than 21 s per mutant, 75 mutants are about
26 minutes, plus about 4 minutes of cargo-mutants install, GMP cache restore and baseline build,
which leaves 2x headroom under a 60-minute job. One value serves every crate, per the
operator's rule that all crates are treated identically; the cost is extra shards for fast
crates (pi-rs, 166 mutants at 3.1 s, becomes 3 jobs of about 3 minutes). Runner minutes on this
public repository are free. The cap 16 bounds one PR's job fan-out; zeta-rs's 748 mutants need 10.

Shards are assigned round-robin (`--sharding round-robin`): mutant i goes to shard i mod n.
cargo-mutants' default, `slice`, gives each shard a consecutive range, which would put zeta's
24 adjacent timeouts in `verify.rs` into one or two shards.

### 2. Crate Makefile template

`scripts/crate_templates/Makefile`'s `mutants` and `mutants-diff` targets accept an optional
`MUTANT_SHARD=k/n`. Empty or unset runs unsharded, exactly as today. A set value must be two
decimal integers `k/n` with `0 <= k < n` and `n >= 1`, the same 0-based convention as
`scripts/cosmic_ray_shard.py`; anything else prints
`error: MUTANT_SHARD must be k/n with 0 <= k < n, got <value>` to stderr and exits 2 before
cargo-mutants runs. A valid value adds `--shard k/n --sharding round-robin` to the
`cargo mutants` command. `--timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle` and
`MUTANTS_SETUP` / `MUTANTS_TAIL` are unchanged. All 13 crates are re-rendered by
`scripts/render_crate_files.py --write`.

### 3. Per-PR gate (`mutation-pr.yml`)

Jobs after the change:

- **`mutation-rs-plan`** (always runs, `timeout-minutes: 30`). Runs `mutation-pr-detect.sh`,
  installs cargo-mutants, and for each changed crate builds its diff with
  `scripts/mutation-pr-diff.sh` and counts K. A new script, `scripts/mutation-rs-plan.sh
<base-ref> <crate-dir>...`, owns this and prints the units JSON
  `[{"crate": <dir>, "slug": <dir with / as ->-<k>of<n>, "k": <k>, "n": <n>}, ...]`, `[]`
  when no crate changed, and one line `plan: <crate> K=<K> n=<n> per-shard=<ceil(K/n)>` per
  crate to stderr. A crate with an empty diff or K = 0 is red (exit 1), as
  `mutation-pr-run.sh` already rules for an empty diff. Outputs: `units`, `has_py`, `py_dirs`,
  `rs_canary`.
- **`mutation-rs`** (`if: units != '[]'`, matrix `include: fromJSON(units)`,
  `fail-fast: false`, `timeout-minutes: 60`). Runs
  `scripts/mutation-pr-run.sh "origin/${GITHUB_BASE_REF}" --shard <k>/<n> <crate>`, which passes
  `MUTANT_SHARD` to `make mutants-diff`. The log streams live:
  `scripts/mutation-pr-run.sh ... 2>&1 | tee "${RUNNER_TEMP}/rs.log"` with
  `rc=${PIPESTATUS[0]}` read on the same line, then the log is appended to
  `GITHUB_STEP_SUMMARY` and the step exits `rc`.
- **`mutation-rs-canary`** (`if: rs_canary == 'true'`, `timeout-minutes: 30`). The existing
  amicable-rs canary step, unchanged and unsharded.
- **`mutation-py-baseline`** (`if: has_py == 'true'`, `timeout-minutes: 30`). The existing
  Python baseline step, moved out of `mutation-rs` unchanged.
- **`mutation-pr`** (aggregator, unchanged name and required-check role). `needs` gains
  `mutation-rs-plan`, `mutation-rs-canary` and `mutation-py-baseline`. Rules: `mutation-rs-plan`
  must be `success`; `mutation-rs` passes on `success`, or on `skipped` only when units is
  `[]`; `mutation-rs-canary` passes on `success`, or on `skipped` only when `rs_canary` is not
  `true`; `mutation-py-baseline` passes on `success`, or on `skipped` only when `has_py` is not
  `true`. `cancelled` and `failure` are always red. The Python rules are unchanged.

`mutation-pr-run.sh` gains `--shard k/n` (same validation as the Makefile, exit 2 on a bad
value) and passes it as `MUTANT_SHARD`; with no `--shard` it behaves exactly as today. Each
shard is classified on its own with the existing rule (limit 0 missed; `--min-caught` only for
the canary).

### 4. Monthly sweep (`mutation-testing.yml`)

- **`setup`** counts each listed crate with `cargo mutants --list --json` (so it installs
  cargo-mutants) and emits one matrix entry per shard:
  `{crate, slug: <crate slug>-<k>of<n>, k, n}`; `units` is the space-joined list of those
  slugs. An unknown `crate` input, an empty crate list and a crate with K = 0 stay red.
- **`mutants`** runs `make -C <crate> mutants MUTANT_SHARD=<k>/<n>` and classifies the shard
  with `mutation-classify.sh ... 0 1` (ADR-0042: any missed is red, caught < 1 is red, timeouts
  green beside a catch). Status and output artifacts are named by the shard slug
  (`mutants-status-<slug>`, `mutants-output-<slug>`); the cancelled-step and upload steps are
  unchanged apart from the slug.
- **`notify`** is unchanged: `EXPECTED_STATUS_UNITS` now holds shard slugs, so a lost shard is
  named.

`mutants-output` has no consumer outside math: ai-config's `mutation-review.yml` downloads only
`mutants-report-python` from `mutation-testing-python.yml`, so per-shard output names break
nothing.

With `n = ceil(K/75)` or fewer shards, every shard holds at least `floor(K/n)` mutants (38 or
more when n > 1), so a shard that catches none is implausible. It is red under `min_caught 1`,
which is the intended reading: a shard that caught nothing measured nothing.

### 5. Sequencing

The change ships as its own PR on `ci/shard-rust-mutation`, with ADR-0046. PR math#246 then
reverts its `mutation-rs` 60 -> 120 commit (26dde61), rebases, and re-runs under the sharded
gate. The Backlog row "zeta monthly mutation sweep budget" is deleted in the CI PR.

### 6. Testing

Root unittest (`tests/test_mutation_workflows.py`) pins the new job graph, `if:` conditions,
timeouts and aggregator rules, and replaces the `mutation-pr-former-job.yml` fixture
comparison with per-job assertions. BATS covers `mutation-rs-plan.sh` (units for 0, 1 and
several crates; K = 75, 76 and 1201 giving n = 1, 2 and 16; empty diff red), `mutation-pr-run.sh
--shard` (valid value reaches `MUTANT_SHARD`, malformed values exit 2, absent flag unchanged),
and the Makefile `MUTANT_SHARD` validation and flag mapping in `tests/scripts/makefile.bats`.

## Requirements

- **R1.** `scripts/crate_templates/Makefile`'s `mutants` and `mutants-diff` recipes accept an optional `MUTANT_SHARD`: unset or empty runs `cargo mutants` with no `--shard`; a value of two decimal integers `k/n` with `0 <= k < n` adds `--shard k/n --sharding round-robin`; any other value prints `error: MUTANT_SHARD must be k/n with 0 <= k < n, got <value>` to stderr and exits 2 without running `cargo mutants`.
- **R2.** Every tracked `*/*-rs/Makefile` equals its render from `scripts/crate_templates/Makefile` after R1 (`tests/test_crate_uniformity.py` passes).
- **R3.** `scripts/mutation-rs-plan.sh <base-ref> <crate-dir>...` prints to stdout a JSON array with one object `{"crate", "slug", "k", "n"}` per shard of each crate, where `n = min(16, max(1, ceil(K/75)))`, K is the count of `cargo mutants --list --json --in-diff <crate diff>`, k runs 0..n-1, and slug is the crate dir with `/` replaced by `-` followed by `-<k>of<n>`; it prints `[]` when given no crate, prints `plan: <crate> K=<K> n=<n> per-shard=<ceil(K/n)>` to stderr per crate, and exits 1 for a crate whose diff is empty or whose K is 0.
- **R4.** `scripts/mutation-pr-run.sh` accepts `--shard k/n` (validated as in R1, exit 2 otherwise) and passes it to `make mutants-diff` as `MUTANT_SHARD`; without `--shard` it passes no `MUTANT_SHARD`.
- **R5.** `mutation-pr.yml` has jobs `mutation-rs-plan` (no `if:`, `timeout-minutes: 30`, outputs `units`, `has_py`, `py_dirs`, `rs_canary`), `mutation-rs` (`if: needs.mutation-rs-plan.outputs.units != '[]'`, matrix `include` from `units`, `fail-fast: false`, `timeout-minutes: 60`), `mutation-rs-canary` (`if:` on `rs_canary == 'true'`, `timeout-minutes: 30`) and `mutation-py-baseline` (`if:` on `has_py == 'true'`, `timeout-minutes: 30`).
- **R6.** The `mutation-rs` run step pipes `scripts/mutation-pr-run.sh "origin/${GITHUB_BASE_REF}" --shard "<k>/<n>" "<crate>"` through `tee "${RUNNER_TEMP}/rs.log"`, reads `PIPESTATUS[0]` in the same command line, appends the log to `GITHUB_STEP_SUMMARY`, and exits with the script's status.
- **R7.** The `mutation-pr` aggregator keeps its job id and `if: always()`, needs every Python and Rust job, and is red unless `mutation-rs-plan` is `success`; `mutation-rs` is `success` or (`skipped` and units is `[]`); `mutation-rs-canary` is `success` or (`skipped` and `rs_canary` is not `true`); `mutation-py-baseline` is `success` or (`skipped` and `has_py` is not `true`); `cancelled` and `failure` of any needed job are red.
- **R8.** `mutation-testing.yml` `setup` emits one matrix entry `{crate, slug, k, n}` per shard with n and slug as in R3 (K from `cargo mutants --list --json` on the whole crate), sets `units` to the space-joined shard slugs, and exits 1 on an unknown `crate` input, an empty crate list or a crate with K = 0.
- **R9.** `mutation-testing.yml` `mutants` runs `make -C <crate> mutants MUTANT_SHARD=<k>/<n>`, classifies with `mutation-classify.sh <rc> <crate>/mutants.out/outcomes.json <crate> 0 1`, and names its artifacts `mutants-status-<slug>` and `mutants-output-<slug>` with the shard slug.
- **R10.** `docs/adr/0046-shard-the-rust-mutation-runs.md` records the shard formula, round-robin assignment, the measurements in this spec, and the job graphs of R5 and R8, and `docs/adr/README.md` lists it.
- **R11.** The `docs/superpowers/README.md` Backlog row named `zeta monthly mutation sweep budget` is removed and the plan index carries this spec's plan.

- **V1.** Dispatch `mutation-testing.yml` on the CI branch with no `crate` input: every shard job finishes under 60 minutes and the run's `notify` closes or does not open the tracking issue; record per-crate shard counts and the longest shard time.
- **V2.** After the CI PR merges, re-run math#246 (with 26dde61 reverted): `mutation-pr` is green and every `mutation-rs` shard finishes under 60 minutes; record shard count and the longest shard time.
- **V3.** A `mutation-rs` shard log is visible in the job's live log while the step runs (open the running job in the Actions UI and see cargo-mutants progress lines before the step ends).

- **N1.** No change to `--timeout-multiplier 5 --minimum-test-timeout 30` and no fixed `--timeout` anywhere (#95).
- **N2.** No change to the classification rules of `mutation-classify.sh` (limit 0 missed; `min_caught 1` in the sweep; timeouts green beside a catch) or to the Python units, `mutation-py`, `mutation-py-canary` or their aggregator rules.
- **N3.** The required status check stays the job id `mutation-pr`; branch protection is not edited.
- **N4.** No per-crate shard-size override: one formula for every crate.
