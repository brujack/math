# snyk-scan fails only on findings the PR introduces

- **Date:** 2026-11-27
- **Backlog row:** none; raised in session after math#255, when every PR's `snyk-scan` was red
- **Related:** ADR-0016 (advisory scans), ADR-0037 (pinned downloads), `tests/test_snyk_cli_pinned.py`

## Problem

`snyk-scan` in `.github/workflows/auto-merge.yml` runs `snyk code test` over the whole tree.
It is advisory (`continue-on-error: true`, not in `needs`, treated as advisory by
`scripts/ci-gate.sh`), and it is red on every PR. The six most recent runs on 2026-11-28
(UTC) all concluded `failure`, in 30 to 56 seconds each. A check that is always red carries no
signal: a PR that adds a real injection looks the same as one that changes a comment.

The scan reports 17 findings on master `d3ef01e`, each read at source in this session:

| Findings | File                                                                               | Rule              | Why it is not a live defect                                               |
| -------- | ---------------------------------------------------------------------------------- | ----------------- | ------------------------------------------------------------------------- |
| 3 MEDIUM | `scripts/mutation_gate_items.py` (420, 584, 588)                                   | Command Injection | argv lists, binary resolved by `shutil.which`                             |
| 8 LOW    | `scripts/mutation_weakening.py` (236, 246, 271, 297, 298, 351, 357, 515)           | Path Traversal    | paths are the operator's own CLI arguments                                |
| 4 LOW    | `scripts/zeta_results.py` (957, 961, 1010, 1013)                                   | Path Traversal    | `rmtree` guarded by `_check_targets` / `_check_owned` and the MARKER file |
| 2        | `tests/test_mutation_weakening_e2e.py:127`, `tests/test_mutation_weakening.py:159` | various           | test code                                                                 |

### What was measured

Both probes ran in CI on throwaway PRs, then were closed and their branches deleted.

- **math#259, sanitisers.** Three code-level sanitisers were added: reject `..`, then
  `os.path.realpath`, then a basename check. None cleared a single Path Traversal or
  Command Injection finding. Snyk Code does not recognise these checks as sanitisers. A
  `.snyk` file with `exclude: code: [tests/**]` dropped the count from 17 to 15, removing
  both test findings.
- **math#260, fingerprint stability.** The same tree was scanned twice: once as is, and
  once with 4 lines inserted near the top of each affected file, so 15 of the 17 findings
  moved line. Each SARIF result carries `fingerprints` with keys `identity`, `"0"`, `"1"`
  and `snyk/asset/finding/v1`. Matching run 1 against run 2:

  | Key                     | Common to both runs            |
  | ----------------------- | ------------------------------ |
  | `identity`              | 17 of 17                       |
  | `snyk/asset/finding/v1` | 17 of 17 (equal to `identity`) |
  | `"1"`                   | 17 of 17                       |
  | `"0"`                   | 4 of 17                        |

  Population: one repo, one Snyk CLI version (1.1308.0), 17 findings, and one kind of
  change (a line shift). The probe did not cover a rename of the enclosing function, a
  file move, or a change in Snyk's engine between the two scans.

Per-finding ignores exist only in the Snyk organisation (web UI or `snyk ignore create`),
not in `.snyk` for Snyk Code. `snyk auth` cannot complete from a remote session (its OAuth
callback targets `127.0.0.1:8080`), so the local CLI is unauthenticated (SNYK-0005) and
every measurement here ran in CI.

## Design

### The comparison

A finding is **known** when its `fingerprints.identity` appears in the base scan, and
**new** otherwise. A head result with no `identity` fingerprint is new, so the comparison
fails closed. Line numbers play no part, which is why the 15 moved findings in math#260
stay known.

### The base

`pull_request` checks out `refs/pull/<n>/merge` by default: a merge commit whose first
parent is master's tip at event time and whose second parent is the PR head. The base is
`HEAD^1`. It needs `fetch-depth: 2` and no fetch of `origin/master`. Because GitHub
computes this ref per event, the base is never a stale payload sha. That was the failure
mode in math#238.

### One policy for both scans

Both scans run under the **base commit's** `.snyk`. Before the head scan, the step replaces
the head tree's `.snyk` with `git show HEAD^1:.snyk`, or deletes it when the base has none.
A PR that widens the exclusion therefore cannot hide its own new finding. A PR that changes
`.snyk` takes effect on the PRs after it merges. That includes the PR that adds `.snyk`:
its base has none, so neither scan excludes `tests/**`, and the two test findings count as
known.

