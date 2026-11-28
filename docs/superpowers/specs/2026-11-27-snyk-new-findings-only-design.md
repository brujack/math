# snyk-scan blocks auto-merge when a PR changes a file that holds a finding

- **Date:** 2026-11-27
- **Backlog row:** none. Raised in session after math#255, when every PR's `snyk-scan` was red.
- **Approved:** 2026-11-28
- **Related:** ADR-0016 (advisory scans), ADR-0037 (pinned downloads), ADR-0048 (items gate, operator-only merges), `tests/test_snyk_cli_pinned.py`
- **Revision:** 6. Round 4 reviewed revision 4 at `fe89565`. Round 5 reviewed revision 5 at `6308713`, which added the presence list. Revision 6 drops `.snyk`, labels drift, and reds on inline suppressions. Earlier judges, each refuted on measured data (see Rejected alternatives):
  - revision 1, `f8ded91`: identity diff against `HEAD^1`;
  - revision 2, `381f3ae`: baseline keyed on identity plus fingerprint `"1"`;
  - revision 3, `1c4114c`: flow-touch.

## Problem

`snyk-scan` in `.github/workflows/auto-merge.yml` runs `snyk code test` over the whole tree,
and nothing reads its result:
- it sets `continue-on-error: true`;
- it is missing from the `auto-merge` job's `needs: [secret-scan, bash-coverage, claude-md-budget]`;
- `scripts/ci-gate.sh` lists it in `ADVISORY_CHECKS`.

The history:
- It was red, unread, on math#150, #158 and #162, then green on #170 through #249.
- On math#250 it went red, listing exactly the 4 new `scripts/zeta_results.py` findings.
  The `auto-merge` job merged that PR two minutes after the second red run.
- math#252's 3 MEDIUM Command Injection findings then landed under a check that was already red.
- It has been red on every PR since.

The repo has `allow_auto_merge: false`, and 54 of the last 60 merges were made by the
`auto-merge` job. That job is the consumer that matters.

The scan reports 17 findings on master `d3ef01e`, each read at source in this session:

| Findings | File | Rule | Why it is not a live defect |
| --- | --- | --- | --- |
| 3 MEDIUM | `scripts/mutation_gate_items.py` (420, 584, 588) | Command Injection | argv lists, binary resolved by `shutil.which` on `_safe_path_entries` |
| 8 LOW | `scripts/mutation_weakening.py` (236, 246, 271, 297, 298, 351, 357, 515) | Path Traversal | paths are the operator's own CLI arguments |
| 4 LOW | `scripts/zeta_results.py` (957, 961, 1010, 1013) | Path Traversal | `rmtree` guarded by `_check_targets`, `_check_owned`, `_canonical` and the MARKER file |
| 2 | `tests/test_mutation_weakening_e2e.py:127`, `tests/test_mutation_weakening.py:159` | various | test code |

Both `scripts/mutation_*.py` files already match the items gate's `GATE_SCRIPT_GLOBS`, so
every edit to them is already an operator merge. Of the existing findings, the 4 in
`scripts/zeta_results.py` and the 2 in `tests/` are outside any gate.

### What was measured

All probes ran in CI on throwaway draft PRs, each closed and its branch deleted. Population:
one repo, Snyk CLI 1.1308.0, and about 3 hours on 2026-11-28.

- **math#259, sanitisers.** Three sanitisers cleared no finding: rejecting `..`,
  `os.path.realpath`, and a basename check. Snyk does not model guards.
- **math#260, line shift.** After 4 lines were inserted, `identity` and fingerprint `"1"`
  both matched 17 of 17.
- **math#261, edits:**
  - **Degraded sink.** Making `run_tool` use `" ".join(args), shell=True` kept both results'
    `identity`. It also kept `f306d8`'s `"1"` byte-equal, although that result's flow gained
    a step.
  - **In-function edit.** An edit inside `zeta_results._recover` left `f5e20d`'s `"1"` equal.
  - **Hiding a file.** `.gitignore` did not hide a new file. `.dcignore` did.
- **math#262, coverage and cross-file:**
  - **Coverage under exclusion.** With the `.snyk` `tests/**` exclusion,
    `properties.coverage` gave `.py` 35 and `.html` 1.
  - **Empty files.** The tree had 36 tracked `.py` files outside `tests/`, and one of them was
    the empty `scripts/probe_empty.py`. So Snyk skips empty files, and 35 is the non-empty count.
  - **Cross-file caller.** A new caller of `run_tool` in `scripts/pip_audit_advisory.py`
    (`run_tool([sys.argv[1]])`) produced a new result located at `scripts/pip_audit_advisory.py:147`.
    Its flow spans both files.
  - **Scope.** The 2 `tests/` findings were gone. `.rs` was `NOT_SUPPORTED`: Snyk Code scans
    no Rust.
- **Offline replays,** against sarif files from #260 and #261:
  - Flow-touch was blind to every guard behind the zeta findings. Deleting the
    `_check_owned` call at line 942 or 943, or gutting `_check_owned`, touched no result,
    because no guard line is a flow step.

### What the measurements decide

- Snyk's fingerprints cannot judge "same finding". Both `identity` and `"1"` missed a
  degraded flow.
- A finding's own flow does not include the code that makes it safe, so watching flows misses
  guard removal.
- A finding's **file** is the unit that holds both the flow and the guards, at least in all
  of today's cases.
- A new taint path yields a result located in the file the PR changes. That was measured
  cross-file in #262.

## Design

### The judge: file-touch

The PR's changed files are the paths printed by
`git -c core.quotePath=false diff --name-only -z --no-renames HEAD^1 HEAD` on the
`refs/pull/<n>/merge` checkout:
- added, modified and deleted paths;
- with `--no-renames`, a move lists both its old and its new path.

