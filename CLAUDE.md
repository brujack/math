# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

High-performance mathematical computation tools.

| Project                                | Language      | Description                                                            | CLAUDE.md                                                                      |
| -------------------------------------- | ------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| [`pi/`](pi/)                           | Python + Rust | Calculate π to N decimal places (Chudnovsky algorithm)                 | [`pi/CLAUDE.md`](pi/CLAUDE.md)                                                 |
| [`prime/`](prime/)                     | Rust          | Find all primes up to 10^N (segmented sieve)                           | [`prime/CLAUDE.md`](prime/CLAUDE.md)                                           |
| [`fib/`](fib/)                         | Python + Rust | Generate all Fibonacci numbers with up to 10^X digits                  | [`fib/CLAUDE.md`](fib/CLAUDE.md)                                               |
| [`sq/`](sq/)                           | Python + Rust | Find all perfect squares with up to 10^N digits (N=1 max)              | [`sq/CLAUDE.md`](sq/CLAUDE.md)                                                 |
| [`twin-primes/`](twin-primes/)         | Rust          | Find all twin prime pairs up to 10^N                                   | [`twin-primes/twin-primes-rs/CLAUDE.md`](twin-primes/twin-primes-rs/CLAUDE.md) |
| [`e/`](e/)                             | Python + Rust | Calculate e to N decimal places (Taylor series)                        | [`e/CLAUDE.md`](e/CLAUDE.md)                                                   |
| [`factorial/`](factorial/)             | Python + Rust | Compute N! to arbitrary precision (prime swing)                        | [`factorial/CLAUDE.md`](factorial/CLAUDE.md)                                   |
| [`perfect-numbers/`](perfect-numbers/) | Python + Rust | Find all perfect numbers up to 10^N (Lucas-Lehmer + sigma)             | [`perfect-numbers/CLAUDE.md`](perfect-numbers/CLAUDE.md)                       |
| [`collatz/`](collatz/)                 | Python + Rust | Find Collatz chain record-setters up to 10^N (vector memoization)      | [`collatz/CLAUDE.md`](collatz/CLAUDE.md)                                       |
| [`goldbach/`](goldbach/)               | Rust          | Find all Goldbach pairs for even n up to 10^N (bitset sieve)           | [`goldbach/CLAUDE.md`](goldbach/CLAUDE.md)                                     |
| [`amicable/`](amicable/)               | Python + Rust | Find all amicable pairs (a,b) with b ≤ 10^N (proper-divisor sum sieve) | [`amicable/CLAUDE.md`](amicable/CLAUDE.md)                                     |

## Architectural Decision Records

Significant architectural decisions are recorded in [`docs/adr/`](docs/adr/README.md). When making a significant choice (algorithm, library, CI structure), write an ADR before or alongside the implementation.

## 10-80-10 Execution Cycle

Sessions in this repo follow the 10-80-10 execution cycle defined in `ai-config` ADR-0009 (and the ADR-0010 wave-dispatch extension):

- **Phase 1 (10%) — Architect.** `brainstorming` → `writing-plans` (emit per-task YAML `yaml-task` blocks with `role`/`model`/`tdd`/`acceptance`/`max_retries`/`files_touched`/`depends_on`/`parallel_group`). Opus role.
- **Phase 2 (80%) — Execute.** `subagent-driven-development` runs iterate-until-green per task; FORBIDDEN list prevents gate cheating; wave-dispatch when `parallel_group` is declared. Sonnet/Haiku per task as declared in the plan.
- **Phase 3 (10%) — Review.** `finishing-a-development-branch` chains `pr-review` → `security-review` → `bug-scan` → `docs` → `learnings` → finish. Opus role.

Validate a plan before dispatch:

```bash
make validate-plan PLAN=docs/superpowers/plans/<file>.md
```

The validator (`~/.claude/scripts/validate-plan.py`, shared from ai-config) enforces required fields, valid role/model/tdd values, haiku scope guard, and disjoint `files_touched` within each `parallel_group`.

## Knowledge Directory

Reference material lives in `docs/knowledge/`. These documents capture algorithm reference sheets, numerical library notes, and curated research findings — things too detailed for CLAUDE.md but useful to look up. See `docs/knowledge/README.md` for what belongs there and what doesn't.

When web research (web-research skill) or context-mode fetches produce findings worth preserving, save them to `docs/knowledge/<topic>.md`.

## Dependency Installation

Each project has its own installer:

