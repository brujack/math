# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

High-performance mathematical computation tools.

| Project                                | Language      | Description                                                       | CLAUDE.md                                                                      |
| -------------------------------------- | ------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| [`pi/`](pi/)                           | Python + Rust | Calculate π to N decimal places (Chudnovsky algorithm)            | [`pi/CLAUDE.md`](pi/CLAUDE.md)                                                 |
| [`prime/`](prime/)                     | Rust          | Find all primes up to 10^N (segmented sieve)                      | [`prime/CLAUDE.md`](prime/CLAUDE.md)                                           |
| [`fib/`](fib/)                         | Python + Rust | Generate all Fibonacci numbers with up to 10^X digits             | [`fib/CLAUDE.md`](fib/CLAUDE.md)                                               |
| [`sq/`](sq/)                           | Python + Rust | Find all perfect squares with up to 10^N digits (N=1 max)         | [`sq/CLAUDE.md`](sq/CLAUDE.md)                                                 |
| [`twin-primes/`](twin-primes/)         | Rust          | Find all twin prime pairs up to 10^N                              | [`twin-primes/twin-primes-rs/CLAUDE.md`](twin-primes/twin-primes-rs/CLAUDE.md) |
| [`e/`](e/)                             | Python + Rust | Calculate e to N decimal places (Taylor series)                   | [`e/CLAUDE.md`](e/CLAUDE.md)                                                   |
| [`factorial/`](factorial/)             | Python + Rust | Compute N! to arbitrary precision (prime swing)                   | [`factorial/CLAUDE.md`](factorial/CLAUDE.md)                                   |
| [`perfect-numbers/`](perfect-numbers/) | Python + Rust | Find all perfect numbers up to 10^N (Lucas-Lehmer + sigma)        | [`perfect-numbers/CLAUDE.md`](perfect-numbers/CLAUDE.md)                       |
| [`collatz/`](collatz/)                 | Python + Rust | Find Collatz chain record-setters up to 10^N (vector memoization) | [`collatz/CLAUDE.md`](collatz/CLAUDE.md)                                       |
| [`goldbach/`](goldbach/)               | Rust          | Find all Goldbach pairs for even n up to 10^N (bitset sieve)      | [`goldbach/CLAUDE.md`](goldbach/CLAUDE.md)                                     |
| [`amicable/`](amicable/)               | Python + Rust | Find all amicable pairs (a,b) with b ≤ 10^N (proper-divisor sum sieve) | [`amicable/CLAUDE.md`](amicable/CLAUDE.md)                                |

## Architectural Decision Records

Significant architectural decisions are recorded in [`docs/adr/`](docs/adr/README.md). When making a significant choice (algorithm, library, CI structure), write an ADR before or alongside the implementation.

## Knowledge Directory

Reference material lives in `docs/knowledge/`. These documents capture algorithm reference sheets, numerical library notes, and curated research findings — things too detailed for CLAUDE.md but useful to look up. See `docs/knowledge/README.md` for what belongs there and what doesn't.

When web research (web-research skill) or context-mode fetches produce findings worth preserving, save them to `docs/knowledge/<topic>.md`.

## Dependency Installation

Each project has its own installer:

| Script                                               | Installs                                          |
| ---------------------------------------------------- | ------------------------------------------------- |
| `pi/install_deps.sh`                                 | GMP + MPFR, `mpmath`, `gmpy2`, `coverage`         |
| `pi/pi-rs/install_deps.sh`                           | GMP + MPFR, Rust toolchain, `cargo-tarpaulin`     |
| `prime/prime-rs/install_deps.sh`                     | Rust toolchain, `cargo-tarpaulin`                 |
| `fib/install_deps.sh`                                | `ruff`, `coverage`                                |
| `fib/fib-rs/install_deps.sh`                         | GMP, Rust toolchain, `cargo-tarpaulin`            |
| `sq/install_deps.sh`                                 | `ruff`, `coverage`                                |
| `sq/sq-rs/install_deps.sh`                           | Rust toolchain                                    |
| `twin-primes/twin-primes-rs/install_deps.sh`         | Rust toolchain, `cargo-tarpaulin`                 |
| `e/install_deps.sh`                                  | GMP + MPFR, `mpmath`, `gmpy2`, `ruff`, `coverage` |
| `e/e-rs/install_deps.sh`                             | GMP + MPFR, Rust toolchain, `cargo-tarpaulin`     |
| `factorial/install_deps.sh`                          | GMP + MPFR, `gmpy2`, `mpmath`, `ruff`, `coverage` |
| `factorial/factorial-rs/install_deps.sh`             | GMP + MPFR, Rust toolchain, `cargo-tarpaulin`     |
| `perfect-numbers/install_deps.sh`                    | `ruff`, `coverage`                                |
| `perfect-numbers/perfect-numbers-rs/install_deps.sh` | GMP, Rust toolchain, `cargo-tarpaulin`            |
| `collatz/install_deps.sh`                            | `ruff`, `coverage`                                |
| `collatz/collatz-rs/install_deps.sh`                 | Rust toolchain, `cargo-tarpaulin`                 |
| `goldbach/goldbach-rs/install_deps.sh`               | Rust toolchain, `cargo-tarpaulin`                 |
| `amicable/install_deps.sh`                           | `ruff`, `coverage`                                |
| `amicable/amicable-rs/install_deps.sh`               | Rust toolchain, `cargo-tarpaulin`                 |

