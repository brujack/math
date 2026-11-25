# zeta: public results page

- **Date:** 2026-11-24
- **Sub-project:** `zeta/` (results page only; the `zeta` CLI is unchanged)
- **Origin:** operator approval of 2026-11-23 for a published page of zeta's verified
  results, built after the V3–V7 runs of `2026-11-23-zeta-rh-verification-design.md`;
  operator choices of 2026-11-24: GitHub Pages, matplotlib.

## Summary

A static page at `https://brujack.github.io/math/zeta/` shows what `zeta` computed:

1. **Verified counts** for N = 2–7 next to the published zero counts N(10^N).
2. **Normalised gap histograms** between consecutive refined zeros. Each is drawn against the
   Wigner surmise, the small-matrix approximation to GUE. A Poisson curve sits on the same axes
   for contrast: uncorrelated points would follow it, so its failure shows level repulsion.
3. **Gram block density** for each height range: Gram blocks per Gram interval.
4. **The run table**: elapsed time, peak memory, binary commit and date for every run behind
   a figure.

A Python script in the repo builds every number and figure from the real `zeta` output
files. Nothing is typed by hand. The page claims what the program did: certified
re-verification of a range already verified much further by others. It never claims a new
result.

## Why

The operator teaches mathematics and wants a page for viewing and teaching, built on the
program's own output: GUE statistics, how repulsion differs from Poisson, and how Gram's law
wears down with height. The spec's V3–V7 runs (recorded in the zeta plan, 2026-11-24) already
produced the data. This spec turns it into a page whose every figure can be traced to a
command and a commit.

## Facts this design rests on (measured 2026-11-24)

- **Pages already serves this repo.** `gh api repos/brujack/math/pages` reports
  `build_type: legacy` and `source: gh-pages /`, with `html_url` `https://brujack.github.io/math/`.
  The only writer is `.github/workflows/benchmarks.yml`
  (`benchmark-action`, `auto-push: true`, `benchmark-data-dir-path: dev/bench`). It is
  triggered by `workflow_dispatch` and `schedule`, with `permissions: contents: write`.
  `origin/gh-pages` holds `README.md` and `dev/bench/` only.
- **The raw tables cannot be committed.** `zeta_1e7.txt` is 1,531,826,030 bytes and
  `zeta_1e6.txt` is 124,683,416 bytes. The page must be generated where the run outputs live,
  on the operator's machine, and the generated site committed.
- **Plain brackets cannot feed a gap histogram.** Plain `zeta 4` brackets are up to 8.18
  wide (plan V7), while the mean gap near 10^7 is 2π/ln(10^7/2π) ≈ 0.44. `--refine` brackets
  are at most 3.89e-3 wide (N = 3, 4, 5). The histogram uses refined `t_n` only.
- **`--refine` cost.** `zeta 5 --refine` took 124.9 s (verification alone 6.6 s), with
  41,344 kB peak RSS. N = 6 and N = 7 `--refine` were unmeasured when this was written.
- **What the printed Gram block count covers.** `RunStats.gram_blocks` is `planned.len()`
  (`verify.rs`, `verify`): the Brent blocks planned over [g₋₁, g_M]. M is Turing's index, not
  the range ≤ T. For N = 2, g_M ≥ 168π, so `zeta 2` prints 283 blocks but 29 zeros. The CLI
  prints g_M (`Turing bound: N(g_M) <= M+1 established at g_M = <value>`) but not M.
- **Measured counts (binary f935b23, 48 threads):**

  | N   | zeros      | Gram blocks            | g_M printed       |
  | --- | ---------- | ---------------------- | ----------------- |
  | 2 | 29 | 283 | 529.115032 |
  | 3 | 649 | 627 | 1000.475576 |
  | 4 | 10,142 | 9,303 | 10000.881777 |
  | 5   | 138,069    | 122,381                | 100000.286772     |
  | 6   | 1,747,146  | 1,512,390              | 1000000.257760    |
  | 7   | 21,136,125 | 17,946,632             | 10000000.349478   |

- **M from g_M works on the real runs.** With the θ formula of the Design section, θ(g_M)/π
  is 138068.00000000972 (N = 5), 1747144.9999998996 (N = 6) and 21136125.00000043 (N = 7).
  So M + 1 is 138069, 1747146 and 21136126. At N = 7, M + 1 exceeds L by one: one zero lies in
  (10^7, g_M].
