# zeta: public results page

- **Date:** 2026-11-24
- **Sub-project:** `zeta/` (results page only; the `zeta` CLI is unchanged)
- **Origin:** operator approval of 2026-11-23 for a published page of zeta's verified
  results, built after the V3–V7 runs of `2026-11-23-zeta-rh-verification-design.md`;
  operator choices of 2026-11-24: GitHub Pages, matplotlib.
- **Revised:** 2026-11-24, after Multi-Lens Review round 1 (operator dispositions below)

## Summary

A static page at `https://brujack.github.io/math/zeta/` shows what `zeta` computed:

1. **Verified counts** for N = 2–7 next to the published zero counts N(10^N).
2. **Normalised gap histograms** between consecutive refined zeros, one figure per refined N.
   - Each is drawn against the Wigner surmise, the small-matrix approximation to GUE.
   - A Poisson curve sits on the same axes for contrast: uncorrelated points would follow it,
     so its failure shows level repulsion.
   - Each figure gives its KS distance to both curves.
3. **Gram's law**: for each refined N, the share of Gram intervals holding exactly one zero, and
   how many hold 0, 1, 2 and 3 zeros. The share falls with height.
4. **The run table**: elapsed time, peak memory, binary commit and date for every run behind a
   figure.

A Python script in the repo builds every number and figure from the real `zeta` output files.
It cross-checks itself against the numbers the CLI printed, and refuses to write the page if
they disagree. The page claims what the program did: certified re-verification of a range
already verified much further by others. It never claims a new result.

## Why

The operator teaches mathematics and wants a page for viewing and teaching, built on the
program's own output:

- GUE statistics and how repulsion differs from Poisson;
- how Gram's law wears down with height.

The spec's V3–V7 runs (recorded in the zeta plan, 2026-11-24) already produced most of the data.
This spec turns it into a page whose every figure traces to a command and a commit.

## Facts this design rests on (measured 2026-11-24)

- **Pages already serves this repo.** `gh api repos/brujack/math/pages` reports
  `build_type: legacy`, `source: gh-pages /` and `html_url` `https://brujack.github.io/math/`.
  - The only writer is `.github/workflows/benchmarks.yml` (`benchmark-action`,
    `auto-push: true`, `benchmark-data-dir-path: dev/bench`).
  - That workflow is triggered by `workflow_dispatch` and a monthly `schedule`
    (`0 2 1 * *`), with `permissions: contents: write`.
  - `origin/gh-pages` holds `README.md` and `dev/bench/` only.
  - Pages builds do fire on `GITHUB_TOKEN` pushes: `pages/builds` shows
    `built github-actions[bot]` on 09-01, 10-01 and 11-01 (Risk lens).
- **The raw tables cannot be committed.** `zeta_1e7.txt` is 1,531,826,030 bytes. The page is
  generated where the run outputs live, on the operator's machine, and the generated site is
  committed.
- **Plain brackets cannot feed a gap histogram or Gram counts.**
  - Plain `zeta 4` brackets are up to 8.18 wide (plan V7), while the mean gap near 10^7 is
    2π/ln(10^7/2π) ≈ 0.44.
  - `--refine` brackets are at most 3.89e-3 wide (N = 3, 4, 5).
  - Both figures therefore use refined runs only. Plain runs contribute only their `out.txt`
    verified count.
- **The CLI already prints what the script must agree with.** `zeta N --refine` prints:
  - `Spacing histogram: delta_n = ... , <k> spacings`;
  - 20 rows `<lo>-<hi>  <count>  <observed>  <wigner>` (bins of 0.15 on [0, 3]);
  - `KS distance to the Wigner surmise CDF: <x.xxxx>`.

  `zeta/zeta-rs/src/spacing.rs` `wigner_cdf` uses F(s) = erf(2s/√π) − (4s/π)·exp(−4s²/π).
  Recomputed from the `t_n` column of the real refined tables (Goal-Fit and Risk lenses):
  - KS 0.044810 (N = 3), 0.027206 (N = 4) and 0.018354 (N = 5), matching the printed 0.0448,
    0.0272 and 0.0184;
  - 60 bins of 0.05 summed in threes equal the printed 20 counts exactly (N = 3 and N = 5);
  - no spacing exceeds 3 (maximum 2.83 at N = 5).
