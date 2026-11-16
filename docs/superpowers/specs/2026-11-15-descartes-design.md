# Descartes: tangent-circle solver and integral Apollonian packings

- **Status:** Draft
- **Date:** 2026-11-15

## Context

A new top-level sub-project `descartes/`, a sibling of `triangle/`, built on the Descartes
circle theorem: four mutually tangent circles with curvatures `k1..k4` satisfy
`(k1+k2+k3+k4)² = 2(k1²+k2²+k3²+k4²)`. It has two modes in one CLI, in Python and Rust:

- **Solve:** given three mutually tangent circles (curvature and centre), print both fourth
  circles, using the complex Descartes theorem for the centres. This is a triangle-style
  geometry solver.
- **Packing:** given an integral root quadruple (default `-1 2 2 3`) and a curvature limit
  `N = 10^K`, enumerate every circle of the integral Apollonian packing with curvature `≤ N`.
  This is the sequence-to-a-limit shape of the other CLIs.

Both modes draw their circles in braille in the terminal, as `triangle` draws its solution.

It is the twelfth Rust crate and the tenth Python project. Every per-project file is rendered
from `scripts/crate_templates/` (operator rule: all crates treated identically).

No earlier spec, ADR or Backlog row mentions Descartes or Apollonian packings (checked with
`grep -rli -E 'descartes|apollon' docs/ */CLAUDE.md`, 0 hits).

## Measurements taken while designing

A draft probe (scratchpad, not shipped) implemented the packing depth-first search and an
independent geometric enumerator. Population: that probe on `claude`, three roots, Python 3.

1. **The first draft of the search was wrong, and the oracle caught it.** It applied the
   growth test `k' > k_i` to the root's own four reflections. For `(-1,2,2,3)`, reflecting the
   `3` gives `3`, the mirror-image circle, which the test dropped together with its whole
   subtree. The search reported 20 circles at N=30 against the oracle's 38. Exempting the
   four root reflections from the growth test made all 9 cases agree (table below).
2. **A non-root quadruple must be reduced first.** `(-1,2,3,6)` and `(-1,3,6,14)` are Descartes
   quadruples inside the `(-1,2,2,3)` packing. Seeding the search from them directly gives
   1665 and 731 circles at N=1000 instead of 3328. Reducing each to its root first (repeatedly
   reflect the largest curvature while that makes it smaller) gives `(-1,2,2,3)` and 3328.
3. **Counts, search and oracle agreeing** (circles with curvature ≤ N, positive curvatures only,
   with multiplicity; then the number of distinct curvatures):

   | Root         | N=30    | N=100    | N=1000     |
   | ------------ | ------- | -------- | ---------- |
   | `-1 2 2 3`   | 38 / 11 | 168 / 33 | 3328 / 324 |
   | `-2 3 6 7`   | 14 / 8  | 66 / 28  | 1300 / 297 |
   | `-3 4 12 13` | 10 / 6  | 40 / 17  | 744 / 200  |

   For `-1 2 2 3` at N=30 the distinct curvatures are
   `2 3 6 11 14 15 18 23 26 27 30`.

4. **Growth and speed** (search only, root `-1 2 2 3`; the oracle was not run past N=1000):

   | K   | circles   | distinct | Python seconds | local exponent |
   | --- | --------- | -------- | -------------- | -------------- |
   | 3   | 3,328     | 324      | 0.00           |                |
   | 4   | 67,166    | 3,299    | 0.09           | 1.3050         |
   | 5   | 1,359,170 | 33,273   | 1.84           | 1.3061         |

   The exponent matches the packing's Hausdorff dimension δ ≈ 1.30568. Extrapolated: K=6 is
   about 2.7×10⁷ circles (Python about 40 s) and K=7 about 5.5×10⁸ (Python about 12 min). The
   Rust figures in this spec are predictions until V1 measures them.

## Design

### CLI

```
descartes.py K [--root A B C D] [--show] [--yes] [--no-draw]   # packing, N = 10^K
descartes.py --smoke                                           # packing at SMOKE_SIZE
descartes.py --solve K1,X1,Y1 K2,X2,Y2 K3,X3,Y3 [--precision P] [--no-draw]
descartes.py                                                   # terminal: prompt for K; otherwise exit 2
```

The Rust binary `descartes` takes the same arguments and writes the same stdout and file.

Packing mode keeps the ADR-0030 contract: `SMOKE_SIZE = 2`, `LARGE_RUN_THRESHOLD = None`, the
output file always written, `--show` echoing it. K is 1-6 in Python and 1-8 in Rust, the same
kind of declared split amicable has (Python 1-7, Rust 1-8). `parse_args` adds `--root`,
`--solve`, `--precision` and `--no-draw` to the common ADR-0030 text; `scripts/cli_contract.py`
runs unchanged because the SIZE cases are unaffected.

