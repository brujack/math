# Mutation Testing — Make It Work, Then Make It Parallel

**Date:** 2026-08-01
**Status:** Spec (pending plan) — Phase A

## Problem

`mutation-testing.yml` has **never passed**. All six runs since inception failed:

| Run         | Date       | Trigger           | Outcome |
| ----------- | ---------- | ----------------- | ------- |
| 30685027791 | 2026-08-01 | schedule          | failure |
| 28495704109 | 2026-07-01 | schedule          | failure |
| 26766884122 | 2026-06-01 | workflow_dispatch | failure |
| 26760109155 | 2026-06-01 | workflow_dispatch | failure |
| 26756239200 | 2026-06-01 | workflow_dispatch | failure |
| 26737080954 | 2026-06-01 | schedule          | failure |

Every failure has the same signature — the GitHub-hosted runner is terminated mid-job:

```
ERROR interrupted
ERROR scenario execution internal error err=interrupted phase=Test
##[error]The runner has received a shutdown signal. This can happen when the runner
service is stopped, or a manually started runner is canceled.
##[error]Process completed with exit code 143
```

Exit 143 is SIGTERM. The job-level `timeout-minutes: 360` was never reached — the
2026-08-01 run died 119 seconds in.

### Root cause

`cargo mutants --timeout 30` is a **wall-clock** timeout with no memory bound. A mutation
that makes a loop non-convergent grows a heap allocation until the 16 GB runner is
exhausted, and the runner agent is killed along with the job. The memory ceiling is hit
well before 30 seconds elapse, so the existing timeout can never catch it.

Concretely, in `collatz/collatz-rs/src/lib.rs`, `chain_length` pushes to `path: Vec<u64>`
on every iteration and only breaks when `curr <= limit && cache[curr as usize] != 0`. Two
of the first four mutants in `--no-shuffle` order make that break unreachable:

```
src/lib.rs:4:5:  replace collatz_next -> u64 with 0     # curr = 0, cache[0] == 0, never breaks
src/lib.rs:5:11: replace / with * in collatz_next       # never converges
```

Measured (repro capped at 200M iterations so it would terminate):

```
NO CONVERGENCE after 200000000 iters, path len 200000000, approx heap 2048 MB
```

Uncapped, this walks through 16 GB in seconds. The 2026-08-01 timeline matches exactly:
baseline OK at 05:02:44, SIGTERM at 05:03:08 — one mutant in flight. The 2026-06-01 run
died in `factorial/factorial-rs` instead, so the failure is a _class_
(allocation-unbounded mutants), not one crate.

A prior diagnosis in `CLAUDE.md` attributed this to the 360-minute CI timeout combined with
infinite-loop mutations, and reduced `--timeout` from 120 to 30 in response. That diagnosis
was wrong — time was never the binding constraint — and the change did not help.

### The other three failures

1. **Artifacts never upload.** The `Upload mutants output` step is `if: always()`, but
   SIGTERM skips it (confirmed `skipped` in the 2026-08-01 run). Six months of runs
   produced zero artifacts.
2. **The Python sibling hides its failures.** `mutation-testing-python.yml` runs
   `make -C "${dir}" mutants || true`, so the workflow is green regardless of what
   happened. Its 2026-08-01 "success" carries no information.
3. **Nothing consumes the reports.** ai-config's `mutation-review.yml:44-46` invokes
   `mutation_review.py --repo "${GITHUB_REPOSITORY}"` (= `brujack/ai-config`) with
   `--artifact "mutants-report"` — a repo and an artifact name that do not match math's.
   That workflow has run once ever (2026-07-02). math's mutation output has never reached
   the `mutation-review` skill by any automated path.

Note what is **not** a problem: the serial loop already tolerates a crate-level failure via
`(cd "${crate_dir}" && cargo mutants …) || failed=1` followed by `exit "${failed}"`. Only
runner _death_ defeated it.

## Scope: Phase A only

This spec covers the smallest change that makes mutation testing work and produces a green
run. Structural changes — a per-crate matrix, artifact aggregation, per-PR mutation
coverage — are **Phase B**, deferred deliberately.

The reason is evidence, not caution. No serial run has ever completed, so there is no
measurement of how long the full sweep takes, how many crates produce survivors, or whether
one crate's runtime crowds out another's. Every argument for the matrix (wall-clock
parallelism, per-project timeout granularity) is sized against data that does not exist
yet. Phase B gets written against the first green run.

