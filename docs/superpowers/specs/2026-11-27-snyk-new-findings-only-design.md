# snyk-scan blocks auto-merge on findings outside a reviewed baseline

- **Date:** 2026-11-27
- **Backlog row:** none; raised in session after math#255, when every PR's `snyk-scan` was red
- **Related:** ADR-0016 (advisory scans), ADR-0037 (pinned downloads), ADR-0048 (operator-only merges for gate items), `tests/test_snyk_cli_pinned.py`
- **Revision:** 2 (round 1 reviewed revision 1 at `f8ded91`: a two-scan diff against `HEAD^1` that stayed advisory)

## Problem

`snyk-scan` in `.github/workflows/auto-merge.yml` runs `snyk code test` over the whole tree.
It is advisory: `continue-on-error: true`, not in the `auto-merge` job's
`needs: [secret-scan, bash-coverage, claude-md-budget]`, and listed in
`ADVISORY_CHECKS` in `scripts/ci-gate.sh`. Nothing reads it.

That is the failure, not the noise. `snyk-scan` was green on every run until math#250. There it
went red listing exactly the 4 new `scripts/zeta_results.py` findings, and the `auto-merge` job
merged math#250 at 18:33:59Z, two minutes after the second red run. The 3 MEDIUM Command
Injection findings then landed under a check that was already red. It has been red on every PR
since. The most recent six runs, on 2026-11-28 UTC, all concluded `failure` in 30 to 56 seconds.

The scan reports 17 findings on master `d3ef01e`, each read at source in this session:

| Findings | File | Rule | Why it is not a live defect |
| --- | --- | --- | --- |
| 3 MEDIUM | `scripts/mutation_gate_items.py` (420, 584, 588) | Command Injection | argv lists, binary resolved by `shutil.which` |
| 8 LOW | `scripts/mutation_weakening.py` (236, 246, 271, 297, 298, 351, 357, 515) | Path Traversal | paths are the operator's own CLI arguments |
| 4 LOW | `scripts/zeta_results.py` (957, 961, 1010, 1013) | Path Traversal | `rmtree` guarded by `_check_targets` / `_check_owned` and the MARKER file |
| 2 | `tests/test_mutation_weakening_e2e.py:127`, `tests/test_mutation_weakening.py:159` | various | test code |

### What was measured

All three probes ran in CI on throwaway draft PRs, which were closed and their branches
deleted. Each SARIF result carries `ruleId`, `level`, a location, `message.text`, `codeFlows`,
and `fingerprints` with keys `identity`, `"0"`, `"1"` and `snyk/asset/finding/v1`, the last
equal to `identity`. All 17 identities are UUIDv4 values, not content hashes, so what they
treat as "the same finding" can only be measured.

- **math#259, sanitisers.** A `..` rejection, `os.path.realpath`, then a basename check
  cleared no finding. A `.snyk` of `version: v1.25.0` / `exclude:` / `  code:` /
  `    - tests/**` took the count from 17 to 15, removing both test findings.
- **math#260, line shift.** The same tree, scanned again with 4 lines inserted near the
  top of each affected file, moved 15 of the 17 findings. `identity` matched 17 of 17;
  `"1"` matched 17 of 17; `"0"` matched 4 of 17.
- **math#261, edits.** One push scanned against the master scan above. 17 results became 18.

  | Change | Result |
  | --- | --- |
  | (b) shared sink `run_tool` (line 173) changed from an argv list to `" ".join(args), shell=True` | The finding moved from line 420 to the sink at line 173 and kept the same `identity`, `ruleId` and `level`. `"1"` changed. |
  | (a) near-copy of `_init_session` (the 420 flow) under a new name | No new result. Snyk reported one result per sink, and the 584 identity vanished (3 results became 2). |
  | (c) one statement added and one local renamed inside `zeta_results._recover` | `identity` was kept for all 4 zeta findings. `"1"` changed on 3 of them, whose flows pass through `_recover`. |
  | (d) new file with `subprocess.run(sys.argv[1], shell=True)` | New identity. |
  | (d) the same file listed in `.gitignore` | New identity. `.gitignore` does not hide a file. |
  | (d) the same file listed in `.dcignore` | Absent. `.dcignore` hides a file. `.py` files analysed went from 118 to 120 for 3 files added. |

  Population: one repo, Snyk CLI 1.1308.0, 17 findings, one engine version.