### Components

Python `descartes/descartes.py` and Rust `descartes/descartes-rs/src/lib.rs` have the same
functions; `main.rs` is thin and uses injectable I/O (ADR-0018).

1. `descartes_fourth(k1, k2, k3)` returns both `k1+k2+k3 ± 2√(k1k2+k2k3+k3k1)`.
2. `solve(c1, c2, c3)` returns both fourth circles. It checks tangency first, then uses the
   complex theorem `k4·z4 = Σki·zi ± 2√(k1k2·z1z2 + k2k3·z2z3 + k3k1·z3z1)`. It pairs each
   curvature with the centre for which the circle is tangent to all three inputs.
3. `validate_root(a, b, c, d)` checks the Descartes relation and exactly one negative value,
   then reduces the quadruple to its root.
4. `root_centres(root)` places the bounding circle at the origin, the second circle inside it on
   the +x axis, the third from the triangle of centre distances, and the fourth through `solve`.
   Floats, for drawing only.
5. `pack(root, n)` is an iterative depth-first search over `(quadruple, replaced index)`. The
   four reflections of the root are seeded when `≤ n`, with no growth test. Every later step
   reflects each position except the one just replaced, `k' = 2(sum of the other three) − k_i`,
   and keeps `k'` only when `k_i < k' ≤ n`. It returns the circle count and a bitmap of
   distinct curvatures. Integers only; Rust uses `i64`, which cannot overflow because
   `k' ≤ 6n` and `n ≤ 10^8`.
6. `visible(root, limit)` runs the same search carrying centres (`z' = (2·Σ(k·z) of the other
three − k_i·z_i) / k'`), keeping circles with curvature `≤ limit`. It is separate from
   `pack`, so the counting loop never touches floats.
7. `render(circles, width, height)` rasterises circles into braille with the midpoint circle
   algorithm. It reads only a list of `(k, x, y)` circles, so another back end can replace it.

### Output

Packing mode prints, in this order: the reduced root, the circle count, the distinct-curvature
count, the elapsed time, `Saved to <file>`, then the drawing. The file is `descartes_1eK.txt`
for the default root and `descartes_1eK_root_A_B_C_D.txt` otherwise (the reduced root, sorted),
one distinct curvature per line in ascending order. The drawing shows circles with curvature
`≤ 2 × canvas width in braille dots`.

Solve mode prints a table of the three given circles and both solutions (curvature, radius,
centre) at `--precision` places (default 4), then draws all five circles.

### Errors

Exit 2: input that cannot describe a problem (unparsable value, wrong count, non-integer root
value, K out of range, zero curvature in `--solve`). Exit 1: well-formed input with no answer
(a root that fails the Descartes relation, a root without exactly one negative value, circles
that are not mutually tangent). Every message names the operation and the input.

### Testing

TDD per function, with boundary, error-path and state-transition cases.

- The geometric enumerator from the probe, cleaned up, lives in the test files only and is the
  oracle for `pack` at N ≤ 1000 on the three roots in the table.
- Python and Rust stdout and files are compared byte for byte at K=1-3 in both modes.
- BATS failure-mode tests run on both binaries; the Rust ones skip when the binary is absent.
- Coverage ≥ 90 % in both languages; `mutation-py` and `mutation-rs` hold 0 survivors on
  changed lines.

## Requirements