## Quick Reference

### Setup (run once per checkout)

```bash
make install-hooks   # installs pre-commit and pre-push hooks
```

### Python (`pi/`)

```bash
cd pi
make run       # python3 pi.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_pi -v
make coverage  # coverage run + report
```

### Rust (`pi/pi-rs/`)

```bash
cd pi/pi-rs
make pi        # cargo build --release
make lint      # cargo fmt --check, then cargo clippy --all-targets -- -D warnings
make test      # lint, then cargo test
```

### Rust (`prime/prime-rs/`)

```bash
cd prime/prime-rs
make prime     # cargo build --release
make lint      # cargo fmt --check, then cargo clippy --all-targets -- -D warnings
make test      # lint, then cargo test
```

### Python (`fib/`)

```bash
cd fib
make run       # python3 fib.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_fib -v
make coverage  # coverage run + report
```

### Rust (`fib/fib-rs/`)

```bash
cd fib/fib-rs
make fib       # cargo build --release
make lint      # cargo fmt --check, then cargo clippy --all-targets -- -D warnings
make test      # lint, then cargo test
```

### Python (`sq/`)

```bash
cd sq
make run       # python3 sq.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_sq -v
make coverage  # coverage run + report
```

### Rust (`sq/sq-rs/`)

```bash
cd sq/sq-rs
make sq        # cargo build --release
make lint      # cargo fmt --check, then cargo clippy --all-targets -- -D warnings
make test      # lint, then cargo test
```

### Rust (`twin-primes/twin-primes-rs/`)

```bash
cd twin-primes/twin-primes-rs
make twin-primes  # cargo build --release
make lint         # cargo fmt --check, then cargo clippy --all-targets -- -D warnings
make test         # lint, then cargo test
```

### Python (`e/`)

```bash
cd e
make run       # python3 e.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_e -v
make coverage  # coverage run + report
```

### Rust (`e/e-rs/`)

```bash
cd e/e-rs
make e         # cargo build --release
make lint      # cargo fmt --check, then cargo clippy --all-targets -- -D warnings
make test      # lint, then cargo test
```

### Python (`factorial/`)

```bash
cd factorial
make run       # python3 factorial.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_factorial -v
make coverage  # coverage run + report
```

### Rust (`factorial/factorial-rs/`)

```bash
cd factorial/factorial-rs
make factorial # cargo build --release
make lint      # cargo fmt --check, then cargo clippy --all-targets -- -D warnings
make test      # lint, then cargo test
```

### Python (`perfect-numbers/`)

```bash
cd perfect-numbers
make run       # python3 perfect_numbers.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_perfect_numbers -v
make coverage  # coverage run + report
```

### Rust (`perfect-numbers/perfect-numbers-rs/`)

```bash
cd perfect-numbers/perfect-numbers-rs
make perfect-numbers  # cargo build --release
make lint             # cargo fmt --check, then cargo clippy --all-targets -- -D warnings
make test             # lint, then cargo test
```

### Python (`collatz/`)

```bash
cd collatz
make run       # python3 collatz.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_collatz -v
make coverage  # coverage run + report
```

### Rust (`collatz/collatz-rs/`)

