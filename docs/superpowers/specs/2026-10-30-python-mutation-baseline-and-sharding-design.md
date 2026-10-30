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
0.6 s, its jobs average 6.6 s. 19 of the 240 sampled jobs hit the 60 s cosmic-ray timeout, and all
19 timed out again when re-run serially on an idle `claude`, so they are deterministic (Design
3). They dominate the cost where they occur: 420 of sq's 450 sampled seconds. A timeout costs
60 s on any runner, so that share of the estimate does not scale with runner speed.

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
and a label (`<dir>-<k>` in CI, `@CRATE@` locally), it reads `work_items` (K) and `work_results`
and prints one line:

`green: pi-3 — S surviving, T timed out, K jobs`

cosmic-ray stores its enums by member **name**: the columns hold `NORMAL`, `KILLED`,
`SURVIVED`, never the lowercase values. Measured on the 8 sample sessions: `'SURVIVED'` matches
12, 17, 13, 4, 6, 4, 9 and 7 rows, `'survived'` matches 0 in every one. S counts
`test_outcome = 'SURVIVED'`; T counts `test_outcome = 'KILLED'` rows whose `output` is
`timeout`.

It prints `red:` and exits non-zero when `K == 0`, the number of result rows differs from `K`,
or any row has a `worker_outcome` other than `NORMAL` or a `test_outcome` other than `KILLED` or
`SURVIVED` (`INCOMPETENT`, `EXCEPTION`, `ABNORMAL`, NULL). Those are jobs that ran no test, and
counting them as results would read green over work not done.

Timeouts are reported, never a fault. cosmic-ray 8.7.0 scores a timeout as a kill
(`cosmic_ray/testing.py:71-74` returns `(TestOutcome.KILLED, "timeout")`), and that is correct
for these mutants: 19 of the 240 sampled jobs timed out (sq 7, collatz 4, pi 3, fib 3, e 1,
perfect-numbers 1), and all 19 timed out again when re-run serially on an idle `claude`. They
are deterministic non-terminating or blow-up mutants (`Mul→Pow`, `AddNot`, `NumberReplacer`
and similar). A slower runner could in principle push a survivor past 60 s, but the slowest
unmutated test run is 5.6 s (e); a month-over-month jump in T in the survivor report is the
signal for that. Survivors never make a cell red either (N3).

The local `mutants` recipe ends by running this script with label `@CRATE@`, so a local run
gets the same verdict line as CI.

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
  `make -C <dir> mutants MUTANT_SHARD=<k>/10 CELL_LABEL=<dir>-<k>` (the recipe's final
  `cosmic_ray_cell_status.py` line goes to `status/<dir>-<k>` and the step summary).
- An `if: always()` step writes `red: <dir>-<k> — make mutants failed (exit N)` to
  `status/<dir>-<k>` when `make` failed before printing a verdict line. A baseline failure, the
  failure this spec exists for, then reaches notify as a named red unit, not as a missing one.
