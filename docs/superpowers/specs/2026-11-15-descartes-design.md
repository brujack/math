# Descartes: tangent-circle solver and integral Apollonian packings

- **Status:** Approved
- **Approved:** 2026-11-15
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
descartes.py --solve K1,X1,Y1 K2,X2,Y2 K3,X3,Y3 [--precision P] [--no-draw]   # P rounds the display only
descartes.py                                                   # terminal: prompt for K; otherwise exit 2
```

The Rust binary `descartes` takes the same arguments. Its clap `--solve` argument sets
`allow_hyphen_values`, so a triple starting with a negative curvature (`-1,0,0`) parses as a
value, as it does under Python argparse.

Packing mode keeps the ADR-0030 contract: `SMOKE_SIZE = 2`, `LARGE_RUN_THRESHOLD = None`, the
output file always written, `--show` echoing it. K is 1-6 in Python and 1-8 in Rust, the same
kind of declared split amicable has (Python 1-7, Rust 1-8). `parse_args` adds `--root`,
`--solve`, `--precision` and `--no-draw` to the common ADR-0030 text; `scripts/cli_contract.py`
runs unchanged because its cases (SIZE, `SIZE --show`, `--smoke`, stdin `y`, `SIZE --yes`, no
arguments) never reach those flags.

Registering a twelfth crate and tenth Python project edits the hard-coded `CRATES` and
`PYTHON_PROJECTS` lists in `scripts/render_crate_files.py` and the length assertions in
`tests/test_crate_uniformity.py` (today 11 and 9).

### Components

Python `descartes/descartes.py` and Rust `descartes/descartes-rs/src/lib.rs` have the same
functions; `main.rs` is thin and uses injectable I/O (ADR-0018).

1. `descartes_fourth(k1, k2, k3)` returns both `k1+k2+k3 ± 2√(k1k2+k2k3+k3k1)`.
2. `solve(c1, c2, c3)` returns both fourth circles. It checks input tangency first: circles i and j pass when
   `|d_ij − (r_i ± r_j)| ≤ 1e-9 × (|r_i| + |r_j|)`, so the tolerance scales with the pair and
   pasted full-precision output round-trips; then uses the complex theorem `k4·z4 = Σki·zi ± 2√(k1k2·z1z2 + k2k3·z2z3 + k3k1·z3z1)`, pairing
   each curvature with the centre for which the circle is tangent to all three inputs. (Tangency
   rule and result set made exact by R24 and R25.)
3. `validate_root(a, b, c, d)` checks the Descartes relation and exactly one negative value,
   then reduces the quadruple to its root.
4. `root_centres(root)` places the bounding circle at the origin, the second circle inside it on
   the +x axis, the third from the triangle of centre distances (a negative `y²` from rounding,
   as for the collinear root `(-2,3,6,7)`, is clamped to 0), and the fourth by the complex
   theorem. It never runs `solve`'s input tangency check. Floats, for drawing only. (Clamp
   superseded by R25.)
5. `pack(root, n)` is an iterative depth-first search over `(quadruple, replaced index)`. It
   first counts each of the root's own positive curvatures that is `≤ n`. The
   four reflections of the root are seeded when `≤ n`, with no growth test. Every later step
   reflects each position except the one just replaced, `k' = 2(sum of the other three) − k_i`,
   and keeps `k'` only when `k_i < k' ≤ n`. It returns the circle count and a bitmap of
   distinct curvatures. Curvatures and the count are `i64` in Rust (the count at K=8 is about
   1.1×10¹⁰, past `u32`); a curvature cannot overflow because `k' ≤ 6n` and `n ≤ 10^8`.
6. `visible(root, limit)` runs the same search carrying centres (`z' = (2·Σ(k·z) of the other
   three − k_i·z_i) / k'`), keeping circles with curvature `≤ limit`. It is separate from
   `pack`, so the counting loop never touches floats.
7. `render(circles, width, height)` rasterises circles into braille with the midpoint circle
   algorithm. It reads only a list of `(k, x, y)` circles, so another back end can replace it.
   The canvas is the terminal size when stdout is a terminal and a fixed 60 × 24 cells when it
   is not, in both languages (as `triangle`'s `_PIPE_WIDTH`). Drawings are checked per
   language, not across languages: Python's compensated `sum()` and `cmath.sqrt` cannot be
   matched bit for bit in Rust cheaply, and integral packings put many dot coordinates on exact
   .5 boundaries where a 1-ulp difference moves a dot.

### Output

Packing mode prints to stdout, in this order: the reduced root, the circle count, the
distinct-curvature count, `Saved to <file>`, then the drawing. The elapsed time goes to stderr.
The file is `descartes_1eK.txt` for the default root and `descartes_1eK_root_A_B_C_D.txt`
otherwise (the reduced root, ascending), one distinct curvature per line in ascending order;
a packing with no circle `≤ N` writes an empty file and draws nothing. The drawing shows
circles with curvature `≤ min(N, 2 × canvas width in braille dots)`, so its circle set depends
on terminal width, which `--help` states.

Solve mode prints a table of the three given circles and both solutions (curvature, radius,
centre), then draws all five circles. Values print at full precision by default, as the
shortest string that round-trips (Python `repr`, Rust `Display`), so pasted output passes the
tangency check; `--precision P` rounds the display to P decimal places and does not change the
computation. A rejected tangency check whose input has 6 or fewer decimal places says so and
suggests full-precision values.

Known limits, stated in `--help` and the sub-project `CLAUDE.md`: pasting solve output back
stops passing the `1e-9` tolerance at curvatures near 2.6×10⁷ (measured ratio 1.88 of the
tolerance), and nearly collinear inputs are ill-conditioned, so a triple that passes the
input check can yield solutions that do not pass when pasted back (measured: the collinear
`(-2,3,6)` triple with y perturbed by 1e-8 passes at 0.22 of the tolerance; its curvature-7
solutions fail at 7×).

### Errors

Exit 2: input that cannot describe a problem (unparsable value, wrong count, non-integer root
value, K out of range, zero curvature in `--solve`). Exit 1: well-formed input with no answer
(a root that fails the Descartes relation, a root without exactly one negative value, circles
that are not mutually tangent). Every message names the operation and the input.

### Testing

TDD per function, with boundary, error-path and state-transition cases.

- The geometric enumerator, rebuilt in the test files only, is the oracle for `pack` at
  N ≤ 1000 on five roots: the three in the table, `(-11,21,24,28)` and `(-3,5,8,8)`. The last two
  break the `d = a+b+c` shape all three table roots share, which is the shape behind the
  probe's seeding bug. The probe's own oracle counted root circles above N, which is why it
  disagreed at `(-11,21,24,28)`, N=10; the rebuilt one filters them.
- Pinned K=4 and K=5 counts check both languages beyond the oracle's range.
- Python/Rust parity lives in a Rust integration test, `descartes-rs/tests/parity.rs`, which
  runs `python3 ../descartes.py` (standard library only) beside the binary at K ≤ 5, about 2 s
  of Python at K=5, inside nextest's 45 s bound. It compares integer output (curvature file,
  count lines) byte for byte and the solve table numerically, after asserting both exit 0 and
  print a non-empty count line. Drawings are not compared across languages. cargo-mutants
  copies only the crate directory, so `../descartes.py` is absent in its copy and the
  unmutated baseline would fail; the crate's own `.cargo/mutants.toml` (per-crate, not
  rendered) therefore sets `additional_cargo_test_args = ["--lib", "--bins", "--test", "cli"]`,
  which leaves `parity.rs` out of mutation runs while `cargo test`, nextest and tarpaulin still
  run it. Measured in a throwaway crate with cargo-mutants 27.1.0: without the line the baseline
  fails (`can't open file '/tmp/cargo-mutants-…tmp/../proj.py'`); with it the baseline passes
  and plain `cargo test` still runs the parity test. `INSIDE_CARGO_MUTANTS` is not set by
  27.1.0, so an environment-variable skip does not work.