- **`/usr/bin/time -v` provenance.** Each run directory's `err.txt` holds
  `Command being timed: "../zeta-<sha7> <args>"`, `Elapsed (wall clock) time`,
  `Maximum resident set size (kbytes)` and `Exit status`.
  - The binary has no `--version` and carries its commit only in its file name (`zeta-f935b23`).
  - Not every existing run was made under `time -v`: n2, n3, v7plain, v7refine and r3 have no
    `Maximum resident` line. They take seconds to re-run.
- **Gram's law counts (Goal-Fit lens, double-precision Gram points by Newton on θ, refined
  midpoints `t_n`):**

  | N | exactly-one share | intervals with 0 / 1 / 2 / 3 zeros | brackets straddling a Gram point |
  |---|---|---|---|
  | 3 | 0.9321 | 22 / 604 / 22 / 0 | 0 |
  | 4 | 0.8385 | 822 / 8504 / 810 / 6 | 1 |
  | 5 | 0.7899 | 14568 / 109064 / 14304 / 132 | 7 |
- **`--refine` cost.**
  - `zeta 5 --refine`: 124.9 s (verification alone 6.6 s), 41,344 kB peak RSS.
  - `zeta 6 --refine` and `zeta 7 --refine` were running when this was written (V4).
- **Published counts.** N(10^N) for N = 2–7 is 29, 649, 10142, 138069, 1747146 and 21136125
  (OEIS A072080). The `zeta` counts equal them.
- **matplotlib 3.11.2** resolves with cp315 wheels locally and cp314 manylinux wheels for CI (dry
  runs). It pulls numpy and pillow, among others. It is not installed in the repo venv today:
  `import matplotlib` raises `ModuleNotFoundError`, and pyright 1.1.411 reports
  `reportMissingImports`.
- **The dependency gate.** `tests/test_root_python_deps.py` requires every unguarded
  third-party import in `scripts/*.py` to be pinned in `requirements-dev.txt`.

## Approach

**Chosen: a local generator plus a dispatch-only deploy workflow.**

- `scripts/zeta_results.py` reads the run directories named on its command line and the
  committed `zeta/results/runs.toml`. It writes `zeta/results/site/`: `index.html`, one SVG per
  figure, and `data.json`.
- The operator runs the script after a measurement run and commits `zeta/results/` through a
  normal PR.
- `.github/workflows/zeta-results-pages.yml` (`workflow_dispatch` only, master only) copies
  `zeta/results/site/` into `gh-pages` under `zeta/`, writes `zeta/deployed-from.txt` with the
  master commit, and pushes.

**Rejected:**

- **Generate in CI.** CI cannot hold the 1.5 GB tables or run the multi-hour verifications.
- **Pages from `master /docs`.** It would break the benchmark page's source and publish every
  spec through Jekyll.
- **Deploy on push.** Operator choice 2026-11-24: manual dispatch, as with releases. Drift
  between master and the live page is made visible instead (`deployed-from.txt`, and the
  generation commit on the page).
- **Hand-typed provenance.** Operator choice 2026-11-24: parse `/usr/bin/time -v` output.
- **A run wrapper script.** It would record provenance more cleanly, but the N = 6 and N = 7
  `--refine` runs were already in flight without one. Parsing `err.txt` covers every run.
- **Gram blocks per Gram interval.** Operator choice 2026-11-24: the exactly-one share, which
  is the statistic the literature tabulates.
- **Static SVG drawn by a stdlib script, or a JS chart library.** The operator chose matplotlib.

## Design

### Inputs

`zeta/results/runs.toml` holds one `[[run]]` table per run, with keys:

- `id`: the run directory's name on the command line;
- `binary_sha`: 40 hex, the commit the binary was built from;
- `machine`: a public label, for example `Threadripper 3960X, 48 threads, Ubuntu 26.04`;
- `date`: an ISO date;
- `note`: optional free text, for example `machine also running other jobs`.

Nothing else is typed. N, `--refine`, elapsed time, peak memory and the exit status come from
`err.txt`, and the counts come from `out.txt`. The script takes run directories as
`--run <id>=<dir>`. Each directory holds `out.txt` (stdout) and `err.txt` (stderr, including
the `/usr/bin/time -v` report). Refined runs also hold `zeta_1eN.txt`.

