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

GitHub Actions (`.github/workflows/build.yml`) runs `cargo build --release` for both `pi-rs` and `prime-rs` on every push and pull request to `master`.

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
| Editing rule or policy change | All affected `CLAUDE.md` → Editing Guidance section |

The sub-project files (`pi/CLAUDE.md`, `prime/CLAUDE.md`) are the source of truth for implementation detail.  This top-level file is the entry point and quick reference — keep both in sync.

## Notes

- Generated output files (`pi_*_digits.txt`, `primes_1e*.txt`) are large artifacts — do not commit them.
- See each project's `CLAUDE.md` for detailed implementation guidance, code layout, and editing rules.
