# Python Mutation Testing: Fail-Closed Baseline, Real Dependencies, Sharded Monthly Run

- **Date:** 2026-10-30
- **Status:** Draft
- **Related:**
  - Backlog P1 row "Python mutation workflows probably mutate nothing";
  - Backlog P2 row "pip installs outside the 16 rendered sites are unpinned";
  - spec `2026-08-01-mutation-testing-per-project-design.md` (the Rust per-project mutation design);
  - ADR-0032 (per-project files rendered from templates); operator rule that all projects are treated identically.

## Problem

Both Python mutation workflows report green over work they never did.

`mutation-testing-python.yml` and `mutation-pr.yml` install only `cosmic-ray` (unpinned).
Every `test_*.py` imports `hypothesis`, and pi, e and factorial also import `mpmath` and
`gmpy2`. `cosmic-ray exec` runs no baseline, so each mutant's test run dies on the import
error and is recorded as `KILLED`.

Reproduced three ways on 2026-10-30 (master `8b4d1c6`):

- **CI.** Run 36822632196 (2026-10-01) reported "0 surviving mutants" for all 8 sub-projects,
  5,346 jobs in total, with fib finishing in 18 s. The log has no `hypothesis` install.
- **Local, broken environment.** fib in a venv holding only `cosmic-ray`: the unmutated test
  command fails with `ModuleNotFoundError: hypothesis`, all 232 mutants come back `KILLED` with
  empty output, and `cosmic-ray exec` exits 0.
- **Local, positive control.** The same fib tree with the pinned `py.yml` package set: 41
  survivors in the first 209 jobs (19.6%). The real figure is non-zero.

`cosmic-ray baseline cosmic-ray.toml` already exists in cosmic-ray 8.7.0 and fails closed:
it exits 1 without the dependencies and 0 with them (measured on fib). No custom baseline
check is needed.

### Installing the dependencies alone turns fake green into a timeout

Measured on `claude` (Threadripper 3960X), Python 3.14.8 with the pinned `py.yml` set, a
random 30-job sample per sub-project (`random.seed(1)`), all 8 samples running concurrently
on 48 threads. Population: one machine, 30 of N jobs per sub-project; the totals are the
sample rate times the full job count from a fresh `cosmic-ray init`, not a full run.

| sub-project     | jobs | s/job | est. serial total | sample survivors |
| --------------- | ---: | ----: | ----------------: | ---------------: |
| pi              | 1859 |  10.4 |             5.4 h |            12/30 |
| e               | 1648 |   7.4 |             3.4 h |            17/30 |
| collatz         |  421 |   8.7 |              61 m |            13/30 |
| sq              |  164 |  15.0 |              41 m |             4/30 |
| perfect-numbers |  679 |   2.5 |              28 m |             6/30 |
| fib             |  232 |   6.6 |              26 m |             4/30 |
| factorial       |  500 |   0.5 |               4 m |             9/30 |
| amicable        |  234 |   0.8 |               3 m |             7/30 |

The sum is about 11.5 h of serial compute. The current workflow runs all 8 in one job under
`timeout-minutes: 120`, and GitHub caps any job at 6 h, so pi alone cannot finish in one job.
cosmic-ray's `local` distributor is serial (`cosmic_ray/distribution/local.py` loops over the
pending work one item at a time). The unmutated test run does not predict job cost: fib's takes
0.6 s, its jobs average 6.6 s. No sampled job hit the 60 s cosmic-ray timeout.

`mutation-pr.yml` has a 30-minute limit and runs every mutant of each changed sub-project, so
with real dependencies a PR touching pi could never finish.

### The pin gap

`tests/test_tool_pins.py` checks `pip install` lines only in the 8 `*-py.yml` workflows and the
8 Python `install_deps.sh`. Three workflow sites are unpinned: `pip install cosmic-ray` in both
mutation workflows and `pip-audit` in `scripts.yml`. The `defusedxml==0.7.1` lines in the 11
`*-rs.yml` are pinned but unscanned.

