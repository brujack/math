# A master-scoped GMP/MPFR build cache for the Rust CI, and parallel bats in scripts.yml

- **Date:** 2026-10-31
- **Status:** Approved
- **Approved:** 2026-10-31
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

1. **One key script.** `scripts/gmp-cache-key.sh` prints two lines for `GITHUB_OUTPUT`:
   `prefix=gmp-mpfr-sys-<versions>-<runner os>-<image os>-` and `key=<prefix><ISO week>`.
   `<versions>` is the sorted, unique set of `gmp-mpfr-sys` versions in the tracked
   `*/*-rs/Cargo.lock` files, joined with `_` (today `1.7.0_1.7.1`). The OS parts come from
   the shell variables `RUNNER_OS` and `ImageOS` (the `${{ env.ImageOS }}` expression is
   empty, because the `env` context holds only workflow-set variables), and the week from
   `date -u +%G-W%V`, overridable by `GMP_CACHE_WEEK` for tests. It exits non-zero with a
   message when no lockfile names `gmp-mpfr-sys` or any part is empty, but only under
   `--strict`. Without `--strict` (the crate jobs) any such case prints `enabled=false` with a
   warning and exits 0, so the restore is skipped and the job builds as today; with all parts
   present it also prints `enabled=true`. Both workflows call it, so the writer and the readers
   cannot disagree on the key.
