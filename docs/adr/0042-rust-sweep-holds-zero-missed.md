# ADR-0042: The Rust mutation sweep holds zero missed

**Date:** 2026-11-05
**Status:** Accepted

## Context

ADR-0024 scored cargo-mutants survivors (exit code 2) and timeouts (exit code 3) green in the
monthly sweep. Its reason was that survivors were the steady state, so scoring them red would
have made every month's report red. That no longer holds: slice 4 brought all 11 Rust crates to
0 missed mutants (full sweep run 41952665142). ADR-0041 then held 0 missed on changed lines per
PR, but the sweep itself still scored a new survivor green, so drift the per-PR gate cannot see
(deleted tests, a rustc update, a cargo-mutants bump that adds operators) went unreported.

A timeout is only safe to count as caught if re-running it with more time does not turn it into
a survivor. All 56 timeouts of run 41952665142 were re-run to find out.

Spec: `docs/superpowers/specs/2026-11-05-worldclass-slice6-rust-sweep-ratchet-design.md`.

## Decision

1. **`mutation-testing.yml` classifies each crate with `mutation-classify.sh ... 0 1`**
   (`max_missed` 0, `min_caught` 1). Any missed mutant is red, `caught < 1` is red, and a missing
   `outcomes.json` or `mutants.out/exit-code` is red.
2. **A timeout counts as caught** in both the per-PR gate and the sweep, so a timeout beside at
   least one catch is green.
3. This supersedes the survivors half of ADR-0024's "exit codes 2 and 3 are green" consequence.
   Timeouts stay green. ADR-0024's memory cap and stateless classification stand.
4. **The issue body names the cause.** It carries each red crate's reason and missed lines in a
   tilde fence (`render_red_units` in `scripts/mutation-notify.sh`), which answers ADR-0024's
   noise concern.

### Timeout classification

All 56 timeouts of run 41952665142, re-run with `--timeout 180` under the 8 GiB cap. None came
back missed.

| Crate              | Timeouts | Re-run result        | Source     |
| ------------------ | -------- | -------------------- | ---------- |
| collatz-rs         | 6        | 6 caught             | slice 5    |
| sq-rs              | 4        | 4 caught             | slice 5    |
| fib-rs             | 4        | 3 caught, 1 timeout  | slice 5    |
| factorial-rs       | 4        | 2 caught, 2 timeout  | slice 5    |
| goldbach-rs        | 3        | 1 caught, 2 timeout  | slice 5    |
| perfect-numbers-rs | 2        | 1 caught, 1 timeout  | slice 5    |
| twin-primes-rs     | 4        | 4 timeout            | slice 5    |
| amicable-rs        | 1        | 1 timeout            | slice 5    |
| pi-rs              | 4        | 2 caught, 2 timeout  | slice 6 V1 |
| prime-rs           | 12       | 9 caught, 3 timeout  | slice 6 V1 |
| e-rs               | 12       | 10 caught, 2 timeout | slice 6 V1 |
| Total              | 56       | 0 missed             |            |

Slice 5 re-ran at `7f9cd29` with `--timeout 180` and the 8 GiB cap, and recorded counts, not
names, for the crates it did not finish.

**V1 method (slice 6).** Measured 2026-11-05 on `claude` (48 threads) from a `git archive` copy
of `0d28038` with cargo-mutants 27.1.0. V1 re-ran all 28 timeouts of pi-rs, prime-rs and e-rs,
a superset of slice 5's 16 unmeasured, since slice 5 recorded counts and not names. Each full
mutant name was regex-escaped and anchored. `cargo mutants --list --re` printed exactly 1 line
per name, the combined selection matched the count, and `outcomes.json` `total_mutants` equalled
it. Unescaped names select nothing: `replace + with * in compute_e` printed 0 lines. Each crate
ran once with `--no-shuffle --timeout 180` under `ulimit -v 8388608`. e-rs also ran with
`MALLOC_ARENA_MAX=2`, because slice 5's e-rs baseline had failed under the cap alone (at
`7f9cd29`, before its 64-thread write tests were shrunk); with it, the baseline passed. V1 did not
re-run e-rs under the cap without `MALLOC_ARENA_MAX`, so glibc malloc arenas inflating address
space on a 48-core host is a consistent explanation, not a measured one. All three baselines
were ok.

### Procedures

- **Fix to close.** Kill the survivor locally with `make -C <crate> mutants`, since the per-PR
  gate cannot prove a kill on an unchanged line. Merge, then dispatch `mutation-testing.yml`
  with no `crate` input. A single-crate dispatch only comments; only a green full sweep closes
  the issue.
- **cargo-mutants bump.** The version is hand-pinned in the workflow (`--version 27.1.0`) and no
  Renovate manager covers it, so a bump PR dispatches a full sweep on its branch before merge.

## Consequences

- A survivor that appears without a code change turns the monthly sweep red. Three triggers
  need no commit: a new stable rustc resolved at run time, a cargo-mutants bump, and a
  runner-shape change (the math#204 precedent). The run log's rustc and `Image:` lines tell
  them apart.
- The ai-config mutation-review cargo-mutants leg is retired in a coordinated ai-config change,
  because it reads only successful runs and a red sweep now has none to read.
- `notify` no longer downloads the per-crate `mutants-output-<slug>` artifacts or re-uploads a
  merged `mutants-output`: that artifact existed only for the retired leg. This supersedes
  ADR-0040 decision 6, and it removes the failure mode where one corrupt per-crate output
  (`digest-mismatch: error` on that download) turned the whole sweep red. The per-crate
  artifacts are still uploaded and are where `missed.txt` lives.
- The Backlog row "Rust survivor drift across rustc releases" tracks measuring how often
  rustc releases move survivors.

## Related

- ADR-0024 (memory cap and stateless classification; survivors half superseded)
- ADR-0040 (one mutation job per Rust crate; decision 6 superseded)
- ADR-0041 (per-PR Rust mutation ratchet)
- `docs/superpowers/specs/2026-11-05-worldclass-slice6-rust-sweep-ratchet-design.md`
