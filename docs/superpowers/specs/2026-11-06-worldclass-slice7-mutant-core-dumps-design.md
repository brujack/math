# Worldclass slice 7: no core dumps from mutation runs

- **Approved:** 2026-11-06

Status: approved (round 3, after the CI probe). Supersedes the round-1 (deadline + sampler) and round-2 (4 GiB cap + shards) designs, both withdrawn: each designed against a cause the evidence later refuted.

## Problem

The monthly Rust sweep (`mutation-testing.yml`) loses hosted runners. Slice 6 V2 (runs 42087535763, 42087540288) and run 42157905568 lost pi-rs, fib-rs and collatz-rs legs: either "The hosted runner lost communication with the server ... starves it for CPU/Memory" (job declared lost ~44 min after the runner went silent) or "The runner has received a shutdown signal" a few minutes into `Run mutants`. A lost leg is red and leaves no log blob, so the sweep cannot go green and the cause was invisible. Issue #217.

### Cause, measured

A throwaway probe branch (never merged, since deleted) ran the unchanged `make mutants` step for pi-rs ×2, collatz-rs, fib-rs and sq-rs on `ubuntu-latest`, with a sidecar that sampled memory, PSI, disk and the top processes every 5 s and mirrored them into a check run, so the data outlived a lost runner.

Run 42314053243 (probe commit `b911e2e`):

- The runner image pipes core dumps to `systemd-coredump` (`core_pattern=|/usr/lib/systemd/systemd-coredump %P %u %g %s %t %c %h %d %F`) with `ulimit -c unlimited`.
- A mutant whose test allocates without bound hits the 8 GiB `ulimit -v` cap and aborts. The kernel then streams its whole image (4-6 GB) to `systemd-coredump`, and the process cannot exit until the dump is consumed. cargo-mutants records a timeout and starts the next mutant, so dumping processes accumulate.
- collatz-rs, final samples: three test binaries alive at 92, 124 and 160 s holding 4.9, 4.1 and 1.7 GB; 12 GB used, swap 3071/3071 MB, PSI `mem.full` 76 %, `io.full` 82 %; then "shutdown signal" at 6.5 min.
- fib-rs: two test binaries at 6.4 and 5.8 GB, `systemd-coredump` running, swap rising to 2.4 GB, `mem.full` 45 % and climbing when telemetry stopped at 23:53; the job was declared lost at 00:37.
- `systemd-coredump` appeared in 13-48 samples of every leg; pi-rs and sq-rs survived only because their dumps did not overlap enough. No kernel OOM lines; the `systemd-oomd` journal was empty.

Run 42321581538 (probe commit `885ceb5`): identical except `ulimit -c 0` before `make mutants`.

| leg        | without (42314053243) | with `ulimit -c 0` (42321581538)                                           |
| ---------- | --------------------- | -------------------------------------------------------------------------- |
| pi-rs (×2) | green, green          | green, green: 159 caught, 4 timeouts, 3 unviable; peak used 6.5 GB, swap 0 |
| fib-rs     | lost                  | green in 6 min: 38 caught, 1 timeout                                       |
| sq-rs      | green                 | green in 3 min: 29 caught, 1 timeout                                       |
| collatz-rs | shutdown at 6.5 min   | green in 73 s: 42 caught, 0 timeouts, 1 unviable                           |

With the limit at 0: zero `systemd-coredump` samples in all five legs, swap 0, `mem.full` 0.0 throughout. `systemd-coredump` receives the crashing process's limit as `%c` and refuses to store a dump when it is 0, so the abort completes at once.

Population: both runs measured one leg per crate on hosted `ubuntu-latest` (Ubuntu 26.04, 4 vCPU, 16 GB) for four of the eleven crates; the claim covers all eleven crates on that image. The other seven were not probed; they share the template and the image, and V1 covers them.

Why no local run reproduced it: `claude` pipes cores to apport with `ulimit -c 0`, so a capped-out mutant dies immediately (the round-2 cgroup probe peaked at 2,960 MB).

A side effect worth recording: collatz-rs's six "timeouts" in earlier sweeps were tests stalled behind their own dump. With no dump they abort at the cap and count as caught. Earlier timeout counts on this image are therefore not evidence of slow mutants.

### #217's misleading body

#217 reads `Cause: verdicts-present` / `Failing crates: (none flagged; see run log)` and then `Cause: missing-status`. `mutation-notify.sh` prepends `build_body` whenever the run failed and any status file arrived, even when none of them is red.

## Design

### 1. No core dumps in the Rust mutation setup (template)

