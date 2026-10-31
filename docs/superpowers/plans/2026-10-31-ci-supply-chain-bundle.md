# CI Supply-Chain Bundle Implementation Plan

spec: docs/superpowers/specs/2026-10-31-ci-supply-chain-bundle-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close four CI supply-chain gaps: an unverified gitleaks download, cargo-deny checking a rewritten lockfile, `deny.toml` changes untested on push, and an unused apt step in 24 Rust workflows.

**Architecture:** One branch `ci/supply-chain-bundle` in `.worktrees/ci-supply-chain`, five sequential tasks, one draft PR. Tests are Python `unittest` (root `tests/`, run by `make test-python`) and bats (`tests/scripts/`, run by `make test-hooks`). Per-crate workflows are rendered from `scripts/crate_templates/` by `scripts/render_crate_files.py`.

**Tech Stack:** GitHub Actions YAML, bash, bats, Python 3 + PyYAML, cargo-deny 0.20.2.

## Global Constraints

- gitleaks stays at 8.21.2; sha256 `5bc41815076e6ed6ef8fbecc9d9b75bcae31f39029ceb55da08086315316e3ba`.
- No change to `*-py.yml`, `mutation-pr.yml`, `mutation-testing-python.yml`, `deny.toml` or `tests/test_deny_policy.py` (N1, N2).
- No new tool, action or package dependency (N3).
- pre-push runs no real-crate `cargo deny`, no `--offline`; no build step gains `--locked` (N4).
- Edit `scripts/crate_templates/*` and run `python3 scripts/render_crate_files.py --write`; never hand-edit a rendered workflow.
- `CLAUDE.md` is 29,954 bytes against a 30,000 ceiling: net growth ≤ 46 bytes.
- Root `make test` takes ~52 s on `claude` (measured 2026-10-31), under the 600 s Bash cap. Run every gate with `< /dev/null`.
- Session verification (orchestrator, after Task 5): `make lint < /dev/null && make test < /dev/null` exit 0 in the worktree; then PR CI green on every `*-rs.yml`, `cargo-deny.yml`, `scripts.yml`, `auto-merge.yml` job, and the `secret-scan` log contains `gitleaks_8.21.2_linux_x64.tar.gz: OK` (V1); a pushed range touching `deny.toml` prints `test: hooks and scripts (bats)` with the `cargo_deny_fixtures.bats` lines `ok` and no `# skip` (V3). V2 waits for the next GMP-crate release.

## Orchestrator steps

1. `git worktree add .worktrees/ci-supply-chain -b ci/supply-chain-bundle origin/master`.
2. Dispatch Tasks 1-5 in order. Every dispatch prompt starts: **IMPORTANT: All work must happen in `/home/bruce/git-repos/personal/math/.worktrees/ci-supply-chain/`. Do not cd anywhere else.**
3. After Task 5: session verification above, then Phase 3 (`finishing-a-development-branch`), push, `gh pr create --draft`, `gh pr checks <n> --watch`, `gh pr ready <n>` only after Phase 3 and green CI.

---

### Task 1: Checksum-verified gitleaks and a download rule for every workflow

```yaml-task
id: 1
description: Pin and sha256-verify gitleaks in secret-scan, and add a test that every workflow download is checksum-verified before use
role: executor
model: sonnet
tdd: required
requirements: [R1, R2]
acceptance:
  - cmd: python3 -m unittest tests.test_workflow_downloads_verified -v
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
  - cmd: make test < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [.github/workflows/auto-merge.yml, tests/test_workflow_downloads_verified.py]
depends_on: []
```

**Files:** create `tests/test_workflow_downloads_verified.py`; modify `.github/workflows/auto-merge.yml` (job `secret-scan`, step `Install gitleaks`).

- [ ] **RED.** Write the test module (`unittest`, `yaml.safe_load`, `pathlib`, `shlex`). Pure function `check_run(text: str) -> tuple[int, list[str]]` returns (download count, problems) for one step's `run:` text:
  - Join continuations: `text.replace("\\\n", " ")`, then split lines.
  - Lines with `\bcurl\b` or `\bwget\b`: if `re.search(r"\|\s*(sh|bash)\b", line)` → problem `piped to shell`. Else `shlex.split` the part before any `|`; a `curl` token list containing `-o` followed by a path, or `wget` with `-O` followed by a path, is a download of that path. A `curl` with no `-o` whose line contains `| jq` is ignored. Anything else → problem `unrecognised curl/wget shape` (covers `wget -qO`, `curl -fsSLo`, `curl -O`, `> file`).
  - For download path P: the first later line containing both `sha256sum -c` and P, with no `||`, is the check. Problem if none exists, or if any line between the download and the check contains P.
  - Collect steps from every `.github/workflows/*.yml` (`jobs.*.steps`) and `.github/actions/**/action.yml` (`runs.steps`); messages name file, job, step and path.
