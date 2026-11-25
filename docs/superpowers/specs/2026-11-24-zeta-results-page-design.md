# zeta: public results page

- **Date:** 2026-11-24
- **Sub-project:** `zeta/` (results page only; the `zeta` CLI is unchanged)
- **Origin:** operator approval of 2026-11-23 for a published page of zeta's verified
  results, built after the V3–V7 runs of `2026-11-23-zeta-rh-verification-design.md`;
  operator choices of 2026-11-24: GitHub Pages, matplotlib.
- **Revised:** 2026-11-24, after Multi-Lens Review rounds 1 and 2 and External Review round 1

- **Approved:** 2026-11-24

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

  `zeta/zeta-rs/src/spacing.rs` computes these from the exact f64 midpoint `a + (b − a)/2` of
  each refined bracket (`write_report`, via `isolate::midpoint`), not from the printed `t_n`:
  - `t_n` is that midpoint rounded to 15 significant digits (`main.rs` `write_table`);
  - `wigner_cdf` is erf(x) − (2/√π)·x·exp(−a·s²) with a = 4/π and x = √a·s, that is
    F(s) = erf(2s/√π) − (4s/π)·exp(−4s²/π), where `erf` is Abramowitz–Stegun 7.1.26
    (absolute error at most 1.5e-7), not an exact erf;
  - `bin_index(s)` is `min(floor(s/0.15), 19)` for s in [0, 3] (3 itself in the last bin);
    a spacing above 3 is not counted.

  Rounding to 15 digits moves δ by about 7.6e-9 near 10^7. Over 2.1·10^7 gaps that is expected
  to flip about one spacing across a bin edge (round-2 Goal-Fit and Risk models; the Goal-Fit
  model predicted 4 flips and observed 4 when r5's midpoints were rounded to 10 digits). So
  the script must use the exact midpoint, not `t_n`, for any value compared with the CLI's.
  Recomputed from the real refined tables (Goal-Fit and Risk lenses):
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
  midpoints; S counts brackets with a Gram point strictly inside, by the 1e-8 rule of Computations; External Review round 1 measured the N = 5 value):**

  | N | exactly-one share | intervals with 0 / 1 / 2 / 3 zeros | brackets straddling a Gram point |
  |---|---|---|---|
  | 3 | 0.9321 | 22 / 604 / 22 / 0 | 0 |
  | 4 | 0.8385 | 822 / 8504 / 810 / 6 | 1 |
  | 5 | 0.7899 | 14568 / 109064 / 14304 / 132 | 6 |
- **`--refine` cost.**
  - `zeta 5 --refine`: 124.9 s (verification alone 6.6 s), 41,344 kB peak RSS.
  - `zeta 6 --refine` and `zeta 7 --refine` were running when this was written (V4).
- **Gap counts.** N = 3 has 648 gaps and N = 4 has 10,141 (`tr4`).
- **Run storage.** Every run directory needed for the page lives outside the repo, on the
  operator's machine in a durable directory chosen by the operator (2026-11-24: `~/zeta-runs/`).
  Session scratch space is a RAM-backed `/tmp` that a reboot clears. The repo never names the
  location. At the time of writing the store holds t2, t3, t4, n5, n6, n7, tr3, tr4 and r5. The
  refined N = 6 and N = 7 runs are in flight in session scratch and move to the store when they
  finish. If either is lost, R18 cannot be met until it is re-run (refined N = 7 is estimated at
  8 hours or more, unmeasured), and the plan says so before Phase 2.
- **Published counts.** N(10^N) for N = 2–7 is 29, 649, 10142, 138069, 1747146 and 21136125
  (OEIS A072080). The `zeta` counts equal them.
- **matplotlib 3.11.2** resolves with cp315 wheels locally and cp314 manylinux wheels for CI (dry
  runs). It pulls numpy and pillow, among others. It is not installed in the repo venv today:
  `import matplotlib` raises `ModuleNotFoundError`, and pyright 1.1.411 reports
  `reportMissingImports`. An import line carrying `# pyright: ignore[reportMissingImports]`
  silences that, and changes nothing when matplotlib is present, because
  `reportUnnecessaryTypeIgnoreComment` is off in `pyrightconfig.json` (round-2 Ergonomics).