Three conclusions follow:

- **`identity` alone is fail-open at exactly the sites that matter.** Probe (b) turned a
  false positive into a real injection and kept the identity.
- **`"1"` tracks the data flow.** It caught (b), and it changes on ordinary edits along a
  flagged flow (c).
- **The PR controls two files that can hide a finding:** `.snyk` and `.dcignore`.

Per-finding ignores exist only in the Snyk organisation, and `snyk auth` cannot complete from
a remote session (its OAuth callback targets `127.0.0.1:8080`), so every measurement here ran
in CI.

## Design

### The baseline

A tracked file, `.snyk-baseline`, lists the findings the operator has accepted, one per line:

```text
# <identity> <fingerprint "1"> <ruleId> <uri> — <why it is accepted>
236272c5-16ff-472c-b639-0123456789ab d5c0229d.639387d0.… python/PT scripts/zeta_results.py — rmtree guarded by _check_owned and MARKER
```

The comparison uses the first two fields. `ruleId` and `uri` are there so a reviewer can read
the file. Blank lines and `#` lines are ignored. Each line holds exactly four whitespace-separated
fields before an optional ` — ` reason. Any other line, or a repeated identity, makes the file
malformed.

### The judge

`scripts/snyk_baseline.py BASELINE SARIF` classifies every result in every run of the SARIF:

- **accepted:** its `identity` is in the baseline, and its `"1"` equals that line's.
- **new:** its `identity` is missing from the baseline, or the result has no `identity`. When two
  results share one identity, only the first can be accepted and the second is new.
- **changed:** its `identity` is in the baseline, but its `"1"` differs or is missing. This is the
  math#261 (b) case.
- **stale:** a baseline identity matches no result.

Output:

- A header line: `snyk: <a> accepted, <n> new, <c> changed, <s> stale`.
- For each new or changed result, in SARIF order:
  - `<new|changed>: <level> <ruleId> <uri>:<startLine> — <message.text>`
  - followed by the line to add to the baseline, `  baseline: <identity> <"1"> <ruleId> <uri> — <reason>`
  - and a GitHub annotation, `::error file=<uri>,line=<startLine>::snyk <new|changed>: <ruleId> — <message.text>`.
- For each stale entry: `stale: <identity> <ruleId> <uri> — delete this baseline line`.

A missing field prints `?`. When `GITHUB_STEP_SUMMARY` is set, the same text, minus the
annotations, is appended to that file.

Exit codes: 0 when `n + c + s` is 0, and 1 otherwise. Exit 2, with
`snyk_baseline: <path>: <reason>` on stderr, in any of these cases:
- either file is missing or unreadable;
- the SARIF is not JSON, has no non-empty `runs` list, or has a run without a `results` array;
- no `properties.coverage` entry with `isSupported: true` has `files` above 0;
- the baseline is malformed.

Stale counts as red, so the baseline can only shrink to what the scan still reports. An
allow-list that outlives its findings is a loose allow-path.

### The job

`snyk-scan` stays a separate job, loses `continue-on-error`, and becomes a `needs` of the
`auto-merge` job. The `Gate and merge` step there runs only after every `needs` job has
succeeded, so a red `snyk-scan` means no merge. `scripts/ci-gate.sh` is not changed.
Its `ADVISORY_CHECKS` entry for `snyk-scan` becomes moot, because `auto-merge` never starts
while `snyk-scan` is red.

Steps:

1. **Checkout:** `actions/checkout` at the pinned sha, with `fetch-depth: 2`. `pull_request`
   checks out `refs/pull/<n>/merge`. Its first parent `HEAD^1` is master at event time, and
   its second parent is the PR head (seen in the math#260 log:
   `HEAD is now at c0a1083 Merge c854680… into d3ef01e…`).
