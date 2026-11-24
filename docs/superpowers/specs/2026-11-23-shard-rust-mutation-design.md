# Shard the Rust mutation runs (per-PR gate and monthly sweep)

- **Status:** Approved
- **Date:** 2026-11-23
- **Approved:** 2026-11-24

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
| zeta-rs earlier PR 3 diff, `claude`, 4 CPUs          | 313 with outcomes      | 12.1 s (`cargo test -- --skip e2e_`) | 14.5              | 4553 s; 234 caught, 55 unviable, 24 timeouts at about 61 s, 0 missed                 |

PR 3 raised zeta's unit-suite time about 6x (2 s to 12–15 s; CI nextest ran all 400 tests in
15.1 s, run 45309470687), and the per-mutant cost rose with it. The CI figure for PR 3 is a lower
bound from a cancelled job. The local row is an earlier state of the PR 3 branch (313 mutants
against the final 339); its 14.5 s per mutant is the only full-run figure for the PR 3 suite. At
26dde61 the 13 crates hold 2537 mutants as whole crates, the largest being descartes-rs (831,
suite about 3 s on 4 CPUs) and zeta-rs (748); the 947-mutant sweep row predates descartes-rs
and zeta-rs. zeta-rs has 748 mutants as a whole crate at PR 3, so its first
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
for every crate. One plan script serves both runs. Stream the per-PR run log live, with a progress line per
mutant. After each shard runs, check that it tested the mutant count the plan assigned it. A
new ADR records it.

## Design

### 1. Shard size

`n = max(1, ceil(K / 75))`, where K is the crate's mutant count from
`cargo mutants --list --json` (for the PR gate, with `--in-diff <crate diff>`). Listing does not
build: 0.23 s for zeta's 339 diff mutants.

75 is set by the slowest measured case, the zeta PR 3 diff. At 21–30 s per mutant, 68–75
mutants take 24–38 minutes. Add about 4 minutes of prebuilt install, GMP cache restore and
baseline build (both runs' shard jobs restore the GMP cache and install cargo-mutants prebuilt;
a cold zeta `cargo build --tests` took 108.6 s on 4 CPUs), and a shard fits a 60-minute job.
The sweep, not the PR, is the binding case: zeta's 748 whole-crate mutants make shards of 75
and 74, against 68 for the PR 3 diff, so V1 measures it first. That B is tuned to a baseline test time of about 15 s, and 30 s per mutant is
an estimate, not a measurement: the CI figure is a lower bound from a cancelled job. Above about
42 s per mutant a 75-mutant shard cancels at 60 minutes. That failure is loud (a cancelled leg
is red), and V2 is the first CI measurement. One value serves every
crate, per the operator's rule that all crates are treated identically. The cost is extra
shards for fast crates: descartes-rs, 831 mutants with a 3 s suite, becomes 12 jobs of a few
minutes each. Runner
minutes on this public repository are free.

There is no per-crate cap. A cap on n is a mutant count, while the budget is time, and a
per-crate cap of 16 x B would fault a large fast crate (descartes-rs) and shrink whenever B is
lowered. The only limit is GitHub's 256-job matrix: the plan fails when the sum of n over all
emitted units exceeds 256, printing
`error: plan needs <T> shards, over the 256-job matrix limit (ADR-0046)`. At 26dde61 the whole
sweep plans 41 shards.

Shards are assigned round-robin (`--sharding round-robin`): mutant i goes to shard i mod n, so
shard k holds `ceil((K - k) / n)` mutants. cargo-mutants' default, `slice`, gives each shard a
consecutive range, which would put zeta's 24 adjacent timeouts in `verify.rs` into one or two
shards. Measured with cargo-mutants 27.1.0: the shard filter applies after `--in-diff` (339 diff
mutants split 68/68/68/68/67 over 5 shards), and the 10 whole-crate shards of zeta on master
(432 mutants, 44/44/43 x 8) union to exactly the unsharded list. A shard that selects nothing
lists `[]`.

### 2. Crate Makefile template

`scripts/crate_templates/Makefile`'s `mutants` and `mutants-diff` targets accept an optional
`MUTANT_SHARD=k/n`. Empty or unset runs unsharded, exactly as today. A set value must be two
decimal integers `k/n` with `0 <= k < n` and `n >= 1`, the same 0-based convention as
`scripts/cosmic_ray_shard.py`. Anything else prints
`error: MUTANT_SHARD must be k/n with 0 <= k < n, got <value>` to stderr and exits 2 before
cargo-mutants runs. A valid value adds `--shard k/n --sharding round-robin` to the
`cargo mutants` command.

