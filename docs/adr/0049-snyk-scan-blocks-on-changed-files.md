# ADR-0049: snyk-scan blocks auto-merge when a PR changes a file that holds a finding

**Date:** 2026-11-28
**Status:** Accepted

## Context

`snyk-scan` in `.github/workflows/auto-merge.yml` runs `snyk code test` over the whole tree, and nothing reads its result. It sets `continue-on-error: true`, it is missing from the `auto-merge` job's `needs`, and `scripts/ci-gate.sh` lists it in `ADVISORY_CHECKS` (ADR-0016 made scans advisory).

The history:

- It was red, unread, on math#150, #158 and #162, then green on #170 through #249.
- On math#250 it went red, listing exactly the 4 new `scripts/zeta_results.py` findings. The `auto-merge` job merged that PR two minutes after the second red run.
- math#252's 3 MEDIUM Command Injection findings then landed under a check that was already red.
- It has been red on every PR since.

The repo has `allow_auto_merge: false`, and 54 of the last 60 merges were made by the `auto-merge` job. That job is the consumer that matters.

The scan reports 17 findings on master `d3ef01e`: 3 MEDIUM in `scripts/mutation_gate_items.py`, 8 LOW in `scripts/mutation_weakening.py`, 4 LOW in `scripts/zeta_results.py`, and 2 in test code. Each was read at source and none is a live defect.

Probes ran in CI on throwaway draft PRs (one repo, Snyk CLI 1.1308.0, about 3 hours on 2026-11-28):

- **math#259:** three sanitisers (rejecting `..`, `os.path.realpath`, a basename check) cleared no finding. Snyk does not model guards.
- **math#260:** after 4 inserted lines, `identity` and fingerprint `"1"` both matched 17 of 17.
- **math#261:** a degraded sink kept both results' `identity` and kept `f306d8`'s `"1"` byte-equal; an edit inside `zeta_results._recover` left `f5e20d`'s `"1"` equal; `.gitignore` did not hide a new file but `.dcignore` did.
- **math#262:** with a `tests/**` exclusion, coverage was `.py` 35 and `.html` 1. Snyk skips empty files. A new caller of `run_tool` in `scripts/pip_audit_advisory.py` produced a new result located in that file, with a flow spanning both files. `.rs` was `NOT_SUPPORTED`: Snyk Code scans no Rust.
- **Offline replay:** flow-touch was blind to every guard behind the zeta findings, because no guard line is a flow step.

