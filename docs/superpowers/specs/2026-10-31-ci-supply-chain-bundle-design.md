# CI supply-chain bundle — design

Date: 2026-10-31. Repo: math. Source: four Backlog rows in `docs/superpowers/README.md`
(gitleaks download in `auto-merge.yml` has no checksum; `cargo-deny.yml` hardening;
`scripts/pre-push` does not run tests on a `deny.toml`-only change; the
`libgmp-dev libmpfr-dev` apt step in the Rust CI jobs is unused). The operator chose to ship
the four as one spec, one plan and one PR.

## Problem

Four gaps in how CI and the local hooks fetch, verify and check what the repo depends on.

1. **gitleaks runs unverified.** The `secret-scan` job in `.github/workflows/auto-merge.yml`
   downloads `gitleaks_8.21.2_linux_x64.tar.gz` with `wget`, extracts it, and installs it
   to `/usr/local/bin` with no checksum. core.md ci-002 requires a pinned version and a
   `sha256sum -c` line before any directly downloaded binary runs. The other two direct
   downloads in the workflows (snyk in `auto-merge.yml`, shellcheck in `auto-merge.yml` and
   `scripts.yml`) already comply; gitleaks is the only one that does not. Nothing checks the
   rule generally: `tests/test_snyk_cli_pinned.py` pins snyk's step only, so the next tool
   added by direct download can repeat the gitleaks gap.
2. **cargo-deny can check a lockfile that does not ship.** `scripts/cargo-deny-all.sh` runs
   `cargo deny` without `--locked`. On a crate whose `Cargo.toml` and `Cargo.lock` disagree,
   cargo-deny silently rewrites the lockfile and checks the rewritten one. `cargo-deny.yml`
   also declares no `permissions:` block; the repo default is `read` today, so the workflow
   holds read only because of a setting outside the repo.
3. **A `deny.toml` change is checked only in CI.** The pre-push routing regex has no
   `deny.toml` pattern, so a push touching only `deny.toml` runs nothing locally: neither
   the policy pin (`tests/test_deny_policy.py`), nor the fixture controls, nor the policy
   against the 11 real crates.
4. **An apt step installs libraries nothing links.** Every Rust-only workflow runs
   `sudo apt-get install -y libgmp-dev libmpfr-dev` (`benchmarks.yml` adds `libmpc-dev`).
   No crate enables a system-library feature of `gmp-mpfr-sys`, which therefore builds
   GMP, MPFR and MPC from source and links them statically. The step costs an
   `apt-get update` and install in 46 jobs per full run (33 CI, 11 release, `gmp-cache.yml`, `benchmarks.yml`) and changes nothing.

## Measurements

All on Linux `claude`, 2026-10-31, against master `d85c410` unless stated.