## Design

### 1. Template `mutants` recipe (rendered to all 8)

`scripts/crate_templates/python/Makefile` gains a `mutants-baseline` target:

```make
mutants-baseline:
	cosmic-ray baseline cosmic-ray.toml || { python3 -m unittest test_@MODULE@; exit 1; }
```

`mutants` depends on it, so a broken environment fails before `cosmic-ray init`, locally and in
CI alike. The re-run is there for the log: `cosmic-ray baseline` prints only
`Baseline failed. Execution with no mutation gives those following errors:` followed by an empty
block when the cause is an import error (measured on fib in a venv without `hypothesis`), while
`python3 -m unittest test_fib` prints the `ImportError`. The re-run command is the same
`test-command` that `cosmic-ray.toml` holds; both are rendered from `@MODULE@`.

`mutants` accepts an optional `MUTANT_SHARD=k/n`. When set, it runs
`python3 ../scripts/cosmic_ray_shard.py cosmic-ray-session.sqlite k n` between `init` and
`exec`. When unset the recipe behaves as today: full session, serial. `MUTANT_SHARD=0/10` is
also the local way to sample a sub-project in about a tenth of the full time.

### 2. `scripts/cosmic_ray_shard.py`

Deletes every work item outside shard `k` of `n` from a freshly initialised session.

The partition key is the mutation spec, not `job_id`: `job_id` is a fresh UUID on every
`init`, and each shard runs its own `init`. Rows of `mutation_specs` are sorted by
`(module_path, operator_name, operator_args, occurrence, start_pos_row, start_pos_col,
end_pos_row, end_pos_col)`; row `i` belongs to shard `i % n`. Round-robin spreads a run of
expensive mutations in one function across shards rather than handing them all to one.

It deletes the dropped rows from `mutation_specs` and `work_items` in one transaction and
prints `kept K of T`. It exits non-zero when the file is missing, the session has no work
items, `n < 1`, `k` is outside `[0, n)`, or either argument is not an integer.

### 3. `scripts/cosmic_ray_cell_status.py`: one verdict per cell

Replaces the inline `cr-report | grep -c 'Outcome.SURVIVED'` verdict. Given a finished session
and a label (`<dir>-<k>`, or `<dir>` locally), it reads `work_items` (K), `work_results` (R),
survivors (S, `test_outcome = 'survived'`) and timeouts (T, a killed result whose `output` is
`timeout`), and prints one line:

`green: pi-3 — S surviving, T timed out, K jobs`

It prints `red:` and exits non-zero when `K == 0`, `R != K` (some job produced no result), or
`T` exceeds 5% of `K`. The timeout arm exists because cosmic-ray 8.7.0 scores a timeout as a
kill (`cosmic_ray/testing.py:71-74` returns `(TestOutcome.KILLED, "timeout")`), so on a slower
runner a survivor that runs past 60 s would otherwise read as caught. No sampled job hit 60 s on
`claude`; the runner is unmeasured. Survivors themselves never make a cell red (N3).

### 4. `mutation-testing-python.yml`: a matrix of sub-project × shard

- A `setup` job validates the sub-project list (the 8, or the `subproject` dispatch input; an
  unknown name fails the job) and emits two outputs: the matrix, and `units`, the
  space-separated `<dir>-<k>` names it expects. Both are built from the same validated list
  × shards `0..9` inside `setup`. The existing empty-list guard moves here.
- `mutants` runs per cell with `strategy.fail-fast: false` and `timeout-minutes: 90`.
  Ten shards puts pi at about 32 min a shard on `claude`, so 90 is roughly a 2.8× margin for a
  runner core of unknown speed. The shard count and timeout are the same for all 8
  sub-projects (operator rule), though amicable's shards are trivial.