Three judges were refuted on this data (see Related for the spec's full list): identity diff against `HEAD^1`, a baseline on identity plus fingerprint `"1"`, and flow-touch.

## Decision

`snyk-scan` loses `continue-on-error` and joins the `auto-merge` job's `needs`. `Gate and merge` is the only automatic merge path, so a red `snyk-scan` means no automatic merge. `scripts/ci-gate.sh` is not changed; its `ADVISORY_CHECKS` entry becomes moot.

`scripts/snyk_file_touch.py` (standard library only, run as `python3 -I`, SARIF on stdin) judges the scan with four checks. It runs exactly two fixed-argv git commands (`diff --name-only -z --no-renames HEAD^1 HEAD` on the `refs/pull/<n>/merge` checkout, and `ls-files -z`). No fingerprint and no line number is read.

1. **File-touch.** A result is touched when its location `uri`, or the `uri` of any step in its codeFlows, is a changed file (percent-decoded). A `uri` that does not decode to a tracked path, a path containing whitespace, or a missing `uri` also counts as touched, so a change in Snyk's path form fails closed. A file is the unit that holds both a flow and its guards. A new file with a finding, a new caller elsewhere, and any edit to `scripts/zeta_results.py` are all touched.
2. **Presence list.** The tracked `.snyk-files` records `<path> <count>` of results per file. Any difference between the scan's per-file counts and the list is red: a file gaining a result, losing one, appearing or vanishing. This catches a worsening edit that makes a finding disappear (in math#261, `scripts/mutation_gate_items.py` went from 3 results to 2). It also turns server-side engine drift red instead of silent.
3. **Coverage.** For `.py`, `.html`, `.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.jsx`, `.vue` and any other `SUPPORTED` language, coverage `files` must equal the number of tracked non-empty files with that extension. On master `d3ef01e` that is `.py` 118/118. This catches a `.dcignore`, a `.snyk`, a size limit or a server-side flag hiding a file.
4. **Inline suppressions.** A tracked non-empty file of a compared extension matching `deepcode\s+ignore` (case-insensitive) is red. Whether the CLI honours the comment is unmeasured; refusing it makes the question moot.

There is no `.snyk`. Excluding `tests/**` worked in math#262, but it would hide a sink placed under any `tests/` directory from all three checks, and a static import check cannot close that because scripts load modules dynamically. The 2 test findings join the presence list instead.

Fail-closed rules of the judge: exit 0 only when nothing is touched, coverage and presence match, and no suppression is found; exit 1 otherwise; exit 2 (`snyk_file_touch: <reason>` on stderr) when stdin is not JSON, `runs` is missing or empty, a run lacks `results` or `properties.coverage`, `.snyk-files` is missing, malformed or has a repeated line, or a git command fails. A result missing a field prints `?`, and a missing or non-string `uri` counts as touched. A malformed coverage entry exits 2, and only `SUPPORTED` entries contribute to coverage (a `NOT_SUPPORTED` or typeless entry analysed nothing).

`.snyk-files` and `scripts/snyk_file_touch.py` are `GATE_FILES` entries in `scripts/mutation_gate_items.py`, so editing either turns `mutation-gate-items` red with `uncleared item:` and needs an operator merge. Adding a `.snyk` or `.dcignore` needs no entry, because the coverage check turns it red.

### When `snyk-scan` is red

The red check is the hold, as with an items-gate red. There is no draft step and no `gate-hold` label; that label belongs to the items gate's own sweep.

- **Touched finding.** Judge it at source, including the guards in that file. Fix a real defect. For a false positive, write the judgment in the PR body. The operator then admin-merges. Each PR that touches the file is judged again; nothing is remembered.
- **Coverage mismatch.** Find the skipped file. Revert an added `.dcignore` or `.snyk`. An empty file that should hold code gets its code. A size limit or a Snyk-side cause goes to the operator.
- **Presence difference in a changed file.** A new or worsened finding is already touched; judge it as above. A finding that vanished is judged too: a real fix updates `.snyk-files`, and a worsening edit that hid the finding is reverted.
- **Presence difference in an unchanged file.** Treat it as drift only when the same difference appears on another open PR, or on an empty probe PR. Then report it, and do not edit `.snyk-files` in an unrelated PR. The operator judges the difference at source and merges one list update. Each held PR then needs a new event to pick up the new master: a push, close and reopen, or a label. A re-run reuses the old merge ref. Otherwise the PR's own edits elsewhere probably caused it, so judge the result at source like a touched finding.
- **Inline suppression.** Remove the comment. A false positive is judged in the PR body instead.
- **A result in a path containing whitespace** is touched on every PR. Rename the file.
- Every `.snyk-files` update is an operator merge.
- **Scanner error.** Re-run. If Snyk is down, the operator admin-merges.

## Consequences

- A finding in a file a PR changes, a hidden file, a count change or a suppression blocks the automatic merge. The 17 existing findings stay green, because there is no per-finding baseline.
- Cost on measured history is low. Since the flagged files landed, only #253 and #255 changed them, and both were items-gate merges, so file-touch adds 0 operator merges.
- **Guards in another file are not watched.** If the guard that justifies a finding lives in a file the flow does not name, editing that guard is green. Today every justifying guard is in its finding's own file.
- **Input routed in from outside Python is not seen.** A Makefile or workflow edit that feeds untrusted input into a flagged script's argv is invisible to Snyk. Workflow edits to gate workflows are items-gate holds; Makefile edits are not.
- **No memory.** Every edit to `scripts/zeta_results.py` needs an operator judgment. On history, that file had 1 commit, the one that created it.
- **Snyk drift blocks every PR.** A server-side change that adds or drops a result turns every open PR red, Renovate and workflow-only PRs included, until the operator merges a `.snyk-files` update and each held PR gets a new event. How often drift happens is unmeasured: three scans on 2026-11-28 gave equal per-file counts.
- **Test files are judged like code.** A new test file whose code Snyk flags goes red, and so does an edit to the 2 flagged test files.
- **A helper change in another file.** If a PR changes only a helper in file A, used by a source and sink in unchanged file B, the new result's flow may not name A. The presence list turns a new result in B red with the unchanged-file label. If Snyk instead merges it into an existing result, nothing is red. Unmeasured.
- **A compensating swap.** A PR could hide one file and add a file Snyk counts that the extension list does not, such as an upper-case extension. That needs deliberate evasion, and Snyk's case handling is unmeasured.
- **Snyk outage, quota or a fork PR** turns the job red, which fails closed; the operator admin-merges. Quota stays at one scan per run, as today.
- **The empty-file rule was measured once,** on a 0-byte file. A whitespace-only file is unmeasured; if Snyk skips it, the check goes red, which is noisy but safe.
- Rejected: a function-scope touch (`ast`, one hop), blind to module-level guards; excluding `tests/**` with `.snyk`; code-level sanitisers (none cleared a finding, #259); Snyk organisation ignores (outside the repo, invisible in review); `--severity-threshold=high` (green on a new MEDIUM Command Injection); removing `snyk-scan` (ai-config `ci-021` requires it); branch protection instead of `needs` (it would also block admin merges during a Snyk outage); a count ratchet (blind to degradation at an existing finding).

## Quota

The Snyk Code test usage and limit are recorded here after merge (spec V4).

## Related

- Spec: `docs/superpowers/specs/2026-11-27-snyk-new-findings-only-design.md`. Plan: `docs/superpowers/plans/2026-11-28-snyk-file-touch.md`.
- Refuted judges, each on measured data: identity diff against `HEAD^1` (forgets a finding once it merges; identity survived a degraded sink, #261), baseline on identity plus `"1"` (`"1"` stayed byte-equal on two degraded or edited flows, #261), flow-touch (blind to guard removal; misses lines inside a multi-line region; hunk parsing fails open on `-diff` attributes, renames and quoted paths).
- ADR-0016 (advisory scans; pip-audit stays advisory), ADR-0048 (items gate, operator-only merges), ADR-0037 (pinned downloads).
- `scripts/snyk_file_touch.py`, `.snyk-files`.
