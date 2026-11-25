# zeta Results Page Implementation Plan

spec: docs/superpowers/specs/2026-11-24-zeta-results-page-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A static, script-generated page at `brujack.github.io/math/zeta/` showing zeta's verified counts, gap histograms against Wigner and Poisson, and Gram's law, with every value cross-checked against the CLI's own output.

**Architecture:** `scripts/zeta_results.py` (stdlib plus matplotlib) parses run directories (`out.txt`, `err.txt`, refined `zeta_1eN.txt`) and the committed `zeta/results/runs.toml`, checks everything fail-closed, and writes `zeta/results/site/` plus copies of each run's `out.txt`/`err.txt` under `zeta/results/runs/<id>/`. A dispatch-only workflow copies the site into `gh-pages` `zeta/`.

**Tech Stack:** Python 3.14 (CI) / 3.15 (local), matplotlib 3.11.2, `tomllib`, unittest, bats, GitHub Actions.

## Global Constraints

- The spec's effective Requirements block (`python3 ~/.claude/scripts/spec_contract.py docs/superpowers/specs/2026-11-24-zeta-results-page-design.md`) is the contract.
- Every value compared with the CLI comes from the f64 midpoint `a + (b - a)/2` of the parsed 30-digit `a`, `b` columns, never from `t_n`; δ is `(m1 - m0) * math.log(m0 / math.tau) / math.tau` in that order.
- erf for the Wigner CDF is Abramowitz–Stegun 7.1.26, ported from `zeta/zeta-rs/src/spacing.rs` `erf`; `wigner_cdf` mirrors its expression order.
- Third-party imports in `scripts/zeta_results.py`: matplotlib only, inside `try`/`except ImportError`, with `# pyright: ignore[reportMissingImports]`.
- No change to `zeta/zeta-rs/` or any crate template (N1). No JavaScript or external request on the page (N2). No absolute path in any committed file under `zeta/results/` or `tests/fixtures/zeta_results/` (N6). The repo never names the operator's run store (N7).
- Python standards: read `~/.claude/standards/python.md` first. Shell: `~/.claude/standards/shell.md`.
- Commit messages via `caveman:caveman-commit`. The repo is public: no private paths or audit text in commits.

## Verification Planning

- **Whole change:** after Task 7, `python3 -m unittest tests.test_zeta_results -v` passes, including the consistency class against the committed site, and `make test` passes at the root.
- **Real-data proof (V2):** Task 7's generation over the operator's run store exits 0, which means every refined run N = 3–7 passed the gap-count, 20-bin and KS cross-checks against the CLI's own printed values, and every counts row reads `equal`.
- **Deploy (V1, post-merge):** `gh workflow run zeta-results-pages.yml --ref master`, then `curl -fsS https://brujack.github.io/math/zeta/` returns the page, `.../zeta/deployed-from.txt` equals the master SHA, and `.../dev/bench/` still returns 200.
- **Edge cases:** a run of an hour or more (`h:mm:ss` elapsed), spacings above 3 (dropped as the CLI does), a Gram point within 1e-8 of a bracket end, matplotlib absent outside CI, a crashed earlier run's `site.*` sibling.
- **Gate on data:** Task 7 needs `zeta 7 --refine` finished in the operator's run store (started 2026-11-24 23:56, estimated 30–45 h). Tasks 1–6 do not.

---

### Task 1: matplotlib pin, fixtures and gitignore exception

```yaml-task
id: 1
description: Pin matplotlib, add the real N=2/N=3 fixtures, and a .gitignore negation with a test that git tracks the refined fixture
role: executor
model: sonnet
tdd: required
requirements: [R13, R19]
acceptance:
  - cmd: python3 -m unittest tests.test_zeta_results.TestFixtures -v
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [requirements-dev.txt, .gitignore, tests/test_zeta_results.py, tests/fixtures/zeta_results/t2/out.txt, tests/fixtures/zeta_results/t2/err.txt, tests/fixtures/zeta_results/t3/out.txt, tests/fixtures/zeta_results/t3/err.txt, tests/fixtures/zeta_results/tr3/out.txt, tests/fixtures/zeta_results/tr3/err.txt, tests/fixtures/zeta_results/tr3/zeta_1e3.txt, tests/fixtures/zeta_results/runs.toml]
depends_on: []
```

**Files:** the orchestrator copies the fixture files into place before dispatch, from the run store's `t2`, `t3`, `tr3` (plain N = 2, plain N = 3, `--refine` N = 3 of binary f935b23 under `/usr/bin/time -v`). Their `err.txt` names the binary `../zeta-f935b23`, a relative path. Do not edit them.

