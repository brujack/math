# ADR-0037: CI supply-chain guardrails — verified downloads, locked cargo-deny, no system GMP

**Date:** 2026-10-31
**Status:** Accepted

## Context

Four Backlog rows described gaps in how CI and the local hooks fetch, verify and check
what the repo depends on:

- **Unverified download.** The `secret-scan` job downloaded gitleaks with `wget` and ran it
  with no checksum, against core.md ci-002. snyk and shellcheck already complied. Only a
  per-tool test (`tests/test_snyk_cli_pinned.py`) existed, so nothing stopped the next
  direct download from repeating the gap.
- **Unlocked cargo-deny.** `scripts/cargo-deny-all.sh` ran without `--locked`. When a
  crate's `Cargo.toml` and `Cargo.lock` disagreed, cargo-deny silently rewrote the lock and
  checked the rewritten one.
- **`deny.toml` unchecked on push.** A push touching `deny.toml` ran nothing locally.
- **Unused apt step.** Every Rust-only workflow apt-installed `libgmp-dev libmpfr-dev`.
  Nothing uses them: no crate enables a system-library feature, so `gmp-mpfr-sys` builds
  GMP, MPFR and MPC from source and links them statically. A cold build of `pi-rs` in a
  clean `ubuntu:26.04` container, without the libraries, succeeded.

Three review rounds on the spec rejected two alternatives:

- **A local real-crate cargo-deny run in pre-push.** Online, it refuses an offline push
  with `failed to fetch advisory database`. With `--offline`, it resolves crates from
  `~/.cargo`, but crate builds cache into `<worktree>/.cache/cargo-home`. So a push that
  changes a dependency fails with `no matching package` or `--offline was specified`.
  cargo-deny 0.20.2 has no flag for an offline advisory DB with online crates.
- **`--locked` on the shipped builds.** It is a no-op in `release.yml`: the same job's
  unlocked `cargo clippy` rewrites a stale lock before the build runs.

## Decision

- **Every `curl` or `wget` in a workflow or composite action must take one canonical
  shape.** `tests/test_workflow_downloads_verified.py` enforces it:
  - The download is a standalone `-o`/`-O` to a literal absolute path.
  - Before any use of that path, the step runs `echo "<hash>  <path>" | sha256sum -c -`.
  - The hash is a 64-hex literal, or a step-`env:` variable holding one that the script
    never reassigns.

  Any other `curl` or `wget` line fails the test. The one exception is a `curl` whose
  single pipeline stage is `jq`. The test is a tripwire for ci-002, not a sandbox against
  deliberate evasion; glob uses of the path are a stated limit. gitleaks 8.21.2 is pinned
  this way.

- **`scripts/cargo-deny-all.sh` passes `--locked` before `check`,** so a stale or missing
  `Cargo.lock` fails the gate. `cargo-deny.yml` declares `permissions: contents: read`.
- **pre-push runs root `make test` on a `deny.toml` change.** That covers the key-level
  policy tests (`tests/test_deny_policy.py`) and the real-cargo-deny fixture controls. Real-crate cargo-deny stays in CI
  (`cargo-deny.yml` runs on every `Cargo.toml`, `Cargo.lock` and `deny.toml` change).
- **Rust-only workflows install no system GMP, MPFR or MPC.** This covers the 22 rendered
  crate workflows, `gmp-cache.yml` and `benchmarks.yml`.
  `tests/test_rust_workflows_no_system_gmp.py` pins exactly those 24 files.

## Consequences

- **New direct downloads must follow the canonical form.** Combined short flags (`-qO`),
  `curl -O`, `> file` and a hash fetched at run time all fail the test. That is
  deliberate: the shapes it accepts are the ones it can check.
- **A dependency change still waits for CI** for its licence and advisory verdict. The
  Backlog row "Local dependency check before push" records the cache measurements in case
  that becomes worth solving.
- **Each Rust CI job saves one `apt-get update` and install.** The first cold build without
  the step on a real runner is the next GMP-crate release (spec V2).
- **Python workflows keep the apt step.** Whether gmpy2's wheels need system GMP is
  unmeasured, and a Backlog row carries it.

## Related

- Spec: [2026-10-31-ci-supply-chain-bundle-design](../superpowers/specs/2026-10-31-ci-supply-chain-bundle-design.md)
- Plan: [2026-10-31-ci-supply-chain-bundle](../superpowers/plans/2026-10-31-ci-supply-chain-bundle.md)
- [ADR-0034](0034-master-scoped-gmp-cache.md): GMP build cache
- [ADR-0035](0035-mit-licence-cargo-deny-and-lgpl-notices.md): cargo-deny policy
- math#191 (`772e431`)