- Each cell uploads two artifacts: `mutants-status-python-<dir>-<k>` (`status/`, `marker/`) and
  `mutants-report-python-<dir>-<k>` (that cell's session and `mutants-report.txt`). Only the
  status artifacts are merged downstream. Status files never share a path; every cell's
  `marker/job-began` does, and any one copy serves its purpose (a cell began). The reports stay
  one artifact per cell; `gh run download <id> --pattern 'mutants-report-python-pi-*'` fetches
  a sub-project's ten in one command.

### 5. Notify and the survivor report

- `notify` downloads `pattern: mutants-status-python-*` with `merge-multiple: true`.
- `scripts/mutation-notify.sh` gains an optional `EXPECTED_STATUS_UNITS`, set from
  `needs.setup.outputs.units`. When the variable is set, the check runs **before** the
  `RESULT == success` early return: if it is empty, or any named unit has no `status/<unit>`
  file, it files or comments on the failure issue as for any red run, naming the missing units,
  and then exits 1 so the run itself ends red. This is the one case the check can turn red on
  its own: `RESULT == success` with an incomplete download (the download step is
  `continue-on-error`). When the variable is unset (the Rust workflow), behaviour is unchanged.
- A new step in `notify`, `scripts/mutation-survivor-report.sh`, is the consumer of the counts.
  It sums the status lines per sub-project into a table (sub-project, cells reporting of
  expected, jobs, survivors, timed out), writes it to the step summary, and posts it as a
  comment on the standing open issue labelled `mutation-report-python`, creating that issue if
  none is open. The comment header states the ref, the trigger event, units reporting of
  expected, and the run URL, so a branch or single-sub-project dispatch is not read as a
  monthly run. It runs whenever any status file was downloaded, success or not, and marks a
  sub-project with missing cells as incomplete. The issue's comment history is the durable
  month-over-month record. It never fails the run on survivor or timeout counts (N3).

The public repo runs about 20 jobs at once, so the estimated wall time is 35-70 min for
80 cells.

### 6. `mutation-pr.yml`: baseline only

The Python step runs `make -C <dir> mutants-baseline` for each changed sub-project and is no
longer advisory: a failure fails the step. A change to any source of the pip line or the
mutation environment (`scripts/crate_templates/python/**`, any `*-py.yml`, any Python
`<dir>/install_deps.sh`, or `mutation-pr.yml` itself) runs the baseline for all 8. A Renovate
bump of `hypothesis` or `gmpy2` is the likeliest way to break the mutation environment, and it
touches no sub-project `.py`. The survivor loop is removed; the monthly workflow
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

- Shard script, against the committed fib `init` sessions: for `n = 10` the shards are
  pairwise disjoint and their union is the full set; the two sessions give the same partition
  by spec key; each error input exits non-zero; an empty session exits non-zero.
- Fixtures: sqlite sessions under `tests/fixtures/cosmic_ray/`, generated by real
  `cosmic-ray init` and `exec` runs over a small fixture module (one survivor, one
  non-terminating mutant), committed together with the `regen.sh` that produced them, so root
  tests need no cosmic-ray install and every outcome string is one cosmic-ray wrote. Two
  independent `init` sessions of fib are committed for the shard determinism test.
- Cell status: the exec fixture's exact green line is pinned, with its non-zero S and T. Error
  cases copy that real session and change one thing: delete one result row (red), delete all
  work items (red), set one row's `test_outcome` to `INCOMPETENT` (red), set one
  `worker_outcome` to `EXCEPTION` (red). Because the green case runs against cosmic-ray's own
  rows, a lowercase query fails it.
- Not a cell-status case: a broken environment. It records every mutant as `KILLED` with
  empty output, which no per-row check can tell from a real kill. The baseline (R1) is the
  guard for that, which is why `mutants` runs it first.
- Recipe: in the rendered `mutants` recipe, `cosmic-ray baseline` precedes `init`, which
  precedes `exec`; `MUTANT_SHARD` invokes the shard script between `init` and `exec`; a failed
  baseline re-runs `python3 -m unittest test_@MODULE@`.
- `mutation_notify.bats`: `RESULT=success` with one expected unit missing files the issue,
  names the unit and exits 1; `EXPECTED_STATUS_UNITS` set but empty does the same; every unit
  present behaves as today; unset behaves as today. The two "as today" cases assert a specific
  output (the close-issue call on success), so a no-op script fails them.
- `mutation_survivor_report.bats` with `tests/mocks/gh`: status files for two sub-projects give
  a table whose survivor and timeout sums equal hand-computed non-zero values; the header
  carries ref, event, units and run URL; an open labelled issue gets a comment; no open issue
  creates one; a missing cell marks its sub-project incomplete.
- `mutation-pr.yml` detection: a diff touching only a pip-line source selects all 8; a diff
  touching only `fib/fib.py` selects fib; a docs-only diff selects none.
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
- **R2.** `[PR1]` `make mutants MUTANT_SHARD=k/n` runs `scripts/cosmic_ray_shard.py` on the session between `init` and `exec`; without `MUTANT_SHARD` no shard script runs; every `make mutants` ends by running `scripts/cosmic_ray_cell_status.py` with label `CELL_LABEL` (default `@CRATE@`).
- **R3.** `[PR1]` `scripts/cosmic_ray_shard.py <sqlite> <k> <n>` keeps exactly the work items whose index in the spec-key sort order is congruent to `k` mod `n`, deleting the rest from `mutation_specs` and `work_items`.
- **R4.** `[PR1]` `scripts/cosmic_ray_shard.py` exits non-zero on a missing file, a session with no work items, `n < 1`, `k` outside `[0, n)`, or a non-integer argument.
- **R5.** `[PR1]` A test against two committed fib `init` sessions shows that for `n = 10` the shards are disjoint, their union is the full set, and both sessions give the same partition.
- **R6.** `[PR1]` `scripts/cosmic_ray_cell_status.py <sqlite> <label>` prints `green: <label> — S surviving, T timed out, K jobs` and exits 0, counting S as `test_outcome = 'SURVIVED'` and T as `test_outcome = 'KILLED'` with `output = 'timeout'`; it prints `red:` and exits non-zero when `K == 0`, result rows differ from `K`, or any row is not `worker_outcome = 'NORMAL'` with `test_outcome` in `KILLED`, `SURVIVED`; timeout counts never make it red.
- **R7.** `[PR1]` Tests run the cell-status script against committed sessions written by a real `cosmic-ray exec` (with `regen.sh`), pinning the exact green line with non-zero S and T, and showing red for a deleted result row, no work items, an `INCOMPETENT` row and an `EXCEPTION` row.
- **R8.** `[PR1]` `mutation-testing-python.yml` runs one `mutants` job per sub-project and shard (8 × 10 when no input is given) with `fail-fast: false` and `timeout-minutes: 90`, each running `make -C <dir> mutants MUTANT_SHARD=<k>/10 CELL_LABEL=<dir>-<k>`, and an `if: always()` step writes `red: <dir>-<k> — make mutants failed (exit N)` to `status/<dir>-<k>` when `make` failed without writing a verdict.
- **R9.** `[PR1]` A `setup` job emits the matrix and an `units` output built from the same validated list; a `subproject` input naming no known sub-project fails it.
- **R10.** `[PR1]` Each matrix cell installs GMP and MPFR, uses `setup-python` 3.14, writes `status/<dir>-<k>`, and uploads `mutants-status-python-<dir>-<k>` and `mutants-report-python-<dir>-<k>` as separate artifacts.
- **R11.** `[PR1]` `notify` merges only the `mutants-status-python-*` artifacts and passes `needs.setup.outputs.units` as `EXPECTED_STATUS_UNITS`.
- **R12.** `[PR1]` When `EXPECTED_STATUS_UNITS` is set, `mutation-notify.sh` checks it before the `RESULT == success` return; when it is empty or any unit lacks a status file, it files or comments on the failure issue naming each missing unit and exits 1; when unset, its behaviour is unchanged.
- **R13.** `[PR1]` `scripts/mutation-survivor-report.sh` writes a per-sub-project table (cells reporting of expected, jobs, survivors, timed out) under a header giving ref, event, units reporting of expected and run URL, to the step summary and as a comment on the open `mutation-report-python` issue, creating the issue when none is open; it never exits non-zero on counts.
- **R14.** `[PR1]` `mutation-pr.yml`'s Python step runs `make -C <dir> mutants-baseline` for each changed sub-project, and for all 8 when the diff touches `scripts/crate_templates/python/`, a `*-py.yml`, a Python `<dir>/install_deps.sh` or `mutation-pr.yml`; it contains no `cosmic-ray exec` and fails the step on a non-zero exit.
- **R15.** `[PR1]` `mutation-pr.yml` installs GMP and MPFR and uses `setup-python` 3.14.
- **R16.** `[PR1]` A test asserts the Python `pip install` line in both mutation workflows is non-empty, contains `hypothesis`, and equals the `py.yml` template's line.
- **R17.** `[PR1]` `tests/test_tool_pins.py` checks every `pip install` in every workflow, skipping `-r <file>`, and requires each package as `name==X.Y.Z` with one version per package.
- **R18.** `[PR1]` `scripts.yml` installs `pip-audit==2.10.1`.
- **R19.** `[PR1]` The Backlog loses the P1 and P2 rows this spec closes and gains a row for the SIGKILL in-place-mutation hazard that notes the longer local run.
- **R20.** `[PR1]` Root `CLAUDE.md` states that Python `make mutants` runs `cosmic-ray baseline` first, that the monthly workflow runs 10 shards per sub-project and reports to the `mutation-report-python` issue, that `MUTANT_SHARD=0/10` samples locally, and that every workflow `pip install` is in pin scope.
- **V1.** Before merge, `gh workflow run mutation-testing-python.yml --ref fix/python-mutation-baseline` for the full matrix: all 80 cells finish inside 90 min and green, pi's summed survivor count is above 0, and the `mutation-report-python` issue gets the table; record the longest cell duration and timeout count per sub-project in the PR body.
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

### Round 2

Reviewed at commit: `5371b24` (all three lenses re-run: the round-1 revision changed design substance)

Goal-Fit — Finding: (1) the timeout premise was false: 19 of 240 sampled jobs timed out, so a
5% bound makes sq, collatz, pi and fib red every run; (2) the survivor predicate
`'survived'` matches 0 rows because cosmic-ray stores enum names; (3) dispatch and branch runs
also post to the report issue, mixing partial and monthly runs; (4) a baseline failure writes no
status and is reported as a missing unit. Assumption: the sampled timeouts are inherent, not
contention; settled by re-running only those jobs serially on an idle machine.
Disposition: Addressed (operator, 2026-10-30, timeouts "a": reported, never a fault). Re-run
done: all 19 timed out again, so inherent. Timeout arm removed (Design 3, R6); uppercase names
(R6) with fixtures written by real `cosmic-ray exec` (R7); comment header names ref, event,
units and run URL (R13); `if: always()` failure status (R8).

Ergonomics — Finding: (1) same enum-name defect; (2) finding a sub-project's survivors takes 10
artifact downloads and the comment has no run link; (3) local `make mutants` never applies the
cell verdict; (4) the new blocking baseline step never runs on the likeliest breakage, a pip-line
change touching no sub-project `.py`. Assumption: pi and e shards fit 90 min on `ubuntu-latest`;
settled by V1.
Disposition: Addressed (operator, 2026-10-30): run URL in the header (R13), one-command
`gh run download --pattern` documented instead of merging reports (Design 4); cell status at the
end of every `make mutants` (R2); pip-line sources run all 8 baselines (R14).

Risk — Finding: (1) same enum-name defect; (2) same false timeout premise, with sq's mutants on
lines 21-23; (3) `R == K` passes rows that ran no test (`INCOMPETENT`, `EXCEPTION`); (4) the
split status artifact breaks `attribute()`'s loop-began test so a total baseline failure is
blamed on "died before loop", and `marker/job-began` collides; (5) "reported red" in R12 did not
say the step exits non-zero. Assumption: timeouts are deterministic; settled as above.
Disposition: Addressed (operator, 2026-10-30): per-row outcome check (R6, R7); failure status
from every cell that reached `make` (R8), so no-status now means the cell never reached it;
marker collision stated as harmless (Design 4); notify exits 1 on missing units (R12).
