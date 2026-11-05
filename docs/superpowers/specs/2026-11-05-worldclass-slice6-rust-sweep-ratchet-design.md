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
   component 4 counts timeouts as evaluated in limit mode on purpose: every mutant of
   `collatz_next` (`collatz-rs` `src/lib.rs:9`) and of the `read_line_from` prompt-retry loops
   timed out in sweep run 41952665142, so a crate floor of `min_caught 1` would make a PR that
   touches only such a line red with nothing to fix. Slice 5 measured the assumption behind it
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
   Context); this design adds none (N2).
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
2. **Issue body carries each red unit's verdict.** In `build_body`'s `verdicts-present` case,
   each red unit is listed as `- <unit>: <line>`, where `<line>` is the first line of its status file that starts with `red`, instead of `- <unit>`.
   That line is the classifier's `red: ... - <reason>` line, so the issue says whether a
   crate is red for `missed=N exceeds max_missed=0`, `caught=0 below min_caught=1`, or an exit
   code. The `missed:` detail lines stay in the run's step summary and in the
   `mutants-output-<slug>` artifact (`missed.txt`); the body links the run. The change is in the
   shared script, so the Python workflow's issue body gains the same reason line.
3. **ADR-0042: the Rust sweep holds 0 missed; a timeout counts as caught.** Records component 1,
   supersedes the survivors half of ADR-0024's "Exit codes 2 and 3 are green" consequence, states
   the timeout rule for both the per-PR gate and the sweep, and carries the timeout
   classification table: slice 5's 40 measured plus the 16 measured under V1.
4. **Documentation.** Root `CLAUDE.md`'s "A sweep leg is red only when ..." line is rewritten in
   place to the component 1 rules, at no more than its current 400 bytes. The two Backlog rows
   are removed. The ADR index gains the 0042 row and marks 0024 partially superseded.

### What is deliberately not done

- No per-crate `--min-caught` on the per-PR gate (operator decision, premise 2).
- No confirmation re-run of per-PR timeouts with a longer timeout. It would close the
  slow-but-correct case at the cost of PR minutes and a new mechanism; V1 measures whether that
  case exists at all in today's timeout population.
- No `missed:` lines in the issue body. They are in the linked run, and the issue body is shared
  with the Python workflow.

### Consequence to accept

A rustc or cargo-mutants update that adds mutation operators turns the next monthly sweep red
until each new survivor gets a killing test or an `exclude_re` entry. That is the ratchet working;
it puts the work on Renovate's schedule rather than on a PR's.

### Testing

- `tests/scripts/mutation_classify.bats` gains cases for the sweep's `0 1` arguments that the
  slice 5 cases do not already cover: caught 5, missed 1, exit 2 is red and stderr names the
  `missed.txt` line; caught 5, missed 0, timeout 2, exit 3 is green; caught 0, missed 0,
  timeout 3, exit 3 is red.
- `tests/test_mutation_workflows.py` changes the pinned `classifier_argc` from `["3"]` to `["5"]`,
  and asserts the fourth and fifth arguments are `0` and `1` (the classifier stub records its
  arguments).
- `tests/scripts/mutation_notify.bats` asserts the `verdicts-present` body lists a red unit with
  its status file's first `red` line, a second red unit with its own line, and no line for a green
  unit.

## Requirements

- **R1.** The `Run mutants` step of `.github/workflows/mutation-testing.yml` calls `scripts/mutation-classify.sh` with five arguments, the fourth `0` and the fifth `1`.
- **R2.** `tests/test_mutation_workflows.py` asserts the sweep's classifier call has 5 arguments and that the fourth and fifth are `0` and `1`.
- **R3.** `tests/scripts/mutation_classify.bats` asserts, with arguments `0 1`: caught 5 missed 1 exit 2 is red and stderr contains the `missed.txt` line; caught 5 missed 0 timeout 2 exit 3 is green; caught 0 missed 0 timeout 3 exit 3 is red.
- **R4.** `scripts/mutation-notify.sh`'s `verdicts-present` body lists each red unit as `- <unit>: <line>`, where `<line>` is the first line of its status file that starts with `red`, and `tests/scripts/mutation_notify.bats` asserts it for two red units and a green one.
- **R5.** `docs/adr/0042-*.md` records the sweep's 0-missed rule and the timeout-counts-as-caught rule with the 56-mutant classification table, and `docs/adr/README.md` lists 0042 and marks 0024 partially superseded.
- **R6.** Root `CLAUDE.md`'s sweep red/green line states the component 1 rules and the file stays at or under 30,000 bytes.
- **R7.** `docs/superpowers/README.md` no longer contains the Backlog rows "Rust mutation sweep drift the per-PR gate cannot see" and "Per-PR Rust gate passes an all-timeout run".
- **V1.** Re-run the 16 unmeasured timeout mutants of run 41952665142 (e-rs 12, prime-rs 2, pi-rs 2) by exact name with `--timeout 180`, by slice 5's method; record each result and the host in ADR-0042. Any that comes back missed gets a killing test in this slice.
- **V2.** Dispatch a full `mutation-testing.yml` sweep on the branch before merge: green, 11 crate status lines, each with caught ≥ 1 and missed 0.
- **V3.** On a local copy, delete one assertion that kills a known mutant in one crate, run `make mutants`, and run the classifier with `0 1` on the result: red, naming the survivor.
- **V4.** The ai-config knowledge entry `math-testing-policy.md` § Mutation green/red describes the new sweep rule, in an ai-config change coordinated with that repo's session.
- **N1.** The per-PR gate does not change: `scripts/mutation-pr-run.sh` and `.github/workflows/mutation-pr.yml` are not modified, and crates still pass only `0`.
- **N2.** No committed per-crate missed count or baseline file.
- **N3.** The Python sweep's verdict rules do not change: `mutation-testing-python.yml` and `scripts/mutation-python-cell.sh` are not modified.
- **N4.** `scripts/mutation-classify.sh` is not modified.