### The job

`snyk-scan` keeps `continue-on-error: true`, stays out of `needs`, and keeps the pinned
install step. Its steps become:

1. `actions/checkout` at the same pinned sha, with `fetch-depth: 2`.
2. `Install Snyk CLI`, unchanged.
3. `Run Snyk Code scan`, with `SNYK_TOKEN` in its env, running in order:
   - `git worktree add --detach "${RUNNER_TEMP}/base" HEAD^1`;
   - apply the base policy to the head tree, as above;
   - scan the head: `snyk code test --sarif-file-output="${RUNNER_TEMP}/head.sarif"`, saving
     the exit status in `rc`;
   - if `rc` is greater than 1, print `::error::snyk-scan: scanner error (exit ${rc}) on head`
     and exit 1;
   - scan the base the same way, from `${RUNNER_TEMP}/base`, into `base.sarif`, with the
     same check naming `base`;
   - run `python3 scripts/snyk_new_findings.py "${RUNNER_TEMP}/base.sarif" "${RUNNER_TEMP}/head.sarif"`
     and exit with its status.

Snyk exits 0 when it finds nothing, 1 when it finds something, 2 on failure, and 3 when
there is no supported project. Any status above 1 is a broken scan, never "no new
findings". The comparison script runs on the runner's `python3` and uses only the standard
library.

### `scripts/snyk_new_findings.py`

`snyk_new_findings.py BASE_SARIF HEAD_SARIF`

- It reads every result in every run of each file.
- It prints `snyk: <k> known, <n> new`, then one line per new head result, in file order:
  `new: <level> <ruleId> <uri>:<startLine>`.
- When `GITHUB_STEP_SUMMARY` is set, it appends the same text there.
- It exits 0 when `n` is 0 and 1 when `n` is greater than 0.
- It exits 2, printing `snyk_new_findings: <path>: <reason>` to stderr, when a file is
  missing, unreadable, not JSON, or has no non-empty `runs` list.
- A result missing `ruleId` or a location prints `?` in that field; it does not fail.

### Docs

- **ADR-0049** records the decision, the measurements from math#259 and math#260, and the
  rejected alternatives below.
- **`CLAUDE.md`:** the `snyk-scan` line is rewritten to say the job fails only on new
  findings, naming the script and the ADR. The file stays at or under 30000 bytes; it is
  at 29993 bytes on `d3ef01e`.
- **`ai-config/docs/knowledge/math-ci.md`:** the snyk detail goes here (the policy file,
  the base parent, and the exit codes), since CLAUDE.md has no room for it.

## Known limits

- **Identity stability is measured only for line shifts.** If renaming a function, moving
  a file or a Snyk engine update changes `identity`, a known finding reappears as new. The
  error lands on the red side, and the job is advisory, so the cost is noise, not a missed
  finding.
- **The 15 known findings stay in the tree.** They print as known on every run but never
  turn the job red. Clearing them needs Snyk organisation ignores, which are out of scope.
- **Two scans per PR.** The job's 30–56 s roughly doubles.
- **Snyk test quota is unmeasured.** The repo is public, but no one has checked whether
  Snyk Code tests count against an organisation limit (V3).
- **No `SNYK_TOKEN`, no scan.** A PR from a fork gets no secret, so the scan fails with
  exit 2 and the job goes red, as it does today.

## Rejected alternatives

- **Code-level sanitisers.** Measured in math#259: none cleared a finding.
- **Snyk organisation ignores.** Each ignore is a manual web-UI step outside the repo,
  invisible in review. An agent session cannot authenticate to create one.
- **`--severity-threshold=high`.** Every current finding is MEDIUM or LOW, so this would go
  green. But it would also stay green on a new MEDIUM Command Injection, the class this job
  exists to report.
- **Removing `snyk-scan`.** ai-config `ci-021` requires `snyk-scan` for supported
  languages.
- **Making `snyk-scan` required.** A separate decision. This spec makes the signal
  trustworthy first.
- **Matching on (`ruleId`, `uri`, fingerprint `"1"`).** It was as stable as `identity` in
  math#260, but it needs three fields where one will do. Adding `uri` also turns a file
  move into a new finding.

## Requirements

