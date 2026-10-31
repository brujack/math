# Rust and Python standards audit, tier 1

- **Date:** 2026-10-31
- **Backlog row:** "Audit Python and Rust standards against current best practice" (P2, queued by the operator 2026-10-24)
- **Status:** Approved
- **Approved:** 2026-10-31

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

The row did not mention a licence gap, found while sizing cargo-deny. math is public (`gh repo view` → `PUBLIC`), publishes release binaries, has no `LICENSE` file, and no crate sets `license`. Five crates (`e`, `factorial`, `fib`, `perfect-numbers`, `pi`: the 5 whose `Cargo.lock` names `gmp-mpfr-sys`) link `rug` and `gmp-mpfr-sys`, both `LGPL-3.0+`, which bundle GMP, MPFR and MPC. All five shipped `v0.1.0` on 2026-10-24 (`gh release list`) with no LGPL notice. The link is static: `ldd` on the released `pi` binary lists only `libc`, `libm`, `libgcc_s` and the loader, and the binary contains GMP's `GNU MP` strings.

## Research summary

Primary sources, fetched 2026-10-31.

- **Edition 2024** shipped with Rust 1.85.0 (2025-02-20). No later edition exists; the edition team's 2026-09-29 minutes say a 2027 edition "in the old pattern won't happen". The Edition Guide's migration: `cargo fix --edition`, set the edition, build, `cargo fmt`; it recommends `style_edition` in `rustfmt.toml` because editors call `rustfmt` directly.
- **`rust-version`:** Cargo refuses an older toolchain, and edition 2024's default resolver (`"3"`) falls back to dependency versions compatible with it. The Cargo docs name `cargo-msrv` and do not distinguish binaries from libraries.
- **Clippy:** the book says not to enable `nursery` or `restriction` wholesale. `pedantic` is "prone to false positives"; common practice enables it at `priority = -1` with allows.
- **cargo-deny 0.20.2** (2026-07-09) runs four checks: advisories (RustSec, the same database as `cargo audit`, plus unmaintained and yanked crates), bans, licenses and sources. The maintainer's position (issue #386) is that it replaces `cargo audit` for anyone who also wants licence, ban or source checks. `--config` is a top-level flag: `cargo deny --config deny.toml --manifest-path <crate>/Cargo.toml check`. Placing it after `check` exits 2 (`unexpected argument '--config'`), measured on 0.20.2.
- **ruff 0.16.0** (2026-07-23) raised the default rule set from 59 to 413 rules. math pins `ruff==0.16.4` but uses an explicit `select`, which replaces the defaults, so it receives none of them. Upstream guidance: "the default rule set is a great place to start", extended with `extend-select`.
- **pyright `strict`** adds the five `reportUnknown*` rules, `reportMissingTypeStubs`, missing-annotation and unused-code rules. mpmath ships no stubs.
- **`pyproject.toml` + lock (PEP 751 `pylock.toml`, uv):** supported for non-package repos, but no PyPA recommendation says a script repo should adopt it.

## Measurements

Taken in a throwaway clone of master `e9f0807` on `claude` (rustc 1.99.1, ruff 0.16.4, pyright 1.1.411, cargo-deny 0.20.2). Population: all 11 crates and all 61 tracked `.py` files, unless a row says otherwise.

| Change                                                                                                 | Measured cost                                                                                                                                                                                                                                                                            |
| ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Edition 2024                                                                                           | `cargo fix --edition --all-targets` changed 0 source lines in 11 crates. With `edition = "2024"`, `cargo clippy --all-targets -- -D warnings` passes in 10; twin-primes fails on 1 `collapsible_if` (let-chains). `cargo fmt --check` fails in all 11 (2024 style-edition import order). |
| `unsafe_code = "forbid"`                                                                               | 0 `unsafe` occurrences.                                                                                                                                                                                                                                                                  |
| clippy `pedantic` + `nursery` + `unwrap_used` + `expect_used` + `rust_2018_idioms` + `unreachable_pub` | 1,024 warnings across 11 crates; 729 are `unwrap_used`/`expect_used` (mostly tests, which `--all-targets` includes). The rest are mostly casts, `uninlined_format_args` and `must_use`. Not split by group.                                                                              |
| pyright `strict`                                                                                       | 2,412 errors: root scope 1,153, pi 521, e 476, the other 6 between 22 and 57. Almost all are `reportUnknown*`.                                                                                                                                                                           |
| ruff upstream defaults plus today's extras (`extend-select`, existing `per-file-ignores` kept)         | 85 findings, about 72 in tests: SIM117 41, EXE001 28, ISC004 3, FURB167 3, SIM114 3, SIM113 2, others 1 each. (A first count of 88 omitted the `tests/**` E402 ignore.)                                                                                                                  |
| ruff `ALL`                                                                                             | 5,980 findings, about 85% in tests (PT009 1,435; ANN; D).                                                                                                                                                                                                                                |
| Dependency licences                                                                                    | Every dependency of the 11 crates is MIT, Apache-2.0, Apache-2.0 WITH LLVM-exception, BSD-2-Clause, Unlicense, Zlib or Unicode-3.0 (or an OR of these), except `rug` and `gmp-mpfr-sys` (`LGPL-3.0+`). `r-efi` is `MIT OR Apache-2.0 OR LGPL-2.1-or-later`, satisfied by MIT.            |
| cargo-deny advisories, default config                                                                  | `cargo deny check advisories` prints `advisories ok` and exits 0 in all 11 crates (default `unmaintained` scope).                                                                                                                                                                        |

