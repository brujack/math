# Per-Project Mutation Testing — Design

**Date:** 2026-08-01
**Status:** Spec (pending plan)

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

Concretely, in `collatz/collatz-rs/src/lib.rs`, `chain_length` pushes to
`path: Vec<u64>` on every iteration and only breaks when
`curr <= limit && cache[curr as usize] != 0`. Two of the first four mutants in
`--no-shuffle` order make that break unreachable:

```
src/lib.rs:4:5:  replace collatz_next -> u64 with 0     # curr = 0, cache[0] == 0, never breaks
src/lib.rs:5:11: replace / with * in collatz_next       # never converges
```

Measured (repro capped at 200M iterations so it would terminate):

```
NO CONVERGENCE after 200000000 iters, path len 200000000, approx heap 2048 MB
```

Uncapped, this walks through 16 GB in seconds. The 2026-08-01 timeline matches exactly:
baseline OK at 05:02:44, SIGTERM at 05:03:08 — one mutant in flight.

The 2026-06-01 run died in `factorial/factorial-rs` rather than collatz, so the failure is
a _class_ (allocation-unbounded mutants), not one crate.

A prior diagnosis recorded in `CLAUDE.md` attributed this to the 360-minute CI timeout
combined with infinite-loop mutations, and reduced `--timeout` from 120 to 30 in response.
That diagnosis was wrong — time was never the binding constraint — and the change did not
help.

### Structural aggravators

1. **Artifacts never upload.** The `Upload mutants output` step is `if: always()`, but
   SIGTERM skips it (confirmed `skipped` in the 2026-08-01 run). Six months of runs
   produced zero artifacts.
2. **The Python sibling hides its failures.** `mutation-testing-python.yml` runs
   `make -C "${dir}" mutants || true`, so the workflow is green regardless of what
   happened. Its 2026-08-01 "success" carries no information.
3. **`mutation-pr.yml` covers one crate of eleven.** It hardcodes a
   `^factorial/factorial-rs/.*\.rs$` diff check; the other ten crates have no per-PR
   mutation coverage at all.
4. **Nothing consumes the reports.** ai-config's `mutation-review.yml:44-46` invokes
   `mutation_review.py --repo "${GITHUB_REPOSITORY}"` (= `brujack/ai-config`) with
   `--artifact "mutants-report"` — a repo and an artifact name that do not match math's.
   That workflow has run once ever (2026-07-02). math's mutation output has never reached
   the `mutation-review` skill by any automated path.

Note what is **not** an aggravator: the serial loop already tolerates a crate-level
failure via `(cd "${crate_dir}" && cargo mutants …) || failed=1` followed by
`exit "${failed}"`. Only runner _death_ defeated it. An earlier draft of this spec claimed
the loop lacked failure isolation; that was wrong, and the matrix is justified below on
other grounds.

## Goals

- An allocation-unbounded mutant is recorded as CAUGHT, not as a dead runner.
- Every project is tested on every run, in parallel, under its own timeout.
- A red result means something is genuinely broken **and reaches the maintainer**.
- A green result means the project was actually tested — not merely that the tool had no
  complaint.
- Reports reach the `mutation-review` skill, which requires wiring the consumer that has
  never pointed at this repo.
- Per-PR mutation coverage extends to all 11 Rust crates and all 8 Python sub-projects,
  without introducing a new merge-blocking quality bar.

## Non-goals

- Raising kill rates or writing killing tests. That is `mutation-review`'s job, and it is
  unblocked by this work rather than performed by it.
- A survivor-count ratchet or committed baseline. Considered and rejected — new state to
  maintain for a report that nothing currently gates on.
- Per-project workflow files (19 of them). Considered and rejected — matrix legs give the
  same runner isolation with 2 files instead of 19 near-identical ones to keep in sync.
- A reusable workflow. GitHub forbids `strategy: matrix` on a job whose body is a
  `uses:` call, which is already documented in this repo's standards after the SBOM
  monitor had to spell out 11 call sites longhand.

## Inventory

**11 Rust crates** (each has a `Makefile` with a `mutants` target):