### Parsing and checks (fail closed)

For each `--run`:

- **`err.txt`:**
  - `Command being timed: "<path>/zeta-<h> <N>[ --refine]"`, where `<h>` equals the first 7
    characters of `binary_sha`, N is in 2–7, and the arguments match `^[2-7]( --refine)?$`;
  - `Exit status: 0`;
  - `Elapsed (wall clock) time` and `Maximum resident set size (kbytes)`.

  The published command is rebuilt as `zeta <N>[ --refine]`. The path in `err.txt` is never
  copied.
- **`out.txt`:** must contain
  `RH verified: all <L> nontrivial zeros with 0 < Im s <= <10^N> lie on Re s = 1/2 and are simple`.
- **Refined runs only:**
  - the table header is `# n a b t_n w_n`;
  - exactly L data lines numbered 1..L, with `a ≤ t_n ≤ b` (the midpoint printed to 15
    significant digits may sit 1 ulp outside; allow 1e-9 relative);
  - `t_n` strictly increasing;
  - every number finite.

  Then, against the CLI's own output in `out.txt`:
  - the spacing count equals both L − 1 and the CLI's `<k> spacings`;
  - the script's 60 bins of 0.05, summed in threes, equal the CLI's 20 printed counts;
  - the script's KS distance to the Wigner surmise, rounded to 4 decimals, equals the CLI's
    `KS distance to the Wigner surmise CDF:` value.
- **`runs.toml`:** every `--run` id has an entry, and every entry has a `--run`.

Any failure exits 1 with one line naming the run id and the check. The site is not written.
When matplotlib cannot be imported, the script exits 1 with
`zeta_results: matplotlib missing; run make install-deps`.

### Computations

- **Counts table:** for every run, L, the published N(10^N) from a constant in the script
  (citing OEIS A072080), and `equal` or `differs`.
- **Gap histogram,** per refined run:
  - normalised gaps δ_n = (t_{n+1} − t_n)·ln(t_n/2π)/2π over all consecutive pairs;
  - a density histogram on [0, 3]: 20 bins of 0.15 when there are fewer than 10,000 gaps
    (N = 3, 4), otherwise 60 bins of 0.05;
  - curves: Wigner surmise p(s) = (32/π²)·s²·exp(−4s²/π), and Poisson exp(−s);
  - KS distance to the Wigner CDF F(s) = erf(2s/√π) − (4s/π)·exp(−4s²/π), and to the Poisson
    CDF 1 − exp(−s);
  - the gap count, shown on the figure.
- **Gram's law,** per refined run:
  - Gram points g_n solve θ(g_n) = nπ by Newton's method in double precision, with
    θ(t) = (t/2)·ln(t/2π) − t/2 − π/8 + 1/(48t) + 7/(5760t³) and g₋₁ ≈ 9.6669;
  - the intervals are [g_{n−1}, g_n) for n = 0..K, where g_K is the last Gram point ≤ 10^N;
  - each zero is assigned to an interval by its `t_n`; output the number of intervals holding
    0, 1, 2, 3 and 4 or more zeros, and the exactly-one share;
  - S, the number of brackets [a, b] containing a Gram point. Their assignment is uncertain, so
    the page reports S beside the share.

  The page states that the zero brackets are certified, the Gram points are not, and S bounds
  how much that matters.

### Output

- `zeta/results/site/index.html` is static HTML with no JavaScript and no external requests. It
  carries `<meta name="viewport" content="width=device-width, initial-scale=1">` and an inline
  style `img{max-width:100%;height:auto}`. It holds:
  - the claim paragraph;
  - one sentence each defining a Gram point and the normalised gap δ (mean gap 1);
  - the counts table;
  - the figures, each an `<img>` of a local SVG with an `alt` text naming N and what it shows;
  - the Gram's-law table;
  - the run table: N, refine, elapsed, peak RSS, command, binary commit, machine, date, note;
  - under every figure, a provenance line giving the command, binary commit, machine and date
    of its run;
  - a footer naming the repo commit the generator ran at (`git rev-parse HEAD`) and linking
    `deployed-from.txt`.
- **Figures:** one SVG per refined N (6 × 4 in, fonts at least 12 pt), and one SVG of the
  exactly-one share against N.
  - matplotlib writes them with `metadata={"Date": None}` and a fixed `svg.hashsalt`, so two
    runs over the same inputs in one environment are byte-identical.