- [ ] Synthetic controls, one test each: no checksum → problem; checksum after `tar` → problem; checksum naming another path → problem; `sha256sum -c - || true` → problem; `curl -fsSL https://x | sh` → problem; `wget -qO /tmp/a https://x` → problem; `curl -fsSL -o /tmp/a https://x` then `echo "h  /tmp/a" | sha256sum -c -` then `tar -xf /tmp/a` → no problem; `curl -s https://api | jq .x` → zero downloads, no problem.
- [ ] Live-tree test: total downloads across all steps `>= 1` and zero problems. Class `TestGitleaksPinned`: the `secret-scan` job's `Install gitleaks` step has `env.GITLEAKS_VER == "8.21.2"` and `env.GITLEAKS_SHA256 ==` the Global Constraints value.
- [ ] Run `python3 -m unittest tests.test_workflow_downloads_verified -v`: live-tree and gitleaks tests FAIL (current line is `wget -qO`, no env); synthetic tests pass.
- [ ] **GREEN.** Replace the step body with env `GITLEAKS_VER`/`GITLEAKS_SHA256` and run:
  ```bash
  set -e
  curl -fsSL -o /tmp/gitleaks.tar.gz \
    "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VER}/gitleaks_${GITLEAKS_VER}_linux_x64.tar.gz"
  echo "${GITLEAKS_SHA256}  /tmp/gitleaks.tar.gz" | sha256sum -c -
  tar -xzf /tmp/gitleaks.tar.gz -C /tmp gitleaks
  sudo mv /tmp/gitleaks /usr/local/bin/gitleaks
  gitleaks version | grep -qx "${GITLEAKS_VER}"
  ```
  (`gitleaks version` prints exactly `8.21.2`, measured.)
- [ ] Re-run the acceptance gates; commit `ci: verify gitleaks checksum; test every workflow download`.

### Task 2: cargo-deny `--locked`, workflow permissions, stale-lock fixture

```yaml-task
id: 2
description: Pass --locked in cargo-deny-all.sh, set cargo-deny.yml permissions to contents read, and prove --locked rejects a stale lockfile with an offline fixture
role: executor
model: sonnet
tdd: required
requirements: [R3, R4, R5]
acceptance:
  - cmd: bats tests/scripts/cargo_deny_all.bats tests/scripts/cargo_deny_fixtures.bats
    exit_code: 0
  - cmd: python3 -m unittest tests.test_cargo_deny_workflow -v
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
  - cmd: make test < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/cargo-deny-all.sh, .github/workflows/cargo-deny.yml, tests/scripts/cargo_deny_all.bats, tests/scripts/cargo_deny_fixtures.bats, tests/test_cargo_deny_workflow.py, tests/fixtures/cargo-deny/stale-lock/app/Cargo.toml, tests/fixtures/cargo-deny/stale-lock/app/Cargo.lock.stale, tests/fixtures/cargo-deny/stale-lock/app/src/main.rs, tests/fixtures/cargo-deny/stale-lock/dep/Cargo.toml, tests/fixtures/cargo-deny/stale-lock/dep/src/lib.rs]
depends_on: [1]
```

- [ ] **RED (argv).** In `tests/scripts/cargo_deny_all.bats` add `@test "--locked precedes check on every invocation"`: `make_crates 11`, run the script, then for every line of `${MOCK_CARGO_LOG}` assert `prefix="${line%% check}"` contains `--locked`, and count 11 lines. Fails today.
- [ ] **RED (permissions).** New `tests/test_cargo_deny_workflow.py`: `yaml.safe_load(.github/workflows/cargo-deny.yml)["permissions"] == {"contents": "read"}`. Fails today (`KeyError`).
- [ ] **RED (fixture).** Create `tests/fixtures/cargo-deny/stale-lock/`:
  - `dep/Cargo.toml`: `[package]` `name = "deny-fixture-stale-dep"`, `version = "0.1.0"`, `edition = "2024"`, `license = "MIT"`; `dep/src/lib.rs` empty.
  - `app/Cargo.toml`: same shape, `name = "deny-fixture-stale-app"`, plus `[dependencies]` `deny-fixture-stale-dep = { path = "../dep" }`; `app/src/main.rs` = `fn main() {}`.
  - `app/Cargo.lock.stale`: a lockfile listing only the app (generate in a temp copy with the dependency line removed: `cargo generate-lockfile --offline`, then copy the file here under this name). Never commit a file named `Cargo.lock` here: the existing `no Cargo.lock is left under the fixtures` test must stay unchanged.
  - In `cargo_deny_fixtures.bats` add two tests that `cp -R` the fixture to `${BATS_TEST_TMPDIR}/stale-lock` and `mv app/Cargo.lock.stale app/Cargo.lock` in the copy:
    - `"stale lock is rejected under --locked"`: `run cargo deny --locked --config "${REPO_ROOT}/deny.toml" --manifest-path <copy>/app/Cargo.toml check licenses`; `[ "$status" -ne 0 ]` and `[[ "$output" == *"cannot update the lock file"* ]]`.
    - `"stale lock passes without --locked and is rewritten"` (control): same without `--locked`; `[ "$status" -eq 0 ]` and `grep -q deny-fixture-stale-dep <copy>/app/Cargo.lock`.
