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

## Notes

- Generated output files (`pi_*_digits.txt`, `primes_1e*.txt`) are large artifacts — do not commit them.
- See each project's `CLAUDE.md` for detailed implementation guidance, code layout, and editing rules.