- **`data.json`:** holds every plotted and tabulated number, plus the provenance per run id. The
  consistency test reads it (see Testing).
- The script writes into a temporary directory beside `site/`, then swaps it in by renaming
  the old directory away and the new one into place. A failed run leaves the previous site
  intact.

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
- `concurrency: { group: gh-pages, cancel-in-progress: false }`;
- every `uses:` pinned to a 40-hex SHA.

Steps:

1. Check out master, then check out `gh-pages` into a separate path.
2. Replace `gh-pages/zeta/` with `zeta/results/site/`.
3. Write `gh-pages/zeta/deployed-from.txt` containing `${{ github.sha }}`.
4. Fail if any path in `git -C <gh-pages> status --porcelain` lies outside `zeta/`.
5. Commit and push without `--force`, only when the status is non-empty.

`benchmarks.yml` gains the same `concurrency` group, so the two `gh-pages` writers never run at
once.

### Dependencies and push-path safety

- `matplotlib==3.11.2` is added to `requirements-dev.txt`, which `scripts.yml` installs. The
  script imports no other third-party module directly (no `numpy`), so
  `tests/test_root_python_deps.py` needs only that pin.
- Dev machines without matplotlib:
  - `tests/test_zeta_results.py` skips with `matplotlib not installed; run make install-deps`
    when the import fails and `CI` is not `true`, and fails when `CI=true`.
  - pyright's `reportMissingImports` cannot be skipped the same way. Before merge, the operator
    and peer sessions get notice to run `make install-deps` in each math checkout (core.md
    git-workflow-020).
- `scripts.yml` `paths:` gains `zeta/results/**`, so a site-only PR runs the consistency test.

### Testing

`tests/test_zeta_results.py` (unittest, under `make test-python`).

**Fixtures:** the real N = 2 and N = 3 runs of binary f935b23 under `/usr/bin/time -v`, plain
and `--refine` (`out.txt`, `err.txt`, and the refined `zeta_1e3.txt`, 60,344 bytes). They live
under `tests/fixtures/zeta_results/`, with a `runs.toml`. Paths in the fixture `err.txt` files
are reduced to `../zeta-f935b23` before commit.

**Value pins** (each fails if a computation produced nothing):

- N = 3 refined:
  - KS to Wigner rounds to 0.0448;
  - 648 gaps;
  - the 20 histogram counts equal the CLI's (0, 7, 26, 58, 96, 92, 109, 80, 58, 57, 28, 19, 8, 9, 1, 0, 0, 0, 0, 0);
  - Gram counts 22 / 604 / 22 / 0 with share 0.9321 and S = 0.
- The N = 3 counts row reads 649 and `equal`.
- The set of SVG files equals the figures listed in `data.json`, and each lists non-empty data.

**Fail-closed paths,** each exiting 1 with the run id named and a pre-existing `site/` left
byte-unchanged:

- no `RH verified` line;
- `Exit status` not 0;
- binary name not matching `binary_sha`;
- refined table header plain;
- data-line count ≠ L;
- a NaN;
- `t_n` not increasing;
- one CLI histogram count altered;
- KS line altered;
- `--run` id absent from `runs.toml`.

**Other tests:**

- **Determinism:** two generations over the fixtures are byte-identical.
- **Page hygiene:** `index.html` has no `<script`, no `src`/`href` starting with `http`, the
  viewport meta, `alt` on every `<img>`, the claim paragraph verbatim, and no path from the
  fixture `err.txt`.
- **Consistency:** the ids and provenance in the committed `zeta/results/site/data.json` equal
  those in `zeta/results/runs.toml`.
- **matplotlib-absent skip:** the module skips with the named line when `CI` is unset and the
  import fails, and fails when `CI=true`.

**Workflow:** extend `tests/test_workflow_actions_pinned.py` coverage, which is automatic. Add a
test asserting the deploy workflow's trigger is only `workflow_dispatch`, its `if` is the master
ref, and both `gh-pages` writers share the `gh-pages` concurrency group. The step 4 guard is
shell, so a bats test runs it against a fixture repo with a change outside `zeta/` and asserts
exit 1.

## Requirements

