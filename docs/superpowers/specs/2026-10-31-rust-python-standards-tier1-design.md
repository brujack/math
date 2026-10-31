# Rust and Python standards audit, tier 1

- **Date:** 2026-10-31
- **Backlog row:** "Audit Python and Rust standards against current best practice" (P2, queued by the operator 2026-10-24)
- **Status:** Draft

## Problem

The backlog row asked for an audit of math's Rust and Python standards against current upstream guidance, a ranking of each gap, and the top tier applied uniformly to all 11 crates and 8 Python projects. This spec records the audit, the ranking, and the design for tier 1. Tiers 2 and 3 become Backlog rows that carry their measurements.

## Premise check (2026-10-31, master `e9f0807`)

The row's claims, checked with commands before design:

| Claim in the row                                               | Result                                                                                                                |
| -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| All crates on edition 2021, no `rust-version`                  | True: `grep '^edition' */*-rs/Cargo.toml` gives 11 × `2021`; 0 files contain `rust-version`.                          |
| Only two lints enabled                                         | True: `missing_debug_implementations` and `clippy::wrong_self_convention` (plus the `unexpected_cfgs` tarpaulin cfg). |
| No `unsafe_code = "forbid"`                                    | True. `git grep -c unsafe -- '*.rs'` finds no `unsafe` in any crate, so forbidding it costs nothing.                  |
| No `cargo deny`                                                | True: no `deny.toml`; `.github/workflows/cargo-audit.yml` runs `cargo audit` (advisories only).                       |
| `pytest`, `coverage`, `hypothesis`, `pip-audit` unpinned in CI | **False now.** Every site pins `name==X.Y.Z` and `tests/test_tool_pins.py` enforces one version per tool.             |
| pyright `standard`/`basic`                                     | **Partly stale.** All 9 configs are `standard`; `strict` is the open step.                                            |
| ruff rules narrow                                              | True, and worse than the row knew (see Research).                                                                     |

The row did not mention a licence gap, found while sizing cargo-deny: math is public (`gh repo view` → `PUBLIC`), publishes release binaries, has no `LICENSE` file, and no crate sets `license`. Five crates (`e`, `factorial`, `fib`, `perfect-numbers`, `pi`; the 5 whose `Cargo.lock` names `gmp-mpfr-sys`) statically link `rug` and `gmp-mpfr-sys`, both `LGPL-3.0+`, which bundle GMP, MPFR and MPC. `pi-v0.1.0` has shipped (2026-10-24) with no LGPL notice.

## Research summary

Primary sources, fetched 2026-10-31.

- **Edition 2024** shipped with Rust 1.85.0 (2025-02-20). No later edition exists; the edition team's 2026-09-29 minutes say a 2027 edition "in the old pattern won't happen". The Edition Guide's migration: `cargo fix --edition`, set the edition, build, `cargo fmt`; it recommends `style_edition` in `rustfmt.toml` because editors call `rustfmt` directly.
- **`rust-version`:** Cargo refuses an older toolchain, and edition 2024's default resolver (`"3"`) falls back to dependency versions compatible with it. The Cargo docs name `cargo-msrv` and do not distinguish binaries from libraries. A declared value that CI never builds with is an unchecked claim.
- **Clippy:** the book says not to enable `nursery` or `restriction` wholesale. `pedantic` is "prone to false positives"; common practice enables it at `priority = -1` with allows.
- **cargo-deny 0.20.2** (2026-07-09) runs four checks: advisories (RustSec, the same database as `cargo audit`), bans, licenses and sources. The maintainer's position (issue #386) is that it replaces `cargo audit` for anyone who also wants licence, ban or source checks.
- **ruff 0.16.0** (2026-07-23) raised the default rule set from 59 to 413 rules. math pins `ruff==0.16.4` but uses an explicit `select`, which replaces the defaults, so it receives none of them. Upstream guidance: "the default rule set is a great place to start", extended with `extend-select`.
- **pyright `strict`** adds the five `reportUnknown*` rules, `reportMissingTypeStubs`, missing-annotation and unused-code rules. mpmath ships no stubs.
- **`pyproject.toml` + lock (PEP 751 `pylock.toml`, uv):** supported for non-package repos, but no PyPA recommendation says a script repo should adopt it.

## Measurements

