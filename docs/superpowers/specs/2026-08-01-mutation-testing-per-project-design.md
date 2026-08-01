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

1. **All 11 crates run in one job.** The first crate to exhaust memory kills the runner,
   so no crate after it in `find` order is ever tested. In practice roughly two of eleven
   crates get any coverage per run.
2. **Artifacts never upload.** The `Upload mutants output` step is `if: always()`, but
   SIGTERM skips it (confirmed `skipped` in the 2026-08-01 run). Six months of runs
   produced zero artifacts for the `mutation-review` skill to consume.
3. **The Python sibling hides its failures.** `mutation-testing-python.yml` runs
   `make -C "${dir}" mutants || true`, so the workflow is green regardless of what
   happened. Its 2026-08-01 "success" carries no information.
4. **`mutation-pr.yml` covers one crate of eleven.** It hardcodes a
   `^factorial/factorial-rs/.*\.rs$` diff check; the other ten crates have no per-PR
   mutation coverage at all.

## Goals

- One project's failure cannot suppress another project's result.
- An allocation-unbounded mutant is recorded as CAUGHT, not as a dead runner.
- A red run means something is genuinely broken and warrants a look.
- Reports reach the `mutation-review` skill without a cross-repo change.
- Per-PR mutation coverage extends to all 11 Rust crates and all 8 Python sub-projects.

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
amicable/amicable-rs          fib/fib-rs                    pi/pi-rs
collatz/collatz-rs            goldbach/goldbach-rs          prime/prime-rs
e/e-rs                        perfect-numbers/perfect-numbers-rs   sq/sq-rs
factorial/factorial-rs        twin-primes/twin-primes-rs
```

**8 Python sub-projects** (each has a `cosmic-ray.toml`):

```
amicable   collatz   e   factorial   fib   perfect-numbers   pi   sq
```

`goldbach`, `prime`, and `twin-primes` are Rust-only and have no Python leg.

## Design

### Workflow structure

All three workflows become matrix-based. No workflow file is added or removed — the repo
stays at 39. Two non-workflow files are added: `scripts/mutation-classify.sh` and
`tests/scripts/mutation_classify.bats` (see Classification script below).

**`mutation-testing.yml`** — Rust, monthly `cron: "0 4 1 * *"`, plus `workflow_dispatch`.

```yaml
jobs:
  mutants:
    strategy:
      fail-fast: false
      matrix:
        crate: [ <11 crate paths> ]
    runs-on: ubuntu-latest
    timeout-minutes: 60          # per leg; was 360 shared across all 11
                                 # basis: slowest measured crate was 98 mutants in 6m
                                 # (factorial-rs, 2026-07-01), so 60 is ~10x headroom
    steps:
      - checkout, rust-toolchain, cargo install cargo-mutants --locked
      - run mutants under a memory cap (below)
      - classify the exit code (below)
      - upload-artifact: mutants-output-<slug>

  aggregate:
    needs: [mutants]
    if: always()
    steps:
      - download-artifact: pattern mutants-output-*, merge-multiple: true
      - upload-artifact: mutants-output
```

**`mutation-testing-python.yml`** — monthly `cron: "0 6 1 * *"`, plus `workflow_dispatch`.
Same shape, 8 legs, each running `make -C <dir> mutants`. The `|| true` is deleted.
Aggregate job re-uploads under `mutants-report-python`.

**`mutation-pr.yml`** — `pull_request` to master. A `detect` job emits two JSON arrays
computed from the PR diff; two matrix jobs consume them:

```yaml
jobs:
  detect:
    outputs:
      rust: ${{ steps.d.outputs.rust }} # e.g. '["collatz/collatz-rs"]'
      python: ${{ steps.d.outputs.python }} # e.g. '["collatz"]'

  mutants-rust:
    needs: [detect]
    if: needs.detect.outputs.rust != '[]'
    strategy:
      fail-fast: false
      matrix:
        crate: ${{ fromJSON(needs.detect.outputs.rust) }}
    steps:
      - cargo mutants --in-diff /tmp/pr.diff --timeout 30 --no-shuffle

  mutants-python:
    needs: [detect]
    if: needs.detect.outputs.python != '[]'
    strategy:
      fail-fast: false
      matrix:
        subproject: ${{ fromJSON(needs.detect.outputs.python) }}