- **R1.** `scripts/zeta_results.py --runs-toml <file> --run <id>=<dir> ... --out <dir>` writes `<dir>/index.html`, one `.svg` per figure and `<dir>/data.json`, and exits 0.
- **R2.** `zeta/results/runs.toml` has one `[[run]]` per run with keys `id`, `binary_sha` (40 hex), `machine`, `date` and optional `note`, and no other key.
- **R3.** The script takes N, `--refine`, elapsed wall time, peak RSS and exit status from the `/usr/bin/time -v` report in each run's `err.txt`, requires `Exit status: 0`, requires the binary file name to be `zeta-` plus the first 7 characters of `binary_sha`, and publishes the command as `zeta <N>[ --refine]` without any path.
- **R4.** The script exits 1, printing one line that names the run id and the failed check, and leaves an existing output directory byte-unchanged, when: `out.txt` lacks `RH verified: all <L> nontrivial zeros with 0 < Im s <= <10^N> lie on Re s = 1/2 and are simple`; `Exit status` is not 0; the binary name does not match `binary_sha`; a refined table's header is not `# n a b t_n w_n`; a refined table's data-line count differs from L; a number is not finite; `t_n` is not strictly increasing; a `--run` id has no `runs.toml` entry or an entry has no `--run`.
- **R5.** For every refined run the script exits 1 unless its gap count equals both L − 1 and the CLI's printed `<k> spacings`, its 0.05-wide bins summed in threes equal the CLI's 20 printed counts, and its KS distance to F(s) = erf(2s/√π) − (4s/π)·exp(−4s²/π) rounded to 4 decimals equals the CLI's `KS distance to the Wigner surmise CDF:` value.
- **R6.** Normalised gaps are δ_n = (t_{n+1} − t_n)·ln(t_n/2π)/2π from refined `t_n`; each refined N gets its own figure, a density histogram on [0, 3] with 20 bins of 0.15 below 10,000 gaps and 60 bins of 0.05 otherwise, the curves (32/π²)·s²·exp(−4s²/π) and exp(−s), the gap count, and the KS distances to F(s) above and to 1 − exp(−s).
- **R7.** For each refined run, Gram points come from Newton's method on θ(t) = (t/2)·ln(t/2π) − t/2 − π/8 + 1/(48t) + 7/(5760t³) = nπ; zeros are assigned to [g_{n−1}, g_n) by `t_n` for every n with g_n ≤ 10^N; the page shows the number of intervals holding 0, 1, 2, 3 and 4+ zeros, the exactly-one share, and the count S of brackets [a, b] containing a Gram point, and states that the Gram points are computed in double precision and are not certified.
- **R8.** The counts table shows, for every run, L, the published N(10^N) from a constant citing OEIS A072080 (29, 649, 10142, 138069, 1747146, 21136125 for N = 2–7), and `equal` or `differs`.
- **R9.** `index.html` has no `<script` element, no `src` or `href` beginning with `http`, the meta `<meta name="viewport" content="width=device-width, initial-scale=1">`, an `alt` on every `<img>`, the claim paragraph of the section "Claim text (exact)" verbatim, no sentence calling the result new, a provenance line (command, binary commit, machine, date) under every figure, and a footer with the generator's repo commit and a link to `deployed-from.txt`.
- **R10.** Two runs of the script over the same inputs in one environment produce byte-identical output directories.
- **R11.** `.github/workflows/zeta-results-pages.yml` triggers on `workflow_dispatch` only, runs only when `github.ref == 'refs/heads/master'`, has `permissions: contents: write` and `concurrency` group `gh-pages` with `cancel-in-progress: false`, pins every `uses:` to a 40-hex SHA, replaces only `zeta/` on `gh-pages` with `zeta/results/site/`, writes `zeta/deployed-from.txt` holding the master commit, exits 1 if any changed path lies outside `zeta/`, and pushes without `--force` only when something changed.
- **R12.** `.github/workflows/benchmarks.yml` gains `concurrency` group `gh-pages` with `cancel-in-progress: false`.
- **R13.** `requirements-dev.txt` pins `matplotlib==3.11.2`, no other file installs matplotlib, and `scripts/zeta_results.py` imports no third-party module other than matplotlib.
- **R14.** Without matplotlib, the script exits 1 with `zeta_results: matplotlib missing; run make install-deps`, and `tests/test_zeta_results.py` skips with `matplotlib not installed; run make install-deps` when `CI` is not `true` and fails when `CI=true`.
- **R15.** `tests/test_zeta_results.py` pins, on the N = 3 refined fixture, KS 0.0448, 648 gaps, the 20 counts 0, 7, 26, 58, 96, 92, 109, 80, 58, 57, 28, 19, 8, 9, 1, 0, 0, 0, 0, 0, Gram counts 22 / 604 / 22 / 0 with share 0.9321 and S = 0, and the N = 3 counts row reading 649 `equal`; it covers every R4 and R5 failure case, R10, R9, and the equality of ids and provenance between the committed `zeta/results/site/data.json` and `zeta/results/runs.toml`.
- **R16.** A bats test runs the deploy workflow's outside-`zeta/` guard against a fixture repo with a change outside `zeta/` and asserts exit 1.
- **R17.** `.github/workflows/scripts.yml` `paths:` includes `zeta/results/**`.
- **R18.** `zeta/results/site/` is committed holding the page generated from the real runs of binary f935b23: plain N = 2–7 and `--refine` N = 3–7, every one under `/usr/bin/time -v`.
- **V1.** After the deploy workflow is dispatched, `https://brujack.github.io/math/zeta/` serves the page with `deployed-from.txt` equal to the master commit, and `https://brujack.github.io/math/dev/bench/` still serves the benchmark page.
- **V2.** On the real runs the script passes every R5 cross-check for N = 3–7, and every counts row reads `equal`.
- **V3.** `pip install -r requirements-dev.txt` succeeds on CI's Python 3.14 (`scripts.yml` job log) and the local 3.15 venv.
- **V4.** The run table records `zeta 6 --refine` and `zeta 7 --refine` elapsed time and peak RSS. This closes the Backlog row "zeta --refine at N = 7 cost unmeasured".
- **V5.** Before merge, the operator and peer sessions are told to run `make install-deps` in every math checkout, because the matplotlib import fails root pyright until they do.
- **N1.** No change to `zeta/zeta-rs/` or to any crate template.
- **N2.** No JavaScript, web font or third-party request on the page.
- **N3.** No run output table (`zeta_1eN.txt`) is committed, apart from the N = 3 refined test fixture.
- **N4.** The deploy workflow never deletes or rewrites anything on `gh-pages` outside `zeta/`.
- **N5.** No change to the Pages source setting (stays `gh-pages /`, legacy build).
- **N6.** No local filesystem path appears in any committed file under `zeta/results/` or `tests/fixtures/zeta_results/`.