**Phase B trigger:** one successful full run of `mutation-testing.yml` on master. Its spec
decides the matrix, artifact staging/aggregation, and whether per-PR mutation coverage is
worth having as a real blocking gate.

## Goals

- An allocation-unbounded mutant is recorded as CAUGHT, not as a dead runner.
- A green leg means the project was actually tested — not merely that the tool had no
  complaint.
- A red result reaches the maintainer instead of sitting in a cron run nobody opens.
- Reports reach the `mutation-review` skill, which requires wiring a consumer that has
  never pointed at this repo.

## Non-goals

- **Per-crate matrix, artifact staging, `aggregate` job** — Phase B.
- **Per-PR mutation coverage beyond today's** — `mutation-pr.yml` is untouched. Advisory
  legs cannot change a merge verdict and produce nothing that outlives the run, so
  widening it to 11 crates would be cost without signal; making it blocking is a real
  quality bar that deserves its own decision rather than arriving inside a workflow
  refactor. Leaving the file alone also **preserves `factorial-rs`'s existing blocking
  bar** — `mutation-pr` is a required check (`ci-gate.sh:3` lists only `snyk-scan` as
  advisory) and its Rust step has no `|| true`, so `factorial-rs` has had a live "no new
  surviving in-diff mutants" gate since that workflow landed. That gate stays.
- **A survivor-count ratchet, or any committed per-crate baseline.** Rejected on its own
  merits below.
- Raising kill rates or writing killing tests — that is `mutation-review`'s job, unblocked
  by this work rather than performed by it.

## Inventory

**11 Rust crates** (each has a `Makefile` with a `mutants` target):

```
amicable/amicable-rs          fib/fib-rs                           pi/pi-rs
collatz/collatz-rs            goldbach/goldbach-rs                 prime/prime-rs
e/e-rs                        perfect-numbers/perfect-numbers-rs   sq/sq-rs
factorial/factorial-rs        twin-primes/twin-primes-rs
```

**8 Python sub-projects** (each has a `cosmic-ray.toml`): `amicable`, `collatz`, `e`,
`factorial`, `fib`, `perfect-numbers`, `pi`, `sq`. `goldbach`, `prime`, and `twin-primes`
are Rust-only.

The repo has **41** workflow files (`ls .github/workflows | wc -l`). `CLAUDE.md` says
"Thirty-nine" and is stale; this work corrects it.

## Design

### The memory cap

Each mutation run executes under an address-space limit:

```bash
ulimit -v 8388608   # 8 GiB, expressed in KiB; runner has 16 GB
```

Every child process inherits it — rustc, cargo, and the mutated test binary. A runaway
mutant hits allocation failure and aborts; the test fails; cargo-mutants records the mutant
as CAUGHT.

**Measured** on `collatz/collatz-rs` under `docker run --platform linux/amd64 rust:1-slim`
(macOS cannot enforce `ulimit -v` at all — `cannot modify limit: Invalid argument`, the
limit stays `unlimited`, so this class of check cannot be run on the Mac):

| run                   | exit | caught | missed | unviable | unviable mutant                                  |
| --------------------- | ---- | ------ | ------ | -------- | ------------------------------------------------ |
| capped (`-v 8388608`) | 2    | 36     | 4      | 1        | `src/lib.rs:41:26: replace > with <`             |
| uncapped (control)    | 3    | 35     | 4      | 1        | `src/lib.rs:41:26: replace > with <` (identical) |

Three things follow. The cap converts a runaway mutant from a timeout into a **caught**
mutant (36 vs 35, exit 2 vs 3) — the mechanism works as designed. The single unviable
mutant is **identical in both runs**, so it is an ordinary non-compiling mutation, not cap
starvation. And `collatz-rs` completes in full under the cap where CI killed the runner.

This settles it for `collatz-rs` only. `factorial-rs`, `pi-rs`, and `e-rs` link GMP/MPFR
and have the largest builds in the repo; their headroom is checked in Verification below.

### Where the cap lives: the Makefile, not the workflow

The `mutants:` target in each of the 11 Rust Makefiles currently reads:

```make
mutants:
	cargo mutants --timeout 120 --no-shuffle
```

It becomes:

```make
mutants:
	@ulimit -v 8388608 2>/dev/null || printf "warning: this platform cannot enforce a memory cap; an allocation-unbounded mutant may exhaust system memory\n" >&2
	@bash -c 'ulimit -v 8388608 2>/dev/null; exec cargo mutants --timeout 30 --no-shuffle'
```

The workflow then calls `make -C <crate> mutants` rather than invoking `cargo` directly.