```bash
cd collatz/collatz-rs
make collatz   # cargo build --release
make lint      # cargo fmt --check, then cargo clippy --all-targets -- -D warnings
make test      # lint, then cargo test
```

### Rust (`goldbach/goldbach-rs/`)

```bash
cd goldbach/goldbach-rs
make goldbach  # cargo build --release
make lint      # cargo fmt --check, then cargo clippy --all-targets -- -D warnings
make test      # lint, then cargo test
```

### Python (`amicable/`)

```bash
cd amicable
make run       # python3 amicable.py
make lint      # ruff check .
make test      # lint, then python3 -m unittest test_amicable -v
make coverage  # coverage run + report
```

### Rust (`amicable/amicable-rs/`)

```bash
cd amicable/amicable-rs
make amicable  # cargo build --release
make lint      # cargo fmt --check, then cargo clippy --all-targets -- -D warnings
make test      # lint, then cargo test
```

### Rust lint/test wrapper (`scripts/rust-check.sh`)

All Rust crate `make lint` and `make test` targets call `scripts/rust-check.sh` to enforce consistent cargo behavior in local checkouts and worktrees.

- `CARGO_HOME` defaults to `<repo>/.cache/cargo-home` when unset, so checks do not rely on global cargo cache write access.
- `RUST_CHECK_OFFLINE=1` enables `--offline` for local resilience when dependencies are already cached.
- Failures are classified as either environment/setup problems (cache/index/network permissions) or code failures (lint/test defects).

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

**Coverage floor: ≥90% line coverage is required for all Rust crates.** This is enforced in CI — each Rust workflow runs `cargo tarpaulin --fail-under 90` in the `test` job after `make test`. A PR that drops any crate below 90% will fail CI and cannot auto-merge. The pre-push hook does not check coverage locally (too slow); CI is the gate.

**Linux vs macOS tarpaulin divergence.** Linux ptrace tarpaulin (used in CI) counts more lines as coverable than macOS tarpaulin (used locally). Two patterns that inflate the Linux denominator:

1. **`fn main()` body lines** — the thin stdio-wrapper `fn main()` is never exercised by unit tests. Add `#[cfg(not(tarpaulin_include))]` immediately before `fn main()` to exclude it. Tarpaulin sets `--cfg tarpaulin_include` when instrumenting, so the function compiles normally in regular builds but is invisible to tarpaulin's line counter.