## Multi-Lens Review

Reviewed at commit: `bf86fa5` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding:

- F1: the KS reference CDF 1 − exp(−4s²/π) is wrong; the Wigner surmise CDF is
  erf(2s/√π) − (4s/π)·exp(−4s²/π) (as in `spacing.rs` `wigner_cdf`).
  - The spec's form gives KS 0.2449 / 0.2320 / 0.2257 at N = 3 / 4 / 5 on the real refined
    tables, against the CLI's 0.0448 / 0.0272 / 0.0184. So R4 contradicts R5.
- F2: "Gram blocks per Gram interval" is not the statistic readers expect for Gram's law.
  - The standard one is the share of Gram intervals holding exactly one zero, with the 0/1/2/3
    counts. It is computable from refined `t_n`.
  - Measured: N = 3: 0.9321 (22/604/22); N = 4: 0.8385 (822/8504/810/6); N = 5: 0.7899
    (14568/109064/14304/132).
  - Brackets straddling a Gram point: 0, 1 and 7.
- F3: no test pins the histogram itself. Pin the 60 bins re-binned 3:1 against the CLI's
  20-bin counts.
- F4: the plain tables add only a row count the CLI already certified (1.5 GB read at N = 7).
  - Generate from `out.txt`, plus refined tables where needed.
  - `data.json` has no reader except tests.

Assumption: `zeta 6 --refine` finishes, so N = 6 can stay mandatory in R14. Settled by `r6/rc.txt`
showing rc=0 and `r6/out.txt` holding the verified and KS lines.
Disposition: Addressed (operator, 2026-11-24: "Exactly-one share" for F2, "Address all" for the rest). F1: the Wigner CDF is corrected and the CLI cross-checks are fail-closed (R5). F2: the Gram figure is the exactly-one share (R7). F3: histogram counts are pinned against the CLI (R5, R15). F4: plain tables are no longer read, and data.json gains a reader (the consistency test).