## Multi-Lens Review

Reviewed at commit: `397479c` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: Worth building; cheap and closes a real blind spot. F1 (load-bearing): the slice makes the only existing Rust survivor consumer structurally dead and the spec does not name it. ai-config `mutation-review.yml` (cron `0 12 2 * *`) runs `mutation_review.py --repo brujack/math --workflow mutation-testing.yml --tool cargo-mutants`, which selects the latest run with `conclusion == "success"` (`mutation_review.py:656`, verified). After this slice every sweep with a survivor is `failure`, so the consumer only ever reads missed=0 runs. It already never fired: the 2026-11-02 run fell back to a 31-day-old run, and no `mutation-review` PR exists. It also drafts `exclude_re` entries for survivors, which CLAUDE.md reserves for true equivalents. F2: component 2 duplicates `build_units_body` (`scripts/mutation-notify.sh:108-117`), which already emits `- <unit>: <first red line>`.
Assumption: V1 can measure e-rs's 12 timeouts; slice 5's method failed there (baseline under the 8 GiB cap on the 48-core host). If V1 runs uncapped, the spec must say so.
Disposition:

### Ergonomics

Finding: F1: the issue body omits which mutant survived, and the stated reason is wrong. Python status files never contain `  missed:` lines (Python survivors go to `mutation-report-python`), so printing every line of a red status file costs Python nothing and puts `src/lib.rs:LINE:COL: replace X with Y` in the issue. F2: duplicate loop; on the missing-status path with RESULT != success, `check_expected_units` concatenates `build_body` and `build_units_body`, so red reasons print twice. F3: "Renovate's schedule" is wrong: the sweep resolves `stable` rustc at run time (no PR behind a rustc change), and cargo-mutants `27.1.0` is hand-pinned with no Renovate custom manager. Record `rustc -V` and `cargo mutants --version` where the red is read, and state the cargo-mutants bump procedure (full sweep dispatched on the bump branch). F4: the fix-to-close loop is undocumented: the per-PR gate does not prove a kill on an unchanged line, a single-crate dispatch only comments, and only a full dispatch closes. F5: V1's method is the one that already failed for e-rs.
Assumption: a mutant's verdict on the CI runner is stable run to run. collatz-rs flipped caught=40/timeout=2 to caught=36/timeout=6 with unchanged code; math#204 was a survivor decided by vCPU count. Refute by dispatching the full sweep 2-3 times on one SHA and diffing the per-crate tuples.
Disposition:

### Risk

Finding: Sound, not over-engineered. Enumerated `0 1` against `classify_mutation_run`: newly red is missed>0 (intended) and missing `outcomes.json` with exit 0 (unreachable behind the exit-code guard); caught=0/timeout>0 stays red with message `caught=0 below min_caught=1`; nothing newly green. F1: caught/timeout flips are harmless (both green), but caught/missed flips have happened (math#204: survived on 2 vCPUs), so runner-shape drift is a third red trigger the Consequence section should name. Premise 2's "every mutant of `collatz_next` timed out" is true of run 41952665142 only; all-timeout is a host property. F2: V2 (empty `crate`, `FULL_SWEEP=true`) on a branch closes an open `mutation-failure` issue on green or posts on red, and re-uploads `mutants-output` that ai-config reads. F3: same duplicate/double-listing as above; no R4 case covers that path. Steady state: run 41948343321 had e-rs and pi-rs missed=1, fixed by math#204 (orchestrator verified: `821acb1..0d28038` is math#204 plus docs), so 0 missed rests on one run of current code.
Assumption: no mutant on today's code flips between missed and caught/timeout across ubuntu-latest runs. Refute by diffing each crate's `missed.txt`/`caught.txt` between the V2 run and 41952665142 and comparing `nproc`.
Disposition:

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