2. **Multi-line `write!/writeln!` argument lines** — when arguments are on separate lines, Linux ptrace counts the first argument (`out,` / `err,`) and the last positional argument as separate coverable probes, but neither probe fires during test execution. The result is uncovered lines that cannot be fixed by adding tests.

   To keep `write!/writeln!` macros single-line (so those probe points don't exist), two measures are needed together:
   - Add a `rustfmt.toml` with `use_small_heuristics = "Max"` to raise rustfmt's `fn_call_width` threshold from 60% to 100% of `max_width`. Without this, cargo fmt expands any macro whose arguments exceed ~60 chars back to multi-line regardless of total line length.
   - Use Rust's captured-variable format syntax (`{c}`, `{m}`, `{exponent}`) to reduce multi-argument macros to two-argument form (`dest, "format {c} {n}"`). This keeps the argument string short enough to stay single-line under the new threshold.

   Note: format strings that are inherently long (e.g., the "Warning: X={} means…" writeln! in fib-rs, whose arguments total 131 chars) cannot be made single-line even with these settings. Accept 1–2 uncoverable lines per crate from unavoidably long macros.

3. **Uncoverable `break;` statements** — Linux ptrace may count a `break;` inside a `while let Some(...)` loop as a coverable probe that never fires (even when the break IS executed). Eliminate the explicit break by folding the exit condition into the loop with `Option::filter`:

   ```rust
   // Before (break; uncoverable):
   while let Some(sq) = k.checked_mul(k) {
       if sq >= limit { break; }
       ...
   }

   // After (no break):
   while let Some(sq) = k.checked_mul(k).filter(|&sq| sq < limit) {
       ...
   }
   ```

Both patterns 1 and 2 require a companion `[lints.rust]` entry in `Cargo.toml` so clippy does not reject `tarpaulin_include` as an unknown cfg:

```toml
[lints.rust]
unexpected_cfgs = { level = "warn", check-cfg = ['cfg(tarpaulin_include)'] }
```

Apply fix 1 (`#[cfg(not(tarpaulin_include))]` on `fn main()`) to every new Rust crate. Apply fixes 2 and 3 only when fix 1 alone leaves coverage below 90% on Linux.

## CI

Twenty-eight workflow files. Project workflows run on PRs to `master` only — the pre-push hook gates branch pushes locally. Build jobs depend on their test job — a build will not run if tests fail.

| Workflow               | File                                           | Jobs                                                                                            |
| ---------------------- | ---------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| pi.py                  | `.github/workflows/pi-py.yml`                  | test                                                                                            |
| pi-rs                  | `.github/workflows/pi-rs.yml`                  | test → build + artifact                                                                         |
| prime-rs               | `.github/workflows/prime-rs.yml`               | test → build + artifact                                                                         |
| fib.py                 | `.github/workflows/fib-py.yml`                 | test                                                                                            |
| fib-rs                 | `.github/workflows/fib-rs.yml`                 | test → build + artifact                                                                         |
| sq.py                  | `.github/workflows/sq-py.yml`                  | test                                                                                            |
| sq-rs                  | `.github/workflows/sq-rs.yml`                  | test → build + artifact                                                                         |
| twin-primes-rs         | `.github/workflows/twin-primes-rs.yml`         | test → build + artifact                                                                         |
| release-pi-rs          | `.github/workflows/release-pi-rs.yml`          | release (manual dispatch)                                                                       |
| release-prime-rs       | `.github/workflows/release-prime-rs.yml`       | release (manual dispatch)                                                                       |
| release-fib-rs         | `.github/workflows/release-fib-rs.yml`         | release (manual dispatch)                                                                       |
| release-sq-rs          | `.github/workflows/release-sq-rs.yml`          | release (manual dispatch)                                                                       |
| release-twin-primes-rs | `.github/workflows/release-twin-primes-rs.yml` | release (manual dispatch)                                                                       |
| e.py                   | `.github/workflows/e-py.yml`                   | test                                                                                            |
| e-rs                   | `.github/workflows/e-rs.yml`                   | test → build + artifact                                                                         |
| release-e-rs           | `.github/workflows/release-e-rs.yml`           | release (manual dispatch)                                                                       |
| factorial.py           | `.github/workflows/factorial-py.yml`           | test                                                                                            |
| factorial-rs           | `.github/workflows/factorial-rs.yml`           | test → build + artifact                                                                         |
| release-factorial-rs   | `.github/workflows/release-factorial-rs.yml`   | release (manual dispatch)                                                                       |
| collatz.py             | `.github/workflows/collatz-py.yml`             | test                                                                                            |
| collatz-rs             | `.github/workflows/collatz-rs.yml`             | test → build + artifact                                                                         |
| goldbach-rs            | `.github/workflows/goldbach-rs.yml`            | test → build + artifact                                                                         |
| amicable.py            | `.github/workflows/amicable-py.yml`            | test                                                                                            |
| amicable-rs            | `.github/workflows/amicable-rs.yml`            | test → build + artifact                                                                         |
| auto-merge             | `.github/workflows/auto-merge.yml`             | secret-scan → ci-gate (polls required checks, merges on pass) → snyk-scan (advisory, not gated) |
| scripts                | `.github/workflows/scripts.yml`                | test (bats --recursive tests/)                                                                  |

**Pre-commit hook** — `scripts/pre-commit` is committed to the repo and installed as a symlink via `make install-hooks`. It runs `make lint` on staged sub-projects and `ggshield secret scan pre-commit` (skipped if not installed). CI gitleaks is a backstop — install and activate ggshield locally so secrets are caught before they leave the machine.

**Pre-push hook** — `scripts/pre-push` is committed to the repo and installed as a symlink via `make install-hooks`. It detects which sub-projects have commits in the push range and runs `make test` for each. Skips branch deletions. Permanent — conserves GitHub Actions minutes by catching failures locally before the push reaches GitHub.

**Worktree compatibility requirement:** `scripts/pre-push` must resolve the repository root with `git rev-parse --show-toplevel` first, with `git rev-parse --git-common-dir` parent only as a fallback. Using `git-common-dir` directly in worktrees can run tests against the shared checkout (`master`) instead of the active feature worktree.

**Shell script testing** — BATS (`bats --recursive tests/`) is the standard for all shell script tests in this repo. Run with `make test-hooks`. Requires system-installed bats-core: `brew install bats-core` (macOS) or `sudo apt-get install -y bats` (Linux).

- `tests/helpers/common.bash` — shared REPO_ROOT export and `load_mocks()` (prepends `tests/mocks/` to PATH)
- `tests/mocks/` — PATH-injected mock executables: `make` (logs calls, exits `$MOCK_MAKE_EXIT`), `git` (dispatches by subcommand, outputs from per-subcommand env vars), `ggshield` (logs calls, exits `$MOCK_GGSHIELD_EXIT`), `gh` (sequential JSON responses via `MOCK_GH_PR_CHECKS_N`, exits `$MOCK_GH_EXIT`)
- `tests/scripts/` — BATS test files; one per script tested (`rust_check.bats`, `pre_commit.bats`, `pre_push.bats`, `ci_gate.bats`, `makefile.bats`)

**Auto-merge gate:** `scripts/ci-gate.sh <PR>` is called by the `auto-merge` job before merging. It polls `gh pr checks` until all checks are terminal, then verifies no check outside the advisory list (`snyk-scan`) and self-checks (`secret-scan`, `auto-merge`) has failed. Docs-only PRs trigger no project workflows and merge immediately. The gate is tested via `tests/scripts/ci_gate.bats` using the `tests/mocks/gh` mock (runs fully offline).

**Paths-filtered workflows** — each project workflow fires only when files in its directory change. The root `Makefile` is covered by `scripts.yml`. Release workflows and `auto-merge.yml` trigger unconditionally. When a new project is added, create its workflow with a `paths:` block — the gate automatically requires it for relevant PRs.

**snyk-scan** runs `snyk code test` (SAST) against the Python and Rust source. It is advisory — not in `needs` for `auto-merge`. Requires `SNYK_TOKEN` in repository secrets.

**When adding a new project**, create a dedicated workflow file `.github/workflows/<project>.yml` following the same pattern:

- Trigger: `pull_request: branches: [master]` only — no `push:` trigger (pre-push hook handles branch pushes locally)
- One `test` job running the project's test suite
- One `build` job with `needs: [test]` that builds the release binary and uploads it as an artifact
- A badge for the new workflow added to the top of `README.md` and to the CI column of the project table — use `badge.svg?event=pull_request` so the badge reflects the last PR run (workflows trigger on `pull_request` only so master-based filters always show no status)

This gives a per-project badge in the README and keeps each project's CI self-contained.

**All jobs must run on Node.js 24.** Use action versions that natively support Node.js 24:

- `actions/checkout@v5` — natively runs on Node.js 24 (v4 used Node.js 20 and is deprecated)

The workflow also sets `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` as a belt-and-suspenders fallback for any third-party actions (e.g. `dtolnay/rust-toolchain`, `Swatinem/rust-cache`) that have not yet released a Node.js 24 native version.

Do **not** add `actions/setup-node` to jobs — these are Rust/Python projects that don't need Node.js at the user-code level, and older versions of `setup-node` are themselves Node.js 20 actions.

**Every Rust build job must upload its release binary as an artifact** using `actions/upload-artifact@v5` with 7-day retention:

```yaml
- name: Upload artifact
  uses: actions/upload-artifact@v5
  with:
    name: <binary-name>
    path: <project>/target/release/<binary-name>
    retention-days: 7
```

Artifacts are downloadable from the Actions run summary page on GitHub.

**GitHub Actions security and output patterns** — required in all workflows:

1. **Env vars for user inputs in `run:` blocks** — never interpolate `${{ inputs.* }}` directly into shell; pass through `env:` instead to prevent expression injection:

   ```yaml
   - name: Create and push tag
     env:
       VERSION: ${{ inputs.version }}
     run: git tag "pi-v${VERSION}"
   ```

2. **Randomized `GITHUB_OUTPUT` delimiter** — never use a fixed `EOF`; a commit message containing `EOF` on its own line truncates the output silently:

   ```bash
   DELIMITER="EOF_$(openssl rand -hex 8)"
   {
     printf 'notes<<%s\n' "${DELIMITER}"
     printf '%s\n' "${NOTES}"
     printf '%s\n' "${DELIMITER}"
   } >> "$GITHUB_OUTPUT"
   ```

3. **Quote `body:` in `softprops/action-gh-release`** — release notes may contain YAML special characters; the value must be quoted:

   ```yaml
   body: "${{ steps.notes.outputs.notes }}"
   ```

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

### Multiprocessing fallback behavior

For Python high-precision calculators (`pi`, `e`, `factorial`), `ProcessPoolExecutor` can fail in restricted environments (for example semaphore sysconf permission errors). Runtime behavior must be:

1. Fall back to serial execution/conversion instead of hard-failing.
2. Print an explicit user-facing message that serial mode is active.
3. Tell the user to install/fix required runtime support (including multiprocessing semaphore support) to restore parallel mode.

### PR Review Gate

Before pushing any feature branch, run the `pr-review` skill. Only push when verdict is **PASS**. If **HOLD**:

1. Fix all CRITICAL findings
2. Run `make test` — confirm no regressions
3. Commit the fixes
4. Re-run `pr-review`
5. Repeat until PASS, or escalate to user after two failed fix attempts

WARNING and INFO findings are advisory — surface them but do not block the push.

## Committing Work

**Create a git commit at the end of each logical unit of work.** A unit of work is a self-contained change: a new feature, a bug fix, a docs update, a refactor, or any combination that belongs together. Do not batch unrelated changes into one commit and do not leave work uncommitted.

Commit message format:

```
<type>: <short summary>

<optional body explaining why, not what>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Common types: `feat`, `fix`, `docs`, `ci`, `refactor`, `test`, `chore`.

## Keeping CLAUDE.md Up To Date

**When making any change to this repository, update the relevant CLAUDE.md file(s) before finishing.** These files are the primary reference for future sessions — stale documentation is worse than none.

What to update and when:

| Change                                 | Files to update                                                                                                                                                                                                                   |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| New or renamed function / constant     | Project `CLAUDE.md` → Code Layout section                                                                                                                                                                                         |
| New or removed Makefile target         | Project `CLAUDE.md` + `README.md` → Makefile targets table; root `Makefile` targets → top-level `CLAUDE.md` Quick Reference + `README.md`                                                                                         |
| New dependency or install step         | `pi/install_deps.sh` + project `CLAUDE.md` + `README.md`                                                                                                                                                                          |
| New test class or change in coverage % | Project `CLAUDE.md` + `README.md` → Testing section                                                                                                                                                                               |
| New project added to the repo          | Top-level `CLAUDE.md` → Repository Overview table                                                                                                                                                                                 |
| Behaviour or algorithm change          | Project `CLAUDE.md` → Important Behavior / Implementation Details                                                                                                                                                                 |
| New project added                      | Create `.github/workflows/<project>.yml` (test → build + artifact); add badge to `README.md` top and CI column; update `CLAUDE.md` CI table; add new sub-project dirs to the loops in `scripts/pre-commit` and `scripts/pre-push` |
| Editing rule or policy change          | All affected `CLAUDE.md` → Editing Guidance section                                                                                                                                                                               |

The sub-project files (`pi/CLAUDE.md`, `prime/CLAUDE.md`, `fib/CLAUDE.md`, `sq/CLAUDE.md`, `e/CLAUDE.md`, `factorial/CLAUDE.md`, and each Rust subtree's `CLAUDE.md` under `pi/pi-rs/`, `prime/prime-rs/`, `fib/fib-rs/`, `sq/sq-rs/`, `e/e-rs/`, `factorial/factorial-rs/`) are the source of truth for implementation detail. This top-level file is the entry point and quick reference — keep them in sync.

## Notes

- **PR learnings (2026-04-29, rust-offline-wrapper):**
  - For Rust crates, route `make lint`/`make test` through `scripts/rust-check.sh` to keep cargo behavior deterministic across root checkouts and worktrees.
  - Verify wrapper behavior at two levels: unit tests (`python3 scripts/test_rust_check.py`) plus a full online+offline crate matrix before merge.
  - The wrapper creates a repo-local `.cache/cargo-home` when `CARGO_HOME` is unset. Treat `.cache/` as transient local state and remove it (`rm -rf .cache`) before final status checks and commits.

- Generated output files (`pi_*_digits.txt`, `primes_1e*.txt`, `twin-primes_1e*.txt`, `e_*_digits.txt`, `factorial_*.txt`) are large artifacts — do not commit them.
- See each project's `CLAUDE.md` for detailed implementation guidance, code layout, and editing rules.