### Ergonomics

Finding:

- F1: runs.toml hand-copies about 90 values that `err.txt` (`/usr/bin/time -v`) already holds,
  and nothing binds `binary_sha`, elapsed, RSS or command to the run.
  - The binary has no `--version`.
  - 5 of the 10 needed runs lack `time -v` output.
  - Proposed fixes: parse `err.txt`, check the binary name against the SHA, or add a
    `scripts/zeta_run.sh` wrapper that records provenance.
- F2: adding matplotlib makes pyright (`reportMissingImports`) and `make test-python` fail on
  any dev machine without it. That blocks unrelated root pushes until `make install-deps` runs.
  - Skip the tests outside CI when matplotlib is absent.
  - Give fan-out notice.
- F3: nothing checks that the committed site matches `runs.toml`, and a site-only PR runs no
  tests (`scripts.yml` paths). Add a consistency test and `zeta/results/**` to the paths.
- F4: a refresh is about 11 steps, including the full Phase 3 chain on generated files. Nothing
  prompts the deploy after merge.
  - Stamp the master SHA on the page, or deploy on push of `zeta/results/site/**`.
- F5: phone and teacher readability.
  - Add a viewport meta, `img{max-width:100%}`, alt text, and one figure per N at 12 pt or more.
  - Define a Gram point and δ in words.
  - Show sample size per panel.
  - N = 3 has only 648 gaps in 60 bins.

Assumption: provenance can be trusted without being derived from the run. It holds only if every
published run comes from one sanctioned wrapper. 5 of the 10 existing run dirs already lack
`time -v`.
Disposition: Addressed (operator, 2026-11-24: "Parse /usr/bin/time output", "Manual + SHA stamp", "Address all"). F1: provenance comes from err.txt and runs.toml keeps 4 keys (R2, R3). F2: the tests skip outside CI and notice goes out before merge (R14, V5). F3: a consistency test and the scripts.yml paths (R15, R17). F4: deployed-from.txt and the footer commit (R9, R11). F5: viewport, alt text, one figure per N, definitions, gap counts and bin choice (R6, R9).

### Risk

Finding:

- R1 (high): the same wrong-CDF finding as Goal-Fit F1.
- R2: make the CLI cross-checks fail-closed at runtime for every refined run, not only in a test:
  - spacing count = L − 1;
  - the 60 bins re-binned 3:1 equal the CLI's 20 printed counts (verified exact on r3 and r5);
  - KS at 4 decimals equals the CLI's line.
- R3: `tests/test_root_python_deps.py` requires every direct third-party import to be pinned.
  - A direct `numpy` import needs `numpy==2.5.5` too.
  - The pre-push breakage is the same as Ergonomics F2.
  - CI 3.14 wheels resolve (dry run).
- R4: hand-typed provenance.
  - `command` copied from `err.txt` would leak a path. Validate it against
    `^zeta [2-7]( --refine)?$`.
  - The SHA is unverifiable: label it "recorded", or add the binary's sha256.
- R5: nothing enforces N4.
  - Fail if `gh-pages` changes outside `zeta/`.
  - Forbid `--force`.
  - Add `concurrency: gh-pages` to both writer workflows.
- R6: a Gram density labelled by N misstates its range: N = 2 covers [g₋₁, 529.1].
  - Label by g_M.
  - The between-run difference can be off by ±1 block (`plan_blocks` trailing run).

Premises verified:

- M from θ(g_M) equals the stderr `progress: X/X Gram points` total minus 2 for N = 2, 5, 6, 7.
  That line is an exact second source of M.
- A072080 counts match.

Assumption: R14 as written depends on `zeta 6 --refine` completing; same settling check as
Goal-Fit.
Disposition: Addressed (operator, 2026-11-24: "Address all"). R1: the CDF is corrected (R5, R6). R2: runtime cross-checks (R5). R3: no direct numpy import (R13) and the skip (R14). R4: the command is rebuilt without a path and the binary name is checked (R3, N6). R5: the guard, concurrency and a bats test (R11, R12, R16). R6: the block-density figure is dropped.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
