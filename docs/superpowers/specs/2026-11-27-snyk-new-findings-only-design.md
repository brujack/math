# snyk-scan blocks auto-merge when a PR touches a flagged flow

- **Date:** 2026-11-27
- **Backlog row:** none; raised in session after math#255, when every PR's `snyk-scan` was red
- **Related:** ADR-0016 (advisory scans), ADR-0037 (pinned downloads), ADR-0048 (operator-only merges for gate items), `tests/test_snyk_cli_pinned.py`
- **Revision:** 3
  - Round 1 reviewed revision 1 at `f8ded91`: a two-scan identity diff against `HEAD^1`, still advisory.
  - Round 2 reviewed revision 2 at `381f3ae`: a committed baseline keyed on identity plus fingerprint `"1"`.
  - Both judges were refuted on measured data. See Rejected alternatives.

## Problem

`snyk-scan` in `.github/workflows/auto-merge.yml` runs `snyk code test` over the whole tree.
It is advisory:
- it sets `continue-on-error: true`;
- it is not in the `auto-merge` job's `needs: [secret-scan, bash-coverage, claude-md-budget]`;
- `scripts/ci-gate.sh` lists it in `ADVISORY_CHECKS`.

Nothing reads it, and that is the failure. It was red on math#150, #158 and #162, and those reds
went unread. It was green on #170 through #249. On math#250 it went red listing exactly the
4 new `scripts/zeta_results.py` findings, and the `auto-merge` job merged that PR at
18:33:59Z, two minutes after the second red run. The 3 MEDIUM Command Injection findings then
landed under a check that was already red, and it has been red on every PR since. The repo has
`allow_auto_merge: false`, and 54 of the last 60 merges were made by the `auto-merge` job, so
that job is the one consumer that matters.

The scan reports 17 findings on master `d3ef01e`, each read at source in this session:

| Findings | File | Rule | Why it is not a live defect |
| --- | --- | --- | --- |
| 3 MEDIUM | `scripts/mutation_gate_items.py` (420, 584, 588) | Command Injection | argv lists, binary resolved by `shutil.which` |
| 8 LOW | `scripts/mutation_weakening.py` (236, 246, 271, 297, 298, 351, 357, 515) | Path Traversal | paths are the operator's own CLI arguments |
| 4 LOW | `scripts/zeta_results.py` (957, 961, 1010, 1013) | Path Traversal | `rmtree` guarded by `_check_targets` / `_check_owned` and the MARKER file |
| 2 | `tests/test_mutation_weakening_e2e.py:127`, `tests/test_mutation_weakening.py:159` | various | test code |

### What was measured

All probes ran in CI on throwaway draft PRs, which were closed and their branches deleted.

- **math#259, sanitisers.** A `..` rejection, `os.path.realpath`, and a basename check
  cleared no finding. A `.snyk` with `exclude: code: [tests/**]` took the count from 17 to 15.
- **math#260, line shift.** With 4 lines inserted near the top of each affected file,
  `identity` matched 17 of 17 and fingerprint `"1"` matched 17 of 17.
- **math#261, edits**, against the master scan. 17 results became 18.
  - **(b)** The shared sink `run_tool` (line 173) was changed from an argv list to
    `" ".join(args), shell=True`. Both results through it kept their `identity`. `236272`'s `"1"`
    changed. `f306d8`'s flow gained a step and its `priorityScore` rose from 368 to 373, but its
    `"1"` stayed byte-equal.
  - **(a)** A near-copy of `_init_session` added no result. This ran in the same push as (b), so
    the two are confounded. `00ab70` (584) vanished.
  - **(c)** One statement was added and one local renamed inside `zeta_results._recover`. `f5e20d`,
    whose flow and sink lie inside the edit, kept its `"1"`.
  - **(d)** A new file with `subprocess.run(sys.argv[1], shell=True)` was reported. Listing it in
    `.gitignore` did not hide it. Listing it in `.dcignore` did: `.py` files analysed went from
    118 to 120 for 3 added.