Both targets also gain `--caught --unviable`. Without them, cargo-mutants 27.1.0 on a non-tty
prints only `Found N mutants`, the baseline line, and TIMEOUT and MISSED lines (measured), so a
green shard streams about two lines in 30 minutes. With them, every mutant prints one line as it
finishes. `--timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle` and `MUTANTS_SETUP` /
`MUTANTS_TAIL` are unchanged. All 13 crates are re-rendered by
`scripts/render_crate_files.py --write`.

### 3. Per-PR gate (`mutation-pr.yml`)

Jobs after the change:

- **`mutation-rs-plan`** (always runs, `timeout-minutes: 30`). Runs `mutation-pr-detect.sh`,
  installs cargo-mutants 27.1.0 with the repo's pinned `taiki-e/install-action` (prebuilt,
  `fallback: none`), and runs a new script, `scripts/mutation-rs-plan.sh <base-ref>
<crate-dir>...`. For each crate it builds the diff with `scripts/mutation-pr-diff.sh` and
  counts K with `cargo mutants --list --json --in-diff`. It prints the units JSON
  `[{"crate": <dir>, "slug": <basename of dir>-<k>, "k": <k>, "n": <n>, "count": <ceil((K-k)/n)>}, ...]`
  to stdout, and one line `plan: <crate> K=<K> n=<n> per-shard=<ceil(K/n)>` per crate to stderr.
  The same script, called as `scripts/mutation-rs-plan.sh --whole <crate-dir>...`, plans the
  monthly sweep (Design 4). The n formula, k range, slug and count exist in one place.
  - A crate with an empty diff is red (exit 1), as `mutation-pr-run.sh` rules today.
  - A crate with K = 0 contributes no unit and prints
    `plan: <crate> K=0 (no mutants on changed lines)`. This keeps a test-only or comment-only
    `src/` change green, as it is today: `cargo mutants --in-diff` exits 0 with no
    `mutants.out`, classified `green: no mutants to test`. `--list --json` prints nothing on
    stdout when there are no mutants, so empty stdout with exit 0 is K = 0. A non-zero exit,
    or stdout that is not a JSON array, is red.
  - A plan whose shards sum past 256 is red (Design 1).
  - No crate, or every crate at K = 0, prints `[]`.

  Outputs: `units`, `rs_canary`.

- **`mutation-rs`** (`if: units != '[]'`, `name: mutation-rs ${{ matrix.slug }}`, matrix
  `include: fromJSON(units)`, `fail-fast: false`, `timeout-minutes: 60`). It installs
  cargo-mutants the same way and runs
  `scripts/mutation-pr-run.sh "origin/${GITHUB_BASE_REF}" --shard <k>/<n> --expect <count> <crate>`.
  The step streams the log live with exactly this form:

  ```bash
  set +e
  scripts/mutation-pr-run.sh ... 2>&1 | tee "${RUNNER_TEMP}/rs.log"
  rc=${PIPESTATUS[0]}
  set -e
  ```

  It then appends to `GITHUB_STEP_SUMMARY` a fenced block holding only the log lines that match
  `^(red|green|repro):|MISSED|TIMEOUT|^error:`, written as
  `{ grep -E '<pattern>' "${RUNNER_TEMP}/rs.log" || [ $? -eq 1 ]; }` so a no-match filter cannot
  fail the step while a grep error (exit 2) still does, and exits `rc`. The full per-mutant stream stays
  in the live log. A fenced summary keeps a `MISSED` line from being folded into 70 `caught`
  lines. GitHub runs a step with no
  `shell:` as `bash -e {0}`, without pipefail. Measured there:
  `... | tee ... && rc=0 || rc=${PIPESTATUS[0]}` gives `rc=0` on a failing script, and
  `... | tee ... || true; rc=${PIPESTATUS[0]}` gives `rc=0` under pipefail. The `set +e` form
  gives the script's status (`rc=3` from a stub returning 3) with and without pipefail.

- **`mutation-rs-canary`** (`if: rs_canary == 'true'`, `timeout-minutes: 30`). The existing
  amicable-rs canary keeps its one-line edit and commit. It then goes through the plan:
  `scripts/mutation-rs-plan.sh HEAD~1 amicable/amicable-rs` must print exactly one unit. That
  unit runs with `scripts/mutation-pr-run.sh HEAD~1 --shard <k>/<n> --expect <count> --min-caught 1 amicable/amicable-rs`.
  A plan defect that zeroes K therefore turns the canary red. `scripts/mutation-rs-plan.sh` and
  `scripts/mutation-exit-code.sh` and `scripts/mutation-shard-count.sh` join `RS_CANARY_PATHS` in
`scripts/mutation-pr-detect.sh`.
  The second was missing before this change.
- **`mutation-py-baseline`** (`needs: mutation-py-plan`, `if: has_py == 'true'`,
  `timeout-minutes: 30`). The existing Python baseline step, moved out of `mutation-rs`
  unchanged. `mutation-py-plan` gains outputs `has_py` and `py_dirs`, passed through from its
  detect step, so a Rust plan failure cannot skip the Python baseline.