2. **Install Snyk CLI:** unchanged.
3. **Check policy files:** no token. The step fails with
   `::error::snyk-scan: <path> changed; the operator reviews and merges this PR` when either of
   these holds:
   - `git diff --name-only HEAD^1 HEAD -- .snyk .dcignore` lists a path;
   - `git diff HEAD^1 HEAD -- .snyk-baseline` contains an added line, one starting with `+` but
     not `+++`.

   Removing baseline lines is allowed, because it only tightens.
4. **Run Snyk Code scan:** `SNYK_TOKEN` is set on this step only. Under `set +e`, it runs
   `snyk code test --sarif-file-output="${RUNNER_TEMP}/snyk.sarif" > "${RUNNER_TEMP}/snyk.txt"`
   and keeps the exit status in `rc`. When `rc` is above 1, it prints
   `::error::snyk-scan: scanner error (exit <rc>)`, prints `snyk.txt`, and exits 1. The step
   then always exits 0, because exit 1 only means findings exist.
5. **Compare with baseline:** no token. It runs
   `python3 scripts/snyk_baseline.py .snyk-baseline "${RUNNER_TEMP}/snyk.sarif"` and exits with
   that command's status.

Step 3 runs before the scan and does not stop it. Step 4 runs `if: always()`, so a policy
failure still shows the findings, and step 5 runs `if: always() && steps.scan.outcome == 'success'`.

The bootstrap PR adds `.snyk`, so step 3 fails on it. The operator's admin merge accepts the
initial baseline. That is the review point.

The 15 initial lines come from the math#260 run-1 SARIF: the master tree minus the two
`tests/` findings, with every reason taken from the table under Problem. The PR's first CI run
checks them, because a wrong identity or fingerprint prints as new or changed with the
corrected `baseline:` line.

### Accepting a finding

When `snyk-scan` is red on a new or changed finding:

1. Judge it at source.
2. If it is real, fix the code.
3. If it is a false positive, copy the printed `baseline:` line into `.snyk-baseline` with a
   reason, and say so in the PR body.

Step 3 then turns the job red as a baseline addition. Only the operator merges that, by admin
override, as for an items-gate PR (ADR-0048). Agents never edit `.snyk`, `.dcignore` or
`.snyk-baseline` to clear their own red without saying so in the PR body. A stale entry is fixed
by deleting its line, which stays green.

### Docs

- **ADR-0049** records the decision and the math#250, #259, #260 and #261 evidence, the
  procedure for accepting a finding, and the rejected alternatives.
- **`CLAUDE.md`:**
  - The `snyk-scan` line is rewritten. It says the job is a `needs` of `auto-merge`, reds on any
    finding outside `.snyk-baseline` by identity and fingerprint `"1"`, and reds on a change to
    the policy files. It names `scripts/snyk_baseline.py` and ADR-0049. The claim that Rust is
    scanned is dropped: the SARIF shows `.rs` as `NOT_SUPPORTED`, 68 files.
  - The `auto-merge.yml` line stops calling snyk-scan advisory.
  - The ci-gate line drops "`snyk-scan` is advisory;".
  - The file stays at or under 30000 bytes; it is 29993 on `d3ef01e`.

## Known limits

- **Snyk merges flows per sink.** Probe (a) showed a second copy of a vulnerable flow
  reaching an accepted sink adds no result. The judge cannot see what Snyk does not
  report.
- **`"1"` changes on edits along a flagged flow.** Every such edit turns `snyk-scan` red and
  needs an operator merge. Two of the last 40 master commits added subprocess or file-I/O code
  under `scripts/`, and the flagged files are under active work. The rate is unmeasured.
- **Snyk outage or quota blocks auto-merge.** A scanner exit above 1 is red and fails closed.
  The operator admin-merges in that case. Test quota stays at one scan per run, as today. The
  monthly Code test limit is unverified (V3).
- **Fork PRs.** They get no `SNYK_TOKEN`, so the scan exits 2 and the job is red, as today.
- **`scripts/ci-gate.sh` still lists `snyk-scan` in `ADVISORY_CHECKS`.** That is harmless under
  `needs`; removing it is a Backlog row.