| What                                   | Command                                                                                                                                                                | Result                                                                                                                                                                                     | Population                                                                                                                              |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| Direct downloads in workflows          | `git grep -n -E 'wget\|curl ' -- .github/`                                                                                                                             | 4 lines: gitleaks (`wget`, no checksum), snyk (`curl`, `sha256sum -c`), shellcheck in `auto-merge.yml` and `scripts.yml` (`curl`, `sha256sum -c`)                                          | every tracked file under `.github/`                                                                                                     |
| gitleaks 8.21.2 checksum               | `gh release download v8.21.2 --repo gitleaks/gitleaks -p 'gitleaks_8.21.2_checksums.txt' -p 'gitleaks_8.21.2_linux_x64.tar.gz'`, then `grep linux_x64` and `sha256sum` | both `5bc41815076e6ed6ef8fbecc9d9b75bcae31f39029ceb55da08086315316e3ba`                                                                                                                    | the one asset the job downloads                                                                                                         |
| Repo default workflow token            | `gh api repos/brujack/math/actions/permissions/workflow --jq .default_workflow_permissions`                                                                            | `read`                                                                                                                                                                                     | this repo's setting, today                                                                                                              |
| `--locked` accepted as a global option | `cargo deny --locked --config deny.toml --manifest-path <prime-rs copy> check licenses`                                                                                | rc 0                                                                                                                                                                                       | one crate copy (prime-rs) in a temp dir                                                                                                 |
| Stale lockfile today                   | same copy with `itoa = "1"` added to `[dependencies]`, without `--locked`                                                                                              | rc 0, `Cargo.lock` rewritten                                                                                                                                                               | one crate copy                                                                                                                          |
| Stale lockfile with `--locked`         | same, with `--locked`                                                                                                                                                  | rc 1, `cannot update the lock file ... because --locked was passed`                                                                                                                        | one crate copy                                                                                                                          |
| `cargo-deny-all.sh` cost               | `time bash scripts/cargo-deny-all.sh`                                                                                                                                  | 5.6 s, rc 0, `git status --porcelain` empty                                                                                                                                                | all 11 crates, warm advisory DB                                                                                                         |
| pre-push on `deny.toml`                | read of the `RUN_HOOK_TESTS` regex in `scripts/pre-push`                                                                                                               | no `deny\.toml` alternative                                                                                                                                                                | the hook as tracked                                                                                                                     |
| apt step locations                     | `git grep -c 'libgmp-dev' -- .github/workflows/`                                                                                                                       | 3 in each `*-rs.yml` (11), 1 in each `release-*-rs.yml` (11), 1 in `gmp-cache.yml`, 1 in `benchmarks.yml`; also 1 in each `*-py.yml` (8), `mutation-pr.yml`, `mutation-testing-python.yml` | all workflows                                                                                                                           |
| System-library features                | `git grep -n -E '^(rug\|gmp-mpfr-sys)' -- '*/Cargo.toml'`                                                                                                              | 5 crates, `rug` with `integer`/`float` only; no `use-system-libs`                                                                                                                          | all 11 manifests                                                                                                                        |
| Cold build without system GMP          | `docker run ubuntu:26.04`: install `build-essential m4 curl`, rustup, `cargo build --release --locked` in a copy of `pi/pi-rs`                                         | rc 0; `dpkg -l` lists 0 `libgmp-dev`/`libmpfr-dev`; `ldd target/release/pi` lists 0 `gmp`/`mpfr`/`mpc` lines; `pi --help` rc 0. `apt-cache depends libgmp-dev` names no `m4`, so the removed step never supplied the one build tool GMP's configure needs                                                                                                                                                                          | one crate (pi-rs, `integer`+`float`, the widest feature set) on the same Ubuntu release as `ubuntu-latest`, not the runner image itself |

The PR's own CI cannot prove item 4: every `*-rs.yml` job restores the GMP build from the
`gmp-cache.yml` cache (keyed on `gmp-mpfr-sys` versions only), so it compiles nothing from
source. The container build is the cold-build evidence; V2 records the first cold build on
a real runner.

## Design

### 1. Checksum-verified gitleaks, and a rule for every download

- `auto-merge.yml` `secret-scan` → step `Install gitleaks` gains `env:` `GITLEAKS_VER: "8.21.2"`
  and `GITLEAKS_SHA256: "5bc41815…3ba"` (full value), downloads with `curl -fsSL -o`, runs
  `echo "${GITLEAKS_SHA256}  /tmp/gitleaks.tar.gz" | sha256sum -c -` before `tar`, and ends
  with a version assertion (`gitleaks version | grep -qx "${GITLEAKS_VER}"`), matching the
  snyk and shellcheck steps.
- New `tests/test_workflow_downloads_verified.py` parses every `.github/workflows/*.yml` and
  `.github/actions/**/action.yml` with `yaml.safe_load`, walks every step's `run:` text, and
  for each step whose text invokes `curl` or `wget` requires: a `sha256sum -c` line, placed
  before the first line that extracts (`tar`), installs (`install`, `mv`, `chmod +x`) or
  executes the downloaded path. It names the file, job and step on failure.
- The test's own controls: a synthetic step with a download and no checksum fails; one with
  the checksum after `tar` fails; one with the checksum before `tar` passes; the current
  tree passes with exactly 4 download steps found (a scan that finds 0 fails, so a parser
  that walks nothing cannot pass).

### 2. cargo-deny hardening

- `cargo-deny.yml` gains a workflow-level `permissions: contents: read`.
- `scripts/cargo-deny-all.sh` passes `--locked` as a global option beside `--config`,
  before `check`.
- `tests/scripts/cargo_deny_all.bats` asserts `--locked` precedes `check` on all 11
  invocations (the mock already records argv).
- A fixture control in `tests/scripts/cargo_deny_fixtures.bats` runs the real cargo-deny on
  a copy of a fixture crate whose `Cargo.toml` names a dependency its `Cargo.lock` lacks,
  and asserts rc ≠ 0 with `--locked` in the output. It fails closed under `CI` when
  cargo-deny is missing, like the existing fixtures.

