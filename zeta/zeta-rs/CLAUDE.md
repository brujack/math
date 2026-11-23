# CLAUDE.md

This file provides guidance to Claude when working with zeta-rs.

## Overview

Rust CLI for certified Riemann Hypothesis verification up to height 10^N (in progress).

## Build

```bash
make zeta       # cargo build --release (binary in target/release/zeta)
make install    # build, then copy to ${XDG_BIN_HOME:-~/.local/bin}/zeta
make lint       # cargo fmt --check + cargo clippy
make test       # lint + cargo test
```

## Code Layout

- `src/lib.rs` — library crate root; declares the modules below
- `src/interval.rs` — `Interval` over MPFR with directed rounding (lo Down, hi Up); `excludes_zero()` is true only for finite bounds that exclude 0, so a sign is certified only then
- `src/config.rs` — `VerifyConfig`, widen-only: `new` admits only settings at least as strict as the defaults (Gabcke multiplier ≥ 1, precision cap 64–512, depth cap ≤ 40)
- `src/main.rs` — clap `Cli` (optional exponent N) and a thin `main()`, excluded from tarpaulin with `#[cfg(not(tarpaulin_include))]`

## Testing

Coverage floor: at least 90% (enforced via `cargo tarpaulin --fail-under 90` in CI).