- [ ] **GREEN.** `scripts/cargo-deny-all.sh`: `cargo deny --locked --config "${REPO_ROOT}/deny.toml" \`; update the comment above it to say both are global options. `cargo-deny.yml`: add top-level `permissions:` / `  contents: read` after `on:`.
- [ ] Run gates; also `bash scripts/cargo-deny-all.sh < /dev/null` prints `cargo-deny-all: all 11 crates passed` and `git status --porcelain` shows no `Cargo.lock` change. Commit `ci: run cargo-deny with --locked; read-only token`.

### Task 3: pre-push runs root `make test` on a `deny.toml` change

```yaml-task
id: 3
description: Add ^deny\.toml$ to the pre-push RUN_HOOK_TESTS regex, with bats cases for deny.toml and for a crate Cargo.toml push
role: executor
model: sonnet
tdd: required
requirements: [R6]
acceptance:
  - cmd: bats tests/scripts/pre_push.bats
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
  - cmd: make test < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/pre-push, tests/scripts/pre_push.bats]
depends_on: [2]
```

- [ ] **RED.** In `tests/scripts/pre_push.bats`, next to `"hook/script change runs the root test target"`, add with the same `run bash "${REPO_ROOT}/scripts/pre-push" <<< "refs/heads/feat abc123 refs/heads/feat abc456"` shape:
  - `"deny.toml-only push runs the root test target"`: `MOCK_GIT_DIFF_NAMES="deny.toml"`; `[ "$status" -eq 0 ]`; `grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$" "${MOCK_CALLS_FILE}"`. Fails today.
  - `"crate Cargo.toml-only push runs no make"`: `MOCK_GIT_DIFF_NAMES="pi/pi-rs/Cargo.toml"`; `[ "$status" -eq 0 ]`; `assert_no_match "^make"`. Passes today; it guards against widening the regex.
- [ ] **GREEN.** In `scripts/pre-push`, append `|^deny\.toml$` to the end of the root-scope `grep -qE '^scripts/|...'` alternation (keep it one single-quoted literal: the existing `every root-scope trigger alternative matches at least one tracked path` test parses it, and `deny.toml` is tracked).
- [ ] Run gates; commit `fix(pre-push): run root tests on deny.toml changes`.

### Task 4: Remove the unused apt step from the 24 Rust-only workflows

```yaml-task
id: 4
description: Delete the libgmp/libmpfr/libmpc apt step from the ci and release templates, gmp-cache.yml and benchmarks.yml, re-render, and pin its absence over exactly 24 files
role: executor
model: sonnet
tdd: required
requirements: [R7, R8]
acceptance:
  - cmd: python3 -m unittest tests.test_rust_workflows_no_system_gmp tests.test_crate_uniformity -v
    exit_code: 0
  - cmd: python3 scripts/render_crate_files.py --check
    exit_code: 0
  - cmd: 'test -z "$(git diff --name-only origin/master -- .github/workflows/*-py.yml .github/workflows/mutation-pr.yml .github/workflows/mutation-testing-python.yml)"'
    exit_code: 0
  - cmd: make test < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/ci.yml, scripts/crate_templates/release.yml, .github/workflows/gmp-cache.yml, .github/workflows/benchmarks.yml, tests/test_rust_workflows_no_system_gmp.py, .github/workflows/amicable-rs.yml, .github/workflows/collatz-rs.yml, .github/workflows/e-rs.yml, .github/workflows/factorial-rs.yml, .github/workflows/fib-rs.yml, .github/workflows/goldbach-rs.yml, .github/workflows/perfect-numbers-rs.yml, .github/workflows/pi-rs.yml, .github/workflows/prime-rs.yml, .github/workflows/sq-rs.yml, .github/workflows/twin-primes-rs.yml, .github/workflows/release-amicable-rs.yml, .github/workflows/release-collatz-rs.yml, .github/workflows/release-e-rs.yml, .github/workflows/release-factorial-rs.yml, .github/workflows/release-fib-rs.yml, .github/workflows/release-goldbach-rs.yml, .github/workflows/release-perfect-numbers-rs.yml, .github/workflows/release-pi-rs.yml, .github/workflows/release-prime-rs.yml, .github/workflows/release-sq-rs.yml, .github/workflows/release-twin-primes-rs.yml]
depends_on: [3]
```