- **`mutation-pr`** (aggregator, unchanged name and required-check role). `needs` gains
  `mutation-rs-plan`, `mutation-rs-canary` and `mutation-py-baseline`. Rules:
  - `mutation-rs-plan` must be `success`.
  - `mutation-rs` passes on `success`, or on `skipped` only when units is `[]`.
  - `mutation-rs-canary` passes on `success`, or on `skipped` only when `rs_canary` is not `true`.
  - `mutation-py-baseline` passes on `success`, or on `skipped` only when `has_py` is not `true`.
  - `cancelled` and `failure` are always red.
  - The Python rules are unchanged.

`mutation-pr-run.sh` gains `--shard k/n` and `--expect N`:

- `--shard` takes the same validation as the Makefile and exits 2 on a bad value. It is passed
  as `MUTANT_SHARD`.
- `--expect N` requires `--shard` and a positive integer N, and exits 2 otherwise. After the
  run and before classifying, it reads `total_mutants` from `<crate>/mutants.out/outcomes.json`.
  A missing file counts as 0. It is red with
  `red: <crate> shard k/n tested <M> mutants, plan expected <N>` when M differs from N. The
  check reads the run that produced the verdict, so no second listing is needed.
- With neither flag it behaves exactly as today.

For every crate it runs, the script prints `repro: scripts/mutation-pr-run.sh <base-ref> <crate>`
before `make`, with ` --shard k/n --expect N` inserted before the crate when sharded. Run locally
against the same diff, that command applies CI's checks. If master has moved inside the crate,
index k can select different mutants locally and `--expect` reports the mismatch, so rebase or
re-run without `--shard`. To confirm a killing test for one missed mutant, run
`cargo mutants --in-diff <diff> -F '<mutant name regex>'` from the crate directory; the root
`CLAUDE.md` repro line says so.

PR shards classify exactly as today's per-PR rule (`mutation-classify.sh` with 4 arguments):
missed limit 0, timeouts green, nothing evaluated red. They do not pass `--min-caught 1`. That
would turn red a small diff whose only changed-line mutants are timeouts, and the change could
not fix it, because `exclude_re` is for equivalents only. Without `--min-caught`, a shard whose
run selected nothing would classify `green: no mutants to test`; `--expect` is the check that
turns it red, so every PR shard and every sweep shard passes it. A plan arithmetic bug that
miscounts reds every multi-shard run while losing no coverage, which fails safe. The canary
keeps `--min-caught 1`.

A `mutation-rs` leg skipped on a PR with no Rust changes may show its name template literally.
The required check is the aggregator, so this is cosmetic.

### 4. Monthly sweep (`mutation-testing.yml`)

- **`setup`** installs cargo-mutants 27.1.0 with the pinned `taiki-e/install-action` and runs
  `scripts/mutation-rs-plan.sh --whole <crate>...`, using the runner's preinstalled cargo
  (listing parses source and needs no particular rustc). `--whole` counts K with
  `cargo mutants --list --json` on the whole crate and emits the same units as the PR mode. A
  crate-level fault (K = 0, which for a whole crate means the listing failed; a failing or
  non-JSON listing) does not fail `setup`: it emits one unit
  `{"crate", "slug": "<basename>-plan", "k": 0, "n": 0, "count": 0, "fault": "<message>"}`, so
  the other crates are still tested that month. `units` is the space-joined list of slugs. An
  unknown `crate` input, an empty crate list and a plan over 256 shards still fail `setup`.
- **`mutants`** (`name: Mutation ${{ matrix.slug }}`). A fault unit prints its `fault` and is
  red without running cargo-mutants, so `notify` names it. Every other unit runs
  `make -C <crate> mutants MUTANT_SHARD=<k>/<n>`, checks `total_mutants` in `outcomes.json`
  against `count` with the same red message as `--expect`, and classifies the shard with
  `mutation-classify.sh ... 0 1` (ADR-0042: any missed is red, caught < 1 is red, timeouts green
  beside a catch). The count check and the PR check are one script,
  `scripts/mutation-shard-count.sh <outcomes.json> <label> <count>`. Status and output artifacts are named by the shard slug
  (`mutants-status-<slug>`, `mutants-output-<slug>`). The cancelled-step and upload steps are
  unchanged apart from the slug.
- **`notify`** is unchanged. `EXPECTED_STATUS_UNITS` now holds shard slugs, so a lost shard is
  named.

`mutants-output` has no consumer outside math: ai-config's `mutation-review.yml` downloads only
`mutants-report-python` from `mutation-testing-python.yml`. Per-shard output names therefore
break nothing.

### 5. Sequencing

The change ships as its own PR on `ci/shard-rust-mutation`, with ADR-0046. ADR-0046 carries a
measurements table that V1 and V2 fill in: per crate, the shard count, the baseline test time
and the longest shard time.