- BATS failure-mode tests cover the Python CLI. Rust failure modes are covered in
  `descartes-rs/tests/cli.rs`, because `scripts.yml` runs BATS without building any crate and
  the rendered `<crate>-rs.yml` has no BATS step.
- Coverage ≥ 90 % in both languages; `mutation-py` and `mutation-rs` hold 0 survivors on
  changed lines, which for a new crate is the whole crate.

## Requirements

- **R1.** `[PR1]` `descartes/` exists with `descartes.py`, `test_descartes.py`, `CLAUDE.md`, `README.md`, `mutants-equivalent.toml`, and a `Makefile`, `install_deps.sh`, `pyrightconfig.json` and `cosmic-ray.toml` byte-equal to `scripts/render_crate_files.py --write` output for project `descartes`, module `descartes`; `PYTHON_PROJECTS` in `scripts/render_crate_files.py` lists `descartes` and `tests/test_crate_uniformity.py` asserts 10 Python projects.
- **R2.** `[PR1]` Python `pack` returns these (circle count, distinct count) pairs: root `(-1,2,2,3)` at n = 30, 100, 1000, 10^4, 10^5: (38, 11), (168, 33), (3328, 324), (67166, 3299), (1359170, 33273); root `(-2,3,6,7)` at n = 30, 100, 1000: (14, 8), (66, 28), (1300, 297); root `(-3,4,12,13)`: (10, 6), (40, 17), (744, 200); root `(-11,21,24,28)` at n = 10, 30, 100, 1000: (0, 0), (3, 3), (9, 9), (144, 114); root `(-3,5,8,8)`: (3, 2), (10, 6), (38, 16), (785, 203).
- **R3.** `[PR1]` Python `pack((-1,2,2,3), 30)`'s distinct curvatures are exactly `2 3 6 11 14 15 18 23 26 27 30`.
- **R4.** `[PR1]` A test-only geometric enumerator, sharing no function with `descartes.py` beyond `root_centres` and counting only circles with curvature `≤ n`, agrees with `pack` on count and distinct set for every root and every n ≤ 1000 in R2.
- **R5.** `[PR1]` `validate_root` reduces `(-1,2,3,6)` and `(-1,3,6,14)` to `(-1,2,2,3)`, and packing mode given either as `--root` produces the same counts and file contents as the default root.
- **R6.** `[PR1]` Packing mode exits 1 with a message naming the root for `--root -1 2 2 4` (Descartes relation fails: `(Σk)²=49`, `2Σk²=50`) and for `--root 0 0 1 1` (not exactly one negative curvature), and exits 2 for `--root -1 2 2 x`; `--root -1 2 2 3` exits 0.
- **R7.** `[PR1]` Python accepts K 1-6 and exits 2 naming the range for K 0 and K 7; `SMOKE_SIZE` is 2 and `LARGE_RUN_THRESHOLD` is `None`.
- **R8.** `[PR1]` Packing mode writes `descartes_1eK.txt` for the default root and `descartes_1eK_root_A_B_C_D.txt` (reduced root, ascending) otherwise, one distinct curvature per line in ascending order; prints the reduced root, circle count, distinct count and `Saved to <file>` to stdout in that order; prints the elapsed time to stderr only; and for `--root -11 21 24 28` at K=1 writes an empty file, reports 0 circles and draws nothing.
- **R9.** `[PR1]` `--solve -1,0,0 2,0.5,0 3,0,0.6666666666666666` returns a curvature-2 circle centred at (-0.5, 0) and a curvature-6 circle centred at (0.5, 0.6666666666666666) within 1e-9, every returned circle is tangent to all three inputs within `1e-9 × (|r_i| + |r_j|)`, and with no `--precision` the table prints `0.6666666666666666` for the curvature-6 centre's y.
- **R10.** `[PR1]` Pasting the R9 table's printed values back into `--solve` exits 0 with the same curvatures; the R9 input scaled by 100 (curvatures -100, 200 and 300, centres divided by 100) exits 0; `--solve -1,0,0 2,0.5,0 3,0,0.6667` exits 1 naming circles 1 and 3 as not tangent and suggesting full-precision values (pairs are checked in the order 1-2, 1-3, 2-3 and the first failing pair is named); a zero curvature or an unparsable `K,X,Y` triple exits 2; `--precision 4` on the R9 input prints `0.6667` and the same curvatures.
- **R11.** `[PR1]` With drawing on and stdout not a terminal, both modes print exactly 24 lines of 60 braille cells, at least one non-blank, for the R9 input and for the default root at K=2; `--no-draw` prints no braille line; `render([], 60, 24)` returns 24 lines, each 60 blank braille cells; the packing drawing includes only circles with curvature `≤ min(N, 2 × canvas width in dots)`.
- **R12.** `[PR1]` `make test` in `descartes/` runs `scripts/cli_contract.py descartes.py` and it exits 0.
- **R13.** `[PR2]` `descartes/descartes-rs/` exists with every file `render_crate_files.py` renders for a crate byte-equal to its output, `Cargo.toml` with no `rug` and no `rayon` dependency, `CRATES` in `scripts/render_crate_files.py` listing `descartes`, and `tests/test_crate_uniformity.py` asserting and passing over 12 crates; `tests/test_mutants_exclusions.py`'s `EXPECTED` set lists `descartes-rs`, and a `mutants.toml` may omit `exclude_re` only when its single key is `additional_cargo_test_args`, so every other crate still requires a non-empty `exclude_re`, and the suite passes.
- **R14.** `[PR2]` Rust accepts K 1-8 and exits 2 naming the range for K 0 and K 9; for every input in R2, R3, R5, R6 and R8-R11 it gives the same results and exit codes as Python, each with non-empty stdout where Python's is non-empty; R11's drawing checks run against the Rust binary; the R9 command parses with the negative first triple.
- **R15.** `[PR2]` `descartes-rs/tests/parity.rs` runs both programs for the default root at K = 1-5, `--root -2 3 6 7` and `--root -11 21 24 28` at K = 1-3, and `--solve` on the R9 input; it first asserts both exit 0 and both print the circle-count line, then that output files and count lines are byte-identical and the solve tables agree numerically within 1e-12; it does not compare drawings; `descartes-rs/.cargo/mutants.toml` sets `additional_cargo_test_args = ["--lib", "--bins", "--test", "cli"]` and `cargo mutants` in `descartes-rs` passes its unmutated baseline.
- **R16.** `[PR2]` `descartes-py.yml`, `descartes-rs.yml` and `release-descartes-rs.yml` exist, rendered from the templates; `scripts/pre-commit` and `scripts/pre-push` loop over `descartes` and `descartes/descartes-rs`; the root `README.md` and `CLAUDE.md` list the project; `.gitignore` lists `descartes_1e*.txt`.
- **R17.** `[PR2]` BATS tests in `tests/scripts/` cover missing K, K out of range, non-integer K, a bad root and a non-tangent `--solve` for the Python CLI; `descartes-rs/tests/cli.rs` covers the same five cases for the Rust binary, asserting exit code and stderr.
- **V1.** On `claude`, time, peak memory and output file size of Rust packing at K = 6, 7 and 8 and Python at K = 6, recorded in the PR2 body; if Rust K=8 exceeds 10 minutes, the K ceiling is amended down before merge.
- **V2.** Python and Rust line coverage ≥ 90 % in CI, and `mutation-pr` green on both PRs.
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
Disposition: Addressed (operator): elapsed time moved to stderr; split parity (integer bytes, solve table numeric, drawings via a shared `floor(x+0.5)` rule, R15/R18); `CRATES`/`PYTHON_PROJECTS` edits named in R1/R13; file size added to V1; V2 (growth exponent) dropped; R11 now asserts a non-empty drawing; R15 asserts exit 0 and non-empty output. Solve mode kept in both languages by operator choice; the packing drawing kept as the requested "see the relationship" view, its width dependence stated in `--help`.