| Script                                               | Installs                                                                  |
| ---------------------------------------------------- | ------------------------------------------------------------------------- |
| `pi/install_deps.sh`                                 | GMP + MPFR, `mpmath`, `gmpy2`, `ruff`, `coverage`, `pytest`, `pytest-cov` |
| `pi/pi-rs/install_deps.sh`                           | GMP + MPFR, Rust toolchain, `cargo-tarpaulin`                             |
| `prime/prime-rs/install_deps.sh`                     | Rust toolchain, `cargo-tarpaulin`                                         |
| `fib/install_deps.sh`                                | `ruff`, `coverage`, `pytest`, `pytest-cov`                                |
| `fib/fib-rs/install_deps.sh`                         | GMP, Rust toolchain, `cargo-tarpaulin`                                    |
| `sq/install_deps.sh`                                 | `ruff`, `coverage`, `pytest`, `pytest-cov`                                |
| `sq/sq-rs/install_deps.sh`                           | Rust toolchain                                                            |
| `twin-primes/twin-primes-rs/install_deps.sh`         | Rust toolchain, `cargo-tarpaulin`                                         |
| `e/install_deps.sh`                                  | GMP + MPFR, `mpmath`, `gmpy2`, `ruff`, `coverage`, `pytest`, `pytest-cov` |
| `e/e-rs/install_deps.sh`                             | GMP + MPFR, Rust toolchain, `cargo-tarpaulin`                             |
| `factorial/install_deps.sh`                          | GMP + MPFR, `gmpy2`, `mpmath`, `ruff`, `coverage`, `pytest`, `pytest-cov` |
| `factorial/factorial-rs/install_deps.sh`             | GMP + MPFR, Rust toolchain, `cargo-tarpaulin`                             |
| `perfect-numbers/install_deps.sh`                    | `ruff`, `coverage`, `pytest`, `pytest-cov`                                |
| `perfect-numbers/perfect-numbers-rs/install_deps.sh` | GMP, Rust toolchain, `cargo-tarpaulin`                                    |
| `collatz/install_deps.sh`                            | `ruff`, `coverage`, `pytest`, `pytest-cov`                                |
| `collatz/collatz-rs/install_deps.sh`                 | Rust toolchain, `cargo-tarpaulin`                                         |
| `goldbach/goldbach-rs/install_deps.sh`               | Rust toolchain, `cargo-tarpaulin`                                         |
| `amicable/install_deps.sh`                           | `ruff`, `coverage`, `pytest`, `pytest-cov`                                |
| `amicable/amicable-rs/install_deps.sh`               | Rust toolchain, `cargo-tarpaulin`                                         |

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
make test      # lint, then pytest test_pi.py -v
make coverage  # pytest --cov, fails under 90%
```

**Ruff config.** A single `ruff.toml` at the repo root reaches all 8 Python subprojects
via ancestor discovery — do not create per-subproject configs. It is the fleet-wide shared
`select` list (ai-config ADR-0058) plus one math-local addition, `C901`, retained because
this repo already enforced complexity. `ruff==0.16.4` is pinned at all 17 install sites
(8 `*-py.yml` workflows + `scripts.yml` + 8 `install_deps.sh`).

The 0.16.1 -> 0.16.4 bump was measured, not assumed. Two pinned venvs run over this
repo's exact gated scope -- `ruff check .` and `ruff format --check .` in each of the 8
sub-projects, plus the root `ruff check .` and the `git ls-files`-derived format check --
produced **byte-identical** output. With a positive control, since two agreeing clean runs
could equally mean neither executed: removing each `# noqa: C901` makes both versions
report `too complex (21 > 10)` at `e/e.py:332` and `pi/pi.py:444`. Identical *score*, not
just identical verdict -- a changed complexity analysis would have moved the number, and
that is the one thing those two suppressions depend on.

`make lint` at the repo root now runs `ruff check .` plus a `ruff format --check` scoped to
the tracked `.py` set, alongside `lint-hooks`. That closed the gap this paragraph used to
record: `scripts/` and `tests/` sat outside every gated scope, and a bare `ruff check .`
from the root was red at 7 findings nothing would ever have caught.

Two details are load-bearing. **`check` takes `.` and `format` does not** — ruff's formatter
rewrites Python code blocks inside markdown, so `ruff format --check .` reports 18 `docs/`
files whose ADR and plan snippets are deliberately as-written; the format scope is derived
from `git ls-files '*.py'` instead, which covers the tracked set with nothing to maintain.
And **`lint-python` guards a missing ruff and exits 0**, which is correct locally (`test`
depends on it and the pre-push hook runs `test`, so a hard failure would lock a machine out
of committing the change that installs ruff) but makes the gate decorative in CI — hence
`scripts.yml` installs `ruff==0.16.4` and `tests/scripts/makefile.bats` asserts that it
does. The companion gap — `pi/install_deps.sh` installing no ruff while
`pi/Makefile` runs it — was closed in #110, along with all 8 installers omitting the
`pytest`/`pytest-cov` their Makefiles invoke. `tests/scripts/install_deps.bats` now derives
the installer/Makefile comparison from `git ls-files`, so a sub-project added later is
covered without anyone remembering to extend a list.