```
amicable/amicable-rs          fib/fib-rs                           pi/pi-rs
collatz/collatz-rs            goldbach/goldbach-rs                 prime/prime-rs
e/e-rs                        perfect-numbers/perfect-numbers-rs   sq/sq-rs
factorial/factorial-rs        twin-primes/twin-primes-rs
```

**8 Python sub-projects** (each has a `cosmic-ray.toml`):

```
amicable   collatz   e   factorial   fib   perfect-numbers   pi   sq
```

`goldbach`, `prime`, and `twin-primes` are Rust-only and have no Python leg.

The repo currently has **41** workflow files (`ls .github/workflows | wc -l`). `CLAUDE.md`
says "Thirty-nine" and is stale; this work corrects it.

## Design

### Workflow structure

All three workflows become matrix-based. No workflow file is added or removed — the repo
stays at 41. Two non-workflow files are added: `scripts/mutation-classify.sh` and
`tests/scripts/mutation_classify.bats`.

**`mutation-testing.yml`** — Rust, monthly `cron: "0 4 1 * *"`, plus `workflow_dispatch`.

```yaml
jobs:
  plan: # emits the matrix; a static YAML list cannot honour the dispatch input
    outputs:
      crates: ${{ steps.p.outputs.crates }} # full 11 list, or a single-entry list
      # when github.event.inputs.crate is non-empty

  mutants:
    needs: [plan]
    strategy:
      fail-fast: false
      matrix:
        crate: ${{ fromJSON(needs.plan.outputs.crates) }}
    runs-on: ubuntu-latest
    timeout-minutes: 60 # per leg; was 360 shared across all 11.
      # basis: slowest measured crate was 98 mutants in 6m
      # (factorial-rs, 2026-07-01), so 60 is ~10x headroom
    steps:
      - checkout, rust-toolchain, cargo install cargo-mutants --locked
      - run mutants under a memory cap (below)
      - classify via scripts/mutation-classify.sh (below)
      - stage mutants.out into out/<slug>/ (see Artifact layout)
      - upload-artifact: mutants-output-<slug>, path out/
      - on red: file/update a labelled issue (see Notification)

  aggregate:
    needs: [mutants]
    if: always()
    steps:
      - download-artifact: pattern mutants-output-*, merge-multiple: true
      - upload-artifact: mutants-output
```

**`mutation-testing-python.yml`** — monthly `cron: "0 6 1 * *"`, plus `workflow_dispatch`.
Same shape, 8 legs, each running `make -C <dir> mutants`. The `|| true` is deleted. Each
leg uploads both `mutants-report.txt` and `cosmic-ray-session.sqlite` (the consumer reads
the sqlite; today it is never uploaded, see Consumer wiring). Aggregate job re-uploads
under `mutants-report-python`.

**`mutation-pr.yml`** — `pull_request` to master. A `detect` job emits two JSON arrays plus
two booleans computed from the PR diff; two matrix jobs consume them:

```yaml
jobs:
  detect:
    outputs:
      has_rust: ${{ steps.d.outputs.has_rust }} # 'true' / 'false'
      has_python: ${{ steps.d.outputs.has_python }}
      rust: ${{ steps.d.outputs.rust }} # e.g. '["collatz/collatz-rs"]'
      python: ${{ steps.d.outputs.python }} # e.g. '["collatz"]'

  mutants-rust:
    needs: [detect]
    if: needs.detect.outputs.has_rust == 'true'
    strategy:
      fail-fast: false
      matrix:
        crate: ${{ fromJSON(needs.detect.outputs.rust) }}
    timeout-minutes: 15 # per leg, was 10 shared
    steps:
      - same ulimit cap and classify script as the monthly legs
      - cargo mutants --in-diff /tmp/pr.diff --timeout 30 --no-shuffle
```

The gate is on a **positive boolean**, not `!= '[]'`. If `detect` fails before writing its
output the value is `''`, and `'' != '[]'` is true — the job would run and `fromJSON('')`
would throw. Failing closed is the correct default when the guard's own input is unknown.