Taken in a throwaway clone of master `e9f0807` on `claude` (rustc 1.99.1, ruff 0.16.4, pyright 1.1.411). Population: all 11 crates and all 61 tracked `.py` files, unless a row says otherwise.

| Change                                                                                                 | Measured cost                                                                                                                                                                                                                                                                            |
| ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Edition 2024                                                                                           | `cargo fix --edition --all-targets` changed 0 source lines in 11 crates. With `edition = "2024"`, `cargo clippy --all-targets -- -D warnings` passes in 10; twin-primes fails on 1 `collapsible_if` (let-chains). `cargo fmt --check` fails in all 11 (2024 style-edition import order). |
| `unsafe_code = "forbid"`                                                                               | 0 `unsafe` occurrences.                                                                                                                                                                                                                                                                  |
| clippy `pedantic` + `nursery` + `unwrap_used` + `expect_used` + `rust_2018_idioms` + `unreachable_pub` | 1,024 warnings across 11 crates; 729 are `unwrap_used`/`expect_used` (mostly tests, which `--all-targets` includes). The rest are mostly casts, `uninlined_format_args` and `must_use`. Not split by group.                                                                              |
| pyright `strict`                                                                                       | 2,412 errors: root scope 1,153, pi 521, e 476, the other 6 between 22 and 57. Almost all are `reportUnknown*`.                                                                                                                                                                           |
| ruff upstream defaults plus today's extras (`extend-select`)                                           | 88 findings, 75 in tests: SIM117 41, EXE001 28, E402 3, ISC004 3, FURB167 3, SIM114 3, SIM113 2, others 1 each.                                                                                                                                                                          |
| ruff `ALL`                                                                                             | 5,980 findings, about 85% in tests (PT009 1,435; ANN; D).                                                                                                                                                                                                                                |
| Dependency licences                                                                                    | Every dependency of the 11 crates is MIT, Apache-2.0, Apache-2.0 WITH LLVM-exception, BSD-2-Clause, Unlicense, Zlib or Unicode-3.0 (or an OR of these), except `rug` and `gmp-mpfr-sys` (`LGPL-3.0+`). `r-efi` is `MIT OR Apache-2.0 OR LGPL-2.1-or-later`, satisfied by MIT.            |

## Ranking

| Tier         | Gap                                                                               | Why this tier                                                                                                                            |
| ------------ | --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| 1            | Edition 2024, `rust-version` with a CI check, `style_edition`                     | Current edition; measured near-zero source change.                                                                                       |
| 1            | `unsafe_code = "forbid"`                                                          | Free, and closes a class permanently.                                                                                                    |
| 1            | MIT licence, cargo-deny replacing cargo-audit, LGPL notices in the 5 GMP releases | A public repo shipping LGPL-linked binaries without the notice is a live compliance gap; cargo-deny keeps the licence set from drifting. |
| 1            | ruff upstream defaults via `extend-select`                                        | 88 findings for 413 curated rules.                                                                                                       |
| 2 (Backlog)  | clippy `pedantic` at `priority = -1` with allows                                  | About 300 warnings needing per-lint judgment.                                                                                            |
| 2 (Backlog)  | `unwrap_used`/`expect_used` policy                                                | 729 hits, mostly tests; needs a test-code carve-out decision first.                                                                      |
| 3 (Backlog)  | pyright `strict`                                                                  | 2,412 errors, mostly from mpmath having no stubs; needs a stub or a typed boundary first.                                                |
| Rejected     | `pyproject.toml` + lock                                                           | No upstream recommendation for non-package repos; pins are already enforced by `test_tool_pins.py`.                                      |
| Rejected     | ruff family-wide `D`, `ANN`, `PT`, `S`                                            | About 4,000 findings, mostly in tests; the defaults already carry the curated subsets (PT 6, S 3, D 1).                                  |
| Out of scope | Cargo workspace                                                                   | Rejected by the 2026-10-25 uniform-cargo spec.                                                                                           |

## Design

Three PRs. Each is independently revertible and lands all 11 crates (or all Python) at once, so no window has some projects on the new standard and others off (operator rule: all crates treated identically).

### PR 1: Rust manifests