A result is **touched** when its location's `uri`, or the `uri` of any step in its codeFlows,
is a changed file. Each `uri` is percent-decoded first. A result with any `uri` that does not decode to a path in `git ls-files` also counts as touched, and is printed with `[untracked uri: <uri>]`. So a future change in Snyk's path form fails closed rather than leaving every result untouched. A result whose decoded location path contains whitespace also counts as touched, because `.snyk-files` cannot name it. An untouched result turns the job red only through the presence list below. That is how the 17 existing findings stay green: there is no per-finding baseline. No fingerprint and no line number is read.

Effects:
- A new file with a finding is touched.
- A new caller elsewhere yields a result in the caller's file, which is touched (#262).
- Any edit to `scripts/zeta_results.py` is touched, including guard removal.
- An edit to `scripts/mutation_*.py` is touched, and is already an items-gate merge.
- The cost on measured history is low. Since the flagged files landed, only #253 and #255
  changed them, and both were items-gate merges. So file-touch adds 0 operator merges.

### The presence list

A tracked file, `.snyk-files`, records how many results Snyk reports per file, counted by each result's location `uri`. Each line is `<path> <count>`; blank and `#` lines are ignored. Counts are keyed by the percent-decoded location path. Results that count as touched because their path is untracked, or contains whitespace, are left out. At bootstrap it holds `scripts/mutation_gate_items.py 3`, `scripts/mutation_weakening.py 8`, `scripts/zeta_results.py 4`, `tests/test_mutation_weakening.py 1` and `tests/test_mutation_weakening_e2e.py 1`. These are the math#260 run-1 SARIF of master `d3ef01e`, which had no `.snyk`. Any difference between the head SARIF's per-file counts and the list is red: a file gaining a result, losing one, appearing or vanishing. This closes the case file-touch alone misses. In math#261, `scripts/mutation_gate_items.py` went from 3 results to 2 under a worsening edit, and a file whose only result vanished would read green. It also turns a server-side engine change that adds or drops results red instead of silent. Such drift is red on every open PR at once, until the operator merges a list update. A difference in a file the PR did not change is printed with `(file unchanged by this PR: Snyk drift, a master-side change, or an effect of this PR's edits elsewhere)`. `.snyk-files` is a `GATE_FILES` entry, so updating it is an operator merge. Outside drift, a count change is already red through file-touch, so on history it adds no merges.

### No `.snyk`

The repo carries no `.snyk`, so every tracked file is scanned, `tests/` included. Excluding `tests/**` was measured to work in math#262, but round 5 showed it is a hole. A PR could put a sink under any `tests/` directory and call it from an unflagged script. Snyk would then never see the sink, and all three checks would stay green. A static import check cannot close this, because scripts already load modules dynamically: `importlib` in `scripts/mutation_gate_items.py` and `scripts/cli_contract.py`, and `sys.path.insert(os.getcwd())` in `scripts/mutation_base_runner.py`. The 2 test findings join the presence list instead. Of 83 tracked test files, 2 hold findings.

### Inline suppressions

The judge is red when any tracked, non-empty file with a compared extension matches `re.compile(r"deepcode\s+ignore", re.I)`. The pattern's source text does not itself contain the phrase, so the judge does not flag itself, and its tests build suppression text at runtime (`"deep" + "code ignore"`). Snyk documents that comment form as an inline suppression. Whether this CLI honours it is unmeasured. If it does, a suppressed result would vanish from the SARIF and slip past every other check. Refusing the comment outright makes the question moot. Today no tracked file contains it.

### The coverage check

Snyk silently skips a file hidden by an added `.snyk`, by a `.dcignore` at any depth, by a size limit
or by a server-side flag. One count covers all of these routes. For each extension in
`.py`, `.html`, `.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.jsx` and `.vue`, and for any other
extension that `properties.coverage` lists as `SUPPORTED`, the coverage `files` value must
equal the number of tracked, non-empty files with that extension. A missing coverage entry counts as 0. Any difference is red, with both numbers printed. On master `d3ef01e`, with no `.snyk`, the measured values are `.py` 118 analysed against 118 tracked and non-empty, and `.html` 1. Snyk skipping empty files was measured twice: once on the `.py` probe file in math#262, and once on `.rs`, where 69 files are tracked, 1 is empty, and coverage was 68.

### Guarded paths

`.snyk-files` and `scripts/snyk_file_touch.py` are added to `GATE_FILES` in
`scripts/mutation_gate_items.py`. `mutation-gate-items` is a required check, runs from
`base.ref`, and turns red with `uncleared item:` on any edit to a listed path. A PR therefore
cannot weaken the judge or the list and still merge automatically. Adding a `.snyk` or a `.dcignore` needs no gate entry, because the coverage check turns it red. `auto-merge.yml` is
already a gate item, because it declares `secret-scan`.

### `scripts/snyk_file_touch.py`

- **Inputs.** It takes no arguments and reads the SARIF on stdin. It runs exactly two
  fixed-argv commands:
  - `git -c core.quotePath=false diff --name-only -z --no-renames HEAD^1 HEAD`;
  - `git ls-files -z`.
  It reads the constant path `.snyk-files`, and reads tracked files of the compared extensions only to test emptiness and to search for `deepcode ignore`. It writes only to stdout and stderr.
- **Invocation.** The job runs it as `python3 -I`, so a PR-added `scripts/json.py` cannot
  shadow the standard library.
- **Header.** `snyk: <t> touched, <u> untouched; coverage <ext> <a>/<b>[, …]`, where `<a>/<b>`
  is analysed over tracked.