Two problems collapse into this one change. The workflow passed `--timeout 30` while the
Makefiles passed `--timeout 120`, so a local `make mutants` and a CI run silently disagreed
on the per-mutant budget — one source of truth now. And `CLAUDE.md:313` tells the
maintainer to run `make mutants` per crate periodically; on the primary Mac that command
still walks `collatz-rs` through system memory, so the warning line is the only honest
signal available there.

### Classification

Verified empirically against `cargo-mutants 27.0.0` using purpose-built scratch crates. The
`--help` output does not document these:

| code                      | meaning                                    |
| ------------------------- | ------------------------------------------ |
| 0                         | all mutants caught                         |
| 2                         | surviving mutants                          |
| 3                         | timeouts present                           |
| 4                         | baseline tests failed in an unmutated tree |
| anything else (incl. 143) | tool error, runner kill, OOM               |

**The exit code alone is not sufficient, and neither is any single count.** Two distinct
buckets exit green while establishing nothing:

- **All-unviable.** Mutants that fail to _build_ are recorded `unviable` and excluded from
  the kill-rate denominator. Measured against 27.0.0 with mutant builds killed at exit 137
  (the OOM signature) and the baseline intact: `5 mutants tested in 1s: 5 unviable`,
  `exit=0`. Since the cap deliberately applies to rustc, this is reachable whenever the
  limit is too tight for a crate.
- **All-timeout.** Exit 3. This is precisely the cap's blind spot: `ulimit -v` catches
  allocating runaways, but a mutation that spins without allocating still times out —
  `CLAUDE.md` documents `p += 1` → `p *= 1` in a sieve as exactly that shape.

One stateless rule covers both, plus the empty case:

```
red if (caught + missed) == 0
```

Nothing was actually evaluated. No committed configuration, nothing to drift, and it
subsumes `total_mutants == 0`.

`scripts/mutation-classify.sh` reads `mutants.out/outcomes.json` (which carries
`total_mutants`, `caught`, `missed`, `unviable`, `timeout` as top-level keys, verified
against 27.0.0) and applies:

- **red** if `outcomes.json` is missing or unparseable **and** the exit code is non-zero
- **red** if `(caught + missed) == 0`
- **red** if the exit code is 4, 143, or anything outside {0, 2, 3}
- otherwise **green**, with survivor and timeout counts written to `$GITHUB_STEP_SUMMARY`

The "and the exit code is non-zero" qualifier is load-bearing even though Phase A never
passes `--in-diff`. Measured: a `--in-diff` run whose diff contains no mutable lines prints
`INFO No mutants to filter`, exits **0**, and writes **no `mutants.out/` at all**. A rule
that reds on a missing file alone would fail every TDD-first PR that adds a test without
changing logic — the modal PR under this repo's testing policy. Phase B will use
`--in-diff` if it revives per-PR coverage, and the rule is written correctly now rather
than rediscovered then.

#### Why not a committed per-crate expected-unviable count

An earlier revision proposed exactly that: red when `unviable` exceeds a per-crate number
committed to the repo. It is rejected. `unviable` is "does the mutated code compile,"
perturbed by any source change and by `dtolnay/rust-toolchain@stable` pulling a new rustc
without a config change. This repo already maintains one hand-tuned per-crate number of
that class — `.cargo/mutants.toml` `exclude_re` in 4 of 11 crates, each carrying a "update
if surrounding code shifts lines" warning — and the new one would drift the same way with a
worse failure mode: `exclude_re` drift surfaces a mutant as a survivor (green, a summary
line), while baseline drift turns the leg **red**, files an issue, and — because
`fetch_latest_artifact` selects only runs whose conclusion is `success` — blanks that
month's report. The rule was also one-directional (`unviable <` expected was silent), so it
would loosen monotonically and quietly stop detecting anything. `caught + missed == 0`
measures the thing directly with none of that.

### Python classification

`make -C <dir> mutants` returns cosmic-ray's own status, which does not encode survivor
counts. The `|| true` is deleted so a genuine cosmic-ray failure is visible. The leg parses
the survivor count from `cr-report` into the summary and is red when `make mutants` fails
or when the session sqlite is absent. Survivors do not turn it red.

Each sub-project uploads both `mutants-report.txt` and `cosmic-ray-session.sqlite` — the
consumer reads the sqlite, and today it is never uploaded (see Consumer wiring).

### Notification

Reducing red frequency does not by itself create attention: all six historical runs were
red and none were opened for six months. The cause was "nobody opens a monthly cron run,"
not "signal buried in noise."