- **The fixture name is gitignored.** `git check-ignore -v` on a fixture `zeta_1e3.txt` reports
  `.gitignore:58:zeta_1e*.txt`.
- **The dependency gate.** `tests/test_root_python_deps.py` requires every unguarded
  third-party import in `scripts/*.py` to be pinned in `requirements-dev.txt`.

## Approach

**Chosen: a local generator plus a dispatch-only deploy workflow.**

- `scripts/zeta_results.py` reads the run directories named on its command line and the
  committed `zeta/results/runs.toml`. It writes `zeta/results/site/`: `index.html` and one SVG
  per figure.
- The operator runs the script after a measurement run and commits `zeta/results/` through a
  normal PR.
- `.github/workflows/zeta-results-pages.yml` (`workflow_dispatch` only, master only) copies
  `zeta/results/site/` into `gh-pages` under `zeta/`, writes `zeta/deployed-from.txt` with the
  master commit, and pushes.
- The run directories stay in the operator's durable run store outside the repo, so the page
  can be regenerated without re-running.

**Rejected:**

- **Generate in CI.** CI cannot hold the 1.5 GB tables or run the multi-hour verifications.
- **Pages from `master /docs`.** It would break the benchmark page's source and publish every
  spec through Jekyll.
- **Deploy on push.** Operator choice 2026-11-24: manual dispatch, as with releases. The page
  links `deployed-from.txt`, which holds the master commit last deployed. A generation commit in
  the page itself was dropped: the repo squash-merges, so the commit a generator ran at never
  lands on master.
- **`data.json`.** Dropped in round 2: no reader of the page used it.
- **Consistency from `runs.toml` alone.** External Review round 1 showed a hand-edited count or
  elapsed time would pass a check of only ids, commits and dates. Instead each run's `out.txt`
  and `err.txt` is committed under `zeta/results/runs/<id>/` (about 30 KB for all eleven). CI
  then regenerates every value those files determine and compares it with `index.html`. That
  covers the counts table, the run table, and each refined run's CLI gap count, 20 bins and KS.
  The δ-derived figures and the Gram table still need the uncommitted tables, so those stay
  operator-attested, cross-checked against the CLI at generation time.
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
  - `Elapsed (wall clock) time (h:mm:ss or m:ss): <v>`, where `<v>` is either `m:ss.ss` or
    `h:mm:ss` (runs of an hour or more), and `Maximum resident set size (kbytes)`.

  The published command is rebuilt as `zeta <N>[ --refine]`. The path in `err.txt` is never
  copied.
- **`out.txt`:** must contain
  `RH verified: all <L> nontrivial zeros with 0 < Im s <= <10^N> lie on Re s = 1/2 and are simple`.
- **Refined runs only:**
  - the table header is `# n a b t_n w_n`;
  - exactly L data lines numbered 1..L;
  - every number finite;
  - the midpoint m_n = a + (b − a)/2, computed in f64 from the parsed 30-digit `a` and `b`,
    strictly increasing;
  - `a ≤ t_n ≤ b` within 1e-9 relative to `t_n` (the 15-digit `t_n` may print just outside a
    very narrow bracket).

  Then, against the CLI's own output in `out.txt`:
  - the spacing count equals both L − 1 and the CLI's `<k> spacings`;
  - the script's 20 bins, `min(floor(δ/0.15), 19)` over δ in [0, 3], equal the CLI's 20 printed
    counts;
  - the script's KS distance to the CLI's F(s) (same Abramowitz–Stegun erf, same expression),
    rounded to 4 decimals, equals the CLI's `KS distance to the Wigner surmise CDF:` value.

  All three use δ_n = (m_{n+1} − m_n)·ln(m_n/2π)/2π computed in that operation order, so they
  reproduce the CLI's values bit for bit rather than within a tolerance.