- `requirements-dev.txt`: add `matplotlib==3.11.2` (sorted position).
- `.gitignore`: add `!tests/fixtures/zeta_results/**/zeta_1e3.txt` after the `zeta_1e*.txt` rule.
- `tests/fixtures/zeta_results/runs.toml`: three `[[run]]` tables, ids `t2`, `t3`, `tr3`, each `binary_sha = "f935b233046fa0905c3198efc93a15fb2412677a"`, `machine = "Threadripper 3960X, 48 threads, Ubuntu 26.04"`, `date = "2026-11-24"`.
- `tests/test_zeta_results.py`: module docstring, then class `TestFixtures`:
  - `git ls-files tests/fixtures/zeta_results/tr3/zeta_1e3.txt` prints that path (run with the repo root as cwd, `GIT_*` env stripped);
  - the fixture table's first line is `# n a b t_n w_n` and it has 649 data lines.
- RED: write the test before the `.gitignore` line and `git add`; it fails because git ignores the table.

**Interfaces:** Produces the fixture layout `tests/fixtures/zeta_results/<id>/{out.txt,err.txt[,zeta_1e3.txt]}` and `runs.toml` used by Tasks 2–4.

### Task 2: parsing and fail-closed input checks

```yaml-task
id: 2
description: Parse /usr/bin/time -v reports, out.txt, runs.toml and refined tables into typed records, failing closed with the run id named
role: executor
model: sonnet
tdd: required
requirements: [R2, R3, R4]
acceptance:
  - cmd: python3 -m unittest tests.test_zeta_results.TestParsing -v
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [scripts/zeta_results.py, tests/test_zeta_results.py]
depends_on: [1]
```

**Produces** (in `scripts/zeta_results.py`; dataclasses frozen):

- `class ResultsError(Exception)`. Its message is `"<run id>: <check>"`.
- `parse_elapsed(value: str) -> float`: accepts `m:ss.ss` and `h:mm:ss`.
- `TimeReport(n: int, refine: bool, binary_hash: str, elapsed_s: float, peak_rss_kb: int)` from `parse_time_report(text: str, run_id: str)`.
  - Reads `Command being timed: "<path>/zeta-<h> <args>"`, where `<args>` matches `^[2-7]( --refine)?$`.
  - Requires `Exit status: 0`, plus `Elapsed (wall clock) time (h:mm:ss or m:ss): <v>` and `Maximum resident set size (kbytes): <k>`.
- `OutSummary(count: int, spacings: int | None, cli_counts: tuple[int, ...] | None, cli_ks: str | None)` from `parse_out(text: str, run_id: str, n: int)`.
  - Requires `RH verified: all <L> nontrivial zeros with 0 < Im s <= <10**n> lie on Re s = 1/2 and are simple`.
  - Refined runs: parses `<k> spacings`, the 20 histogram rows (second column), and `KS distance to the Wigner surmise CDF: <x>`, which is kept as a string.
- `RunMeta(id, binary_sha, machine, date, note)` from `load_runs_toml(path) -> dict[str, RunMeta]`.
  - Keys are exactly `id`, `binary_sha` (40 hex), `machine`, `date`, and optional `note`.
- `RefinedTable(a: list[float], b: list[float], m: list[float])` from `read_refined(path, run_id: str, count: int)`.
  - Header must be `# n a b t_n w_n`, with exactly `count` lines numbered 1..count, all values finite.
  - `m` is `a + (b - a) / 2`, strictly increasing.
  - `a <= t_n <= b` within `1e-9 * abs(t_n)`.
- `check_binary(meta: RunMeta, rep: TimeReport, run_id)`: `rep.binary_hash` must equal `meta.binary_sha[:7]`.

**Tests (TestParsing):**

- On the fixtures, each parser returns the real values: tr3 count 649, spacings 648, the 20 counts, KS `"0.0448"`.
- One test per R4 failure, using `assertRaisesRegex(ResultsError, "^tr3: ")` on a copied, edited fixture:
  - no verified line;
  - `Exit status: 1`;
  - binary hash mismatch;
  - plain header on a refined table;
  - a missing line;
  - `nan`;
  - non-increasing midpoints;
  - unknown runs.toml key.
- `parse_elapsed("0:02.45") == 2.45` and `parse_elapsed("1:02:23") == 3743`.

### Task 3: computations: spacings, CLI cross-check, histograms, Gram counts

