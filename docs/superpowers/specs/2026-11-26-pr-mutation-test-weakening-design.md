# PR mutation gates see test weakening

- **Date:** 2026-11-26
- **Backlog row closed:** "PR mutation gates miss test-only weakening (Rust and Python)" (P2)
- **Related:** ADR-0042 (Rust sweep holds zero missed), ADR-0044 (per-PR Python gate), ADR-0046
  (shard the Rust runs), `specs/2026-11-05-worldclass-slice5-rust-pr-mutation-ratchet-design.md`,
  `specs/2026-11-07-worldclass-slice8-python-pr-mutation-gate-design.md` ("Known gap, not closed here")

## Summary

Both per-PR mutation gates judge only mutants on lines a PR changes. A PR that deletes or weakens
tests changes no production line, so it is never judged, and the surviving mutants it creates sit
on unchanged lines. This spec closes that gap:

- **Rust:** any change under a crate's `src/` or `tests/` runs every mutant in that crate, held to
  the sweep's rule (0 missed, timeouts green). It replaces the changed-line run for those crates.
- **Python:** a change to `test_<module>.py` mutates the whole head module and runs the head tests
  on every mutant, then runs the base tests on each head survivor. A mutant the base tests kill and
  the head tests do not is a weakening, and the gate is red.

## Why

Measured 2026-11-26 on master `0bc607f`:

- `scripts/mutation-pr-detect.sh` puts a Python dir in `py_src_dirs` only when
  `git diff --numstat` shows added lines in `<dir>/<module>.py`. A PR touching only
  `test_<module>.py` runs no Python mutant.
- A Rust crate is selected only when a changed path matches `<crate>/src/**/*.rs`, and its mutants
  are filtered by `--in-diff`. A hunk inside a `#[test]` yields `INFO No mutants to filter`, exit 0
  (orchestrator probe recorded in the slice 5 spec, 2026-11-05). A change under `<crate>/tests/`
  (13 crates have one) selects no crate.
- The 90% coverage floors (`--cov-fail-under=90` in the Python template, `tarpaulin --fail-under 90`
  in every `*-rs.yml`) catch a large test deletion but not a weakened assertion: coverage is unchanged
  when `assertEqual(x, 5)` becomes `assertIsNotNone(x)`.