- **Each touched result,** in SARIF order: `touched: <level> <ruleId> <uri>:<startLine> — <message.text> [changed: <file>[, …]]`.
- **Each coverage mismatch:** `snyk-scan: Snyk analysed <a> <ext> files but <b> non-empty ones are tracked; a file is hidden from the scan (changed <ext> files: <list or none>)`.
- **Each presence difference:** `snyk-scan: <path> has <m> results; .snyk-files says <n>`, with ` (file unchanged by this PR: Snyk drift, a master-side change, or an effect of this PR's edits elsewhere)` appended when `<path>` is not a changed file.
- **Each suppression:** `snyk-scan: <path> contains an inline Snyk suppression (deepcode ignore)`.
- **On exit 1,** one final `::error::snyk-scan: <t> finding(s) in files this PR changes; <m> coverage mismatch(es); <p> presence difference(s); <s> suppression(s)`.
- **Missing fields** print `?`.
- **Exit codes:**
  - 0 when nothing is touched, coverage and presence match, and no suppression is found;
  - 1 otherwise;
  - 2, with `snyk_file_touch: <reason>` on stderr, when stdin is not JSON, there is no non-empty
    `runs`, a run lacks `results` or `properties.coverage`, `.snyk-files` is missing or has a malformed or repeated line, or a git command fails.

### The job