### PR legs are advisory

Surviving in-diff mutants do **not** block merge. `scripts/ci-gate.sh:3` lists only
`snyk-scan` as advisory, so every new `mutants-rust (<crate>)` leg would otherwise become a
required check, and `cargo mutants --in-diff` exits 2 on a surviving mutant. Widening the
gate from one crate to eleven would have introduced a repo-wide "zero new surviving
mutants" merge bar as a side effect of a workflow refactor — a real quality bar, but one
that deserves its own decision rather than arriving unannounced.

PR legs therefore use the same classification as the monthly legs: survivors and timeouts
are reported to the job summary and exit 0; only genuine breakage is red. Python PR legs
keep their existing advisory-warning semantics for the same reason plus one of their own —
cosmic-ray has no `--in-diff` equivalent, so it runs every mutation and pre-existing
survivors would fire on every Python PR.

The PR legs get the **same `ulimit -v` cap** as the monthly legs. Without it, a PR touching
`collatz/collatz-rs/src/lib.rs:4-5` reproduces exit 143 on the PR surface — applying the
remedy to one of two surfaces would widen the bug's blast radius from one crate to eleven
while fixing it in only one place.

### Why a matrix, given the loop already tolerated crate failures

Three reasons, none of them "one crate kills all" (the `|| failed=1` loop already handled
that):

1. **Wall clock.** 11 crates run in parallel rather than in sequence. The 2026-07-01 run
   spent ~6 minutes on two crates before dying.
2. **Timeout granularity.** Each project gets its own 60-minute budget instead of sharing
   one 360-minute pool, so one slow crate cannot consume another's headroom.
3. **Defence in depth.** If the `ulimit -v` value turns out to be wrong for some crate, a
   dead leg is one dead leg. The cap is the fix; the matrix is what keeps a wrong cap from
   being a total loss.

### Matrix leg isolation

Each matrix leg is scheduled on its own runner with its own 16 GB. `fail-fast: false`
prevents GitHub from cancelling surviving legs when one fails.

`workflow_dispatch`'s single-project input is honoured by the `plan` job, which emits either
the full list or a single-entry list. A static YAML matrix list cannot be overridden by an
input — and this path is Verification step 1, the acceptance check for the whole fix, so it
cannot be left implicit.

### Artifact layout

Artifact names cannot contain `/`, so each leg uploads under a slug with slashes replaced
by hyphens: `collatz/collatz-rs` → `mutants-output-collatz-collatz-rs`.
`actions/upload-artifact@v7` rejects two uploads sharing one name, so per-leg names are
mandatory, not stylistic.

Each leg **stages its output into `out/<slug>/mutants.out/` before uploading**, and uploads
`path: out/`. This is load-bearing: `upload-artifact` roots an artifact at the least common
ancestor of the matched files, so a single-crate leg matching `**/mutants.out/` would place
`outcomes.json` at the artifact root and all 11 legs would collide onto identical paths
under `merge-multiple: true`. Today's single-job upload preserves crate prefixes only
because its LCA across 11 crates happens to be the repo root.

### Consumer wiring (cross-repo)

The `aggregate` job alone does not deliver reports to `mutation-review` — the consumer was
never pointed at this repo. Three changes in ai-config, in the same cycle:

1. `mutation-review.yml` — invoke `mutation_review.py` against `brujack/math` with
   `--artifact mutants-output` (cargo-mutants) and `--artifact mutants-report-python`
   (cosmic-ray), rather than `${GITHUB_REPOSITORY}` / `mutants-report`.
2. `mutation_review.py:684-686` — `for candidate in artifact_dir.rglob("outcomes.json"):
outcomes_path = candidate; break` takes the **first** match and stops, so a correctly
   merged 11-crate artifact still yields one crate. Collect all matches and merge.
3. `mutation_review.py` cosmic-ray branch — reads `artifact_dir /
"cosmic-ray-session.sqlite"` with no rglob fallback, and math never uploaded that file.
   math starts uploading it (above); the reader gains the same collect-all treatment.