- **`runs.toml`:** every `--run` id has an entry, and every entry has a `--run`.
- The script copies each run's `out.txt` and `err.txt` into `zeta/results/runs/<id>/`. The
  `Command being timed` path in `err.txt` is reduced to `zeta-<h>` on copy, so no path is
  committed.
- **Start:** stale `site.*` siblings from a crashed earlier run are removed before anything is
  read.

Any failure exits 1 with one line naming the run id and the check. The site is not written.
When matplotlib cannot be imported, the script exits 1 with
`zeta_results: matplotlib missing; run make install-deps`.

### Computations

- **Counts table:** for every run, L, the published N(10^N) from a constant in the script
  (citing OEIS A072080), and `equal` or `differs`.
- **Gap histogram,** per refined run:
  - normalised gaps δ_n as in the checks above, from the exact midpoints m_n;
  - a density histogram on [0, 3], dividing by the total gap count as the CLI does: 20 bins of
    0.15 when there are fewer than 10,000 gaps (N = 3), otherwise 60 bins of 0.05
    (`min(floor(δ/0.05), 59)`); the threshold is a parameter of the binning function;
  - curves: Wigner surmise p(s) = (32/π²)·s²·exp(−4s²/π), and Poisson exp(−s);
  - KS distance to the Wigner CDF F(s) above, and to the Poisson CDF 1 − exp(−s);
  - the gap count, shown on the figure.

  The page says the Poisson contrast is the lesson. A KS of 0.018 on 138,068 gaps still
  rejects the surmise statistically (the 5% critical value is about 0.0037), because the
  surmise is an approximation and convergence with height is slow.
- **Gram's law,** per refined run:
  - Gram points g_n solve θ(g_n) = nπ by Newton's method in double precision, with
    θ(t) = (t/2)·ln(t/2π) − t/2 − π/8 + 1/(48t) + 7/(5760t³) and g₋₁ ≈ 9.6669;
  - the intervals are [g_{n−1}, g_n) for n = 0..K, where g_K is the last Gram point ≤ 10^N;
  - each zero is assigned to an interval by its midpoint m_n; output the number of intervals
    holding 0, 1, 2, 3 and 4 or more zeros, and the exactly-one share;
  - S, the number of brackets with a Gram point g strictly inside, a < g < b, where a g within
    an absolute 1e-8 of a or b counts as that endpoint. The tolerance is sized to the f64 Newton
    error (about 2e-9 at 10^7), not to g: refined brackets narrow with height (median width
    1.55e-5 at N = 5), so a relative tolerance would hide real straddles. The CLI isolates on the Gram grid, so a bracket
    can start exactly at a Gram point without its zero's interval being in doubt. The page
    reports S beside the share.
  - The zero above the last Gram point g_K ≤ 10^N is in no interval, and the page says so.

  The page states that the zero brackets are certified, the Gram points are not, and S bounds
  how much that matters.

### Output

- `zeta/results/site/index.html` is static HTML with no JavaScript and no external requests. It
  carries `<meta name="viewport" content="width=device-width, initial-scale=1">` and an inline
  style `img{max-width:100%;height:auto}`. Every table sits in a `<div style="overflow-x:auto">`.
  It holds:
  - the claim paragraph;
  - one sentence each defining a Gram point and the normalised gap δ (mean gap 1);
  - the counts table;
  - the figures, each an `<img>` of a local SVG with an `alt` text naming N and what it shows;
  - the Gram's-law table;
  - the run table: N, refine, elapsed, peak RSS, binary commit, date, note, with the machine
    printed once above it when every run shares it;
  - under every figure, a provenance line giving the command, binary commit, machine and date
    of its run;
  - a footer linking `deployed-from.txt`.
- **Figures:** one SVG per refined N (6 × 4 in, fonts at least 12 pt), and one SVG of the
  exactly-one share against N.
  - matplotlib writes them with `metadata={"Date": None}` and a fixed `svg.hashsalt`, so two
    runs over the same inputs in one environment are byte-identical.