`scripts/crate_templates/Makefile`'s `MUTANTS_SETUP` sets `ulimit -c 0` immediately after `ulimit -f 262144` and before the `MUTANTS_UNCAPPED` branch, so it applies capped and uncapped. A failure prints `error: cannot disable core dumps (ulimit -c 0).` and exits 1, matching the `-f` line. Bare `ulimit -c 0` lowers both the soft and the hard limit, so nothing below the recipe can re-enable dumps; that lock is intended. Lowering a limit cannot fail on Linux or macOS, so the error branch is defensive. `scripts/render_crate_files.py --write` renders it to all 11 crates; `mutants` and `mutants-diff` both use `MUTANTS_SETUP`, so the sweep and `mutation-pr.yml` are covered.

The 8 GiB `ulimit -v` cap is unchanged. It still ends an allocation-unbounded mutant; the mutant now aborts without a dump.

### 2. The same line in the Python mutation setup (template)

`scripts/crate_templates/python/Makefile`'s `MUTANTS_CAP` gets the same line in the same position. Python under the cap raises `MemoryError` rather than aborting, so this is uniformity, not a measured fix: a C-extension abort (gmpy2) under the cap would dump the same way.

### 3. `mutation-notify.sh` body

When the cause is `verdicts-present` and `render_red_units` returns nothing, the expected-units path does not prepend `build_body`: the `missing-status` body stands alone. With a red unit present the body is unchanged.

### 4. Docs

ADR-0043 amends ADR-0024: records the cause, both probe runs, and that the memory cap needs core dumps off to bound memory on a host that pipes cores. CLAUDE.md's mutation memory cap line names `ulimit -c 0`. The Backlog row "Hosted runners lost mid-sweep on fib-rs/pi-rs" is rewritten to name the cause and await V1 (removed after V1), and the plan index gets this slice's spec and plan rows.

## Rejected alternatives

- **4 GiB cap (round 2).** Halves dump size but keeps the dumps; also broke local unpinned runs (7/20 thread-spawn failures) without `MALLOC_ARENA_MAX=2`.
- **Sharding (round 2).** Changed no verdict and blurred attribution.
- **Deadline + sampler (round 1).** Premise false: the runner dies 3-12 min into the step, not at the deadline.
- **Disable `systemd-coredump` in the workflow (`sudo sysctl kernel.core_pattern=...`).** Fixes CI only; a developer box piping to `systemd-coredump` with a raised limit would still dump. The Makefile is the one place every run passes through.

## Testing

- **Rust:** `tests/scripts/makefile.bats`: for a rendered crate, a mocked `cargo` records `ulimit -c`; the `mutants` and `mutants-diff` recipes give 0, with and without `MUTANTS_UNCAPPED=1`. Each test first raises the parent soft limit to `$(ulimit -Hc)` and asserts it is non-zero (skipping otherwise), because both dev boxes already run with a soft limit of 0 and a test inheriting it would pass without the fix; a missing record line fails the test.
- **Python:** the same, for both `MUTANTS_CAP` targets (`mutants`, `mutants-baseline`) with a mocked `cosmic-ray`.
- **Notify:** `tests/scripts/mutation_notify.bats`: failed run, every arriving status green, one unit missing → body starts `Cause: missing-status` and contains no `verdicts-present`; one red unit present → body as on master.
- `tests/test_crate_uniformity.py` passes after `--write`.

## Requirements