PR math#246 then reverts its `mutation-rs` 60 -> 120 commit (26dde61), rebases, and re-runs
under the sharded gate. That run is V2, the first CI measurement of a PR 3 shard. If a shard
there runs past about 50 minutes, B is lowered in a follow-up PR before #246 merges. V1 has the
same rule: a sweep shard past about 50 minutes lowers B before the CI PR merges. The Backlog row
"zeta monthly mutation sweep budget" exists only on #246's branch, so #246's rebase deletes it;
the CI PR adds only the plan-index row.

V1 dispatches the sweep from the CI branch with no `crate` input, so `notify` runs with
`FULL_SWEEP=true` and closes, comments on or opens the real tracking issue. That is intended:
the run is a full sweep of master's crates under the new workflow.

### 6. Testing

Root unittest (`tests/test_mutation_workflows.py`) pins:
- the new job graph, `if:` conditions, `name:` templates, timeouts and the install step;
- the aggregator rules, the `set +e` live-log lines and the fenced summary filter;
- the sweep `setup` calling `mutation-rs-plan.sh --whole`, and `mutants` failing a fault unit;
- `RS_CANARY_PATHS` containing both new paths.

It replaces the `mutation-pr-former-job.yml` fixture comparison with per-job assertions.

BATS covers:

- `mutation-rs-plan.sh`:
  - units for 0, 1 and several crates;
  - K = 1, 75, 76 and 1201 give n = 1, 1, 2 and 17;
  - units summing to 257 shards are red, 256 are not;
  - K = 339 gives counts 68, 68, 68, 68, 67 summing to K;
  - K = 0 (empty `--list` stdout) gives no unit and exit 0;
  - an empty diff is red;
  - a failing or non-JSON `--list` is red;
  - `--whole` on K = 432 gives k = 0..9 with counts 44, 44, 43 x 8 summing to K;
  - `--whole` with one faulting crate emits its `-plan` fault unit plus the other crates'
    units, and exits 0.
- `mutation-pr-run.sh`:
  - `--shard` reaches `MUTANT_SHARD`, and malformed values exit 2;
  - `--expect` without `--shard`, or with 0, exits 2;
  - an `outcomes.json` whose `total_mutants` equals `--expect` classifies as usual;
  - a different `total_mutants`, or no `outcomes.json`, is red with the message;
  - no flag behaves as before;
  - the repro line with and without the shard;
- `mutation-shard-count.sh`: equal, unequal and missing-file cases.
- The live-log form: the four R6 lines extracted from `mutation-pr.yml` (not retyped), with the
  script replaced by a stub exiting 3, yield `rc=3` under `bash -e`
  and under `bash -eo pipefail`.
- `tests/scripts/makefile.bats`: the `MUTANT_SHARD` validation and flag mapping, and
  `--caught --unviable` on both targets.

The canary is the end-to-end case that pins a non-zero derived value: a real one-line edit must
plan to one unit with a count of at least 1 and must catch at least one mutant.

## Requirements