- **Published counts.** N(10^N) for N = 2–7 is 29, 649, 10142, 138069, 1747146, 21136125
  (OEIS A072080; Odlyzko's tables). The `zeta` counts equal them.
- **matplotlib wheels exist for both interpreters.** In the repo venv (Python 3.15.2),
  `pip install --dry-run --only-binary=:all: matplotlib==3.11.2` resolves:
  contourpy 1.4.0, cycler 0.12.1, fonttools 4.68.0, kiwisolver 1.5.1, numpy 2.5.5,
  packaging 26.4, pillow 13.0.0, pyparsing 3.3.3, python-dateutil 4.0.0, tzdata 2026.6.
  CI's `scripts.yml` runs Python 3.14 (not measured here, see V3).

## Approach

**Chosen: a local generator plus a dispatch-only deploy workflow.**

- `scripts/zeta_results.py` reads the run directories named on its command line, plus the
  committed provenance file `zeta/results/runs.toml`. It writes `zeta/results/site/`:
  `index.html`, one SVG per figure, and `data.json`.
- The operator runs the script after a measurement run and commits `zeta/results/` through a
  normal PR.
- `.github/workflows/zeta-results-pages.yml` (`workflow_dispatch` only, master only) copies
  `zeta/results/site/` into `gh-pages` under `zeta/` and pushes.

**Rejected:**

- **Generate in CI.** CI cannot hold or produce the 1.5 GB tables or the multi-hour runs.
- **Pages from `master /docs`.** This changes the Pages source away from `gh-pages`, which
  would break the benchmark page. It would also publish every spec and plan under `docs/`
  through Jekyll.
- **Pages deploy on every push to master.** The repo's workflows trigger on `pull_request`
  only, plus manual `workflow_dispatch` for releases and benchmarks. A publish is an
  outward-facing act, so the operator triggers it, as with a release.
- **Static SVG drawn by a stdlib script, or a client-side JS chart library.** The operator
  chose matplotlib, the mathematics standard (2026-11-24).

## Design

### Inputs

`zeta/results/runs.toml` holds one `[[run]]` table per run:

- `id`: the run directory's name as given on the command line (for example `n7`, `r6`);
- `n`, and `refine` (bool);
- `binary_sha`: the 40-hex commit of the `zeta` binary;
- `command`: the exact command, for example `zeta 6 --refine`;
- `machine`: a public label, for example `Threadripper 3960X, 48 threads, Ubuntu 26.04`;
- `date`: an ISO date;
- `elapsed_s` and `peak_rss_kb`: from `/usr/bin/time -v`.

Local paths never appear in it. The script takes run directories as `--run <id>=<dir>`.
Each directory holds the `out.txt` (stdout) and the `zeta_1eN.txt` of one run.

### Parsing and checks (fail closed)

For each `--run`:

- `out.txt` must contain `RH verified: all <L> nontrivial zeros with 0 < Im s <= <T> ...`
  with T = 10^n. It must also contain the `Gram blocks: <B>` and
  `Turing bound: ... at g_M = <g>` lines.
- The table must start with `# n a b` (plain) or `# n a b t_n w_n` (refined, required when
  `refine = true`). It must hold exactly L data lines numbered 1..L.
- Every number must be finite.
- M is computed as `round(θ(g_M)/π)`, where θ uses the Riemann–Siegel asymptotic
  θ(t) = (t/2)·ln(t/2π) − t/2 − π/8 + 1/(48t) + 7/(5760t³). The value must lie within 0.01 of
  an integer. At g_M ≥ 100 the truncation error is below 10⁻⁸, and the printed six decimals
  of g_M move θ by at most 5·10⁻⁷·½·ln(g_M/2π) < 10⁻⁵.

Any failure exits 1 with one line naming the run and the check. The site is not written.

### Computations

- **Counts table:** L per plain run, the published value from a constant in the script
  (citing OEIS A072080), and "equal" or "differs".
- **Gap histogram** per refined run:
  - normalised gaps δ_n = (t_{n+1} − t_n)·ln(t_n/2π)/2π over all consecutive pairs, using the
    table's `t_n` column;
  - density histogram on [0, 3] with 60 bins;
  - curves: Wigner surmise p(s) = (32/π²)·s²·exp(−4s²/π), and Poisson exp(−s);
  - KS distance of the δ_n sample to the Wigner CDF 1 − exp(−4s²/π), shown on the panel.

  The CLI computes the same KS for its `KS distance to the Wigner surmise CDF:` line. The
  script must agree with it to the 4 printed decimals, a cross-check that the computation ran.

- **Gram block density:** B/(M+1) for each plain run over [g₋₁, g_M]. For consecutive
  plain runs it is also (B_k − B_j)/(M_k − M_j) over (g_{M_j}, g_{M_k}]. The page labels it
  "Gram blocks per Gram interval". It is 1 where Gram's law holds everywhere and falls as
  longer blocks appear.
  - It is not the share of Gram intervals with exactly one zero, and the page says so.
  - An unusable Gram point merges two blocks, so B can undercount by the number of such points.
    The page states this.

### Output

- `zeta/results/site/index.html` is static HTML with no JavaScript and no external requests.
  It holds:
  - the claim paragraph;
  - the counts table;
  - the figures as `<img>` of local SVGs;
  - the run table;
  - under every figure, a provenance line: binary commit, command, machine and date of each
    run it uses.
- The SVGs are written by matplotlib with `metadata={"Date": None}` and
  `rcParams["svg.hashsalt"]` fixed, so two runs over the same inputs are byte-identical.
- `data.json` holds every plotted number: bins, densities, curve samples, KS, counts and
  densities.
- The script writes into a temporary directory beside `site/`, then replaces `site/` with it,
  so a failed run leaves the previous site intact.

### Claim text (exact)

> `zeta` re-verified, with certified interval arithmetic, that every nontrivial zero of ζ(s)
> with 0 < Im s ≤ 10^N lies on the critical line and is simple, for each N shown. This is an
> independent re-computation of a known result, not a new one. Platt and Trudgian (2021)
> verified the same property up to 3·10^12, and Odlyzko's tables give the zeros themselves.

### Deploy workflow

`.github/workflows/zeta-results-pages.yml`:

- trigger: `workflow_dispatch` only;
- job condition: `if: github.ref == 'refs/heads/master'`;
- `permissions: contents: write`;
- every `uses:` pinned to a 40-hex SHA;
- steps: check out master, check out `gh-pages` into a separate path, then replace
  `gh-pages/zeta/` with `zeta/results/site/`. Nothing outside `zeta/` is touched.
- It commits and pushes only when `git status --porcelain` is non-empty.

### Dependencies

`matplotlib==3.11.2` is added to `requirements-dev.txt`, the one root-scope install site, which
`scripts.yml` installs. `tests/test_tool_pins.py` then sees one version. No other workflow
installs it.

### Testing

`tests/test_zeta_results.py` (unittest, under `make test-python`):

- **Fixtures:** the real N = 2 and N = 3 outputs, plain and `--refine` (`out.txt` plus table;
  the N = 3 refined table is 60,344 bytes), under `tests/fixtures/zeta_results/`, with a
  `runs.toml` for them.
- **Value pins:**
  - the N = 3 refined KS equals the fixture's printed 0.0448 to 4 decimals;
  - the N = 3 counts row reads 649 and "equal";
  - M from the N = 3 g_M is an integer that matches the B/(M+1) printed in `data.json`.
- **Fail-closed paths**, each exiting 1 with the run named:
  - a missing verified line;
  - a row count differing from L;
  - a refined run whose table header is plain;
  - a NaN;
  - an unknown `--run` id;
  - θ(g_M)/π off-integer.
- **Atomic write:** a failure leaves a pre-existing `site/` unchanged.
- **Determinism:** two generations over the fixtures give byte-identical `site/`.
- **No-JS and no-external:** `index.html` contains no `<script` and no `http` in `src`
  attributes.

A bats test for the workflow file is not needed. `tests/test_workflow_actions_pinned.py`
already covers SHA pins, and the workflow has no logic beyond copy-and-push.

## Requirements

- **R1.** `scripts/zeta_results.py --runs-toml <file> --run <id>=<dir> ... --out <dir>` writes `<dir>/index.html`, one `.svg` per figure and `<dir>/data.json`, and exits 0.
- **R2.** `zeta/results/runs.toml` lists one `[[run]]` per run with keys `id`, `n`, `refine`, `binary_sha` (40 hex), `command`, `machine`, `date`, `elapsed_s` and `peak_rss_kb`, and contains no filesystem path.
- **R3.** The script exits 1, prints one line naming the run id and the failed check, and leaves any existing output directory byte-unchanged in each of these cases: `out.txt` without the `RH verified: all <L> nontrivial zeros with 0 < Im s <= <10^n>` line; a table whose data-line count differs from L; `refine = true` with a table header other than `# n a b t_n w_n`; a non-finite number; a `--run` id absent from `runs.toml`; θ(g_M)/π more than 0.01 from an integer.
- **R4.** Normalised gaps are δ_n = (t_{n+1} − t_n)·ln(t_n/2π)/2π from the `t_n` column of refined runs only, histogrammed as a density on [0, 3] with 60 bins, and each histogram panel draws the Wigner surmise (32/π²)·s²·exp(−4s²/π) and Poisson exp(−s) and shows the KS distance to 1 − exp(−4s²/π).
- **R5.** For the N = 3 `--refine` fixture the script's KS distance rounds to 0.0448 at 4 decimals, equal to the CLI's printed value.
- **R6.** The counts table shows, for every plain run, the verified count L, the published N(10^n) from a constant citing OEIS A072080 (29, 649, 10142, 138069, 1747146, 21136125 for n = 2–7) and the word `equal` or `differs`.
- **R7.** Gram block density is B/(M+1) per plain run and (B_k − B_j)/(M_k − M_j) between consecutive plain runs, with M = round(θ(g_M)/π), θ(t) = (t/2)·ln(t/2π) − t/2 − π/8 + 1/(48t) + 7/(5760t³), and the page labels it "Gram blocks per Gram interval" and states that it is not the share of Gram intervals with exactly one zero.
- **R8.** `index.html` contains no `<script` element and no `src` or `href` beginning with `http`, and shows under every figure the binary commit, command, machine and date of each run the figure uses.
- **R9.** `index.html` contains the claim paragraph of the section "Claim text (exact)" verbatim, and no sentence calling the result new.
- **R10.** Two runs of the script over the same inputs produce byte-identical output directories.
- **R11.** `.github/workflows/zeta-results-pages.yml` triggers on `workflow_dispatch` only, runs only when `github.ref == 'refs/heads/master'`, has `permissions: contents: write`, pins every `uses:` to a 40-hex SHA, replaces only `zeta/` on `gh-pages` with `zeta/results/site/`, and pushes only when the working tree changed.
- **R12.** `requirements-dev.txt` pins `matplotlib==3.11.2`, and no other file installs matplotlib.
- **R13.** `tests/test_zeta_results.py` covers R3's six failure cases, R5, R10, R8's no-script check, and the N = 3 counts row reading 649 `equal`, with real N = 2 and N = 3 outputs as fixtures under `tests/fixtures/zeta_results/`.
- **R14.** `zeta/results/site/` is committed holding the page generated from the real runs of binary f935b23: plain N = 2–7, and `--refine` N = 3, 5, 6, plus N = 7 if that run exists.
- **V1.** After the deploy workflow is dispatched, `https://brujack.github.io/math/zeta/` serves the page, and `https://brujack.github.io/math/dev/bench/` still serves the benchmark page.
- **V2.** On the real runs, the script's KS for N = 5 equals the CLI's 0.0184, and every counts row reads `equal`.
- **V3.** `pip install -r requirements-dev.txt` succeeds on CI's Python 3.14 (`scripts.yml` job log) and on the local 3.15 venv.
- **V4.** Record the `zeta 6 --refine` (and, if run, `zeta 7 --refine`) elapsed time and peak RSS in `runs.toml`. This closes the Backlog row "zeta --refine at N = 7 cost unmeasured" when N = 7 is run.
- **N1.** No change to `zeta/zeta-rs/` or to any crate template.
- **N2.** No JavaScript, web font or third-party request on the page.
- **N3.** No run output table (`zeta_1eN.txt`) is committed, apart from the N = 2 and N = 3 test fixtures.
- **N4.** The deploy workflow never deletes or rewrites anything on `gh-pages` outside `zeta/`.
- **N5.** No change to the Pages source setting (stays `gh-pages /`, legacy build).
