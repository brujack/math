# zeta

Certified verification of the Riemann Hypothesis up to height 10^N for N = 2–7, with an optional `--refine` pass that narrows each zero's bracket and reports the spacing statistics.

`zeta N` proves a finite-range theorem: every nontrivial zero ρ of the
Riemann zeta function with 0 < Im ρ ≤ T = 10^N lies on the critical line Re s = 1/2 and is
simple. It also reports how many such zeros there are. Every number the proof depends
on is an interval enclosure computed with directed rounding (MPFR), so the claim holds even
though the computation runs in floating point.

This is evidence for the Riemann Hypothesis, never a proof of it: the output says "RH
verified up to T", never "RH holds".

No Python implementation — Rust only.

## Status

For N from 2 to 7 the CLI runs the self-check of its Hardy Z evaluator, then the one-pass
verification. When every zero up to T = 10^N is isolated, it writes `zeta_1eN.txt`
(header `# n a b`, then one line per zero with the certified interval (a, b), a rounded
down and b rounded up to 30 significant digits) and prints to stdout:

```text
Self-check: Riemann–Siegel and Euler–Maclaurin agree on [200, 300] (8 points)
Turing bound: N(g_M) <= M+1 established at g_M = <value>
Isolating zeros in 0 < t <= <T> (<k> threads)...

RH verified: all <count> nontrivial zeros with 0 < Im s <= <T> lie on Re s = 1/2 and are simple
Gram blocks: <b>   Rosser exceptions: <r>   max precision: <p> bits
Saved zeta_1eN.txt
Elapsed: <s> s
```

`<value>` is g_M to 6 decimals (a `[lo, hi]` pair when its certified bracket is wider than that). These lines are printed together once the table is saved, so a failed save is never preceded
by a verified claim.

The table is written to `zeta_1eN.tmp.txt` and renamed on completion; no `zeta_1eN.txt` is
created on any other exit. When the proof cannot be completed it prints
`RH NOT verified up to <T>: <reason>` (for example `647 of 649 zeros isolated`, then the
unresolved Gram blocks and `No claim is made for this range.`) and exits 3;
no claim is made for that range. N = 7 also prints a warning about output size and run time
to stderr.

Progress goes to stderr, never stdout, in two stages: `progress: <done>/<total> Gram points, t = <t>`
while the Gram points g_-1 .. g_M are certified (the stage that dominates a large N), then
`progress: <done>/<total> Gram blocks, t = <t>` while the blocks are isolated. `t` is the
highest height below which every item of the stage has finished (items finish out of order
on the pool, so `t` never passes an unfinished one). Each stage prints a line when at least
1% more of its items have finished and at least 2 s have passed since that stage's previous
line, plus one final line, so a short run prints only the two final lines. A run that stops
before a stage (for example a failed Turing step) prints none for it.

| Exit | Meaning |
| ---- | ------- |
| 0 | Verified up to T |
| 1 | Bad input: N outside 2–7, not a number, or end of input at the prompt |
| 3 | Not verified: any uncertain result (an unresolved Gram block, too few zeros isolated, Turing's bound not established, a zero's side of T uncertain, no certified left boundary or Gram block); no output file |
| 4 | A write to stdout, stderr or the output file failed (a failed table write removes the temporary file; if only stdout fails after the table was saved, the table stays) |
| 5 | Self-check failed: the Riemann–Siegel and Euler–Maclaurin paths disagree at a test point |
| 6 | Internal fault during verification (a Z fault, a NaN height, a sign conflict, a worker panic) |

The library already has the certified building blocks:

- `Interval` — MPFR interval arithmetic with directed rounding (lower bound rounded down,
  upper bound rounded up); a sign is certified only when the interval excludes 0
- `VerifyConfig` — verification settings, which can only be made stricter than the defaults
- certified Riemann–Siegel θ(t) by the Stirling series with an explicit remainder bound,
  and Gram-point brackets with certified signs at both ends
- certified Hardy Z(t): Riemann–Siegel with Gabcke's remainder bound for t ≥ 200,
  Euler–Maclaurin below 200, and a self-check that compares the two paths at 8 points
  in [200, 300]

