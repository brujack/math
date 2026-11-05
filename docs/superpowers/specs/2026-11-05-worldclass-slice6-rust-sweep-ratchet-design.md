# Worldclass slice 6: the monthly Rust sweep holds 0 missed

- **Status:** Draft
- **Date:** 2026-11-05
- **Backlog rows:** "Rust mutation sweep drift the per-PR gate cannot see", "Per-PR Rust gate passes an all-timeout run"

## Context

Slice 4 (math#203, math#204) brought all 11 Rust crates to 0 missed mutants. Slice 5 (math#206,
ADR-0041) holds that line on the lines a PR changes. Two Backlog rows record what neither holds.
The operator folded both into this slice (2026-11-05).

Premises verified on master `7d55c62` before design:

1. **The sweep scores survivors green.** `.github/workflows/mutation-testing.yml:136` calls
   `scripts/mutation-classify.sh "${rc}" <outcomes.json> <crate>` with three arguments. Without a
   fourth argument the classifier is red only when `caught + missed == 0`, when the exit code is
   outside `{0, 2, 3}`, or when `outcomes.json` is missing with a non-zero code. A crate with
   survivors (cargo-mutants exit 2) is green. `scripts/mutation-notify.sh` then closes the
   tracking issue on a green full sweep. Rust has no survivor report (Python has
   `mutation-report-python`, issue #184). So a survivor that a deleted test, a rustc update or a
   cargo-mutants bump introduces appears only in the step summary of a green run.
   `tests/test_mutation_workflows.py:895` pins the three-argument call (`classifier_argc == ["3"]`).
2. **The all-timeout per-PR case is a decision slice 5 made, not an oversight.** Slice 5
   component 4 counts timeouts as evaluated in limit mode on purpose: in sweep run 41952665142
   every mutant of `collatz_next` (`collatz-rs` `src/lib.rs:9`) and of the `read_line_from`
   prompt-retry loops timed out, so a crate floor of `min_caught 1` would make a PR that touches
   only such a line red with nothing to fix. All-timeout is a property of the host as much as of
   the code: on unchanged collatz-rs source, run 41948343321 read caught=40/timeout=2 and
   41952665142 read caught=36/timeout=6, with `collatz_next -> u64 with 0` among the flips
   (Step 8 risk lens, `timeout.txt` diff). Slice 5 measured the assumption behind it
   (a timed-out mutant never terminates): 40 of that run's 56 timeouts were re-run with
   `--timeout 180` under the 8 GiB cap and none came back missed. 16 were not measured: e-rs 12
   (baseline failed under the cap on a 48-core host), prime-rs 2 and pi-rs 2 (run interrupted).
   The residual risk is a mutant that is slow but correct, timing out on a slow runner and
   hiding a survivor. Operator decision (2026-11-05): narrow, do not gate. Measure the 16, record
   the timeout rule in an ADR, and close the row as decided.
3. **This was rejected once, on a premise that no longer holds.** ADR-0024 (Consequences) made
   exit 2 green because "survivors are the expected steady state" and "making either red
   guarantees a red run every month, which is the noise that let six genuine failures pass
   unnoticed." Two things changed. Slice 4 made 0 missed the steady state in all 11 crates, and
   slice 5's per-PR gate keeps changed lines at 0, so a red sweep now means a new survivor rather
   than the standing population. ADR-0024's noise concern still applies to the issue body:
   `build_body`'s `verdicts-present` case (`scripts/mutation-notify.sh:61-63`) lists only the red
   unit names, so a survivor red and a runner failure read the same. Component 2 answers that.
   The 2026-08-01 per-project spec also rejected a committed per-crate missed baseline (ADR-0041,
   Context); this design adds none (N2). The steady state is young: run 41948343321 (`821acb1`)
   had e-rs and pi-rs at missed=1, and `821acb1..0d28038` is math#204 (which killed them) plus
   docs, so 0 missed rests on one sweep of current code. V2 tests whether it holds run to run.
5. **The only automated Rust survivor consumer is already dead and this slice would make it
   permanent.** ai-config `.github/workflows/mutation-review.yml` (cron `0 12 2 * *`) runs
   `mutation_review.py --repo brujack/math --workflow mutation-testing.yml --tool cargo-mutants`,
   which reads only the latest run with `conclusion == "success"` (`mutation_review.py:656`). It
   has never opened a PR, and it drafts `exclude_re` entries for survivors, which root `CLAUDE.md`
   reserves for true equivalents. Once a survivor turns the sweep red, it can never see one.
   Operator decision (2026-11-05): retire its cargo-mutants leg (V4); the tracking issue is the
   Rust survivor consumer.
4. **Root `CLAUDE.md` is 29,926 bytes against a 30,000-byte ceiling** (`wc -c CLAUDE.md` on
   `7d55c62`). The sweep rule's line is 400 bytes. Its rewrite must not grow the file past the
   ceiling.

## Design

### Components

1. **Sweep classifier arguments.** The `Run mutants` step of `mutation-testing.yml` calls the
   classifier with five arguments, `"${rc}" <outcomes.json> "${CRATE_DIR}" 0 1`, the canary's
   mode. The existing classifier then gives the sweep these rules, with no change to its code:
   - missed > 0 is red, and the `missed.txt` lines are printed (already captured into
     `status/<slug>` by the step's `2>&1`);
   - caught < 1 is red, so a crate whose mutants all time out stays red (without the `1`, limit
     mode would count timeouts as evaluated and turn that case green);
   - a missing `outcomes.json` is red whatever the exit code (today exit 0 without it is green,
     which a full crate cannot legitimately produce);
   - timeouts are green when caught ≥ 1 and missed is 0;
   - a non-green exit code (baseline failed, runner died) is red, as today.
2. **Issue body carries each red unit's status, from one helper.** A single function in
   `scripts/mutation-notify.sh` renders the red units. For each status file containing a line
   that starts with `red`, it prints `- <unit>: <line>`, where `<line>` is that first `red`
   line. The detail lines are every line after it (a preamble before the first `red` line is not
   printed); when there are any, they follow inside a fenced code block indented two spaces under
   the list item, at most 20 of them, with `... <K> more lines in the run` as the block's last
   line when K > 0. The fence is required: GitHub renders a raw `replace sieve -> Vec<u32> with
   vec![]` in a list item as `replace sieve -> Vec with vec![]` (measured 2026-11-05 with
   `gh api -X POST /markdown`, mode `gfm`), and return-value replacements are a main
   cargo-mutants mutation kind. Both `build_body`'s `verdicts-present` case and
   `build_units_body` call it, replacing `build_units_body`'s own loop. A posted body lists each
   red unit once: when `check_expected_units` prefixes a `verdicts-present` body to the
   missing-status report, the red list is not printed a second time. For a Rust crate the body
   thus carries the reason (`missed=N exceeds max_missed=0`, `caught=0 below min_caught=1`, an
   exit code) and the `missed: src/lib.rs:LINE:COL: ...` lines. The cap
   keeps a mass-survivor month (a cargo-mutants bump adding an operator) under GitHub's
   65,536-character comment limit: 11 units of 24 lines at about 200 bytes stays near 53 KB. No
   total byte cap: an oversize body fails `gh` loudly (accepted, operator 2026-11-05).
   Python status files are single `red: <label> — <reason>` lines (`mutation-python-cell.sh`,
   `cosmic_ray_cell_status.py`), so the Python body gains only the reason.
3. **ADR-0042: the Rust sweep holds 0 missed; a timeout counts as caught.** Records component 1,
   supersedes the survivors half of ADR-0024's "Exit codes 2 and 3 are green" consequence, states
   the timeout rule for both the per-PR gate and the sweep, and carries the timeout
   classification table: slice 5's 40 measured plus the 16 measured under V1. It also states two
   procedures. Fix-to-close: kill the survivor locally (`make -C <crate> mutants`, which the
   per-PR gate cannot prove because the survivor's line is unchanged), merge, then dispatch
   `mutation-testing.yml` with no `crate` input; a single-crate dispatch only comments, and only
   a green full sweep closes the issue. cargo-mutants bump: the version is hand-pinned (no
   Renovate manager), so a bump PR dispatches a full sweep on its branch before merge.
4. **Documentation.** Root `CLAUDE.md`'s "A sweep leg is red only when ..." line is rewritten in
   place to the component 1 rules, at no more than its current 400 bytes. The two Backlog rows
   are removed, and one Backlog row is added: on the first full sweep after a stable rustc newer
   than 1.99.1, diff each crate's `missed.txt` against V2's to measure whether rustc releases move
   survivors (Step 8 round 2 goal-fit assumption, accepted). The ADR index gains the 0042 row and
   marks 0024 partially superseded.

### What is deliberately not done

- No per-crate `--min-caught` on the per-PR gate (operator decision, premise 2).
- No confirmation re-run of per-PR timeouts with a longer timeout. It would close the
  slow-but-correct case at the cost of PR minutes and a new mechanism; V1 measures whether that
  case exists at all in today's timeout population.
- No automated draft PRs for Rust survivors: the ai-config `mutation-review.yml` cargo-mutants
  leg is retired rather than taught to read red runs (premise 5).
- No Renovate custom manager for the cargo-mutants pin; the bump procedure is in ADR-0042.

### Consequence to accept

Three things can turn a monthly sweep red with no math commit behind it, until each new survivor
gets a killing test (or, for a true equivalent, an `exclude_re` entry):

- a new stable rustc, which the sweep resolves at run time with no PR;
- a cargo-mutants bump that adds operators, if its PR skipped the full-sweep dispatch;
- a runner-shape change (vCPU count, image), which decided a survivor before (math#204: caught
  only where threads exceeded test bytes, surviving on CI's 2 vCPUs).

That is the ratchet working. The issue links the run, whose job logs carry the rustc version
(`rust-toolchain` step) and the runner image (`Image:`, `Version:`), which separate the first from
the third.

### Testing

- `tests/scripts/mutation_classify.bats` gains cases for the sweep's `0 1` arguments that the
  slice 5 cases do not already cover: caught 5, missed 1, exit 2 is red and stderr names the
  `missed.txt` line; caught 5, missed 0, timeout 2, exit 3 is green; caught 0, missed 0,
  timeout 3, exit 3 is red.
- `tests/test_mutation_workflows.py` changes the pinned `classifier_argc` from `["3"]` to `["5"]`,
  and asserts the fourth and fifth arguments are `0` and `1` (the classifier stub records its
  arguments).
- `tests/scripts/mutation_notify.bats` asserts the `verdicts-present` body lists a red unit with
  its status file's first `red` line and its detail lines inside an indented fence, a second red
  unit with its own line, and no line for a green unit; that a red file with 25 detail lines, one
  of them containing `Vec<u32>`, prints 20 inside the fence with `... 5 more lines in the run`;
  that a red file with no detail lines prints no fence; and that the missing-status body with
  RESULT `failure` names each red unit once.
- Every line of a fenced block, fences included, carries the two-space prefix: one unprefixed line ends the list item, strips `<T>` again and renders the next unit inside a code block (Step 8 round 3, render-verified). The tests assert the block as an exact multi-line substring, not line presence.
- Two existing `mutation_notify.bats` cases invert, and change as follows.
  "red units are listed with their first-line reason" (status `red: pi-3 -- ...\nsecond line`):
  `second line` is now asserted present, inside the fence under `- pi-3: red: pi-3 -- ...`.
  "a red line that is not the first line is still detected ..." (status
  `note: preamble\nred: pi -- late verdict\nred: second red`): `- pi: red: pi -- late verdict`
  stays, `red: second red` is now asserted present inside the fence, and `note: preamble` is
  asserted absent.
- `tests/test_mutation_workflows.py`'s single-line status assertions are unchanged (the status
  file format does not change).

## Requirements

- **R1.** The `Run mutants` step of `.github/workflows/mutation-testing.yml` calls `scripts/mutation-classify.sh` with five arguments, the fourth `0` and the fifth `1`.
- **R2.** `tests/test_mutation_workflows.py` asserts the sweep's classifier call has 5 arguments and that the fourth and fifth are `0` and `1`.
- **R3.** `tests/scripts/mutation_classify.bats` asserts, with arguments `0 1`: caught 5 missed 1 exit 2 is red and stderr contains the `missed.txt` line; caught 5 missed 0 timeout 2 exit 3 is green; caught 0 missed 0 timeout 3 exit 3 is red.
- **R4.** `scripts/mutation-notify.sh` renders red units in one function, called by both `build_body`'s `verdicts-present` case and `build_units_body`: `- <unit>: <line>` with `<line>` the file's first `red` line, then, when the file has lines after it, a fenced code block in which every line, both fences included, starts with two spaces, holding at most 20 of those lines and `... <K> more lines in the run` when K > 0; lines before the first `red` line are not printed. With no red unit, `build_body`'s list is `- (none flagged; see run log)` and `build_units_body`'s is `- (none)`, as today.
- **R5.** A body posted by `check_expected_units` with RESULT not `success` names each red unit exactly once.
- **R6.** `tests/scripts/mutation_notify.bats` asserts R4 for two red units with detail lines and a green unit, a red unit with no detail lines (no fence), the 25-line truncation to 20 plus `... 5 more lines in the run` with a `Vec<u32>` line inside the fence, each as an exact multi-line substring (list item, two-space fence, two-space-prefixed content lines, closing fence), both empty-list fallbacks, and R5; and its two existing cases are inverted as the Testing section states (`second line` and `red: second red` present, `note: preamble` absent).
- **R7.** `docs/adr/0042-*.md` records the sweep's 0-missed rule, the timeout-counts-as-caught rule with the 56-mutant classification table, the fix-to-close procedure and the cargo-mutants bump procedure, and `docs/adr/README.md` lists 0042 and marks 0024 partially superseded.
- **R8.** Root `CLAUDE.md`'s sweep red/green line states the component 1 rules and the file stays at or under 30,000 bytes.
- **R9.** `docs/superpowers/README.md` no longer contains the Backlog rows "Rust mutation sweep drift the per-PR gate cannot see" and "Per-PR Rust gate passes an all-timeout run", and contains a row for measuring survivor drift on the first sweep after a stable rustc newer than 1.99.1.
- **V1.** Re-run the 16 unmeasured timeout mutants of run 41952665142 (e-rs 12, prime-rs 2, pi-rs 2) on `claude` from a `git archive` copy, each selected by its full name (`src/<file>:LINE:COL: <description>`) regex-escaped and anchored, as `(ulimit -v 8388608; cargo mutants --no-shuffle --timeout 180 --re '^<escaped name>$')` in the crate directory (calling cargo-mutants directly bypasses the Makefile cap, so the `ulimit` is explicit). An unescaped name selects nothing: measured 2026-11-05 on a `git archive` copy of `0d28038` `e/e-rs` with cargo-mutants 27.1.0, `--list --re 'src/lib.rs:144:13: replace + with * in compute_e'` printed 0 lines and the escaped, anchored form printed 1. Before each run `cargo mutants --list --re '^<escaped name>$'` prints exactly 1 line, and after it `mutants.out/outcomes.json` reports `total_mutants` 1; otherwise the result is not recorded. For e-rs, first add `MALLOC_ARENA_MAX=2` under the same `ulimit` (the cap likely failed on glibc malloc-arena address space, not real use); if its baseline still fails, run without `ulimit` inside `systemd-run --user --scope -p MemoryMax=16G -p MemorySwapMax=0`, never fully uncapped, because an OOM kill on the shared host may take a peer session's process. Record each result, the host and which bound ran in ADR-0042. Any that comes back missed gets a killing test in this slice.
- **V2.** Before dispatch, `gh issue list --label mutation-failure --state open` is empty (a full dispatch from the branch has `FULL_SWEEP=true`, so green closes and red posts; accepted, operator 2026-11-05). Dispatch two full `mutation-testing.yml` sweeps on the same branch SHA. Each is green with 11 crate status lines, each caught ≥ 1 and missed 0. Diff each crate's sorted `missed.txt` and `caught.txt` between the two runs and against run 41952665142, and record `nproc`; a mutant missed in one run and not another stops the slice for an operator decision.
- **V3.** On a local copy, delete one assertion that kills a known mutant in one crate, run `make mutants`, and run the classifier with `0 1` on the result: red, naming the survivor.
- **V4.** In an ai-config change coordinated with that repo's session: the knowledge entry `math-testing-policy.md` § Mutation green/red describes the new sweep rule, and `.github/workflows/mutation-review.yml` no longer runs the math cargo-mutants leg.
- **N1.** The per-PR gate does not change: `scripts/mutation-pr-run.sh` and `.github/workflows/mutation-pr.yml` are not modified, and crates still pass only `0`.
- **N2.** No committed per-crate missed count or baseline file.
- **N3.** The Python sweep's verdict rules do not change: `mutation-testing-python.yml` and `scripts/mutation-python-cell.sh` are not modified.
- **N4.** `scripts/mutation-classify.sh` is not modified.

## Multi-Lens Review

Reviewed at commit: `397479c` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: Worth building; cheap and closes a real blind spot. F1 (load-bearing): the slice makes the only existing Rust survivor consumer structurally dead and the spec does not name it. ai-config `mutation-review.yml` (cron `0 12 2 * *`) runs `mutation_review.py --repo brujack/math --workflow mutation-testing.yml --tool cargo-mutants`, which selects the latest run with `conclusion == "success"` (`mutation_review.py:656`, verified). After this slice every sweep with a survivor is `failure`, so the consumer only ever reads missed=0 runs. It already never fired: the 2026-11-02 run fell back to a 31-day-old run, and no `mutation-review` PR exists. It also drafts `exclude_re` entries for survivors, which CLAUDE.md reserves for true equivalents. F2: component 2 duplicates `build_units_body` (`scripts/mutation-notify.sh:108-117`), which already emits `- <unit>: <first red line>`.
Assumption: V1 can measure e-rs's 12 timeouts; slice 5's method failed there (baseline under the 8 GiB cap on the 48-core host). If V1 runs uncapped, the spec must say so.
Disposition: Addressed (operator, 2026-11-05: "Retire the Rust leg") — premise 5 and V4 retire the ai-config cargo-mutants leg; F2 by the single helper (component 3, R4); assumption by V1 running e-rs with `MUTANTS_UNCAPPED=1`.

### Ergonomics

Finding: F1: the issue body omits which mutant survived, and the stated reason is wrong. Python status files never contain `  missed:` lines (Python survivors go to `mutation-report-python`), so printing every line of a red status file costs Python nothing and puts `src/lib.rs:LINE:COL: replace X with Y` in the issue. F2: duplicate loop; on the missing-status path with RESULT != success, `check_expected_units` concatenates `build_body` and `build_units_body`, so red reasons print twice. F3: "Renovate's schedule" is wrong: the sweep resolves `stable` rustc at run time (no PR behind a rustc change), and cargo-mutants `27.1.0` is hand-pinned with no Renovate custom manager. Record `rustc -V` and `cargo mutants --version` where the red is read, and state the cargo-mutants bump procedure (full sweep dispatched on the bump branch). F4: the fix-to-close loop is undocumented: the per-PR gate does not prove a kill on an unchanged line, a single-crate dispatch only comments, and only a full dispatch closes. F5: V1's method is the one that already failed for e-rs.
Assumption: a mutant's verdict on the CI runner is stable run to run. collatz-rs flipped caught=40/timeout=2 to caught=36/timeout=6 with unchanged code; math#204 was a survivor decided by vCPU count. Refute by dispatching the full sweep 2-3 times on one SHA and diffing the per-crate tuples.
Disposition: Addressed (operator, 2026-11-05: "All of (a)-(f)"; "Two runs + diff") — full status lines with a 20-line cap in the body (component 3, R4-R6), toolchain line (component 2, R7), Consequence rewritten, fix-to-close and bump procedures in ADR-0042 (component 4, R8), V1 e-rs uncapped, V2 two runs with missed/caught diffs.

### Risk

Finding: Sound, not over-engineered. Enumerated `0 1` against `classify_mutation_run`: newly red is missed>0 (intended) and missing `outcomes.json` with exit 0 (unreachable behind the exit-code guard); caught=0/timeout>0 stays red with message `caught=0 below min_caught=1`; nothing newly green. F1: caught/timeout flips are harmless (both green), but caught/missed flips have happened (math#204: survived on 2 vCPUs), so runner-shape drift is a third red trigger the Consequence section should name. Premise 2's "every mutant of `collatz_next` timed out" is true of run 41952665142 only; all-timeout is a host property. F2: V2 (empty `crate`, `FULL_SWEEP=true`) on a branch closes an open `mutation-failure` issue on green or posts on red, and re-uploads `mutants-output` that ai-config reads. F3: same duplicate/double-listing as above; no R4 case covers that path. Steady state: run 41948343321 had e-rs and pi-rs missed=1, fixed by math#204 (orchestrator verified: `821acb1..0d28038` is math#204 plus docs), so 0 missed rests on one run of current code.
Assumption: no mutant on today's code flips between missed and caught/timeout across ubuntu-latest runs. Refute by diffing each crate's `missed.txt`/`caught.txt` between the V2 run and 41952665142 and comparing `nproc`.
Disposition: Addressed (operator, 2026-11-05: "All of (a)-(f)"; "Two runs + diff"; V2 side effect "Accept, state it") — runner-shape drift in Consequence, premise 2 wording corrected, R5 single listing, V2 pre-check of open `mutation-failure` issues and the accepted side effect, V2 two-run diff.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.

### Round 2 (all three lenses, reviewed at `56985db`)

#### Goal-Fit

Finding: Worth building; component 3 and the cap are justified. F1: the toolchain line (component 2, R7) cannot do what the Consequence section claims. Separating a rustc change from a runner change needs the previous green run's rustc and the runner shape, and the line records neither. The image (`Image: ubuntu-26.04`, `Version: 20261101.186.1`) and `rustc 1.99.1` are already in every job log (90-day retention), and the cargo-mutants version is pinned in git. It also forces rewrites of the single-line status assertions in `tests/test_mutation_workflows.py` and adds a `bash -e` abort path. Fix: drop component 2 and R7; point the Consequence at the run log.
Assumption: reds with no math commit behind them stay rare, rather than each ~6-weekly stable rustc moving survivors. V2 holds the toolchain fixed, so it cannot test this; a full sweep on the V2 SHA after the next stable rustc, diffed against V2, can.
Disposition: Addressed (operator, 2026-11-05: "Drop it"; "Accept both") — component 2 and R7 removed, Consequence points at the run log; assumption accepted and carried as a Backlog row (component 4, R9) for the first sweep after rustc 1.99.1.

#### Ergonomics

Finding: F1 (verified by the orchestrator with `gh api -X POST /markdown`, mode `gfm`): raw `missed:` lines in a list lose generic arguments, so `replace sieve -> Vec<u32> with vec![]` renders as `replace sieve -> Vec with vec![]`. Return-value replacements are a main cargo-mutants mutation kind. Fix (render-verified by the lens): put detail lines in a fenced block indented two spaces under the list item; R4 and R6 pin the fence, and the 25-line case includes a `<T>` line. F2: the 20-line cap drops the toolchain line in the mass-survivor month it exists for. F3: R7 passes on `toolchain: ; ` because `run_crate_job` does not stub `rustc` or `cargo`. Red-month path is 6 steps with one ~15-minute wait; V2 costs ~150 runner-minutes (public repo, free) and ~30 minutes wall time; V1 under an hour.
Assumption: 0 missed is reproducible run to run on CI's 2-vCPU runners. Refute with V2's diffs, or now by dispatching on `0d28038` and diffing against 41952665142.
Disposition: Addressed (operator, 2026-11-05: "All of (a)-(d)"; "Drop it") — detail lines fenced and indented under the list item (component 2, R4, R6 with a `Vec<u32>` line); F2/F3 moot with the toolchain line dropped; assumption tested by V2.

#### Risk

Finding: F1: same as Ergonomics F2 (toolchain line truncated). F2: existing tests contradict R4 and the spec lists only additions: `tests/scripts/mutation_notify.bats:706` (`run ! grep -qF -- "second line"`) and `:777` (`note: preamble` / `red: pi -- late verdict` / `red: second red`, asserting `second red` absent) invert, and R4 leaves open whether "other lines" include lines before the first `red` line. F3: same as Ergonomics F3, plus the failure path of `$(cargo mutants --version)` under `bash -e` is unspecified. F4: V1 running e-rs uncapped on `claude` (48 threads, 157 GiB available, peer sessions co-resident) can reach the OOM killer, which picks by RSS and may kill a peer session. The cap likely failed on VSZ from glibc malloc arenas (8 × 48 × 64 MiB; inference, not measured). Remedies: `MALLOC_ARENA_MAX=2` under the existing `ulimit -v 8388608`, or `systemd-run --user --scope -p MemoryMax=16G -p MemorySwapMax=0` (caps RSS; user cgroup has `memory` delegated). V1 should give the exact command, since `cargo mutants -F` bypasses the Makefile cap. F5 (minor): nothing caps total body bytes; an oversize body fails `gh` loudly.
Assumption: missed vs caught/timeout is deterministic run to run on ubuntu-latest. Precedent against: e-rs `.cargo/mutants.toml` already excludes `src/lib.rs:112:49` because one run caught it and run 41948343321 missed it; math#204 was vCPU-decided. Refute by diffing every retained run's `missed.txt` against `caught.txt`/`timeout.txt` on source-identical SHAs.
Disposition: Addressed (operator, 2026-11-05: "Drop it"; "All of (a)-(d)"; "Arena cap, then cgroup"; "Accept both") — F1/F3 moot; F2 by the Testing section listing both inverted cases and R4 excluding the preamble; F4 by V1's exact commands, `MALLOC_ARENA_MAX=2` under the cap, then a 16G `systemd-run` scope, never fully uncapped; F5 accepted (fails loud); assumption tested by V2.

### Round 3 (scoped Risk re-review of the round 2 rewrite, reviewed at `6e8ace1`)

Finding: F1 (load-bearing): V1's `--re '<exact name>'` reads the name as an unanchored regex, and the timeout names contain `+`, `*`, `+=` and `[1]`, so each selects zero mutants; V1 would pass vacuously, the e-rs baseline would never run, and ADR-0042 would record unmeasured rows. Orchestrator measured on a `git archive` copy of `0d28038` `e/e-rs` (cargo-mutants 27.1.0): raw name 0 lines, `^src/lib\.rs:144:13: replace \+ with \* in compute_e$` 1 line. F2: a fence indented two spaces renders correctly only if every content line also carries the prefix; one unprefixed line ends the list item, strips `<T>`, and swallows the next unit into a code block (render-verified); R6 as written passes both shapes. Minor: the helper's empty-list fallbacks (`- (none flagged; see run log)`, pinned at `mutation_notify.bats:99`, and `- (none)`, unpinned) are not stated. Checked clean: no fence breakout (0 backticks in crate sources; status lines come only from the classifier and fixed `printf`s), no bats inversions beyond the two named, `ulimit` subshell scope, env inheritance under `systemd-run --scope`.
Assumption: cargo-mutants 27.1.0 matches `--re` against the full name including the location prefix. Settled by the orchestrator's `--list` probe above: it does.
Disposition: Addressed (operator, 2026-11-05: "Apply all three") — V1 escapes and anchors each name with a 1-line `--list` pre-check and `total_mutants` 1 post-check; R4 requires the two-space prefix on every block line and keeps both fallbacks; R6 asserts exact multi-line substrings and both fallbacks. Review stops here: the remaining findings sat in the verification apparatus, and the design shrank across rounds.