The two `# noqa: C901` directives in `e/e.py` and `pi/pi.py` are load-bearing: both
functions measure complexity 21 against a ceiling of 10, and `maintainability-review`
invokes `ruff check --select C901` on the CLI — which overrides any config — so removing
a suppression without changing the code reads to its ratchet as a 0 → 21 regression.

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
make test      # lint, then pytest test_fib.py -v
make coverage  # pytest --cov, fails under 90%
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
make test      # lint, then pytest test_sq.py -v
make coverage  # pytest --cov, fails under 90%
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
make test      # lint, then pytest test_e.py -v
make coverage  # pytest --cov, fails under 90%
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
make test      # lint, then pytest test_factorial.py -v
make coverage  # pytest --cov, fails under 90%
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
make test      # lint, then pytest test_perfect_numbers.py -v
make coverage  # pytest --cov, fails under 90%
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
make test      # lint, then pytest test_collatz.py -v
make coverage  # pytest --cov, fails under 90%
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
make test      # lint, then pytest test_amicable.py -v
make coverage  # pytest --cov, fails under 90%
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

## Language Standards

Language-specific standards for this repo. These supplement the universal standards loaded
from `~/.claude/CLAUDE.md` (tdd, behavior, git-workflow, ci, code-standards, logic-review,
repo-structure, shell).

@~~/.claude/standards/python.md
@~~/.claude/standards/rust.md

### API-quality lints (all 11 Rust crates)

Every `*-rs/Cargo.toml` enables two Rust API Guidelines items a compiler can check:

```toml
[lints.rust]
missing_debug_implementations = "warn"   # C-DEBUG

[lints.clippy]
wrong_self_convention = "warn"           # C-CONV
```

`scripts/rust-check.sh` runs clippy with `-D warnings`, so both are blocking, not
advisory — a new `pub struct` without `#[derive(Debug)]` fails `make lint`.

`missing_docs` (`C-DOCS`) is deliberately **not** enabled here. It is a guideline about
API consumed across a crate boundary, and these crates have none: all 11 `lib.rs` files
were created in one commit so Criterion benches could call the logic, 3 of 344 commits
have ever touched one, and none is published. It ships in `etch-cli` instead, where a
real cross-crate consumer exists.

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

### Type checking (Python — pyright)

Every Python sub-project has a `pyrightconfig.json` and a `Run pyright` step in its CI workflow.

| Mode       | Sub-projects                                                                                              |
| ---------- | --------------------------------------------------------------------------------------------------------- |
| `standard` | amicable, collatz, fib, sq, factorial, perfect-numbers, scripts                                           |
| `basic`    | pi, e (gmpy2 has no type stubs; `reportAttributeAccessIssue` and `reportOptionalMemberAccess` suppressed) |

Pyright runs in CI only — not in `make lint` (spawn overhead on macOS makes it slow locally). To run manually: `cd <sub-project> && pyright`.

When adding a new Python sub-project, add `pyrightconfig.json` (copy from any `standard`-mode sub-project) and a `Run pyright` step to the CI workflow. Start with `standard` mode; fall back to `basic` only if the dependency has no stubs.

### Mutation testing (Rust)

For a mathematical library, **correctness is the primary quality metric** — coverage % is necessary but not sufficient. Mutation testing measures whether tests actually catch behavior changes by making small code mutations (flipping operators, changing constants) and verifying the test suite catches them.