- **Coverage.** SARIF `runs[0].properties.coverage` reports `.py` files analysed. On master that
  was 118, equal to `git ls-tree -r --name-only d3ef01e | grep -c '\.py$'`. `.rs` showed 68 files
  `NOT_SUPPORTED`. Snyk Code scans no Rust.

Population: one repo, Snyk CLI 1.1308.0, 17 findings, and about 2 hours on one day.

### What the measurements rule out

- `identity` and fingerprint `"1"` are both opaque and server-assigned. `"1"` has a fixed 16
  segments for flows of 8 to 56 steps, so it is a lossy sketch. Matching on either missed a real
  injection in math#261 (b).
- Anything keyed on Snyk's fingerprints also breaks all at once if Snyk's server-side engine
  re-fingerprints. The CLI pin does not cover that.

### What the measurements support

The SARIF carries each result's location and one codeFlow, a list of file and line steps from
source to sink. Those are plain coordinates in the head tree, and they can be compared with the
PR's own diff.

## Design

### The judge: flow-touch

A result is **touched** when its primary location, or any step of its codeFlows, lies on a line
this PR added or changed.
- The PR's lines are the new-side lines of every hunk in `git diff -U0 HEAD^1 HEAD`, on the
  `refs/pull/<n>/merge` checkout.
- A pure-deletion hunk `+s,0` marks lines `s` and `s+1`.
- A new file is touched on every line.

Untouched results never turn the job red, however many exist. That is how the 15 existing
findings stay green with no baseline. No fingerprint is read.

Replaying math#261 offline (the probe diff against `sarif3`):
- **Touched (6):**
  - `236272` and `f306d8`, through the degraded sink. Fingerprint `"1"` missed `f306d8`.
  - `0bd274` and `f5e20d`, in the edited `_recover`. Fingerprint `"1"` missed `f5e20d`.
  - both new probe files.
- **Untouched (12):**
  - the 8 `mutation_weakening.py` results;
  - both `tests/` results;
  - zeta 1011 and 1014, whose flows do not include the edited lines.

### The coverage check

Snyk silently skips any file hidden by `.snyk`, by `.dcignore` at any depth, by a size limit or
by a server-side flag. Any of those routes would let a PR's new file escape the judge. The check
that covers all of them is a count. The `.py` entry in `properties.coverage` must equal the
number of `git ls-files '*.py' ':!:tests/**'`, which is the tracked Python outside the `.snyk`
exclusion. Any difference is red, with both numbers printed.

### Guarded paths

- A diff touching `.snyk` or `scripts/snyk_flow_touch.py` is red, with
  `snyk-scan: <path> changed; the operator reviews and merges this PR`.
- `auto-merge.yml` itself is already a gate item: it declares `secret-scan`, so
  `mutation-gate-items` holds any edit to it.

### `scripts/snyk_flow_touch.py`

- It reads the SARIF on **stdin**, and runs only two fixed-argv commands: `git diff -U0 --no-color HEAD^1 HEAD` and
  `git ls-files '*.py' ':!:tests/**'`. It writes only to stdout and
  stderr. With no path argument, no environment-derived path and no file write, it avoids the
  patterns Snyk flags in this repo (math#163: a Python write to `$GITHUB_STEP_SUMMARY` was
  flagged as Path Traversal).
- Output:
  - **Header:** `snyk: <t> touched, <u> untouched; coverage .py <a> analysed, <b> tracked`.
  - **Per touched result, in SARIF order:**
    - `touched: <level> <ruleId> <uri>:<startLine> — <message.text>`;
    - `  on PR lines: <uri>:<line>[, …]`, at most 5;
    - `::error file=<uri>,line=<startLine>::snyk: this PR touches a flagged flow (<ruleId>) — <message.text>`.
  - **A guarded-path or coverage failure:** its own line, starting `snyk-scan:`.
  - **Missing fields** print as `?`.