2. **A warm workflow on master.** New `.github/workflows/gmp-cache.yml`, triggered by
   `workflow_dispatch` and a weekly `schedule` (both run on the default branch, so the saved
   cache is readable by every PR). One job: checkout, compute the key, restore the exact key,
   and on a miss run `cargo build -p gmp-mpfr-sys` in each crate whose lockfile names it, with
   `GMP_MPFR_SYS_CACHE` set to `${{ runner.temp }}/gmp-mpfr-sys`, then save that directory under
   the key with `actions/cache/save`. Writer and readers use the same absolute path, which
   `actions/cache` requires for a restore to match. It calls the script with `--strict`. Before saving
   it asserts that each locked `gmp-mpfr-sys` version's directory holds `libgmp.a`, `libmpfr.a`
   and `libmpc.a` (measured: `-p gmp-mpfr-sys` in pi-rs builds
   all three, because cargo unifies rug's features). Each week gets a new key, so a fresh
   entry is saved weekly: that keeps the entry young under the 10 GB eviction pressure and
   rebuilds it after a runner-image gcc change, which `gmp-mpfr-sys`'s cache path ignores.
   A failed warm run is accepted without notification: it can only make PRs slower, never
   wrong, and slow rug-crate coverage on PRs is the visible signal. After a `gmp-mpfr-sys`
   bump on master, dispatch the workflow by hand: `gmp-mpfr-sys` reuses a cached build only
   at the same or a newer patch version, so older entries do not help.
   `permissions: contents: read`. It runs nothing else and gates nothing.
3. **Read-only restore in every crate job.** The rendered `ci.yml` template's `test`,
   `coverage` and `build` jobs set `GMP_MPFR_SYS_CACHE` to `${{ runner.temp }}/gmp-mpfr-sys`.
   Before the first cargo step they run `scripts/gmp-cache-key.sh >> "$GITHUB_OUTPUT"` (no
   `--strict`) and, only `if: steps.gmpkey.outputs.enabled == 'true'`, `actions/cache/restore`
   reading `key: ${{ steps.gmpkey.outputs.key }}`, with `restore-keys` set to the script's `prefix`, so a PR in a week the warm
   job has not yet run restores the previous week's entry for the same versions and image. No job saves, so PR runs add nothing to the 10 GB budget. A
   miss builds exactly as today: the change can only make a job faster, never fail it.
   Rendered to all 11 crates; the six without `rug` restore a 3.4 MB entry they never read.
4. **Parallel bats in scripts.yml.** The bats install step also installs GNU `parallel`, and
   the test step runs `bats --jobs 8 --recursive tests/`, matching the local `JOBS` default.

Rejected alternative: `rug`'s `use-system-libs` with the `libgmp-dev libmpfr-dev` CI
already installs would remove the C build with no cache, but release binaries would then
link GMP dynamically, or CI would test a different GMP from the one shipped. The apt step in
`ci.yml` is meanwhile unused by the Rust build; that goes to the Backlog.

## Testing

- `tests/scripts/gmp_cache_key.bats`: a fixture tree with two lockfiles naming `1.7.1` and
  `1.7.0`, with `RUNNER_OS=Linux ImageOS=ubuntu26 GMP_CACHE_WEEK=2026-W44`, prints exactly
  `prefix=gmp-mpfr-sys-1.7.0_1.7.1-Linux-ubuntu26-` and
  `key=gmp-mpfr-sys-1.7.0_1.7.1-Linux-ubuntu26-2026-W44`; duplicate versions collapse; no
  `gmp-mpfr-sys` in any lockfile, an empty `RUNNER_OS` and an empty `ImageOS` each exit
  non-zero naming the cause under `--strict`, and print `enabled=false` and exit 0 without it.
  One case runs the script on the real repo and asserts the key
  starts with `gmp-mpfr-sys-1.7.`.
- `tests/test_rust_ci_jobs.py` (YAML via `yaml.safe_load`): in every rendered
  `*-rs.yml`, the `test`, `coverage` and `build` jobs set `GMP_MPFR_SYS_CACHE`, run
  `scripts/gmp-cache-key.sh` without `--strict` appending to `$GITHUB_OUTPUT` in a step with an
  `id`, and use `actions/cache/restore` (never `actions/cache` or `actions/cache/save`) before
  any step running cargo or make, guarded by that step's `enabled` output and reading its `key`
  and `prefix` outputs; `gmp-cache.yml` has only
  `workflow_dispatch` and `schedule` triggers and saves with the same key script.
- A test asserts `scripts.yml` runs bats with `--jobs` and installs `parallel`.

## Out of scope

- The 11.4 GB cache budget, driven by per-PR rust-cache entries.
- Unifying the two `gmp-mpfr-sys` versions (1.7.0 in e, fib, pi; 1.7.1 in factorial,
  perfect-numbers); Renovate's lock-file maintenance (math#149) covers it.
- Parallel root Python tests (25 s), release workflows, and the rust-cache configuration.

## Requirements

- **R1.** `[PR1]` `scripts/gmp-cache-key.sh` prints `prefix=gmp-mpfr-sys-<sorted unique versions joined by _>-${RUNNER_OS}-${ImageOS}-` and `key=<prefix><ISO week, or GMP_CACHE_WEEK>` from the tracked `*/*-rs/Cargo.lock` files, and `enabled=true`; when no lockfile names `gmp-mpfr-sys` or `RUNNER_OS`, `ImageOS` or the week is empty it exits non-zero with a message under `--strict`, and otherwise prints `enabled=false` and exits 0.
- **R2.** `[PR1]` `.github/workflows/gmp-cache.yml` triggers only on `workflow_dispatch` and `schedule`, has `contents: read`, builds `gmp-mpfr-sys` on a key miss with `GMP_MPFR_SYS_CACHE` set to `${{ runner.temp }}/gmp-mpfr-sys`, calls the key script with `--strict`, asserts `libgmp.a`, `libmpfr.a` and `libmpc.a` exist for each locked `gmp-mpfr-sys` version, and saves that directory with `actions/cache/save` under the `key` from `scripts/gmp-cache-key.sh`.
- **R3.** `[PR1]` Every rendered `*-rs.yml` `test`, `coverage` and `build` job sets `GMP_MPFR_SYS_CACHE` to `${{ runner.temp }}/gmp-mpfr-sys` and, before any cargo or make step, restores it with `actions/cache/restore` guarded by the key step's `enabled` output, reading that step's `key` output with `restore-keys` set to its `prefix` output.
- **R4.** `[PR1]` No crate workflow job saves the GMP cache.
- **R5.** `[PR1]` `scripts.yml` installs GNU `parallel` and runs `bats --jobs 8 --recursive tests/`.
- **R6.** `[PR1]` Tests pin R1's exact key for a two-version fixture and its error exits, R3 and R4 across all rendered crate workflows, R2's triggers and save step, and R5.
- **R7.** `[PR1]` The Backlog loses the "GMP/MPFR rebuilt from source" row, and root `CLAUDE.md` names `gmp-cache.yml` and the read-only restore in its workflow lines, and its `scripts.yml` line says bats runs with `--jobs 8`.
- **R8.** `[PR1]` Root `CLAUDE.md` says to dispatch `gmp-cache.yml` after a `gmp-mpfr-sys` bump on master, and the Backlog gains a row for the unused `libgmp-dev libmpfr-dev` apt step in the Rust CI jobs.
- **V1.** After merge, dispatch `gmp-cache.yml` on master: it saves a cache whose key matches `scripts/gmp-cache-key.sh`.
- **V2.** On the next PR that runs the rug crates' workflows, each rug crate's coverage log shows a cache restore hit for the GMP key and under 20 s between `Compiling rug` and the next `Compiling` line; record each crate's coverage and build step times beside the 2026-10-26 figures in the PR body.
- **V3.** On this PR, the `scripts` job's bats step runs in parallel (its log shows `--jobs 8`) and passes.
- **N1.** No crate workflow gains a `push` or `schedule` trigger.
- **N2.** No change to the rust-cache steps' configuration.
- **N3.** No crate-to-crate difference in the rendered workflows.
- **N4.** No change to `release-*-rs.yml`.

## Multi-Lens Review

Reviewed at commit: `c6eab7e` (Step 7 self-review commit, before Step 8 dispatch)

Goal-Fit — Finding: worth building; rust-cache `cache-directories` would stay PR-scoped and
cannot fix coverage's fingerprint miss; `use-system-libs` is a real alternative the spec did
not reject. Assumption: the master entry survives eviction (oldest live cache about 4 days old
at 11.4 GB).
Ergonomics — Finding: `restore-keys: gmp-mpfr-sys-` cannot help after a bump (`build.rs` reuses
only same-or-newer patch); no consumer of a warm failure; V2 passes on absence. Assumption:
restores refresh `last_accessed_at`.
Risk — Finding: `${{ env.ImageOS }}` is empty, so the key's OS part is decorative and R6's
fixture hides it; the cache path ignores gcc, so a runner-image change reuses `libgmp.a`.
Assumption: `-p gmp-mpfr-sys` builds the libraries the consumers need (pi needs MPC).
Disposition (all three): Addressed (operator, 2026-10-31): key from shell variables plus an ISO
week, saved weekly, restore prefix scoped to versions and image (R1-R3); `libmpc.a` asserted
before save, and measured: `-p gmp-mpfr-sys` in pi-rs builds libgmp, libmpfr and libmpc; V2
pinned to a positive signal; `use-system-libs` recorded as rejected and the dead apt step
backlogged (R8). No push trigger, Accepted, reason: bumps are rare and a cold week costs only
speed; dispatch-after-bump documented (R8). Warm-failure notification Accepted, reason: failure
costs only speed and slow PR coverage is the signal.
Adversarial Spec Review: N/A — no comparison/evaluator/ambiguous-criteria trigger.

### Round 2

Reviewed at commit: `46fc422` (one combined lens covering goal-fit, ergonomics and risk)

Finding: the key script failed closed in all 33 crate jobs, so an empty `ImageOS` or a lost
`GITHUB_OUTPUT` write would turn every Rust job red, contradicting "can only make a job faster";
tests checked only that the script is called, not that the restore reads its outputs; the
`libmpc.a` check passed if only one of two locked versions built. Checked clean: `%G-W%V` year
boundary, week-boundary fallback, `cache/save` on an existing key warns only, eviction by last
access. Assumption: `ImageOS` is set in the step shell on `ubuntu-26.04` (runner-images source
sets it; no math log shows it).
Disposition: Addressed (operator, 2026-10-31): `--strict` only in the warm
job, fail-open `enabled=false` in crate jobs with the restore guarded on it (R1, R3); tests pin
the guard and the output wiring; per-version library assertion (R2). The `ImageOS` assumption is
covered by fail-open plus V2's required cache hit.

## Amendments

- R2 -> `.github/workflows/gmp-cache.yml` triggers only on `workflow_dispatch` and `schedule`, has `contents: read`, builds `gmp-mpfr-sys` on a key miss with `GMP_MPFR_SYS_CACHE` set to `${{ runner.temp }}/gmp-mpfr-sys`, calls the key script with `--strict`, asserts that for each locked `gmp-mpfr-sys` version some cached directory of the same major.minor at that patch or newer holds `libgmp.a`, `libmpfr.a` and `libmpc.a`, and saves that directory with `actions/cache/save` under the `key` from `scripts/gmp-cache-key.sh`. — measured 2026-10-31: saving a 1.7.1 build deletes the 1.7.0 directory (`save_cache` in `build.rs`), and a 1.7.0 crate then loads the 1.7.1 entry (0.81 s), so a correct cache holds one directory and failed the per-version check.
- R2 -> `.github/workflows/gmp-cache.yml` triggers only on `workflow_dispatch` and `schedule`, has `contents: read`, builds `gmp-mpfr-sys` on a key miss with `GMP_MPFR_SYS_CACHE` set to `${RUNNER_TEMP}/gmp-mpfr-sys` through `$GITHUB_ENV` in its first step, calls the key script with `--strict`, asserts that for each locked `gmp-mpfr-sys` version some cached directory of the same major.minor at that patch or newer holds `libgmp.a`, `libmpfr.a` and `libmpc.a`, and saves `${{ runner.temp }}/gmp-mpfr-sys` with `actions/cache/save` under the `key` from `scripts/gmp-cache-key.sh`. — the `runner` context is not available in `jobs.<id>.env`, so GitHub rejects the job-level form (actionlint 1.7.12: `context "runner" is not allowed here`).
- R3 -> Every rendered `*-rs.yml` `test`, `coverage` and `build` job sets `GMP_MPFR_SYS_CACHE` to `${RUNNER_TEMP}/gmp-mpfr-sys` through `$GITHUB_ENV` in its key step and, before any cargo or make step, restores `${{ runner.temp }}/gmp-mpfr-sys` with `actions/cache/restore` guarded by the key step's `enabled` output, reading that step's `key` output with `restore-keys` set to its `prefix` output. — same `runner`-context restriction as R2; the value is unchanged.
- finding R2 (2026-10-31, reviewer both): DIFFERS — Everything else matches (triggers workflow_dispatch+schedule only at :4-7, contents: read at :9, --strict at :23, build on cache-hit != 'true', same-minor patch>= check for libgmp.a/libmpfr.a/libmpc.a, actions/cache/save of ${{ runner.temp }}/gmp-mpfr-sys under steps.gmpkey.outputs.key at :91-95), but GMP_MPFR_SYS_CACHE is written to $GITHUB_ENV in the job's second step ('Derive GMP cache key'), not its first step, which is actions/checkout.
- R2 -> `.github/workflows/gmp-cache.yml` triggers only on `workflow_dispatch` and `schedule`, has `contents: read`, builds `gmp-mpfr-sys` on a key miss with `GMP_MPFR_SYS_CACHE` set to `${RUNNER_TEMP}/gmp-mpfr-sys` through `$GITHUB_ENV` in its key step (the first step after checkout), calls the key script with `--strict`, asserts that for each locked `gmp-mpfr-sys` version some cached directory of the same major.minor at that patch or newer holds `libgmp.a`, `libmpfr.a` and `libmpc.a`, and saves `${{ runner.temp }}/gmp-mpfr-sys` with `actions/cache/save` under the `key` from `scripts/gmp-cache-key.sh`. — checkout must run before the key script exists on disk, so the export sits in the first step after it; "first step" was imprecise.
- finding R7 (2026-10-31, reviewer both): DIFFERS — The Backlog row is removed, gmp-cache.yml is named at CLAUDE.md:160 and the read-only restore at :163, and the scripts.yml line at :183 says `--jobs 8`, but the other scripts.yml line at :161 (the auto-merge.yml line) still says `scripts.yml` runs `bats --recursive tests/` without `--jobs 8`.
- R7 reviewed: fixed in 3cff605