- The Rust monthly sweep holds 0 missed (ADR-0042), so a Rust weakening is reported within a month,
  after merge. The Python sweep carries about 1,250 open survivors (issue #184), so a new Python
  survivor is indistinguishable from the backlog and is never reported at all.

Agents write most of the tests here, and weakening a test to make a gate pass is a known agent failure
(it is on the executor FORBIDDEN list). Nothing mechanical catches it before merge today.

## Facts this design rests on (measured 2026-11-26)

- **Rust whole-crate cost.** The monthly sweep `mutation-testing.yml` run 45479226540 (2026-11-24, all
  13 crates, 2,221 mutants, 37 shards at B = 75) took 9 minutes of wall time; its longest shard was
  7.4 min (descartes-rs, ADR-0046 V1). zeta-rs is the outlier: 748 whole-crate mutants at about 29.6 s
  each on CI, so a full 75-mutant shard runs about 37 min and the 10-shard crate about the same wall
  time (ADR-0046 V2 measured a 68-mutant zeta shard at 33.8 min).
- **Planner.** `scripts/mutation-rs-plan.sh --whole <crate-dir>...` already plans every mutant of the
  named crates and emits a fault unit `{"slug":"<name>-plan",...,"fault":"<cause>"}` instead of failing
  the plan.
- **Python per-mutant replay.** `cosmic-ray mutate-and-test MODULE_PATH OPERATOR OCCURRENCE TEST_COMMAND`
  (cosmic-ray 8.7.0, the pinned version) mutates one occurrence and runs the given command. Probed on a
  `git archive` copy of `sq/`: `core/NumberReplacer` occurrence 0 reported `"test_outcome": "killed"`
  with `python3 -m unittest -q test_sq` and `"survived"` with `python3 -c pass`, and `sq.py` was
  byte-identical to `HEAD:sq/sq.py` afterwards. A cosmic-ray session's dump names each job's operator
  and occurrence, so a head survivor can be replayed under another test command.
- **Python test layout.** Each of the 10 Python sub-projects has exactly one test file,
  `<dir>/test_<module>.py`, and no `conftest.py`.
- **Python whole-module cost.** The Python sweep (`mutation-testing-python.yml`, 10 shards per
  project) takes about 20 minutes of wall time; pi and e hold 613 mutants each (slice 8 spec).

## Design

### Rust: whole crate on any crate change

1. `mutation-pr-detect.sh` selects a crate dir for `rs_dirs` when any changed path is under
   `<crate>/src/` or `<crate>/tests/` (any file type; a fixture change can weaken a test).
2. `mutation-rs-plan` plans the selected crates with `mutation-rs-plan.sh --whole`, not the
   `--in-diff` mode. A fault unit is a red unit in `mutation-pr`.
3. Each shard runs as today and is classified with the sweep's rule: red on any missed mutant, on
   `caught + missed + timeout == 0`, on a missing `outcomes.json` or `mutants.out/exit-code`, or on a
   failed baseline; timeouts are green beside a catch (`scripts/mutation-classify.sh`, ADR-0042).
4. The amicable-rs canary is unchanged.
5. Consequence, accepted by the operator: drift from a newer rustc or cargo-mutants surfaces on the
   next PR that touches the crate, not only in the monthly sweep.

### Python: same code, two test suites

Triggered for a dir when `test_<module>.py` changes (any added, removed or renamed line), in addition
to the existing module-change trigger. The question is whether the head tests kill less of the same
code than the base tests did, so both suites run against the **head** module:

1. **Head run.** Mutate the whole head module and run the head tests on every mutant, sharded as the
   sweep shards it. The existing changed-line rule still applies on top: any survivor on a changed line
   of `<module>.py` is red.
2. **Base suite.** Write `git show <merge-base>:<dir>/test_<module>.py` to `<dir>/test_<module>_base.py`
   in the job's checkout. If the base has no such file, the comparison is skipped and says so.
3. **Obsolete base tests.** Run the base suite once against the unmutated head module. Every base test
   that fails or errors there is excluded from step 4 and listed by id; a behaviour change made it
   obsolete, so it does not block.
4. **Replay.** For each head survivor, run `cosmic-ray mutate-and-test` with the base suite restricted
   to the tests that passed in step 3. Only head survivors can be weakenings, so this pass is small.
5. **Verdict.** A mutant with base outcome `killed` and head outcome `survived` is a weakening: the dir
   is red and the summary lists each such mutant's operator, occurrence and diff. Timeouts count as
   killed on both sides, as the per-PR gate counts them today.
6. If `test_<module>.py` is missing at head while present at base, the dir is red with
   `test_<module>.py deleted`.

### Local repro

- Rust: `scripts/mutation-pr-run.sh --whole <crate>` runs every mutant of one crate with the PR rule.
- Python: `make -C <dir> mutants-weakening BASE=<ref>` runs steps 1-5 for one dir and prints the same
  verdict lines as CI.

## Requirements

- **R1.** `scripts/mutation-pr-detect.sh` prints a crate dir in `rs_dirs` when a changed path starts with `<crate>/src/` or `<crate>/tests/`, whatever the file extension, so a change only to a non-`.rs` file under `<crate>/tests/` selects the crate.
- **R2.** In `mutation-pr.yml`, `mutation-rs-plan` plans every selected crate with `scripts/mutation-rs-plan.sh --whole <crate-dir>...` and never passes `--in-diff` for a selected crate.
- **R3.** A `--whole` fault unit (`"fault": "<cause>"`) makes `mutation-pr` red and its summary names the crate and the cause.
- **R4.** A Rust PR shard is red on any missed mutant, on `caught + missed + timeout == 0`, on a missing `mutants.out/outcomes.json` or `mutants.out/exit-code`, or on a failed baseline, and green on timeouts beside at least one caught mutant, using `scripts/mutation-classify.sh`.
- **R5.** `mutation-pr-detect.sh` prints a Python dir in a new output `py_test_dirs=<sorted dirs>` when `git diff --numstat --no-renames` shows any added or deleted line in `<dir>/test_<module>.py` (module = dir with `-` as `_`), including a deletion of the file.
- **R6.** For each dir in `py_test_dirs`, the gate mutates the whole head `<dir>/<module>.py` and runs the head `test_<module>.py` on every mutant, sharded with `n = min(10, max(1, ceil(K/150)))`.
- **R7.** For each dir in `py_test_dirs`, the gate writes the merge base's `<dir>/test_<module>.py` to `<dir>/test_<module>_base.py`, runs it once against the unmutated head module, and excludes every base test that fails or errors there, listing the excluded test ids in the summary under `obsolete base tests:`.
- **R8.** For each head survivor of a dir in `py_test_dirs`, the gate runs `cosmic-ray mutate-and-test <module>.py <operator> <occurrence> "<base test command>"` with the base suite restricted to the tests not excluded by R7.
- **R9.** A dir in `py_test_dirs` is red when any mutant's base outcome is `killed` and head outcome is `survived`, and its summary line reads `weakened: <count> mutants killed by base tests survive head tests`, followed by each mutant's operator, occurrence and diff.
- **R10.** A dir in `py_test_dirs` whose `test_<module>.py` exists at the merge base and not at head is red with `test_<module>.py deleted`.
- **R11.** A dir in `py_test_dirs` whose merge base has no `test_<module>.py` skips R7-R9 and its summary says `no base test file: weakening check skipped`.
- **R12.** A timeout counts as `killed` on both the head and the base side of the R9 comparison.
- **R13.** A dir in `py_test_dirs` keeps the existing rule that any head survivor on a line the PR added to `<module>.py` is red.
- **R14.** `scripts/mutation-pr-run.sh --whole <crate-dir>` runs every mutant of one crate locally and exits non-zero on the R4 red conditions.
- **R15.** Every Python `Makefile` (rendered from `scripts/crate_templates/python/Makefile`) gains a `mutants-weakening` target that takes `BASE=<ref>`, runs R6-R12 for that dir and prints the same verdict lines as the CI summary.
- **R16.** `tests/scripts/mutation_pr_detect.bats` covers R1 (a `tests/` fixture change and a non-`.rs` `src/` file each select the crate) and R5 (an added-only, a deleted-only and a file-deletion change to `test_<module>.py` each select the dir; a change to `<module>.py` alone does not put it in `py_test_dirs`).
- **R17.** A test drives the Python weakening comparison on a copy of `sq/` where the head `test_sq.py` drops one assertion that kills a known mutant, and requires that exact mutant reported under `weakened: 1`; a second case where head only adds a test reports `weakened: 0`; a third where a base test fails on the unmutated head lists it under `obsolete base tests:` and does not count it.
- **R18.** Root `CLAUDE.md` (Mutation testing sections) and ADR-0046 or a new ADR describe the whole-crate PR rule and the Python weakening check with their repro commands, `docs/superpowers/README.md` removes the Backlog row "PR mutation gates miss test-only weakening (Rust and Python)", and root `CLAUDE.md` stays at or under 30,000 bytes.

- **V1.** Positive control before the PR is marked ready: a throwaway draft PR built on the branch that deletes one assertion from a crate's `#[cfg(test)]` module, where the deletion leaves a mutant uncaught, shows `mutation-pr` red naming that mutant; the PR is closed and its branch deleted.
- **V2.** Positive control: a throwaway draft PR that weakens one assertion in `sq/test_sq.py` shows `mutation-pr` red with `weakened: 1` naming the mutant; closed and deleted afterwards.
- **V3.** Negative control: a throwaway draft PR that only adds a test to `sq/test_sq.py` shows `mutation-pr` green.
- **V4.** Record the wall time of the PR's own `mutation-pr` run and of V1-V3; a zeta-rs whole-crate PR run is measured or projected from shard times, and any shard past about 50 minutes lowers B per ADR-0046.

- **N1.** The monthly `mutation-testing.yml` and `mutation-testing-python.yml` sweeps do not change.
- **N2.** No committed survivor, missed or baseline list is added for any crate or Python dir.
- **N3.** The local pre-push hook runs no mutants.
- **N4.** The required check stays `mutation-pr`; no new required check is added to branch protection.
- **N5.** The base test file is written only inside the CI job's or the local run's checkout and is never committed; nothing writes to a tracked file in the working tree a developer is using.
- **N6.** The Python changed-line gate's existing behaviour for dirs not in `py_test_dirs` does not change.