- **R1.** `[PR1]` `descartes/` exists with `descartes.py`, `test_descartes.py`, `CLAUDE.md`, `README.md`, `mutants-equivalent.toml`, and a `Makefile`, `install_deps.sh`, `pyrightconfig.json` and `cosmic-ray.toml` byte-equal to `scripts/render_crate_files.py --write` output for project `descartes`, module `descartes`.
- **R2.** `[PR1]` Python `pack((-1,2,2,3), n)` returns circle counts 38, 168 and 3328 and distinct-curvature counts 11, 33 and 324 for n = 30, 100 and 1000; for root `(-2,3,6,7)` it returns 14, 66, 1300 and 8, 28, 297; for root `(-3,4,12,13)` it returns 10, 40, 744 and 6, 17, 200.
- **R3.** `[PR1]` Python `pack((-1,2,2,3), 30)`'s distinct curvatures are exactly `2 3 6 11 14 15 18 23 26 27 30`.
- **R4.** `[PR1]` A test-only geometric enumerator, sharing no function with `descartes.py` beyond `root_centres`, agrees with `pack` on count and distinct set for every root and n in R2.
- **R5.** `[PR1]` `validate_root` reduces `(-1,2,3,6)` and `(-1,3,6,14)` to `(-1,2,2,3)`, and packing mode given either as `--root` produces the same counts and file contents as the default root.
- **R6.** `[PR1]` Packing mode exits 1 with a message naming the root for `--root -1 2 2 4` (Descartes relation fails: `(Σk)²=49`, `2Σk²=50`) and for `--root 0 0 1 1` (not exactly one negative curvature), and exits 2 for `--root -1 2 2 x`.
- **R7.** `[PR1]` Python accepts K 1-6 and exits 2 naming the range for K 0 and K 7; `SMOKE_SIZE` is 2 and `LARGE_RUN_THRESHOLD` is `None`.
- **R8.** `[PR1]` Packing mode writes `descartes_1eK.txt` for the default root and `descartes_1eK_root_A_B_C_D.txt` (reduced root, ascending) otherwise, one distinct curvature per line in ascending order, and prints the reduced root, circle count, distinct count, elapsed time and `Saved to <file>` in that order.
- **R9.** `[PR1]` `--solve` on the circles of `(-1,2,2,3)` at their `root_centres` positions (curvatures -1, 2 and 2) returns curvatures 3 and 3 with centres mirrored in the x axis, and every returned circle is tangent to all three inputs within `1e-9 × max(|radius|)`.
- **R10.** `[PR1]` `--solve` exits 1 naming the pair for two circles that are not tangent, and exits 2 for a zero curvature or an unparsable `K,X,Y` triple.
- **R11.** `[PR1]` `render` reads only a list of `(k, x, y)` circles; `--no-draw` suppresses the drawing in both modes; the packing drawing includes only circles with curvature `≤ 2 × canvas width in dots`.
- **R12.** `[PR1]` `make test` in `descartes/` runs `scripts/cli_contract.py descartes.py` and it exits 0.
- **R13.** `[PR2]` `descartes/descartes-rs/` exists with every file `render_crate_files.py` renders for a crate byte-equal to its output, `Cargo.toml` with no `rug` and no `rayon` dependency, and `tests/test_crate_uniformity.py` passing over 12 crates.
- **R14.** `[PR2]` Rust accepts K 1-8 and exits 2 naming the range for K 0 and K 9; for every other input in R2-R10 it gives the same results and exit codes as Python.
- **R15.** `[PR2]` A test runs both programs at K = 1, 2 and 3 for the default root and `--root -2 3 6 7`, and for `--solve` on the R9 input, and asserts stdout and output files are byte-identical.
- **R16.** `[PR2]` `descartes-py.yml`, `descartes-rs.yml` and `release-descartes-rs.yml` exist, rendered from the templates; `scripts/pre-commit` and `scripts/pre-push` loop over `descartes` and `descartes/descartes-rs`; the root `README.md` and `CLAUDE.md` list the project; `.gitignore` lists `descartes_1e*.txt`.
- **R17.** `[PR2]` BATS tests cover missing K, K out of range, non-integer K, a bad root and a non-tangent `--solve` for both binaries, each Rust case starting with `[[ -x "$RUST_BIN" ]] || skip`.
- **V1.** On `claude`, time and peak memory of Rust packing at K = 6, 7 and 8 and Python at K = 6, recorded in the PR2 body; if Rust K=8 exceeds 10 minutes, the K ceiling is amended down before merge.
- **V2.** The local growth exponent `log10(count(K+1)/count(K))` from Rust at K = 6→7 and 7→8 lies within 0.02 of 1.30568, recorded in the PR2 body.
- **V3.** Python and Rust line coverage ≥ 90 % in CI, and `mutation-pr` green on both PRs.
- **N1.** No graphical window, SVG or plotting back end (a Desmos-style macOS window is a P4 Backlog row).
- **N2.** No parallel packing: no `rayon` and no threads in the packing search (a Backlog row).
- **N3.** No zero-curvature (straight line) circles in `--solve`, and no non-integral packings.
- **N4.** No `rug`, `gmpy2` or arbitrary-precision arithmetic.
- **N5.** No change to any existing sub-project's source or tests (root `scripts/`, `tests/`, hooks and docs may change to register the new project), and no edit to a rendered file except through its template.

## Multi-Lens Review

Reviewed at commit: `ce72885` (spec commit, before Step 8 dispatch)

### Goal-Fit

