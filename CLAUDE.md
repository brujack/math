# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

One line per rule; detail behind pointers to `ai-config/docs/knowledge/math-*.md`. `CLAUDE.md` is capped at 30,000 bytes by `scripts/claude_md_budget.py` (ADR-0028).

A trailing pointer on a rule means: before acting on that rule's subject, read the named heading for the procedure, history and measurements.

## Repository Overview

High-performance mathematical computation tools.

Each sub-project has its own `CLAUDE.md`, the source of truth for its implementation detail (`twin-primes`' is `twin-primes/twin-primes-rs/CLAUDE.md`); keep this file and those in sync. → ai-config/docs/knowledge/math-overview.md § Sub-project table
Sub-projects (dir: language): `pi/` Python+Rust, `prime/` Rust, `fib/` Python+Rust, `sq/` Python+Rust, `twin-primes/` Rust, `e/` Python+Rust, `factorial/` Python+Rust, `perfect-numbers/` Python+Rust, `collatz/` Python+Rust, `goldbach/` Rust, `amicable/` Python+Rust. → ai-config/docs/knowledge/math-overview.md § Sub-project table
Rust crates live at `<project>/<project>-rs/` (all 11 projects, e.g. `pi/pi-rs`, `twin-primes/twin-primes-rs`); the 8 Python sub-projects sit at `<project>/` (pi, fib, sq, e, factorial, perfect-numbers, collatz, amicable).

## Architectural Decision Records

Write an ADR in `docs/adr/` (index `docs/adr/README.md`) before or alongside any significant choice (algorithm, library, CI structure). → ai-config/docs/knowledge/math-overview.md § Architectural Decision Records

## 10-80-10 Execution Cycle

Follow the 10-80-10 cycle of `ai-config` ADR-0009 (ADR-0010 wave dispatch): Phase 1 Architect (`brainstorming` → `writing-plans`, Opus), Phase 2 Execute (`subagent-driven-development`, Sonnet/Haiku per plan), Phase 3 Review (`finishing-a-development-branch`, Opus); plans use `yaml-task` blocks (`role`, `model`, `tdd`, `acceptance`, `max_retries`, `files_touched`, `depends_on`, `parallel_group`). → ai-config/docs/knowledge/math-overview.md § 10-80-10 cycle
Run `make validate-plan PLAN=docs/superpowers/plans/<file>.md` before dispatching a plan (validator `~/.claude/scripts/validate-plan.py`, shared from ai-config). → ai-config/docs/knowledge/math-overview.md § 10-80-10 cycle

## Knowledge Directory

Reference material lives in `ai-config/docs/knowledge/math-<topic>.md` (ADR-0020); save web-research findings there, not in CLAUDE.md. → ai-config/docs/knowledge/math-overview.md § Knowledge directory

## Dependency Installation

Each sub-project has its own installer: `<project>/install_deps.sh` for Python, `<project>/<project>-rs/install_deps.sh` for Rust (19 total; `goldbach`, `prime` and `twin-primes` have only the nested Rust one). → ai-config/docs/knowledge/math-dependency-installation.md § Installer table
Rust installers add the toolchain, `cargo-tarpaulin` (not for `sq-rs`) and GMP (+ MPFR for pi/e/factorial) where needed; Python installers add `ruff`, `coverage`, `pytest`, `pytest-cov` (plus GMP + MPFR, `mpmath`, `gmpy2` for pi/e/factorial). → ai-config/docs/knowledge/math-dependency-installation.md § Installer table

Root-scope Python has no `install_deps.sh` by design: `requirements-dev.txt` (`defusedxml==0.7.1`, `pyyaml==6.0.3`) is consumed by `make install-deps`. → ai-config/docs/knowledge/math-dependency-installation.md § Root-scope Python

## Quick Reference

### Setup (run once per checkout)

```bash
make install-hooks   # installs pre-commit and pre-push hooks
make install-deps    # installs root-scope Python's third-party imports
```

`make install-deps` refuses on a PEP 668 externally-managed interpreter; the remedy is `python3 -m venv .venv && . .venv/bin/activate`. → ai-config/docs/knowledge/math-quick-reference.md § Setup

### Python (`<project>/`)

Run from `<project>/`; `<name>` is the module and test file stem: pi, fib, sq, e, factorial, `perfect_numbers` (dir `perfect-numbers`), collatz, amicable (so `make run` runs `python3 <name>.py`, `make test` runs `pytest test_<name>.py -v`).

```bash
cd <project>
make run       # python3 <name>.py
make lint      # ruff check .
make test      # lint, then pytest test_<name>.py -v
make coverage  # pytest --cov, fails under 90%
```

### Rust (`<project>/<project>-rs/`)

All 11 projects (pi, prime, fib, sq, twin-primes, e, factorial, perfect-numbers, collatz, goldbach, amicable); the release build target is named after the project (`make pi`, `make twin-primes`, `make perfect-numbers`, ...). → ai-config/docs/knowledge/math-quick-reference.md § Sub-project command blocks

```bash
cd <project>/<project>-rs
make <project>  # cargo build --release
make lint       # cargo fmt --check, then cargo clippy --all-targets -- -D warnings
make test       # lint, then cargo test
```

A single `ruff.toml` at the repo root serves all 8 Python sub-projects via ancestor discovery; keep one root `ruff.toml` only and never create per-subproject configs. → ai-config/docs/knowledge/math-quick-reference.md § Ruff config
`ruff==0.16.4` is pinned at all 17 install sites (8 `*-py.yml` workflows, `scripts.yml`, 8 `install_deps.sh`); bump them together. → ai-config/docs/knowledge/math-quick-reference.md § Ruff config
Root `make lint` runs `ruff check .` plus `ruff format --check` scoped to `git ls-files '*.py'` (never `ruff format --check .`, which rewrites markdown code blocks) alongside `lint-hooks`. → ai-config/docs/knowledge/math-quick-reference.md § Ruff config
`lint-python` exits 0 when ruff is missing (so a machine can still commit the fix); `scripts.yml` installs ruff so CI enforces it, and `tests/scripts/makefile.bats` asserts that. → ai-config/docs/knowledge/math-quick-reference.md § Ruff config
The two `# noqa: C901` directives in `e/e.py` and `pi/pi.py` are load-bearing: `maintainability-review` runs `ruff check --select C901` on the CLI, which overrides config, so removing one without refactoring reads as a 0 → 21 regression. → ai-config/docs/knowledge/math-quick-reference.md § Ruff config

### Rust lint/test wrapper (`scripts/rust-check.sh`)

All Rust crate `make lint` and `make test` go through `scripts/rust-check.sh`; `CARGO_HOME` defaults to `<repo>/.cache/cargo-home` when unset and `RUST_CHECK_OFFLINE=1` adds `--offline`. → ai-config/docs/knowledge/math-quick-reference.md § Rust lint/test wrapper
Treat `.cache/` as transient local state: remove it (`rm -rf .cache`) before final status checks and commits. → ai-config/docs/knowledge/math-quick-reference.md § Rust lint/test wrapper

## Language Standards

Neither file below is loaded at session start. Read it before the work it governs:

- **Read `~/.claude/standards/python.md` before writing or changing any `.py` file or Python tooling config** (`ruff.toml`, `pyrightconfig.json`, `install_deps.sh`, `requirements-dev.txt`, a `*-py.yml` workflow, mutmut/cosmic-ray setup).
- **Read `~/.claude/standards/rust.md` before writing or changing any `.rs` file, `Cargo.toml`, `.cargo/mutants.toml`, `rustfmt.toml`, `scripts/rust-check.sh` or a `*-rs.yml` workflow.** The trigger includes source on purpose. → ai-config/docs/knowledge/math-language-standards.md § Language standards triggers


### API-quality lints (all 11 Rust crates)

Every `*-rs/Cargo.toml` enables `missing_debug_implementations = "warn"` (`[lints.rust]`) and `wrong_self_convention = "warn"` (`[lints.clippy]`); clippy runs `-D warnings`, so a `pub struct` without `#[derive(Debug)]` fails `make lint`. → ai-config/docs/knowledge/math-language-standards.md § API-quality lints in the Rust crates
Do not enable `missing_docs` in these crates (no cross-crate consumers). → ai-config/docs/knowledge/math-language-standards.md § API-quality lints in the Rust crates


## Testing Policy

**TDD is required.** Write the failing test first, then write the minimum implementation to make it pass. Never write implementation before the test. Tests must be added in the same commit as the code they cover.

Every test must cover more than the happy path. Three categories are required for every function:

- **Boundary value tests** — empty/zero/null input, single vs multiple elements, min/max valid values, one above/below valid range
- **Error path tests** — what happens on failure, dependency failure, partial failure
- **State transition tests** — before/after assertions, no unintended side effects, idempotency

Where to add tests:

- Python tests: add to `pi/test_pi.py` (pi), `fib/test_fib.py` (fib), `sq/test_sq.py` (sq), `e/test_e.py` (e), or `factorial/test_factorial.py` (factorial), run with `make test` from the project directory
- Rust tests: add to the `#[cfg(test)] mod tests` block in `src/main.rs`, run with `make test`
- Coverage tools: `make coverage` (Python), `cargo tarpaulin` (Rust)

Coverage floor: 90% for Python and Rust per sub-project, never lowered.

### Type checking (Python — pyright)

Every Python sub-project has a `pyrightconfig.json` and a `Run pyright` step in its CI workflow.

Modes: `standard` for amicable, collatz, fib, sq, factorial, perfect-numbers; `basic` for pi and e (gmpy2 has no type stubs; `reportAttributeAccessIssue` and `reportOptionalMemberAccess` suppressed). → ai-config/docs/knowledge/math-testing-policy.md § Pyright modes


Root-scope Python (`tests/`, `scripts/`, `.claude/scripts/`) is gated by a root `pyrightconfig.json` (`standard` mode, `include` `["scripts", "tests", ".claude/scripts"]`) over every tracked root-scope `.py` file (count: `git ls-files 'tests/*.py' 'scripts/*.py' '.claude/scripts/*.py' | wc -l`). → ai-config/docs/knowledge/math-testing-policy.md § Root-scope pyright
Its `exclude` is pyright's default list minus `**/.*`, and the omission is load-bearing: exclude beats include, and `**/.*` would drop `.claude/scripts`. → ai-config/docs/knowledge/math-testing-policy.md § Root-scope pyright
`pyright==1.1.411` is pinned only at the `scripts.yml` install site; the other 8 `*-py.yml` workflows install it unpinned (backlog row). → ai-config/docs/knowledge/math-testing-policy.md § Root-scope pyright
`tests/test_root_pyright_scope.py` runs pyright under `make test-python`, which pre-push invokes on pushes touching `scripts/`, `tests/`, `.claude/scripts/` or `pyrightconfig.json`; sub-project pyright stays CI-only. → ai-config/docs/knowledge/math-testing-policy.md § Root-scope pyright
pyright walks up the tree for its config like `ruff.toml`: deleting a sub-project's `pyrightconfig.json` falls through to the root config instead of removing type checking. → ai-config/docs/knowledge/math-testing-policy.md § Root-scope pyright
Run pyright manually with `cd <sub-project> && pyright`; for root scope run `pyright` from the repo root.


When adding a new Python sub-project, add `pyrightconfig.json` (copy from any `standard`-mode sub-project) and a `Run pyright` step to the CI workflow. Start with `standard` mode; fall back to `basic` only if the dependency has no stubs.

### Mutation testing (Rust)

Rust mutation testing uses `cargo-mutants` (`cargo install cargo-mutants --locked`); run `make mutants` in a crate directory; correctness over coverage %, a kill rate above 80% is good for math code. → ai-config/docs/knowledge/math-testing-policy.md § Mutation testing
Mutation CI is `.github/workflows/mutation-testing.yml` (monthly `cron: "0 4 1 * *"` plus `workflow_dispatch`), calling `make -C <crate> mutants` so local and CI share one definition. → ai-config/docs/knowledge/math-testing-policy.md § Mutation testing

Never put a fixed `--timeout` back (#95): keep `--timeout-multiplier 5 --minimum-test-timeout 30` in each crate's `Makefile` `mutants` target, not the workflow, because a fixed value caps the unmutated baseline and evaluated zero mutants for a month; `tests/scripts/makefile.bats` pins both halves across all 11 crates. → ai-config/docs/knowledge/math-testing-policy.md § Mutation timeout

Keep `ulimit -v 8388608` (8 GiB) in the same `mutants` recipe; macOS cannot enforce it, so set `MUTANTS_UNCAPPED=1` deliberately there (the recipe fails closed otherwise). → ai-config/docs/knowledge/math-testing-policy.md § Mutation memory cap

A mutation leg is red only when `caught + missed == 0`, the baseline fails or the runner dies; survivors (exit 2) and timeouts (exit 3) are green (`scripts/mutation-classify.sh`, `tests/scripts/mutation_classify.bats`). → ai-config/docs/knowledge/math-testing-policy.md § Mutation green/red

The notify job stays separate (`needs: [mutants], if: always()`) with `issues: write` only, labelled `mutation-failure` (`mutation-failure-python` via `ISSUE_LABEL` for the Python workflow); `scripts/mutation-notify.sh` derives the cause from the `marker/job-began` breadcrumb. → ai-config/docs/knowledge/math-testing-policy.md § Mutation notification
Add `mutants` to a new Rust crate's `Makefile` `.PHONY` list and target; investigate surviving mutants in logic code, not main glue. → ai-config/docs/knowledge/math-testing-policy.md § Mutation notification


Exclude equivalent mutants via the crate's `.cargo/mutants.toml` `exclude_re` regexes matched against `src/lib.rs:<line>:<col>: <description>`; `// mutants::skip` is not recognized (cargo-mutants ≥27.x), only `#[mutants::skip]` on items. → ai-config/docs/knowledge/math-testing-policy.md § Equivalent mutations
`exclude_re` patterns embed line numbers; update them when surrounding code shifts (worked example `factorial/factorial-rs/.cargo/mutants.toml`). → ai-config/docs/knowledge/math-testing-policy.md § Equivalent mutations


A mutation on a comparison that algebraic identity makes always true (e.g. `verify_perfect`) is a dead-code equivalent; exclude it in `.cargo/mutants.toml`. → ai-config/docs/knowledge/math-testing-policy.md § Algebraic-identity equivalents


In prompt tests supplying N via `io::Cursor`, assert the concrete output artifact (e.g. `assert!(dir.path().join("goldbach_1e2.txt").exists());`) to kill guard `→ true` mutations. → ai-config/docs/knowledge/math-testing-policy.md § Prompt-guard assertions


## CI

Project workflows run on PRs to `master` only; the pre-push hook gates branch pushes locally; a build job depends on its test job (`needs: [test]`). → ai-config/docs/knowledge/math-ci.md § Workflow table
Workflows are `<project>-py.yml` (job `test`) and `<project>-rs.yml` (`test` → build + artifact), `release-<project>-rs.yml` (manual dispatch), plus `auto-merge.yml`, `mutation-pr.yml`, `mutation-testing.yml`, `mutation-testing-python.yml`, `scripts.yml` (list with `git ls-files .github/workflows/`). → ai-config/docs/knowledge/math-ci.md § Workflow table
`auto-merge.yml` runs secret-scan, bash-coverage and claude-md-budget (gated), then ci-gate (polls required checks, merges on pass), then snyk-scan (advisory, not gated); `scripts.yml` runs `bats --recursive tests/`. → ai-config/docs/knowledge/math-ci.md § Workflow table


Every `release-*-rs.yml` builds with `cargo auditable build --release` (a plain build makes the SBOM list 1 package instead of 13). → ai-config/docs/knowledge/math-ci.md § Atomic release publication
Sign in the release job via the composite action `.github/actions/sbom-sign`; never reintroduce a separate signing job, and keep the `Create and push tag` step after the sbom-sign step (a failure after the tag leaves an unshippable version: `fatal: tag already exists`). → ai-config/docs/knowledge/math-ci.md § Atomic release publication
Every `softprops/action-gh-release` call sets `fail_on_unmatched_files: true`; `tests/test_release_workflows.py` pins all three invariants via `yaml.safe_load`. → ai-config/docs/knowledge/math-ci.md § Atomic release publication
Release workflows use `workflow_dispatch` with a `version` input (no `v`) and create tag `{subproject}-v{version}` themselves.
Release and CI jobs run Node.js 24 with `actions/checkout@v7`; Rust builds `needs: [test]` and use `actions/upload-artifact@v7` (7 days); badges use `?event=pull_request`.


Pre-commit: `scripts/pre-commit` (installed by `make install-hooks`) runs `make lint` on staged sub-projects and `ggshield secret scan pre-commit` (skipped if absent); install ggshield locally. → ai-config/docs/knowledge/math-ci.md § Pre-commit hook


Pre-push: `scripts/pre-push` (installed by `make install-hooks`) runs `make test` per sub-project with `.py`/`.rs` source changes, and the root `make test` (`lint test-hooks test-python`) when the push touches `scripts/`, `tests/` or the root `Makefile`, else root `make lint-hooks` when it touches any `.sh` (e.g. an `install_deps.sh`), and refuses a pushed commit that changes `CLAUDE.md` past the 30000-byte ceiling; it skips branch deletions and is permanent. → ai-config/docs/knowledge/math-ci.md § Pre-push hook
math's hooks bypass root `test:`, so fix the hooks (not the root target) when lint or test coverage on push is wrong. → ai-config/docs/knowledge/math-ci.md § Pre-push hook


Trigger pre-push tests on `.py`/`.rs` source changes only; Makefile, workflow and doc changes must not run the suites (macOS `resource_tracker` daemons accumulate and hang), and run `make test < /dev/null`. → ai-config/docs/knowledge/math-ci.md § resource_tracker gotcha


`scripts/pre-push` resolves the repo root with `git rev-parse --show-toplevel` first, `--git-common-dir` parent only as fallback, or worktrees test the shared checkout instead of the feature worktree. → ai-config/docs/knowledge/math-ci.md § Worktree compatibility


**Shell script testing** — BATS (`bats --recursive tests/`) is the standard for all shell script tests in this repo. Run with `make test-hooks`. Requires system-installed bats-core: `brew install bats-core` (macOS) or `sudo apt-get install -y bats` (Linux).

`make test-python` runs `python3 -m unittest discover -s tests -p 'test_*.py'` and `make test` runs `test-hooks` then `test-python`; `scripts.yml` calls both. → ai-config/docs/knowledge/math-ci.md § Repo-level Python tests


`.claude/scripts/triage_log.py` is vendored per-repo because its `.resolve()` follows the `~/.claude/scripts/` symlink and would write this repo's triage log into ai-config; invoke the vendored copy, not the home path. → ai-config/docs/knowledge/math-ci.md § triage_log.py


Test helpers: `tests/helpers/common.bash` (REPO_ROOT, `load_mocks()`), PATH-injected mocks in `tests/mocks/` (`make`, `git`, `ggshield`, `gh`, `syft`, `cosign`), BATS files in `tests/scripts/` (one per script tested). → ai-config/docs/knowledge/math-ci.md § Test helpers and mocks
`tests/mocks/*` are extensionless and linted via `$(wildcard tests/mocks/*)` in `SHELL_SOURCES`; verify a lint change by seeding a defect and watching `make lint-hooks` fail. → ai-config/docs/knowledge/math-ci.md § Test helpers and mocks


### Bash Coverage

`scripts/run-bash-coverage.sh` is a per-repo copy of dotfiles' (`67417bc`, re-synced math#108); re-sync from dotfiles master when upstream changes (one PR per copy per change); its header lists math's divergences. → ai-config/docs/knowledge/math-ci.md § Bash coverage re-sync


`make bash-coverage` runs the PS4 tracer over the bats suite (skipped if `bats` is missing; not in `make test` or `make lint`); inspect with `bash scripts/run-bash-coverage.sh --list-sources`, `--count-coverable <file>`, `--file-coverage <file> <trace>`; predicate tests in `tests/scripts/bash_coverage.bats`. → ai-config/docs/knowledge/math-ci.md § Bash Coverage


The instrumented set is derived from `git ls-files 'scripts/*.sh' '*/install_deps.sh' '*/*/install_deps.sh' scripts/pre-push scripts/pre-commit scripts/commit-msg` minus `scripts/bash-tracer.sh`; keep the 19 `install_deps.sh` in the denominator (untested, not uncoverable). → ai-config/docs/knowledge/math-ci.md § Bash coverage predicate


The `bash-coverage` job in `auto-merge.yml` gates at `FLOOR=24`, defined once in that step and set from CI's own measurement on `ubuntu-latest`, never a local run. → ai-config/docs/knowledge/math-ci.md § Bash coverage floor
The floor is a regression ratchet over the reachable quarter of the denominator, not a quality bar for the repo's shell. → ai-config/docs/knowledge/math-ci.md § Bash coverage floor


`scripts/ci-gate.sh <PR>` polls `gh pr checks` and fails on any non-advisory failure (`snyk-scan` is advisory; `secret-scan` and `auto-merge` are self-checks); tested via `tests/scripts/ci_gate.bats` with `tests/mocks/gh`. → ai-config/docs/knowledge/math-ci.md § Auto-merge gate


A Rust workflow calling `scripts/test_metrics.py` (today `factorial-rs.yml`) needs `pip install defusedxml` (a step named `Install Python dependencies`, `if: always()`) immediately before `Generate test metrics`, or CI fails with `ModuleNotFoundError`. → ai-config/docs/knowledge/math-ci.md § test_metrics.py in Rust workflows


### Renovate auto-merge policy

`renovate.json`'s `packageRules` must begin with the five canonical rules of ai-config `renovate-presets/default.json` (`renovate_preset_sync.py` tests prefix equality and reports DRIFT; appended rules are deviations); rules 3-4 hold Python interpreter updates. → ai-config/docs/knowledge/math-ci.md § Renovate auto-merge policy
Each of the ten `updateType`s must be auto-merged or declared in `_DELIBERATELY_HELD` in `tests/test_renovate_automerge_policy.py`; do not name held types in `renovate.json`. → ai-config/docs/knowledge/math-ci.md § Renovate auto-merge policy


Project workflows are paths-filtered (root `Makefile` covered by `scripts.yml`); release workflows and `auto-merge.yml` trigger unconditionally. → ai-config/docs/knowledge/math-ci.md § Paths-filtered workflows


**snyk-scan** runs `snyk code test` (SAST) against the Python and Rust source. It is advisory — not in `needs` for `auto-merge`. Requires `SNYK_TOKEN` in repository secrets.

A new project gets `.github/workflows/<project>.yml` triggered only by `pull_request: branches: [master]` (no `push:`) with a `paths:` block, a `test` job and a `build` job (`needs: [test]`) uploading an artifact, plus a README badge `badge.svg?event=pull_request` at the top and in the CI column. → ai-config/docs/knowledge/math-ci.md § Adding a new project workflow


## Branch Workflow

**Never commit directly to `master`.** All changes — features, fixes, docs — go through a feature branch and PR.

**Worktree directory:** Use `.worktrees/` (project-local, listed in `.gitignore`) for all git worktrees in this repo.

```bash
git worktree add .worktrees/<branch-name> -b <type>/<short-description>
# work in .worktrees/<branch-name>/
git push -u origin <branch>
gh pr create --title "..." --body "..."
```

The pre-push hook runs `make test` for changed sub-projects locally before the push reaches GitHub. GitHub Actions CI runs on PRs only. The `auto-merge` workflow enables GitHub auto-merge when the PR is opened; it merges automatically once all required checks pass.

Auto-merge lands a PR as soon as its required checks pass, so run Phase 3 (`finishing-a-development-branch`) before marking it ready for review; open your own changes as a draft PR.

### Multiprocessing fallback behavior

Python high-precision calculators (`pi`, `e`, `factorial`) must fall back to serial when `ProcessPoolExecutor` fails, print an explicit message that serial mode is active, and tell the user to fix multiprocessing semaphore support. → ai-config/docs/knowledge/math-branch-workflow.md § Multiprocessing fallback


## Keeping CLAUDE.md Up To Date

**When making any change to this repository, update the relevant CLAUDE.md file(s) before finishing.** These files are the primary reference for future sessions — stale documentation is worse than none.

Per-change update map (new function, Makefile target, dependency, test class, project, behaviour change, rule change) and the new-project checklist (workflow, badge, CI table, loops in `scripts/pre-commit` and `scripts/pre-push`). → ai-config/docs/knowledge/math-claude-md-maintenance.md § Update map
Sub-project `CLAUDE.md` files are the source of truth for implementation detail; this file is the entry point and quick reference. → ai-config/docs/knowledge/math-claude-md-maintenance.md § Update map


## Notes

Verify rust-check wrapper changes with unit tests (`python3 scripts/test_rust_check.py`) plus a full online+offline crate matrix before merge. → ai-config/docs/knowledge/math-quick-reference.md § rust-offline-wrapper learnings


- Generated output files (`pi_*_digits.txt`, `primes_1e*.txt`, `twin-primes_1e*.txt`, `e_*_digits.txt`, `factorial_*.txt`) are large artifacts — do not commit them.
- See each project's `CLAUDE.md` for detailed implementation guidance, code layout, and editing rules.

## Definition of Done

The universal DoD in `behavior.md` applies. math adds:

- [ ] Rust coverage ≥90% on Linux CI — verify from CI output (`gh run view --repo brujack/math <id> --log | grep Coverage`)
- [ ] BATS failure-mode tests added/updated for any new or modified CLI
- [ ] Plan index updated (`docs/superpowers/README.md`) if this PR implements a tracked spec
- [ ] Root `README.md` CLI table updated if a new CLI was added
