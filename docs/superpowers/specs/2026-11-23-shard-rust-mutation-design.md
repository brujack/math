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
(`cargo mutants --list --json --in-diff`). `mutation-rs` was cancelled at 60 minutes (run
45291587213), then at 120 minutes after a raise to 120 (run 45309470730; its canary step was
skipped, so the 117.6 minutes of the Rust step were zeta alone). The job writes the run log to a
file and prints it only at the end, so a cancelled run shows no progress at all.

### What drives the cost

cargo-mutants runs the crate's test suite once per mutant and times a mutant out at 5x the
baseline test time (minimum 30 s). The cost per mutant therefore follows the crate's baseline
test time, not its mutant count.

| Population                                           | Mutants                | Baseline test                        | s per mutant      | Source                                                                               |
| ---------------------------------------------------- | ---------------------- | ------------------------------------ | ----------------- | ------------------------------------------------------------------------------------ |
| 11 crates, full sweep, run 42328612206 (sha 9313b1a) | 20–166 each, 947 total | not recorded                         | 1.5–5.0, mean 2.9 | `Run mutants` step timestamps; counts from `cargo mutants --list --json` on that sha |
| zeta-rs, earlier PR runs 45126222244 and 45232851299 | 309 and 132            | 2 s                                  | 3.3 and 2.7       | `N mutants tested in Mm` and `Unmutated baseline` log lines                          |
| zeta-rs PR 3 diff, CI, run 45309470730               | 339 listed             | not printed (cancelled)              | more than 20.8    | step ran 117.6 min and was cancelled                                                 |
| zeta-rs PR 3 diff, `claude` pinned to 4 CPUs         | 313 with outcomes      | 12.1 s (`cargo test -- --skip e2e_`) | 14.5              | 4553 s; 234 caught, 55 unviable, 24 timeouts at about 61 s, 0 missed                 |

PR 3 raised zeta's unit-suite time about 6x (2 s to 12–15 s; CI nextest ran all 400 tests in
15.1 s, run 45309470687), and the per-mutant cost rose with it. The CI figure for PR 3 is a lower
bound from a cancelled job. zeta-rs has 748 mutants as a whole crate at PR 3, so its first
monthly sweep after PR 3 will also exceed a 60-minute job.

Trimming zeta's slowest tests does not avoid sharding: its twelve slowest unit tests sum to
about 23 s of about 44 s CPU, and even a halved suite leaves the 748-mutant sweep near
125 minutes. `cargo mutants --jobs` does not help on a 4-vCPU runner whose test suite already
uses every thread.

The Python PR gate already solved this shape (ADR-0044): a plan job counts the work, emits
units `{dir, k, n}` with `n = min(10, max(1, ceil(K/150)))`, a matrix runs one unit per job
with `MUTANT_SHARD=k/n`, and the aggregator `mutation-pr` stays the required check.

## Decision summary

Shard both Rust runs the way ADR-0044 shards Python, sized by mutant count with one shard size
for every crate, stream the per-PR run log live, and print each shard's baseline test time and
a one-shard repro. A new ADR records it.

## Design

### 1. Shard size

`n = min(16, max(1, ceil(K / 75)))`, where K is the crate's mutant count from
`cargo mutants --list --json` (for the PR gate, with `--in-diff <crate diff>`). Listing does not
build: 0.23 s for zeta's 339 diff mutants.

75 is set by the slowest measured case, the zeta PR 3 diff: at 21–30 s per mutant, 68–75
mutants take 24–38 minutes, plus about 4 minutes of install, GMP cache restore and baseline
build, under a 60-minute job. It is tuned to a baseline test time of about 15 s; a crate whose
suite grows well past that will need a smaller B, and the first sign is the baseline line each
shard prints (Design 3), before any cancel. One value serves every crate, per the operator's
rule that all crates are treated identically; the cost is extra shards for fast crates (pi-rs,
166 mutants at 3.1 s, becomes 3 jobs of about 3 minutes). Runner minutes on this public
repository are free. The cap 16 bounds one PR's job fan-out; zeta-rs's 748 mutants need 10.

