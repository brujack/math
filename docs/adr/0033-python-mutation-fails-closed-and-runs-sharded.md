# ADR-0033: Python Mutation Testing Fails Closed and Runs as an 8 × 10 Sharded Matrix

**Date:** 2026-10-30
**Status:** Accepted. Spec: `docs/superpowers/specs/2026-10-30-python-mutation-baseline-and-sharding-design.md` (R1-R23, R8 amended).

## Context

Both Python mutation workflows installed only `cosmic-ray`. Every test module imports
`hypothesis`, so each mutant's test run died on an import error and cosmic-ray recorded it as
`KILLED`. The 2026-10-01 monthly run reported 0 survivors across 5,346 jobs, and fib finished
in 18 s. With the real dependencies installed, a 30-job sample per sub-project found 4 to 17
survivors each.

Installing the dependencies alone does not fix the workflow. cosmic-ray 8.7.0's `local`
distributor is serial. Measured on `claude`, pi's 1,859 jobs take about 5.4 h and e's 1,648
about 3.4 h, against `timeout-minutes: 120` and GitHub's 6 h job cap. Some mutants never
terminate and are killed at the 60 s timeout. One pi mutant reached 138 GB resident within
that timeout, against about 16 GB on a runner.

## Decision

- **Fail closed locally and in CI.** The rendered Python `mutants` recipe runs
  `cosmic-ray baseline` before `init`. When the baseline fails, the recipe re-runs the test
  command so the log shows the cause. Both run under the Rust recipes' 8 GiB `ulimit -v` cap,
  with the same `MUTANTS_UNCAPPED=1` escape.
- **Shard the monthly run.** `mutation-testing-python.yml` runs one job per sub-project and
  shard: 8 × 10 cells, `fail-fast: false`, `timeout-minutes: 90`, the same for every
  sub-project. `scripts/cosmic_ray_shard.py` partitions a fresh session by a sorted spec key,
  because `job_id` is a new UUID on every `init`.
- **One verdict per cell, from the session itself.** `scripts/cosmic_ray_cell_status.py` reads
  cosmic-ray's uppercase enum names. A cell is red when it has no jobs, when a job has no
  result, or when any row ran no test. Timeouts and survivors are reported and never make a
  cell red.
- **A durable consumer.** Notify checks that every expected cell reported. It posts
  per-sub-project counts to the standing `mutation-report-python` issue and keeps survivor
  locations for 90 days in artifact `mutants-survivors-python`.
- **PR check is baseline only.** `mutation-pr.yml` runs `make mutants-baseline` for the changed
  sub-projects, and for all 8 when a source of the pip line changes. It mutates nothing.

## Consequences

- A broken mutation environment now turns the job red instead of reporting a perfect score.
- The monthly run costs about 11.5 h of serial compute across 80 jobs, plus 160 artifacts.
- Survivor counts gate nothing. Acting on them is a human decision, taken from the issue and
  the survivor list.
- cosmic-ray's `http` distributor was rejected. It needs a separate source copy per worker,
  and it is capped at the runner's vCPU count.
- Open, in the Backlog: an interrupted local run leaves a mutated source file behind, and
  `mutation-notify.sh` can name the wrong cause for a cell whose runner died.

## Related

- ADR-0032 (per-project files rendered from templates).
- `.github/workflows/mutation-testing.yml` (the Rust equivalent, unchanged).