Notification is a **separate job**, not a step inside the mutation job:

```yaml
notify:
  needs: [mutants]
  if: always()
  runs-on: ubuntu-latest # fresh runner — survives the mutation job's death
```

This placement is the whole point. SIGTERM skips `if: always()` _steps_ within the killed
job — that is why six months of artifacts never uploaded — so an in-job notification step
cannot report runner death or a job-level timeout, which are exactly the two failure classes
with no other output. A separate job runs on its own runner and reports both.

The mutation job writes `status/<slug>` for each project as it finishes. `notify` downloads
the status artifact and derives per-project state; a **missing** status file is itself the
runner-death signal, and it is the one case nothing else can report.

On red, `notify` files or updates a labelled issue using `release-sbom-monitor.yml`'s
existing pattern — `gh issue list --search 'in:title "<exact phrase>"'` for dedup (the
exact-phrase form from #89, which fixed a false-match bug in that same check), creating when
absent and commenting when present. **On green, it closes the issue** with a comment. An
SBOM issue correctly stays open because a CVE does not self-heal; a mutation failure does,
and without close-on-green the label degrades into a pile of stale rows and stops working as
a worklist — the exact endpoint this mechanism exists to avoid. The job needs
`permissions: issues: write`.

### Consumer wiring (cross-repo, ai-config)

The reports do not reach `mutation-review` today, and no change inside math can fix that.
Four changes in ai-config:

1. `mutation-review.yml` — invoke `mutation_review.py` against `brujack/math`.
   `--artifact` is `required=True` and single-valued (`mutation_review.py:635`), so the
   cargo-mutants and cosmic-ray paths are **two invocations**, not one call with two names.
2. `mutation_review.py:666` hardcodes `"mutation-testing.yml"` as the workflow name at the
   `fetch_latest_artifact` call site, so the cosmic-ray path can never reach
   `mutation-testing-python.yml` regardless of artifact name. Parameterize it.
3. `mutation_review.py:684-686` —
   `for candidate in artifact_dir.rglob("outcomes.json"): outcomes_path = candidate; break`
   takes the **first** match and stops. Harmless for Phase A's single-artifact upload, and a
   latent bug for any multi-crate artifact; fix it now so Phase B does not inherit it.
4. `fetch_latest_artifact` has **no date bound**. On a red run it silently falls back to the
   previous green run and reports its survivors as current — reachable-and-wrong, which is
   worse than unreachable. Add a staleness check that reports the artifact's run date, and
   refuse or loudly warn when it is older than the expected cadence.

Phase A's math changes do not depend on these landing, and vice versa — but Verification
step 5 does, so ai-config goes first.

### Classification script

The logic lives in `scripts/mutation-classify.sh`, not inline in a `run:` block. Inline YAML
cannot be unit-tested, and this repo already runs `bats --recursive tests/` via
`scripts.yml`.

`tests/scripts/mutation_classify.bats` covers every exit code in the table — 0, 2, 3, 4,
143, and an unknown code — **and** every count rule: `caught + missed == 0` via the
all-unviable case, via the all-timeout case, and via the zero-mutant case; missing
`outcomes.json` with exit 0 (green, the no-mutants-to-filter case); missing `outcomes.json`
with a non-zero exit (red); unparseable `outcomes.json`. Both branches of every guard, per
this repo's testing policy.

## Verification

`mutation-testing.yml` already exists on the default branch with `workflow_dispatch`, so
branch dispatch works before merge. (A workflow absent from the default branch cannot be
dispatched by `--ref` at all — GitHub resolves the workflow list against the default
branch.)

1. **The fix itself.** `gh workflow run mutation-testing.yml --ref <branch> -f crate=collatz/collatz-rs`
   Expected: green; no exit 143; `outcomes.json` shows `caught == 36`, `missed == 4`,
   `unviable == 1`, matching the Docker measurement.
2. **Cap headroom on the big-build crates.** `factorial-rs`, `pi-rs`, `e-rs` (GMP/MPFR
   links). For each, compare `unviable` capped vs uncapped in Docker. Expected: identical.
   A capped count above the uncapped count means the limit starves that crate's builds —
   the failure that would otherwise present as green, and the reason `caught + missed == 0`
   exists as a backstop. Scoped to three crates rather than all eleven because the uncapped
   arm on `collatz-rs` _is the bug_ (exit 143, no `outcomes.json` to compare against) and
   because Docker on Apple Silicon runs `--platform linux/amd64` under emulation.
3. **The first green full run.** Dispatch with no crate input. Expected: all 11 crates
   report, the run is green, and the artifact uploads. This run is also the Phase B trigger
   and the first real measurement of total sweep time.
4. **Python.** Dispatch `mutation-testing-python.yml` on the branch. Expected: 8
   sub-projects report; the artifact contains 8 sqlite files.
5. **Consumer contract, end to end.** Run the updated `mutation_review.py` against the
   branch run. Expected: it locates the artifact and reports survivors, and reports the
   artifact's run date.
6. **Notification, both directions.** Force a red (dispatch against a crate with a
   deliberately broken test): expect one labelled issue. Re-run red: expect a comment, not a
   duplicate. Then run green: expect the issue closed.
7. **Runner-death reporting.** Force the failure this design exists to fix — dispatch with
   the cap raised high enough that `collatz-rs` OOMs the runner — and confirm `notify` still
   files an issue from its own runner with no status file present. This is the one path that
   cannot be verified by reasoning, because it is the path where the reporting mechanism's
   own host dies.

Step 7 is not optional. The implementation PR touches only workflow, script, and Makefile
files, so it exercises none of the runtime failure paths on its own. This repo's standards
already record a change-detection script that shipped completely inert because its tests only
covered the path the implementation PR happened to take.

## Consequences

**Runner minutes.** Unchanged — one job, one `cargo install cargo-mutants`, same serial
sweep. The `notify` job adds well under a minute.

**Rollback.** Two reverts, one per repo. No state, no migration, no baseline file.

**Docs.** `CLAUDE.md`'s stale "Thirty-nine workflow files" becomes 41; the note attributing
these failures to the 360-minute timeout is corrected; the `--timeout 120` → `30` Makefile
change and the memory cap are recorded in the mutation-testing section.

**What Phase B inherits.** A green baseline, a real sweep-time measurement, a tested
classifier, and a notification path proven against runner death — which is a materially
better position from which to argue for a matrix than the current one, where the argument
rests on numbers nobody has.

## Multi-Lens Review

### Round 1 — reviewed at commit `6a41d56`

#### Goal-Fit (R1)

Finding: Goal 4 ("reports reach the `mutation-review` skill without a cross-repo change")
is false, and it is the goal the other four serve. ai-config's `mutation-review.yml:44-46`
passes `--repo "${GITHUB_REPOSITORY}"` (= ai-config) and `--artifact "mutants-report"` —
neither matches math's names; that workflow has run once ever. The `aggregate` job, slug
scheme, and artifact-name preservation are correct engineering serving a consumer that is
not wired up. Secondary: the serial loop already tolerated crate failures, so the matrix was
justified on a symptom of the bug the cap fixes; widening `mutation-pr` to 11 crates creates
a repo-wide blocking merge gate the spec never names; the 8 Python PR legs fail the reads-it
test by construction.

Assumption: that an `ulimit -v` cap records a runaway mutant as CAUGHT rather than
`Unviable`.

Disposition: **Addressed.** Consumer wiring moved in scope; aggravator corrected; matrix
re-justified (and in round 2, deferred entirely). Assumption **measured**, not accepted —
see the Memory cap table.

#### Ergonomics (R1)

Finding: `mutation_review.py:497` selects only runs whose conclusion is `success`, so with
`fail-fast: false` the partial-coverage case `aggregate: if: always()` exists to serve is
exactly the case the consumer refuses to read. Secondary: the cap was specified only for the
monthly legs while PR legs stayed uncapped; the stated cause of the six-month blindness does
not hold (all six runs were red — the cause was that nobody opens a cron run); the dispatch
override is impossible against a static YAML matrix; workflow count is 41; local/CI timeout
drift.

Assumption: same as Goal-Fit R1.

Disposition: **Addressed.** Notification added; count corrected; timeout drift fixed in the
Makefile. The matrix, and with it the `fail-fast`/`aggregate` interaction, is deferred to
Phase B.

#### Risk (R1)

Finding: **The memory cap's failure mode is a green run.** Measured against 27.0.0 with
mutant builds killed at exit 137 and the baseline intact: `5 mutants tested in 1s: 5
unviable`, `exit=0` — green while testing nothing. Secondary: first-match `rglob`; the
unspecified per-leg upload path and its least-common-ancestor collision; the cosmic-ray
sqlite is never uploaded; `if: … != '[]'` fails open.

Assumption: that a too-tight `ulimit -v` fails loudly.

Disposition: **Addressed.** Count-based classification adopted (and in round 2 replaced with
a stateless rule). `rglob` and sqlite upload are named changes. The `fromJSON` guard and
upload-path items are deferred with the matrix. Assumption **partially settled** — measured
clean on `collatz-rs`; the big-build crates are Verification step 2.

### Round 2 — reviewed at commit `5041fe3`

#### Goal-Fit (R2)

Finding: the measured root cause has a four-line fix, and the spec spent ~15 files across
two repos without pricing the increment against it. Goals 2 and 6 are solution statements,
not problems; the matrix is sized against data that does not exist, because no serial run
has ever completed. The advisory PR legs fail the reads-it test outright — no verdict can
differ and nothing durable is produced — while costing 11 × `cargo install` plus 8 full
cosmic-ray runs per PR. The per-crate expected-unviable count contradicts the spec's own
Non-goals. Making all PR legs advisory silently _deletes_ `factorial-rs`'s existing blocking
bar. Verified separately: math PRs #83 and #84 killed surviving mutants across seven
sub-projects, both driven by local `make mutants` — the human path has a track record, the
CI consumer path has produced nothing.

Assumption: that a too-tight cap starves _partially_ (baseline builds, later mutants do not)
rather than all-or-nothing. If starvation is all-or-nothing, roughly a third of the spec's
new surface guards a state that cannot occur.

Disposition: **Addressed.** Scope cut to Phase A; PR legs dropped entirely and the goal
deleted; the per-crate baseline removed in favour of a stateless rule; `factorial-rs`'s bar
preserved explicitly by leaving `mutation-pr.yml` untouched. The assumption is now guarded
rather than predicted — `caught + missed == 0` catches the partial case without needing to
know whether it occurs, and Verification step 2 measures it on the three crates where it
could plausibly bind.

#### Ergonomics (R2)

Finding: the per-crate expected-unviable count is the committed baseline Non-goals rejects,
and its most likely trigger is ordinary churn, not breakage — one-directional (only ever
bumped up, so it loosens monotonically), and each false red blanks that month's report for
every crate. **The notification step dies with the runner it exists to report on**: it was
placed inside the leg, and SIGTERM skips `if: always()` steps — so runner death and leg
timeout, the two classes with no other output, file nothing. Secondary: Verification step 2
was unrunnable as written because the uncapped arm on `collatz-rs` is the bug; local
`make mutants` keeps the memory bug on macOS; no close-on-green makes the label a pile of
stale rows; `workflow_dispatch` free-text input typos into an empty run.

Assumption: that a crate's `unviable` count is stable across source edits and rustc drift.

Disposition: **Addressed.** Baseline removed. Notification moved to a separate job with a
status-file protocol where a missing file _is_ the runner-death signal, and Verification
step 7 forces that exact path. Step 2 narrowed to the three GMP/MPFR crates. Makefile
carries the cap with a Darwin warning. Close-on-green added. The assumption is now moot —
nothing depends on `unviable` stability.

#### Risk (R2)

Finding: **the new "missing `outcomes.json` = red" rule produces a merge-blocking false red
on the modal PR.** Measured (and independently re-measured): a `--in-diff` run with no
mutable lines in the diff prints `INFO No mutants to filter`, exits 0, and writes no
`mutants.out/` — so a TDD-first PR adding a test would go red across 11 crates. **The
`timeout` bucket has exactly the hole `unviable` was just fixed for**: exit 3 is green with
no guard, and that is the cap's blind spot, since a mutation that spins without allocating
still times out. Both collapse into `caught + missed == 0`. Secondary: the expected-unviable
calibration is circular ("first run establishes it" bakes in any starvation already
present); "PR legs are advisory" was asserted but not implemented, since `ci-gate.sh` matches
exact check names with no glob path; the cross-repo list was incomplete (`--artifact` is
single-valued; `mutation-testing.yml` is hardcoded at `:666`); `fetch_latest_artifact` has no
date bound, so a red run silently yields stale survivors reported as current; the `plan` job
is complexity the matrix creates rather than complexity that solves the problem.

Assumption: that a crate's `unviable` count is a durable constant.

Disposition: **Addressed.** Stateless rule adopted; the missing-`outcomes.json` rule now
requires a non-zero exit, with the measurement recorded inline; the `--artifact` arity, the
hardcoded workflow name, and the missing date bound are all named ai-config changes; the
`plan` job and PR legs are gone with Phase B and the PR-leg decision respectively. The
assumption is moot — no committed count remains.

### Adversarial Spec Review

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