Shards are assigned round-robin (`--sharding round-robin`): mutant i goes to shard i mod n.
cargo-mutants' default, `slice`, gives each shard a consecutive range, which would put zeta's
24 adjacent timeouts in `verify.rs` into one or two shards. Measured with cargo-mutants 27.1.0:
the shard filter applies after `--in-diff` (339 diff mutants split 68/68/68/68/67 over 5
shards), and the 10 whole-crate shards of zeta on master (432 mutants, 44/44/43 x 8) union to
exactly the unsharded list.

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
  installs cargo-mutants 27.1.0 with the repo's pinned `taiki-e/install-action` (prebuilt,
  `fallback: none`), and runs a new script, `scripts/mutation-rs-plan.sh <base-ref>
<crate-dir>...`. For each crate it builds the diff with `scripts/mutation-pr-diff.sh` and
  counts K with `cargo mutants --list --json --in-diff`. It prints the units JSON
  `[{"crate": <dir>, "slug": <dir with / as ->-<k>of<n>, "k": <k>, "n": <n>}, ...]` to stdout
  and one line `plan: <crate> K=<K> n=<n> per-shard=<ceil(K/n)>` per crate to stderr.
  - A crate with an empty diff is red (exit 1), as `mutation-pr-run.sh` rules today.
  - A crate with K = 0 contributes no unit and prints `plan: <crate> K=0 (no mutants on
changed lines)`; this keeps a test-only or comment-only `src/` change green, as it is
    today (`cargo mutants --in-diff` exits 0 with no `mutants.out`, classified
    `green: no mutants to test`). `--list --json` prints nothing on stdout when there are no
    mutants, so empty stdout with exit 0 is K = 0; a non-zero exit or stdout that is not a
    JSON array is red.
  - No crate, or every crate at K = 0, prints `[]`.

  Outputs: `units`, `has_py`, `py_dirs`, `rs_canary`.

- **`mutation-rs`** (`if: units != '[]'`, `name: mutation-rs ${{ matrix.slug }}`, matrix
  `include: fromJSON(units)`, `fail-fast: false`, `timeout-minutes: 60`). Installs
  cargo-mutants the same way and runs
  `scripts/mutation-pr-run.sh "origin/${GITHUB_BASE_REF}" --shard <k>/<n> --min-caught 1 <crate>`.
  The log streams live with exactly this form, which keeps the script's status with or without
  `pipefail`:

  ```bash
  scripts/mutation-pr-run.sh ... 2>&1 | tee "${RUNNER_TEMP}/rs.log" && rc=0 || rc=${PIPESTATUS[0]}
  ```

  The step then appends the log to `GITHUB_STEP_SUMMARY` and exits `rc`. (`|| true` before
  reading `PIPESTATUS` was measured to yield `rc=0` on a failing script.)

- **`mutation-rs-canary`** (`if: rs_canary == 'true'`, `timeout-minutes: 30`). The existing
  amicable-rs canary step, unchanged and unsharded (`--min-caught 1`).
- **`mutation-py-baseline`** (`if: has_py == 'true'`, `timeout-minutes: 30`). The existing
  Python baseline step, moved out of `mutation-rs` unchanged.
- **`mutation-pr`** (aggregator, unchanged name and required-check role). `needs` gains
  `mutation-rs-plan`, `mutation-rs-canary` and `mutation-py-baseline`. Rules: `mutation-rs-plan`
  must be `success`; `mutation-rs` passes on `success`, or on `skipped` only when units is
  `[]`; `mutation-rs-canary` passes on `success`, or on `skipped` only when `rs_canary` is not
  `true`; `mutation-py-baseline` passes on `success`, or on `skipped` only when `has_py` is not
  `true`. `cancelled` and `failure` are always red. The Python rules are unchanged.

`mutation-pr-run.sh` gains `--shard k/n` (same validation as the Makefile, exit 2 on a bad
value), passed as `MUTANT_SHARD`; with no `--shard` it behaves exactly as today. For every
crate it runs it prints, before `make`:
`repro: d=$(mktemp) && scripts/mutation-pr-diff.sh <base-ref> <crate> "$d" && make -C <crate> mutants-diff DIFF="$d"`
followed by ` MUTANT_SHARD=k/n` when sharded, and after the run it prints cargo-mutants'
`Unmutated baseline in ...` line from `<crate>/mutants.out/log/baseline.log` when present.