- Every check runs before anything is written. The script then writes a temporary directory
  beside `site/` and swaps it in by renaming the old directory away and the new one into place.
  If the second rename fails, it renames the old one back. A failed check therefore leaves the
  previous site byte-unchanged.

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
- job-level `concurrency: { group: gh-pages, cancel-in-progress: false }`;
- every `uses:` pinned to a 40-hex SHA.

Steps:

1. Check out master, then check out `gh-pages` into a separate path.
2. Replace `gh-pages/zeta/` with `zeta/results/site/`.
3. Write `gh-pages/zeta/deployed-from.txt` containing `${{ github.sha }}`.
4. Fail if any path in `git -C <gh-pages> status --porcelain` lies outside `zeta/`.
5. Commit and push without `--force`, only when the status is non-empty.

`benchmarks.yml`'s job gains the same `concurrency` group, so the two `gh-pages` writers never
run at once. GitHub keeps at most one pending run per group, and a newer one replaces it. A
deploy dispatched while a benchmark run is already pending could therefore displace that run.
This is accepted: both are re-runnable by hand.

### Dependencies and push-path safety

- `matplotlib==3.11.2` is added to `requirements-dev.txt`, which `scripts.yml` installs. The
  script imports no other third-party module directly (no `numpy`). The matplotlib import is
  guarded by `except ImportError`, which `tests/test_root_python_deps.py` skips, so an AST test
  in `tests/test_zeta_results.py` enforces this (Testing, Imports).
- Dev machines without matplotlib:
  - `tests/test_zeta_results.py` skips with `matplotlib not installed; run make install-deps`
    when the import fails and `CI` is not `true`, and fails when `CI=true`.
  - The matplotlib import sits in `try`/`except ImportError` (for the R14 message) and carries
    `# pyright: ignore[reportMissingImports]`, so root pyright passes with or without
    matplotlib, and no push path breaks.
- `scripts.yml` `paths:` gains `zeta/results/**`, so a site-only PR runs the consistency test.

### Testing

`tests/test_zeta_results.py` (unittest, under `make test-python`).

**Fixtures:** under `tests/fixtures/zeta_results/`, with a `runs.toml` for them:

- the real plain N = 2 and N = 3 runs of binary f935b23 (`out.txt`, `err.txt`);
- the real `--refine` N = 3 run (`out.txt`, `err.txt`, `zeta_1e3.txt`, 60,344 bytes), all made
  under `/usr/bin/time -v`.

`.gitignore` gains the negation `!tests/fixtures/zeta_results/**/zeta_1e3.txt`, and a test
asserts that `git ls-files` lists that fixture. The fixture `err.txt` files already name the
binary as `../zeta-f935b23`, a relative path.

**Value pins** (each fails if its computation produced nothing):

- N = 3 refined:
  - KS to Wigner 0.0448 and to Poisson 0.3260;
  - 648 gaps;
  - the 20 counts 0, 7, 26, 58, 96, 92, 109, 80, 58, 57, 28, 19, 8, 9, 1, 0, 0, 0, 0, 0;
  - with the bin threshold set to 0, the 60 counts 0, 0, 0, 0, 4, 3, 3, 13, 10, 12, 22, 24,
    26, 27, 43, 34, 22, 36, 37, 41, 31, 31, 19, 30, 22, 23, 13, 20, 21, 16, 8, 9, 11, 6, 5, 8,
    5, 3, 0, 7, 2, 0, 0, 0, 1 and then 15 zeros;
  - Gram counts 22 / 604 / 22 / 0 and 4+ = 0, share 0.9321, S = 0.
- **S and assignment on synthetic brackets:**
  - one bracket straddling the computed g₀ ≈ 17.8456 gives S = 1, and one starting exactly at
    g₀ gives S = 0;
  - near g ≈ 9.2·10^4, a bracket of width 2e-5 with the Gram point 1e-5 inside gives S = 1, and
    one whose end is 5e-9 from the Gram point gives S = 0.
- The N = 3 counts row reads 649 and `equal`.
- The SVG files written equal the `<img>` sources in `index.html`. Each SVG contains at least
  one bar and both curves.

