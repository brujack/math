# ADR-0046: Shard the Rust mutation runs

**Date:** 2026-11-24
**Status:** Accepted

## Context

Both Rust mutation runs executed one crate in one job. The monthly sweep (`mutation-testing.yml`) ran every mutant of a crate in a single 60-minute job, and the per-PR gate (`mutation-pr.yml`, job `mutation-rs`) ran every changed-line mutant of a crate in one job. A crate with many mutants cannot finish inside the job limit: descartes has 831 mutants on master, zeta has 432 (748 with math#246), and a large diff does the same to the PR gate. A fixed `--timeout` was removed in #95 because it capped the baseline and tested zero mutants, so the fix has to be fewer mutants per job, not a shorter clock.

Spec: `docs/superpowers/specs/2026-11-23-shard-rust-mutation-design.md`. Plan: `docs/superpowers/plans/2026-11-24-shard-rust-mutation.md`.

## Decision

1. **Shard size.** `B = 75` mutants per shard. A crate with K mutants gets `n = max(1, ceil(K/75))` shards and no per-crate cap. Assignment is round-robin (`--sharding round-robin`), so shard k (1-based) holds `ceil((K-k)/n)` mutants. The whole plan is red past 256 emitted units, fault units included (the GitHub matrix limit; R3 amendment).
2. **Planner.** `scripts/mutation-rs-plan.sh (<base-ref> | --whole) <crate-dir>...` lists mutants with cargo-mutants and prints a JSON array of `{crate, slug, k, n, count}` units, `[]` when none. A base ref counts changed-line mutants (`--in-diff`); `--whole` counts every mutant for the sweep.
3. **PR job graph.** `mutation-rs-plan` emits the units; `mutation-rs` is a matrix over them, one job per shard, each running `scripts/mutation-pr-run.sh "origin/${GITHUB_BASE_REF}" --shard "${K}/${N}" --expect "${COUNT}" "${CRATE}"`. `mutation-rs-canary` plans its own diff of the amicable canary line and runs its shard with `--min-caught 1`. The aggregator `mutation-pr` keeps the required-check name and needs the plan, the shards and the canary. Sharded `mutation-pr-run.sh` takes exactly one crate (R4 amendment).
4. **Sweep job graph.** `mutation-testing.yml` `setup` runs `mutation-rs-plan.sh --whole` and `mutants` is a matrix with one job per shard; `notify` needs both and keeps its label and full-sweep rules.
5. **Post-run count check.** `--expect <count>` (via `scripts/mutation-shard-count.sh <outcomes.json> <label> <count>`) compares the mutants the shard actually tested with the planned count. A mismatch is red and the classifier does not run, so a shard that tested nothing or the wrong set cannot pass. An empty shard lists `[]` and writes no `outcomes.json`.
6. **No `--min-caught` on PR shards.** PR shards classify with limit 0 and no `--min-caught`: a diff whose mutants all time out must stay green (timeouts are green beside a catch only in the sweep). `--expect` is the guard against a shard that tested nothing. Only the canary keeps `--min-caught 1`.
7. **Cost driver.** Baseline test time (a cold `cargo build --tests` plus the unmutated suite) is paid once per shard, so the number of shards, not the mutant count, multiplies the fixed cost. Above about 42 s per mutant a 75-mutant shard reaches 60 minutes; B is lowered before merge if a measured shard passes about 50 minutes.

## Measurements

Population is stated per figure; estimates are labelled.

- cargo-mutants 27.1.0 lists zeta's 339 PR-3 diff mutants in 0.23 s, so planning is cheap.
- 339 mutants split 68/68/68/68/67 over 5 shards (`339 = 68*4 + 67`).
- zeta whole-crate (432 mutants on master), 10 shards: 44, 44, 43 x 8; the union equals the unsharded list.
- Per-mutant time 21-30 s for the zeta PR-3 diff. This is a CI lower bound from a cancelled job: an estimate, not a measurement.
- Cold zeta `cargo build --tests` takes 108.6 s on 4 CPUs.
- Plan on master at the branch base (`mutation-rs-plan.sh --whole`, all 13 crates, measured): 2221 mutants, 37 shards: amicable 20/1, collatz 44/1, descartes 831/12, e 136/2, factorial 64/1, fib 41/1, goldbach 87/2, perfect-numbers 89/2, pi 166/3, prime 158/3, sq 32/1, twin-primes 121/2, zeta 432/6. With math#246's zeta (748 mutants) the spec counted 2537 mutants and 41 shards at 26dde61.

| crate | shards | baseline test time | longest shard | source |
|---|---|---|---|---|
| V1 (sweep) | pending | pending | pending | pending |
| V2 (math#246) | pending | pending | pending | pending |

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