### Ergonomics

Finding: (1) Load-bearing: Rust clap will likely parse `--solve -1,0,0 ...` (a bounding circle first) as an unknown short flag unless the argument sets `allow_hyphen_values`; `allow_negative_numbers` does not cover `-1,0,0`. Python argparse 3.14 parses it (probed). The spec must state the parser setting. (2) R15 vs R8 elapsed time, as Goal-Fit (1). (3) Solve prints 4 places by default, but the input tangency check has no stated tolerance; pasting printed centres back (`0.6667` for 2/3) fails at 1e-9. State an input tolerance or print full precision. (4) The packing drawing's circle set changes with terminal width; say so in help. (5) R11 passes for a renderer that draws nothing; R17 Rust cases go green by skip in any job without the binary; add a non-empty-drawing check.
Assumption: byte-identical braille from float centres across languages (rounding rule, complex sqrt branch). Settle by running the R15 cases with drawing on and `cmp` after masking the time line.
Disposition: Addressed (operator): clap `allow_hyphen_values` on `--solve` (Design, R14); input tangency tolerance `5e-4 × max(|r|)` so pasted 4-place centres pass (R10); width-dependent drawing stated in `--help`; non-empty drawing check (R11); R17 binary built in `descartes-rs.yml`.

### Risk

Finding: (1) R8/R15 elapsed-time contradiction. (2) The R9 geometry is dyadic, so scaled coordinates land on exact .5 ties where Python and Rust round differently; name one rule, for example `floor(x+0.5)`, in both. (3) R9 is degenerate: for curvatures (-1,2,2) the radicand is 0 and both solutions are 3, so curvature-to-centre pairing is never tested on distinct k4; add a case such as three unit circles. (4) Vacuous passes: R15 (two empty stdouts compare equal; assert exit 0 and non-empty), R11 (never-drawing program passes), R10 (always-exit-2 program passes). (5) Otherwise proportionate: K=8 about 1.1x10^10 circles, likely 1-2 min Rust, guarded by V1; bitmap 12.5 MB; i64 safe; reduction terminates; a new crate is all changed lines, so `mutation-rs` 0 survivors covers the whole crate and tolerance comparisons will need equivalent entries. Verified every table value and both reductions with an independent DFS.
Assumption: same float byte-parity assumption; check whether any scaled R9 coordinate is an exact .5.
Disposition: Addressed (operator): elapsed time to stderr; one rounding rule `floor(x+0.5)` (R18); R9 replaced by the non-degenerate `(-1,2,3)` input giving k4 = 2 and 6 at distinct centres; vacuous passes closed (R10 adds a passing tangent case, R11 a non-empty drawing, R15 exit 0 and non-empty output).

### Adversarial Spec Review (comparison/judge designs only)

Trigger: borderline (oracle-versus-implementation comparison); run per the default-to-run rule. Finding: pinned values are correct, confirmed by an exact integer oracle sharing no code with the spec (circles as exact (k, k*z) pairs, every reflection applied, exact dedup): (-1,2,2,3) 38/11, 168/33, 3328/324 and K=4 67166/3299; every R2 value for the other two roots; the R3 set. The spec's `pack` rule also matches a float oracle on (-11,21,24,28) 144/114, (-3,5,8,8) 785/203 and (-6,10,15,19) 322/143 at N=1000. Gaps, by weight: (1) nothing checks Rust correctness above K=3; pin K=4 (67166/3299) and K=5 (1359170/33273) in both languages and compare Python and Rust at K=4-6; state the count type (K=8 overflows `u32`). (2) All three tested roots satisfy d = a+b+c, the shape that caused the probe bug; add (-11,21,24,28) or (-3,5,8,8). (3) The empty result is untested: (-11,21,24,28) at K=1 yields 0 circles (empty file, no drawing). (4) Collinear roots are a float hazard: for (-2,3,6,7) the probe put the third centre at y = sqrt(1.1e-16), about 1e-8, failing a 1e-9 tangency check; if `root_centres` routes through `solve`'s check, two of three table roots fail. Bias: the oracle shares the reduced root and `root_centres` with `pack`, so a wrong reduction is invisible to it; R5 covers only two reductions.
Assumption: byte parity at K<=3 implies Rust correct to K=8; refuted or confirmed by running Rust at K=4-6 against Python's counts.
Disposition: Addressed (operator): K=4/K=5 pinned in R2 and Python/Rust compared at K=4-6 (R15); count type `i64` stated; roots `(-11,21,24,28)` and `(-3,5,8,8)` added to R2/R4; empty result pinned (R2, R8); collinear clamp in `root_centres`, which never runs the input tangency check.

### Round 2

Reviewed at commit: `2d34195` (round-1 dispositions applied). Lenses: Goal-Fit, Ergonomics, and Risk combined with the adversarial check.