- **R1.** `scripts/crate_templates/Makefile`'s `mutants` and `mutants-diff` recipes pass `--caught --unviable` to `cargo mutants` and accept an optional `MUTANT_SHARD`: unset or empty runs `cargo mutants` with no `--shard`; a value of two decimal integers `k/n` with `0 <= k < n` adds `--shard k/n --sharding round-robin`; any other value prints `error: MUTANT_SHARD must be k/n with 0 <= k < n, got <value>` to stderr and exits 2 without running `cargo mutants`.
- **R2.** Every tracked `*/*-rs/Makefile` equals its render from `scripts/crate_templates/Makefile` after R1 (`tests/test_crate_uniformity.py` passes).
- **R3.** `scripts/mutation-rs-plan.sh <base-ref> <crate-dir>...` prints to stdout a JSON array with one object `{"crate", "slug", "k", "n", "count"}` per shard of each crate with K > 0, where `n = max(1, ceil(K/75))`, K is the length of the JSON array `cargo mutants --list --json --in-diff <crate diff>` prints (empty stdout with exit 0 counts as K = 0), k runs 0..n-1, `count` is `ceil((K-k)/n)`, and slug is the crate dir's basename followed by `-<k>`; per crate it prints `plan: <crate> K=<K> n=<n> per-shard=<ceil(K/n)>` to stderr, or `plan: <crate> K=0 (no mutants on changed lines)` and no unit when K = 0; it prints `[]` when no crate has K > 0; it exits 1 for a crate whose diff is empty, whose `--list` exits non-zero, whose `--list` stdout is non-empty and not a JSON array, and it exits 1 printing `error: plan needs <T> shards, over the 256-job matrix limit (ADR-0046)` when the units' n sum past 256; with `--whole` first, K is the length of `cargo mutants --list --json` on the whole crate, a crate that is empty-listed or failing to list emits instead one unit `{"crate", "slug": "<basename>-plan", "k": 0, "n": 0, "count": 0, "fault": "<message>"}` and the script exits 0.
- **R4.** `scripts/mutation-pr-run.sh` accepts `--shard k/n` (validated as in R1, exit 2 otherwise), passed to `make mutants-diff` as `MUTANT_SHARD`, and `--expect N` (exit 2 without `--shard` or when N is not a positive integer), which after the run and before classifying calls `scripts/mutation-shard-count.sh <crate>/mutants.out/outcomes.json <crate> N`; `mutation-shard-count.sh` reads `total_mutants` (a missing file is 0) and exits 1 printing `red: <label> tested <M> mutants, plan expected <N>` when M differs from N; with neither flag `mutation-pr-run.sh` passes no `MUTANT_SHARD` and checks no count; for each crate it prints `repro: scripts/mutation-pr-run.sh <base-ref> <crate>` (with ` --shard k/n --expect N` before the crate when sharded) before running.
- **R5.** `mutation-pr.yml` has jobs `mutation-rs-plan` (no `if:`, `timeout-minutes: 30`, outputs `units`, `rs_canary`), `mutation-rs` (`if: needs.mutation-rs-plan.outputs.units != '[]'`, `name: mutation-rs ${{ matrix.slug }}`, matrix `include` from `units`, `fail-fast: false`, `timeout-minutes: 60`), `mutation-rs-canary` (`if:` on `rs_canary == 'true'`, `timeout-minutes: 30`) and `mutation-py-baseline` (`needs: mutation-py-plan`, `if:` on `needs.mutation-py-plan.outputs.has_py == 'true'`, `timeout-minutes: 30`); `mutation-py-plan` gains outputs `has_py` and `py_dirs`; `mutation-rs-plan`, `mutation-rs` and `mutation-rs-canary` install cargo-mutants with `taiki-e/install-action` pinned to a 40-hex SHA, `tool: cargo-mutants@27.1.0`, `fallback: none`, and `mutation-rs` and `mutation-rs-canary` keep today's Rust toolchain step and read-only GMP cache restore (`scripts/gmp-cache-key.sh`).
- **R6.** The `mutation-rs` run step is the four lines `set +e`, `scripts/mutation-pr-run.sh "origin/${GITHUB_BASE_REF}" --shard "<k>/<n>" --expect "<count>" "<crate>" 2>&1 | tee "${RUNNER_TEMP}/rs.log"`, `rc=${PIPESTATUS[0]}`, `set -e`, followed by appending to `GITHUB_STEP_SUMMARY` a fenced block of the log lines matching `^(red|green|repro):|MISSED|TIMEOUT|^error:` and `exit "${rc}"`; it passes no `--min-caught`.
- **R7.** The `mutation-pr` aggregator keeps its job id and `if: always()`, needs every Python and Rust job, and is red unless `mutation-rs-plan` is `success`; `mutation-rs` is `success` or (`skipped` and units is `[]`); `mutation-rs-canary` is `success` or (`skipped` and `rs_canary` is not `true`); `mutation-py-baseline` is `success` or (`skipped` and `has_py` is not `true`); `cancelled` and `failure` of any needed job are red.
- **R8.** `mutation-testing.yml` `setup` installs cargo-mutants as in R5, builds its matrix from the units of `scripts/mutation-rs-plan.sh --whole <crate>...` (R3), sets `units` to the space-joined unit slugs, and exits 1 only on an unknown `crate` input, an empty crate list, or a plan over 256 shards.
- **R9.** `mutation-testing.yml` `mutants` has `name: Mutation ${{ matrix.slug }}`, installs cargo-mutants as in R5 (no `cargo install cargo-mutants`), restores the GMP cache read-only as `mutation-rs` does; for a unit with `fault` it prints the fault and writes a red status without running cargo-mutants; otherwise it runs `make -C <crate> mutants MUTANT_SHARD=<k>/<n>`, is red when `scripts/mutation-shard-count.sh <crate>/mutants.out/outcomes.json <slug> <count>` exits 1, classifies with `mutation-classify.sh <rc> <crate>/mutants.out/outcomes.json <crate> 0 1`, and names its artifacts `mutants-status-<slug>` and `mutants-output-<slug>` with the shard slug.
- **R10.** `docs/adr/0046-shard-the-rust-mutation-runs.md` records the shard formula and cap, round-robin assignment, the post-run count check, baseline test time as the cost driver, the measurements in this spec, a measurements table for V1 and V2, and the job graphs of R5 and R8, and `docs/adr/README.md` lists it.
- **R11.** Root `CLAUDE.md` stays at or under its 30000-byte ceiling with no net byte growth (29991 bytes at b091030): its Rust mutation lines are rewritten to point at `docs/adr/0046-shard-the-rust-mutation-runs.md` for detail, and describe the sharded `mutation-rs` (plan job, shard matrix, `--expect` per shard, `--min-caught 1` on the canary only) and the sweep's one job per shard, and its repro line reads `scripts/mutation-pr-run.sh origin/master [--shard <k>/<n> --expect <count>] <crate>`, with `cargo mutants --in-diff <diff> -F '<regex>'` from the crate directory for one mutant.
- **R12.** `[#246]` The `docs/superpowers/README.md` Backlog row named `zeta monthly mutation sweep budget` is removed in math#246's rebase onto the merged CI PR; the CI PR's `docs/superpowers/README.md` plan index carries this spec's plan.
- **R13.** The `mutation-rs-canary` job runs `scripts/mutation-rs-plan.sh HEAD~1 amicable/amicable-rs` after its one-line commit, is red unless that prints exactly one unit, and runs that unit with `scripts/mutation-pr-run.sh HEAD~1 --shard <k>/<n> --expect <count> --min-caught 1 amicable/amicable-rs`; `RS_CANARY_PATHS` in `scripts/mutation-pr-detect.sh` contains `scripts/mutation-rs-plan.sh`, `scripts/mutation-exit-code.sh` and `scripts/mutation-shard-count.sh`.

