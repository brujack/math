# CLAUDE.md

## Repository Overview

Rust half of the `descartes` sub-project: tangent circles by Descartes' theorem and
integral Apollonian packings. Task 6 scaffold: `descartes_fourth` and a stub binary;
the packing, geometry, render and CLI arrive in later tasks of
`docs/superpowers/plans/2026-11-15-descartes.md`.
Injectable I/O pattern (ADR-0018): `run<W,E>(stdout, stderr, ...)`; `fn main()` is a thin
clap wrapper excluded from tarpaulin.

## Running

```bash
make descartes # cargo build --release (binary in target/release/descartes)
make install   # build, then copy to ${XDG_BIN_HOME:-~/.local/bin}/descartes
make lint      # cargo fmt --check + clippy -D warnings + cargo machete
make test      # lint + cargo nextest run
```

## Code Layout

- `DescartesError { BadInput, NoSolution }` — exit 2 and exit 1, as in Python
- `descartes_fourth(k1, k2, k3)` — both fourth curvatures; radicand below `-1e-12 × (|k1k2|+|k2k3|+|k3k1|)` is `NoSolution`, otherwise clamped at 0 (R23, identical to Python)
- `run<W,E>(stdout, stderr, k)` — stub in `main.rs`; replaced by the full CLI in Task 9

## Important Behavior

- `.cargo/mutants.toml` sets only `additional_cargo_test_args = ["--lib", "--bins", "--test", "cli"]`: `tests/parity.rs` runs the Python program, which cargo-mutants' crate-only copy does not contain.
- No `rug`, `rayon` or arbitrary precision (spec N2, N4).

## Coverage

≥90% on Linux CI.
