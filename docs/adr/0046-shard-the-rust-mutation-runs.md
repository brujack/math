# ADR-0046: Shard the Rust mutation runs

**Date:** 2026-11-24
**Status:** Accepted

## Context

Both Rust mutation runs gave one crate one job. The monthly sweep (`mutation-testing.yml`) ran every mutant of a crate in a single 60-minute job. The per-PR job `mutation-rs` (`mutation-pr.yml`) ran all changed crates' changed-line mutants, then the amicable-rs canary, then the Python baselines, serially in one 60-minute job. A crate with many mutants cannot finish inside the job limit: descartes has 831 mutants on master, zeta has 432 (748 with math#246), and a large diff does the same to the PR gate. A fixed `--timeout` was removed in #95 because it capped the baseline and tested zero mutants, so the fix has to be fewer mutants per job, not a shorter clock.

Spec: `docs/superpowers/specs/2026-11-23-shard-rust-mutation-design.md`. Plan: `docs/superpowers/plans/2026-11-24-shard-rust-mutation.md`.

## Decision

1. **Shard size.** `B = 75` mutants per shard. A crate with K mutants gets `n = max(1, ceil(K/75))` shards and no per-crate cap. Assignment is round-robin (`--sharding round-robin`), so shard k (0-based, as `MUTANT_SHARD`) holds `ceil((K-k)/n)` mutants. The whole plan is red past 256 emitted units, fault units included (the GitHub matrix limit; R3 amendment).
2. **Planner.** `scripts/mutation-rs-plan.sh (<base-ref> | --whole) <crate-dir>...` lists mutants with cargo-mutants and prints a JSON array of `{crate, slug, k, n, count}` units, `[]` when none. A base ref counts changed-line mutants (`--in-diff`); `--whole` counts every mutant for the sweep.
3. **PR job graph.** `mutation-rs-plan` (`timeout-minutes: 30`) runs `mutation-pr-detect.sh` and the planner and writes `units=[]` when no crate changed. `mutation-rs` (`if: needs.mutation-rs-plan.outputs.units != '[]'`, `fail-fast: false`, `timeout-minutes: 60`) is a matrix over the units, one job per shard, each running `scripts/mutation-pr-run.sh "origin/${GITHUB_BASE_REF}" --shard "${K}/${N}" --expect "${COUNT}" "${CRATE}"`. `mutation-rs-canary` (`if: needs.mutation-rs-plan.outputs.rs_canary == 'true'`) plans its own diff of the amicable canary line and runs its shard with `--min-caught 1`. The aggregator `mutation-pr` keeps the required-check name and needs the plan, the shards and the canary. Sharded `mutation-pr-run.sh` takes exactly one crate (R4 amendment).
4. **Sweep job graph.** `mutation-testing.yml` `setup` runs `mutation-rs-plan.sh --whole`; `mutants` is a matrix with one job per shard (`fail-fast: false`); `notify` needs both and keeps its label and full-sweep rules. A crate whose listing faults becomes a fault unit (slug `<name>-plan`, field `fault`) whose leg prints `red: <slug> - plan fault: <cause>`, so the other crates are still tested and `notify` names the fault; it is never a `setup` failure. `setup` exits 1 only on an unknown `crate` input, an empty crate list, a non-zero planner exit, or a plan with no unit (R8 amendment).
5. **Post-run count check.** `--expect <count>` (via `scripts/mutation-shard-count.sh <outcomes.json> <label> <count>`) compares the mutants the shard actually tested with the planned count. A mismatch is red and the classifier does not run, so a shard that tested nothing or the wrong set cannot pass. An empty shard lists `[]` and writes no `outcomes.json`.
6. **No `--min-caught` on PR shards.** PR shards classify with limit 0 and no `--min-caught`: a diff whose mutants all time out must stay green (timeouts are green beside a catch only in the sweep). `--expect` is the guard against a shard that tested nothing. Only the canary keeps `--min-caught 1`.
7. **Cost driver.** cargo-mutants runs the crate's test suite once per mutant and times a mutant out at 5x the baseline test time (minimum 30 s), so per-mutant cost follows the baseline test time, not the mutant count. B = 75 is tuned to a baseline of about 15 s. Separately, the unmutated baseline build and test are paid once per shard, so more shards add fixed cost. Above about 42 s per mutant a 75-mutant shard reaches 60 minutes; B is lowered before merge if a measured shard passes about 50 minutes.

## Measurements

Population is stated per row; estimates are labelled.