**Fail-closed paths,** each exiting 1 with the run id named and a pre-existing `site/` left
byte-unchanged:

- no `RH verified` line;
- `Exit status` not 0;
- binary name not matching `binary_sha`;
- refined table header plain;
- data-line count ≠ L;
- a NaN;
- midpoints not increasing;
- one CLI histogram count altered;
- KS line altered;
- `--run` id absent from `runs.toml`.

**Other tests:**

- **Parsing:** the `/usr/bin/time` elapsed parser reads both `0:02.45` and `1:02:23`.
- **Determinism:** two generations over the fixtures are byte-identical.
- **Page hygiene:** `index.html` has:
  - no `<script`;
  - no `src` or `href` starting with `http`;
  - the viewport meta and `alt` on every `<img>`;
  - every table inside an `overflow-x:auto` div;
  - the claim paragraph verbatim;
  - no path from the fixture `err.txt`.
- **Consistency (runs in CI):** from the committed `zeta/results/runs.toml` and
  `zeta/results/runs/<id>/{out,err}.txt` alone, the script's table builders regenerate the
  counts table, the run table and each refined run's CLI gap count, 20 counts and KS. Each must
  equal what the committed `zeta/results/site/index.html` shows, with no extra run.
- **Imports:** an AST walk of `scripts/zeta_results.py` finds exactly one third-party top-level
  module, `matplotlib`. `tests/test_root_python_deps.py` skips imports guarded by
  `except ImportError`, so this test is the one that enforces R13.
- **matplotlib-absent skip:** the module skips with the named line when `CI` is unset and the
  import fails, and fails when `CI=true`.

**Workflow:** `tests/test_workflow_actions_pinned.py` already covers the SHA pins. Add a test
that the deploy workflow's trigger is only `workflow_dispatch`, its `if` is the master ref, and
both `gh-pages` writers' jobs share the `gh-pages` concurrency group. The outside-`zeta/` guard is
shell, so a bats test runs it against a fixture repo with a change outside `zeta/` and asserts
exit 1.

## Requirements