```yaml-task
id: 3
description: Spacings from exact midpoints, CLI-identical 20 bins/erf/KS cross-check, display bins, Poisson KS, Gram points and counts with strict S, published counts
role: executor
model: sonnet
tdd: required
requirements: [R5, R6, R7, R8, R15]
acceptance:
  - cmd: python3 -m unittest tests.test_zeta_results.TestComputations -v
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [scripts/zeta_results.py, tests/test_zeta_results.py]
depends_on: [2]
```

**Produces:**

- Spacing functions:
  - `spacings(m: list[float]) -> list[float]`;
  - `as_erf(x)`, a port of `spacing.rs` `erf`;
  - `wigner_pdf(s)` and `wigner_cdf(s)`, mirroring `spacing.rs`;
  - `poisson_cdf(s) = 1 - exp(-s)`;
  - `ks_distance(d, cdf) -> float`.
- Bin functions:
  - `cli_bins(d) -> list[int]`: 20 bins, `min(int(s / 0.15), 19)` for 0 <= s <= 3, with s > 3 dropped;
  - `display_bins(d, threshold: int = 10_000) -> tuple[float, list[int]]`: bin width 0.15 with 20 bins when `len(d) < threshold`, else width 0.05 with 60 bins via `min(int(s/0.05), 59)`.
- `cross_check(run_id, d, out: OutSummary, count)` raises `ResultsError` unless all three hold:
  - `len(d) == count - 1 == out.spacings`;
  - `cli_bins(d) == list(out.cli_counts)`;
  - `f"{ks_distance(d, wigner_cdf):.4f}" == out.cli_ks`.
- Gram functions:
  - `theta(t)` (spec R7 formula) and `gram_points_upto(T) -> list[float]`, from g₋₁ by Newton, stopping at the last g ≤ T;
  - `GramStats(counts: dict[int, int], share: float, straddles: int)` from `gram_stats(table, gram) -> GramStats`.
  - Zeros are assigned by `m`, and key 4 means 4 or more zeros.
  - S counts brackets with `a + 1e-8 < g < b - 1e-8` for some g.
- `PUBLISHED_COUNTS = {2: 29, 3: 649, 4: 10142, 5: 138069, 6: 1747146, 7: 21136125}`, with a comment citing OEIS A072080.

**Tests (TestComputations), values on the tr3 fixture:**

- KS 0.0448 against Wigner and 0.3260 against Poisson; 648 gaps.
- `cli_bins` = 0, 7, 26, 58, 96, 92, 109, 80, 58, 57, 28, 19, 8, 9, 1, 0, 0, 0, 0, 0.
- `display_bins(d, threshold=0)` counts = 0, 0, 0, 0, 4, 3, 3, 13, 10, 12, 22, 24, 26, 27, 43, 34, 22, 36, 37, 41, 31, 31, 19, 30, 22, 23, 13, 20, 21, 16, 8, 9, 11, 6, 5, 8, 5, 3, 0, 7, 2, 0, 0, 0, 1 followed by 15 zeros.
- Gram counts {0: 22, 1: 604, 2: 22, 3: 0, 4: 0}, share 0.9321 (4 dp), S = 0.

**Synthetic tests:**

- A bracket straddling g₀ ≈ 17.8456 gives S = 1, and one starting exactly at g₀ gives S = 0.
- Near g ≈ 9.2e4, a width-2e-5 bracket with g 1e-5 inside gives S = 1, and one whose end is 5e-9 from g gives S = 0.
- `cross_check` raises with one CLI count altered, and again with the KS string altered.
- `cli_bins([3.0, 3.1])` gives `[0]*19 + [1]`.

### Task 4: rendering, CLI entry point, run copies and determinism

```yaml-task
id: 4
description: matplotlib SVGs, index.html, run out/err copies with path stripped, atomic site swap, main() CLI, matplotlib-missing handling
role: executor
model: sonnet
tdd: required
requirements: [R1, R6, R7, R9, R10, R13, R14, R15, R20]
acceptance:
  - cmd: python3 -m unittest tests.test_zeta_results.TestRendering -v
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [scripts/zeta_results.py, tests/test_zeta_results.py]
depends_on: [3]
```

**Produces:** `main(argv: list[str] | None = None) -> int`, with
`--runs-toml <file> --run <id>=<dir> ... --out <site dir> --runs-out <runs dir>`. It runs in this order:

1. Remove stale `<out>.*` siblings.
2. Run every check from Tasks 2–3 for every run. A run id missing from the toml, or a toml entry with no `--run`, is a failure.
3. Build the counts table, the gap figures (one SVG per refined N), the Gram table, the Gram share SVG and the run table.
4. Write the site to `<out>.tmp`, then swap: rename the old site away, the new one in, and restore the old on failure.
5. Copy `out.txt` and `err.txt` to `<runs dir>/<id>/`, rewriting the `Command being timed` path to `zeta-<h>`.