- **R1.** `[PR1]` A root `.snyk` file contains exactly the lines `version: v1.25.0`, `exclude:`, `  code:` and `    - tests/**`, optionally preceded by `#` comment lines.
- **R2.** `[PR1]` The `snyk-scan` job keeps `continue-on-error: true`, is in no other job's `needs`, keeps the `Install Snyk CLI` step unchanged, and its `actions/checkout` step sets `fetch-depth: 2`.
- **R3.** `[PR1]` The `Run Snyk Code scan` step creates a detached worktree of `HEAD^1` at `${RUNNER_TEMP}/base`, and before the head scan replaces the head tree's `.snyk` with `git show HEAD^1:.snyk`, or deletes it when `HEAD^1` has no `.snyk`.
- **R4.** `[PR1]` The step runs `snyk code test --sarif-file-output="${RUNNER_TEMP}/head.sarif"` in the head tree and `snyk code test --sarif-file-output="${RUNNER_TEMP}/base.sarif"` in `${RUNNER_TEMP}/base`. When either exits with a status greater than 1, the step prints `::error::snyk-scan: scanner error (exit <status>) on <head|base>` and exits 1.
- **R5.** `[PR1]` The step ends by running `python3 scripts/snyk_new_findings.py "${RUNNER_TEMP}/base.sarif" "${RUNNER_TEMP}/head.sarif"` and exits with that command's status.
- **R6.** `[PR1]` `scripts/snyk_new_findings.py BASE HEAD` counts a head result as known when its `fingerprints.identity` appears among the base results, and as new otherwise, including when the head result has no `identity`. It reads results from every run in each file.
- **R7.** `[PR1]` The script prints `snyk: <k> known, <n> new` followed by one line `new: <level> <ruleId> <uri>:<startLine>` per new result in head file order, using `?` for any missing field. It appends the same text to the file named by `GITHUB_STEP_SUMMARY` when that variable is set, and exits 0 when `n` is 0 and 1 otherwise.
- **R8.** `[PR1]` The script exits 2 and prints `snyk_new_findings: <path>: <reason>` to stderr when either file is missing, unreadable, not valid JSON, or lacks a non-empty `runs` list.
- **R9.** `[PR1]` `tests/test_snyk_new_findings.py` covers: no new findings; one new finding; a known finding at a different `startLine` (still known); a head result without `identity` (new); results in a second run; the `GITHUB_STEP_SUMMARY` append; and each R8 exit-2 case.
- **R10.** `[PR1]` A workflow test pins R2 to R5: the `fetch-depth`, the worktree and policy commands, both scan commands, the `exit 1` on a status above 1 for each scan, and the final script call.
- **R11.** `[PR1]` `docs/adr/0049-*.md` records the decision, the math#259 and math#260 measurements, and the rejected alternatives, with a row in `docs/adr/README.md`.
- **R12.** `[PR1]` The `CLAUDE.md` `snyk-scan` line states that the job fails only on findings whose fingerprint the base scan lacks, and names `scripts/snyk_new_findings.py` and ADR-0049. `CLAUDE.md` stays at or under 30000 bytes.
- **V1.** On the implementing PR, the `snyk-scan` log shows `snyk: <k> known, 0 new` with `k` of at least 15, and the job concludes `success`.
- **V2.** On a throwaway PR that adds one new Command Injection (`subprocess.run(sys.argv[1], shell=True)` in a new `scripts/` file), the job concludes `failure` and the log names that file under `new:`. Close the PR afterwards.
- **V3.** After V1 and V2, record the Snyk organisation's Code test usage from the Snyk web UI. The operator reads it, because an agent session cannot authenticate.
- **V4.** In the V1 run's log, `git rev-parse HEAD^2` equals the PR's head sha, which shows the checkout was the merge ref.
- **V5.** On a scan with zero findings, Snyk still writes the `--sarif-file-output` file. Verify in V1's log, or in a probe on a tree with no findings. If it does not, the script reads a missing file as exit 2 and the plan must cover that case.
- **N1.** No change to `scripts/ci-gate.sh`, `.github/required-status-checks`, or the advisory status of `snyk-scan`.
- **N2.** No code changes to the 15 known findings' source files to placate Snyk.
- **N3.** No Snyk organisation ignores and no `snyk ignore` calls.
- **N4.** No third-party Python dependency for `scripts/snyk_new_findings.py`, and no `actions/setup-python` step in `snyk-scan`.