## Ranking

| Tier         | Gap                                                                               | Why this tier                                                                                                                    |
| ------------ | --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| 1            | Edition 2024 and `style_edition`                                                  | Current edition; measured near-zero source change.                                                                               |
| 1            | `unsafe_code = "forbid"`                                                          | Free, and closes a class permanently.                                                                                            |
| 1            | MIT licence, cargo-deny replacing cargo-audit, LGPL notices in the 5 GMP releases | Five public LGPL-linked binaries ship without the notice: a live compliance gap. cargo-deny keeps the licence set from drifting. |
| 1            | ruff upstream defaults via `extend-select`                                        | 85 findings for 413 curated rules.                                                                                               |
| 2 (Backlog)  | clippy `pedantic` at `priority = -1` with allows                                  | About 300 warnings needing per-lint judgment.                                                                                    |
| 2 (Backlog)  | `unwrap_used`/`expect_used` policy                                                | 729 hits, mostly tests; needs a test-code carve-out decision first.                                                              |
| 3 (Backlog)  | pyright `strict`                                                                  | 2,412 errors, mostly from mpmath having no stubs; needs a stub or a typed boundary first.                                        |
| Rejected     | `rust-version` and an MSRV CI job                                                 | See below.                                                                                                                       |
| Rejected     | `pyproject.toml` + lock                                                           | No upstream recommendation for non-package repos; pins are already enforced by `test_tool_pins.py`.                              |
| Rejected     | ruff family-wide `D`, `ANN`, `PT`, `S`                                            | About 4,000 findings, mostly in tests; the defaults already carry the curated subsets (PT 6, S 3, D 1).                          |
| Out of scope | Cargo workspace                                                                   | Rejected by the 2026-10-25 uniform-cargo spec.                                                                                   |

### Why no `rust-version`

The first draft declared the lowest passing toolchain and gated every PR on an `msrv` job. Review rejected it on two independent grounds, and the operator agreed (2026-10-31):

- **Nothing reads it.** `rust-version` protects someone building from source on an older toolchain. math ships binaries built on stable, publishes nothing to crates.io, and its crates have no consumers (the same reason CLAUDE.md gives for not enabling `missing_docs`).
- **It would stall Renovate.** Every dependency is a caret range, so Renovate's cargo updates are lock-only `--precise` bumps grouped into one auto-merged PR. `--precise` bypasses resolver 3's MSRV fallback, so the first dependency release that raises its own `rust-version` past ours would fail the gate, block the whole group, and require a hand PR bumping all 11 crates. The current lock already sits on the floor: `clap_builder` 4.6 declares `rust-version = "1.85"`, edition 2024's minimum.

## Design

Three PRs. Each is independently revertible and lands all 11 crates (or all Python) at once, so no window has some projects on the new standard and others off (operator rule: all crates treated identically).

### PR 1: Rust manifests

- Every `*-rs/Cargo.toml`: `edition = "2024"` and `[lints.rust] unsafe_code = "forbid"`.
- `scripts/crate_templates/rustfmt.toml` gains `style_edition = "2024"`, rendered to 11. `cargo fmt` is run in all 11 crates.
- twin-primes: collapse the one `if` that clippy flags under 2024.
- `tests/test_crate_uniformity.py` pins the edition and `unsafe_code = "forbid"`, and fails if any crate declares `rust-version`. Its existing `[lints]` equality check already rejects drift.

### PR 2: licence, cargo-deny and LGPL notices

