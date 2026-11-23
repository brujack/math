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
- `src/theta.rs` — certified θ(t) by Stirling (DLMF 5.11, shift 10, n = 25; floor about 3.4·10⁻²² near t = 2π); `ThetaContext` per precision; `gram_bracket(n, prec)` returns f64 points 2π < b < c with certified signs of θ − nπ at both ends
- `src/complex.rs` — `pub(crate)` complex intervals (re, im as `Interval`), shared by θ and Euler–Maclaurin
- `src/zfun.rs` — Hardy Z: `ZEvaluator` per precision (Riemann–Siegel with Gabcke's C₀ bound 0.127·t^(−3/4) for t ≥ 200, tabulated ln k and 1/√k; Euler–Maclaurin by Johansson Thm 1 below 200); `RealZ` holds one evaluator per rung 64/128/256/512; `ZSource::z_over(lo, hi, prec)` encloses Z over every t in [lo, hi] (theta by its end values from t = 7, N from the interval, required, no default); `ZSource::z(t, prec)` returns `Ok(None)` for a refusal and `Err(ZFault)` for a fault (exit 6 once the verifier lands; the self-check runs over `ZPaths`, where any `ZError` is a `SelfCheckFailure`, exit 5); `self_check` compares both paths at 8 points in [200, 300] at 128 bits with the unscaled 0.127
- `src/isolate.rs` — `GramBlock` (certified boundary points plus Rosser's expected count) in, `BlockPoints` out via `isolate_block`: every gap is halved per level until the alternations reach Rosser's count, `depth_cap` or `MAX_BLOCK_POINTS` = 2^16 points, whichever comes first (effective depth 16, below the configured cap of 40); `IsolateError` (`Fault`, `BadInterval`, `NotSignChange`, `BoundaryInsideInterval`); `Point { t, sign }`; `certified_sign` wraps `zfun::certified_sign_ladder` (shared with boundary.rs), which climbs the 64→512 ladder only while each rung at least halves the enclosure width; `resolve_straddle(lo, hi, t, Option<&ZeroFreeBracket>, z, cfg)` bisects at most 60 times (a midpoint equal to t is `Uncertain`) and returns a `Straddle`
- `src/boundary.rs` — `certify_boundary(n, z, cfg)`: `gram_bracket` gives `[b_n, c_n]`, then Z's sign over the whole bracket is certified through `ZSource::z_over` on the 64→512 ladder (capped by `cfg`); `Ok(None)` when anything stays uncertain, `Err` only for a Z fault; `Boundary` (private fields, accessors `point()` = `Point { t: b_n, sign }` and `bracket()`) where `ZeroFreeBracket` has no public constructor (a `#[cfg(test)]` one exists for tests)
- `src/turing.rs` — Turing's method (Trudgian 2011 eq. 2.1, a = 2.067, b = 0.059): `establish(m, z, cfg)` refuses b_M ≤ 168π, a bad g_M and an uncertified bracket, adds Gram blocks (Brent's definition; a block over `MAX_BLOCK_LEN` = 16 intervals fails the candidate) after g_M until their count meets eq. 2.1 at c of the last block, crediting an adjacent pair of the merged certified points to the one closed block `[b_j, b_k]` holding both; `TuringBound` carries g_M's `Boundary`; `choose_m(t, ...)` takes M as the smallest index with certified θ(T) − Mπ ≤ 0 (g_M ≥ max(T, 168π), so T may lie inside g_M's bracket), rejects a non-finite T as an internal fault, then tries at most 11 consecutive indices, re-failing a block already known to fail without isolating it again; `TuringFailure::is_fault` separates faults (exit 6) from candidate failures
- `src/main.rs` — `run` reads N (argument or prompt, 2–7 else exit 1), warns on N = 7, runs the self-check (exit 5 on failure) and, until zero isolation lands, prints `RH NOT verified up to <T>: zero isolation is not implemented yet` and exits 3; thin `main()` excluded from tarpaulin with `#[cfg(not(tarpaulin_include))]`

## Exit codes

0 verified, 1 bad input, 3 not verified (uncertified, Turing bound not established or not yet implemented), 4 output write failed (including stdout or stderr), 5 self-check failed (including any Z-path error inside it), 6 internal fault during verification (a Z fault, a NaN height, a sign conflict). Today `run` returns 1, 3, 4 and 5, and clap itself exits 0 for `--help` and 2 for a usage error; a verified run's 0 and exit 6 arrive with the verifier (plan Tasks 9–10). Only 0 claims verification, and only up to T.

## Testing

Coverage floor: at least 90% (enforced via `cargo tarpaulin --fail-under 90` in CI).
