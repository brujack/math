# ADR-0034: The GMP/MPFR Build Cache Is Saved Only by a Master-Scoped Warm Workflow

**Date:** 2026-10-31
**Status:** Accepted. Spec: `docs/superpowers/specs/2026-10-31-ci-gmp-cache-and-parallel-bats-design.md`.

## Context

Five `rug` crates build GMP, MPFR and MPC from source through `gmp-mpfr-sys` on every CI
rust-cache miss. `gmp-mpfr-sys` keeps its C build under the directory named by
`GMP_MPFR_SYS_CACHE`, but rust-cache does not save that path, so the build repeats.

Caches written on a pull request are scoped to that PR's ref and are not visible to other
PRs. A cache that every PR saves therefore never warms the next one. A cache saved on master
is readable from every PR.

## Decision

- **One saver.** `.github/workflows/gmp-cache.yml` is the only job that saves the cache. It
  runs weekly (`cron: "0 3 * * 1"`) and by `workflow_dispatch`, on master. It runs
  `scripts/gmp-cache-key.sh --strict`, so an unusable lockfile fails the run. The key carries
  the sorted `gmp-mpfr-sys` versions of every tracked crate lockfile and the ISO week.
- **Crate jobs restore read-only.** `scripts/crate_templates/ci.yml` sets
  `GMP_MPFR_SYS_CACHE` through `$GITHUB_ENV` from `RUNNER_TEMP` (the `runner` context is not
  allowed in `jobs.<id>.env`), runs the key script without `--strict`, and restores with
  `actions/cache/restore` only when it prints `enabled=true`. An unusable input degrades to a
  cold build with a warning.
- **The warm job's library check accepts a newer patch.** `gmp-mpfr-sys` deletes older patch
  directories when a newer one saves, and a crate locked at 1.7.0 loads 1.7.1. The check
  therefore accepts a same-minor directory at the locked patch or newer, and requires
  `libgmp.a`, `libmpfr.a` and `libmpc.a` in it.
- **Static linking and MPC are kept.** No dependency or feature changes.

## Consequences

- The first PR after a `gmp-mpfr-sys` bump builds cold until `gmp-cache.yml` is dispatched
  on master. Dispatching it after such a bump is a manual step.
- A failed warm run is not notified, by design. Its effect is a cold build in crate jobs,
  which is slower and not wrong.
- Crate jobs cannot poison the cache, because they never save it.
- The weekly key costs one rebuild per week and one cache entry per week until eviction.

## Rejected alternatives

- **rust-cache `cache-directories`.** It is PR-scoped, and tarpaulin's `RUSTFLAGS` miss the
  fingerprint anyway.
- **A push trigger on `Cargo.lock`.** The fleet rule is `pull_request`-only triggers, and
  bumps are rare.
- **`use-system-libs`.** It links GMP dynamically into release binaries.

## Related

- ADR-0032 (per-project CI files rendered from templates).
- ADR-0033 (the same weekly-and-dispatch workflow pattern for mutation testing).
