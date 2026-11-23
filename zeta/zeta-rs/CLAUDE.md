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
- `src/zfun.rs` — Hardy Z: `ZEvaluator` per precision (Riemann–Siegel with Gabcke's C₀ bound 0.127·t^(−3/4) for t ≥ 200, tabulated ln k and 1/√k; Euler–Maclaurin by Johansson Thm 1 below 200); `RealZ` holds one evaluator per rung 64/128/256/512; `ZSource::z_over(lo, hi, prec)` encloses Z over every t in [lo, hi] (theta by its end values from t = 7, N from the interval, required, no default); `ZSource::z(t, prec)` returns `Ok(None)` for a refusal and `Err(ZFault)` for a fault (exit 6; the self-check runs over `ZPaths`, where any `ZError` is a `SelfCheckFailure`, exit 5); `self_check` compares both paths at 8 points in [200, 300] at 128 bits with the unscaled 0.127
- `src/isolate.rs` — `GramBlock` (certified boundary points plus Rosser's expected count) in, `BlockPoints` out via `isolate_block`: every gap is halved per level until the alternations reach Rosser's count, `depth_cap` or `MAX_BLOCK_POINTS` = 2^16 points, whichever comes first (effective depth 16, below the configured cap of 40); `IsolateError` (`Fault`, `BadInterval`, `NotSignChange`, `BoundaryInsideInterval`); `Point { t, sign }`; `certified_sign` wraps `zfun::certified_sign_ladder` (shared with boundary.rs), which climbs the 64→512 ladder only while each rung at least halves the enclosure width; `resolve_straddle(lo, hi, t, Option<&ZeroFreeBracket>, z, cfg)` bisects at most 60 times (a midpoint equal to t is `Uncertain`) and returns a `Straddle`
- `src/boundary.rs` — `certify_boundary(n, z, cfg)`: `gram_bracket` gives `[b_n, c_n]`, then Z's sign over the whole bracket is certified through `ZSource::z_over` on the 64→512 ladder (capped by `cfg`); `Ok(None)` when anything stays uncertain, `Err` only for a Z fault; `Boundary` (private fields, accessors `point()` = `Point { t: b_n, sign }` and `bracket()`) where `ZeroFreeBracket` has no public constructor (a `#[cfg(test)]` one exists for tests)
- `src/turing.rs` — Turing's method (Trudgian 2011 eq. 2.1, a = 2.067, b = 0.059): `establish(m, z, cfg)` refuses b_M ≤ 168π, a bad g_M and an uncertified bracket, adds Gram blocks (Brent's definition; a block over `MAX_BLOCK_LEN` = 16 intervals fails the candidate) after g_M until their count meets eq. 2.1 at c of the last block, crediting an adjacent pair of the merged certified points to the one closed block `[b_j, b_k]` holding both; `TuringBound` carries g_M's `Boundary`; `choose_m(t, ...)` takes M as the smallest index with certified θ(T) − Mπ ≤ 0 (g_M ≥ max(T, 168π), so T may lie inside g_M's bracket), rejects a non-finite T as an internal fault, then tries at most 11 consecutive indices, re-failing a block already known to fail without isolating it again; `TuringFailure::is_fault` separates faults (exit 6) from candidate failures
- `src/verify.rs` — `verify(t, z, cfg, PoolPolicy, stderr) -> Verdict` (`Verified{count, intervals, stats}` (`RunStats`: M, g_M bracket, Gram blocks, Rosser exceptions, max precision seen by a `PrecisionProbe` around Z, threads), `NotVerified{reason, blocks}`, `Fault{reason}`, `WriteFailed`): `choose_m`, certify g_-1..g_M on a private `ThreadPoolBuilder::build` pool (never the global one; `Runner::try_map` stops at the first `Err`; a build failure prints `Parallel mode unavailable ({error}); falling back to serial.` to `stderr` and runs serially, as do `Serial` and `Threads(0)`; a panic anywhere is `Fault::WorkerPanicked`), cut the usable boundaries into Brent blocks (an unusable Gram point merges its block with the next), isolate every block, re-search each unresolved block merged with its neighbours (Rosser neighbour search, judged by every known point in the union), then merge the points in place (`PointsFault` on a NaN or a sign conflict) and count L in [b_-1, b_M] (L > M+1 fault, L < M+1 `ShortCount`, L = M+1 with a block still unresolved `UnresolvedBlocks`); the interval holding T goes through `resolve_straddle`
- `src/main.rs` — `run` reads N (argument or prompt, 2–7 else exit 1), warns on N = 7, runs the self-check (exit 5 on failure), removes a stale `zeta_1eN.tmp.txt`, calls `verify` and maps the `Verdict`: `Verified` writes `zeta_1eN.tmp.txt` (header `# n a b`, a rounded down and b rounded up to 30 digits) through an `OutputStore` (opened with `create_new`, synced before the rename; a failed create removes nothing), renames it to `zeta_1eN.txt` and prints the `RH verified: ...` line (exit 0); `NotVerified` prints `RH NOT verified up to <T>: <reason>` and any unresolved Gram blocks on stdout (exit 3); `Fault` prints `internal error: ...` on stderr (exit 6); a write failure removes the temporary file (exit 4). `run_with` and the self-check skip of `Env` exist only under `#[cfg(test)]`; `NotVerifiedReason` has a spec-worded `Display` and the verified block prints in the spec order after the save; `run` fixes the production values. Tests named `e2e_` run a full verification and are skipped by cargo-mutants (`.cargo/mutants.toml`, spec V8), so every line they reach is also covered by a unit test; `tests/fixtures/odlyzko_1e3.txt` holds the first 649 zeros for them. Thin `main()` excluded from tarpaulin with `#[cfg(not(tarpaulin_include))]`

## Exit codes

0 verified, 1 bad input, 3 not verified (uncertified, Turing bound not established), 4 output write failed (the table, stdout or stderr; the temporary file is removed), 5 self-check failed (including any Z-path error inside it), 6 internal fault during verification (a Z fault, a NaN height, a sign conflict, a worker panic). `run` returns all of 0, 1, 3, 4, 5 and 6, and clap itself exits 0 for `--help` and 2 for a usage error. Only 0 claims verification, and only up to T; no `zeta_1eN.txt` is created on any other exit.

## Testing

Coverage floor: at least 90% (enforced via `cargo tarpaulin --fail-under 90` in CI).