- **Tool:** `cargo-mutants` (install: `cargo install cargo-mutants --locked`)
- **Per-crate:** `make mutants` in any Rust crate directory
- **CI:** `.github/workflows/mutation-testing.yml` runs monthly (`cron: "0 4 1 * *"`) and on-demand via `workflow_dispatch`
- **Interpretation:** A "surviving mutant" means a code change went undetected by tests — strengthen the test to kill it. 100% kill rate is the goal but rarely achievable; >80% is good for math code.
- **Per-mutant timeout:** `--timeout 30`, set in each crate's `Makefile` `mutants` target — NOT in the workflow, which calls `make -C <crate> mutants` so local and CI share one definition. They previously disagreed (Makefiles 120, workflow 30) with nothing reconciling them.
- **Memory cap:** `ulimit -v 8388608` (8 GiB) in the same recipe. `cargo mutants --timeout` is wall-clock only with no memory bound, so an allocation-unbounded mutant exhausts the 16 GB runner well inside the 30s budget and kills the runner agent along with the job. This is why all six `mutation-testing.yml` runs between 2026-06-01 and 2026-08-01 failed with exit 143 (SIGTERM). An earlier note here blamed the 360-minute job timeout combined with infinite-loop mutations and reduced `--timeout` from 120 to 30 in response; **that diagnosis was wrong** — the 2026-08-01 run died 119 seconds in, and the change did not help. See ADR-0024.
- **`MUTANTS_UNCAPPED=1`** runs without the cap. Required on macOS, which cannot enforce `ulimit -v` at all (`cannot modify limit: Invalid argument`) — a local `make mutants` fails closed with an explicit message rather than silently running uncapped and eating system memory. Also the way to reproduce the pre-fix OOM deliberately.
- **Green/red:** a leg is red only when it evaluated nothing (`caught + missed == 0`, which covers all-unviable, all-timeout, and zero-mutant), when the baseline tests fail, or when the runner dies. Survivors (exit 2) and timeouts (exit 3) are green and reported to the job summary — both are the expected steady state, and gating on them guarantees a red run every month. `scripts/mutation-classify.sh` implements this; `tests/scripts/mutation_classify.bats` covers every rule.
- **Notification:** a red run files or updates a labelled `mutation-failure` issue; a green run closes it. The notify job is separate from the mutants job with `needs: [mutants], if: always()`, because SIGTERM skips `if: always()` _steps_ inside the job it kills — which is why six months of runs uploaded zero artifacts.

When adding a new Rust crate, include `mutants` in its `Makefile` `.PHONY` list and target. Periodically run mutation testing per crate; investigate any surviving mutants in `lib/`-style code (logic, not main glue).

**Equivalent mutations** — mathematical algorithms frequently produce mutations that are semantically equivalent: the code changes but all valid inputs produce the same output. No test can kill an equivalent mutant because there is no observable difference to detect. Exclude them via `.cargo/mutants.toml` in the crate directory:

```toml
# .cargo/mutants.toml
# Format: regex matched against "src/lib.rs:<line>:<col>: <description>"
exclude_re = [
    # while p*p <= n: p*p→p+p loops to n/2 vs √n, but sieve output is identical
    "src/lib\\.rs:13:13: replace \\* with \\+",
]
```

**Important:** `// mutants::skip` inline comments are **not** recognized by cargo-mutants ≥27.x — only `#[mutants::skip]` attributes on items are supported. Use `.cargo/mutants.toml` `exclude_re` patterns instead.

**Caveat:** `exclude_re` patterns include line numbers. If surrounding code shifts the line, the pattern stops matching and the equivalent mutant reappears as "surviving." Update the file and its comments when nearby code changes. See `factorial/factorial-rs/.cargo/mutants.toml` for a worked example with three excluded equivalences (two sieve `p*p→p+p` variants and one `exp>0→exp>=0` in `compute_swing_chunk`).

**Algebraic-identity dead-code equivalents** — when a function body contains a comparison that is always true for all valid inputs due to mathematical identity, any mutation to that comparison is an equivalent dead-code mutation. Example: `verify_perfect(p)` checks `sigma_result == 2*n`; Euler's theorem proves this is always true for any p yielding a Mersenne prime, so `==` → `!=` or intermediate arithmetic mutations are unreachable. Exclude them in `.cargo/mutants.toml`. Diagnosis: write a test that exercises the function with several known-good inputs — if the mutant still passes, it's equivalent, not a gap.

**Prompt-guard output-filename assertion kills match-guard mutations** — in interactive-prompt tests that supply N via `io::Cursor::new("2\n")`, a `→ true` mutation on the prompt validation loop (e.g., converting `n >= 1 && n <= 8` to `true`) makes all N values valid and `run()` returns `Ok` regardless of input. The test still passes. Kill this mutation by asserting on the concrete output artifact after `run()`:

```rust
assert!(dir.path().join("goldbach_1e2.txt").exists());
```

With this assertion, the filename encodes the actual N value — a mutant that accepts any N would write the correct file for the supplied N=2 anyway, so the precise guard needed is on the output file. Add this assertion to every prompt test that could be affected by a guard `→ true` mutation.

## CI