Every shard classifies with `--min-caught 1`, so a shard whose outcomes hold no caught mutant
is red: an all-unviable shard, or a shard whose mutant set came out empty because the run and
the plan disagreed. The unsharded path keeps today's rule.

A local repro of one shard matches CI only when the local diff matches CI's. CI diffs from
the merge base of the PR's merge commit; if master has moved inside that crate, index k can
select different mutants locally, so the reliable handle for a missed mutant is the name the
classifier prints, not k.

### 4. Monthly sweep (`mutation-testing.yml`)

- **`setup`** installs cargo-mutants 27.1.0 with the pinned `taiki-e/install-action`, counts
  each listed crate with `cargo mutants --list --json`, and emits one matrix entry per shard:
  `{crate, slug: <crate slug>-<k>of<n>, k, n}`; `units` is the space-joined list of those
  slugs. An unknown `crate` input, an empty crate list and a crate with K = 0 stay red (a whole
  crate with no mutants means the listing failed).
- **`mutants`** (`name: Mutation ${{ matrix.slug }}`) runs
  `make -C <crate> mutants MUTANT_SHARD=<k>/<n>` and classifies the shard with
  `mutation-classify.sh ... 0 1` (ADR-0042: any missed is red, caught < 1 is red, timeouts
  green beside a catch). Status and output artifacts are named by the shard slug
  (`mutants-status-<slug>`, `mutants-output-<slug>`); the cancelled-step and upload steps are
  unchanged apart from the slug.
- **`notify`** is unchanged: `EXPECTED_STATUS_UNITS` now holds shard slugs, so a lost shard is
  named.

`mutants-output` has no consumer outside math: ai-config's `mutation-review.yml` downloads only
`mutants-report-python` from `mutation-testing-python.yml`, so per-shard output names break
nothing.

### 5. Sequencing

The change ships as its own PR on `ci/shard-rust-mutation`, with ADR-0046. PR math#246 then
reverts its `mutation-rs` 60 -> 120 commit (26dde61), rebases, and re-runs under the sharded
gate; that run is V2, the first CI measurement of a PR 3 shard. If a shard there runs past
about 50 minutes, B is lowered in a follow-up PR before #246 merges. The Backlog row
"zeta monthly mutation sweep budget" is deleted in the CI PR.

### 6. Testing

Root unittest (`tests/test_mutation_workflows.py`) pins the new job graph, `if:` conditions,
`name:` templates, timeouts, the install step and the aggregator rules, and replaces the
`mutation-pr-former-job.yml` fixture comparison with per-job assertions. BATS covers:

- `mutation-rs-plan.sh`: units for 0, 1 and several crates; K = 1, 75, 76 and 1201 giving
  n = 1, 1, 2 and 16; K = 0 (empty `--list` stdout) giving no unit and exit 0; an empty diff
  red; a failing or non-JSON `--list` red.
- `mutation-pr-run.sh`: `--shard` reaching `MUTANT_SHARD`; malformed values exit 2; no flag
  unchanged; the repro line with and without the shard; a shard with zero caught red under
  `--min-caught 1`.
- The live-log form: a stub script exiting 1 through the R6 pipeline yields `rc=1` both with
  and without `set -o pipefail`.
- `tests/scripts/makefile.bats`: the `MUTANT_SHARD` validation and flag mapping.

## Requirements

