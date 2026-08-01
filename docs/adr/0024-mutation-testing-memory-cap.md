# ADR-0024: Mutation testing memory cap and stateless classification

**Status:** Accepted
**Date:** 2026-08-01

## Context

`mutation-testing.yml` had never passed. All six runs since the workflow was
introduced failed identically:

| Run         | Date       | Trigger           |
| ----------- | ---------- | ----------------- |
| 30685027791 | 2026-08-01 | schedule          |
| 28495704109 | 2026-07-01 | schedule          |
| 26766884122 | 2026-06-01 | workflow_dispatch |
| 26760109155 | 2026-06-01 | workflow_dispatch |
| 26756239200 | 2026-06-01 | workflow_dispatch |
| 26737080954 | 2026-06-01 | schedule          |

Every one ended with the runner terminated mid-job:

```
ERROR interrupted
##[error]The runner has received a shutdown signal.
##[error]Process completed with exit code 143
```

Exit 143 is SIGTERM. The job-level `timeout-minutes: 360` was never approached —
the 2026-08-01 run died 119 seconds in.

**Root cause.** `cargo mutants --timeout` is a wall-clock bound with no memory
bound. A mutation that makes a loop non-convergent grows an allocation until the
16 GB runner is exhausted, and the runner agent is killed along with the job. The
memory ceiling is reached well inside the 30-second per-mutant budget, so the
existing timeout can never catch it.

In `collatz/collatz-rs/src/lib.rs`, `chain_length` pushes to `path: Vec<u64>` on
every iteration and only breaks when `curr <= limit && cache[curr] != 0`. Two of
the first four mutants in `--no-shuffle` order make that break unreachable:
`replace collatz_next -> u64 with 0` and `replace / with * in collatz_next`. A
capped repro reached 200M iterations and ~2 GB of `path` without converging.

The 2026-06-01 run died in `factorial/factorial-rs` instead, so this is a class of
failure — allocation-unbounded mutants — not one crate's bug.

A prior diagnosis recorded in `CLAUDE.md` attributed the failures to the
360-minute CI timeout combined with infinite-loop mutations, and reduced
`--timeout` from 120 to 30 in response. That diagnosis was wrong: time was never
the binding constraint, and the change did not help.

## Decision

**Cap address space at 8 GiB via `ulimit -v` in each crate's `Makefile`**, not in
the workflow. The workflow calls `make -C <crate> mutants`, so a local
`make mutants` and a CI run share one definition of the budget — they previously
disagreed (120 vs 30) with nothing to reconcile them.

The recipe is a single shell line. Each `make` recipe line runs in its own shell,
so a `ulimit` on one line and `cargo` on the next would set a limit in a shell
that exits immediately — a probe presented as enforcement.

`MUTANTS_UNCAPPED=1` opts out, and is checked **before** the `ulimit`, not in its
failure branch. Written the other way it is consulted only when `ulimit -v` fails,
which never happens on Linux, so the flag would silently do nothing on the only
platform CI runs on and mean two different things by operating system.

**Classify on `outcomes.json` counts, not the exit code alone.** The stateless
rule is:

```
red if (caught + missed) == 0
```

Two distinct buckets exit green while establishing nothing. A run of nothing but
`unviable` mutants exits **0** — measured against cargo-mutants 27.0.0 with
mutant builds killed at exit 137: `5 mutants tested in 1s: 5 unviable`, `exit=0`.
A run of nothing but timeouts exits **3**, and that is precisely the cap's blind
spot, since `ulimit -v` catches allocating runaways but a mutation that spins
without allocating still times out. One rule covers both, plus the zero-mutant
case.

An earlier draft gated on a committed per-crate expected-`unviable` count. It was
rejected: `unviable` is "does the mutated code compile", perturbed by any source
change and by `dtolnay/rust-toolchain@stable` pulling a new rustc, so the number
would drift on ordinary churn and each false red would blank that month's report.
The rule above needs no committed state.

**Notification is a separate job**, not a step. SIGTERM skips `if: always()`
_steps_ inside the job it kills — which is why six months of runs uploaded zero
artifacts. An in-job notification therefore cannot report runner death or a job
timeout, the two failure classes with no other output. A job with
`needs: [mutants], if: always()` runs on a fresh runner and survives.

## Consequences

- A runaway mutant is recorded CAUGHT rather than killing the runner. Measured on
  `collatz/collatz-rs` under `docker --platform linux/amd64`: capped gives exit 2
  with 36 caught / 4 missed / 1 unviable; uncapped gives exit 3 with 35 caught /
  4 missed / 1 **identical** unviable. The cap converts a timeout into a catch and
  starves no build.
- Exit codes 2 (survivors) and 3 (timeouts) are green. Survivors are the expected
  steady state — `CLAUDE.md` states >80% kill rate is good for math code and 100%
  is rarely achievable — and pre-existing timeouts were measured in
  `perfect-numbers-rs` (4) and `amicable-rs` (1). Making either red guarantees a
  red run every month, which is the noise that let six genuine failures pass
  unnoticed.
- **Partial cap starvation is checked once, at merge, and is not monitored after.**
  If a later rustc pushes a crate over the limit, the `caught + missed == 0` rule
  catches total starvation but not partial. The `unviable` count is written to the
  job summary as the only ongoing signal.
- macOS cannot enforce `ulimit -v` at all (`cannot modify limit: Invalid
argument`), so a local `make mutants` fails closed with an explicit override
  rather than silently running uncapped. A hard refusal was considered and
  rejected — math PRs #83 and #84, the only work that has ever raised kill rate
  here, were local `make mutants` runs on macOS.

## Related

- ADR-0022 — Python mutation testing via cosmic-ray
- `docs/superpowers/specs/2026-08-01-mutation-testing-per-project-design.md`
- Phase B, triggered by the first green full run, decides the per-crate matrix,
  artifact aggregation, and whether per-PR mutation coverage is worth having.
