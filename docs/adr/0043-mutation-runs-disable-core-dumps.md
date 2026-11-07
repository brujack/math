# ADR-0043: Mutation runs disable core dumps

**Date:** 2026-11-06
**Status:** Accepted

## Context

Hosted runners were lost mid-sweep on fib-rs and pi-rs (#217). ADR-0024 capped each mutation
process at 8 GiB of address space (`ulimit -v 8388608`) and each file at 256 MiB, on the
assumption that the cap bounds what a runaway mutant can cost. The cap did not stop the losses.

A throwaway probe branch (never merged, since deleted) ran the unchanged `make mutants` step for
pi-rs (twice), collatz-rs, fib-rs and sq-rs on `ubuntu-latest`. A sidecar sampled memory, PSI,
disk and the top processes every 5 s and mirrored them into a check run, so the data outlived a
lost runner.

Run 42314053243 (probe commit `b911e2e`):

- The runner image pipes core dumps to `systemd-coredump`
  (`core_pattern=|/usr/lib/systemd/systemd-coredump %P %u %g %s %t %c %h %d %F`) with
  `ulimit -c unlimited`.
- A mutant whose test allocates without bound hits the 8 GiB `ulimit -v` cap and aborts. The
  kernel then streams its whole image (4-6 GB) to `systemd-coredump`, and the process cannot exit
  until the dump is consumed. cargo-mutants records a timeout and starts the next mutant, so
  dumping processes accumulate.
- collatz-rs, final samples: three test binaries alive at 92, 124 and 160 s holding 4.9, 4.1 and
  1.7 GB; 12 GB used, swap 3071/3071 MB, PSI `mem.full` 76 %, `io.full` 82 %; then "shutdown
  signal" at 6.5 min.
- fib-rs: two test binaries at 6.4 and 5.8 GB, `systemd-coredump` running, swap rising to 2.4 GB,
  `mem.full` 45 % and climbing when telemetry stopped at 23:53; the job was declared lost at
  00:37.
- `systemd-coredump` appeared in 13-48 samples of every leg. pi-rs and sq-rs survived only because
  their dumps did not overlap enough. There were no kernel OOM lines, and the `systemd-oomd`
  journal was empty.

Run 42321581538 (probe commit `885ceb5`) was identical except for `ulimit -c 0` before
`make mutants`:

| leg        | without (42314053243) | with `ulimit -c 0` (42321581538)                                           |
| ---------- | --------------------- | -------------------------------------------------------------------------- |
| pi-rs (x2) | green, green          | green, green: 159 caught, 4 timeouts, 3 unviable; peak used 6.5 GB, swap 0 |
| fib-rs     | lost                  | green in 6 min: 38 caught, 1 timeout                                       |
| sq-rs      | green                 | green in 3 min: 29 caught, 1 timeout                                       |
| collatz-rs | shutdown at 6.5 min   | green in 73 s: 42 caught, 0 timeouts, 1 unviable                           |

With the limit at 0 there were zero `systemd-coredump` samples in all five legs, swap stayed at 0,
and `mem.full` stayed at 0.0. `systemd-coredump` receives the crashing process's limit as `%c`
and refuses to store a dump when it is 0, so the abort completes at once.

Population: both runs measured one leg per crate on hosted `ubuntu-latest` (Ubuntu 26.04, 4 vCPU,
16 GB) for four of the eleven crates. The claim covers all eleven crates on that image. The other
seven were not probed; they share the template and the image, and the verification sweep (V1)
covers them.

No local run reproduced it because `claude` pipes cores to apport with `ulimit -c 0`, so a
capped-out mutant dies immediately.

Spec: `docs/superpowers/specs/2026-11-06-worldclass-slice7-mutant-core-dumps-design.md`.

## Decision

1. **Both mutation templates set `ulimit -c 0`** (no core dumps) in `MUTANTS_SETUP` (Rust) and
   `MUTANTS_CAP` (Python), before the uncapped branch, so it applies on every platform and with `MUTANTS_UNCAPPED=1`.
2. This amends ADR-0024: the 8 GiB address-space cap bounds memory only while core dumps are off.
   With dumps on, the abort at the cap turns into a multi-gigabyte write that outlives the process.

## Consequences

- collatz-rs's earlier timeouts were tests stalled behind their own dump. With no dump they abort
  at the cap and count as caught, so earlier timeout counts on this image are not evidence of slow
  mutants.
- The verification sweep V1 may surface real MISSED mutants that a dump stall had scored as
  timeouts (e-rs and factorial-rs carried 5 and 4 timeouts in run 42157905568). Each needs a killing test, not an exclusion.
- A core dump is no longer available to debug a crashing mutant on CI.

## Related

- ADR-0024: Mutation testing memory cap and stateless classification (amended)
- ADR-0042: The Rust mutation sweep holds zero missed
- Spec: `docs/superpowers/specs/2026-11-06-worldclass-slice7-mutant-core-dumps-design.md`
- Issue #217