- **R1.** `scripts/crate_templates/Makefile`'s `mutants` and `mutants-diff` recipes accept an optional `MUTANT_SHARD`: unset or empty runs `cargo mutants` with no `--shard`; a value of two decimal integers `k/n` with `0 <= k < n` adds `--shard k/n --sharding round-robin`; any other value prints `error: MUTANT_SHARD must be k/n with 0 <= k < n, got <value>` to stderr and exits 2 without running `cargo mutants`.
- **R2.** Every tracked `*/*-rs/Makefile` equals its render from `scripts/crate_templates/Makefile` after R1 (`tests/test_crate_uniformity.py` passes).
- **R3.** `scripts/mutation-rs-plan.sh <base-ref> <crate-dir>...` prints to stdout a JSON array with one object `{"crate", "slug", "k", "n"}` per shard of each crate with K > 0, where `n = min(16, max(1, ceil(K/75)))`, K is the length of the JSON array `cargo mutants --list --json --in-diff <crate diff>` prints (empty stdout with exit 0 counts as K = 0), k runs 0..n-1, and slug is the crate dir with `/` replaced by `-` followed by `-<k>of<n>`; per crate it prints `plan: <crate> K=<K> n=<n> per-shard=<ceil(K/n)>` to stderr, or `plan: <crate> K=0 (no mutants on changed lines)` and no unit when K = 0; it prints `[]` when no crate has K > 0; it exits 1 for a crate whose diff is empty, whose `--list` exits non-zero, or whose `--list` stdout is non-empty and not a JSON array.
- **R4.** `scripts/mutation-pr-run.sh` accepts `--shard k/n` (validated as in R1, exit 2 otherwise) and passes it to `make mutants-diff` as `MUTANT_SHARD`, and without `--shard` passes no `MUTANT_SHARD`; for each crate it prints `repro: d=$(mktemp) && scripts/mutation-pr-diff.sh <base-ref> <crate> "$d" && make -C <crate> mutants-diff DIFF="$d"` (with ` MUTANT_SHARD=k/n` appended when sharded) before running, and after running prints the `Unmutated baseline` line of `<crate>/mutants.out/log/baseline.log` when that file exists.
- **R5.** `mutation-pr.yml` has jobs `mutation-rs-plan` (no `if:`, `timeout-minutes: 30`, outputs `units`, `has_py`, `py_dirs`, `rs_canary`), `mutation-rs` (`if: needs.mutation-rs-plan.outputs.units != '[]'`, `name: mutation-rs ${{ matrix.slug }}`, matrix `include` from `units`, `fail-fast: false`, `timeout-minutes: 60`), `mutation-rs-canary` (`if:` on `rs_canary == 'true'`, `timeout-minutes: 30`) and `mutation-py-baseline` (`if:` on `has_py == 'true'`, `timeout-minutes: 30`); `mutation-rs-plan`, `mutation-rs` and `mutation-rs-canary` install cargo-mutants with `taiki-e/install-action` pinned to a 40-hex SHA, `tool: cargo-mutants@27.1.0`, `fallback: none`.
- **R6.** The `mutation-rs` run step is `scripts/mutation-pr-run.sh "origin/${GITHUB_BASE_REF}" --shard "<k>/<n>" --min-caught 1 "<crate>" 2>&1 | tee "${RUNNER_TEMP}/rs.log" && rc=0 || rc=${PIPESTATUS[0]}`, followed by appending the log to `GITHUB_STEP_SUMMARY` and `exit "${rc}"`.
- **R7.** The `mutation-pr` aggregator keeps its job id and `if: always()`, needs every Python and Rust job, and is red unless `mutation-rs-plan` is `success`; `mutation-rs` is `success` or (`skipped` and units is `[]`); `mutation-rs-canary` is `success` or (`skipped` and `rs_canary` is not `true`); `mutation-py-baseline` is `success` or (`skipped` and `has_py` is not `true`); `cancelled` and `failure` of any needed job are red.
- **R8.** `mutation-testing.yml` `setup` installs cargo-mutants as in R5, emits one matrix entry `{crate, slug, k, n}` per shard with n and slug as in R3 (K from `cargo mutants --list --json` on the whole crate), sets `units` to the space-joined shard slugs, and exits 1 on an unknown `crate` input, an empty crate list, or a crate whose K is 0 or whose `--list` fails.
- **R9.** `mutation-testing.yml` `mutants` has `name: Mutation ${{ matrix.slug }}`, runs `make -C <crate> mutants MUTANT_SHARD=<k>/<n>`, classifies with `mutation-classify.sh <rc> <crate>/mutants.out/outcomes.json <crate> 0 1`, and names its artifacts `mutants-status-<slug>` and `mutants-output-<slug>` with the shard slug.
- **R10.** `docs/adr/0046-shard-the-rust-mutation-runs.md` records the shard formula, round-robin assignment, baseline test time as the cost driver, the measurements in this spec, and the job graphs of R5 and R8, and `docs/adr/README.md` lists it.
- **R11.** Root `CLAUDE.md`'s Rust mutation lines describe the sharded `mutation-rs` (plan job, shard matrix, `--min-caught 1` per shard) and the sweep's one job per shard, and its repro line reads `d=$(mktemp) && scripts/mutation-pr-diff.sh origin/master <crate> "$d" && make -C <crate> mutants-diff DIFF="$d" MUTANT_SHARD=<k>/<n>`.
- **R12.** The `docs/superpowers/README.md` Backlog row named `zeta monthly mutation sweep budget` is removed and the plan index carries this spec's plan.