`snyk-scan` loses `continue-on-error` and joins the `auto-merge` job's `needs`. `Gate and
merge` is the only automatic merge path, so a red `snyk-scan` means no automatic merge.
`scripts/ci-gate.sh` is not changed; its `ADVISORY_CHECKS` entry becomes moot.

Steps:

1. **Checkout.** `actions/checkout` at the pinned sha, with `fetch-depth: 2`. `HEAD` is the
   merge of the PR head into master. `HEAD^1` is master at event time; the math#260 log shows
   `HEAD is now at c0a1083 Merge c854680… into d3ef01e…`.
2. **Install Snyk CLI.** Unchanged.
3. **Run Snyk Code scan** (`id: scan`). `SNYK_TOKEN` is set on this step only.
   - Under `set +e`, it runs
     `snyk code test --sarif-file-output="${RUNNER_TEMP}/snyk.sarif" > "${RUNNER_TEMP}/snyk.txt"`.
   - On an exit status above 1, it prints `::error::snyk-scan: scanner error (exit <rc>)` and
     the contents of `snyk.txt`, then exits 1.
   - Otherwise it exits 0, because exit 1 only means findings exist.
4. **Judge.** No token. Runs under `if: ${{ !cancelled() && steps.scan.outcome == 'success' }}`.
   - Under `set +e`, it runs `python3 -I scripts/snyk_file_touch.py < "${RUNNER_TEMP}/snyk.sarif" > "${RUNNER_TEMP}/judge.txt"`
     and keeps the status in `rc`.
   - It prints `judge.txt`, and appends `judge.txt` minus `::error` lines to `$GITHUB_STEP_SUMMARY`.
   - It exits with the saved status.

### When `snyk-scan` is red

The red check is the hold, as with an items-gate red. There is no draft step and no
`gate-hold` label; that label belongs to the items gate's own sweep.

- **Touched finding.** Judge it at source, including the guards in that file. Fix a real
  defect. For a false positive, write the judgment in the PR body. The operator then
  admin-merges. Each PR that touches the file is judged again; nothing is remembered.
- **Coverage mismatch.** Find the skipped file. Revert an added `.dcignore` or `.snyk`. An
  empty file that should hold code gets its code. A size limit or a Snyk-side cause goes to
  the operator.
- **Presence difference in a changed file.** A new or worsened finding is already touched; judge it as above. A finding that vanished is judged too: a real fix updates `.snyk-files`, and a worsening edit that hid the finding is reverted.
- **Presence difference in an unchanged file.** Treat it as drift only when the same difference appears on another open PR, or on an empty probe PR. Then report it, and do not edit `.snyk-files` in an unrelated PR. The operator judges the difference at source and merges one list update. Each held PR then needs a new event to pick up the new master: a push, close and reopen, or a label. A re-run reuses the old merge ref. Otherwise the PR's own edits elsewhere probably caused it, so judge the result at source like a touched finding.
- **Inline suppression.** Remove the comment. A false positive is judged in the PR body instead.
- **A result in a path containing whitespace** is touched on every PR. Rename the file.
- Every `.snyk-files` update is an operator merge.
- **Scanner error.** Re-run. If Snyk is down, the operator admin-merges.

The implementing PR adds `scripts/snyk_file_touch.py` and `.snyk-files`, and changes
`scripts/mutation_gate_items.py`. It is therefore an items-gate PR, and the operator's admin
merge is its review.

### Docs

- **ADR-0049.** Records:
  - the decision;
  - the evidence from math#250 and math#259 to #262;
  - the three refuted judges;
  - the red procedure;
  - the Known limits.
- **`CLAUDE.md`:**
  - The `snyk-scan` line says the job is a `needs` of `auto-merge`. It reds on a finding in a
    file the PR changes, on a coverage mismatch, on a `.snyk-files` presence difference, or on an
    inline suppression.
  - That line names `scripts/snyk_file_touch.py` and ADR-0049.
  - That line drops the claim that Rust is scanned.
  - The `auto-merge.yml` line and the ci-gate line stop calling `snyk-scan` advisory.
  - The items-gate line's list gains nothing; `GATE_FILES` stays a code detail.
  - The file stays at or under 30000 bytes. It is 29993 bytes on `d3ef01e`.

## Known limits

- **Guards in another file are not watched.** A finding is watched through every file its
  flow names. If the guard that justifies it lives in a file the flow does not name, editing
  that guard is green. Today every justifying guard is in its finding's own file.
- **Input routed in from outside Python is not seen.** A Makefile or workflow edit that feeds
  untrusted input into a flagged script's argv is invisible to Snyk. Workflow edits to gate
  workflows are items-gate holds; Makefile edits are not.
- **No memory.** Every edit to `scripts/zeta_results.py` needs an operator judgment. On
  history, that file had 1 commit, the one that created it.
- **Snyk drift blocks every PR.** A server-side change that adds or drops a result in any file turns every open PR red. That includes Renovate and workflow-only PRs. It lasts until the operator merges a `.snyk-files` update, and then until each held PR gets a new event (push, reopen or label), because a re-run reuses the old merge ref. The drift label names the cause, but how often drift happens is unmeasured: three scans on 2026-11-28 gave equal per-file counts.
- **Test files are judged like code.** A new test file whose code Snyk flags goes red, and so does an edit to the 2 flagged test files. Each is an operator merge.
- **A helper change in another file.** If a PR changes only a helper in file A, used by a source and sink in unchanged file B, the new result's flow may not name A. Snyk would then report it in B as a new result. The presence list turns that red, with the unchanged-file label, and the red procedure judges it at source unless the same difference shows on another PR. If instead Snyk merges it into an existing result, nothing is red. Unmeasured.
- **A compensating swap.** A PR could hide one file and add a file Snyk counts that R7 does not, such as an upper-case extension. That needs deliberate evasion, and Snyk's case handling is unmeasured.
- **Snyk outage, quota or a fork PR** turns the job red, which fails closed. The operator
  admin-merges. Quota stays at one scan per run, as today; the monthly limit is unverified (V4).
- **The empty-file rule was measured once,** on a 0-byte file. A whitespace-only file is
  unmeasured. If Snyk skips it, the check goes red, which is noisy but safe.

## Rejected alternatives

- **Identity diff against `HEAD^1`** (revision 1). It forgets a finding once the finding
  merges, and identity survived a degraded sink (#261).
- **Baseline on identity plus `"1"`** (revision 2). `"1"` stayed byte-equal on two
  degraded or edited flows (#261). It is also exposed to server-side re-fingerprinting.
- **Flow-touch** (revision 3). It is blind to guard removal, because guards are never flow
  steps. It misses lines inside a multi-line region. And hunk parsing fails open on
  `-diff` attributes, renames and quoted paths.
- **A function-scope touch (`ast`, one hop).** More code, and it is still blind to module-level
  guards, MARKER for example.
- **Excluding `tests/**` with `.snyk`** (revisions 1 to 5). It hides any sink placed under a `tests/` directory from all three checks.
- **Code-level sanitisers.** None cleared a finding (#259).
- **Snyk organisation ignores.** They live outside the repo, are invisible in review, and
  need an auth an agent cannot complete.
- **`--severity-threshold=high`.** Green on a new MEDIUM Command Injection.
- **Removing `snyk-scan`.** ai-config `ci-021` requires it.
- **Branch protection instead of `needs`.** It would also block the operator's admin merges
  during a Snyk outage.
- **A count ratchet.** Blind to degradation at an existing finding.

## Requirements

- **R1.** `[PR1]` No `.snyk` and no `.dcignore` file is tracked anywhere in the repo.
- **R2.** `[PR1]` In `.github/workflows/auto-merge.yml`: `snyk-scan` has no `continue-on-error`; the `auto-merge` job's `needs` contains `snyk-scan`; the `Install Snyk CLI` step is unchanged; and `snyk-scan`'s `actions/checkout` sets `fetch-depth: 2`. `tests/test_workflow_continue_on_error.py` no longer allow-lists `snyk-scan`.
- **R3.** `[PR1]` The scan step has `id: scan` and is the only step with `SNYK_TOKEN`. Under `set +e` it runs `snyk code test --sarif-file-output="${RUNNER_TEMP}/snyk.sarif"` with stdout redirected to `${RUNNER_TEMP}/snyk.txt`. On an exit status above 1 it prints `::error::snyk-scan: scanner error (exit <status>)` and the contents of `snyk.txt`, then exits 1; otherwise it exits 0.
- **R4.** `[PR1]` A judge step without `SNYK_TOKEN`, with `if: ${{ !cancelled() && steps.scan.outcome == 'success' }}`, runs under `set +e` `python3 -I scripts/snyk_file_touch.py < "${RUNNER_TEMP}/snyk.sarif" > "${RUNNER_TEMP}/judge.txt"`, saves the status in `rc`, prints `judge.txt`, appends it minus lines starting `::error` to `$GITHUB_STEP_SUMMARY`, and exits with `rc`.
- **R5.** `[PR1]` `scripts/snyk_file_touch.py` takes no arguments, reads the SARIF from stdin, the constant path `.snyk-files`, and tracked files of the compared extensions (for emptiness and the suppression search), runs no command other than `git -c core.quotePath=false diff --name-only -z --no-renames HEAD^1 HEAD` and `git ls-files -z`, and opens no file for writing.
- **R6.** `[PR1]` The script percent-decodes every location and codeFlow step `uri`, and marks a result touched when any decoded `uri` of its first location or of any step in any of its codeFlows' threadFlows equals a path from the diff command or is not a path printed by `git ls-files -z` (printed as `[untracked uri: <uri>]` on its `touched:` line), or when its decoded location path contains whitespace.
- **R7.** `[PR1]` For each extension in `.py`, `.html`, `.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.jsx` and `.vue`, and any other extension a `properties.coverage` entry with `type` `SUPPORTED` lists, the script compares the coverage `files` value (0 when no entry exists) with the number of `git ls-files -z` paths that have that extension and are non-empty regular files on disk; any inequality is a coverage mismatch. Any such file whose content matches `re.compile(r"deepcode\s+ignore", re.I)` is a suppression; the script's own source does not contain the phrase `deepcode ignore`.
- **R8.** `[PR1]` The script prints `snyk: <t> touched, <u> untouched; coverage <ext> <a>/<b>` for each compared extension, comma-separated. For each touched result in SARIF order it prints `touched: <level> <ruleId> <uri>:<startLine> — <message.text> [changed: <comma-separated changed paths on that result>]`. For each mismatch it prints `snyk-scan: Snyk analysed <a> <ext> files but <b> non-empty ones are tracked; a file is hidden from the scan (changed <ext> files: <list or none>)`. For each presence difference (counts keyed by decoded location path, excluding results touched for an untracked or whitespace path) it prints `snyk-scan: <path> has <m> results; .snyk-files says <n>`, appending ` (file unchanged by this PR: Snyk drift, a master-side change, or an effect of this PR's edits elsewhere)` when `<path>` is not a changed path. For each suppression it prints `snyk-scan: <path> contains an inline Snyk suppression (deepcode ignore)`. On exit 1 it prints a final `::error::snyk-scan: <t> finding(s) in files this PR changes; <m> coverage mismatch(es); <p> presence difference(s); <s> suppression(s)`. Missing fields print `?`. It exits 0 when all four counts are 0, and 1 otherwise.
- **R9.** `[PR1]` The script exits 2 and prints `snyk_file_touch: <reason>` to stderr when stdin is not valid JSON, has no non-empty `runs` list, has a run without a `results` array or without `properties.coverage`, when `.snyk-files` is missing or has a line that is not `<path> <non-negative integer>` or repeats a path, or when either git command exits non-zero.
- **R10.** `[PR1]` `tests/test_snyk_file_touch.py`, with git calls, the `.snyk-files` read and file reads and stats all stubbed, covers: no touched result; a touched location; a touched flow step in a second file only; an added file; a deleted file; a renamed file listed under both paths; a percent-encoded `uri`; a `uri` outside the tracked set; a whitespace path; a result in a second run; a coverage mismatch in each direction; an empty tracked file excluded; a missing coverage entry counted as 0; presence equal, a count up, a count down, a file appearing and a file vanishing, each with and without the drift label; a suppression comment in upper and lower case and with extra whitespace, with the suppression text built at runtime so the test file itself never contains the phrase; the suppression check over the real tracked tree reporting 0; and each R9 exit-2 case. It also replays committed fixtures: `tests/fixtures/snyk/sarif-262.json` with changed paths `scripts/pip_audit_advisory.py` alone, asserting exactly the result at `scripts/pip_audit_advisory.py:147` is touched; and `tests/fixtures/snyk/sarif-d3ef01e.json` (math#260 run 1) with `tests/fixtures/snyk/files-d3ef01e.tsv` (`<size>\t<path>` per tracked file of `d3ef01e`), asserting coverage `.py 118/118` and `.html 1/1` and no presence difference against the R16 list.
- **R11.** `[PR1]` A workflow test, `tests/test_snyk_scan_workflow.py`, pins R2 to R4: the `needs` entry and the absent `continue-on-error`; `fetch-depth: 2`; `SNYK_TOKEN` on exactly one step; the scan step's `set +e`, command, stdout redirect and exit-above-1 branch; and the judge step's `if:`, `set +e`, `python3 -I` stdin invocation, `rc` capture and summary filter.
- **R12.** `[PR1]` `GATE_FILES` in `scripts/mutation_gate_items.py` contains `.snyk-files` and `scripts/snyk_file_touch.py`; a test in `tests/test_mutation_gate_items.py` shows an edit to each yields an `uncleared item: gate` line.
- **R13.** `[PR1]` `docs/adr/0049-*.md` records the decision, the evidence from math#250 and math#259 to #262, the three refuted judges, the red procedure and the Known limits, with a row in `docs/adr/README.md`.
- **R14.** `[PR1]` `CLAUDE.md`'s `snyk-scan` line says the job is a `needs` of `auto-merge` and fails on a finding in a file the PR changes, a coverage mismatch, a `.snyk-files` presence difference or an inline suppression, and names `scripts/snyk_file_touch.py` and ADR-0049. No CLAUDE.md line calls `snyk-scan` advisory or says it scans Rust. `CLAUDE.md` stays at or under 30000 bytes.
- **R15.** `[PR1]` A P3 Backlog row records removing `snyk-scan` from `ADVISORY_CHECKS` in `scripts/ci-gate.sh` and its `tests/scripts/ci_gate.bats` cases.
- **R16.** `[PR1]` A root `.snyk-files` holds exactly the lines `scripts/mutation_gate_items.py 3`, `scripts/mutation_weakening.py 8`, `scripts/zeta_results.py 4`, `tests/test_mutation_weakening.py 1` and `tests/test_mutation_weakening_e2e.py 1`, optionally preceded by `#` comment lines, plus one line per new file of the implementing PR in which V1 shows results.
- **V1.** On the implementing PR the judge prints exactly the 3 `scripts/mutation_gate_items.py` results as `touched:`, plus any located in the PR's new files. It prints coverage `.py <a>/<a>` and `.html 1/1` (equal counts; `a` is 121 if the PR adds exactly three `.py` files), no suppression, and no presence difference beyond the PR's new files. `snyk-scan` is red, the `auto-merge` job is skipped, and `mutation-gate-items` is red. If any other line appears, the PR is not merged and the spec is amended.
- **V2.** After merge, open a throwaway draft PR with two pushes: **Push 1** (a mechanism check; it cannot fail under file-touch by design) deletes the `_check_owned(flag, target, allow_empty=True)` call in `scripts/zeta_results.py`. It must print `touched:` for the 4 zeta results, and the `auto-merge` job must be skipped. **Push 2** reverts push 1 and adds `scripts/probe_new.py` (`subprocess.run(sys.argv[1], shell=True)`) plus `scripts/.dcignore` naming it. It must print a `.py` coverage mismatch. Close the PR afterwards.
- **V3.** On a later PR that changes no flagged file, the judge prints `snyk: 0 touched, <u> untouched` with `u` at least 17, coverage equal for every extension, and the `auto-merge` job runs.
- **V4.** The operator reads the Snyk organisation's Code test usage and limit and records them in ADR-0049; if the monthly limit is below twice the auto-merge run count of the last 30 days, quota exhaustion is added to Known limits as an expected wedge with its reset date.
- **N1.** No change to `scripts/ci-gate.sh`, `tests/scripts/ci_gate.bats` or `.github/required-status-checks`.
- **N2.** No edit to the 17 existing findings' source files aimed at clearing or reshaping a finding; R12's `GATE_FILES` entries are the only change to a flagged file.
- **N3.** No Snyk organisation ignores, no `snyk ignore` calls, and no inline `deepcode ignore` comments.
- **N4.** No third-party Python dependency for `scripts/snyk_file_touch.py`, and no `actions/setup-python` step in `snyk-scan`.
- **N5.** No second Snyk scan per run, and no use of SARIF `fingerprints` or line numbers in the touch decision.

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
Disposition: operator approved 2026-11-28 ("Approved"), as suggested: Addressed by revisions 4 to 6.
#### Risk

Finding: a SARIF run without a `results` array reads as zero findings and passes green. R8 misses this. The SARIF spec says absent `results` means the tool produced none, while `[]` means it found nothing. Fix: exit 2 on a run lacking a `results` array, optionally also on no `properties.coverage` entry with `isSupported: true` and `files > 0`, and add an R9 case. Second: the step runs under `bash -e`, and the head scan always exits 1. So the obvious `snyk ...; rc=$?` aborts before `rc` is read (probed: `bash -e -c 'false; rc=$?; echo reached'` printed nothing), and R10's text pin would pass that broken code. Fix: R4 should require `set +e`, as `claude-md-budget` already does. Also not raised: `SNYK_TOKEN` should be scoped to the two `snyk` calls rather than the PR-controlled script.
Assumption: a base scan from `${RUNNER_TEMP}/base` (another path, a git worktree) yields the same `identity` values for unchanged findings as a head scan from `$GITHUB_WORKSPACE`. The identities are UUIDv4, which suggests server-side assignment possibly keyed on project or path. math#260 measured two runs at the same path only. If false, every known finding is new, and the job is red on every PR again. This is settled by scanning one tree at both paths in one job.
Disposition: operator approved 2026-11-28 ("Approved"), as suggested: Addressed by revisions 4 to 6.
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
Disposition: operator approved 2026-11-28 ("Approved"), as suggested: Addressed by revisions 4 to 6.
#### Ergonomics

Finding: engine drift turns every open PR red at once, including Renovate, docs-only and workflow-only PRs. The output names files the PR never touched, and agents follow "copy the `baseline:` line" into operator-only merges. A re-run does not help, because it reuses the old merge ref, so every PR needs a new event. Fix: mark each line "in this PR's diff" or "not in this PR's diff", say "likely engine drift" when none are, and add drift to Known limits.
Secondary findings:
- Copying a `changed:` line's `baseline:` text duplicates the identity, which is R9 exit 2. The output should say "replace".
- The judge accepts a reasonless or `?` reason.
- No `gate-hold` instruction tells the operator a PR is waiting.

Estimated cost: about 2 operator merges a month from new code, and 0 of 2 historical edits touched a flagged flow.
Assumption: the same engine-drift stability as goal-fit.
Disposition: operator approved 2026-11-28 ("Approved"), as suggested: Addressed by revisions 4 to 6.
#### Risk

Finding:
- **Fail-open: the policy pathspec is root-only.** `scripts/.dcignore` does not match `-- .snyk .dcignore` (probed). Whether a nested `.dcignore` hides a file is unmeasured.
- **Fail-open: the judge script is unguarded.** The workflow edit is caught by the items gate (`auto-merge.yml` declares `secret-scan`), but `scripts/snyk_baseline.py` is not, so an agent can weaken it and merge green.
- **Engine drift is an undocumented block on every merge**, and the `changed` class cannot tell drift from degradation.
- **V4 passes on no measurement**, because a skipped compare step is green.
- **Minor:** `if: always()` spends quota on cancelled runs (use `!cancelled()`), and R2 and R9 disagree on whether a reason is required.
Assumption: the same engine-drift stability.
Disposition: operator approved 2026-11-28 ("Approved"), as suggested: Addressed by revisions 4 to 6.
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

### Round 3

Reviewed at commit: `1c4114c` (revision 3, flow-touch). Fresh lenses; earlier rounds framed as history.

#### Goal-Fit

Finding: the guards that make the 15 findings safe are not flow steps. Snyk does not model them (math#259).
- In the zeta flows, no step falls in `_check_owned` (903-916), its calls (942-944), `_has_marker`, `_check_symlinks`, `_check_inputs` or `_canonical`'s refusals (863-870). Deleting line 943 gave 0 touched in the replay, and so did gutting `_check_owned`.
- A PR can turn a tolerated finding into a live defect and stay green.

Simpler and stronger alternative, **file-touch**: red when the PR changes any line of a file holding a result's location or any flow step. On measured history it adds 0 operator merges: the flagged files were touched after landing only by #253 and #255, both already items-gate merges.

Premise verified: flow-touch, or file-touch, would have turned math#250 and #252 red, because both added their files. The R10 replay of math#261 is exact: 6 touched, 12 untouched.
Assumption: with the new `.snyk`, SARIF coverage `.py` drops excluded files to 35. That is unmeasured; every SARIF so far came from a run without `.snyk`. Settle it with a pre-PR probe.
Disposition: operator approved 2026-11-28 ("Approved"), as suggested: Addressed by revisions 4 to 6.
#### Ergonomics

Finding: reds are rare. A replay of the last 40 first-parent commits on d3ef01e found only #250 and #252 touched, the commits that added the code. #253 and #255 touched nothing.
- **`gate-hold` is overloaded.** The items gate's sweep (`ITEMS_GATE_LINE`) would un-draft and un-label snyk-held PRs. The draft-plus-label step adds nothing, because the red `needs` already holds the merge. Fix: mirror the items gate, where the red check is the hold, with no draft and no label.
- It also confirms the off-flow guard gap and the startLine-only gap.
- **Minor:** about 10 error annotations per step may be capped (unverified). Emit one `::error` line with a count.

Assumption: the same `.snyk` coverage figure of 35.
Disposition: operator approved 2026-11-28 ("Approved"), as suggested: Addressed by revisions 4 to 6.
#### Risk

Finding:
- **F1: the guarded-path check runs inside the PR's own judge**, so an edit can delete it and stay green. `.snyk` and the judge must go into the items gate's `GATE_FILES` (run from `base.ref`, required).
- **F2: stdlib shadowing.** A PR-added `scripts/json.py` replaces the judge's parser (probed). Run it with `python3 -I`.
- **F3: diff parsing fails open.** A `.gitattributes` `*.py -diff` turns a new file into `Binary files … differ` with no hunk. A `git mv` out of `tests/` shows no hunks. Quoted non-ASCII paths and paths with spaces fail to map.
- **F4: likely wedge.** `.rs` coverage reads 68 against 69 tracked, and the only empty `.rs` file is the likely reason. If Snyk skips empty files, an empty `__init__.py` reads as hidden.
- **F5:** coverage checks `.py` only, but Snyk also analyses `.html`.

Assumption: the `.snyk` coverage formula, including empty files.
Disposition: operator approved 2026-11-28 ("Approved"), as suggested: Addressed by revisions 4 to 6.
#### Adversarial Spec Review (comparison/judge designs only)

Findings:
- **Off-flow guards, confirmed with concrete green PRs:** delete line 942; change line 912 to `if allow_empty:`; drop the cwd check at 869.
- **Multi-line regions:** the step 926-929 misses an edit at 928, which drops `_canonical` on `--runs-out`.
- **The items gate already holds most findings.** `GATE_SCRIPT_GLOBS` covers `scripts/mutation_*.py`, so 11 of the 15 findings already sit behind operator merges, and flow-touch's marginal value is the 4 zeta findings, which is exactly where the guard gap bites.
- **Cross-file flows:** all 17 flows stay within one file, so whether a new caller in another file yields a result is unknown.
- **Recall:** R10 replays only known cases. Add offline fixture cases for 942, 912 and 928.

Assumption: a new taint path to an existing sink yields a result whose coordinates land on the PR's lines. math#261 (a) was the only evidence, and it was confounded. Settle it with an unconfounded probe before merge.
Disposition: Addressed. The operator chose "File-touch + probe first (Recommended)". math#262 then measured three things: coverage `.py` 35 under `.snyk`, an empty file skipped, and a cross-file caller giving a result in its own file. Revision 4 judges by file, moves the guard into the items gate's `GATE_FILES`, runs `python3 -I`, and checks coverage per extension on non-empty files.

### Round 4

Reviewed at commit: `fe89565` (revision 4, file-touch). Fresh lenses; earlier rounds framed as history.

#### Goal-Fit

Finding: revision 4 is worth building, and the cheaper path fails. Extending the items gate to cover the flagged paths would have caught neither incident: math#250 and #252 added new files, and the items gate runs from `base.ref`. File-touch covers a new file with a finding by construction.

Two smaller findings:
- **V1 passes on nothing.** The implementing PR edits `scripts/mutation_gate_items.py`, so its 3 results must be touched and the `auto-merge` job skipped.
- **R10's `35/35` replay drops `scripts/probe_empty.py` because the file is missing on disk, not because it is empty.**

The "0 added operator merges" figure rests on a 2-day history.
Assumption: a PR that only changes a helper in file A, used by a source and sink in an unchanged file B, gets a result whose flow names A. Unmeasured.
Disposition: operator approved 2026-11-28 ("Approved"), as suggested: Addressed by revisions 4 to 6.
#### Ergonomics

Finding: **R7's `tests/` exclusion is root-only, but Snyk excludes `tests/**` at any depth.**
- Evidence from `.rs`: 69 tracked, 1 of them empty, 5 under root `tests/` and 14 under nested `*/tests/`.
- sarif1 reports 68. sarif4 reports 49, which is 68 − 5 − 14. A root-only exclusion would give 63.

The first nested `foo/tests/x.py` wedges every later PR red, and the remedy text points at `.dcignore` or `.snyk`. Also V1 is vacuous, and R10 depends on the live checkout. The mismatch line cannot name the hidden file; printing the PR's changed paths for that extension would help. Red rate: on the last 60 merged PRs, file-touch adds none. Both checks go red together on edits to `scripts/mutation_*.py`, and one admin merge clears both.
Assumption: the any-depth semantics measured on `.rs` also hold for `.py`.
Disposition: operator approved 2026-11-28 ("Approved"), as suggested: Addressed by revisions 4 to 6.
#### Risk

Finding:
- **F1:** a SARIF `uri` that is not a raw git path is silently untouched. A percent-encoded space or non-ASCII name, or a future `./` or `file://` form, leaves it untouched. Fix: any location or flow `uri` not in `git ls-files` counts as touched, which fails closed.
- **F2:** the same nested-`tests/` wedge as above, with the same `.rs` arithmetic.
- **F3:** V1 is vacuous.
- **F4:** R10 cannot pass as written, because emptiness is read from a disk that the stubbed fixture does not populate.
- **F5:** the judge step's status capture is unpinned. Under `bash -e`, `python3 … > judge.txt; rc=$?` aborts before printing. Pin `set +e`.