## Usage

```bash
./target/release/zeta            # prompts for N
./target/release/zeta 3          # verifies the 649 zeros up to 1000, writes zeta_1e3.txt, exits 0
./target/release/zeta 3 --refine # also narrows every bracket and prints the spacing report
```

### `--refine`

After a verified run, `--refine` bisects each zero's certified bracket (at most 256 steps,
every step certified by the same precision ladder) and replaces the table with
`# n a b t_n w_n`: the narrowed bracket `[a, b]`, `t_n` a 15-significant-digit rounded
estimate of its midpoint (it can print just outside a very narrow `[a, b]`) and `w_n = b - a`
rounded up to 3 significant digits. `Elapsed:` then covers verification plus refinement.

Resolution is not f64 everywhere. Above t = 200 the Hardy Z enclosure carries Gabcke's
Riemann–Siegel remainder bound 0.127·t^(-3/4) (about 2.4e-3 at t = 200), which does not
shrink with precision, so brackets there stop at `w_n` of about 1e-3 to 4e-3 (measured at
N = 3: 570 of 649 zeros, largest `w_n` 3.89e-3, the same at N = 4). Below t = 200
(Euler–Maclaurin) they reach about 1e-15. Do not expect f64-resolution brackets above t = 200.

The spacing report compares the normalised gaps
`delta_n = (t_(n+1) - t_n) ln(t_n / 2 pi) / 2 pi` with the Wigner surmise of the GUE: a
20-bin histogram of the observed density against `p(s)`, the Kolmogorov–Smirnov distance
between the empirical gap distribution and the surmise's CDF (smaller is closer), and the largest `w_n`, which
bounds how well every zero is located. Zeros repel each other (the histogram is empty near
`s = 0`), whereas independent random points would instead peak there. This is a
statistical illustration of random-matrix behaviour, not part of the proof.

Measured example, release build, 2026-11-24, Linux x86_64 with 48 threads, `zeta 3 --refine`
(649 zeros, 648 spacings, 0.6 s): KS distance 0.0448, largest `w_n` 3.89e-3. Reproduce it
with the command above.

## Results page

The results page is generated locally from finished run directories and committed under `zeta/results/site/`. Each run directory holds the CLI's `out.txt` and `err.txt`, where `err.txt` must be the report from `/usr/bin/time -v`, because the generator reads provenance from it. Each `--run` id must match an `id` entry in `runs.toml`. To regenerate:

```bash
python3 scripts/zeta_results.py --runs-toml zeta/results/runs.toml \
    --run t3=<run dir> --run r7=<run dir> \
    --out zeta/results/site --runs-out zeta/results/runs
```

The generator fails closed on any check (provenance from `/usr/bin/time -v`, an exact-midpoint cross-check against the CLI's printed values), so a refusal means the input needs fixing, not the generator.

Output targets are guarded. The generator refuses `.`, `..` and the current directory, symlinked targets or `.tmp` and `.old` siblings, targets that overlap an input or each other, and any existing non-empty directory without the `.zeta-results` marker that it writes into every tree it produces. The deploy step does not publish the marker.

To publish the committed site, dispatch the workflow from master: `gh workflow run zeta-results-pages.yml --ref master`. It copies the site into `gh-pages/zeta/` under the shared `gh-pages` concurrency group. See [ADR-0047](../docs/adr/0047-zeta-results-page-on-gh-pages.md).

## Build

```bash
cd zeta-rs
make zeta       # cargo build --release (binary in target/release/zeta)
make install    # build, then copy to ${XDG_BIN_HOME:-$HOME/.local/bin}/zeta
make lint       # cargo fmt --check + clippy
make test       # lint + cargo test
```

## Design

- Spec: [`docs/superpowers/specs/2026-11-23-zeta-rh-verification-design.md`](../docs/superpowers/specs/2026-11-23-zeta-rh-verification-design.md)
- Plan: [`docs/superpowers/plans/2026-11-23-zeta-rh-verification.md`](../docs/superpowers/plans/2026-11-23-zeta-rh-verification.md)