`fetch_latest_artifact` also selects `.workflow_runs | map(select(.conclusion ==
"success")) | first`. With `fail-fast: false`, one red leg makes the run conclusion
`failure` and the merged artifact becomes unreachable — so the classification rules below
(which keep survivors and timeouts green) are what make partial-failure runs consumable at
all. A run is red only when something is genuinely broken, which is also when its report is
least useful.

### Notification

Reducing red frequency does not by itself create attention: all six historical runs were
red and none were opened for six months. The cause was "nobody opens a monthly cron run,"
not "signal buried in noise."

A red leg therefore files or updates a labelled issue, reusing `release-sbom-monitor.yml`'s
existing pattern — `gh issue list --search 'in:title "<exact phrase>"'` for dedup (the
exact-phrase form from #89, which fixed a false-match bug in that same check), creating when
absent and commenting when present. One issue per project, so a persistently broken crate
does not open a new issue every month.

### Memory cap

Each leg sets an address-space limit before invoking the mutation tool:

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
starvation. And `collatz-rs` completes in full under the cap where CI killed the runner,
which is the fix demonstrated end to end.

This settles the assumption for `collatz-rs` only. `factorial-rs` links GMP and has the
largest build in the repo; its cap headroom is unverified, and Verification step 2 below
runs the same capped-vs-uncapped comparison per crate. If a crate shows unviables under the
cap that it does not show uncapped, raise the limit for that crate and record the settled
value in `CLAUDE.md`.

### Classification

Verified empirically against `cargo-mutants 27.0.0` using purpose-built scratch crates (a
crate with an uncaught mutant, one with a failing baseline test, one with an infinite-loop
mutant). The `--help` output does not document these:

| code                      | meaning                                    | verdict                                        |
| ------------------------- | ------------------------------------------ | ---------------------------------------------- |
| 0                         | all mutants caught                         | green                                          |
| 2                         | surviving mutants                          | green, count written to `$GITHUB_STEP_SUMMARY` |
| 3                         | timeouts present                           | green, count written to summary                |
| 4                         | baseline tests failed in an unmutated tree | **red**                                        |
| anything else (incl. 143) | tool error, runner kill, OOM               | **red**                                        |

**The exit code alone is not sufficient**, and this is the one place the design must not
trust it. Mutants that fail to _build_ are recorded `unviable` and excluded from the
kill-rate denominator; a run of nothing but unviable mutants exits **0**. Measured against
27.0.0 with mutant builds killed at exit 137 (the OOM signature) and the baseline intact:
`5 mutants tested in 1s: 5 unviable`, `exit=0` — green while testing nothing. Since the cap
deliberately applies to rustc, that is a reachable state whenever the limit is too tight for
a crate, and it degrades silently as `dtolnay/rust-toolchain@stable` pulls newer rustc.

`scripts/mutation-classify.sh` therefore reads `mutants.out/outcomes.json` — which carries
`total_mutants`, `caught`, `missed`, `unviable`, `timeout` as top-level keys — and applies:

- **red** if `total_mutants == 0` (nothing was tested)
- **red** if `outcomes.json` is missing or unparseable (the tool did not get far enough)
- **red** if `unviable > <per-crate expected count>` (the cap starved a build). The expected
  count is committed per crate; `collatz-rs` is 1, measured above. A crate's first run
  establishes its number.
- otherwise the exit-code table above

Exit 0 currently means "cargo-mutants had no complaint," not "this crate was tested." The
count guard is what makes a green leg mean the second thing.

Python legs have no equivalent exit-code table — `make -C <dir> mutants` returns
cosmic-ray's own status, which does not encode survivor counts. The leg parses the survivor
count out of `cr-report` for the summary, and is red when `make mutants` fails or when the
session sqlite is absent. Deleting `|| true` is what makes that failure visible; it does not
turn survivors red.

### Classification script

The logic lives in `scripts/mutation-classify.sh`, not inline in a `run:` block. The
workflow calls it. Inline YAML cannot be unit-tested, and this repo already runs
`bats --recursive tests/` via `scripts.yml`.

`tests/scripts/mutation_classify.bats` covers every exit code in the table — 0, 2, 3, 4,
143, and an unknown code — **and** every count-based rule: `total_mutants == 0`, missing
`outcomes.json`, unparseable `outcomes.json`, `unviable` at and above the expected count.
Both branches of every guard, per this repo's testing policy.

### Local/CI timeout alignment

Every Rust `Makefile` `mutants:` target passes `--timeout 120`; the workflows pass
`--timeout 30`. The legs invoke `cargo mutants` directly (not `make`), so the two would stay
silently divergent. The 11 Makefiles move to `--timeout 30` so a local `make mutants` and a
CI leg agree on the per-mutant budget.

## Verification

Both monthly workflows already exist on the default branch with `workflow_dispatch`, so
branch dispatch works before merge. (A workflow absent from the default branch cannot be
dispatched by `--ref` at all — GitHub resolves the workflow list against the default
branch.)

1. **The fix itself.**
   `gh workflow run mutation-testing.yml --ref <branch> -f crate=collatz/collatz-rs`
   Expected: leg green; no exit 143; `outcomes.json` shows `caught == 36`,
   `unviable == 1`, matching the Docker measurement above. This also exercises the `plan`
   job's single-crate path.
2. **Cap headroom, per crate.** For each of the 11 crates, compare `unviable` counts from a
   capped and an uncapped run (Docker locally, or two dispatches). Expected: identical
   counts. Any crate where capped exceeds uncapped has a too-tight limit — the failure that
   would otherwise present as green.
3. **Isolation.** Full 11-leg dispatch on the branch. Expected: all 11 legs reach a terminal
   state; `aggregate` produces `mutants-output` containing 11 distinct `out/<slug>/mutants.out/`
   trees (verifying the staging fix, not just the merge).
4. **Python.** Dispatch `mutation-testing-python.yml` on the branch. Expected: 8 legs
   terminal, aggregate produces `mutants-report-python` containing 8 sqlite files.
5. **Consumer contract, end to end.** Run the updated `mutation_review.py` against the
   branch run. Expected: it locates the merged artifact and reports survivors from **all**
   crates, not one — the specific regression the first-match `rglob` causes.
6. **Notification.** Force a red leg (dispatch against a crate with a deliberately broken
   test). Expected: one labelled issue created; a second red run comments rather than
   opening a duplicate.
7. **PR matrix path.** A throwaway PR touching one crate's `src/`. Expected: `detect` emits
   that crate, `mutants-rust` runs exactly one leg, and a surviving in-diff mutant does not
   block merge.

Steps 6 and 7 are not optional. The implementation PR touches only workflow and script
files, so it exercises `detect`'s empty-diff skip path and nothing else. This repo's
standards already record a change-detection script that shipped completely inert because its
tests only ever covered the path the implementation PR happened to take.

## Consequences

**Runner minutes.** `cargo install cargo-mutants --locked` runs once per leg instead of
once per run — roughly 11 × 70 s of extra runner time monthly. Wall clock is unchanged
because legs run in parallel. A prebuilt-binary install action would remove it at the cost
of a new third-party dependency; not worth it at ~13 minutes a month.

**Concurrency.** 11 legs at 04:00 and 8 at 06:00 on the first of the month. The crons stay
staggered so the two matrices never contend.

**Cross-repo coupling.** This work now spans math and ai-config. The ai-config changes are
independently useful (the first-match `rglob` is a latent bug for any multi-crate repo) but
they are a second SDLC cycle, and math's Verification step 5 depends on them landing first.

**Rollback.** Two reverts, one per repo. No state, no migration, no baseline file — except
the per-crate expected-unviable counts, which live in the classifier's committed config.

**Docs.** `CLAUDE.md`'s CI table job descriptions change; the stale "Thirty-nine workflow
files" becomes 41; the note attributing these failures to the 360-minute timeout is
corrected; the settled `ulimit -v` value and per-crate expected-unviable counts are
recorded.

## Multi-Lens Review

Reviewed at commit: `6a41d56` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: Goal 4 ("reports reach the `mutation-review` skill without a cross-repo change")
is false, and it is the goal the other four serve. Verified: ai-config's
`mutation-review.yml:44-46` passes `--repo "${GITHUB_REPOSITORY}"` (= `brujack/ai-config`)
and `--artifact "mutants-report"` — neither matches math's `mutants-output` or
`mutants-report-python`. That workflow has run once ever (2026-07-02). math's mutation
artifacts have never been consumed by anything automated, so the `aggregate` job, the slug
scheme, and the artifact-name preservation are correct engineering serving a consumer that
is not wired up. Applying the reads-it test: no verdict changes because the artifact
exists, and its post-run home is a 30-day GitHub artifact nothing downloads.

Secondary: (a) structural aggravator #1 is overstated — the current loop already survives
a crate-level failure via `(cd … ) || failed=1`; only _runner death_ defeated it, which
`ulimit -v` alone removes, so the matrix must be justified on parallelism, per-project
timeout granularity, and defence-in-depth rather than on failure isolation the loop already
had. (b) Widening `mutation-pr` to 11 crates converts a near-always-green check into a
repo-wide blocking merge gate — `ci-gate.sh:3` lists only `snyk-scan` as advisory, and
`cargo mutants --in-diff` exits 2 on a surviving in-diff mutant. The spec lists this as a
goal and never names it as a new quality bar, and it contradicts the monthly table where
exit 2 is green. (c) The 8 Python PR legs fail the reads-it test by construction — they are
advisory-only by design, so no verdict differs, and their output is a `::warning::`
annotation on a merged PR.

Assumption: that an `ulimit -v` cap causes cargo-mutants to record a runaway mutant as
CAUGHT rather than `Unviable`. Settled by running `ulimit -v 8388608; cargo mutants` on
Linux and reading `summary` for `src/lib.rs:4:5` and `5:11` in `mutants.out/outcomes.json`.

Disposition: **Addressed.** Consumer wiring moved in-scope as three named ai-config changes
(Consumer wiring section); goals rewritten; aggravator #1 replaced with an explicit note
that the loop already tolerated crate failures; matrix re-justified on parallelism, timeout
granularity, and defence-in-depth; PR legs made advisory with the same classification as
the monthly legs. Assumption **checked, not accepted on argument** — measured on Linux in
Docker: capped run gives exit 2 / 36 caught / 1 unviable, uncapped gives exit 3 / 35 caught
/ 1 identical unviable. The cap converts the runaway mutant to CAUGHT and introduces no
unviables. Recorded in the Memory cap section.

### Ergonomics

Finding: The consumer cannot see the merged artifact on any run where a leg fails.
`mutation_review.py:497` selects `.workflow_runs | map(select(.conclusion == "success")) | first`.
With `fail-fast: false`, one red leg makes the run conclusion `failure`, so the
partial-coverage case `aggregate: if: always()` exists to serve is exactly the case the
consumer refuses to read. This also makes goals 3 and 4 mutually exclusive as specified:
any run red enough to warrant a look is a run whose report is unreachable.

Secondary: (a) The memory cap is specified only for the monthly Rust legs; the PR leg is a
bare `cargo mutants --in-diff`, so a PR touching `collatz/collatz-rs/src/lib.rs:4-5`
reproduces exit 143 on a required check — the design widens the bug's blast radius from one
crate to eleven while applying the remedy to one of two surfaces. (b) The stated cause of
the six-month blindness does not hold: all six runs were red, so there was no noise to bury
the signal. The cause was "nobody opens a monthly cron run," and reducing red frequency
does not create attention — goal 3 has no mechanism behind it. The repo already has the
right pattern in `release-sbom-monitor.yml`, which files a labelled issue with `in:title`
dedup. (c) `workflow_dispatch`'s single-crate override is impossible against a static YAML
matrix list; it needs a preceding job emitting `fromJSON`-able output, which the sketch
omits — and that path is Verification step 1, the acceptance check for the whole fix.
(d) Workflow count is 41, not 39. (e) Local `make mutants` passes `--timeout 120` while CI
passes 30; the spec does not say whether legs call `make` or `cargo` directly.

Assumption: that a mutant killed by the `ulimit -v` cap is recorded CAUGHT rather than
`Unviable`, a tool error, or a baseline failure. Same settling command as Goal-Fit.

Disposition: **Addressed.** Keeping survivors and timeouts green is now explicitly what
makes partial-failure runs consumable, and is stated as such in Consumer wiring. PR legs
get the same cap and classifier. Labelled-issue notification added on the
`release-sbom-monitor.yml` pattern with `in:title` dedup. `plan` job added to make the
dispatch override real. Count corrected to 41 throughout and in the `CLAUDE.md` follow-up.
Makefiles move to `--timeout 30` to match CI; legs call `cargo` directly. Assumption
measured — see Goal-Fit disposition.

### Risk

Finding: **The memory cap's failure mode is a green run, not a red one.** The exit-code
table has no row for `unviable`, which is exactly the bucket the cap creates. Measured
against cargo-mutants 27.0.0 with mutant builds killed (exit 137, the OOM signature) and
the baseline untouched: `5 mutants tested in 1s: 5 unviable`, `exit=0` — green under the
proposed rule. The spec deliberately routes the cap to rustc ("every child process inherits
it") while calling the 8 GiB figure unverified, so the signal for "the cap is too tight" is
a green leg that tested nothing. The partial mitigation is real (a cap that starves rustc
outright fails the baseline, exit 4, red); the hole is the partial case, where the baseline
builds and later mutant builds do not, because they run against a populated target dir at
higher memory pressure. That degrades silently as `dtolnay/rust-toolchain@stable` pulls
newer rustc — the six-months-unnoticed failure this design exists to kill, reintroduced in
the harder-to-see direction. Fix, same script: classify on `mutants.out/outcomes.json`
counts, not the exit code alone — red on `total_mutants == 0`, red or threshold-warned on
`unviable > 0`. Exit 0 currently means "cargo-mutants had no complaint," not "this crate
was tested."

Secondary: (a) `mutation_review.py:684-686` does
`for candidate in artifact_dir.rglob("outcomes.json"): outcomes_path = candidate; break` —
first match then stop, so even a correctly merged 11-crate artifact yields one crate.
(b) The per-leg upload `path:` is unspecified; carrying over `**/mutants.out/` in a
single-crate leg makes upload-artifact's least-common-ancestor rule strip the crate prefix,
so `merge-multiple: true` collides all 11 legs onto identical paths. (c) The cosmic-ray
consumer branch reads `artifact_dir / "cosmic-ray-session.sqlite"` with no rglob fallback,
and that file is never uploaded — the Python consumer path has never worked.
(d) `if: needs.detect.outputs.rust != '[]'` fails open: if `detect` errors before writing
the output the value is `''`, the comparison is true, the job runs, and `fromJSON('')`
throws.

Assumption: that a too-tight `ulimit -v` fails loudly. The spec's tuning plan ("if it
starves rustc, raise it") only works if starving rustc yields a red leg. Settled on Linux
in the largest-build crate: exit 0 or 2 with `unviable > 0` refutes it and the classifier
must gate on counts; exit 4 or `unviable == 0` confirms it.

Disposition: **Addressed.** Classification now reads `outcomes.json` counts — red on
`total_mutants == 0`, on missing/unparseable output, and on `unviable` above a committed
per-crate expected count — with the exit-code table demoted to a secondary rule and the
`unviable`-is-green hole documented inline. All four secondary items fixed: `rglob`
collect-all and the sqlite upload are named ai-config/math changes, per-leg staging into
`out/<slug>/` is specified with the LCA rationale, and the `detect` guard fails closed on a
positive boolean. Assumption **partially settled**: measured clean on `collatz-rs` (capped
and uncapped produce the same single unviable), so the cap is not starving that crate.
`factorial-rs` and the other nine remain unmeasured, which is why the per-crate
capped-vs-uncapped comparison is now Verification step 2 rather than a tuning note.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