- Exit codes: 0 when nothing is touched, the coverage matches, and no guarded path changed; 1 when
  any of those fails. Exit 2, with `snyk_flow_touch: <reason>` on stderr, when:
  - stdin is not JSON;
  - it has no non-empty `runs`;
  - a run lacks a `results` array;
  - no `.py` coverage entry exists;
  - the git command fails.

### The job

`snyk-scan` loses `continue-on-error` and joins the `auto-merge` job's `needs`. `Gate and
merge` is the only automatic merge path, so a red `snyk-scan` means no automatic merge.
`scripts/ci-gate.sh` is unchanged; its `ADVISORY_CHECKS` entry becomes moot.

Steps:

1. **Checkout:** `actions/checkout` at the pinned sha, with `fetch-depth: 2`.
   - The checkout is `refs/pull/<n>/merge`. `HEAD^1` is master at event time and `HEAD^2` is the PR
     head (math#260 log: `HEAD is now at c0a1083 Merge c854680… into d3ef01e…`).
2. **Install Snyk CLI:** unchanged.
3. **Run Snyk Code scan** (`id: scan`): `SNYK_TOKEN` on this step only, under `set +e`.
   - It runs `snyk code test --sarif-file-output="${RUNNER_TEMP}/snyk.sarif" > "${RUNNER_TEMP}/snyk.txt"`.
   - On an exit status above 1 it prints `::error::snyk-scan: scanner error (exit <rc>)` and
     `snyk.txt`, then exits 1.
   - Otherwise it exits 0, because exit 1 only means findings exist.
4. **Judge:** no token, `if: ${{ !cancelled() && steps.scan.outcome == 'success' }}`.
   - It runs `python3 scripts/snyk_flow_touch.py < "${RUNNER_TEMP}/snyk.sarif" > "${RUNNER_TEMP}/judge.txt"`
     and keeps the status.
   - It prints `judge.txt`.
   - It appends `judge.txt`, minus `::error` lines, to `$GITHUB_STEP_SUMMARY`.
   - It exits with the saved status.

### When `snyk-scan` is red

- **Touched finding:** judge it at source. If it is real, fix it. If it is a false positive, write
  the judgment in the PR body, run `gh pr ready --undo <n>` and `gh pr edit <n> --add-label gate-hold`,
  and leave the merge to the operator's admin merge, as with an items-gate PR (ADR-0048). The
  next PR that touches the same flow is judged again; nothing is remembered.
- **Coverage mismatch:** find the file Snyk skipped. A `.dcignore` or `.snyk` edit is reverted. A
  size limit or Snyk-side cause goes to the operator.
- **Guarded path:** operator admin merge.
- **Scanner error:** re-run; if Snyk is down, the operator admin-merges.

The implementing PR adds `scripts/snyk_flow_touch.py` and `.snyk`, so it is red by design, and
the operator's admin merge is its review.

### Docs

- **ADR-0049** records the decision, the evidence from math#250 and #259 to #261, the two refuted
  judges, the red procedure and the residual limits.
- **`CLAUDE.md`:**
  - The `snyk-scan` line says the job is a `needs` of `auto-merge`. It reds on a finding whose
    flow the PR touches, on a `.py` coverage mismatch, or on a guarded-path change. It names
    `scripts/snyk_flow_touch.py` and ADR-0049, and it drops the claim that Rust is scanned.
  - The `auto-merge.yml` line and the ci-gate line stop calling `snyk-scan` advisory.
  - The file stays at or under 30000 bytes. It is 29993 on `d3ef01e`.

## Known limits

- **One representative flow.** Snyk reports one codeFlow per result. An edit on a path only a
  second caller takes is invisible if Snyk shows the other caller's flow (V3).
- **Flow merging.** A new flow reaching an existing sink may add no result. A PR can then add a
  caller whose own lines are not on the displayed flow (math#261 (a), confounded).
- **No memory.** A false positive on a hot flow is re-judged on every PR that touches it, each
  time by the operator. Two of the last 40 master commits added code with findings, and 0 of 2
  later edits to the flagged files touched a flagged flow.
- **Snyk outage, quota or fork PR:** red, closed. The operator admin-merges. Quota stays at one
  scan per run, as today; the monthly limit is unverified (V4).
- **`.snyk`'s exclusion is mirrored by the coverage formula.** Changing one without the other is
  red, which is intended.
- **The PR runs its own judge.** Edits to it are a guarded path. Edits to the workflow are held by
  the items gate.

## Rejected alternatives

- **Identity diff against `HEAD^1` (revision 1).** It forgets a finding once it merges, and
  identity was kept on a degraded sink in math#261 (b).
- **Baseline keyed on identity plus `"1"` (revision 2).** `"1"` stayed byte-equal on `f306d8` and
  `f5e20d`, both on degraded or edited flows. Both fingerprints also tie every PR to Snyk's
  server-side fingerprinting.
- **Code-level sanitisers.** None cleared a finding in math#259.
- **Snyk organisation ignores.** They are manual web-UI steps outside the repo, invisible in
  review, and need an auth an agent cannot complete.
- **`--severity-threshold=high`.** It stays green on a new MEDIUM Command Injection.
- **Removing `snyk-scan`.** ai-config `ci-021` requires it.
- **Branch protection instead of `needs`.** It would also block the operator's admin merges during
  a Snyk outage.
- **A count ratchet** (red when results exceed N). It misses a degradation at an existing
  finding and fix-one-add-one swaps.

## Requirements

- **R1.** `[PR1]` A root `.snyk` contains exactly the lines `version: v1.25.0`, `exclude:`, `  code:` and `    - tests/**`, optionally preceded by `#` comment lines.
- **R2.** `[PR1]` In `.github/workflows/auto-merge.yml`, `snyk-scan` has no `continue-on-error`, the `auto-merge` job's `needs` contains `snyk-scan`, the `Install Snyk CLI` step is unchanged, and `snyk-scan`'s `actions/checkout` sets `fetch-depth: 2`; `tests/test_workflow_continue_on_error.py` no longer allow-lists `snyk-scan`.
- **R3.** `[PR1]` The scan step has `id: scan` and is the only step with `SNYK_TOKEN`. Under `set +e` it runs `snyk code test --sarif-file-output="${RUNNER_TEMP}/snyk.sarif"` with stdout redirected to `${RUNNER_TEMP}/snyk.txt`. On an exit status above 1 it prints `::error::snyk-scan: scanner error (exit <status>)` and the contents of `snyk.txt`, then exits 1. Otherwise it exits 0.
- **R4.** `[PR1]` A judge step without `SNYK_TOKEN`, with `if: ${{ !cancelled() && steps.scan.outcome == 'success' }}`, runs `python3 scripts/snyk_flow_touch.py < "${RUNNER_TEMP}/snyk.sarif"` with stdout saved to a file. It prints that file and appends it, minus lines starting `::error`, to `$GITHUB_STEP_SUMMARY`. It exits with the script's status.
- **R5.** `[PR1]` `scripts/snyk_flow_touch.py` takes no arguments, reads the SARIF from stdin, runs no command other than `git diff -U0 --no-color HEAD^1 HEAD` and `git ls-files '*.py' ':!:tests/**'`, and opens no file for writing.
- **R6.** `[PR1]` The script marks a result touched when its primary location or any codeFlow step location has a `uri` and `startLine` among the PR lines. PR lines are the new-side lines of each hunk; a hunk with new count 0 at start `s` contributes `s` and `s+1`; every line of an added file counts.
- **R7.** `[PR1]` The script fails the coverage check when the run's `properties.coverage` `.py` `files` value differs from the number of paths printed by `git ls-files '*.py' ':!:tests/**'`. It fails the guarded-path check when the diff's `+++ b/` or `--- a/` paths include `.snyk` or `scripts/snyk_flow_touch.py`.
- **R8.** `[PR1]` The script prints `snyk: <t> touched, <u> untouched; coverage .py <a> analysed, <b> tracked`. For each touched result in SARIF order it prints `touched: <level> <ruleId> <uri>:<startLine> — <message.text>`, `  on PR lines: <uri>:<line>` (at most 5, comma-separated) and `::error file=<uri>,line=<startLine>::snyk: this PR touches a flagged flow (<ruleId>) — <message.text>`. A coverage failure prints `snyk-scan: Snyk analysed <a> .py files but <b> are tracked outside tests/; a file is hidden from the scan`. A guarded-path failure prints `snyk-scan: <path> changed; the operator reviews and merges this PR`. Missing fields print `?`. It exits 0 when no result is touched, the coverage matches and no guarded path changed, and 1 otherwise.
- **R9.** `[PR1]` The script exits 2 and prints `snyk_flow_touch: <reason>` to stderr when stdin is not valid JSON, has no non-empty `runs` list, has a run without a `results` array, has no `.py` coverage entry, or when either git command exits non-zero.
- **R10.** `[PR1]` `tests/test_snyk_flow_touch.py` covers, with git calls stubbed, these cases: no result touched; a touched primary location; a touched codeFlow step only; a pure-deletion hunk touching `s` and `s+1`; an added file; a result in a second run; the coverage mismatch in both directions; each guarded path; and each R9 exit-2 case. It also replays the committed fixtures `tests/fixtures/snyk/sarif-261.json` and `tests/fixtures/snyk/diff-261.txt` (from math#261) and asserts that exactly the results located at `scripts/mutation_gate_items.py:173` and `:589`, `scripts/zeta_results.py:958` and `:962`, `scripts/probe_new.py:6` and `scripts/probe_gitignore.py:6` are touched.
- **R11.** `[PR1]` A workflow test pins R2 to R4: the `needs` entry and the absent `continue-on-error`; `fetch-depth: 2`; `SNYK_TOKEN` on exactly one step; `set +e`, the scan command, the stdout redirect and the exit-above-1 branch; and the judge step's `if:`, stdin redirect and summary filter.
- **R12.** `[PR1]` `docs/adr/0049-*.md` records the decision, the evidence from math#250 and #259 to #261, both refuted judges, the red procedure and the Known limits, with a row in `docs/adr/README.md`.
- **R13.** `[PR1]` `CLAUDE.md`'s `snyk-scan` line says the job is a `needs` of `auto-merge`, fails when the PR touches a flagged flow, on a `.py` coverage mismatch or on a guarded-path change, and names `scripts/snyk_flow_touch.py` and ADR-0049. No CLAUDE.md line calls `snyk-scan` advisory or says it scans Rust. `CLAUDE.md` stays at or under 30000 bytes.
- **R14.** `[PR1]` A P3 Backlog row records removing `snyk-scan` from `ADVISORY_CHECKS` in `scripts/ci-gate.sh` and its `tests/scripts/ci_gate.bats` cases.
- **V1.** On the implementing PR, the judge prints the header and `snyk-scan: scripts/snyk_flow_touch.py changed …` and `.snyk changed …`. The coverage figures are equal (`a = b`), which confirms the formula under the new `.snyk`. Any `touched:` lines name only the new script. The operator admin-merges.
- **V2.** After merge, open a throwaway draft PR that degrades `run_tool` as in math#261 (b), adds `scripts/probe_new.py`, and adds `scripts/.dcignore` naming `scripts/probe_new.py`. `snyk-scan` fails. The log shows `touched:` for both `run_tool` results, and a coverage mismatch. The `auto-merge` job is skipped. Close the PR.
- **V3.** On the same throwaway PR, as a second push, revert (b). Then add a second caller of an existing flagged sink whose lines appear on no displayed flow. Record whether any result is touched. This measures the one-representative-flow limit, and the result goes into ADR-0049.
- **V4.** The operator reads the Snyk organisation's Code test usage and limit and records them in ADR-0049.
- **V5.** On a later Python-free PR, the judge prints `snyk: 0 touched, <u> untouched; coverage .py <a> analysed, <a> tracked` with `u` at least 15 and the `auto-merge` job runs.
- **N1.** No change to `scripts/ci-gate.sh`, `tests/scripts/ci_gate.bats` or `.github/required-status-checks`.
- **N2.** No code change to the 15 existing findings' source files to placate Snyk.
- **N3.** No Snyk organisation ignores and no `snyk ignore` calls.
- **N4.** No third-party Python dependency for `scripts/snyk_flow_touch.py`, and no `actions/setup-python` step in `snyk-scan`.
- **N5.** No second Snyk scan per run, and no use of SARIF `fingerprints`.

## Multi-Lens Review

### Round 1

Reviewed at commit: `f8ded91` (revision 1, Step 7 self-review commit, before Step 8 dispatch)

#### Goal-Fit

Finding: the job's output has no consumer, and the repo's history shows that missing consumer is the real failure. `snyk-scan` was green on every run until math#250, where it went red listing exactly the 4 new `zeta_results.py` findings. That is the output this spec aims for. Auto-merge merged math#250 at 18:33:59Z, two minutes after the second red (`gh pr checks 250`: `snyk-scan fail`; merged by `app/github-actions`; verified by the author). `scripts/ci-gate.sh` lists `snyk-scan` in `ADVISORY_CHECKS`, `auto-merge` does not need it, and no ai-config skill reads it. Reads-it test: it changes no decision, and its output survives only in the run log. The `HEAD^1` base also erases the signal itself: once a finding merges, every later PR calls it known, and nothing records that it was let through. Simpler path: commit an identity baseline file. That means one scan, no worktree and no `.snyk` swap, and adding to the baseline shows in the PR diff. Pair the baseline with a consumer: ci-gate blocking on `n>0`, or the `gate-hold` label. Empty measurement: a head SARIF of `{"runs":[{"results":[]}]}` yields `0 known, 0 new` and exit 0.
Assumption: Snyk accepts about 2x the current Snyk Code test volume (168 auto-merge runs in 30 days) without a cap turning scans into exit 2. This is settled by the Snyk org's usage page.
Disposition: Addressed. The operator chose "Baseline + ci-gate blocks (Recommended)"; revision 2 commits `.snyk-baseline` and makes `snyk-scan` a `needs` of the `auto-merge` job.

#### Ergonomics

Finding: a red result is hard to act on. Both scans print every finding in human format, about 34 blocks above the one-line verdict. The `new:` line uses SARIF terms (`note`, `python/PT`), while the log says `[LOW] Path Traversal`. It also drops `message.text`, the source-to-sink sentence a reader needs to judge the finding. And no action is stated for a red result: sanitisers do not work (math#259), and org ignores are excluded (N3). Fix: add `message.text`, emit a `::warning file=,line=::` annotation per new finding, send scan stdout to a file, and write the disposition procedure ("judge, record in the PR body, merge") into the ADR and knowledge entry. Red should be rare: 2 of the last 40 master commits added subprocess or file-I/O code under `scripts/`.
Assumption: `identity` survives an edit inside the function that holds a known finding (a statement added between source and sink, or a local variable renamed), not only a line shift. If false, the busiest files re-flag their known findings as new. This is settled by a throwaway-PR probe.
Disposition:

#### Risk

Finding: a SARIF run without a `results` array reads as zero findings and passes green. R8 misses this. The SARIF spec says absent `results` means the tool produced none, while `[]` means it found nothing. Fix: exit 2 on a run lacking a `results` array, optionally also on no `properties.coverage` entry with `isSupported: true` and `files > 0`, and add an R9 case. Second: the step runs under `bash -e`, and the head scan always exits 1. So the obvious `snyk ...; rc=$?` aborts before `rc` is read (probed: `bash -e -c 'false; rc=$?; echo reached'` printed nothing), and R10's text pin would pass that broken code. Fix: R4 should require `set +e`, as `claude-md-budget` already does. Also not raised: `SNYK_TOKEN` should be scoped to the two `snyk` calls rather than the PR-controlled script.
Assumption: a base scan from `${RUNNER_TEMP}/base` (another path, a git worktree) yields the same `identity` values for unchanged findings as a head scan from `$GITHUB_WORKSPACE`. The identities are UUIDv4, which suggests server-side assignment possibly keyed on project or path. math#260 measured two runs at the same path only. If false, every known finding is new, and the job is red on every PR again. This is settled by scanning one tree at both paths in one job.
Disposition:

#### Adversarial Spec Review (comparison/judge designs only)

Trigger: the design is a judge (known vs new).

- F1: all 17 identities are UUIDv4, not content hashes. Their equivalence relation is Snyk's and opaque, and refactor-tolerant tracking is a false-negative source for a diff gate. Known limits covers identity drift (errs red) but not identity over-matching (errs green).
- F2: degradation at a known site is invisible. Turning `mutation_gate_items.py:420` into `subprocess.run(" ".join(cmd), shell=True)` likely keeps `identity`, so the finding stays known. A `level` or `ruleId` change at a matched identity is ignored too.
- F3: replacing a known flow with a different flow in the same function may inherit its identity. This is unmeasured.
- F4: set semantics. Two head results sharing one identity both count as known. A `Counter` subtraction is free and fails closed.
- F5: the policy swap covers only `.snyk`. Snyk Code also honours `.gitignore` and `.dcignore` (unverified here), so a PR could hide its new file that way.
- Recall: R9 uses synthetic SARIF, and V2 is the easiest case (a new file), so false-negative rate is unmeasured. Cheapest added V: on one throwaway PR, (a) copy the function holding a known finding (expect 1 new) and (b) degrade the known site in place (expect at least 1 new).
- Tangential: SARIF coverage shows `.rs` `NOT_SUPPORTED` (68 files), so CLAUDE.md's "against the Python and Rust source" is wrong.

Assumption: equal `identity` means the same vulnerability, not a similar one nearby. Probes (a) and (b) above confirm or refute it.
Disposition: Addressed. Measured in math#261; probe (b) confirmed F2 (identity kept at a degraded sink) and probe (d) confirmed F5 for `.dcignore`. The operator chose "1": key on identity plus fingerprint `"1"`; revision 2 also reds on `.snyk`/`.dcignore` changes and uses claim-once matching (F4).

### Round 2

Reviewed at commit: `381f3ae` (revision 2). Fresh lenses; round 1 framed as history.

#### Goal-Fit

Finding: revision 2 gives the signal a consumer. `allow_auto_merge` is `false` and 54 of the last 60 merges ran through the `auto-merge` job, so a red `needs` blocks every automatic merge. But R8 makes the judge write `GITHUB_STEP_SUMMARY` from Python, and R7 opens two CLI paths. math#163 (`2fd5efa`) found Snyk flags the first pattern as Path Traversal and ignores inline suppressions, and master flags the second 8 times. So the judge will report 1 to 3 findings on itself, and V1's "15 accepted" is wrong. Fix: print to stdout only, have the shell append to the summary, and use repo-anchored constant paths. A premise error too: `snyk-scan` was not green until math#250. It was red on #150, #158 and #162, and green on #170 through #249. That is earlier red that nobody read, which strengthens the case.
Assumption: Snyk's server-side engine keeps `identity` and `"1"` stable for unchanged code over weeks. All evidence spans about 2 hours on one day. Settled by re-scanning `d3ef01e` a week or more later.
Disposition:

#### Ergonomics

Finding: engine drift turns every open PR red at once, including Renovate, docs-only and workflow-only PRs. The output names files the PR never touched, and agents follow "copy the `baseline:` line" into operator-only merges. A re-run does not help, because it reuses the old merge ref, so every PR needs a new event. Fix: mark each line "in this PR's diff" or "not in this PR's diff", say "likely engine drift" when none are, and add drift to Known limits.
Secondary findings:
- Copying a `changed:` line's `baseline:` text duplicates the identity, which is R9 exit 2. The output should say "replace".
- The judge accepts a reasonless or `?` reason.
- No `gate-hold` instruction tells the operator a PR is waiting.

Estimated cost: about 2 operator merges a month from new code, and 0 of 2 historical edits touched a flagged flow.
Assumption: the same engine-drift stability as goal-fit.
Disposition:

#### Risk

Finding:
- **Fail-open: the policy pathspec is root-only.** `scripts/.dcignore` does not match `-- .snyk .dcignore` (probed). Whether a nested `.dcignore` hides a file is unmeasured.
- **Fail-open: the judge script is unguarded.** The workflow edit is caught by the items gate (`auto-merge.yml` declares `secret-scan`), but `scripts/snyk_baseline.py` is not, so an agent can weaken it and merge green.
- **Engine drift is an undocumented block on every merge**, and the `changed` class cannot tell drift from degradation.
- **V4 passes on no measurement**, because a skipped compare step is green.
- **Minor:** `if: always()` spends quota on cancelled runs (use `!cancelled()`), and R2 and R9 disagree on whether a reason is required.
Assumption: the same engine-drift stability.
Disposition:

#### Adversarial Spec Review (comparison/judge designs only)

Findings:
- **F1 (load-bearing, verified by the author): `"1"` is a lossy sketch, not a flow hash.** It is a fixed 16 segments for flows of 8 to 56 steps, segment values recur, and small edits flip a subset of segments.
  - On math#261 data, `f306d8` passes through the degraded `shell=True` sink. Its flow gained a step (`154, 174, 174, 173`) and `priorityScore` rose from 368 to 373, but `"1"` stayed byte-equal, so it is judged accepted.
  - `f5e20d`, whose flow and sink sit inside the edited `_recover`, also kept `"1"`.
  - The spec's claim that (b) changed `"1"` holds only for `236272`.
- **F2:** the policy check is root-only. The fix: red when SARIF coverage `.py` files differ from `git ls-files '*.py' ':!tests/**'`, which held exactly on master (118). That one check covers nested `.dcignore`, `.snyk`, size limits and flag drift.
- **F3:** probe (a) did not show "one result per sink". It was confounded with (b). Master has 3 results on sink 173. Deleting a stale line is self-service green even when the PR changed that flow.
- **F4:** the judge and workflow paths are unguarded.
- **Minor:** `"0"` matched 2 of 17 in math#260, not 4. `level` and `ruleId` should be compared on a match.
- **Recall:** V2 replays only known-good cases. A fixture replay of sarif1 against sarif3 catches F1 offline. Fix: a **flow-touch** rule. A result is red when its location or any codeFlow step lies in a new-side hunk of `git diff -U0 HEAD^1 HEAD`.

Assumption: Snyk's single reported codeFlow per result includes the lines a degrading edit touches. Settled by a probe that degrades a line only a non-representative caller passes through.
Disposition: Addressed. F1 was verified by the author (`f306d8` and `f5e20d` kept `"1"`). The operator chose "Flow-touch, no fingerprints (Recommended)": revision 3 drops the baseline and every fingerprint, judges by whether the PR's diff touches a result's location or flow, and adds the coverage count (F2) and guarded judge path (F4).