- Each cell installs GMP and MPFR (`apt-get`), runs `setup-python` 3.14, installs with a
  `pip install` line byte-identical to the `py.yml` template's, runs
  `make -C <dir> mutants MUTANT_SHARD=<k>/10`, then `cosmic_ray_cell_status.py`, writing its
  line to `status/<dir>-<k>` and the step summary.
- Each cell uploads two artifacts: `mutants-status-python-<dir>-<k>` (`status/`, `marker/`) and
  `mutants-report-python-<dir>-<k>` (that cell's session and `mutants-report.txt`). Only the
  status artifacts are merged downstream, so no two merged files share a path; the reports stay
  one artifact per cell.

### 5. Notify and the survivor report

- `notify` downloads `pattern: mutants-status-python-*` with `merge-multiple: true`.
- `scripts/mutation-notify.sh` gains an optional `EXPECTED_STATUS_UNITS`, set from
  `needs.setup.outputs.units`. When the variable is set, the check runs **before** the
  `RESULT == success` early return: if it is empty, or any named unit has no `status/<unit>`
  file, the run is reported red and the missing units are named. This is the one case the
  check can turn red on its own: `RESULT == success` with an incomplete download (the download
  step is `continue-on-error`). When the variable is unset (the Rust workflow), behaviour is
  unchanged.
- A new step in `notify`, `scripts/mutation-survivor-report.sh`, is the consumer of the counts.
  It sums the status lines per sub-project into a table (sub-project, cells reporting of
  expected, jobs, survivors, timed out), writes it to the step summary, and posts it as a
  comment on the standing open issue labelled `mutation-report-python`, creating that issue if
  none is open. It runs whenever any status file was downloaded, success or not, and marks a
  sub-project with missing cells as incomplete. The issue's comment history is the durable
  month-over-month record. It never fails the run on survivor counts (N3).

The public repo runs about 20 jobs at once, so the estimated wall time is 35-70 min for
80 cells.

### 6. `mutation-pr.yml`: baseline only

The Python step runs `make -C <dir> mutants-baseline` for each changed sub-project and is no
longer advisory: a failure fails the step. The survivor loop is removed; the monthly workflow
is the measurement. The job gains the GMP and MPFR step, moves `setup-python` from 3.11 to
3.14, and installs the same pip line as `py.yml` alongside the pinned `cargo-mutants`.

What this catches that `py.yml` does not: cosmic-ray runs `python3 -m unittest`, `py.yml` runs
pytest, so a test relying on a pytest-only feature passes `py.yml` and breaks every mutation
run; and it proves the mutation environment itself (cosmic-ray plus the pinned set) on each
Python PR.

### 7. Pins

- `test_tool_pins.py` scans every `pip install` in every workflow, skipping a `-r <file>`
  argument (`requirements-dev.txt` is already exact-pinned). Every package must be
  `name==X.Y.Z`, one version per package repo-wide.
- `scripts.yml` pins `pip-audit==2.10.1`, the version every other site uses.
- A new test asserts both mutation workflows' Python `pip install` line is non-empty, contains
  `hypothesis`, and equals the `py.yml` template's. One-version-per-package alone would not
  catch a missing `hypothesis`, which is this bug.

### Testing

- Shard script, against a real `cosmic-ray init` session of fib: for `n = 10` the shards are
  pairwise disjoint and their union is the full set; two separate `init` runs give the same
  partition by spec key; each error input exits non-zero; an empty session exits non-zero.
- Cell status, against hand-built sessions: a specific session with K=20, S=3, T=1 prints
  exactly `green: fib-0 — 3 surviving, 1 timed out, 20 jobs`; K=0, R<K and T=2 of K=20 (10%)
  are each red; T=1 of K=20 (5%) is green.
- Recipe: in the rendered `mutants` recipe, `cosmic-ray baseline` precedes `init`, which
  precedes `exec`; `MUTANT_SHARD` invokes the shard script between `init` and `exec`; a failed
  baseline re-runs `python3 -m unittest test_@MODULE@`.
- `mutation_notify.bats`: `RESULT=success` with one expected unit missing is red and names it;
  `EXPECTED_STATUS_UNITS` set but empty is red; every unit present behaves as today; unset
  behaves as today.
- `mutation_survivor_report.bats` with `tests/mocks/gh`: status files for two sub-projects give
  a table whose survivor sums equal the hand-computed values; an open labelled issue gets a
  comment; no open issue creates one; a missing cell marks its sub-project incomplete.
- Workflow structure tests read the YAML with `yaml.safe_load`, as `test_release_workflows.py`
  does.

## Out of scope

- A SIGKILL during a local `make mutants` leaves the source mutated in place: cosmic-ray
  restores the file only on a normal exit. The 2026-10-30 reproduction's `timeout` left
  `fib/fib.py` in its scratch copy with `a + b` changed to `a * b`. CI runners are discarded,
  so only local runs are exposed, and the exposure grows now that a real local run of pi takes
  hours rather than seconds. Goes to the Backlog.
- Resuming an interrupted local run: the recipe's `rm -f` before `init` discards cosmic-ray's
  resume. Unchanged here.
- cosmic-ray's `http` distributor with several workers per job: needs a separate source copy
  per worker and is capped at the runner's vCPU count. Rejected in favour of matrix shards.

## Requirements

- **R1.** `[PR1]` The Python template `Makefile` has a `mutants-baseline` target running `cosmic-ray baseline cosmic-ray.toml` and, when it fails, `python3 -m unittest test_@MODULE@` before exiting non-zero; `mutants` runs it before `cosmic-ray init`, in all 8 rendered copies.
- **R2.** `[PR1]` `make mutants MUTANT_SHARD=k/n` runs `scripts/cosmic_ray_shard.py` on the session between `init` and `exec`; without `MUTANT_SHARD` no shard script runs.
- **R3.** `[PR1]` `scripts/cosmic_ray_shard.py <sqlite> <k> <n>` keeps exactly the work items whose index in the spec-key sort order is congruent to `k` mod `n`, deleting the rest from `mutation_specs` and `work_items`.
- **R4.** `[PR1]` `scripts/cosmic_ray_shard.py` exits non-zero on a missing file, a session with no work items, `n < 1`, `k` outside `[0, n)`, or a non-integer argument.
- **R5.** `[PR1]` A test shows that for `n = 10` the shards of a real fib session are disjoint, their union is the full set, and two independent `init` runs give the same partition.
- **R6.** `[PR1]` `scripts/cosmic_ray_cell_status.py <sqlite> <label>` prints `green: <label> — S surviving, T timed out, K jobs` and exits 0, or prints `red:` and exits non-zero when `K == 0`, results differ from `K`, or timeouts exceed 5% of `K`.
- **R7.** `[PR1]` A test pins the exact green line for a session with K=20, S=3, T=1, and shows T=1 of 20 green and T=2 of 20 red.
- **R8.** `[PR1]` `mutation-testing-python.yml` runs one `mutants` job per sub-project and shard (8 × 10 when no input is given) with `fail-fast: false` and `timeout-minutes: 90`, each running `make -C <dir> mutants MUTANT_SHARD=<k>/10` then `cosmic_ray_cell_status.py`.
- **R9.** `[PR1]` A `setup` job emits the matrix and an `units` output built from the same validated list; a `subproject` input naming no known sub-project fails it.
- **R10.** `[PR1]` Each matrix cell installs GMP and MPFR, uses `setup-python` 3.14, writes `status/<dir>-<k>`, and uploads `mutants-status-python-<dir>-<k>` and `mutants-report-python-<dir>-<k>` as separate artifacts.
- **R11.** `[PR1]` `notify` merges only the `mutants-status-python-*` artifacts and passes `needs.setup.outputs.units` as `EXPECTED_STATUS_UNITS`.
- **R12.** `[PR1]` When `EXPECTED_STATUS_UNITS` is set, `mutation-notify.sh` checks it before the `RESULT == success` return and reports red, naming each missing unit, when it is empty or any unit lacks a status file; when unset, its behaviour is unchanged.
- **R13.** `[PR1]` `scripts/mutation-survivor-report.sh` writes a per-sub-project table (cells reporting of expected, jobs, survivors, timed out) to the step summary and comments it on the open `mutation-report-python` issue, creating the issue when none is open.
- **R14.** `[PR1]` `mutation-pr.yml`'s Python step runs `make -C <dir> mutants-baseline` for each changed sub-project, contains no `cosmic-ray exec`, and fails the step on a non-zero exit.
- **R15.** `[PR1]` `mutation-pr.yml` installs GMP and MPFR and uses `setup-python` 3.14.
- **R16.** `[PR1]` A test asserts the Python `pip install` line in both mutation workflows is non-empty, contains `hypothesis`, and equals the `py.yml` template's line.
- **R17.** `[PR1]` `tests/test_tool_pins.py` checks every `pip install` in every workflow, skipping `-r <file>`, and requires each package as `name==X.Y.Z` with one version per package.
- **R18.** `[PR1]` `scripts.yml` installs `pip-audit==2.10.1`.
- **R19.** `[PR1]` The Backlog loses the P1 and P2 rows this spec closes and gains a row for the SIGKILL in-place-mutation hazard that notes the longer local run.
- **R20.** `[PR1]` Root `CLAUDE.md` states that Python `make mutants` runs `cosmic-ray baseline` first, that the monthly workflow runs 10 shards per sub-project and reports to the `mutation-report-python` issue, that `MUTANT_SHARD=0/10` samples locally, and that every workflow `pip install` is in pin scope.
- **V1.** Before merge, `gh workflow run mutation-testing-python.yml --ref fix/python-mutation-baseline` for the full matrix: all 80 cells finish inside 90 min, no cell exceeds the 5% timeout bound, pi's summed survivor count is above 0, and the `mutation-report-python` issue gets the table; record the longest cell duration and timeout count per sub-project in the PR body.
- **V2.** Locally, `make -C fib mutants-baseline` in a venv without `hypothesis` exits non-zero and its output contains `ImportError`; with the `py.yml` set it exits 0.
- **V3.** Locally, the exact `mutation-pr.yml` Python step command for fib, in a fresh venv built from the workflow's pip line, exits 0.
- **N1.** No change to any `cosmic-ray.toml` `test-command` or `timeout`.
- **N2.** No sub-project gets a different shard count or timeout from the others.
- **N3.** No survivor count gates any workflow or PR.
- **N4.** No change in behaviour of the Rust `mutation-testing.yml` or its use of `mutation-notify.sh`.
- **N5.** No use of cosmic-ray's `http` distributor.
- **N6.** No diff-scoped Python mutation in `mutation-pr.yml`.

## Multi-Lens Review

Reviewed at commit: `d8e8e94` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: (1) The sharded matrix fails the reads-it test. Survivor counts land only in per-cell
step summaries and a 30-day artifact; `mutation-notify.sh` never reads them (0 hits for
`surviv`), N3 forbids gating on them, and no commit since 2026-06-01 acted on a Python survivor
count. The matrix's only verdict-changing outputs are a baseline failure, a timeout or a dead
runner, and R1 and R11 already catch the first. Either name a consumer, or split: PR1 = R1 and
R11-R17 (the fail-closed fix), PR2 = sharding once a consumer exists. (2) R1 alone turns fake
green into honest red; an unsharded pi then times out red rather than green. (3) R11's stated
gap (a test that passes under pytest and fails under unittest) is caught in seconds by adding
`python3 -m unittest test_@MODULE@` to the `py.yml` template, without installing cosmic-ray in
`mutation-pr.yml`. Verification cases judged adequate. Premise verified: four monthly runs
(July-October), all `success` at about 11 min.
Assumption: someone acts on monthly Python survivor counts. Settled by asking the operator what
reads the per-sub-project number and what decision it feeds.
Disposition: Addressed (operator, 2026-10-30: "Keep, add consumer"): the matrix stays and gains a consumer, `mutation-survivor-report.sh`, which posts the per-sub-project table to the standing `mutation-report-python` issue (Design 5, R13). Item 3 Accepted, reason: operator kept the 2a baseline in `mutation-pr.yml` ("Keep 2a baseline"), since it also proves the mutation environment per PR.

### Ergonomics

Finding: (1) A red `cosmic-ray baseline` gives no cause: it prints `Baseline failed` and an
empty `>>>` block, because `result.output` is empty for an import error (verified in a scratch
venv); running `python3 -m unittest test_fib` shows the `ImportError`. Re-run the test command
on failure. (2) No run-level survivor total: reading a monthly run means 80 cell summaries, and
`merge-multiple` overwrites the same-path `mutants-report.txt` and session files, keeping one
shard in ten. The status line also lacks the shard id. (3) A shortfall names a count, not the
missing `<dir>-<k>` cells; an empty `EXPECTED_STATUS_COUNT` silently behaves as unset. (4)
Locally a real run is hours long, not resumable (`rm -f` before `init`) and not parallel in one
checkout; document `MUTANT_SHARD=0/10` as the local sampling path and note the larger SIGKILL
exposure in the Backlog row. (5) R13 passes if both lines are empty; require non-empty and
containing `hypothesis`.
Assumption: the `claude`-measured s/job holds on `ubuntu-latest` within the 2.8x margin. Settled
by `gh workflow run mutation-testing-python.yml --ref <branch> -f subproject=pi` before merge.
Disposition: Addressed (operator, 2026-10-30): baseline failure re-runs the test command (R1, V2); status artifacts split from report artifacts and summed into a run-level table (R10, R11, R13); missing units named and empty-set is red (R12); `MUTANT_SHARD=0/10` documented (R20) and the Backlog row notes the longer local run (R19); R16 requires a non-empty line containing `hypothesis`; V1 moved before merge.

### Risk

Finding: (1) A timeout counts as a kill: cosmic-ray 8.7.0 `testing.py:71-74` returns
`(TestOutcome.KILLED, "timeout")` (verified). On a slower runner, survivors past 60 s score as
caught, and V1's "pi survivors > 0" still passes. Count `output = 'timeout'` rows per cell, put
it in the status line, and go red above a stated fraction; also assert per cell that result rows
equal `kept K` and `K > 0`. (2) `EXPECTED_STATUS_COUNT` cannot change a verdict where placed:
`main()` returns on `RESULT == success` (line 104) before reading status files, and a dead cell
already makes `RESULT` a failure. The case it can catch is `RESULT=success` with an incomplete
download, so the check must run before the early return, with a bats case for it. (3) The
expected count must be derived in `setup` from the validated list x 10, not from the emitted
matrix (self-comparison) or a literal 80 (single-sub-project dispatch always red). (4)
`merge-multiple` drops 9 of 10 report files per sub-project (same as Ergonomics 2). Matrix plus
shard script judged proportionate; a blocking baseline step judged low risk. Premise verified:
run 36822632196 log has 0 `hypothesis` matches and prints `surviving mutants: 0` for every
sub-project.
Assumption: on `ubuntu-latest` no meaningful fraction of mutant runs exceeds 60 s. Settled by a
pre-merge dispatch for pi and sq, then counting `output='timeout'` rows in the uploaded session.
Disposition: Addressed (operator, 2026-10-30): per-cell timeout count with red above 5% and results == K > 0 (Design 3, R6, R7); unit check before the success return (R12) with units derived in `setup` from the validated list (R9); per-cell artifacts no longer collide (R10, R11); V1 runs before merge and records timeouts.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