Checked clean:
- `python3 -I` isolation, probed with a planted `json.py`;
- the `GATE_FILES` exact-match path to `uncleared item: gate`;
- `-z` path output;
- submodule gitlinks.
Assumption: SARIF `uri` equals git's raw path for every filename. F1's rule makes it moot.
Disposition: operator approved 2026-11-28 ("Approved"), as suggested: Addressed by revisions 4 to 6.
#### Adversarial Spec Review (comparison/judge designs only)

Findings:
- **F1: a worsening edit can make a file's results disappear.** In sarif1 to sarif3 (math#261), `scripts/mutation_gate_items.py` went from 3 results to 2: `00ab70` vanished when the sink degraded, and only its siblings kept the file touched. A single-result file losing its result reads green. Fix: a committed per-file count list, `.snyk-files`, as a `GATE_FILES` entry. It is red when result-bearing files or their counts differ. That also turns engine drift red instead of silent. It reads no fingerprints, and it is stable on the axis #260 and #261 measured.
- **F2:** percent-encoded `uri`, as in Risk F1. Fix: `unquote`, then fail closed on a `uri` outside the tracked set.
- **F3:** `.snyk` makes `tests/` invisible to both checks. Today nothing runs or imports `tests/*.py` as a tool. Either drop the exclusion or name it in Known limits.