### 3. pre-push runs the deny checks on a `deny.toml` change

- `scripts/pre-push`: a push whose diff touches `^deny\.toml$` or
  `^scripts/cargo-deny-all\.sh$` sets `RUN_HOOK_TESTS=1` (root `make test`: the policy pin
  and the fixture controls) and a new `RUN_CARGO_DENY=1`.
- `RUN_CARGO_DENY=1` runs `scripts/cargo-deny-all.sh < /dev/null` after the hook tests and
  before the early exits; a non-zero exit refuses the push.
- When `cargo` or `cargo-deny` is absent, the hook prints
  `pre-push: cargo-deny not installed; skipping the deny.toml check (cargo install cargo-deny --locked --version 0.20.2)`
  and continues (core.md shell-004). CI's `cargo-deny.yml` still enforces it.
- `tests/scripts/pre_push.bats` (mocked `cargo`, `make`, `git`): a `deny.toml`-only push
  runs both root `make test` and the script; a push without `deny.toml` runs neither; a
  failing script refuses the push with rc 1; a missing cargo-deny prints the remedy line
  and exits 0.

### 4. Remove the apt step from Rust-only workflows

- Delete the `Install GMP and MPFR` step from `scripts/crate_templates/ci.yml` (3 jobs) and
  `scripts/crate_templates/release.yml` (1 job), then
  `python3 scripts/render_crate_files.py --write` so all 22 rendered workflows match.
- Delete it from `gmp-cache.yml` and `benchmarks.yml` by hand (neither is rendered).
- `*-py.yml`, `mutation-pr.yml` and `mutation-testing-python.yml` keep it: they install
  `gmpy2`, which this spec has not measured. A Backlog row carries that question.
- A test asserts that no Rust-only workflow (`*-rs.yml`, `release-*-rs.yml`,
  `gmp-cache.yml`, `benchmarks.yml`) contains `libgmp-dev`, `libmpfr-dev` or `libmpc-dev`,
  and that the set it scanned has 24 files.

### Docs

- `CLAUDE.md`: the pre-push paragraph names `deny.toml`; the cargo-deny line says
  `--locked`. Byte budget re-checked (`scripts/claude_md_budget.py`).
- ADR-0035 gains a dated line for `--locked` and the pre-push check.
- Backlog: remove the four rows; add the Python apt row.

## Requirements

- **R1.** The `secret-scan` job's gitleaks install step pins `GITLEAKS_VER: "8.21.2"` and `GITLEAKS_SHA256: "5bc41815076e6ed6ef8fbecc9d9b75bcae31f39029ceb55da08086315316e3ba"` and runs `sha256sum -c` before `tar`.
- **R2.** A test fails when any step in `.github/workflows/*.yml` or `.github/actions/**/action.yml` runs `curl` or `wget` without a `sha256sum -c` line before the downloaded file is extracted, installed or executed, and it fails when it finds 0 download steps.
- **R3.** `cargo-deny.yml` declares `permissions: contents: read` at workflow level.
- **R4.** `scripts/cargo-deny-all.sh` passes `--locked` before `check` on every one of the 11 invocations, asserted by `tests/scripts/cargo_deny_all.bats`.
- **R5.** A cargo-deny fixture test shows that `cargo-deny-all.sh`'s invocation exits non-zero on a crate whose `Cargo.lock` lacks a dependency named in its `Cargo.toml`.
- **R6.** `scripts/pre-push` runs root `make test` and `scripts/cargo-deny-all.sh` when the pushed range touches `deny.toml` or `scripts/cargo-deny-all.sh`, and runs neither for that reason otherwise.
- **R7.** When cargo-deny is not installed, `scripts/pre-push` prints a line naming `cargo install cargo-deny --locked --version 0.20.2` and does not refuse the push for that reason.
- **R8.** No `*-rs.yml`, `release-*-rs.yml`, `gmp-cache.yml` or `benchmarks.yml` installs `libgmp-dev`, `libmpfr-dev` or `libmpc-dev`, and a test asserts it over exactly those 24 files.
- **R9.** The apt step is removed through `scripts/crate_templates/` and `render_crate_files.py --write`; `tests/test_crate_uniformity.py` passes.
- **V1.** This PR's CI is green on every `*-rs.yml`, `cargo-deny.yml`, `scripts.yml` and `auto-merge.yml` job, and the `secret-scan` log shows `gitleaks_8.21.2_linux_x64.tar.gz: OK`.
- **V2.** The next release dispatch of a GMP crate (e, factorial, fib, perfect-numbers or pi) succeeds without the apt step, and `ldd` on its binary lists no `libgmp`, `libmpfr` or `libmpc`.
- **V3.** A local push of a `deny.toml`-only commit on the branch runs `cargo-deny-all: all 11 crates passed` in the hook output.
- **N1.** No change to `*-py.yml`, `mutation-pr.yml` or `mutation-testing-python.yml`.
- **N2.** No change to `deny.toml` or `tests/test_deny_policy.py`.
- **N3.** No new tool, action or package dependency; gitleaks stays at 8.21.2.
- **N4.** pre-push does not refuse a push because cargo-deny is absent.