- **R1.** `scripts/zeta_results.py --runs-toml <file> --run <id>=<dir> ... --out <dir>` writes `<dir>/index.html` and one `.svg` per figure, and exits 0.
- **R2.** `zeta/results/runs.toml` has one `[[run]]` per run with keys `id`, `binary_sha` (40 hex), `machine`, `date` and optional `note`, and no other key.
- **R3.** The script takes N, `--refine`, elapsed wall time (accepting both `m:ss.ss` and `h:mm:ss`), peak RSS and exit status from the `/usr/bin/time -v` report in each run's `err.txt`, requires `Exit status: 0`, requires the binary file name to be `zeta-` plus the first 7 characters of `binary_sha`, and publishes the command as `zeta <N>[ --refine]` without any path.
- **R4.** The script exits 1, printing one line that names the run id and the failed check, and leaves an existing output directory byte-unchanged, when: `out.txt` lacks `RH verified: all <L> nontrivial zeros with 0 < Im s <= <10^N> lie on Re s = 1/2 and are simple`; `Exit status` is not 0; the binary name does not match `binary_sha`; a refined table's header is not `# n a b t_n w_n`; a refined table's data-line count differs from L; a number is not finite; the midpoints a + (b − a)/2 are not strictly increasing; `t_n` lies outside [a, b] by more than 1e-9 relative; a `--run` id has no `runs.toml` entry or an entry has no `--run`.
- **R5.** For every refined run the script computes δ_n = (m_{n+1} − m_n)·ln(m_n/2π)/2π from the f64 midpoints m_n = a + (b − a)/2 of the parsed `a` and `b` columns (never from `t_n`), and exits 1 unless its gap count equals both L − 1 and the CLI's printed `<k> spacings`, its counts `min(floor(δ/0.15), 19)` over δ in [0, 3] equal the CLI's 20 printed counts, and its KS distance to F(s) = erf(x) − (2/√π)·x·exp(−(4/π)·s²), x = (2/√π)·s, with erf by Abramowitz–Stegun 7.1.26, rounded to 4 decimals equals the CLI's `KS distance to the Wigner surmise CDF:` value.
- **R6.** Each refined N gets its own figure from R5's δ_n: a density histogram on [0, 3] divided by the total gap count, with 20 bins of 0.15 below 10,000 gaps and 60 bins of 0.05 (`min(floor(δ/0.05), 59)`) otherwise, the curves (32/π²)·s²·exp(−4s²/π) and exp(−s), the gap count, and the KS distances to R5's F(s) and to 1 − exp(−s).
- **R7.** For each refined run, Gram points come from Newton's method on θ(t) = (t/2)·ln(t/2π) − t/2 − π/8 + 1/(48t) + 7/(5760t³) = nπ; zeros are assigned to [g_{n−1}, g_n) by their midpoint a + (b − a)/2 for every n with g_n ≤ 10^N; the page shows the number of intervals holding 0, 1, 2, 3 and 4+ zeros, the exactly-one share, and the count S of brackets with a Gram point g strictly inside (a < g < b, with g within an absolute 1e-8 of an endpoint counted as that endpoint), and states that the Gram points are computed in double precision and are not certified.
- **R8.** The counts table shows, for every run, L, the published N(10^N) from a constant citing OEIS A072080 (29, 649, 10142, 138069, 1747146, 21136125 for N = 2–7), and `equal` or `differs`.
- **R9.** `index.html` has no `<script` element, no `src` or `href` beginning with `http`, the meta `<meta name="viewport" content="width=device-width, initial-scale=1">`, an `alt` on every `<img>`, every `<table>` inside a `<div style="overflow-x:auto">`, the claim paragraph of the section "Claim text (exact)" verbatim, no sentence calling the result new, a provenance line (command, binary commit, machine, date) under every figure, and a footer linking `deployed-from.txt`.
- **R10.** Two runs of the script over the same inputs in one environment produce byte-identical output directories.
- **R11.** `.github/workflows/zeta-results-pages.yml` triggers on `workflow_dispatch` only, runs only when `github.ref == 'refs/heads/master'`, has `permissions: contents: write` and job-level `concurrency` group `gh-pages` with `cancel-in-progress: false`, pins every `uses:` to a 40-hex SHA, replaces only `zeta/` on `gh-pages` with `zeta/results/site/`, writes `zeta/deployed-from.txt` holding the master commit, exits 1 if any changed path lies outside `zeta/`, and pushes without `--force` only when something changed.
- **R12.** `.github/workflows/benchmarks.yml`'s job gains `concurrency` group `gh-pages` with `cancel-in-progress: false`.
- **R13.** `requirements-dev.txt` pins `matplotlib==3.11.2`, no other file installs matplotlib, `scripts/zeta_results.py` imports no third-party module other than matplotlib, and its matplotlib import carries `# pyright: ignore[reportMissingImports]`.
- **R14.** Without matplotlib, the script exits 1 with `zeta_results: matplotlib missing; run make install-deps`, and `tests/test_zeta_results.py` skips with `matplotlib not installed; run make install-deps` when `CI` is not `true` and fails when `CI=true`.
- **R15.** `tests/test_zeta_results.py` pins, on the N = 3 refined fixture: KS 0.0448 to Wigner and 0.3260 to Poisson; 648 gaps; the 20 counts 0, 7, 26, 58, 96, 92, 109, 80, 58, 57, 28, 19, 8, 9, 1, 0, 0, 0, 0, 0; with the bin threshold set to 0, the 60 counts 0, 0, 0, 0, 4, 3, 3, 13, 10, 12, 22, 24, 26, 27, 43, 34, 22, 36, 37, 41, 31, 31, 19, 30, 22, 23, 13, 20, 21, 16, 8, 9, 11, 6, 5, 8, 5, 3, 0, 7, 2, 0, 0, 0, 1 followed by 15 zeros; Gram counts 22 / 604 / 22 / 0 and 4+ = 0 with share 0.9321 and S = 0; and the N = 3 counts row reading 649 `equal`. It also covers: S = 1 for a synthetic bracket straddling g₀ and S = 0 for one starting at g₀; S = 1 for a width-2e-5 bracket with a Gram point near 9.2·10^4 1e-5 inside it and S = 0 when the end is 5e-9 from it; an AST check that the script's only third-party top-level import is `matplotlib`; both elapsed formats; every R4 and R5 failure case; R10; R9; the SVG set equal to the `<img>` sources, each SVG with a bar and both curves; and, from the committed `zeta/results/runs.toml` and `zeta/results/runs/<id>/{out,err}.txt` alone, the counts table, the run table and each refined run's CLI gap count, 20 counts and KS regenerating equal to the committed `index.html`, with no extra run.
- **R16.** A bats test runs the deploy workflow's outside-`zeta/` guard against a fixture repo with a change outside `zeta/` and asserts exit 1.
- **R17.** `.github/workflows/scripts.yml` `paths:` includes `zeta/results/**`.
- **R18.** `zeta/results/site/` is committed holding the page generated from the real runs of binary f935b23: plain N = 2–7 and `--refine` N = 3–7, every one under `/usr/bin/time -v`.
- **R19.** `.gitignore` carries `!tests/fixtures/zeta_results/**/zeta_1e3.txt`, and a test asserts `git ls-files` lists the N = 3 refined fixture table.
- **R20.** The script copies each run's `out.txt` and `err.txt` to `zeta/results/runs/<id>/`, replacing the `Command being timed` binary path with `zeta-<first 7 of binary_sha>`, and both are committed with the site.
- **V1.** After the deploy workflow is dispatched, `https://brujack.github.io/math/zeta/` serves the page with `deployed-from.txt` equal to the master commit, and `https://brujack.github.io/math/dev/bench/` still serves the benchmark page.
- **V2.** On the real runs the script passes every R5 cross-check for N = 3–7, and every counts row reads `equal`.
- **V3.** `pip install -r requirements-dev.txt` succeeds on CI's Python 3.14 (`scripts.yml` job log) and the local 3.15 venv.
- **V4.** The run table records `zeta 6 --refine` and `zeta 7 --refine` elapsed time and peak RSS. This closes the Backlog row "zeta --refine at N = 7 cost unmeasured".
- **N1.** No change to `zeta/zeta-rs/` or to any crate template.
- **N2.** No JavaScript, web font or third-party request on the page.
- **N3.** No run output table (`zeta_1eN.txt`) is committed, apart from the N = 3 refined test fixture.
- **N4.** The deploy workflow never deletes or rewrites anything on `gh-pages` outside `zeta/`.
- **N5.** No change to the Pages source setting (stays `gh-pages /`, legacy build).
- **N6.** No absolute filesystem path appears in any committed file under `zeta/results/` or `tests/fixtures/zeta_results/`.
- **N7.** The repo never names the operator's run store location.

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