Goal-Fit finding: Design §5 omitted counting the root's own circles `≤ n`; implemented literally it returns 35/10 at `(-1,2,2,3)`, n=30, not the pinned 38/11 (the pinned values are right). Byte-identical drawings fail the reads-it test and are fragile: centres sit on rational points, and Python `cmath.sqrt` and complex division are not specified for Rust. The piped canvas width was not pinned. R15's non-empty guard is satisfied by count lines alone.
Ergonomics finding: the `5e-4 × max(|r|)` tolerance is scaled to the radius while 4-place rounding error (~5e-5) is absolute, so pasted output fails once max radius is below ~0.1 (measured at scale 10: tolerance 2.5e-5, error 2.7e-5); a curvature of 1e5 prints radius `0.0000`. Piped canvas width unspecified. `render([])` "only blank lines" passes on zero lines.
Risk finding: `floor(x+0.5)` cannot make drawings identical when inputs differ upstream: Python `sum()` is compensated (`sum([1e16,1.0,-1e16]) == 1.0` on 3.14.8) and `cmath.sqrt` differs from a Rust complex sqrt; 40 of 2,286 scaled coordinates for the default root lie within 1e-9 of a .5 tie. R15 had no home (Python K=6 ~40 s against nextest's 45 s; a Python-side test pays per mutant and lacks the binary). R17's Rust BATS cases always skip because `scripts.yml` builds no crate and the rendered `<crate>-rs.yml` has no BATS step. Adversarial: an independent breadth-first geometric search reproduced every R2 pair, including K=4/K=5, and R9 checked by hand.
Assumption (all three): Python and Rust compute bit-identical float centres; refuted in part by the compensated `sum()` measurement, so cross-language drawing parity was removed rather than tested.
Disposition: Addressed (operator, 2026-11-15): drawings checked per language only, R18 and the `floor(x+0.5)` rule removed, piped canvas fixed at 60 × 24 in both languages (R11); full-precision solve output by default with `--precision` display-only, per-pair tolerance `1e-9 × (|r_i| + |r_j|)`, scaled-by-100 and paste-back cases (R9, R10); §5 counts root circles; R15 moved to `descartes-rs/tests/parity.rs` at K ≤ 5 without drawings; Rust failure modes in `descartes-rs/tests/cli.rs`, BATS Python-only (R17); R11 pins exact line count; R14 requires non-empty Rust output and runs R11 against Rust. The round-1 dispositions above that cite `floor(x+0.5)`, R18, the `5e-4` tolerance and K=4-6 parity are superseded by this one.

### Round 3 (scoped, Risk only)

Reviewed at commit: `7471adb`. Scope: the sections round 2 changed.

Finding: `parity.rs` runs `python3 ../descartes.py`, but cargo-mutants (27.1.0, the CI pin) copies only the crate directory, so the unmutated baseline fails (`ERROR cargo test failed in an unmutated tree, so no mutants were tested`) and every mutation run on the crate would be red. Tolerance: Python `repr` round-trips of solve output pass at worst 7e-3 of the tolerance on realistic inputs (R9, R9 ×100, collinear, `(-11,21,24)`, shifted to (1e5,1e5)); paste-back fails near curvature 2.6×10⁷ (1.88×), and a near-collinear triple (y + 1e-8) yields curvature-7 solutions failing paste-back at 7×. R10 and R11 cannot pass on empty output; no R/N contradiction.
Assumption: the parity test can see `../descartes.py` from every harness that runs the crate's tests; refuted for cargo-mutants.
Disposition: Addressed (operator, 2026-11-15): `descartes-rs/.cargo/mutants.toml` excludes `parity.rs` via `additional_cargo_test_args` (verified in a throwaway crate; `INSIDE_CARGO_MUTANTS` checked and absent in 27.1.0), R15 extended; the paste-back limits are documented in Output rather than loosening the tolerance.

### Round 4 (scoped, Risk only)

Reviewed at commit: `962e1d5`. Scope: the round-3 changes.

Finding: a config-only `descartes-rs/.cargo/mutants.toml` turns `tests/test_mutants_exclusions.py` red: `test_crate_set_is_the_expected_eight` compares the glob to a hard-coded 8-crate `EXPECTED` set, `test_each_file_has_a_nonempty_exclude_re_list` requires a non-empty `exclude_re`, and `test_entries_match_listed_mutants` indexes `["exclude_re"]`. The suite runs in `make test-python` and on pre-push for `mutants.toml` changes, so PR2 could not push. No conflict with the template mutation targets, `mutation-pr-run.sh` or `mutation-testing.yml` (no test selection, no `test_tool`); `--bins` and `--test cli` resolve.
Assumption: cargo-mutants 27.1.0 honours `additional_cargo_test_args` in `--in-diff` mode. Confirmed by the orchestrator in the throwaway crate: `cargo mutants --in-diff <diff> --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle` passed its baseline, 5 of 5 caught, no parity run in any log.
Disposition: Addressed (operator, 2026-11-15): R13 names the `tests/test_mutants_exclusions.py` change; review closed and spec approved.

## Amendments

- R16 withdrawn — rendering `descartes` as a Python project in PR1 writes `descartes-py.yml`, and `render_crate_files.py --check` fails until it exists, so the registration splits by PR into R18 and R19.
- adds R18 [PR1]: `.github/workflows/descartes-py.yml` exists, rendered from the template; `descartes` appears beside `triangle` in `all_dirs` of `mutation-testing-python.yml`, `PYTHON_DIRS` of `scripts/mutation-pr-detect.sh` and `scripts/mutation-python-cell.sh`, and the `scripts/pre-commit` and `scripts/pre-push` loops; the root `README.md` and `CLAUDE.md` list the Python project; `.gitignore` lists `descartes_1e*.txt`. — split from R16 for PR1.
- adds R19 [PR2]: `.github/workflows/descartes-rs.yml` and `release-descartes-rs.yml` exist, rendered from the templates; `scripts/pre-commit` and `scripts/pre-push` loop over `descartes/descartes-rs`; the root `README.md` and `CLAUDE.md` list the crate. — split from R16 for PR2.
- adds R20 [PR1]: Python `pack` raises `BadInput` naming the ceiling for `n > N_MAX`, where `N_MAX = 10**6` (R7's K ≤ 6), so the core cannot be asked for an unbounded run whatever its caller; every test of the ceiling lowers `N_MAX` first, so a broken check fails in seconds rather than running a full packing. — added after a mutation probe on an uncapped harness ran a packing walk to 239 GB and OOM-killed the session (2026-11-15).
- adds R21 [PR1]: the Component 5 growth test `k_i < k' ≤ n` stays in `pack` even though no valid Descartes quadruple can fail it (a quadruple's only decreasing reflection is the one just made, which the search already skips); it bounds the walk when the reflection arithmetic is wrong. A test disables root validation, feeds the non-Descartes `(-1,1,1,1)` and budgets `_mark`, so removing the guard fails fast. — `c88c65e` had removed it as dead code, against Component 5.
- adds R22 [PR2]: Rust `pack` enforces the same core ceiling at `10^8` (R14's K ≤ 8). — R20 for the crate.
- adds R23 [PR1, PR2]: `descartes_fourth` raises `NoSolution` when `k1k2+k2k3+k3k1 < -1e-12 × (|k1k2|+|k2k3|+|k3k1|)` and clamps the radicand at 0 otherwise, in both languages; Python and Rust tests share the four fixtures of `test_tolerance_is_one_ppt_of_the_summed_products`, including the boundary `(2, 999999999999, -2)` that clamps. — the radicand is a sum of products, so its rounding error scales with the products, not with `max(|k|)`; one rule keeps `--solve` output identical across languages (R14).
- adds R24 [PR1, PR2]: three solve/visible details the Design leaves open. (a) Tangency uses signed radii `r = 1/k`: circles i and j pass when `| |z_i − z_j| − |r_i + r_j| | ≤ 1e-9 × (|r_i| + |r_j|)`, which is the sum of radii for two positive circles and their difference when one is the bounding circle. (b) The full-precision hint is added when any centre coordinate is a non-integer whose shortest round-trip form has 1 to 6 decimal places (`0.6667` and `0.5` yes; `0` and `0.6666666666666666` no; the hint is advice, so an exactly representable short value triggering it is harmless); integer coordinates are exact and never trigger it. (c) `solve` returns every distinct circle among the four sign combinations of the complex theorem that passes (a) against all three inputs, ordered by curvature then y; a fourth curvature of 0 is a straight line, not a circle, and is omitted, so `solve` can return one circle; a zero radicand gives one curvature with two centres (`(-1,2,2)` gives curvature 3 at y = ±2/3). (d) `visible` returns only positive-curvature circles, the same set `pack` counts, so `len(visible(root, n)) == pack(root, n)[0]`; the drawing adds the bounding circle from `root_centres`. — Python and Rust must agree on all four (R14); none is stated in Components 2 or 6.
- adds R25 [PR1, PR2]: replaces Component 4's clamp. `root_centres` computes the third circle's `x` and `y²` exactly from the integer curvatures (Python `Fraction`; Rust checked `i128` rationals, or `f64` with an equivalent proof), so a collinear root gets `y = 0` exactly; the float clamp is not enough, because float rounding on `(-2,3,6,7)` leaves `y² = +1.1e-16`, `y = 1e-8`, and the fourth circle then fails the R24(a) tangency. The third circle has `y ≥ 0` and the fourth is the candidate of curvature `d` with the larger `y`. `solve` treats a fourth curvature with `|k| ≤ 1e-9 × (|k1|+|k2|+|k3|)` as the R24(c) line, and raises `NoSolution` naming its inputs when no candidate passes. — found by Task 2; measured root placement stays valid to root curvatures of 1e18.
- adds R26 [PR1, PR2]: `solve` raises `BadInput` (exit 2) when any input value is NaN or infinite or any curvature's radius `1/k` is not finite (e.g. `5e-324`), before any tangency test; otherwise an infinite tolerance passes every pair. Circles in `solve` and `visible` are distinct when their curvatures differ by more than `1e-9 × |k|` or their centres by more than `1e-9 × |1/k|`, so the R24(c) zero-radicand pair stays two circles at any scale (the absolute tolerance merged them at scale 1e10). `solve` orders its result by curvature, then y, then x (R24(c) plus an x tiebreak, so equal-(k, y) results are deterministic in both languages). — Errors puts input that cannot describe a problem at exit 2; Task 2 review measured both defects.
- adds R27 [PR1, PR2]: CLI details the Design leaves open, fixed so Rust matches (R14, R15). Bounds: the canvas is the terminal size clamped to at least 1 × 1 and at most 1000 × 500 cells, one row short of the terminal height so the prompt stays visible, which caps the drawing limit at 4000 (measured: 20,360 circles, 6.5 MB for the default root; an unclamped `COLUMNS=100000` reached `MemoryError` at a 4 GB cap); `--precision P` accepts 0 ≤ P ≤ 17 (17 decimals round-trip any double; `P = 10^8` wrote 2.3 GB) and exits 2 otherwise. Mode flags: `--solve` with K, `--root`, `--smoke`, `--show` or `--yes` exits 2, and so does `--precision` without `--solve`. Messages: errors print `Error: <message>` to stderr; a non-integer K at the prompt names the input (`Invalid input: 'abc' is not an integer K.`, exit 2); end of input at the prompt exits 1 as in amicable. The elapsed line is `Elapsed: <seconds to 2 places>s` on stderr. The output file is opened before `pack` runs, so a path or permission error exits 1 before the computation. The solve table is a header `kind # curvature radius x y`, then `given 1-3` and `solution 1-n` rows, columns padded to align with no trailing space, values `repr` (Rust `Display`) or `P` fixed decimals, `-0` printed unsigned, radius `1/k`. — Task 4 and its review; the two bounds keep a hostile terminal or flag from exhausting memory.
- adds R28 [PR1, PR2]: `validate_root` raises `BadInput` (exit 2) when any root curvature exceeds `ROOT_MAX = 10^8` in absolute value, before the Descartes check, in both languages. — The reduction loop takes one step per reflection, and a valid root can need very many: `(-1, 2, n²+2, (n+1)²+2)` reduces to `(-1, 2, 2, 3)` in n steps, so `n = 10^12` ran about 89 hours (measured 0.32 µs per step) and argparse accepts integers up to 4300 digits (bug-scan, PR1 Phase 3). Curvatures grow at least quadratically along a reflection chain, so the cap bounds reduction at about 10^4 steps; 10^8 is also Rust's N ceiling (R22) and keeps `(Σk)²` (at most 1.6e17) inside `i64`. The cap refuses some valid quadruples that reduce to a small root; such input is not the CLI's use case.
- finding R13 (2026-11-16, reviewer both): NOT-BUILT — No descartes/descartes-rs/ files, no CRATES entry, no 12-crate assertion and no test_mutants_exclusions.py change appear in the diff (Rust crate, later PR).
- R13 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- finding R14 (2026-11-16, reviewer both): NOT-BUILT — No Rust binary or Rust tests exist in the diff (later PR).
- R14 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- finding R15 (2026-11-16, reviewer both): NOT-BUILT — No descartes-rs/tests/parity.rs or descartes-rs/.cargo/mutants.toml in the diff (later PR).
- R15 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- finding R17 (2026-11-16, reviewer A): NOT-BUILT — No BATS test in tests/scripts/ exercises the descartes Python CLI (the only bats changes are list/count updates in makefile, mutation_pr_detect, mutation_python_cell and pre_push), and there is no descartes-rs/tests/cli.rs; the five cases are covered only by unittest in test_descartes.py, which is not what R17 names.
- R17 reviewed: Python half fixed in 1063b08 (tests/scripts/descartes.bats: the five failure modes plus a K=1 run, exit code and stderr asserted separately); the descartes-rs/tests/cli.rs half is PR2.
- finding R19 (2026-11-16, reviewer both): NOT-BUILT — No descartes-rs.yml, release-descartes-rs.yml or descartes/descartes-rs hook-loop entry in the diff (later PR).
- R19 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- finding R22 (2026-11-16, reviewer both): NOT-BUILT — No Rust pack in the diff (later PR).
- R22 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- finding R23 (2026-11-16, reviewer A): NOT-BUILT — Python half is present (raise when s < -1e-12*(|k1k2|+|k2k3|+|k3k1|), clamp max(s,0), four fixtures including (2, 999999999999, -2) clamping), but the requirement says 'in both languages' and shared Python/Rust fixtures, and no Rust implementation or test exists in the diff.
- R23 reviewed: the Python half is built and tested in PR1; the Rust half and its shared fixtures are PR2, where plan Task 6 requires them.
- finding R25 (2026-11-16, reviewer A): NOT-BUILT — Python half is present (Fraction x3 and y3², fourth = larger-y candidate of curvature d, line threshold 1e-9*(|k1|+|k2|+|k3|), NoSolution naming inputs), but the requirement also specifies the Rust root_centres (checked i128 rationals or proven f64), which the diff does not contain.
- R25 reviewed: the Python half is built and tested in PR1; the Rust root_centres is PR2, bound by plan Task 8.
- finding R26 (2026-11-16, reviewer B): DIFFERS — solve's half is met (check_tangent rejects NaN/inf/zero/non-finite 1/k as BadInput for every circle before any pair; _same_circle uses 1e-9×|k| and 1e-9×|1/k|; order is (k, y, x)), but visible applies no distinctness test at all: it appends every searched circle without calling _same_circle, so the stated distinctness rule for visible has no mechanism in the code.
- R26 -> `solve` raises `BadInput` (exit 2) when any input value is NaN or infinite or any curvature's radius `1/k` is not finite (e.g. `5e-324`), before any tangency test; otherwise an infinite tolerance passes every pair. Circles returned by `solve` are distinct when their curvatures differ by more than `1e-9 × |k|` or their centres by more than `1e-9 × |1/k|` (`visible` needs no such test: every reflection of its walk is a new circle, so its output is distinct by construction), so the R24(c) zero-radicand pair stays two circles at any scale (the absolute tolerance merged them at scale 1e10). `solve` orders its result by curvature, then y, then x (R24(c) plus an x tiebreak, so equal-(k, y) results are deterministic in both languages). — visible's walk yields each circle once, so a distinctness test there would never fire; the rule applies to solve only, which is what was built and tested.
- finding R27 (2026-11-16, reviewer both): DIFFERS — R27 says errors print 'Error: <message>' to stderr, but K out of range prints 'K must be between 1 and 6, got 0.' with no 'Error:' prefix (pinned by test_out_of_range_exits_2_naming_the_range), and mode-flag clashes, --precision out of range and a bare non-TTY run go through parser.error, which prints argparse's 'usage: ... descartes.py: error: ...' form; the canvas clamp, 0-17 precision, mode-flag exits, prompt messages, Elapsed format, open-before-pack and table format all match.
- R27 -> CLI details the Design leaves open, fixed so Rust matches (R14, R15). Bounds: the canvas is the terminal size clamped to at least 1 × 1 and at most 1000 × 500 cells, one row short of the terminal height so the prompt stays visible, which caps the drawing limit at 4000 (measured: 20,360 circles, 6.5 MB for the default root; an unclamped `COLUMNS=100000` reached `MemoryError` at a 4 GB cap); `--precision P` accepts 0 ≤ P ≤ 17 (17 decimals round-trip any double; `P = 10^8` wrote 2.3 GB) and exits 2 otherwise. Mode flags: `--solve` with K, `--root`, `--smoke`, `--show` or `--yes` exits 2, and so does `--precision` without `--solve`. Messages: `BadInput`, `NoSolution` and file errors print `Error: <message>` to stderr; argparse rejections (mode flags, `--precision` range, a missing or non-integer K on the command line) print argparse's usage block and `descartes.py: error: <message>`; K out of range prints `K must be between 1 and 6, got K.` as amicable does; a non-integer K at the prompt names the input (`Invalid input: 'abc' is not an integer K.`, exit 2); end of input at the prompt exits 1 as in amicable. The elapsed line is `Elapsed: <seconds to 2 places>s` on stderr. The output file is opened before `pack` runs, so a path or permission error exits 1 before the computation. The solve table is a header `kind # curvature radius x y`, then `given 1-3` and `solution 1-n` rows, columns padded to align with no trailing space, values `repr` (Rust `Display`) or `P` fixed decimals, `-0` printed unsigned, radius `1/k`. — argparse owns its own error format and amicable's range message is kept verbatim (all sub-projects treated identically); the Error: prefix covers the errors the program raises itself.
- finding R28 (2026-11-16, reviewer A): NOT-BUILT — Python half is present (ROOT_MAX = 10**8, BadInput before the Descartes check, exit 2 via _run_packing, tested), but the requirement says 'in both languages' and no Rust validate_root exists in the diff.
- R28 reviewed: the Python half is built and tested in PR1 (ROOT_MAX, TestRootCeiling); the Rust validate_root is PR2, bound by plan Task 7.
- finding R13 (2026-11-16, reviewer both): NOT-BUILT — No descartes/descartes-rs/ files, no CRATES entry, no 12-crate assertion and no tests/test_mutants_exclusions.py change appear in the diff (Rust crate, later PR).
- R13 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- finding R14 (2026-11-16, reviewer both): NOT-BUILT — No Rust binary, K 1-8 handling or Rust tests exist in the diff (later PR).
- R14 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- finding R15 (2026-11-16, reviewer both): NOT-BUILT — No descartes-rs/tests/parity.rs or descartes-rs/.cargo/mutants.toml in the diff (later PR).
- R15 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- finding R17 (2026-11-16, reviewer both): NOT-BUILT — The Python half is present (tests/scripts/descartes.bats covers missing K, K 0/7, non-integer K, a bad root and a non-tangent --solve, asserting status and stderr), but descartes-rs/tests/cli.rs for the Rust binary is absent.
- R17 reviewed: the Python half is built (tests/scripts/descartes.bats, 1063b08); the descartes-rs/tests/cli.rs half is PR2.
- finding R19 (2026-11-16, reviewer both): NOT-BUILT — No descartes-rs.yml, release-descartes-rs.yml or descartes/descartes-rs hook-loop entry in the diff (later PR).
- R19 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- finding R22 (2026-11-16, reviewer both): NOT-BUILT — No Rust pack or 10^8 ceiling appears in the diff (later PR).
- R22 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- finding R23 (2026-11-16, reviewer both): NOT-BUILT — The Python half is present (descartes.py:55 raises NoSolution when s < -1e-12 x (|k1k2|+|k2k3|+|k3k1|), :60 clamps max(s, 0), and test_tolerance_is_one_ppt_of_the_summed_products holds the four fixtures including (2, 999999999999, -2) clamping), but the requirement says both languages share those fixtures and no Rust implementation or test exists.
- R23 reviewed: the Python half is built and tested in PR1; the Rust half and its shared fixtures are PR2 (plan Task 6).
- finding R25 (2026-11-16, reviewer both): NOT-BUILT — The Python half is present (_place_root computes x3 and y3² in Fraction, keeps y3 >= 0, picks the curvature-d candidate with the larger y; _tangent_circles skips |k| <= 1e-9 x (|k1|+|k2|+|k3|); solve raises NoSolution naming its inputs), but the requirement also specifies the Rust root_centres (checked i128 rationals or proven f64), which the diff does not contain.
- R25 reviewed: the Python half is built and tested in PR1; the Rust root_centres is PR2 (plan Task 8).
- finding R28 (2026-11-16, reviewer both): NOT-BUILT — The Python half is present (ROOT_MAX = 10**8, validate_root raises BadInput before the Descartes check, exit 2 via _run_packing, TestRootCeiling), but the requirement says both languages and no Rust validate_root exists in the diff.
- R28 reviewed: the Python half is built and tested in PR1; the Rust validate_root is PR2 (plan Task 7).
- finding R1 (2026-11-16, reviewer both): NOT-BUILT — Python-only (descartes/ files, PYTHON_PROJECTS, 10 Python projects in test_crate_uniformity): the diff touches only descartes/CLAUDE.md, README.md and one comment in descartes.py, so none of the rendered Python files or the PYTHON_PROJECTS entry is in it (per task context these are on the PR1 base).
- R1 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- finding R2 (2026-11-16, reviewer both): NOT-BUILT — Requires Python `pack` values; descartes.py and test_descartes.py are not changed except one comment, so nothing in this diff shows them (the identical Rust table is at descartes/descartes-rs/src/lib.rs:822 under R14).
- R2 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- finding R3 (2026-11-16, reviewer both): NOT-BUILT — Requires Python `pack((-1,2,2,3),30)` distinct set; no Python test or code for it is in the diff (Rust equivalent lib.rs:1075 counts under R14).
- R3 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- finding R4 (2026-11-16, reviewer A): NOT-BUILT — The test-only geometric enumerator is a Python test against descartes.py; test_descartes.py is not in the diff.
- R4 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- finding R5 (2026-11-16, reviewer B): NOT-BUILT — Python validate_root and packing mode are not in this diff; the Rust analogue (validate_reduces_to_root_a, descartes/descartes-rs/src/lib.rs:942; unreduced_root_gives_the_default_packing_and_file_name, src/main.rs:559) is covered under R14.
- R5 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- finding R6 (2026-11-16, reviewer B): NOT-BUILT — Python packing-mode exit codes for bad roots are not in this diff; Rust equivalents are assessed under R14.
- R6 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- finding R7 (2026-11-16, reviewer both): NOT-BUILT — Python K 1-6, SMOKE_SIZE and LARGE_RUN_THRESHOLD live in descartes.py, which the diff changes only in a PRECISION_MAX comment.
- R7 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- finding R8 (2026-11-16, reviewer B): NOT-BUILT — Python packing output/file naming is not in this diff; the Rust equivalent (run_packing, descartes/descartes-rs/src/main.rs:332-379) is assessed under R14.
- R8 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- finding R9 (2026-11-16, reviewer B): NOT-BUILT — Python --solve is not in this diff; Rust solve_r9_values and cli.rs:91 are assessed under R14.
- R9 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- finding R10 (2026-11-16, reviewer B): NOT-BUILT — Python --solve paste-back/scale/non-tangent/precision behaviour is not in this diff; Rust equivalents assessed under R14.
- R10 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- finding R11 (2026-11-16, reviewer B): NOT-BUILT — Python drawing behaviour is not in this diff; the Rust drawing checks (cli.rs:118, main.rs:608, main.rs:950, lib.rs render_empty_list_is_an_all_blank_grid) are assessed under R14.
- R11 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- finding R12 (2026-11-16, reviewer both): NOT-BUILT — descartes/Makefile (Python) is not in the diff, so nothing shows `make test` running scripts/cli_contract.py descartes.py.
- R12 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- finding R18 (2026-11-16, reviewer both): NOT-BUILT — Python registration (descartes-py.yml, all_dirs, PYTHON_DIRS, hook loops for `descartes`, .gitignore descartes_1e*.txt) is not added by this diff; the hooks already list `descartes` in context lines and .gitignore changes only a comment.
- R18 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- finding R20 (2026-11-16, reviewer both): NOT-BUILT — Python N_MAX = 10**6 and its lowered-ceiling tests are in descartes.py/test_descartes.py, not in the diff.
- R20 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- finding R21 (2026-11-16, reviewer B): NOT-BUILT — R21 names the Python pack guard and a Python test that budgets _mark; neither is in this diff (the Rust walk keeps an analogous guard at descartes/descartes-rs/src/lib.rs:212 with walk_terminates_when_the_root_invariant_is_broken, but that is not the Python requirement).
- R21 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- finding R25 (2026-11-16, reviewer A): DIFFERS — The requirement names `checked i128` rationals (or f64 with a proof); place_root (lib.rs:488-506) uses plain unchecked i128 multiplication justified by an overflow proof in the doc comment ("no operation can overflow, so none is checked"), so the mechanism is i128-with-proof rather than checked arithmetic; the bound itself holds (|P| ≤ 3e16, P² ≤ 9e32 ≪ i128::MAX) and every other clause (exact y=0 for collinear roots, y ≥ 0, larger-y fourth, line threshold, NoSolution naming inputs) is met.
- R25 -> replaces Component 4's clamp. `root_centres` computes the third circle's `x` and `y²` exactly from the integer curvatures (Python `Fraction`; Rust `i128` rationals with no overflow possible: under `ROOT_MAX` = 10^8, |P| ≤ 3·10^16 and P² ≤ 9·10^32, about five millionths of `i128::MAX`, a bound proved in `place_root`'s doc comment), so a collinear root gets `y = 0` exactly; the float clamp is not enough, because float rounding on `(-2,3,6,7)` leaves `y² = +1.1e-16`, `y = 1e-8`, and the fourth circle then fails the R24(a) tangency. The third circle has `y ≥ 0` and the fourth is the candidate of curvature `d` with the larger `y`. `solve` treats a fourth curvature with `|k| ≤ 1e-9 × (|k1|+|k2|+|k3|)` as the R24(c) line, and raises `NoSolution` naming its inputs when no candidate passes. — the bound makes every i128 product in place_root provably in range, so checked arithmetic would add only an unreachable error path; the reviewer confirmed the proof (|P| ≤ 3e16).
- finding R27 (2026-11-16, reviewer A): DIFFERS — Usage rejections in Rust print clap's format (`error: <message>` then `Usage: descartes [OPTIONS] [K]`, main.rs:396 and tests main.rs:722) instead of the argparse usage block and `descartes.py: error: <message>` the requirement fixes for Rust to match; descartes-rs/CLAUDE.md:62 records this as a known difference, but R27 carves out only Display-vs-repr for values, not the usage format; all other R27 clauses (canvas clamp 1..1000 x 1..500 one row short, precision 0-17, mode-flag exits, Error: prefix, prompt messages, EOF exit 1, Elapsed format, open-before-pack, table layout, unsigned -0) match.
- R27 -> CLI details the Design leaves open, fixed so Rust matches (R14, R15). Bounds: the canvas is the terminal size clamped to at least 1 × 1 and at most 1000 × 500 cells, one row short of the terminal height so the prompt stays visible, which caps the drawing limit at 4000 (measured: 20,360 circles, 6.5 MB for the default root; an unclamped `COLUMNS=100000` reached `MemoryError` at a 4 GB cap); `--precision P` accepts 0 ≤ P ≤ 17 (17 significant digits round-trip any double; `P = 10^8` wrote 2.3 GB) and exits 2 otherwise. Mode flags: `--solve` with K, `--root`, `--smoke`, `--show` or `--yes` exits 2, and so does `--precision` without `--solve`. Messages: `BadInput`, `NoSolution` and file errors print `Error: <message>` to stderr; argparse rejections (mode flags, `--precision` range, a missing or non-integer K on the command line) print argparse's usage block and `descartes.py: error: <message>` (Rust: clap's `error: <message>` then its `Usage: descartes [OPTIONS] [K]` line, same exit 2); K out of range prints `K must be between 1 and 6, got K.` (Rust: `between 1 and 8`, R22) as amicable does; a non-integer K at the prompt names the input (`Invalid input: 'abc' is not an integer K.`, exit 2); end of input at the prompt exits 1 as in amicable. The elapsed line is `Elapsed: <seconds to 2 places>s` on stderr. The output file is opened before `pack` runs, so a path or permission error exits 1 before the computation. The solve table is a header `kind # curvature radius x y`, then `given 1-3` and `solution 1-n` rows, columns padded to align with no trailing space, values `repr` (Rust `Display`) or `P` fixed decimals, `-0` printed unsigned, radius `1/k`. — clap owns its usage format as argparse owns its own (crate CLAUDE.md lists the difference; exit codes match, parity tests compare them); Rust's K range is 1-8 by R22; the round-trip claim is about significant digits, as the corrected comments say.
- R27 -> CLI details the Design leaves open, fixed so Rust matches (R14, R15). Bounds: the canvas is the terminal size clamped to at least 1 × 1 and at most 1000 × 500 cells, one row short of the terminal height so the prompt stays visible, which caps the drawing limit at 4000 (measured: 20,360 circles, 6.5 MB for the default root; an unclamped `COLUMNS=100000` reached `MemoryError` at a 4 GB cap); `--precision P` accepts 0 ≤ P ≤ 17 (17 significant digits round-trip any double; `P = 10^8` wrote 2.3 GB) and exits 2 otherwise. Mode flags: `--solve` with K, `--root`, `--smoke`, `--show` or `--yes` exits 2, and so does `--precision` without `--solve`. Messages: `BadInput`, `NoSolution` and file errors print `Error: <message>` to stderr; argparse rejections (mode flags, `--precision` range, a missing or non-integer K on the command line) print argparse's usage block and `descartes.py: error: <message>` (Rust: clap's `error: <message>` then its `Usage: descartes [OPTIONS] [K]` line, same exit 2); K out of range prints `K must be between 1 and 6, got K.` (Rust: `between 1 and 8`, R22) as amicable does; a non-integer or out-of-range K at the prompt prints its message and prompts again; end of input at the prompt exits 1 as in amicable. The elapsed line is `Elapsed: <seconds to 2 places>s` on stderr. The output file is opened before `pack` runs, so a path or permission error exits 1 before the computation. The solve table is a header `kind # curvature radius x y`, then `given 1-3` and `solution 1-n` rows, columns padded to align with no trailing space, values `repr` (Rust `Display`) or `P` fixed decimals, `-0` printed unsigned, radius `1/k`. — clap owns its usage format as argparse owns its own (crate CLAUDE.md lists the difference; exit codes match, parity tests compare them); Rust's K range is 1-8 by R22; the round-trip claim is about significant digits, as the corrected comments say. — re-prompting adopted by docs/superpowers/specs/2026-11-17-svg-output-and-prompt-reprompt-design.md R1-R2.

## Spec alignment (2026-11-16)

- spec: docs/superpowers/specs/2026-11-15-descartes-design.md
- anchor: fbe2bcdf9d068c8ee32a34ab2fe155cb68aeb51c
- in scope: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13, R14, R15, R17, R18, R19, R20, R21, R22, R23, R24, R25, R26, R27, R28
- out of scope: none

### Findings

| ID | Reviewer | Verdict | Reason | Amendment |
| --- | --- | --- | --- | --- |
| R1 | both | NOT-BUILT | Python-only (descartes/ files, PYTHON_PROJECTS, 10 Python projects in test_crate_uniformity): the diff touches only descartes/CLAUDE.md, README.md and one comment in descartes.py, so none of the rendered Python files or the PYTHON_PROJECTS entry is in it (per task context these are on the PR1 base). | - R1 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge. |
| R2 | both | NOT-BUILT | Requires Python `pack` values; descartes.py and test_descartes.py are not changed except one comment, so nothing in this diff shows them (the identical Rust table is at descartes/descartes-rs/src/lib.rs:822 under R14). | - R2 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge. |
| R3 | both | NOT-BUILT | Requires Python `pack((-1,2,2,3),30)` distinct set; no Python test or code for it is in the diff (Rust equivalent lib.rs:1075 counts under R14). | - R3 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge. |
| R4 | A | NOT-BUILT | The test-only geometric enumerator is a Python test against descartes.py; test_descartes.py is not in the diff. | - R4 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge. |
| R5 | B | NOT-BUILT | Python validate_root and packing mode are not in this diff; the Rust analogue (validate_reduces_to_root_a, descartes/descartes-rs/src/lib.rs:942; unreduced_root_gives_the_default_packing_and_file_name, src/main.rs:559) is covered under R14. | - R5 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge. |
| R6 | B | NOT-BUILT | Python packing-mode exit codes for bad roots are not in this diff; Rust equivalents are assessed under R14. | - R6 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge. |
| R7 | both | NOT-BUILT | Python K 1-6, SMOKE_SIZE and LARGE_RUN_THRESHOLD live in descartes.py, which the diff changes only in a PRECISION_MAX comment. | - R7 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge. |
| R8 | B | NOT-BUILT | Python packing output/file naming is not in this diff; the Rust equivalent (run_packing, descartes/descartes-rs/src/main.rs:332-379) is assessed under R14. | - R8 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge. |
| R9 | B | NOT-BUILT | Python --solve is not in this diff; Rust solve_r9_values and cli.rs:91 are assessed under R14. | - R9 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge. |
| R10 | B | NOT-BUILT | Python --solve paste-back/scale/non-tangent/precision behaviour is not in this diff; Rust equivalents assessed under R14. | - R10 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge. |
| R11 | B | NOT-BUILT | Python drawing behaviour is not in this diff; the Rust drawing checks (cli.rs:118, main.rs:608, main.rs:950, lib.rs render_empty_list_is_an_all_blank_grid) are assessed under R14. | - R11 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge. |
| R12 | both | NOT-BUILT | descartes/Makefile (Python) is not in the diff, so nothing shows `make test` running scripts/cli_contract.py descartes.py. | - R12 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge. |
| R18 | both | NOT-BUILT | Python registration (descartes-py.yml, all_dirs, PYTHON_DIRS, hook loops for `descartes`, .gitignore descartes_1e*.txt) is not added by this diff; the hooks already list `descartes` in context lines and .gitignore changes only a comment. | - R18 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge. |
| R20 | both | NOT-BUILT | Python N_MAX = 10**6 and its lowered-ceiling tests are in descartes.py/test_descartes.py, not in the diff. | - R20 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge. |
| R21 | B | NOT-BUILT | R21 names the Python pack guard and a Python test that budgets _mark; neither is in this diff (the Rust walk keeps an analogous guard at descartes/descartes-rs/src/lib.rs:212 with walk_terminates_when_the_root_invariant_is_broken, but that is not the Python requirement). | - R21 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge. |
| R25 | A | DIFFERS | The requirement names `checked i128` rationals (or f64 with a proof); place_root (lib.rs:488-506) uses plain unchecked i128 multiplication justified by an overflow proof in the doc comment ("no operation can overflow, so none is checked"), so the mechanism is i128-with-proof rather than checked arithmetic; the bound itself holds (\|P\| ≤ 3e16, P² ≤ 9e32 ≪ i128::MAX) and every other clause (exact y=0 for collinear roots, y ≥ 0, larger-y fourth, line threshold, NoSolution naming inputs) is met. | - R25 -> replaces Component 4's clamp. `root_centres` computes the third circle's `x` and `y²` exactly from the integer curvatures (Python `Fraction`; Rust `i128` rationals with no overflow possible: under `ROOT_MAX` = 10^8, \|P\| ≤ 3·10^16 and P² ≤ 9·10^32, about five millionths of `i128::MAX`, a bound proved in `place_root`'s doc comment), so a collinear root gets `y = 0` exactly; the float clamp is not enough, because float rounding on `(-2,3,6,7)` leaves `y² = +1.1e-16`, `y = 1e-8`, and the fourth circle then fails the R24(a) tangency. The third circle has `y ≥ 0` and the fourth is the candidate of curvature `d` with the larger `y`. `solve` treats a fourth curvature with `\|k\| ≤ 1e-9 × (\|k1\|+\|k2\|+\|k3\|)` as the R24(c) line, and raises `NoSolution` naming its inputs when no candidate passes. — the bound makes every i128 product in place_root provably in range, so checked arithmetic would add only an unreachable error path; the reviewer confirmed the proof (\|P\| ≤ 3e16). |
| R27 | A | DIFFERS | Usage rejections in Rust print clap's format (`error: <message>` then `Usage: descartes [OPTIONS] [K]`, main.rs:396 and tests main.rs:722) instead of the argparse usage block and `descartes.py: error: <message>` the requirement fixes for Rust to match; descartes-rs/CLAUDE.md:62 records this as a known difference, but R27 carves out only Display-vs-repr for values, not the usage format; all other R27 clauses (canvas clamp 1..1000 x 1..500 one row short, precision 0-17, mode-flag exits, Error: prefix, prompt messages, EOF exit 1, Elapsed format, open-before-pack, table layout, unsigned -0) match. | - R27 -> CLI details the Design leaves open, fixed so Rust matches (R14, R15). Bounds: the canvas is the terminal size clamped to at least 1 × 1 and at most 1000 × 500 cells, one row short of the terminal height so the prompt stays visible, which caps the drawing limit at 4000 (measured: 20,360 circles, 6.5 MB for the default root; an unclamped `COLUMNS=100000` reached `MemoryError` at a 4 GB cap); `--precision P` accepts 0 ≤ P ≤ 17 (17 significant digits round-trip any double; `P = 10^8` wrote 2.3 GB) and exits 2 otherwise. Mode flags: `--solve` with K, `--root`, `--smoke`, `--show` or `--yes` exits 2, and so does `--precision` without `--solve`. Messages: `BadInput`, `NoSolution` and file errors print `Error: <message>` to stderr; argparse rejections (mode flags, `--precision` range, a missing or non-integer K on the command line) print argparse's usage block and `descartes.py: error: <message>` (Rust: clap's `error: <message>` then its `Usage: descartes [OPTIONS] [K]` line, same exit 2); K out of range prints `K must be between 1 and 6, got K.` (Rust: `between 1 and 8`, R22) as amicable does; a non-integer K at the prompt names the input (`Invalid input: 'abc' is not an integer K.`, exit 2); end of input at the prompt exits 1 as in amicable. The elapsed line is `Elapsed: <seconds to 2 places>s` on stderr. The output file is opened before `pack` runs, so a path or permission error exits 1 before the computation. The solve table is a header `kind # curvature radius x y`, then `given 1-3` and `solution 1-n` rows, columns padded to align with no trailing space, values `repr` (Rust `Display`) or `P` fixed decimals, `-0` printed unsigned, radius `1/k`. — clap owns its usage format as argparse owns its own (crate CLAUDE.md lists the difference; exit codes match, parity tests compare them); Rust's K range is 1-8 by R22; the round-trip claim is about significant digits, as the corrected comments say. |

### Reviewed

- R13 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- R14 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- R15 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- R17 reviewed: Python half fixed in 1063b08 (tests/scripts/descartes.bats: the five failure modes plus a K=1 run, exit code and stderr asserted separately); the descartes-rs/tests/cli.rs half is PR2.
- R19 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- R22 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- R23 reviewed: the Python half is built and tested in PR1; the Rust half and its shared fixtures are PR2, where plan Task 6 requires them.
- R25 reviewed: the Python half is built and tested in PR1; the Rust root_centres is PR2, bound by plan Task 8.
- R28 reviewed: the Python half is built and tested in PR1 (ROOT_MAX, TestRootCeiling); the Rust validate_root is PR2, bound by plan Task 7.
- R13 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- R14 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- R15 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- R17 reviewed: the Python half is built (tests/scripts/descartes.bats, 1063b08); the descartes-rs/tests/cli.rs half is PR2.
- R19 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- R22 reviewed: [PR2] item; the Rust crate is PR2 (plan Tasks 6-11) and this branch is PR1.
- R23 reviewed: the Python half is built and tested in PR1; the Rust half and its shared fixtures are PR2 (plan Task 6).
- R25 reviewed: the Python half is built and tested in PR1; the Rust root_centres is PR2 (plan Task 8).
- R28 reviewed: the Python half is built and tested in PR1; the Rust validate_root is PR2 (plan Task 7).
- R1 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- R2 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- R3 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- R4 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- R5 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- R6 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- R7 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- R8 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- R9 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- R10 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- R11 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- R12 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- R18 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- R20 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.
- R21 reviewed: Python-side requirement delivered and tested by PR1 (math#224, 39ab225) and present on the base; this diff (PR2, the Rust crate) touches descartes.py by one comment line only, so the reviewer had no Python code to judge.

### Verifications

- V1: no evidence recorded
- V2: no evidence recorded