## Multi-Lens Review

Reviewed at commit: `65e4a8b` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: Item 3's `RUN_CARGO_DENY` stage costs the most and buys the least: `deny.toml` has 2 commits ever, both need operator approval (N2, the policy pin), and `cargo-deny.yml` and `scripts.yml` already run on it in CI. Adding `^deny\.toml$` to the existing `RUN_HOOK_TESTS` regex gets the policy pin and fixture controls locally for one line; `^scripts/` already covers `cargo-deny-all.sh`. The pre-push run also fetches the advisory DB, so an offline push would be refused, which R7/N4 do not cover. Smaller: `--locked` guards the checker, not what ships (`ci.yml` `cargo build --release`, `release.yml` `cargo auditable build --release` lack it); V2's `ldd` cannot tell before from after (static either way), only "the build succeeds" carries signal; the gitleaks version-assertion format was unmeasured.
Assumption: the pre-push run assumes cargo-deny can check offline against a cached advisory DB. Measured by the author after the lens: with HTTP(S)_PROXY pointed at a dead port, `cargo deny ... check` exits 1 (`failed to fetch advisory database`); `cargo deny --offline ... check` and `--frozen` exit 0 (`advisories ok, bans ok, licenses ok, sources ok`) on pi-rs. `unshare -rn` is not permitted on this host. The assumption as written is false; `--offline` makes it true. `gitleaks version` from the verified 8.21.2 tarball prints exactly `8.21.2`.
Disposition:

### Ergonomics

Finding: The new pre-push deny check runs on the rarest change and skips the common one `--locked` newly fails: a crate `Cargo.toml` edited without its `Cargo.lock`. Per-crate routing matches only `\.rs$` and `RUN_HOOK_TESTS` has no `Cargo.(toml|lock)`. `git log --format='%an' -- '*/*-rs/Cargo.toml'`: 26 operator commits, 1 renovate[bot]; `8b6cb04` (0.2.0 bump) changed 22 `Cargo.toml`/`Cargo.lock` files and 0 `.rs`, and the hook ran nothing. Fix: add `^[^/]+/[^/]+-rs/Cargo\.(toml|lock)$` to the `RUN_CARGO_DENY` trigger only, plus one bats case.
Assumption: R5's fixture fails with the `--locked` message offline with a cold cargo cache. Measured by the author after the lens (`CARGO_NET_OFFLINE=true`, fresh `CARGO_HOME`): a path dependency on a sibling fixture crate exits 1 with `because --locked was passed`; a registry dependency (`itoa = "1"`) exits 1 with `no matching package`, the wrong reason. The fixture must use a path dependency.
Disposition:

### Risk

Finding: Item 4 is safe: `apt-cache depends libgmp-dev libmpfr-dev` names no `m4`; nothing else in those jobs uses the libraries (Python steps install only `defusedxml`; tarpaulin and nextest come from `taiki-e/install-action`; `gmp-cache.yml` checks `.a` files in its cache dir); `release.yml` and `benchmarks.yml` already cold-build without the GMP cache. The weakness is R2: it checks that some `sha256sum -c` precedes the first `tar`/`install`/`mv`, not that it names the downloaded path, so a checksum of another file, `sha256sum -c ... || true`, or `curl ... | sh` all pass; and the `curl` keyword makes any future API call a false positive. Fix: for each `-o`/`-O` target require a `sha256sum -c` naming that path with no `||`, before any later use; assert `>= 1` steps, not `== 4`. Factual error: `rug` keeps default features, so `complex` (MPC) is built too; the Measurements row saying `integer`/`float` only is wrong but harmless.
Assumption: `gitleaks version` prints exactly `8.21.2`. Measured by the author: it does.
Disposition:

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