On `ResultsError` it prints the message to stderr and returns 1. Without matplotlib it prints `zeta_results: matplotlib missing; run make install-deps` and returns 1.

**index.html requirements:** spec R9 in full.

- The viewport meta.
- `img{max-width:100%;height:auto}`.
- Tables inside `<div style="overflow-x:auto">`.
- `alt` on every image.
- The claim paragraph verbatim from the spec section "Claim text (exact)".
- Definitions of a Gram point and of δ.
- The Poisson-contrast sentence.
- A provenance line under each figure.
- A footer linking `deployed-from.txt`.

**SVG settings:** `metadata={"Date": None}` and `rcParams["svg.hashsalt"] = "zeta-results"`. Each figure is 6×4 in with fonts of at least 12 pt.

**Tests (TestRendering)**, using fixtures in a temp dir:

- **Smoke run:** exit 0.
- **Determinism:** two runs give byte-identical output dirs.
- **Atomic failure:** with a pre-existing site, a failing run leaves it byte-unchanged.
- **Crash leftovers:** a stale `site.tmp` is removed.
- **Page hygiene:**
  - no `<script` in the HTML;
  - no `http` in any `src` or `href`;
  - the viewport meta, the table div wrapper and the claim paragraph are present;
  - no `../zeta-f935b23` anywhere in the site.
- **SVG set:** the SVG files equal the `<img>` sources, and each SVG contains a bar path and two curve lines.
- **Run copies:** have no `../` in their command line.
- **No absolute paths (N6):** no file under `zeta/results/` or `tests/fixtures/zeta_results/` matches `(?<![\w.])/(home|tmp|Users|root|var)/`.
- **Imports:** an AST check finds that the only third-party top-level import is `matplotlib`.
- **matplotlib absent:** skip with `matplotlib not installed; run make install-deps` when the import fails and `CI` is unset; fail when `CI` is set.

### Task 5: deploy workflow, guard script, concurrency and CI paths

```yaml-task
id: 5
description: zeta-results-pages.yml (dispatch-only, master-only, concurrency gh-pages), guard script with bats test, benchmarks.yml concurrency, scripts.yml paths
role: executor
model: sonnet
tdd: required
requirements: [R11, R12, R16, R17]
acceptance:
  - cmd: bats tests/scripts/gh_pages_zeta_guard.bats
    exit_code: 0
    stdout_match: 'ok 1 '
  - cmd: python3 -m unittest tests.test_zeta_results_workflow -v
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [.github/workflows/zeta-results-pages.yml, .github/workflows/benchmarks.yml, .github/workflows/scripts.yml, scripts/gh-pages-zeta-guard.sh, tests/scripts/gh_pages_zeta_guard.bats, tests/test_zeta_results_workflow.py]
depends_on: [1]
```

**Files:**

- `scripts/gh-pages-zeta-guard.sh <gh-pages dir>`: exits 1, naming the first offending path, if any path in `git -C <dir> status --porcelain` lies outside `zeta/`. Exits 0 otherwise. Shell standards apply.
- Bats test, in a temp repo with `GIT_*` unset in `setup()`:
  - a change under `zeta/` exits 0;
  - a change to `dev/bench/x` exits 1;
  - a deletion outside `zeta/` exits 1.
- Workflow, per spec R11:
  - `on: workflow_dispatch` only;
  - job `if: github.ref == 'refs/heads/master'`;
  - `permissions: contents: write`;
  - job-level `concurrency: {group: gh-pages, cancel-in-progress: false}`;
  - steps: checkout master, then checkout `gh-pages` into `gh-pages/` (same pinned `actions/checkout` SHA as `benchmarks.yml`); `rm -rf gh-pages/zeta && cp -R zeta/results/site gh-pages/zeta`; write `gh-pages/zeta/deployed-from.txt` from `${{ github.sha }}`; run the guard; commit and push with no `--force`, only if the status is non-empty.
- `benchmarks.yml`: the same job-level concurrency.
- `scripts.yml`: add `"zeta/results/**"` to `paths`.

**Tests:** `tests/test_zeta_results_workflow.py` asserts, via `yaml.safe_load`:

- the trigger keys are exactly `{"workflow_dispatch"}`;
- the job `if` is the master ref;
- both workflows' jobs have concurrency group `gh-pages` with cancel false;
- no `--force` appears in the run text;
- `scripts.yml` paths include `zeta/results/**`.

