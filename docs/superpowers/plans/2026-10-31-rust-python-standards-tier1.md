# Rust and Python Standards Tier 1 Implementation Plan

> **Status: DONE** (math#187 c398814, math#188 31aae33, math#189 8aae590)

spec: docs/superpowers/specs/2026-10-31-rust-python-standards-tier1-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move all 11 crates to edition 2024 with `unsafe_code` forbidden, license the repo MIT with cargo-deny enforcing the dependency licence set and LGPL notices in every release, and put ruff on its upstream default rule set.

**Architecture:** Three PRs, each landing all 11 crates (or all Python) at once. PR 1 changes the shared `Cargo.toml` shape and the rustfmt template. PR 2 adds a root `deny.toml` pinned by a whole-file test, a crate-loop script used by a new `cargo-deny.yml`, offline fixture controls, and a notices script the release template runs before tagging. PR 3 switches `ruff.toml` to `extend-select` and fixes the findings.

**Tech Stack:** Rust 1.99 stable, cargo-deny 0.20.2, bats, Python unittest, ruff 0.16.4, GitHub Actions.

## Global Constraints

- All 11 crates treated identically; per-crate files come from `scripts/crate_templates/` via `python3 scripts/render_crate_files.py --write`, never hand-edited.
- No `rust-version` in any `Cargo.toml`; no MSRV job in any workflow.
- `deny.toml` global allow-list is exactly: MIT, Apache-2.0, Apache-2.0 WITH LLVM-exception, BSD-2-Clause, Unlicense, Zlib, Unicode-3.0; `LGPL-3.0-or-later` only as exceptions for `rug` and `gmp-mpfr-sys`; `[advisories] unmaintained = "all"`; no `ignore` entries.
- cargo-deny invocation: `cargo deny --config <deny.toml> --manifest-path <crate>/Cargo.toml check [licenses]` (`--config` before `check`).
- `cargo-deny@0.20.2` installed only through the pinned `taiki-e/install-action@5488ac5a951645ce95062214902ac4b6bc1a1037 # v2.87.32` with `fallback: none`.
- Licence texts: `licenses/LGPL-3.0.txt` = https://www.gnu.org/licenses/lgpl-3.0.txt (sha256 `e3a994d82e644b03a792a930f574002658412f62407f5fee083f2555c5f23118`), `licenses/GPL-3.0.txt` = https://www.gnu.org/licenses/gpl-3.0.txt (sha256 `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`).
- Fixtures live under `tests/fixtures/cargo-deny/` with no `-rs` path segment.
- Run every `make test` / `make test-rust` with `< /dev/null`.
- Never commit to master; each PR on its own branch in its own worktree under `.worktrees/`; PRs open as drafts.

## Verification Planning

- **PR 1:** `make test-rust < /dev/null` exits 0 (all 11 crates lint and test under edition 2024); `python3 -m unittest tests.test_crate_uniformity` exits 0; `grep -l rust-version */*-rs/Cargo.toml` prints nothing. Edge: the twin-primes `collapsible_if` site (`twin-primes/twin-primes-rs/src/lib.rs:111`) passes clippy `-D warnings`.
- **PR 2:** `bash scripts/cargo-deny-all.sh` locally prints 11 crate lines and exits 0; the three fixture bats cases pass (two rejections with `error[rejected]`, one exit 0); `bash scripts/third-party-notices.sh pi/pi-rs <tmp>` writes one file containing `gmp-mpfr-sys`, `LGPL-3.0-or-later`, and the first lines of both licence texts, and `prime/prime-rs` writes one file with no licence text. CI: `cargo-deny` job green with 11 crates in its log (V1); `scripts` job log shows the fixture tests ran (V3). Edge: missing lockfile, missing/empty licence text, empty or short crate list each exit non-zero.
- **PR 3:** `make lint` exits 0 under `extend-select`; `ruff check --no-cache .` reports 0.

---

## PR 1: Rust manifests (branch `feat/rust-edition-2024`)

Orchestrator: `git worktree add .worktrees/rust-2024 -b feat/rust-edition-2024 origin/master`.

### Task 1: Edition 2024, unsafe forbid, style edition

```yaml-task
id: 1
description: Pin edition 2024, unsafe_code forbid and no rust-version in the uniformity test, then migrate all 11 crates and the rustfmt template
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R3]
acceptance:
  - cmd: python3 -m unittest tests.test_crate_uniformity
    exit_code: 0
  - cmd: make test-rust < /dev/null
    exit_code: 0
  - cmd: make test < /dev/null
    exit_code: 0
  - cmd: '! git grep -n "rust-version" -- "*/*-rs/Cargo.toml"'
    exit_code: 0
max_retries: 3
depends_on: []
```

**Files:** `tests/test_crate_uniformity.py`; the 11 `*/*-rs/Cargo.toml`; `scripts/crate_templates/rustfmt.toml` (rendered to 11 `*/*-rs/rustfmt.toml`); every `.rs` file `cargo fmt` rewrites; `twin-primes/twin-primes-rs/src/lib.rs`; `CLAUDE.md`.

- [ ] In `TestCargoTomlShape`, add three tests over `rcf.CRATES`: `package.edition == "2024"`; `lints.rust.unsafe_code == "forbid"`; `"rust-version" not in package`. Run `python3 -m unittest tests.test_crate_uniformity`; expect 22 failures (11 edition, 11 unsafe_code). The `rust-version` test passes on the base tree by design (R1 forbids a future addition).
- [ ] In each `Cargo.toml`: `edition = "2024"`; under `[lints.rust]` add `unsafe_code = "forbid"`.
- [ ] Append `style_edition = "2024"` to `scripts/crate_templates/rustfmt.toml`; run `python3 scripts/render_crate_files.py --write`.
- [ ] In each crate dir run `cargo fmt`.
- [ ] Collapse `twin-primes/twin-primes-rs/src/lib.rs:111-112` into one let-chain: `if let (Some(lp), Some(&fp)) = (last_prime, seg.first()) && fp == lp + 2 && fp < limit {`.
- [ ] `CLAUDE.md` "API-quality lints" line: add that every crate is edition 2024 with `unsafe_code = "forbid"` and declares no `rust-version` (spec § Why no `rust-version`). Keep `CLAUDE.md` under 30,000 bytes (`python3 scripts/claude_md_budget.py`).
- [ ] Run the acceptance gates; commit.

**Interfaces:** Produces the `[lints.rust]` table Task 2 extends with `license` (in `[package]`).

Orchestrator after Task 1: Phase 3 (`finishing-a-development-branch`), push, `gh pr create --draft`, `gh pr checks --watch`, `gh pr ready` after Phase 3. PR 2 branches from master after PR 1 merges.

---

## PR 2: Licence, cargo-deny, LGPL notices (branch `feat/licence-cargo-deny`)

Orchestrator: after PR 1 merges, `git worktree add .worktrees/licence-deny -b feat/licence-cargo-deny origin/master`.

### Task 2: MIT licence

```yaml-task
id: 2
description: Add the MIT LICENSE and license = "MIT" to all 11 crates, pinned by the uniformity test
role: executor
model: sonnet
tdd: required
requirements: [R4]
acceptance:
  - cmd: python3 -m unittest tests.test_crate_uniformity
    exit_code: 0
  - cmd: 'grep -q "^MIT License" LICENSE'
    exit_code: 0
max_retries: 3
files_touched: [LICENSE, tests/test_crate_uniformity.py, amicable/amicable-rs/Cargo.toml, collatz/collatz-rs/Cargo.toml, e/e-rs/Cargo.toml, factorial/factorial-rs/Cargo.toml, fib/fib-rs/Cargo.toml, goldbach/goldbach-rs/Cargo.toml, perfect-numbers/perfect-numbers-rs/Cargo.toml, pi/pi-rs/Cargo.toml, prime/prime-rs/Cargo.toml, sq/sq-rs/Cargo.toml, twin-primes/twin-primes-rs/Cargo.toml]
depends_on: []
parallel_group: wave-1
```

- [ ] Add a `TestCargoTomlShape` test: `package.license == "MIT"` for every crate. Run it; expect 11 failures.
- [ ] Insert `license = "MIT"` after `edition` in each `[package]`.
- [ ] Root `LICENSE`: standard MIT text, first line `MIT License`, `Copyright (c) 2026 Bruce Jackson`.
- [ ] Scoped gates only (wave member; the orchestrator runs `make test < /dev/null` at wave close). Commit.

### Task 3: deny.toml, policy test, fixtures, scripts.yml

```yaml-task
id: 3
description: Add the root deny.toml, a whole-file policy test, the exact-11 crate-list test, three offline cargo-deny fixtures with bats controls, and install cargo-deny in scripts.yml
role: executor
model: sonnet
tdd: required
requirements: [R5, R7]
acceptance:
  - cmd: python3 -m unittest tests.test_deny_policy tests.test_tool_pins
    exit_code: 0
  - cmd: bats tests/scripts/cargo_deny_fixtures.bats
    exit_code: 0
  - cmd: bats tests/scripts/cargo_deny_fixtures.bats
    exit_code: 0
    stdout_match: 'ok 3 '
max_retries: 3
files_touched: [deny.toml, tests/test_deny_policy.py, tests/test_tool_pins.py, tests/scripts/cargo_deny_fixtures.bats, tests/fixtures/cargo-deny/gpl/Cargo.toml, tests/fixtures/cargo-deny/gpl/src/main.rs, tests/fixtures/cargo-deny/lgpl/Cargo.toml, tests/fixtures/cargo-deny/lgpl/src/main.rs, tests/fixtures/cargo-deny/mit/Cargo.toml, tests/fixtures/cargo-deny/mit/src/main.rs, .github/workflows/scripts.yml]
depends_on: []
parallel_group: wave-1
```

- [ ] `tests/test_deny_policy.py`: `tomllib.load` of `deny.toml` must equal one `EXPECTED` dict literal in the test (the Global Constraints values plus `[bans] multiple-versions = "warn"`, `[sources] unknown-registry = "deny"`, `unknown-git = "deny"`; no other keys). Second test: `git ls-files '*/*-rs/Cargo.toml'` equals the 11 `<crate>/<crate>-rs/Cargo.toml` paths from `render_crate_files.CRATES`. Run; expect the policy test to fail (no file).
- [ ] Write `deny.toml` to match `EXPECTED` exactly (exceptions as `{ crate = "rug", allow = ["LGPL-3.0-or-later"] }`, same for `gmp-mpfr-sys`).
- [ ] Fixtures: three `[package]` crates, `edition = "2024"`, names `deny-fixture-gpl` (`license = "GPL-3.0-only"`), `deny-fixture-lgpl` (`license = "LGPL-3.0-or-later"`), `deny-fixture-mit` (`license = "MIT"`), no dependencies, `src/main.rs` = `fn main() {}`.
- [ ] `tests/scripts/cargo_deny_fixtures.bats`: `setup()` skips with a message when `cargo-deny` is absent and `CI` is unset, fails when absent and `CI` is set; each test copies its fixture to `${BATS_TEST_TMPDIR}` and runs `cargo deny --config "${REPO_ROOT}/deny.toml" --manifest-path <copy>/Cargo.toml check licenses`. gpl and lgpl: `status -eq 4` and output contains `error[rejected]`; mit: `status -eq 0`. Assert no `Cargo.lock` appears under `tests/fixtures/`.
- [ ] `scripts.yml`: add a `taiki-e/install-action` step (pinned SHA, `tool: cargo-deny@0.20.2`, `fallback: none`) before the bats step; add `deny.toml` and `tests/fixtures/cargo-deny/**` to `paths` (`tests/**` already covers fixtures; add `deny.toml`).
- [ ] `tests/test_tool_pins.py`: `test_action_versions_match_installer_pins` treats `cargo-deny` like `cargo-auditable` (CI-only, no installer pin) and adds it to the expected `seen` set; `test_release_only_tool_has_one_version` covers it too.
- [ ] Scoped gates; commit.

**Interfaces:** Produces `deny.toml` consumed by Tasks 4 and the fixture tests.

### Task 4: cargo-deny-all.sh and cargo-deny.yml

```yaml-task
id: 4
description: Add scripts/cargo-deny-all.sh with a crate-count guard and replace cargo-audit.yml with cargo-deny.yml running it
role: executor
model: sonnet
tdd: required
requirements: [R6]
acceptance:
  - cmd: bats tests/scripts/cargo_deny_all.bats
    exit_code: 0
  - cmd: bash scripts/cargo-deny-all.sh < /dev/null
    exit_code: 0
  - cmd: python3 -m unittest tests.test_tool_pins
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/cargo-deny-all.sh, tests/scripts/cargo_deny_all.bats, tests/mocks/cargo, .github/workflows/cargo-deny.yml, .github/workflows/cargo-audit.yml]
depends_on: [2, 3]
```

- [ ] `tests/scripts/cargo_deny_all.bats` with a PATH mock `tests/mocks/cargo` (records argv to `${MOCK_CARGO_LOG}`, exits `${MOCK_CARGO_EXIT_<n>:-0}` per call or a fail-list env). Cases: 11 crates all pass → exit 0 and 11 log lines each with `--config` before `check`; one crate fails → non-zero, all 11 still invoked; empty list (`CARGO_DENY_CRATES` override pointing at an empty file) → non-zero with a message; 10 crates → non-zero. Run; expect failures (no script).
- [ ] `scripts/cargo-deny-all.sh`: shell standards (`#!/usr/bin/env bash`, sourcing guard, `[[ ]]`, `printf`); crate list from `git ls-files '*/*-rs/Cargo.toml'` (test override `CARGO_DENY_CRATES=<file>`); refuse when the count is not 11 with `cargo-deny-all: expected 11 crates, found N`; loop every crate `cargo deny --config "${REPO_ROOT}/deny.toml" --manifest-path "${manifest}" check`, print `=== <crate> ===`, record failures, exit 1 if any.
- [ ] `.github/workflows/cargo-deny.yml`: same triggers as `cargo-audit.yml` plus `deny.toml` and `scripts/cargo-deny-all.sh` in `paths`; weekly cron `0 6 * * 1`; checkout (pinned SHA as in cargo-audit.yml), `dtolnay/rust-toolchain` (same pin), taiki install of `cargo-deny@0.20.2`, run `scripts/cargo-deny-all.sh`. `git rm .github/workflows/cargo-audit.yml`.
- [ ] Run gates; commit.

### Task 5: third-party-notices.sh and licence texts

```yaml-task
id: 5
description: Add the GNU licence texts and scripts/third-party-notices.sh, which writes one THIRD-PARTY-NOTICES.txt per crate and embeds LGPL-3.0 and GPL-3.0 for GMP crates
role: executor
model: sonnet
tdd: required
requirements: [R8]
acceptance:
  - cmd: bats tests/scripts/third_party_notices.bats
    exit_code: 0
  - cmd: 'sha256sum -c <<< "e3a994d82e644b03a792a930f574002658412f62407f5fee083f2555c5f23118  licenses/LGPL-3.0.txt"'
    exit_code: 0
  - cmd: 'sha256sum -c <<< "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986  licenses/GPL-3.0.txt"'
    exit_code: 0
max_retries: 3
files_touched: [licenses/LGPL-3.0.txt, licenses/GPL-3.0.txt, scripts/third-party-notices.sh, tests/scripts/third_party_notices.bats]
depends_on: []
parallel_group: wave-1
```

- [ ] Download both texts with `curl -fsSL` from the Global Constraints URLs; verify the sha256s.
- [ ] Bats cases (fixture lockfiles written in `BATS_TEST_TMPDIR`; `LICENSES_DIR` override for the missing/empty cases): GMP lockfile (`gmp-mpfr-sys` 1.7.0, `rug` 1.30.0) → exit 0, out-dir holds exactly `THIRD-PARTY-NOTICES.txt`, which contains `gmp-mpfr-sys 1.7.0`, `rug 1.30.0`, `GMP`, `MPFR`, `MPC`, `LGPL-3.0-or-later`, `statically linked`, `GNU LESSER GENERAL PUBLIC LICENSE` and `GNU GENERAL PUBLIC LICENSE`; non-GMP lockfile → one file, contains `links no LGPL components`, not `GNU GENERAL PUBLIC LICENSE`; missing lockfile → non-zero; GMP lockfile with `LGPL-3.0.txt` missing → non-zero; with it empty → non-zero; unwritable out-dir → non-zero. Run; expect failures.
- [ ] `scripts/third-party-notices.sh <crate-dir> <out-dir>`: versions parsed from `[[package]]` blocks in `<crate-dir>/Cargo.lock`; GMP text says sources are this repository at the release tag (MIT application source, sufficient to relink) and the `gmp-mpfr-sys` crate on crates.io (bundles the C sources), both of which must remain available; then embeds both licence files verbatim. Fail closed on every error case above.
- [ ] Scoped gates; commit.

**Interfaces:** Produces `scripts/third-party-notices.sh <crate-dir> <out-dir>` → `<out-dir>/THIRD-PARTY-NOTICES.txt`, consumed by Task 6.

### Task 6: Release template runs the notices script

```yaml-task
id: 6
description: Run the notices script before the tag step in the release template and attach THIRD-PARTY-NOTICES.txt by exact path, rendered to 11 workflows
role: executor
model: sonnet
tdd: required
requirements: [R9]
acceptance:
  - cmd: python3 -m unittest tests.test_release_workflows tests.test_crate_uniformity
    exit_code: 0
  - cmd: make test < /dev/null
    exit_code: 0
max_retries: 3
depends_on: [2, 3, 4, 5]
```

**Files:** `tests/test_release_workflows.py`, `scripts/crate_templates/release.yml`, the 11 rendered `.github/workflows/release-*-rs.yml`.

- [ ] Tests: a step whose `run` invokes `scripts/third-party-notices.sh @crate@/@crate@-rs <dir>` exists and its index precedes `Create and push tag`; `files:` contains `<dir>/THIRD-PARTY-NOTICES.txt`; no `files:` entry contains `*`. Run; expect failures.
- [ ] Template: after `Generate SHA256 checksum`, step `Write third-party notices` running `mkdir -p "${RUNNER_TEMP}/notices" && scripts/third-party-notices.sh @CRATE@/@CRATE@-rs "${RUNNER_TEMP}/notices"`; add `${{ runner.temp }}/notices/THIRD-PARTY-NOTICES.txt` to `files:`. Render with `--write`.
- [ ] Run gates (orchestrator: this is the wave-close `make test`); commit.

### Task 7: Docs, ADR, Backlog

```yaml-task
id: 7
description: Document the licence, cargo-deny gate and notices in CLAUDE.md, ADR-0035 and the plan index, and move tier 2/3 gaps to the Backlog (docs-only, no behavior change)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: python3 scripts/claude_md_budget.py
    exit_code: 0
  - cmd: 'grep -q "0035" docs/adr/README.md'
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 2
files_touched: [CLAUDE.md, docs/adr/0035-mit-licence-cargo-deny-and-lgpl-notices.md, docs/adr/README.md, docs/superpowers/README.md]
depends_on: [6]
```

- [ ] `CLAUDE.md`: add `cargo-deny.yml` to the workflow list; one line: repo is MIT, `deny.toml` (pinned whole by `tests/test_deny_policy.py`; changes need operator approval) runs via `scripts/cargo-deny-all.sh`; one line: releases attach `THIRD-PARTY-NOTICES.txt` from `scripts/third-party-notices.sh`, which embeds LGPL-3.0/GPL-3.0 for the 5 GMP crates and fails before the tag.
- [ ] ADR-0035 (Context, Decision, Consequences, Related) + index row.
- [ ] `docs/superpowers/README.md`: Backlog rows for clippy `pedantic` (~300 warnings), `unwrap_used`/`expect_used` policy (729 hits), pyright `strict` (2,412 errors), each pointing at the spec; delete the P4 `cargo deny` licence-policy row (done here).
- [ ] Commit.

Orchestrator after Task 7: Phase 3, push, draft PR, CI watch (confirm V1 and V3 in the logs), `gh pr ready`. Message the ai-config session for V5 (`math-new-cli` skill scaffolds `edition = "2024"`, `unsafe_code = "forbid"`, `license = "MIT"`). Put V4 to the operator.

---

## PR 3: ruff defaults (branch `feat/ruff-defaults`)

Orchestrator: after PR 2 merges, `git worktree add .worktrees/ruff-defaults -b feat/ruff-defaults origin/master`.

### Task 8: extend-select and fix findings

```yaml-task
id: 8
description: Switch ruff.toml to extend-select over the pinned ruff defaults, pin that with a test, and fix every finding
role: executor
model: sonnet
tdd: required
requirements: [R10]
acceptance:
  - cmd: python3 -m unittest tests.test_ruff_config
    exit_code: 0
  - cmd: ruff check --no-cache .
    exit_code: 0
  - cmd: make test < /dev/null
    exit_code: 0
max_retries: 3
depends_on: []
```

**Files:** `ruff.toml`, `tests/test_ruff_config.py`, the `.py` files ruff flags, `CLAUDE.md`.

- [ ] `tests/test_ruff_config.py`: `tomllib` load of `ruff.toml`; assert `"select" not in lint` and `lint["extend-select"]` equals today's list (`E4, E7, E9, F, W, I, B, C4, UP, PIE, RUF, PLW1510, BLE001, S110, S112, C901`). Run; expect failure.
- [ ] `ruff.toml`: rename `select` to `extend-select`; keep `ignore`, `unfixable`, `per-file-ignores`.
- [ ] `ruff check --no-cache .` (expect about 85: SIM117 41, EXE001 28, ISC004 3, FURB167 3, SIM114 3, SIM113 2, others). Fix each: combine nested `with`; drop shebangs from files nothing executes directly (keep and `chmod +x` where a file is run directly); others by hand. Ignore only per file with a reason comment.
- [ ] `CLAUDE.md` ruff line: config extends ruff's default rule set; new defaults arrive only with a deliberate pin bump, gated by that PR's `make lint`.
- [ ] Run gates; commit.

Orchestrator after Task 8: Phase 3, push, draft PR, CI watch, `gh pr ready`; mark the plan Done.

## Non-goal check

Fresh reviewer, 2026-10-31, against N1-N7 of the approved spec: all CLEAR, 0 CONFLICT, 0 UNCLEAR. Closest items, with the reviewer's reasoning: N1/N2 (Task 7 names clippy `pedantic`, `unwrap_used`/`expect_used` and pyright `strict` only as Backlog rows); N5 (the only per-crate code edit, `twin-primes/twin-primes-rs/src/lib.rs`, is not a templated file); N6 (Task 8 renames `select` to `extend-select` with the list unchanged); N7 (`[bans]`/`[sources]` keys are not licences, exceptions or ignores). No plan revision or amendment needed.