- **The PR runs its own copy of `scripts/snyk_baseline.py`.** A PR can weaken the judge, as it
  can weaken any `pull_request` workflow. The script has no token in its environment. The
  defence is review, not mechanism. This is the same posture as every other job in this
  workflow.

## Rejected alternatives

- **Two scans, diffing against `HEAD^1` (revision 1).** It forgets a finding the moment it
  merges, doubles the scans, and its identity-only match missed probe (b).
- **Code-level sanitisers.** Measured in math#259: none cleared a finding.
- **Snyk organisation ignores.** They are manual web-UI steps outside the repo, invisible in
  review, and an agent session cannot authenticate to create one.
- **`--severity-threshold=high`.** It would stay green on a new MEDIUM Command Injection.
- **Removing `snyk-scan`.** ai-config `ci-021` requires it for supported languages.
- **Adding `snyk-scan` to branch protection.** It would block the operator's own admin
  merges on a Snyk outage. `needs` blocks only the automatic merge.
- **Matching on `identity` only.** It misses probe (b).
- **Matching on `"1"` only.** It would make every flow edit look like a new finding with no
  link to the accepted one, so a reviewer cannot tell "moved" from "new".

## Requirements

- **R1.** `[PR1]` A root `.snyk` contains exactly the lines `version: v1.25.0`, `exclude:`, `  code:` and `    - tests/**`, optionally preceded by `#` comment lines.
- **R2.** `[PR1]` A root `.snyk-baseline` holds one line per Snyk Code finding on the implementing PR's head (15 expected). Each line has the form `<identity> <fingerprint "1"> <ruleId> <uri> — <reason>`, with a non-empty reason. The file may also hold `#` comment lines and blank lines.
- **R3.** `[PR1]` In `.github/workflows/auto-merge.yml`, `snyk-scan` has no `continue-on-error`, the `auto-merge` job's `needs` contains `snyk-scan`, the `Install Snyk CLI` step is unchanged, and `snyk-scan`'s `actions/checkout` sets `fetch-depth: 2`. `tests/test_workflow_continue_on_error.py` no longer allow-lists `snyk-scan`.
- **R4.** `[PR1]` A `snyk-scan` step without `SNYK_TOKEN` fails with `::error::snyk-scan: <path> changed; the operator reviews and merges this PR` when `git diff --name-only HEAD^1 HEAD -- .snyk .dcignore` is non-empty, or when `git diff HEAD^1 HEAD -- .snyk-baseline` has a line starting with `+` but not `+++`.
- **R5.** `[PR1]` The scan step, the only step with `SNYK_TOKEN`, runs `if: always()` under `set +e`. It runs `snyk code test --sarif-file-output="${RUNNER_TEMP}/snyk.sarif"` with stdout redirected to `${RUNNER_TEMP}/snyk.txt`. On an exit status above 1 it prints `::error::snyk-scan: scanner error (exit <status>)` and the contents of `snyk.txt`, then exits 1. Otherwise it exits 0.
- **R6.** `[PR1]` A final step without `SNYK_TOKEN`, guarded by `if: always() && steps.<scan id>.outcome == 'success'`, runs `python3 scripts/snyk_baseline.py .snyk-baseline "${RUNNER_TEMP}/snyk.sarif"` and exits with its status.
- **R7.** `[PR1]` `scripts/snyk_baseline.py BASELINE SARIF` classifies each SARIF result, across all runs, as follows: accepted when its `fingerprints.identity` is a baseline identity not already claimed by an earlier result and its `fingerprints["1"]` equals that line's; new when its identity is absent, missing, or already claimed; changed when the identity matches but `"1"` differs or is missing. A baseline identity that matches no result is stale.
- **R8.** `[PR1]` The script prints `snyk: <a> accepted, <n> new, <c> changed, <s> stale`. Then, per new or changed result in SARIF order, it prints: `<new|changed>: <level> <ruleId> <uri>:<startLine> — <message.text>`; `  baseline: <identity> <"1"> <ruleId> <uri> — <reason>`; `::error file=<uri>,line=<startLine>::snyk <new|changed>: <ruleId> — <message.text>`. Then, per stale entry, it prints `stale: <identity> <ruleId> <uri> — delete this baseline line`. It uses `?` for any missing field. When `GITHUB_STEP_SUMMARY` is set, it appends the same text without the `::error` lines to that file. It exits 0 when `n + c + s` is 0 and 1 otherwise.
- **R9.** `[PR1]` The script exits 2 and prints `snyk_baseline: <path>: <reason>` to stderr in any of these cases: either file is missing or unreadable; the SARIF is not valid JSON, lacks a non-empty `runs` list, or has a run without a `results` array; no run's `properties.coverage` has an entry with `isSupported: true` and `files` above 0; a non-comment, non-blank baseline line does not have four fields before an optional ` — ` reason; the baseline repeats an identity.
- **R10.** `[PR1]` `tests/test_snyk_baseline.py` covers each classification: all accepted; one new; an accepted finding at a different `startLine` (still accepted); same identity with a different `"1"` (changed); a missing `identity` (new); a missing `"1"` on a baseline identity (changed); two results sharing one accepted identity (one accepted, one new); a stale entry; results in a second run. It also covers the `GITHUB_STEP_SUMMARY` append, the R8 lines for a result missing `ruleId` and location, and each R9 exit-2 case.
- **R11.** `[PR1]` A workflow test pins R3 to R6: the `needs` entry and the absent `continue-on-error`; `fetch-depth: 2`; both policy commands and the error text; `SNYK_TOKEN` present on exactly one step; `set +e`, the scan command, the stdout redirect and the exit-above-1 branch; both `if:` conditions and the final script call.
- **R12.** `[PR1]` `docs/adr/0049-*.md` records the decision, the math#250, #259, #260 and #261 evidence, the accepting-a-finding procedure, and the rejected alternatives, with a row in `docs/adr/README.md`.
- **R13.** `[PR1]` `CLAUDE.md`'s `snyk-scan` line says the job is a `needs` of `auto-merge`, fails on any finding outside `.snyk-baseline` (matched by identity and fingerprint `"1"`) and on a `.snyk`, `.dcignore` or baseline-addition change, and names `scripts/snyk_baseline.py` and ADR-0049. No CLAUDE.md line calls `snyk-scan` advisory or says it scans Rust. `CLAUDE.md` stays at or under 30000 bytes.
- **R14.** `[PR1]` A P3 Backlog row records removing `snyk-scan` from `ADVISORY_CHECKS` in `scripts/ci-gate.sh` and its `tests/scripts/ci_gate.bats` cases.
- **V1.** On the implementing PR, `snyk-scan` fails only in the policy step, because the PR adds `.snyk` and the baseline. The compare step prints `snyk: 15 accepted, 0 new, 0 changed, 0 stale`. The operator admin-merges.
- **V2.** After merge, open a throwaway draft PR that degrades `run_tool` to `shell=True` as in math#261 (b), plus `scripts/probe_new.py`, plus a `.dcignore` line. `snyk-scan` fails. The log shows `changed:` naming `scripts/mutation_gate_items.py:173`, `new:` naming `scripts/probe_new.py`, and the policy error naming `.dcignore`. The `auto-merge` job is skipped. Close the PR.
- **V3.** The operator reads the Snyk organisation's Code test usage and limit in the web UI and records them in the ADR. An agent session cannot authenticate.
- **V4.** On a PR that changes no Python, for example a docs or workflow-only PR, `snyk-scan` is green and the `auto-merge` job runs.
- **N1.** No change to `scripts/ci-gate.sh`, `tests/scripts/ci_gate.bats` or `.github/required-status-checks`.
- **N2.** No code change to the 15 baseline findings' source files to placate Snyk.
- **N3.** No Snyk organisation ignores and no `snyk ignore` calls.
- **N4.** No third-party Python dependency for `scripts/snyk_baseline.py`, and no `actions/setup-python` step in `snyk-scan`.
- **N5.** No second Snyk scan per run.

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