- **V1.** Dispatch `mutation-testing.yml` on the CI branch with no `crate` input (its `notify` acts on the real tracking issue, intended): every shard job finishes under 60 minutes, and any shard past about 50 minutes lowers B before the CI PR merges and the run's `notify` closes or does not open the tracking issue; record per-crate shard counts, each zeta shard's baseline test time, and the longest shard time in ADR-0046's measurements table; from the downloaded `mutants-output-<slug>` artifacts, each crate's shard `total_mutants` sum to its K and its shards' mutant names are disjoint.
- **V2.** After the CI PR merges, re-run math#246 (with 26dde61 reverted): `mutation-pr` is green and every `mutation-rs` shard finishes under 60 minutes; record shard count, cargo-mutants' `Unmutated baseline` line, mutants tested per shard, and the longest shard time in ADR-0046's measurements table.
- **V3.** A `mutation-rs` shard log is visible in the job's live log while the step runs: open the running job in the Actions UI and see at least one caught or unviable mutant line before the step ends.

- **N1.** No change to `--timeout-multiplier 5 --minimum-test-timeout 30` and no fixed `--timeout` anywhere (#95).
- **N2.** No change to `scripts/mutation-classify.sh` (its rules stay: limit 0 missed, `min_caught` only when a caller passes it, timeouts green beside a catch), and no change to the Python units, `mutation-py`, `mutation-py-canary` or their aggregator rules.
- **N3.** The required status check stays the job id `mutation-pr`; branch protection is not edited.
- **N4.** No per-crate shard-size override: one formula for every crate.

## Multi-Lens Review

Round 1 reviewed `bfedc33`, round 2 `6523648`, round 3 `130d640`. All rounds' findings are history; the body above is the revision that answers them.

#### Round 1

##### Goal-Fit

Finding: Worth building; simpler paths (trimming zeta's slow tests, `--jobs`) fall short. Load-bearing framing flaw: the cost driver is the crate's baseline test time (zeta's unit suite rose about 6x in PR 3), not its mutant count, so B = 75 is tuned to one diff's suite speed and later suite growth eats the headroom silently. Factual error: run 45309470730 skipped the canary; the 117.6 min were zeta alone. Verdict count: a PR shard that tests zero mutants passes. Reads-it: the `plan:` line is cheap decoration; the live log fixes the stated pain.
Assumption: a zeta PR 3 shard of 68 mutants fits under 60 min on CI (true CI cost 21–30 s per mutant, not 45 s or more); confirmed or refuted by the baseline line and `N mutants tested in Mm` of one sharded CI run (V2).
Disposition: Addressed (operator, 2026-11-24: "Addressed"): cost driver reframed as baseline test time with a per-shard baseline line (R4); canary fact corrected; every PR shard classifies with `--min-caught 1` (R4, R7). Assumption carried as V2.

##### Ergonomics

Finding: A red shard had no repro path and no readable leg name (matrix tuple as name); the CLAUDE.md repro line reruns the whole diff (4553 s for zeta). A PR shard that ran nothing classified green (4-argument classify). cargo-mutants would build from source twice on the critical path; the pinned `taiki-e/install-action` prebuilt is the repo's pattern. Caveat: a local shard index can select different mutants than CI when master moved.
Assumption: zeta on CI costs no more than about 40 s per mutant, so 75 mutants plus setup fit in 60 min; settle with one timed CI shard.
Disposition: Addressed (operator, 2026-11-24: "Addressed"): per-shard leg names (R5), one-shard repro line (R4, R11), `--min-caught 1` per shard, pinned `taiki-e/install-action` prebuilt (R5), local-k caveat in CLAUDE.md (R11). Assumption carried as V2.

##### Risk

Finding: K = 0 red would turn routine test-only and comment-only `src/` PRs red with no fix (today they are green: `no mutants to test`); the spec's claim that `mutation-pr-run.sh` already rules K = 0 red was false. `--list --json` prints nothing, not `[]`, at K = 0. Under `pipefail`, `| tee ... || true; rc=${PIPESTATUS[0]}` gives a false green (measured); only `&& rc=0 || rc=${PIPESTATUS[0]}` keeps the status. Shard mechanics verified: sharding applies after `--in-diff`, and whole-crate shards partition the list exactly.
Assumption: CI's real zeta cost per mutant is at most about 40 s; one 75-mutant zeta shard on CI (or V2) settles it.
Disposition: Addressed (operator, 2026-11-24: "Addressed"): K = 0 adds no unit and stays green (R3, R7); empty `--list` stdout read as K = 0, a failed listing red; live-log form pinned as `&& rc=0 || rc=${PIPESTATUS[0]}` (R6). Assumption carried as V2.

#### Round 2

##### Goal-Fit

Finding: Worth building; the competing path (a 240–360-minute PR job plus `tee`) loses on the sweep, since zeta's 748 whole-crate mutants at 21–30 s each take 262–374 min. Blocker: the R6 form `| tee ... && rc=0 || rc=${PIPESTATUS[0]}` gives `rc=0` on a failing script under GitHub's default `bash -e {0}`, which has no pipefail (measured), and the spec's own test case contradicts it. `--min-caught 1` on every PR shard adds a no-fix red for timeout-only shards; 4-argument classify already reds nothing evaluated. Without `--caught`, cargo-mutants streams almost nothing on a green shard. The baseline "early warning" has no consumer. Cap 16 silently overruns the budget for K > 1200.
Assumption: CI's cost per zeta PR 3 mutant is at most about 30 s, so a 68–75-mutant shard plus setup fits 60 min; settled by V2's shard duration and `N mutants tested in Mm`.
Disposition: Addressed (operator, 2026-11-24: "Approved"): findings answered by the round-2 and round-3 revisions; open cost assumption carried as V1/V2.

##### Ergonomics

Finding: Same R6 false green. The `Unmutated baseline` line is never written to `mutants.out/` (measured: 0 hits under `log/`), so R4's baseline print was a silent no-op; the duration is in `outcomes.json`. `--min-caught 1` per shard reds timeout-only small diffs; the direct check is a count match against the plan. The `make mutants-diff` repro ends with cargo's exit code and no classifier verdict; `mutation-pr-run.sh --shard` is shorter and matches CI. Slugs repeated the crate name and read as off-by-one. The cap is per crate, not per PR. `mutation-py-baseline` hung off the Rust plan, so a Rust install failure skipped Python's baseline.
Assumption: a zeta PR 3 shard of about 68 mutants finishes inside 60 minutes on CI (at most about 40 s per mutant); settled by V2's baseline duration and shard time.
Disposition: Addressed (operator, 2026-11-24: "Approved"): findings answered by the round-2 and round-3 revisions; open cost assumption carried as V1/V2.

##### Risk

Finding: Same R6 false green. `--min-caught 1` changes today's verdict: CI always passes `--shard`, so the "unsharded path keeps today's rule" never applies, and `{caught 0, timeout 1, unviable 2}` goes from green to red; a plan-emitted per-unit count checked by the run is the exact guard. New false-green path: K = 0 adds no unit, so a plan defect that zeroes K turns every Rust PR green, `scripts/mutation-rs-plan.sh` is not in `RS_CANARY_PATHS`, and the unsharded canary bypasses the plan. Minor: sweep `setup` lists with the runner's cargo. Pre-existing: `scripts/mutation-exit-code.sh` is missing from `RS_CANARY_PATHS`.
Assumption: CI's per-mutant cost for a zeta PR 3 shard is at most about 44 s; settled by `Unmutated baseline in` and `N mutants tested in Mm` from one sharded zeta CI run (V2).
Disposition: Addressed (operator, 2026-11-24: "Approved"): findings answered by the round-2 and round-3 revisions; open cost assumption carried as V1/V2.

#### Round 3

##### Goal-Fit

Finding: Worth building; the sweep cannot avoid sharding and the PR gate reuses its shape; the `set +e` form plus `--caught --unviable` fixes the live-log pain. The baseline mechanism (R4) is decoration: its line repeats cargo-mutants' own, and the `::warning` changes no verdict, lands on green checks nothing reads, repeats per shard, never appears on a cancelled shard, and never reaches the sweep. R8 widened the sweep's blast radius: one crate's listing fault or K > 1200 fails `setup`, so no crate is tested that month. The `--expect` rationale overstated it: its real catch is a shard that lists 0 while the plan said N.
Assumption: CI's zeta PR 3 cost per mutant is at most about 44 s; settled by V2's `Unmutated baseline in` and `N mutants tested in Mm` lines per shard.
Disposition: Addressed (operator, 2026-11-24: "Approved"): findings answered by the round-2 and round-3 revisions; open cost assumption carried as V1/V2.

##### Ergonomics

Finding: The printed repro dropped `--expect`, so local drift from CI ran silently on the wrong shard. The `::warning` is likely on every zeta PR from day one (CI baseline plausibly 17–25 s) and fires once per shard. With `--caught --unviable` the step summary floods with about 70 unfenced `caught` lines per shard, burying `MISSED`. No narrow repro for one missed mutant; `cargo mutants -F` belongs in the CLAUDE.md line.
Assumption: zeta's CI per-mutant cost under the PR 3 suite stays below about 48 s; settled by V2 or one dispatched zeta shard.
Disposition: Addressed (operator, 2026-11-24: "Approved"): findings answered by the round-2 and round-3 revisions; open cost assumption carried as V1/V2.

##### Risk

Finding: The sweep's `setup` re-implemented the shard plan inline with no count and no test, so an off-by-one k range drops 1/n of a crate's mutants with every job green and `notify` closing the issue. `--expect` checked a second listing rather than the run; `outcomes.json`'s `total_mutants` measures the run itself and works unchanged in the sweep. B = 75 rests on a CI lower bound and an unsourced 30 s upper figure; the failure is loud and V2 is the backstop.
Assumption: every shard of a crate sees the same full listing, so `--shard k/n` partitions; confirmed in V1 by summing shard `total_mutants` to K and checking mutant names are disjoint.
Disposition: Addressed (operator, 2026-11-24: "Approved"): findings answered by the round-2 and round-3 revisions; open cost assumption carried as V1/V2.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.

## External Review

### Round 1 (reviewed at `b091030`)

Report: [round1.md](2026-11-23-shard-rust-mutation-design.external-review/round1.md)

#### Author response

| finding | disposition | evidence | reviewer verdict | operator (Step 9) |
| ------- | ----------- | -------- | ---------------- | ----------------- |
| F1.1 | Fixed | Per-crate cap and K > 1200 rule removed; `n = max(1, ceil(K/75))`; the plan is red only when its shards sum past 256 (Design 1, R3, R8, Testing). | unjudged | approved 2026-11-24 ("Approved") |
| F1.2 | Fixed | V1 gains the 50-minute lower-B rule; R9 gives sweep shards the prebuilt install and the GMP cache restore; Design 1 names the sweep as the binding case. | unjudged | approved 2026-11-24 ("Approved") |
| F1.3 | Fixed | Confirmed: `git show origin/master:docs/superpowers/README.md \| grep -c 'mutation sweep budget'` is 0. The row's deletion moves to #246's rebase (Design 5, R12). | unjudged | approved 2026-11-24 ("Approved") |
| F1.4 | Fixed | Confirmed: `git show origin/master:CLAUDE.md \| wc -c` is 29991. R11 requires no net byte growth, with detail behind an in-repo pointer to ADR-0046, so no ai-config change is needed. | unjudged | approved 2026-11-24 ("Approved") |
| F1.5 | Fixed | The local row is labelled an earlier PR 3 state (313 against 339) in the table and the text below it. | unjudged | approved 2026-11-24 ("Approved") |
| F1.6 | Fixed | Context states 2537 mutants across 13 crates at 26dde61; the fast-crate example is descartes-rs (12 shards). | unjudged | approved 2026-11-24 ("Approved") |
| F1.7 | Fixed | R5 requires the Rust toolchain step and read-only GMP cache restore in `mutation-rs` and `mutation-rs-canary`. | unjudged | approved 2026-11-24 ("Approved") |
| F1.8 | Fixed | `scripts/mutation-shard-count.sh` joins `RS_CANARY_PATHS` (Design 3, R13). | unjudged | approved 2026-11-24 ("Approved") |
| F1.9 | Fixed | The live-log BATS case extracts the R6 lines from `mutation-pr.yml` (Testing). | unjudged | approved 2026-11-24 ("Approved") |
| F1.10 | Fixed | The summary filter is `{ grep -E ... \|\| [ $? -eq 1 ]; }`: no match passes, a grep error still fails (Design 3). | unjudged | approved 2026-11-24 ("Approved") |
| F1.11 | Fixed | Design 5 and V1 state that V1's dispatch acts on the real tracking issue, intended. | unjudged | approved 2026-11-24 ("Approved") |

Stopped: reviewer recommended stopping in round 1
