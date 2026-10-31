# A master-scoped GMP/MPFR build cache for the Rust CI, and parallel bats in scripts.yml

- **Date:** 2026-10-31
- **Status:** Draft
- **Related:**
  - Backlog P3 row "GMP/MPFR rebuilt from source on every CI rust-cache miss";
  - etch-cli#158 (its job split; math already has the same split from math#177);
  - ADR-0032 (per-crate files rendered from one template).

## Problem

### The rug crates rebuild GMP/MPFR in nearly every coverage and release build

The five crates that depend on `rug` (pi, e, fib, factorial, perfect-numbers) set a PR's CI
critical path. Step timings from their 2026-10-26 PR runs: `Check coverage (≥90%)` took
150-217 s, and `Build` took 137-179 s on a cache miss and 4.7 s on a hit. The non-rug
`goldbach-rs` took 20-74 s for coverage and 10 s for its build. In pi-rs's coverage log the
rust-cache restore succeeds, `Compiling rug` starts at 20:23:41, and the next line,
`Compiling pi`, comes at 20:26:32: 171 s spent in `gmp-mpfr-sys`'s build script compiling
GMP and MPFR from C. Tarpaulin builds with its own `RUSTFLAGS`, so cargo's fingerprint misses
and the build script runs again.

`gmp-mpfr-sys` keeps its C build in a cache directory (`GMP_MPFR_SYS_CACHE`, default
`~/.cache/gmp-mpfr-sys`) laid out as `<major.minor>/<target>/<version>/`. Nothing in CI saves
that directory. Measured on `claude` with fib-rs in a scratch copy: 57 s cold; 5 s with the
cache warm under `RUSTFLAGS="-C instrument-coverage"` in a fresh target directory; 55 s again
with the cache disabled (`GMP_MPFR_SYS_CACHE=_`). The cache is 3.4 MB. GMP is configured with
`--enable-fat` (`gmp-mpfr-sys` 1.7.0 `build.rs:10`, `:650`), so the library is portable
across x86-64 CPUs and a cache built on one runner is safe on another.

### PR-scoped caches never reach the next PR

GitHub Actions caches are scoped to the ref that saved them. A run can read caches from its
own ref and from the default branch, never from another PR. math's crate workflows run on
`pull_request` only, so they save nothing on `master`. Of the repo's 89 caches (measured
2026-10-31), 88 are on PR refs (`refs/pull/149/merge` 39, `181` 27, `180` 22) and one is on
`refs/heads/master`. The "Cache restored" lines above came from re-runs inside the same PR, so
each new PR's first run of a rug crate starts cold. Total cache use is 11.4 GB, over the
10 GB limit, so entries are also being evicted.

### scripts.yml runs bats serially

`scripts.yml` runs `bats --recursive tests/` (39 s) without `--jobs`, while the local
`make test-hooks` already uses `bats --jobs 8` when GNU parallel is present.

## Design

1. **One key script.** `scripts/gmp-cache-key.sh` prints the cache key
   `gmp-mpfr-sys-<versions>-<os>`. `<versions>` is the sorted, unique set of `gmp-mpfr-sys`
   versions in the tracked `*/*-rs/Cargo.lock` files, joined with `_` (today `1.7.0_1.7.1`).
   `<os>` is its first argument (the workflows pass `${{ runner.os }}-${{ env.ImageOS }}`).
   It exits non-zero with a message when no lockfile names `gmp-mpfr-sys`. Both workflows
   below call it, so the writer and the readers cannot disagree on the key.
2. **A warm workflow on master.** New `.github/workflows/gmp-cache.yml`, triggered by
   `workflow_dispatch` and a weekly `schedule` (both run on the default branch, so the saved
   cache is readable by every PR). One job: checkout, compute the key, restore it, and on a
   miss run `cargo build -p gmp-mpfr-sys` in each crate whose lockfile names it, with
   `GMP_MPFR_SYS_CACHE` set to `${{ runner.temp }}/gmp-mpfr-sys`, then save that directory under
   the key with `actions/cache/save`. Writer and readers use the same absolute path, which
   `actions/cache` requires for a restore to match.
   `permissions: contents: read`. It runs nothing else and gates nothing.
3. **Read-only restore in every crate job.** The rendered `ci.yml` template's `test`,
   `coverage` and `build` jobs set `GMP_MPFR_SYS_CACHE` to `${{ runner.temp }}/gmp-mpfr-sys`.
   Before the first cargo step they run `scripts/gmp-cache-key.sh` and
   `actions/cache/restore`, with `restore-keys: gmp-mpfr-sys-` so a version bump still restores
   the older versions' builds. No job saves, so PR runs add nothing to the 10 GB budget. A
   miss builds exactly as today: the change can only make a job faster, never fail it.
   Rendered to all 11 crates; the six without `rug` restore a 3.4 MB entry they never read.