Recall: V2 push 1 cannot fail under file-touch. Missing probes are a single-result file under `shell=True` and a taint-losing refactor, plus an encoded filename.
Assumption: a worsening edit leaves at least one result touching a changed file. #261 already shows one result vanishing. `.snyk-files` makes the assumption moot.
Disposition: Addressed. The operator chose "Add .snyk-files (Recommended)" for F1 and "Keep, name in limits (Recommended)" for F3. Revision 5 adds `.snyk-files` (R16, R8, R9), percent-decodes and fails closed on an untracked `uri` (F2, R6), and names `tests/` in Known limits.

### Round 5 (scoped)

Reviewed at commit: `6308713` (revision 5). Scoped to the text changed since `74161ac`; Risk and Adversarial only, because round 4 left the file-touch design standing.

#### Risk

Finding: presence is compared repo-wide, so engine drift reddens every open PR until an operator merges a `.snyk-files` update. That is the wedge revision 2 was rejected for, and it went unstated. Neither Known limits nor the red procedure handled it: the procedure called every presence difference "already touched", which is false for drift. Two unchanged lines also contradicted the presence list: "Untouched results never turn the job red" and R14's description of the `CLAUDE.md` line. The presence key was undefined (raw or decoded path, whitespace).

Checked and right:
- The R16 bootstrap counts (3/8/4, plus the #262 probe's 1 in `pip_audit_advisory.py`).
- Bootstrap ordering.
- R7's any-depth `tests` arithmetic on the #262 tree.
- R4's `set +e`.

Assumption: per-file counts stay stable for unchanged code across Snyk engine updates. Unmeasured beyond one day.
Disposition: Addressed. The operator chose "Repo-wide, drift branch (Recommended)". Revision 6 adds the drift label, a Known-limits row with the blast radius, the drift branch in the red procedure, the decoded and no-whitespace presence key, and the corrected design line and R14.

#### Adversarial Spec Review (comparison/judge designs only)

Findings:
- **Hole A (definite): a sink placed under any `tests/` directory and called from an unflagged script is green on all three checks.** `.snyk` hides the sink, and R7 skips `tests` too. The Known-limits line "Today nothing runs or imports `tests/*.py`" described the present state, not a guard.
- **Replay of #261 through all three conditions:** each is red on its own.
- **Presence false positives:** counts equal across sarif1, sarif2 and sarif4.
- **The same-file swap is caught**, and the cross-file guard case narrows: #262 shows Snyk names helper files in flows.

Assumption: inline `# deepcode ignore` comments do not drop results from the CLI SARIF. Unmeasured; math#163 holds no such measurement.
Disposition: Addressed. The operator chose "Drop .snyk entirely (Recommended)". Revision 6 has no `.snyk` (R1), scans and counts `tests/`, and adds the 2 test findings to `.snyk-files`. It also makes the suppression assumption moot: any tracked `deepcode ignore` is red (R7, R8, N3).

## External Review

### Round 1 (reviewed at `97e1bae`)

Report: [round1.md](2026-11-27-snyk-new-findings-only-design.external-review/round1.md)

#### Author response

| finding | disposition | evidence | reviewer verdict | operator (Step 9) |
| ------- | ----------- | -------- | ---------------- | ----------------- |
| F1.1 | Fixed | Inline suppressions and R7: pattern `re.compile(r"deepcode\s+ignore", re.I)`, whose source lacks the phrase; R10: runtime-built fixtures, whitespace variant, and a case that the real tree reports 0 | unjudged | approved 2026-11-28 ("Approved") |
| F1.2 | Fixed | Label now reads "Snyk drift, a master-side change, or an effect of this PR's edits elsewhere" (design, R8); red procedure treats an unchanged-file difference as drift only when another open PR or an empty probe PR shows it, else judges at source; Known limits helper row updated | unjudged | approved 2026-11-28 ("Approved") |
| F1.3 | Fixed | Red procedure and the drift Known-limits row state each held PR needs a new event (push, reopen, label) because a re-run reuses the old merge ref | unjudged | approved 2026-11-28 ("Approved") |
| F1.4 | Fixed | R11 names `tests/test_snyk_scan_workflow.py`; V1 requires equal counts, with `a` = 121 for three new `.py` files | unjudged | approved 2026-11-28 ("Approved") |
| F1.5 | Fixed | Red procedure: a whitespace path is touched on every PR; rename the file | unjudged | approved 2026-11-28 ("Approved") |
| F1.6 | Fixed | V2 push 1 labelled a mechanism check that cannot fail by design; V4 now states its decision (below 2x monthly runs adds a quota wedge to Known limits) | unjudged | approved 2026-11-28 ("Approved") |

Stopped: reviewer recommended stopping in round 1