### Round 2 (all three lenses, reviewed at `66786f1`, the round-1 revision)

**Goal-Fit.**

Findings:

- (high) δ from the 15-digit `t_n` probably fails R5's exact bin equality at N = 7 (about 63%;
  modelled, and the model matched 4 of 4 flips when r5 midpoints were rounded to 10 digits).
- A&S erf vs exact erf.
- The footer SHA never lands on master after a squash-merge.
- The bin threshold contradicts N = 4 (10,141 gaps).
- S with closed brackets gives 2 and 8, not 1 and 7.
- Poisson KS, the 60-bin path and 4+ are unpinned.
- `data.json` has no reader.

Reproduced: KS, the 60→20 equality, Gram counts, g₋₁ = 9.666908 and g₀ = 17.845600.

Assumption: the N = 7 table reproduces the CLI's bins from `t_n`; removed by the midpoint fix.

**Ergonomics.**

Findings:

- (high) The same `t_n` defect: a synthetic rescale to 10^7 gave 6 flips.
- No durable store for run directories (RAM-backed scratch).
- Pyright can be silenced with an inline ignore, so the fleet notice is unnecessary.
- The run table overflows a phone.
- The 60-bin path, the Poisson KS and the curves are untested.
- `h:mm:ss` elapsed is untested.
- The fixture list named a non-existent refined N = 2.
- N6 should say "absolute".