- **R1.** `[PR1]` The Rust template's `MUTANTS_SETUP` runs `ulimit -c 0` after `ulimit -f 262144` and before the `MUTANTS_UNCAPPED` branch, exiting 1 with `error: cannot disable core dumps (ulimit -c 0).` on failure.
- **R2.** `[PR1]` All 11 rendered crate `Makefile`s match the template (`tests/test_crate_uniformity.py` green).
- **R3.** `[PR1]` The Python template's `MUTANTS_CAP` runs `ulimit -c 0` after `ulimit -f 262144` and before its `MUTANTS_UNCAPPED` branch, with the same error line, rendered to every Python project.
- **R4.** `[PR1]` `tests/scripts/makefile.bats` asserts a mocked `cargo` sees `ulimit -c` = 0 under `mutants` and `mutants-diff`, capped and with `MUTANTS_UNCAPPED=1`, after raising the parent soft limit to `$(ulimit -Hc)` and asserting it non-zero (skip otherwise), and fails when the mock wrote no record line; and a mocked `cosmic-ray` sees 0 under every Python target that uses `MUTANTS_CAP` (`mutants`, `mutants-baseline`), capped and uncapped.
- **R5.** `[PR1]` `mutation-notify.sh` omits the `verdicts-present` prefix when no arriving status is red, so the body starts `Cause: missing-status`; with a red status the body is unchanged from master.
- **R6.** `[PR1]` `tests/scripts/mutation_notify.bats` covers both R5 cases.
- **R7.** `[PR1]` `docs/adr/0043-mutation-runs-disable-core-dumps.md` exists, amends ADR-0024, cites runs 42314053243 and 42321581538, and is indexed in `docs/adr/README.md`.
- **R8.** `[PR1]` Root `CLAUDE.md`'s mutation memory cap line names `ulimit -c 0`, and the file stays under 30,000 bytes.
- **R9.** `[PR1]` The Backlog row "Hosted runners lost mid-sweep on fib-rs/pi-rs" in `docs/superpowers/README.md` is rewritten to name the core-dump cause, this PR, and "awaiting V1"; it is not removed in PR1.
- **V1.** After merge, one full 11-crate `mutation-testing.yml` dispatch on master: no leg lost, no "shutdown signal", every leg has a status file; then remove the Backlog row citing that run id. A MISSED mutant in V1 (e-rs and factorial-rs carried 5 and 4 timeouts in run 42157905568) is the fix exposing a survivor that a dump stall had scored TIMEOUT: it gets a killing test, not a revert.
- **V2.** Done: probe runs 42314053243 (dumps on: collatz-rs shutdown, fib-rs lost) and 42321581538 (`ulimit -c 0`: 5/5 green, 0 `systemd-coredump` samples, swap 0).
- **V3.** ai-config's `math-testing-policy.md` § Mutation memory cap records the core-dump cause, via the session that owns ai-config.
- **N1.** The `ulimit -v 8388608` value is unchanged in both templates.
- **N2.** `mutation-testing.yml`'s matrix, timeouts and steps are unchanged.
- **N3.** The cargo-mutants flags in the `mutants` and `mutants-diff` recipes are unchanged.
- **N4.** No crate or Python project differs from its template.

## Multi-Lens Review

Reviewed at commit: `51ffd11` (round 3, against the core-dump design)

### Goal-Fit

Finding: Worth building; one template line backed by a controlled A/B. One flaw: R9 removes the "Hosted runners lost" Backlog row in PR1, before V1 has run on the seven unprobed crates, so the durable record of an open problem disappears when the claim is least proven. Keep the row in PR1 (marked fix shipped, awaiting V1) and remove it in the V1 follow-up citing V1's run id. Premise check: `gh run view` on 42314053243 / 42321581538 confirms the run-level A/B. Assumption: no non-dump mechanism exhausts memory on the seven unprobed crates; V1 settles it.
Disposition: Addressed — operator 2026-11-06: R9 now rewrites the row and V1 removes it citing its run id.

### Ergonomics

Finding: No load-bearing problem; both dev boxes and macOS already run with soft core limit 0, so local runs see no change. (1) §1's "lowering a soft limit" is wrong: bare `ulimit -c 0` lowers soft and hard, so a child cannot re-enable dumps; harmless, but the text must say so. (2) R4 passes without the fix on `claude` and `workstation` (soft limit already 0) unless the test raises the parent limit to `$(ulimit -Hc)` first, asserts it is non-zero (skip otherwise), and greps the mock's recorded line so a missing call fails. Premise check: `ulimit -Sc; ulimit -Hc` → `0` / `unlimited` on both boxes; `bash -c 'ulimit -c 0; ulimit -Hc'` → `0`. Assumption: the unprobed crates lose runners only through dumps; V1 or a probe of those seven settles it.
Disposition: Addressed — operator 2026-11-06: §1 wording corrected (soft and hard limit, lock intended); R4 and Testing require raising to `$(ulimit -Hc)`, a non-zero precondition and a record line.

### Risk

Finding: Passes; failure mode far smaller than the problem. (1) Turning dumps off cannot turn a caught mutant MISSED (a cap abort fails the test either way), but it can turn a slow-but-passing mutant that previously stalled into TIMEOUT (green) into MISSED (red). e-rs (5 timeouts) and factorial-rs (4) in run 42157905568 are candidates, so V1 may go red on a real survivor; the spec must say that red is the fix working and needs a killing test, not a revert. (2) Same R4 precondition gap as Ergonomics (2). Notify change hides no red. Premise check: probe check-run telemetry recounted: coredump samples 28/30, 16, 12, 48 with dumps on vs 0 ×5 off; swap 3071 vs 0. Assumption: an aborted test binary leaves no lingering child holding memory; V1's e-rs and factorial-rs legs confirm.
Disposition: Addressed — operator 2026-11-06: V1 states a MISSED is a real survivor needing a killing test; R4 precondition as for Ergonomics.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