- Root `LICENSE`: MIT, copyright Bruce Jackson. Every `Cargo.toml` gets `license = "MIT"`.
- Root `deny.toml`, shared by all 11 crates:
  - `[licenses] allow` lists exactly the measured set: MIT, Apache-2.0, Apache-2.0 WITH LLVM-exception, BSD-2-Clause, Unlicense, Zlib, Unicode-3.0.
  - `LGPL-3.0-or-later` is allowed through `[[licenses.exceptions]]` for `rug` and `gmp-mpfr-sys` only, never in the global list.
  - `[advisories]` sets `unmaintained = "all"` explicitly. That is cargo-deny 0.20.2's default (`src/advisories/cfg.rs:281`) and the scope at which all 11 crates measured clean; setting it explicitly means a cargo-deny release that changes the default cannot change the gate silently. A new unmaintained notice on any dependency, direct or transitive, fails the PR that surfaces it, including a Renovate group PR; the remedy is an `[advisories] ignore` entry the operator approves (N7). `"workspace"` was rejected: it emits no diagnostic at all for a crate reached only through other dependencies, so transitive notices `cargo audit` shows today would go silent.
  - `[bans]` and `[sources]` are enabled; `sources` allows crates.io only.
- A dependency that arrives under a licence not on the list fails the PR that brings it, including a Renovate group PR. That is intended: the remedy is a one-line `deny.toml` edit the operator approves, never a widening of the list by an agent on its own judgment.
- `scripts/cargo-deny-all.sh` runs `cargo deny --config deny.toml --manifest-path <crate>/Cargo.toml check` for every crate in `git ls-files '*/*-rs/Cargo.toml'`. It checks every crate before exiting, exits non-zero if any crate fails, and exits non-zero when the crate list is empty or holds fewer than 11 entries, so a run that checked nothing is never green.
- `.github/workflows/cargo-deny.yml` replaces `cargo-audit.yml`. It keeps the same triggers (pull_request on `**/Cargo.toml`, `**/Cargo.lock` and its own path, plus the weekly cron), adds `deny.toml` and the script to `paths`, installs `cargo-deny@0.20.2` through the pinned `taiki-e/install-action` with `fallback: none`, and runs `scripts/cargo-deny-all.sh`.
- Positive controls run in `scripts.yml`, which also installs `cargo-deny@0.20.2` the same way and adds `deny.toml` and `tests/fixtures/cargo-deny/**` to its `paths`, so an allow-list edit re-runs them. Three fixture crates live at `tests/fixtures/cargo-deny/<name>/` (`gpl`, `lgpl`, `mit`), with no `-rs` path segment, because `git ls-files '*/*-rs/Cargo.toml'` lets `*` cross `/` and would otherwise add a fixture to every crate list. Each test copies its fixture to `BATS_TEST_TMPDIR` (cargo-deny writes a `Cargo.lock` beside the manifest) and runs `cargo deny --config <repo>/deny.toml --manifest-path <copy>/Cargo.toml check licenses` only, which needs no network:
  - a crate whose own `license` is `GPL-3.0-only`: must fail, and the output must carry cargo-deny's rejection diagnostic naming that licence;
  - a crate not named `rug` or `gmp-mpfr-sys` declaring `LGPL-3.0-or-later`: must fail with the same diagnostic, proving the exception is scoped;
  - a crate licensed `MIT`: must pass, proving the command and config are well-formed.
    A non-zero exit without the diagnostic fails the test, so a malformed command, a missing binary or a missing `deny.toml` cannot pass as a rejection. When cargo-deny is absent outside CI the tests print a skip line; in CI they fail.
- A test parses `deny.toml` and compares the whole structure with one expected value held in the test, so every key is pinned: the allow-list, exceptions, `unmaintained`, `ignore`, and any `clarify`, `private`, `bans` or `sources` setting (a `[[licenses.clarify]]` entry could otherwise relabel a GPL crate as MIT without touching the allow-list). Any change to `deny.toml` is therefore also an edit to that test, which the operator approves (N7).
- A test asserts `git ls-files '*/*-rs/Cargo.toml'` returns exactly the 11 crate manifests, so a fixture or stray manifest cannot join the crate list.
- LGPL notices. A new `scripts/third-party-notices.sh <crate-dir> <out-dir>` writes exactly one file, `<out-dir>/THIRD-PARTY-NOTICES.txt`, for every crate. `<out-dir>` is a dedicated directory the release job creates, not `target/release`.
  - When the crate's `Cargo.lock` names `gmp-mpfr-sys`, the file names GMP, MPFR, MPC, `rug` and `gmp-mpfr-sys` with their locked versions, states that they are under LGPL-3.0-or-later and statically linked, and says where the corresponding source is: this repository at the release tag (the MIT application source, sufficient to relink) and the `gmp-mpfr-sys` crate on crates.io (which bundles the C sources). It states that both locations must remain available. The file then embeds the full texts of `licenses/LGPL-3.0.txt` and `licenses/GPL-3.0.txt` (LGPL-3.0 §4(b) requires both to accompany the binary; it does not require separate files).
  - Otherwise the file says the binary links no LGPL components and embeds no licence text.
  - The script exits non-zero when the lockfile is missing or unreadable, when a GMP crate's licence texts are missing from `licenses/` or empty, or when the output directory is unwritable.