- [ ] **RED.** New `tests/test_rust_workflows_no_system_gmp.py`: file set = `sorted(glob(".github/workflows/*-rs.yml")) + [gmp-cache.yml, benchmarks.yml]` (the glob yields both `<crate>-rs.yml` and `release-<crate>-rs.yml`); assert `len == 24`; for each, assert none of `libgmp-dev`, `libmpfr-dev`, `libmpc-dev` occurs in the text, naming the file. Fails today on all 24.
- [ ] **GREEN.** Delete the `- name: Install GMP and MPFR` step (name line, `run:` line, following blank line) at its 3 sites in `scripts/crate_templates/ci.yml` and 1 in `scripts/crate_templates/release.yml`; run `python3 scripts/render_crate_files.py --write`. In `gmp-cache.yml` delete the step with its `if:`; in `benchmarks.yml` delete the `libgmp-dev libmpfr-dev libmpc-dev` step. Leave every `*-py.yml` and both Python-capable mutation workflows alone (N1).
- [ ] Confirm `git diff --stat` touches exactly the 26 workflow/template files plus the test. Run gates; commit `ci: drop unused GMP apt step from Rust workflows`.

### Task 5: Docs, ADR line, Backlog rows

```yaml-task
id: 5
description: Update CLAUDE.md (≤46 bytes net), ADR-0035 and the Backlog for the bundle (docs-only, no behaviour change, so TDD does not apply)
role: executor
model: sonnet
tdd: not-applicable
requirements: []
acceptance:
  - cmd: 'test "$(wc -c < CLAUDE.md)" -le 30000'
    exit_code: 0
  - cmd: python3 scripts/claude_md_budget.py HEAD
    exit_code: 0
  - cmd: grep -q 'deny.toml' CLAUDE.md
    exit_code: 0
  - cmd: grep -c 'local dependency check' docs/superpowers/README.md
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [CLAUDE.md, docs/adr/0035-mit-licence-cargo-deny-and-lgpl-notices.md, docs/superpowers/README.md]
depends_on: [4]
```

- [ ] `CLAUDE.md`: in the Pre-push paragraph change "touches `scripts/`, `tests/`, `typings/` or the root `Makefile`" to "touches `scripts/`, `tests/`, `typings/`, `deny.toml` or the root `Makefile`"; in the CI line "`scripts/cargo-deny-all.sh` checks all 11 crates" append " (`--locked`)". Check `wc -c CLAUDE.md` ≤ 30000.
- [ ] ADR-0035: append under Decision one dated line: "2026-10-31: `cargo-deny-all.sh` passes `--locked`; a `deny.toml` push runs root `make test` locally; no local real-crate run (offline cache measurements in the CI supply-chain bundle spec)."
- [ ] `docs/superpowers/README.md` Backlog: delete the four rows (gitleaks checksum; `cargo-deny.yml` hardening; pre-push `deny.toml`; unused apt step). Add two rows: "`*-py.yml` and Python mutation workflows still apt-install GMP | unmeasured whether gmpy2 wheels need system GMP; Rust-only workflows dropped it in the CI supply-chain bundle" and "Local dependency check before push | offline `cargo deny` resolves from `~/.cargo` while builds cache into `<worktree>/.cache/cargo-home`, so a dependency-change push fails with `no matching package`; cargo-deny 0.20.2 has no offline-DB/online-crates flag. Detail: [spec](specs/2026-10-31-ci-supply-chain-bundle-design.md)". Add a plan-index row for this plan if absent.
- [ ] Run gates; commit `docs: CI supply-chain bundle notes`.

## Non-goal check

Reviewer verdicts (4 CLEAR, 0 CONFLICT, 0 UNCLEAR):

- N1 CLEAR — Task 4 scopes to `*-rs.yml`, `gmp-cache.yml` and `benchmarks.yml`, and an acceptance gate fails if any `*-py.yml` or Python mutation workflow differs from `origin/master`.
- N2 CLEAR — no task lists `deny.toml` or `tests/test_deny_policy.py` in `files_touched`.
- N3 CLEAR — Task 1 swaps `wget` for `curl`, both preinstalled; Task 2's fixture crates are local path packages, not dependencies.
- N4 CLEAR — Task 3 runs root `make test`, whose real cargo-deny calls touch only fixture crates; the one `--offline` is a one-time `cargo generate-lockfile` while authoring the fixture; `--locked` goes to cargo-deny, not a build step.

Resolution: none needed.