4. **Parallel bats in scripts.yml.** The bats install step also installs GNU `parallel`, and
   the test step runs `bats --jobs 8 --recursive tests/`, matching the local `JOBS` default.

## Testing

- `tests/scripts/gmp_cache_key.bats`: a fixture tree with two lockfiles naming `1.7.1` and
  `1.7.0` gives exactly `gmp-mpfr-sys-1.7.0_1.7.1-Linux-ubuntu26`; duplicate versions collapse;
  a tree with no `gmp-mpfr-sys` exits non-zero naming the cause; a missing argument exits
  non-zero. One case runs the script on the real repo and asserts the key starts with
  `gmp-mpfr-sys-1.7.`.
- `tests/test_rust_ci_jobs.py` (YAML via `yaml.safe_load`): in every rendered
  `*-rs.yml`, the `test`, `coverage` and `build` jobs set `GMP_MPFR_SYS_CACHE`, call
  `scripts/gmp-cache-key.sh`, and use `actions/cache/restore` (never `actions/cache` or
  `actions/cache/save`) before any step running cargo or make; `gmp-cache.yml` has only
  `workflow_dispatch` and `schedule` triggers and saves with the same key script.
- A test asserts `scripts.yml` runs bats with `--jobs` and installs `parallel`.

## Out of scope

- The 11.4 GB cache budget, driven by per-PR rust-cache entries.
- Unifying the two `gmp-mpfr-sys` versions (1.7.0 in e, fib, pi; 1.7.1 in factorial,
  perfect-numbers); Renovate's lock-file maintenance (math#149) covers it.
- Parallel root Python tests (25 s), release workflows, and the rust-cache configuration.

## Requirements

- **R1.** `[PR1]` `scripts/gmp-cache-key.sh <os>` prints `gmp-mpfr-sys-<sorted unique versions joined by _>-<os>` from the tracked `*/*-rs/Cargo.lock` files, and exits non-zero with a message when none names `gmp-mpfr-sys` or the argument is missing.
- **R2.** `[PR1]` `.github/workflows/gmp-cache.yml` triggers only on `workflow_dispatch` and `schedule`, has `contents: read`, builds `gmp-mpfr-sys` on a key miss with `GMP_MPFR_SYS_CACHE` set to `${{ runner.temp }}/gmp-mpfr-sys`, and saves that directory with `actions/cache/save` under the key from `scripts/gmp-cache-key.sh`.
- **R3.** `[PR1]` Every rendered `*-rs.yml` `test`, `coverage` and `build` job sets `GMP_MPFR_SYS_CACHE` to `${{ runner.temp }}/gmp-mpfr-sys` and, before any cargo or make step, restores it with `actions/cache/restore` under the key from `scripts/gmp-cache-key.sh` with `restore-keys: gmp-mpfr-sys-`.
- **R4.** `[PR1]` No crate workflow job saves the GMP cache.
- **R5.** `[PR1]` `scripts.yml` installs GNU `parallel` and runs `bats --jobs 8 --recursive tests/`.
- **R6.** `[PR1]` Tests pin R1's exact key for a two-version fixture and its error exits, R3 and R4 across all rendered crate workflows, R2's triggers and save step, and R5.
- **R7.** `[PR1]` The Backlog loses the "GMP/MPFR rebuilt from source" row, and root `CLAUDE.md` names `gmp-cache.yml` and the read-only restore in its workflow lines, and its `scripts.yml` line says bats runs with `--jobs 8`.
- **V1.** After merge, dispatch `gmp-cache.yml` on master: it saves a cache whose key matches `scripts/gmp-cache-key.sh`.
- **V2.** On the next PR that runs the rug crates' workflows, their coverage logs show no build-script wait between `Compiling rug` and `Compiling <crate>`; record each crate's coverage and build step times beside the 2026-10-26 figures in the PR body.
- **V3.** On this PR, the `scripts` job's bats step runs in parallel (its log shows `--jobs 8`) and passes.
- **N1.** No crate workflow gains a `push` or `schedule` trigger.
- **N2.** No change to the rust-cache steps' configuration.
- **N3.** No crate-to-crate difference in the rendered workflows.
- **N4.** No change to `release-*-rs.yml`.
