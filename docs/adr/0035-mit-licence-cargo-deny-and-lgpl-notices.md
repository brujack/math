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
  plus licences, bans and sources, with `unmaintained = "all"` and `unsound = "all"` (cargo-deny
  0.20.2 defaults `unsound` to `workspace`, which skips transitive crates; added 2026-10-31). `scripts/cargo-deny-all.sh`
  checks all 11 crates and refuses a crate list other than 11. `cargo-deny.yml` runs it, and
  `scripts.yml` runs the fixture controls, which prove the licence policy (whole-file pin
  removed 2026-10-31; see the amendment below).
- **LGPL compliance by embedded notices.** Every release attaches `THIRD-PARTY-NOTICES.txt`,
  built by `scripts/third-party-notices.sh`. For crates whose lockfile contains
  `gmp-mpfr-sys` it embeds the LGPL-3.0 and GPL-3.0 texts. It fails before the tag is pushed
  on a missing or unreadable lockfile or licence text, consistent with ADR-0026 (sign before
  publishing).

2026-10-31: `cargo-deny-all.sh` passes `--locked`; a `deny.toml` push runs root `make test` locally; no local real-crate run (offline cache measurements in the CI supply-chain bundle spec).

2026-10-31 (operator, to match etch-cli): the whole-file pin in `tests/test_deny_policy.py` is removed. The licence policy is proven by the `tests/fixtures/cargo-deny` controls (GPL and un-excepted LGPL rejected; MIT and `rug`, only through its exception, accepted). Settings fixtures cannot see are pinned by key: only the four sections `licenses`, `advisories`, `bans` and `sources`; `unsound`/`unmaintained` = "all" with no other `[advisories]` key but `ignore`; `[sources]` exactly `unknown-registry`/`unknown-git` = "deny"; and the LGPL exceptions exactly `rug` and `gmp-mpfr-sys`. A test keeps `deny.toml` the only advisory ignore list: no tracked workflow, script or Makefile passes `--ignore`. Other keys (`[bans]`, the allow list beyond what the fixtures exercise) are reviewed in their PR.

## Consequences

- A new licence or advisory ignore is an edit to `deny.toml` reviewed in its PR and must keep
  the fixture controls green; a new LGPL exception also changes `tests/test_deny_policy.py`
  (amended 2026-10-31, above).
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