cargo-mutants 27.1.0 lists zeta's 339 PR-3 diff mutants in 0.23 s, so planning is cheap. 339 mutants split 68/68/68/68/67 over 5 shards. zeta whole-crate (432 mutants on master) split over 10 shards gives 44, 44, 43 x 8, and their union equals the unsharded list. A shard that selects nothing lists `[]` and writes no `outcomes.json`.

| Population | Mutants | Baseline test | s per mutant | Source |
|---|---|---|---|---|
| 11 crates, full sweep, run 42328612206 (sha 9313b1a) | 20-166 each, 947 total | not recorded | 1.5-5.0, mean 2.9 | `Run mutants` step timestamps; counts from `cargo mutants --list --json` on that sha |
| zeta-rs, earlier PR runs 45126222244 and 45232851299 | 309 and 132 | 2 s | 3.3 and 2.7 | `N mutants tested in Mm` and `Unmutated baseline` log lines |
| zeta-rs PR 3 diff, CI, run 45309470730 | 339 listed | not printed (cancelled) | more than 20.8 | step ran 117.6 min and was cancelled |
| zeta-rs earlier PR 3 diff, `claude`, 4 CPUs | 313 with outcomes | 12.1 s (`cargo test -- --skip e2e_`) | 14.5 | 4553 s; 234 caught, 55 unviable, 24 timeouts at about 61 s, 0 missed |

- PR 3 raised zeta's unit-suite time about 6x (2 s to 12-15 s; CI nextest ran all 400 tests in 15.1 s, run 45309470687). The descartes-rs suite takes about 3 s on 4 CPUs.
- The measured CI lower bound for the zeta PR 3 diff is more than 20.8 s per mutant (run 45309470730, cancelled job). 30 s per mutant is an estimate, not a measurement; the local row is an earlier state of the branch (313 of the final 339 mutants).
- A cold zeta `cargo build --tests` takes 108.6 s on 4 CPUs.
- Plan on master at the branch base (`mutation-rs-plan.sh --whole`, all 13 crates, measured): 2221 mutants, 37 shards. With math#246's zeta (748 mutants) the spec counted 2537 mutants and 41 shards at 26dde61.

Pending results, one row per crate for V1 (the sweep, shard counts from the 37-shard plan) and one for V2:

| run | crate | shards | mutants per shard | baseline test time | longest shard | source |
|---|---|---|---|---|---|---|
| V1 (sweep) | amicable-rs | 1 | pending | pending | pending | pending |
| V1 (sweep) | collatz-rs | 1 | pending | pending | pending | pending |
| V1 (sweep) | descartes-rs | 12 | pending | pending | pending | pending |
| V1 (sweep) | e-rs | 2 | pending | pending | pending | pending |
| V1 (sweep) | factorial-rs | 1 | pending | pending | pending | pending |
| V1 (sweep) | fib-rs | 1 | pending | pending | pending | pending |
| V1 (sweep) | goldbach-rs | 2 | pending | pending | pending | pending |
| V1 (sweep) | perfect-numbers-rs | 2 | pending | pending | pending | pending |
| V1 (sweep) | pi-rs | 3 | pending | pending | pending | pending |
| V1 (sweep) | prime-rs | 3 | pending | pending | pending | pending |
| V1 (sweep) | sq-rs | 1 | pending | pending | pending | pending |
| V1 (sweep) | twin-primes-rs | 2 | pending | pending | pending | pending |
| V1 (sweep) | zeta-rs | 6 | pending | pending | pending | pending |
| V2 (math#246) | zeta-rs | pending | pending | pending | pending | pending |

Rule: a shard past about 50 minutes lowers B before merge.

## Consequences

- No Rust mutation job approaches the 60-minute limit at B = 75 unless per-mutant time exceeds about 42 s.
- Total CI minutes rise by the baseline cost of every extra shard; wall time falls because shards run in parallel.
- The matrix limit of 256 bounds the plan; a plan past it is red rather than silently truncated.
- Every shard is checked against its planned count, so a plan that disagrees with the runner (different list, different diff) goes red instead of passing on a subset.

## Related

- ADR-0042: Rust sweep holds zero missed
- ADR-0043: mutation runs disable core dumps
- ADR-0044: per-PR Python mutation gate (aggregator and plan-job pattern)
- #95: fixed `--timeout` removed
- Spec `docs/superpowers/specs/2026-11-23-shard-rust-mutation-design.md`; plan `docs/superpowers/plans/2026-11-24-shard-rust-mutation.md`