- **V1.** Dispatch `mutation-testing.yml` on the CI branch with no `crate` input: every shard job finishes under 60 minutes and the run's `notify` closes or does not open the tracking issue; record per-crate shard counts, each zeta shard's baseline test time, and the longest shard time.
- **V2.** After the CI PR merges, re-run math#246 (with 26dde61 reverted): `mutation-pr` is green and every `mutation-rs` shard finishes under 60 minutes; record shard count, the baseline test time, mutants tested per shard, and the longest shard time.
- **V3.** A `mutation-rs` shard log is visible in the job's live log while the step runs (open the running job in the Actions UI and see cargo-mutants progress lines before the step ends).

- **N1.** No change to `--timeout-multiplier 5 --minimum-test-timeout 30` and no fixed `--timeout` anywhere (#95).
- **N2.** No change to `scripts/mutation-classify.sh` (its rules stay: limit 0 missed, `min_caught` only when a caller passes it, timeouts green beside a catch), and no change to the Python units, `mutation-py`, `mutation-py-canary` or their aggregator rules; passing `--min-caught 1` for each PR shard is a caller argument, not a classifier change.
- **N3.** The required status check stays the job id `mutation-pr`; branch protection is not edited.
- **N4.** No per-crate shard-size override: one formula for every crate.

## Multi-Lens Review

Reviewed at commit: `bfedc33` (Step 7 self-review commit, before Step 8 dispatch). Round 1
findings are history; the body above is the revision that answers them.

### Goal-Fit

Finding: Worth building; simpler paths (trimming zeta's slow tests, `--jobs`) fall short. Load-bearing framing flaw: the cost driver is the crate's baseline test time (zeta's unit suite rose about 6x in PR 3), not its mutant count, so B = 75 is tuned to one diff's suite speed and later suite growth eats the headroom silently. Factual error: run 45309470730 skipped the canary; the 117.6 min were zeta alone. Verdict count: a PR shard that tests zero mutants passes. Reads-it: the `plan:` line is cheap decoration; the live log fixes the stated pain.
Assumption: a zeta PR 3 shard of 68 mutants fits under 60 min on CI (true CI cost 21–30 s per mutant, not 45 s or more); confirmed or refuted by the baseline line and `N mutants tested in Mm` of one sharded CI run (V2).
Disposition:

### Ergonomics

Finding: A red shard had no repro path and no readable leg name (matrix tuple as name); the CLAUDE.md repro line reruns the whole diff (4553 s for zeta). A PR shard that ran nothing classified green (4-argument classify). cargo-mutants would build from source twice on the critical path; the pinned `taiki-e/install-action` prebuilt is the repo's pattern. Caveat: a local shard index can select different mutants than CI when master moved.
Assumption: zeta on CI costs no more than about 40 s per mutant, so 75 mutants plus setup fit in 60 min; settle with one timed CI shard.
Disposition:

### Risk

Finding: K = 0 red would turn routine test-only and comment-only `src/` PRs red with no fix (today they are green: `no mutants to test`); the spec's claim that `mutation-pr-run.sh` already rules K = 0 red was false. `--list --json` prints nothing, not `[]`, at K = 0. Under `pipefail`, `| tee ... || true; rc=${PIPESTATUS[0]}` gives a false green (measured); only `&& rc=0 || rc=${PIPESTATUS[0]}` keeps the status. Shard mechanics verified: sharding applies after `--in-diff`, and whole-crate shards partition the list exactly.
Assumption: CI's real zeta cost per mutant is at most about 40 s; one 75-mutant zeta shard on CI (or V2) settles it.
Disposition:

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