Assumption: as Goal-Fit.

**Risk.**

Findings:

- (high) The same `t_n` defect.
- (high) The fixture `zeta_1e3.txt` is gitignored (`.gitignore:58`).
- S = 0 and the Poisson KS cannot detect a missing computation.
- The footer SHA can name a commit without the generator.
- The `h:mm:ss` format.
- The swap is not atomic, and stale siblings block it.
- A cheaper pyright fix.
- Pending-run replacement in a concurrency group.

Checked clean:

- Gram points by f64 Newton (error about 2e-9 against brackets about 1e-3).
- Privacy of the fixture `err.txt`.
- Spacings above 3 are dropped as the CLI does.

Assumption: as Goal-Fit.

Disposition: Addressed (operator, 2026-11-24: "Address all" and run store "~/zeta-runs/"). Changes:

- every compared value is computed from the exact midpoint a + (b − a)/2, using the CLI's
  A&S erf and bin rule (R5, R6, R7);
- footer SHA and `data.json` dropped; the consistency test reads `index.html` (R1, R9, R15);
- threshold example fixed;
- strict S (R7);
- pins for Poisson KS, the 60 bins, 4+, synthetic S and both elapsed formats (R3, R15);
- inline pyright ignore replaces the fleet notice (R13; V5 removed);
- `.gitignore` negation and test (R19);
- tables scroll (R9);
- swap ordering and stale-sibling cleanup;
- job-level concurrency, with pending replacement accepted (R11, R12);
- durable run store outside the repo, never named in it (N7).

Stopping signal for the lens loop:

- the round-2 findings sit in reproduction precision and test apparatus, not in the design's
  premises;
- the round-2 corrections removed surface: `data.json`, the footer SHA and the fleet notice.

So the next step is Step 8.5, not a third lens round.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.

## External Review

### Round 1 (reviewed at `72d375b2d90cc069775faeb86f29b9eb0d8720b4`)

Report: [round1.md](2026-11-24-zeta-results-page-design.external-review/round1.md)

#### Author response

| finding | disposition | evidence | reviewer verdict | operator (Step 9) |
| ------- | ----------- | -------- | ---------------- | ----------------- |
| F1.1 | Fixed | S now uses an absolute 1e-8 endpoint tolerance (Computations, R7); Facts N = 5 S is 6, the reviewer's measured value under that rule; R15 adds the width-2e-5 straddle near 9.2·10^4 (S = 1) and a 5e-9 end (S = 0) | unjudged | approved 2026-11-24 ("Spec approved") |
| F1.2 | Fixed | Facts "Run storage" now states r6 and r7 are in flight in scratch, move to the store on completion, and that a loss blocks R18 until re-run, to be stated in the plan before Phase 2. R18 unchanged: r6 was running under `/usr/bin/time -v` at review time and r7 is queued behind it | unjudged | approved 2026-11-24 ("Spec approved") |
| F1.3 | Fixed | Testing gains an AST import test; R15 covers it; the Dependencies sentence now says `test_root_python_deps.py` skips the guarded import | unjudged | approved 2026-11-24 ("Spec approved") |
| F1.4 | Fixed | Adopted: each run's `out.txt` and `err.txt` committed under `zeta/results/runs/<id>/` with the path reduced (R20); the CI consistency test regenerates the counts table, run table and CLI gap count, bins and KS from them and compares with `index.html` (R15); weighed under Approach | unjudged | approved 2026-11-24 ("Spec approved") |
| F1.5 | Fixed | The Facts Gram header now names the 1e-8 rule and the N = 5 value is 6 (with F1.1) | unjudged | approved 2026-11-24 ("Spec approved") |

Stopped: reviewer recommended stopping in round 1

