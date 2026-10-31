# ADR-0035: MIT Licence, cargo-deny Replaces cargo-audit, and LGPL Notices for Statically Linked GMP

**Date:** 2026-10-31
**Status:** Accepted. Spec: `docs/superpowers/specs/2026-10-31-rust-python-standards-tier1-design.md`. Plan: `docs/superpowers/plans/2026-10-31-rust-python-standards-tier1.md`.

## Context

The repository had no licence file and no `license` field in any crate, so nobody had a
stated right to use the code. Five crates (`e`, `factorial`, `fib`, `perfect-numbers`, `pi`)
link GMP, MPFR and MPC statically through `rug` and `gmp-mpfr-sys`. Those libraries are
LGPL-3.0 (with GPL-3.0 components), and distributing a statically linked binary carries
notice and text obligations that the release assets did not meet. Supply-chain checking was
`cargo-audit`, which covers RustSec advisories only, with no licence, ban or source policy.

## Decision

- **MIT licence.** A root `LICENSE` file and `license = "MIT"` in every crate's
  `Cargo.toml`, pinned by `tests/test_crate_uniformity.py`.
- **cargo-deny replaces cargo-audit.** One root `deny.toml` covers the same RustSec database
  plus licences, bans and sources, with `unmaintained = "all"`. `scripts/cargo-deny-all.sh`
  checks all 11 crates and refuses a crate list other than 11. `cargo-deny.yml` runs it, and
  `scripts.yml` runs the fixture controls. `tests/test_deny_policy.py` pins `deny.toml`
  whole, so any change (a licence, an exception, an `[advisories] ignore`) is an
  operator-approved edit to that test.
- **LGPL compliance by embedded notices.** Every release attaches `THIRD-PARTY-NOTICES.txt`,
  built by `scripts/third-party-notices.sh`. For crates whose lockfile contains
  `gmp-mpfr-sys` it embeds the LGPL-3.0 and GPL-3.0 texts. It fails before the tag is pushed
  on a missing or unreadable lockfile or licence text, consistent with ADR-0026 (sign before
  publishing).

## Consequences

- A new licence, exception or advisory ignore is a deliberate, reviewed change to
  `tests/test_deny_policy.py`, not a quiet edit to `deny.toml`.
- Release jobs fail closed on incomplete notice data, so a bad lockfile blocks a release
  instead of shipping one without notices.
- The five already-published v0.1.0 releases (2026-10-24) predate the notices step and ship
  without them. Remediation (attach notices, re-release or withdraw) is an open operator
  decision (spec V4); nothing is uploaded without an explicit yes.

## Related

- Spec `docs/superpowers/specs/2026-10-31-rust-python-standards-tier1-design.md` and plan
  `docs/superpowers/plans/2026-10-31-rust-python-standards-tier1.md`.
- ADR-0026 (sign before publishing).
- ADR-0034 (the same `gmp-mpfr-sys` crates and their build cache).