Finding: (1) R15 contradicts R8: elapsed time on stdout cannot be byte-identical across two processes. (2) Byte parity is sound for integer output (curvature file, count lines) but not for float-derived output (solve table, braille): Python `round()` is half-even, Rust `f64::round` half-away; compare those numerically or fix one rounding rule. (3) Solve mode is a second program sharing only `descartes_fourth` with packing, outside the ADR-0030 SIZE shape; dropping it or deferring it to a later Python-only PR keeps most of the value at about half the parity and mutation surface. (4) Reads-it: the packing drawing is the same picture at every K (decoration); V2 has no action on failure (decoration); Rust K=8 writes about 3x10^7 lines (~300 MB) with no reader, so V1 should record file size. (5) `render_crate_files.py` hard-codes `CRATES` (11) and `PYTHON_PROJECTS` (9) and `test_crate_uniformity.py` asserts both lengths; R1/R13 should name those edits. (6) R11 "reads only a list" has no behavioural test; R15 passes when both binaries fail identically unless it asserts exit 0. Verified: an independent DFS reproduced every table value; `cli_contract.py` cases never reach the extra flags; rug-free crates already exist.
Assumption: Python and Rust produce byte-identical float output (solve table at `--precision`, braille rasters). Settle by diffing `f'{x:.4f}'` against `format!("{:.4}", x)` on 10^6 random doubles and diffing both renderers on the `(-1,2,2,3)` circles.
Disposition:

### Ergonomics

Finding: (1) Load-bearing: Rust clap will likely parse `--solve -1,0,0 ...` (a bounding circle first) as an unknown short flag unless the argument sets `allow_hyphen_values`; `allow_negative_numbers` does not cover `-1,0,0`. Python argparse 3.14 parses it (probed). The spec must state the parser setting. (2) R15 vs R8 elapsed time, as Goal-Fit (1). (3) Solve prints 4 places by default, but the input tangency check has no stated tolerance; pasting printed centres back (`0.6667` for 2/3) fails at 1e-9. State an input tolerance or print full precision. (4) The packing drawing's circle set changes with terminal width; say so in help. (5) R11 passes for a renderer that draws nothing; R17 Rust cases go green by skip in any job without the binary; add a non-empty-drawing check.
Assumption: byte-identical braille from float centres across languages (rounding rule, complex sqrt branch). Settle by running the R15 cases with drawing on and `cmp` after masking the time line.
Disposition:

### Risk

Finding: (1) R8/R15 elapsed-time contradiction. (2) The R9 geometry is dyadic, so scaled coordinates land on exact .5 ties where Python and Rust round differently; name one rule, for example `floor(x+0.5)`, in both. (3) R9 is degenerate: for curvatures (-1,2,2) the radicand is 0 and both solutions are 3, so curvature-to-centre pairing is never tested on distinct k4; add a case such as three unit circles. (4) Vacuous passes: R15 (two empty stdouts compare equal; assert exit 0 and non-empty), R11 (never-drawing program passes), R10 (always-exit-2 program passes). (5) Otherwise proportionate: K=8 about 1.1x10^10 circles, likely 1-2 min Rust, guarded by V1; bitmap 12.5 MB; i64 safe; reduction terminates; a new crate is all changed lines, so `mutation-rs` 0 survivors covers the whole crate and tolerance comparisons will need equivalent entries. Verified every table value and both reductions with an independent DFS.
Assumption: same float byte-parity assumption; check whether any scaled R9 coordinate is an exact .5.
Disposition:

### Adversarial Spec Review (comparison/judge designs only)

Trigger: borderline (oracle-versus-implementation comparison); run per the default-to-run rule. Finding: pinned values are correct, confirmed by an exact integer oracle sharing no code with the spec (circles as exact (k, k*z) pairs, every reflection applied, exact dedup): (-1,2,2,3) 38/11, 168/33, 3328/324 and K=4 67166/3299; every R2 value for the other two roots; the R3 set. The spec's `pack` rule also matches a float oracle on (-11,21,24,28) 144/114, (-3,5,8,8) 785/203 and (-6,10,15,19) 322/143 at N=1000. Gaps, by weight: (1) nothing checks Rust correctness above K=3; pin K=4 (67166/3299) and K=5 (1359170/33273) in both languages and compare Python and Rust at K=4-6; state the count type (K=8 overflows `u32`). (2) All three tested roots satisfy d = a+b+c, the shape that caused the probe bug; add (-11,21,24,28) or (-3,5,8,8). (3) The empty result is untested: (-11,21,24,28) at K=1 yields 0 circles (empty file, no drawing). (4) Collinear roots are a float hazard: for (-2,3,6,7) the probe put the third centre at y = sqrt(1.1e-16), about 1e-8, failing a 1e-9 tangency check; if `root_centres` routes through `solve`'s check, two of three table roots fail. Bias: the oracle shares the reduced root and `root_centres` with `pack`, so a wrong reduction is invisible to it; R5 covers only two reductions.
Assumption: byte parity at K<=3 implies Rust correct to K=8; refuted or confirmed by running Rust at K=4-6 against Python's counts.
Disposition:
