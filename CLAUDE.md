# CLAUDE.md

This file provides guidance to Claude when working with code in this repository.

## Repository Overview

High-performance mathematical computation tools.

| Project | Language | Description | CLAUDE.md |
|---------|----------|-------------|-----------|
| [`pi/`](pi/) | Python + Rust | Calculate π to N decimal places (Chudnovsky algorithm) | [`pi/CLAUDE.md`](pi/CLAUDE.md) |
| [`prime/`](prime/) | Rust | Find all primes up to 10^N (segmented sieve) | [`prime/CLAUDE.md`](prime/CLAUDE.md) |

## Dependency Installation

A single installer covers all projects (Python packages, C libs, Rust toolchain, test tools):

```bash
bash pi/install_deps.sh
```

Installs: GMP + MPFR, `mpmath`, `gmpy2`, `coverage`, Rust toolchain (via rustup), `cargo-tarpaulin`.

## Quick Reference

### Python (`pi/`)

```bash
cd pi
make run       # python3 pi.py
make test      # python3 -m unittest test_pi -v
make coverage  # coverage run + report
```

### Rust (`pi/pi-rs/`)

```bash
cd pi/pi-rs
make pi        # cargo build --release
make test      # cargo test
```

### Rust (`prime/prime-rs/`)

```bash
cd prime/prime-rs
make prime     # cargo build --release
make test      # cargo test
```

## Testing Policy

**Unit tests must be written for all new code added to any project in this repository.**

- Python tests: add to `pi/test_pi.py`, run with `make test` from `pi/`
- Rust tests: add to the `#[cfg(test)] mod tests` block in `src/main.rs`, run with `make test`
- Coverage tools: `make coverage` (Python), `cargo tarpaulin` (Rust)

## CI

GitHub Actions (`.github/workflows/build.yml`) runs tests then builds for all projects on every push and pull request to `master`.  The build jobs depend on their test jobs — a build will not run if its tests fail.

**All jobs must run on Node.js 24.**  Use action versions that natively support Node.js 24:

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

## Committing Work

**Create a git commit at the end of each logical unit of work.**  A unit of work is a self-contained change: a new feature, a bug fix, a docs update, a refactor, or any combination that belongs together.  Do not batch unrelated changes into one commit and do not leave work uncommitted.

Commit message format:

```
<type>: <short summary>

<optional body explaining why, not what>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Common types: `feat`, `fix`, `docs`, `ci`, `refactor`, `test`, `chore`.

## Keeping CLAUDE.md Up To Date

**When making any change to this repository, update the relevant CLAUDE.md file(s) before finishing.**  These files are the primary reference for future sessions — stale documentation is worse than none.

What to update and when:

| Change | Files to update |
|--------|----------------|
| New or renamed function / constant | Project `CLAUDE.md` → Code Layout section |
| New or removed Makefile target | Project `CLAUDE.md` + `README.md` → Makefile targets table |
| New dependency or install step | `pi/install_deps.sh` + project `CLAUDE.md` + `README.md` |
| New test class or change in coverage % | Project `CLAUDE.md` + `README.md` → Testing section |
| New project added to the repo | Top-level `CLAUDE.md` → Repository Overview table |
| Behaviour or algorithm change | Project `CLAUDE.md` → Important Behavior / Implementation Details |
| New Rust CI build job added | `CLAUDE.md` → CI section; use `actions/checkout@v5`, upload artifact with `actions/upload-artifact@v5`, 7-day retention |
| Editing rule or policy change | All affected `CLAUDE.md` → Editing Guidance section |

The sub-project files (`pi/CLAUDE.md`, `prime/CLAUDE.md`) are the source of truth for implementation detail.  This top-level file is the entry point and quick reference — keep both in sync.

## Notes

- Generated output files (`pi_*_digits.txt`, `primes_1e*.txt`) are large artifacts — do not commit them.
- See each project's `CLAUDE.md` for detailed implementation guidance, code layout, and editing rules.