- `scripts/crate_templates/release.yml` runs the script after the build and before `Create and push tag`, so a notices failure stops the release before any tag exists. `files:` gains one exact path, `<out-dir>/THIRD-PARTY-NOTICES.txt`, which exists for every crate, so `fail_on_unmatched_files: true` can never fire on it and no glob or conditional step is needed. The rendered workflow is identical for all 11; the lockfile decides which crates' notices embed the LGPL text.
- The 5 already-published `v0.1.0` releases are handled under V4.

### PR 3: ruff defaults

- `ruff.toml`: `select = [...]` becomes `extend-select = [...]` with the same extras, so the pinned ruff's default set applies. `ignore`, `unfixable` and `per-file-ignores` stay.
- Fix the 85 findings. A finding is ignored, rather than fixed, only per file with a comment giving the reason. For EXE001 (a shebang on a file without the executable bit), remove the shebang where nothing runs the file directly.
- The default set changes only when the ruff pin is bumped by hand (Renovate's `enabledManagers` are `github-actions` and `cargo`). The bump PR's own `make lint` is the gate for new defaults; `tests/test_tool_pins.py` only keeps the version identical at every site.

## Error handling

- `cargo-deny-all.sh`: a crate that fails any check fails the run after every crate has been checked, so one run reports all failures; an empty or short crate list fails.
- `third-party-notices.sh`: fails closed on a missing lockfile, missing or empty licence texts for a GMP crate, or an unwritable output directory. The release stops before the tag is pushed.
- cargo-deny and the edition change are CI-only gates for a developer on current stable: `make lint` does not run cargo-deny. Stated so nobody assumes pre-push catches a licence violation.

## Testing

- PR 1: uniformity tests for edition, `unsafe_code = "forbid"` and the absence of `rust-version` (and in PR 2, `license = "MIT"`, so a 12th crate missing it fails locally rather than only in CI); the full crate matrix (`make test-rust`) green under edition 2024.
- PR 2: the three cargo-deny fixtures, asserting the diagnostic for the two rejections and exit 0 for the MIT fixture; the `deny.toml` policy test; the exact-11 crate-list test; `cargo-deny-all.sh` tests for an empty list, a short list and one failing crate among passing ones (PATH-mocked `cargo`); notices-script tests for a GMP lockfile (asserting the locked `gmp-mpfr-sys` and `rug` versions, the LGPL-3.0-or-later wording, and a line unique to each embedded licence text), a non-GMP lockfile (no licence text embedded), a missing lockfile, and a GMP lockfile with a licence text missing or empty, each asserting the script wrote only `THIRD-PARTY-NOTICES.txt`; a release-workflow test that the notices step precedes the tag step and `files:` lists its output by exact path with no glob; the existing `fail_on_unmatched_files: true` check stays.
- PR 3: root `make lint` green; a test that `ruff.toml` uses `extend-select` and not `select`.

## Requirements

- **R1.** `[PR1]` All 11 `*-rs/Cargo.toml` files declare `edition = "2024"` and `[lints.rust] unsafe_code = "forbid"` and no `rust-version`, and `tests/test_crate_uniformity.py` fails when either declaration is missing or differs, or when any crate declares `rust-version`.
- **R2.** `[PR1]` No workflow gains a job that installs a toolchain other than stable for an MSRV check.
- **R3.** `[PR1]` `scripts/crate_templates/rustfmt.toml` sets `style_edition = "2024"` and all 11 crates pass `cargo fmt --check`.
- **R4.** `[PR2]` A root `LICENSE` file holds the MIT licence, every `*-rs/Cargo.toml` sets `license = "MIT"`, and `tests/test_crate_uniformity.py` fails when one does not.
- **R5.** `[PR2]` A root `deny.toml` allows exactly MIT, Apache-2.0, Apache-2.0 WITH LLVM-exception, BSD-2-Clause, Unlicense, Zlib and Unicode-3.0 globally, allows `LGPL-3.0-or-later` only as exceptions for `rug` and `gmp-mpfr-sys`, sets `[advisories] unmaintained = "all"` with no `ignore` entries, and a test fails when any part of the parsed `deny.toml` differs from the structure the test expects.
- **R6.** `[PR2]` `cargo-deny.yml` replaces `cargo-audit.yml`, installs `cargo-deny@0.20.2` through the pinned `taiki-e/install-action` with `fallback: none`, runs `scripts/cargo-deny-all.sh`, and keeps the weekly cron; the script passes `--config` before `check` and exits non-zero on an empty or short crate list or any failing crate.
- **R7.** `[PR2]` Fixtures live under `tests/fixtures/cargo-deny/` with no `-rs` path segment, a test asserts `git ls-files '*/*-rs/Cargo.toml'` returns exactly the 11 crates, and tests run in `scripts.yml` with cargo-deny installed, using `check licenses` on a copy in `BATS_TEST_TMPDIR`, and show a `GPL-3.0-only` fixture and a non-`rug`/`gmp-mpfr-sys` `LGPL-3.0-or-later` fixture each fail with cargo-deny's licence-rejection diagnostic, and an `MIT` fixture passes.
- **R8.** `[PR2]` `scripts/third-party-notices.sh` writes exactly one file, `THIRD-PARTY-NOTICES.txt`, for every crate; when the crate's `Cargo.lock` names `gmp-mpfr-sys` it names the locked `gmp-mpfr-sys` and `rug` versions and LGPL-3.0-or-later and embeds the full LGPL-3.0 and GPL-3.0 texts, and otherwise embeds no licence text; it exits non-zero when the lockfile is missing or a required licence text is missing or empty.
- **R9.** `[PR2]` Every rendered `release-*-rs.yml` runs the notices script before `Create and push tag` and lists `THIRD-PARTY-NOTICES.txt` in `files:` by exact path, with no glob.
- **R10.** `[PR3]` `ruff.toml` uses `extend-select` (no `select` key) and root `make lint` passes.
- **V1.** `cargo-deny.yml` passes on the PR 2 CI run, and its log shows all 11 crates checked.
- **V2.** The next release of one of the 5 GMP crates carries one `THIRD-PARTY-NOTICES.txt` embedding the LGPL-3.0 and GPL-3.0 texts, and the next release of a non-GMP crate carries one `THIRD-PARTY-NOTICES.txt` with no licence text.
- **V3.** The PR 2 CI log of `scripts.yml` shows the three cargo-deny fixture tests ran (not skipped).
- **V4.** The operator decides how to remediate the five published `v0.1.0` releases of `e`, `factorial`, `fib`, `perfect-numbers` and `pi` (attach the notice files, re-release, or withdraw); nothing is uploaded to or removed from an existing release without that "yes".
- **V5.** The `math-new-cli` skill (owned by ai-config) scaffolds `edition = "2024"`, `unsafe_code = "forbid"` and `license = "MIT"`; requested from the ai-config session by message, since that repo is outside this diff.
- **N1.** No clippy `pedantic`, `nursery`, `restriction`, `unwrap_used` or `expect_used` lint is enabled.
- **N2.** No pyright config changes from `standard`.
- **N3.** No `pyproject.toml`, `uv.lock` or `pylock.toml` is added.
- **N4.** No Cargo workspace is introduced.
- **N5.** No per-crate difference in any templated or uniformity-tested file, other than which crates' releases carry LGPL text, which the lockfile decides.
- **N6.** No ruff rule family is added beyond the upstream defaults and today's extras.
- **N7.** No licence, exception or `[advisories] ignore` entry is added to `deny.toml` beyond the R5 set without the operator's approval.

## Multi-Lens Review

Reviewed at commit: `0350122` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: (1) The premise named only `pi-v0.1.0`; all five GMP crates shipped `v0.1.0` on 2026-10-24, so V4 left four non-compliant binaries unaddressed. (2) The `msrv` job fails the reads-it test: nothing builds from source on an older toolchain, there are no consumers, its output lives only in CI logs, and as a required check it forces an 11-crate bump whenever a dependency raises its MSRV. (3) Several PASS cases pass on empty input: the deny loop on zero crates, an empty notices file, and R7's fixtures exercise `deny.toml`, not the workflow loop. (4) The ruff count is 85, not 88. Not raised: LGPL §4(d) relinking (MIT source at the tag suffices), the crates.io source pointer, the unused `libgmp-dev` in the release job, the tier 2/3 ranking.
Assumption: The bundled `gmp-mpfr-sys` build is what ships (GMP/MPFR/MPC static in the binary); confirm with `ldd` on a downloaded release binary. Checked by the orchestrator: `ldd` on `pi-v0.1.0`'s `pi` lists no GMP library, and the binary contains `GNU MP` strings, so the link is static.
Disposition: Addressed (operator, 2026-10-31): V4 covers all five releases; `rust-version` and the `msrv` job dropped, with the reasons recorded under "Why no `rust-version`"; crate-count guard, content assertions and a passing fixture added; count corrected to 85.

### Ergonomics

Finding: Gating on the lowest passing MSRV stalls Renovate's grouped auto-merge: caret ranges make cargo updates lock-only `--precise` bumps, which bypass resolver 3's fallback, so the first dependency raising its MSRV fails the gate, blocks the group PR, and needs a hand PR across 11 crates; `clap_builder` 4.6 already declares 1.85. Secondary: cargo-deny's `unmaintained` is stricter than cargo-audit and was not measured; the exact licence allow-list will block a group PR when a new licence appears, and the spec should name the remedy; the claim that `test_tool_pins.py` gates new ruff defaults is loose; cargo-deny is CI-only; R7 needs the rejection diagnostic, not a bare non-zero exit; V1 would pass if `rust-version` read empty and fell back to stable.
Assumption: Renovate's grouped cargo PRs rarely need a toolchain newer than the declared MSRV; refuted or confirmed by how often clap, rayon and tempfile raise `rust-version`. Moot once the MSRV gate is dropped.
Disposition: Addressed (operator, 2026-10-31): MSRV gate dropped; `cargo deny check advisories` measured clean in all 11 crates and `unmaintained` set explicitly; the operator-approved `deny.toml` edit is named as the remedy (N7); ruff gate wording corrected; CI-only scope stated; R7 asserts the diagnostic.

### Risk

Finding: (1) Attaching the licence texts from an identical template is either fail-open (a glob) or fails after the tag (exact paths with `fail_on_unmatched_files` on the 6 non-GMP crates); nothing failed closed on a missing licence text. (2) The spec's cargo-deny command (`check --config`) exits 2 on 0.20.2, and both R7 controls expect failure, so they pass on a malformed command, a missing binary or a missing `deny.toml`; `scripts.yml` installs no cargo-deny. With the corrected command and the spec's `deny.toml`, all 11 crates pass all four checks. (3) LGPL §4(d)(0) is satisfiable (MIT source at the tag), but the notice should state that the repository and crates.io must stay available. Not raised: GMP cache under an older toolchain, edition 2024 drop order (only `io::stdout().lock()` tail temporaries), cargo-audit removal (cargo-deny is stricter), release build without `--locked`. Process note: the lens ran one `sed -i` in the main checkout after a failed `cd`, adding `license = "MIT"` to 11 `Cargo.toml` files, and reverted it; the orchestrator verified 0 porcelain lines and no `license` lines afterwards.
Assumption: The pinned `dtolnay/rust-toolchain` honours a `toolchain:` input from a step output. Moot once the MSRV job is dropped.
Disposition: Addressed (operator, 2026-10-31): the notices script fails closed on missing texts before the tag, and the glob is safe because of it; `--config` placement fixed, a passing MIT fixture and diagnostic assertions added, cargo-deny installed in `scripts.yml`; the notice states both source locations must stay available.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.

### Round 2 (all three lenses, reviewed at `0c22702`)

Goal-fit, Ergonomics and Risk each found, independently, that the round-1 `<out-dir>/*.txt` release glob rested on a false claim: it always matched `THIRD-PARTY-NOTICES.txt` itself, so every release listed that file twice (the pinned `softprops/action-gh-release` does not deduplicate and uploads concurrently), and narrowing it would fail the 6 non-GMP releases after the tag. Goal-fit and Risk found that `git ls-files '*/*-rs/Cargo.toml'` lets `*` cross `/`, so a fixture under a `*-rs` path would join every crate list. Risk found N7 unenforced and `scripts.yml` not triggered by `deny.toml`; Ergonomics found fixtures write a `Cargo.lock` in place, `unmaintained = "all"` would hard-block Renovate on transitive notices, N7 silent on `[advisories] ignore`, and the `math-new-cli` skill scaffolding none of the new fields. Assumptions: Risk asked whether cargo-deny maps `LGPL-3.0+` to `LGPL-3.0-or-later`; checked by the orchestrator with the exact R5 `deny.toml` (11/11 pass `check licenses`, rc 0; without the exceptions pi fails rc 4 with `error[rejected]` on `rug` and `gmp-mpfr-sys`). Goal-fit and Ergonomics asked about the glob's behaviour, which the revision removes.
Disposition: Addressed (operator, 2026-10-31): licence texts embedded in the single always-present notices file, attached by exact path; `unmaintained = "workspace"`; fixtures at `tests/fixtures/cargo-deny/<name>/` copied to `BATS_TEST_TMPDIR` and run with `check licenses`; exact-11 crate-list test; `deny.toml` policy test enforcing N7 (now covering exceptions and ignores); `scripts.yml` paths; local `license` check; V5 for the skill. Scoped re-review by one Risk lens over the changed sections.

### Round 3 (scoped Risk lens, reviewed at `54b82d2`)

Finding: (1) The spec called `unmaintained = "workspace"` cargo-deny's default; in 0.20.2 the default is `all` (`src/advisories/cfg.rs:281`), so the clean measurement was taken at `all`, and `workspace` emits no diagnostic for a crate reached only through other dependencies, silently dropping transitive notices `cargo audit` shows today. The operator's round-2 choice of `workspace` rested on that wrong claim. (2) The `deny.toml` policy test pinned the allow-list, exceptions and ignores but not `unmaintained`, `[[licenses.clarify]]`, `[licenses.private]`, `bans` or `sources`, so N7 had open allow-paths. Checked clean: `check licenses` on a copied path-only fixture runs offline and gives rc 4 with one `error[rejected]`; embedding the GPL text satisfies LGPL-3.0 §4(b); the exact-path `files:` entry cannot trip `fail_on_unmatched_files`; no R-versus-N contradiction.
Assumption: No crate in the 11 lockfiles has a RustSec unmaintained or unsound notice today; confirmed by the round-1 measurement at the default (`all`), which printed `advisories ok` in all 11.
Disposition: Addressed (operator, 2026-10-31, after the correction was put to them): `unmaintained = "all"` with operator-approved `ignore` entries as the remedy; the policy test compares the whole parsed `deny.toml`.

## Amendments

- finding R4 (2026-10-31, reviewer both): NOT-BUILT — No root LICENSE file is added, no Cargo.toml hunk sets license = "MIT", and no uniformity test checks license.
- R4 reviewed: built in PR 2 (Task 2) of the same plan; this branch is PR 1, which implements R1-R3 only — the plan splits the spec into three PRs by design.
- finding R5 (2026-10-31, reviewer both): NOT-BUILT — No root deny.toml and no test parsing it appear in the diff.
- R5 reviewed: built in PR 2 (Task 3) of the same plan; this branch is PR 1, which implements R1-R3 only — the plan splits the spec into three PRs by design.
- finding R6 (2026-10-31, reviewer both): NOT-BUILT — No cargo-deny.yml, no removal of cargo-audit.yml and no scripts/cargo-deny-all.sh appear in the diff.
- R6 reviewed: built in PR 2 (Task 4) of the same plan; this branch is PR 1, which implements R1-R3 only — the plan splits the spec into three PRs by design.
- finding R7 (2026-10-31, reviewer both): NOT-BUILT — No tests/fixtures/cargo-deny/ fixtures, no git ls-files crate-count test, no cargo-deny bats tests and no scripts.yml change appear in the diff.
- R7 reviewed: built in PR 2 (Task 3) of the same plan; this branch is PR 1, which implements R1-R3 only — the plan splits the spec into three PRs by design.
- finding R8 (2026-10-31, reviewer both): NOT-BUILT — No scripts/third-party-notices.sh appears in the diff.
- R8 reviewed: built in PR 2 (Task 5) of the same plan; this branch is PR 1, which implements R1-R3 only — the plan splits the spec into three PRs by design.
- finding R9 (2026-10-31, reviewer both): NOT-BUILT — No release-*-rs.yml or its template is changed to run a notices script or list THIRD-PARTY-NOTICES.txt.
- R9 reviewed: built in PR 2 (Task 6) of the same plan; this branch is PR 1, which implements R1-R3 only — the plan splits the spec into three PRs by design.
- finding R10 (2026-10-31, reviewer both): NOT-BUILT — ruff.toml is not changed in the diff; no extend-select replacement of select is present.
- R10 reviewed: built in PR 3 (Task 8) of the same plan; this branch is PR 1, which implements R1-R3 only — the plan splits the spec into three PRs by design.
- finding R1 (2026-10-31, reviewer both): NOT-BUILT — The diff adds no edition, `[lints.rust] unsafe_code = "forbid"` or rust-version change and no rust-version uniformity test. `edition = "2024"` and `test_every_crate_forbids_unsafe_code` show up only as unchanged context lines (Cargo.toml hunks, tests/test_crate_uniformity.py:328), so this diff does not show the forbid declarations or a test that fails on a `rust-version` key.
- R1 reviewed: built and merged in PR 1 (math#187, c398814); this branch is PR 2, which implements R4-R9 only — the plan splits the spec into three PRs by design.
- finding R3 (2026-10-31, reviewer both): NOT-BUILT — The diff has no hunk for `scripts/crate_templates/rustfmt.toml` and no `style_edition` text anywhere, so it does not show this requirement.
- R3 reviewed: built and merged in PR 1 (math#187, c398814); this branch is PR 2, which implements R4-R9 only — the plan splits the spec into three PRs by design.
- finding R10 (2026-10-31, reviewer both): NOT-BUILT — The diff has no `ruff.toml` hunk and no `extend-select` text, and nothing in it shows that root `make lint` passes.
- R10 reviewed: built in PR 3 (Task 8) of the same plan; this branch is PR 2, which implements R4-R9 only — the plan splits the spec into three PRs by design.

## Spec alignment (2026-10-31)

- spec: docs/superpowers/specs/2026-10-31-rust-python-standards-tier1-design.md
- anchor: 54305dfad83999dceb9f4baa9c36ad0d927105b2
- in scope: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10
- out of scope: none

### Findings

| ID | Reviewer | Verdict | Reason | Amendment |
| --- | --- | --- | --- | --- |
| R1 | both | NOT-BUILT | The diff adds no edition, `[lints.rust] unsafe_code = "forbid"` or rust-version change and no rust-version uniformity test. `edition = "2024"` and `test_every_crate_forbids_unsafe_code` show up only as unchanged context lines (Cargo.toml hunks, tests/test_crate_uniformity.py:328), so this diff does not show the forbid declarations or a test that fails on a `rust-version` key. | - R1 reviewed: built and merged in PR 1 (math#187, c398814); this branch is PR 2, which implements R4-R9 only — the plan splits the spec into three PRs by design. |
| R3 | both | NOT-BUILT | The diff has no hunk for `scripts/crate_templates/rustfmt.toml` and no `style_edition` text anywhere, so it does not show this requirement. | - R3 reviewed: built and merged in PR 1 (math#187, c398814); this branch is PR 2, which implements R4-R9 only — the plan splits the spec into three PRs by design. |
| R10 | both | NOT-BUILT | The diff has no `ruff.toml` hunk and no `extend-select` text, and nothing in it shows that root `make lint` passes. | - R10 reviewed: built in PR 3 (Task 8) of the same plan; this branch is PR 2, which implements R4-R9 only — the plan splits the spec into three PRs by design. |

### Reviewed

- R4 reviewed: built in PR 2 (Task 2) of the same plan; this branch is PR 1, which implements R1-R3 only — the plan splits the spec into three PRs by design.
- R5 reviewed: built in PR 2 (Task 3) of the same plan; this branch is PR 1, which implements R1-R3 only — the plan splits the spec into three PRs by design.
- R6 reviewed: built in PR 2 (Task 4) of the same plan; this branch is PR 1, which implements R1-R3 only — the plan splits the spec into three PRs by design.
- R7 reviewed: built in PR 2 (Task 3) of the same plan; this branch is PR 1, which implements R1-R3 only — the plan splits the spec into three PRs by design.
- R8 reviewed: built in PR 2 (Task 5) of the same plan; this branch is PR 1, which implements R1-R3 only — the plan splits the spec into three PRs by design.
- R9 reviewed: built in PR 2 (Task 6) of the same plan; this branch is PR 1, which implements R1-R3 only — the plan splits the spec into three PRs by design.
- R10 reviewed: built in PR 3 (Task 8) of the same plan; this branch is PR 1, which implements R1-R3 only — the plan splits the spec into three PRs by design.
- R1 reviewed: built and merged in PR 1 (math#187, c398814); this branch is PR 2, which implements R4-R9 only — the plan splits the spec into three PRs by design.
- R3 reviewed: built and merged in PR 1 (math#187, c398814); this branch is PR 2, which implements R4-R9 only — the plan splits the spec into three PRs by design.
- R10 reviewed: built in PR 3 (Task 8) of the same plan; this branch is PR 2, which implements R4-R9 only — the plan splits the spec into three PRs by design.

### Verifications

- V1: no evidence recorded
- V2: no evidence recorded
- V3: no evidence recorded
- V4: no evidence recorded
- V5: no evidence recorded