```

Python legs keep their existing advisory-warning semantics: cosmic-ray has no `--in-diff`
equivalent, so it runs every mutation and pre-existing survivors would otherwise fire on
every Python PR.

`timeout-minutes` moves from the job (10, shared) to each leg (10, per project), since a
leg now covers one project rather than all of them. `.cargo/mutants.toml` exclusion files
in four crates are untouched by this work.

### Matrix leg isolation

Each matrix leg is scheduled on its own runner with its own 16 GB. One crate exhausting
memory kills one leg. `fail-fast: false` prevents GitHub from cancelling the surviving
legs when one fails.

`workflow_dispatch`'s single-project input is preserved on both monthly workflows: when the
input is non-empty the matrix is overridden to that one entry, when empty it is the full
list.

### Artifact naming

Artifact names cannot contain `/`. Each leg uploads under a slug with slashes replaced by
hyphens:

```
collatz/collatz-rs  ->  mutants-output-collatz-collatz-rs
```

`actions/upload-artifact@v7` rejects two uploads sharing one name, so per-leg names are
mandatory, not stylistic.

### Consumer compatibility

ai-config's `mutation_review.py` fetches exactly one named artifact
(`--artifact mutants-report-python`, `--artifact mutants-output`). The `aggregate` job
downloads every leg artifact by pattern, merges them, and re-uploads under the original
single name — so the consumer contract is unchanged and no cross-repo edit is required.

`aggregate` carries `if: always()` so a failed leg still yields a merged artifact covering
the legs that succeeded.

### Memory cap

Each leg sets an address-space limit before invoking the mutation tool:

```bash
ulimit -v 8388608   # 8 GiB, expressed in KiB; runner has 16 GB
```

Every child process inherits it — rustc, cargo, and the mutated test binary. A runaway
mutant hits allocation failure and aborts; the test fails; cargo-mutants records the mutant
as CAUGHT. That is the correct outcome, and it means `collatz-rs`'s two unbounded-`Vec`
mutants need no `.cargo/mutants.toml` exclusion.

**The 8 GiB figure is a starting value, not a verified one.** `ulimit -v` caps virtual
address space, and rustc reserves generously. The value is only settled by the acceptance
check below: every leg must build _and_ the collatz mutants must register CAUGHT. If 8 GiB
starves rustc, raise it until both hold, and record the settled value in `CLAUDE.md`.

### Exit-code classification

Verified empirically against `cargo-mutants 27.0.0` using purpose-built scratch crates
(a crate with an uncaught mutant, one with a failing baseline test, one with an
infinite-loop mutant). The `--help` output does not document these:

| code                      | meaning                                    | verdict                                        |
| ------------------------- | ------------------------------------------ | ---------------------------------------------- |
| 0                         | all mutants caught                         | green                                          |
| 2                         | surviving mutants                          | green, count written to `$GITHUB_STEP_SUMMARY` |
| 3                         | timeouts present                           | green, count written to summary                |
| 4                         | baseline tests failed in an unmutated tree | **red**                                        |
| anything else (incl. 143) | tool error, runner kill, OOM               | **red**                                        |

Rationale for 2 and 3 being green: `CLAUDE.md` states >80% kill rate is good for math code
and 100% is rarely achievable, so survivors are the expected steady state. Timeouts are
likewise pre-existing — the 2026-07-01 run measured 4 in `perfect-numbers-rs` and 1 in
`amicable-rs` — and are a slow mutant, not broken infrastructure. Making either red
guarantees a red run every month, which is precisely the noise that let six consecutive
genuine failures go unnoticed.

Python legs have no equivalent exit-code table — `make -C <dir> mutants` returns
cosmic-ray's own status, which does not encode survivor counts. The leg therefore parses
the survivor count out of `cr-report` for the summary, and is red only when
`make mutants` itself fails. Deleting `|| true` is what makes that failure visible; it does
not turn survivors red.

### Classification script

The exit-code logic lives in `scripts/mutation-classify.sh`, not inline in a `run:` block.
The workflow calls it. Inline YAML cannot be unit-tested, and this repo already runs
`bats --recursive tests/` via `scripts.yml`.

`tests/scripts/mutation_classify.bats` covers every code in the table — 0, 2, 3, 4, 143,
and an unknown code — with both branches of every guard exercised, per this repo's testing
policy.

## Verification

Both monthly workflows already exist on the default branch with `workflow_dispatch`, so
branch dispatch works before merge. (A workflow absent from the default branch cannot be
dispatched by `--ref` at all — GitHub resolves the workflow list against the default
branch.)

1. **The fix itself.**
   `gh workflow run mutation-testing.yml --ref <branch> -f crate=collatz/collatz-rs`
   Expected: leg green; `src/lib.rs:4:5` and `src/lib.rs:5:11` mutants both recorded
   CAUGHT; no exit 143 anywhere in the log.
2. **Isolation.** Full 11-leg dispatch on the branch. Expected: all 11 legs reach a
   terminal state; `aggregate` produces `mutants-output` containing 11 crates' `mutants.out/`.
3. **Python.** Dispatch `mutation-testing-python.yml` on the branch. Expected: 8 legs
   terminal, aggregate produces `mutants-report-python`.
4. **Consumer contract.** Run `mutation_review.py --artifact mutants-output` against the
   branch run. Expected: it locates and parses the merged artifact.
5. **PR matrix path.** A throwaway PR touching one crate's `src/`. Expected: `detect`
   emits that crate, `mutants-rust` runs exactly one leg.

Step 5 is not optional. The implementation PR touches only workflow and script files, so it
exercises `detect`'s empty-diff skip path and nothing else. This repo's standards already
record a change-detection script that shipped completely inert because its tests only ever
covered the path the implementation PR happened to take.

## Consequences

**Runner minutes.** `cargo install cargo-mutants --locked` runs once per leg instead of
once per run — roughly 11 × 70 s of extra runner time monthly. Wall clock is unchanged
because legs run in parallel. A prebuilt-binary install action would remove it at the cost
of a new third-party dependency; not worth it at ~13 minutes a month.

**Concurrency.** 11 legs at 04:00 and 8 at 06:00 on the first of the month. The crons stay
staggered so the two matrices never contend.

**Rollback.** Single `git revert`. No state, no migration, no baseline file.

**Docs.** `CLAUDE.md`'s CI table job descriptions change (file count stays 39). The note
attributing these failures to the 360-minute timeout is corrected, and the settled
`ulimit -v` value is recorded.

## Open decisions

None. All resolved during brainstorming: scope (all three workflows), mechanism (matrix
legs, 2 monthly files), memory cap (`ulimit -v`), red semantics (infra-only), PR gate
(dynamic matrix from diff), artifacts (aggregate job restores the single name), timeouts
(green, counted).