- Every `*-rs/Cargo.toml`: `edition = "2024"`, `rust-version = "<MSRV>"`, and `[lints.rust] unsafe_code = "forbid"`.
- `<MSRV>` is measured during implementation: the lowest stable toolchain, at or above 1.85 (edition 2024's floor), on which all 11 crates pass `cargo check --locked --all-targets`. The spec does not guess it.
- `scripts/crate_templates/rustfmt.toml` gains `style_edition = "2024"`, rendered to 11. `cargo fmt` is run in all 11 crates.
- twin-primes: collapse the one `if` that clippy flags under 2024.
- `scripts/crate_templates/ci.yml` gains an `msrv` job, rendered to 11 `*-rs.yml`. It reads `rust-version` from the crate's `Cargo.toml`, installs that toolchain through the SHA-pinned `dtolnay/rust-toolchain` action, and runs `cargo check --locked --all-targets`. It restores the GMP cache the same way the other jobs do. It does not need the `test` job.
- `tests/test_crate_uniformity.py` pins the edition, the presence and equality of `rust-version` across all 11, and `unsafe_code = "forbid"`. Its existing `[lints]` equality check already rejects drift.

### PR 2: licence, cargo-deny and LGPL notices

- Root `LICENSE`: MIT, copyright Bruce Jackson. Every `Cargo.toml` gets `license = "MIT"`.
- Root `deny.toml`, shared by all 11 crates:
  - `[licenses] allow` lists exactly the measured set: MIT, Apache-2.0, Apache-2.0 WITH LLVM-exception, BSD-2-Clause, Unlicense, Zlib, Unicode-3.0.
  - `LGPL-3.0-or-later` is allowed through `[[licenses.exceptions]]` for `rug` and `gmp-mpfr-sys` only, never in the global list.
  - `[advisories]`, `[bans]` and `[sources]` are enabled. `sources` allows crates.io only.
- `.github/workflows/cargo-deny.yml` replaces `cargo-audit.yml`. It keeps the same triggers (pull_request on `**/Cargo.toml`, `**/Cargo.lock` and its own path, plus the weekly cron), adds `deny.toml` to `paths`, installs `cargo-deny@0.20.2` through the pinned `taiki-e/install-action` with `fallback: none`, and runs `cargo deny --manifest-path <crate>/Cargo.toml check --config deny.toml` for each of the 11 crates, failing if any crate fails.
- LGPL notices. A new `scripts/third-party-notices.sh <crate-dir> <out-dir>` writes `<out-dir>/THIRD-PARTY-NOTICES.txt` for every crate.
  - When the crate's `Cargo.lock` names `gmp-mpfr-sys`, the file names GMP, MPFR, MPC, `rug` and `gmp-mpfr-sys` with their locked versions, states that they are under LGPL-3.0-or-later, and says where the corresponding source is (this repository at the release tag, and the `gmp-mpfr-sys` crate on crates.io, which bundles the C sources). The script also copies `licenses/LGPL-3.0.txt` and `licenses/GPL-3.0.txt` (LGPL-3.0 incorporates GPL-3.0 by reference) into `<out-dir>`.
  - Otherwise the file says the binary links no LGPL components.
  - The script exits non-zero when the lockfile is missing or unreadable, so a release never ships without a notice.
- `scripts/crate_templates/release.yml` runs the script after the build and attaches `THIRD-PARTY-NOTICES.txt` to every release. The two licence texts are attached when present. The rendered workflow is identical for all 11; which crates carry LGPL text is decided by the lockfile, not by the template.
- Positive controls in the test suite: a fixture crate whose own `license` is `GPL-3.0-only` must fail `cargo deny check licenses` under `deny.toml`, and a fixture crate named other than `rug`/`gmp-mpfr-sys` declaring `LGPL-3.0-or-later` must also fail, proving the exception is scoped. The fixtures use path dependencies only, so they run offline. The bats or Python tests for `third-party-notices.sh` cover the GMP lockfile, a non-GMP lockfile, and a missing lockfile.

### PR 3: ruff defaults

- `ruff.toml`: `select = [...]` becomes `extend-select = [...]` with the same extras, so the pinned ruff's default set applies. `ignore`, `unfixable` and `per-file-ignores` stay.
- Fix the 88 findings. A finding is ignored, rather than fixed, only per file with a comment giving the reason (for example EXE001 on a test module that carries a shebang but is not meant to be executed: remove the shebang instead where nothing runs it directly).
- The default set changes only when the ruff pin is bumped, which `tests/test_tool_pins.py` already gates, so the lint set stays deterministic between bumps.

## Error handling

- `msrv` job: a toolchain that cannot be installed, or a `rust-version` that cannot be read, fails the job. It never falls back to stable.
- cargo-deny: a crate that fails any check fails the workflow after every crate has been checked, so one run reports all failures.
- `third-party-notices.sh`: fails closed on a missing lockfile or an unwritable output directory; the release stops before the tag is pushed, because the step sits before `Create and push tag`.

## Testing

- PR 1: uniformity tests for edition, `rust-version` and `forbid`; a workflow test that every `*-rs.yml` has the `msrv` job reading `rust-version` from `Cargo.toml`; the full crate matrix (`make test-rust`) green under edition 2024.
- PR 2: the two cargo-deny positive controls; notices-script tests for three lockfile cases; a release-workflow test that the notices step precedes the tag step and its output is in `files:`; the existing `fail_on_unmatched_files: true` check stays.
- PR 3: root `make lint` green; a test that `ruff.toml` uses `extend-select` and not `select`.

## Requirements

- **R1.** `[PR1]` All 11 `*-rs/Cargo.toml` files declare `edition = "2024"`, one identical `rust-version`, and `[lints.rust] unsafe_code = "forbid"`, and `tests/test_crate_uniformity.py` fails when any of the three is missing or differs.
- **R2.** `[PR1]` The declared `rust-version` is at least `1.85`, and every rendered `*-rs.yml` has an `msrv` job that installs the toolchain named by the crate's `rust-version` and runs `cargo check --locked --all-targets`.
- **R3.** `[PR1]` `scripts/crate_templates/rustfmt.toml` sets `style_edition = "2024"` and all 11 crates pass `cargo fmt --check`.
- **R4.** `[PR2]` A root `LICENSE` file holds the MIT licence and every `*-rs/Cargo.toml` sets `license = "MIT"`.
- **R5.** `[PR2]` A root `deny.toml` allows exactly MIT, Apache-2.0, Apache-2.0 WITH LLVM-exception, BSD-2-Clause, Unlicense, Zlib and Unicode-3.0 globally, and allows `LGPL-3.0-or-later` only as exceptions for `rug` and `gmp-mpfr-sys`.
- **R6.** `[PR2]` `cargo-deny.yml` replaces `cargo-audit.yml`, runs `cargo deny check` on all 11 crates with the root `deny.toml`, installs `cargo-deny@0.20.2` through the pinned `taiki-e/install-action` with `fallback: none`, and keeps the weekly cron.
- **R7.** `[PR2]` Tests show `cargo deny check licenses` fails on a fixture crate licensed `GPL-3.0-only` and on a fixture crate not named `rug` or `gmp-mpfr-sys` licensed `LGPL-3.0-or-later`.
- **R8.** `[PR2]` `scripts/third-party-notices.sh` writes `THIRD-PARTY-NOTICES.txt` for every crate, copies `LGPL-3.0.txt` and `GPL-3.0.txt` only when the crate's `Cargo.lock` names `gmp-mpfr-sys`, and exits non-zero when the lockfile is missing.
- **R9.** `[PR2]` Every rendered `release-*-rs.yml` runs the notices script before `Create and push tag` and attaches `THIRD-PARTY-NOTICES.txt` to the release.
- **R10.** `[PR3]` `ruff.toml` uses `extend-select` (no `select` key) and root `make lint` passes.
- **V1.** The `msrv` job passes on the PR 1 CI run for all 11 crates.
- **V2.** `cargo-deny.yml` passes on the PR 2 CI run for all 11 crates.
- **V3.** The next release of one of the 5 GMP crates carries `THIRD-PARTY-NOTICES.txt`, `LGPL-3.0.txt` and `GPL-3.0.txt`, and the next release of a non-GMP crate carries `THIRD-PARTY-NOTICES.txt` only.
- **V4.** The operator decides whether to attach the notice files to the existing `pi-v0.1.0` release; nothing is uploaded to an existing release without that "yes".
- **N1.** No clippy `pedantic`, `nursery`, `restriction`, `unwrap_used` or `expect_used` lint is enabled.
- **N2.** No pyright config changes from `standard`.
- **N3.** No `pyproject.toml`, `uv.lock` or `pylock.toml` is added.
- **N4.** No Cargo workspace is introduced.
- **N5.** No per-crate difference in any templated or uniformity-tested file, other than which crates' releases carry LGPL text, which the lockfile decides.
- **N6.** No ruff rule family is added beyond the upstream defaults and today's extras.