### Task 6: ADR and docs

```yaml-task
id: 6
description: ADR-0047 for publishing zeta results on gh-pages from a local generator; zeta README/CLAUDE.md usage; ADR index (docs-only, no behaviour change)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: test -f docs/adr/0047-zeta-results-page-on-gh-pages.md
    exit_code: 0
  - cmd: 'grep -qE "0047" docs/adr/README.md'
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 2
files_touched: [docs/adr/0047-zeta-results-page-on-gh-pages.md, docs/adr/README.md, zeta/README.md, zeta/CLAUDE.md]
depends_on: [4, 5]
```

**Content:**

- **ADR-0047.** Context, Decision, Consequences and Related, in the same shape as ADR-0046.
  - Context: data too large for CI, and Pages on legacy `gh-pages`.
  - Decision: a local generator and a committed site, deployed by dispatch-only copy into `gh-pages/zeta/` under a shared `gh-pages` concurrency group.
  - Consequences: page figures are operator-attested and CLI-cross-checked, and CI re-verifies the tables derived from the committed `out.txt`/`err.txt`.
- **zeta/README.md:** a "Results page" section covering how to regenerate (`python3 scripts/zeta_results.py --runs-toml zeta/results/runs.toml --run <id>=<dir> ... --out zeta/results/site --runs-out zeta/results/runs`), the `/usr/bin/time -v` requirement, and how to deploy (`gh workflow run zeta-results-pages.yml --ref master`). It must name no machine path.
- **zeta/CLAUDE.md:** one line pointing to `scripts/zeta_results.py` and `zeta/results/`.

The orchestrator runs `make test` after this task. No file here is read by the suite.

### Task 7 (orchestrator): generate the real site after `zeta 7 --refine`

```yaml-task
id: 7
description: Generate and commit the real site, runs.toml and run copies from the operator's run store, add the CI consistency test, record V2/V4 (gated on zeta 7 --refine finishing)
role: executor
model: sonnet
tdd: required
requirements: [R15, R18, R20]
acceptance:
  - cmd: python3 -m unittest tests.test_zeta_results.TestCommittedSiteConsistency -v
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 2
files_touched: [zeta/results/runs.toml, zeta/results/site, zeta/results/runs, tests/test_zeta_results.py, docs/superpowers/README.md, docs/superpowers/specs/2026-11-24-zeta-results-page-design.md]
depends_on: [4, 5, 6]
```

**Precondition:** the run store's `r7/rc.txt` reads `rc=0`. If r7 failed or was lost, stop and report to the operator. R18 cannot be met until it is re-run.

**Steps:**

1. Write `zeta/results/runs.toml` with eleven entries, all `binary_sha` f935b23… and date 2026-11-24:
   - plain `t2 t3 t4 n5 n6 n7`;
   - refined `tr3 tr4 r5 r6 r7`.

   Add a `note` on r5–r7 and n5–n7: "machine also running other jobs".

2. Run the generator over those eleven directories. It must exit 0. That exit code is V2: every refined cross-check passed and every counts row reads `equal`.
3. RED: add `TestCommittedSiteConsistency`, which fails before the site is committed. From `zeta/results/runs.toml` and `zeta/results/runs/<id>/` only, it rebuilds the counts table, the run table and each refined run's CLI gap count, 20 counts and KS. Each must equal what `zeta/results/site/index.html` shows, with no extra run.
4. Commit the site, the copies, the toml and the test.
5. Record V4 (N = 6 and N = 7 `--refine` elapsed and peak RSS) in the spec's Verifications. Remove the Backlog row "zeta --refine at N = 7 cost unmeasured" from `docs/superpowers/README.md`.

**After merge (orchestrator, V1):** dispatch the workflow and run the three checks in Verification Planning.

## Non-goal check

Run on 2026-11-25 by a fresh reviewer against N1–N7. Every verdict is CLEAR, with 0 CONFLICT and 0 UNCLEAR. The reviewer's advisory notes:

- **N6:** nothing checked for an absolute path in the committed `out.txt`/`err.txt`, beyond the `../` command-line check.
  - Resolution: the plan revises Task 4's tests.
  - Before: "Run copies: have no `../` in their command line."
  - After: that line, plus a check that no file under `zeta/results/` or `tests/fixtures/zeta_results/` matches `(?<![\w.])/(home|tmp|Users|root|var)/`.
- **N3:** the `.gitignore` negation matches any fixture directory's `zeta_1e3.txt`.
  - It still admits N = 3 tables only, inside the stated exception.
  - No change.