Forty-one workflow files (`git ls-files .github/workflows/ | wc -l`). Project workflows run on PRs to `master` only — the pre-push hook gates branch pushes locally. Build jobs depend on their test job — a build will not run if tests fail. `bash-coverage` is a new job (auto-merge.yml) — see Bash Coverage below.

| Workflow                | File                                            | Jobs                                                                                                                    |
| ----------------------- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| pi.py                   | `.github/workflows/pi-py.yml`                   | test                                                                                                                    |
| pi-rs                   | `.github/workflows/pi-rs.yml`                   | test → build + artifact                                                                                                 |
| prime-rs                | `.github/workflows/prime-rs.yml`                | test → build + artifact                                                                                                 |
| fib.py                  | `.github/workflows/fib-py.yml`                  | test                                                                                                                    |
| fib-rs                  | `.github/workflows/fib-rs.yml`                  | test → build + artifact                                                                                                 |
| sq.py                   | `.github/workflows/sq-py.yml`                   | test                                                                                                                    |
| sq-rs                   | `.github/workflows/sq-rs.yml`                   | test → build + artifact                                                                                                 |
| twin-primes-rs          | `.github/workflows/twin-primes-rs.yml`          | test → build + artifact                                                                                                 |
| release-pi-rs           | `.github/workflows/release-pi-rs.yml`           | release (manual dispatch)                                                                                               |
| release-prime-rs        | `.github/workflows/release-prime-rs.yml`        | release (manual dispatch)                                                                                               |
| release-fib-rs          | `.github/workflows/release-fib-rs.yml`          | release (manual dispatch)                                                                                               |
| release-sq-rs           | `.github/workflows/release-sq-rs.yml`           | release (manual dispatch)                                                                                               |
| release-twin-primes-rs  | `.github/workflows/release-twin-primes-rs.yml`  | release (manual dispatch)                                                                                               |
| e.py                    | `.github/workflows/e-py.yml`                    | test                                                                                                                    |
| e-rs                    | `.github/workflows/e-rs.yml`                    | test → build + artifact                                                                                                 |
| release-e-rs            | `.github/workflows/release-e-rs.yml`            | release (manual dispatch)                                                                                               |
| factorial.py            | `.github/workflows/factorial-py.yml`            | test                                                                                                                    |
| factorial-rs            | `.github/workflows/factorial-rs.yml`            | test → build + artifact                                                                                                 |
| release-factorial-rs    | `.github/workflows/release-factorial-rs.yml`    | release (manual dispatch)                                                                                               |
| collatz.py              | `.github/workflows/collatz-py.yml`              | test                                                                                                                    |
| collatz-rs              | `.github/workflows/collatz-rs.yml`              | test → build + artifact                                                                                                 |
| goldbach-rs             | `.github/workflows/goldbach-rs.yml`             | test → build + artifact                                                                                                 |
| amicable.py             | `.github/workflows/amicable-py.yml`             | test                                                                                                                    |
| amicable-rs             | `.github/workflows/amicable-rs.yml`             | test → build + artifact                                                                                                 |
| auto-merge              | `.github/workflows/auto-merge.yml`              | secret-scan + bash-coverage (gated) → ci-gate (polls required checks, merges on pass) → snyk-scan (advisory, not gated) |
| mutation-pr             | `.github/workflows/mutation-pr.yml`             | cosmic-ray on changed Python sub-projects (advisory; survivors warn, not block)                                         |
| mutation-testing        | `.github/workflows/mutation-testing.yml`        | cargo mutants on all Rust crates (monthly + workflow_dispatch)                                                          |
| mutation-testing-python | `.github/workflows/mutation-testing-python.yml` | cosmic-ray on all Python sub-projects (monthly + workflow_dispatch)                                                     |
| scripts                 | `.github/workflows/scripts.yml`                 | test (bats --recursive tests/)                                                                                          |

**Pre-commit hook** — `scripts/pre-commit` is committed to the repo and installed as a symlink via `make install-hooks`. It runs `make lint` on staged sub-projects and `ggshield secret scan pre-commit` (skipped if not installed). CI gitleaks is a backstop — install and activate ggshield locally so secrets are caught before they leave the machine.

**Pre-push hook** — `scripts/pre-push` is committed to the repo and installed as a symlink via `make install-hooks`. It detects which sub-projects have **source file** (`.py`, `.rs`) changes in the push range and runs `make test` for each. It separately runs the **root** `make test` target — `lint test-hooks test-python`, where `lint` is `lint-hooks` (shellcheck) plus `lint-python` (ruff check + format) — whenever the push touches `scripts/`, `tests/`, or the root `Makefile`. Skips branch deletions. Permanent — conserves GitHub Actions minutes by catching failures locally.

**ProcessPoolExecutor resource_tracker gotcha (macOS):** Python's `spawn` multiprocessing context starts a `resource_tracker` daemon that can deadlock with git's push pipe. `< /dev/null` on `make test` prevents the stdin deadlock for a single test run. However, running many sequential test suites (e.g. a cross-cutting Makefile change touching all 7 Python CLIs at once) causes resource_tracker daemons to accumulate — later suites fail to acquire semaphores and hang indefinitely. Fix: scope the test trigger to `.py`/`.rs` source changes only. Makefile, workflow, and doc changes never affect test outcomes and must not trigger the pre-push test suite.

**Worktree compatibility requirement:** `scripts/pre-push` must resolve the repository root with `git rev-parse --show-toplevel` first, with `git rev-parse --git-common-dir` parent only as a fallback. Using `git-common-dir` directly in worktrees can run tests against the shared checkout (`master`) instead of the active feature worktree.

**Shell script testing** — BATS (`bats --recursive tests/`) is the standard for all shell script tests in this repo. Run with `make test-hooks`. Requires system-installed bats-core: `brew install bats-core` (macOS) or `sudo apt-get install -y bats` (Linux).

**Repo-level Python tests** — `make test-python` runs `python3 -m unittest discover -s tests -p 'test_*.py'`,
and `make test` runs `test-hooks` then `test-python`. Added 2026-08-07 (#104). Before that nothing executed
`tests/*.py` at all: `scripts.yml` ran bats and pyright, so `tests/test_time_tests.py` was type-checked but
its 8 tests had never once run. `scripts.yml` now calls `make test-python` alongside the bats step. Note this
is repo-level only — each sub-project keeps its own `make test`. The suite is **53 tests** as of
2026-08-24: `test_time_tests.py`, `test_test_metrics.py`, `test_triage_log.py`, and
`test_renovate_automerge_policy.py` (added in #123 — it asserts `renovate.json`'s auto-merge policy is
exhaustive over the ten-member `updateType` enum; see the Renovate auto-merge policy section above).

**`.claude/scripts/triage_log.py`** — vendored per-repo because of its resolver, not its availability. It
does ship via the `~/.claude/scripts/` symlink like every other script there; what fails is that its output
dir is `Path(__file__).resolve().parent.parent / "triage-log"` and `.resolve()` follows the symlink, so
invoking it through the home path writes this repo's triage log into ai-config. The vendored copy exists to
put the log in the right repo. Sibling scripts need no vendoring — `cost_log.py`/`cost_summary.py` resolve
`.claude/cost-log/` relative to the cwd and `dod_log.py` is home-anchored, so both are correct to invoke as
`~/.claude/scripts/<name>`. Retiring this one means fixing the resolver (ai-config spec
`2026-07-29-telemetry-home-anchoring-design.md`, still Status: Spec)
because `bug-fix-cycle` emits its telemetry through it. Paired suite at `tests/test_triage_log.py`; the JSONL
it writes is gitignored.

- `tests/helpers/common.bash` — shared REPO_ROOT export and `load_mocks()` (prepends `tests/mocks/` to PATH)
- `tests/mocks/` — PATH-injected mock executables: `make` (logs calls, exits `$MOCK_MAKE_EXIT`), `git` (dispatches by subcommand, outputs from per-subcommand env vars), `ggshield` (logs calls, exits `$MOCK_GGSHIELD_EXIT`), `gh` (sequential JSON responses via `MOCK_GH_PR_CHECKS_N`, exits `$MOCK_GH_EXIT`)
- `tests/scripts/` — BATS test files; one per script tested (`rust_check.bats`, `pre_commit.bats`, `pre_push.bats`, `ci_gate.bats`, `makefile.bats`, `bash_coverage.bats`)

### Bash Coverage

Ported from `dotfiles/scripts/run-bash-coverage.sh` @ `67417bc` (re-synced 2026-08-10, math#108) — a PS4 xtrace tracer that runs the whole bats suite under `BASH_ENV=scripts/bash-tracer.sh` and reports per-file and overall line coverage. Per-repo copy is deliberate; there is no cross-repo sharing mechanism today, and the copy carries the six rounds of defect-correction (plus two more found porting it into ai-config) baked in — see the header comment in `scripts/run-bash-coverage.sh` for math's specific divergences from the dotfiles source.

**Re-sync from dotfiles master, and expect to do it again.** The original port landed at `c27cc4e`; three further upstream fixes (#202/#203/#204) put this copy a full PR behind within a day, and closing that took its own PR. ADR-0061 decision 5 predicted this drift and it is now measured — budget one PR per copy per upstream change. Code drift across the three copies was zero; what went stale was a header's divergence enumeration, which is prose nothing tests.

- **Run:** `make bash-coverage` (guarded on a missing `bats` binary; not wired into `make test` or `make lint` — it re-runs the whole bats suite under the tracer, which takes minutes)
- **Inspect without a full run:** `bash scripts/run-bash-coverage.sh --list-sources` (the instrumented set), `--count-coverable <file>`, `--file-coverage <file> <trace>`
- **CI:** `.github/workflows/auto-merge.yml`'s `bash-coverage` job, gated in `auto-merge`'s `needs:` — see the floor note below
- **Test:** `tests/scripts/bash_coverage.bats` — regression coverage for the `INCLUDE_FILES` predicate (every element derived independently in the test, never hardcoded against the script's own output)

**Predicate — instrumented set is 26 files, tracked shell is 28.** The instrumented set is `git ls-files 'scripts/*.sh' '*/install_deps.sh' '*/*/install_deps.sh' scripts/pre-push scripts/pre-commit scripts/commit-msg`, less `scripts/bash-tracer.sh` (structurally uncoverable — `set -x` is its own last command, so nothing before it can be traced and nothing follows it). That is 4 `scripts/*.sh` files (`ci-gate.sh`, `mutation-classify.sh`, `rust-check.sh`, `run-bash-coverage.sh`; `bash-tracer.sh` matches the glob too but is filtered after derivation) + 19 `install_deps.sh` scripts across both directory-nesting depths + 3 extensionless hooks = **26 instrumented files**. Tracked shell overall is `git ls-files '*.sh' '*.bash'` (25, after this port added `run-bash-coverage.sh` and `bash-tracer.sh`) + the 3 hooks = 28; the instrumented set excludes only `tests/helpers/common.bash` (test code) and `bash-tracer.sh` (uncoverable) from that total. `run-bash-coverage.sh` is itself instrumented — it is not self-referentially traced when it runs the suite (`BASH_ENV` is only exported around the `bats` invocation), but every direct `bash scripts/run-bash-coverage.sh ...` subprocess call inside `tests/scripts/bash_coverage.bats` inherits `BASH_ENV` from the tracer's own bats run and gets traced that way.

**The 19 `install_deps.sh` scripts are ~73% of math's instrumented set (19 of 26), and no bats suite executes any of them.** They are in the predicate anyway, and this is the load-bearing judgement of the whole port: a script no suite invokes is **untested**, not uncoverable. Excluding it would raise the reported percentage by deleting the untested majority from the denominator — precisely the flattering-denominator defect this tooling exists to eliminate (see `tdd.md`'s Coverage Denominators section). Expect a low headline percentage as a result — that is the honest number, not a bug in the port. (The count is 19, not 16 — an earlier estimate for this port undercounted the nested `<name>-rs/install_deps.sh` depth for `goldbach`, `prime`, and `twin-primes`, which have no top-level `install_deps.sh` at all, only the nested one. `git ls-files '*/install_deps.sh' '*/*/install_deps.sh' | wc -l` is the derivation; the Makefile's `SHELL_SOURCES` comment independently records the same 19.)

**Floor: 24%, set from CI's own measurement.** `auto-merge.yml`'s `bash-coverage` job gates at `FLOOR=24`, defined once in that job's step and referenced by the gate, the reminder condition and the reminder message, so raising it is a one-line change. CI measured **30% (331/1085)** on `ubuntu-latest` — identical to the local macOS run including both heuristic disagreements — and the floor sits one point below, matching dotfiles, ai-config and terraform_ansible. Publish the CI figure, not a local one: dotfiles measured an 11-covered-line platform delta between macOS (92%) and `ubuntu-latest` (91%) on the identical commit, and this repo's agreement is a property of its simple instrumented set, not something to assume elsewhere.

**Read the gate for what it is.** 19 of the 26 instrumented files are per-subproject `install_deps.sh` that no bats suite invokes, so roughly three-quarters of the denominator can never move. They are in the denominator deliberately — a script no suite runs is **untested**, not uncoverable, and excluding them would raise the figure by deleting the untested majority, which is the flattering-denominator defect this tooling exists to prevent. (`scripts/bash-tracer.sh` _is_ excluded, because no test **could** reach it: `set -x` is its own last command.) The floor is therefore a regression ratchet over the reachable quarter, not a quality bar for the repo's shell.

**Reachability: measured, not estimated.** The 25% figure is itself the direct measurement — a full local `make bash-coverage` run over the real predicate, dominated by the 19 `install_deps.sh` scripts sitting at 0%. An earlier spec-era estimate of 14% predated the predicate correction and is superseded.

**Auto-merge gate:** `scripts/ci-gate.sh <PR>` is called by the `auto-merge` job before merging. It polls `gh pr checks` until all checks are terminal, then verifies no check outside the advisory list (`snyk-scan`) and self-checks (`secret-scan`, `auto-merge`) has failed. Docs-only PRs trigger no project workflows and merge immediately. The gate is tested via `tests/scripts/ci_gate.bats` using the `tests/mocks/gh` mock (runs fully offline).

**`test_metrics.py` in Rust workflows needs explicit `pip install defusedxml`** — `factorial-rs.yml` is the only Rust workflow that calls `scripts/test_metrics.py`. Unlike Python workflows (which have a full `pip install` step), Rust workflows have no Python dependency install step. `test_metrics.py` imports `defusedxml` (added in #69 for XXE safety), which is not pre-installed on GitHub-hosted Ubuntu runners. Any Rust workflow that calls `test_metrics.py` must add this step immediately before the `Generate test metrics` step:

```yaml
- name: Install Python dependencies
  if: always()
  run: pip install defusedxml
```

Omitting this causes `ModuleNotFoundError: No module named 'defusedxml'` in CI. The symptom is subtle — the PR may touch unrelated files in `factorial/factorial-rs/` (e.g. bench deps) and unexpectedly trigger this workflow.

### Renovate auto-merge policy

`renovate.json`'s `packageRules` must **begin** with the canonical pair from ai-config's
`renovate-presets/default.json` — `renovate_preset_sync.py:87` tests prefix equality
element-by-element and reports DRIFT (exit 1) when it does not hold. Anything appended
after that prefix is a *deviation* (exit 0) and is the designed extension point. Renovate
itself is indifferent to the order, because the three rules match disjoint `updateType`s
so "later overrides earlier" never fires between them — only preset-sync cares.

Expect `renovate_preset_sync` to report DRIFT anyway, for a reason that is not this repo's:
canonical's element 0 carries no `addLabels` while all nine repos do, so the prefix compare
fails fleet-wide. Backlogged in ai-config; do not chase it here.

**Four of the schema's ten `updateType`s are held by omission** — `lockFileMaintenance`,
`rollback`, `bump`, `replacement`. That is safe but silent: `packageRules` are additive
overrides merged onto base config, and base `automerge` is `false`, so an unmatched type is
held with no `addLabels` and `auto-merge.yml`'s label guard leaves it for triage. Naming
them in `renovate.json` would buy documentation and no mechanism, so the declaration lives
in `tests/test_renovate_automerge_policy.py` instead, where `_DELIBERATELY_HELD` maps each
held type to its reason and a type that is neither auto-merged nor declared fails the suite.
`_UPDATE_TYPES` is transcribed from the schema `renovate.json`'s own `$schema` names; it is
hand-maintained and cannot catch an eleventh type added upstream.

**Paths-filtered workflows** — each project workflow fires only when files in its directory change. The root `Makefile` is covered by `scripts.yml`. Release workflows and `auto-merge.yml` trigger unconditionally. When a new project is added, create its workflow with a `paths:` block — the gate automatically requires it for relevant PRs.

**snyk-scan** runs `snyk code test` (SAST) against the Python and Rust source. It is advisory — not in `needs` for `auto-merge`. Requires `SNYK_TOKEN` in repository secrets.

**When adding a new project**, create a dedicated workflow file `.github/workflows/<project>.yml` following the same pattern:

- Trigger: `pull_request: branches: [master]` only — no `push:` trigger (pre-push hook handles branch pushes locally)
- One `test` job running the project's test suite
- One `build` job with `needs: [test]` that builds the release binary and uploads it as an artifact
- A badge for the new workflow added to the top of `README.md` and to the CI column of the project table — use `badge.svg?event=pull_request` so the badge reflects the last PR run (workflows trigger on `pull_request` only so master-based filters always show no status)

This gives a per-project badge in the README and keeps each project's CI self-contained.

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

## Definition of Done

The universal DoD in `behavior.md` applies. math adds:

- [ ] Rust coverage ≥90% on Linux CI — verify from CI output (`gh run view --repo brujack/math <id> --log | grep Coverage`)
- [ ] BATS failure-mode tests added/updated for any new or modified CLI
- [ ] Plan index updated (`docs/superpowers/README.md`) if this PR implements a tracked spec
- [ ] Root `README.md` CLI table updated if a new CLI was added
