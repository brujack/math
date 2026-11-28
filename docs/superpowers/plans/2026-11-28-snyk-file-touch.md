# snyk-scan file-touch judge Implementation Plan

spec: docs/superpowers/specs/2026-11-27-snyk-new-findings-only-design.md
scope: PR1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `snyk-scan` becomes a `needs` of `auto-merge` and fails only on a finding in a file the PR changes, a coverage mismatch, a `.snyk-files` presence difference or an inline suppression.

**Architecture:** The scan step writes SARIF; a new stdlib-only judge, `scripts/snyk_file_touch.py`, reads it on stdin, compares it with the merge ref's changed files (`HEAD^1..HEAD`), tracked files and `.snyk-files`, and prints one verdict. Both new files join `GATE_FILES`, so editing them is an items-gate hold.

**Tech Stack:** Python 3 stdlib, GitHub Actions, `unittest`, PyYAML (tests only), Snyk CLI 1.1308.0 (unchanged).

## Global Constraints

- Work only in the worktree `.worktrees/snyk-file-touch` (branch `ci/snyk-file-touch`). Never `git add -A`/`.`/`-u`; stage exact paths. No `--no-verify`, no `--amend`, no `git stash`, no `git config`.
- Python tools come from the main checkout's venv: `../../.venv/bin/python3`, `../../.venv/bin/pyright`, `../../.venv/bin/ruff`. Read `~/.claude/standards/python.md` before writing `.py`.
- The judge imports only the standard library (N4) and is run as `python3 -I`, so it must not import sibling modules.
- No SARIF `fingerprints` and no line number takes part in the touch decision (N5). No second Snyk scan.
- No change to `scripts/ci-gate.sh`, `tests/scripts/ci_gate.bats` or `.github/required-status-checks` (N1).
- No edit to `scripts/mutation_weakening.py`, `scripts/zeta_results.py`, `tests/test_mutation_weakening.py`, `tests/test_mutation_weakening_e2e.py`; the only edit to `scripts/mutation_gate_items.py` is the two `GATE_FILES` entries (N2).
- No `.snyk`, `.dcignore`, `snyk ignore` or inline suppression comment anywhere (N3, R1).
- The phrase `deepcode` + space + `ignore` must not appear in any tracked `.py`, `.html`, `.js`, `.mjs`, `.cjs`, `.ts`, `.tsx`, `.jsx` or `.vue` file, the judge and its tests included: build it at runtime as `"deep" + "code ignore"`. The suppression regex is `re.compile(r"deepcode\s+ignore", re.I)`.
- Per-task gates are scoped; the orchestrator runs root `make test` once after Task 5.

### Judge contract (exact strings, R5-R9)

- Commands, fixed argv: `["git", "-c", "core.quotePath=false", "diff", "--name-only", "-z", "--no-renames", "HEAD^1", "HEAD"]` and `["git", "ls-files", "-z"]`. Any non-zero exit: exit 2.
- Compared extensions: `.py .html .js .mjs .cjs .ts .tsx .jsx .vue` in that order, then any other `lang` of a coverage entry with `type` `SUPPORTED`, sorted. Extension of a path is `os.path.splitext(path)[1]`. Coverage `files` per extension is summed over all runs' entries; no entry counts 0. Tracked count: `git ls-files` paths with that extension that are regular files (`os.lstat`, `stat.S_ISREG`) with size > 0.
- Header: `snyk: <t> touched, <u> untouched; ` + `", ".join(f"coverage {ext} {a}/{b}")`. `u` = total results over all runs minus `t`.
- Touched line: `touched: <level> <ruleId> <uri>:<startLine> — <message.text> [changed: <paths or none>]`, then ` [untracked uri: <uri>]` for each untracked decoded uri. `<uri>` is the decoded first-location uri. Missing field: `?`.
- Mismatch line: `snyk-scan: Snyk analysed <a> <ext> files but <b> non-empty ones are tracked; a file is hidden from the scan (changed <ext> files: <comma list or none>)`.
- Presence line: `snyk-scan: <path> has <m> results; .snyk-files says <n>`, plus ` (file unchanged by this PR: Snyk drift, a master-side change, or an effect of this PR's edits elsewhere)` when `<path>` is not changed. Sorted by path.
- Suppression line: `snyk-scan: <path> contains an inline Snyk suppression (deepcode ignore)` (literal built at runtime), in `git ls-files` order.
- Exit 1 only: last line `::error::snyk-scan: <t> finding(s) in files this PR changes; <m> coverage mismatch(es); <p> presence difference(s); <s> suppression(s)`.
- Exit 2: `snyk_file_touch: <reason>` on stderr; stdout empty.

---

### Task 1: Judge touch decision and failure modes

```yaml-task
id: 1
description: scripts/snyk_file_touch.py with input parsing, touch decision, header, touched lines and exit 0/1/2 (coverage, presence and suppression counts fixed at 0 until Task 2)
role: executor
model: sonnet
tdd: required
requirements: [R5, R6, R9]
acceptance:
  - cmd: 'env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE ../../.venv/bin/python3 -m unittest discover -s tests -p test_snyk_file_touch.py'
    exit_code: 0
    stderr_match: 'Ran [1-9][0-9]* tests?[\s\S]*OK'
  - cmd: '../../.venv/bin/pyright scripts/snyk_file_touch.py tests/test_snyk_file_touch.py'
    exit_code: 0
  - cmd: 'bash -c ''PATH="$PWD/../../.venv/bin:$PATH" make lint'''
    exit_code: 0
max_retries: 3
files_touched: [scripts/snyk_file_touch.py, tests/test_snyk_file_touch.py]
depends_on: []
```

**Interfaces — Produces** (Tasks 2-3 extend these; keep names):

- `class JudgeError(Exception)` — message is the exit-2 reason.
- `parse_manifest(text: str) -> dict[str, int]` — skips blank and `#` lines; a line not matching `^(\S+) ([0-9]+)$` or a repeated path raises `JudgeError`. (Used from Task 2; write it now with tests.)
- `judge(sarif: object, changed: set[str], tracked: list[str], manifest: dict[str, int], size_of: Callable[[str], int | None], read_text: Callable[[str], str]) -> tuple[list[str], int]` — pure; returns stdout lines and exit code 0/1; raises `JudgeError` for a SARIF that is not a dict with a non-empty `runs` list, or a run whose `results` is not a list or whose `properties.coverage` is not a list.
- `main(stdin: TextIO, run_git: Callable[[list[str]], bytes], read_manifest: Callable[[], str], size_of, read_text) -> int` — JSON decode error, `JudgeError`, a missing `.snyk-files` (`FileNotFoundError`) all print `snyk_file_touch: <reason>` to stderr and return 2. `run_git` raises `JudgeError` on non-zero exit. `if __name__ == "__main__": sys.exit(main(sys.stdin, <real defaults>))`.

**Touch rule (R6):** percent-decode (`urllib.parse.unquote`) the first location uri and every `codeFlows[*].threadFlows[*].locations[*].location.physicalLocation.artifactLocation.uri`. Touched if any decoded uri is in `changed`, or not in `tracked`, or the decoded location path contains whitespace (`any(c.isspace() ...)`).

**Tests (all inputs stubbed; no real git):** no touched result → exit 0; touched location; flow step in a second file only; added file; deleted file; rename listed under both paths; `%20`-style encoded uri; uri not tracked → `[untracked uri: …]`; whitespace path; result in a second run; missing fields print `?`; each exit-2 case: invalid JSON, `{}`, `{"runs": []}`, run without `results`, run without `properties.coverage`, missing `.snyk-files`, malformed line, repeated path, git non-zero. One test asserts the two argv lists are exactly the contract's, and that the source contains no `open(` with a `w`, `a` or `x` mode.

- [ ] Write tests, run, see them fail (exit 1 on import).
- [ ] Implement; run all three gates; commit via `caveman:caveman-commit`.

### Task 2: Coverage, presence and suppression checks; `.snyk-files`

```yaml-task
id: 2
description: Add the coverage, presence and suppression checks to judge() and create .snyk-files with the five bootstrap lines
role: executor
model: sonnet
tdd: required
requirements: [R7, R8, R16]
acceptance:
  - cmd: 'env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE ../../.venv/bin/python3 -m unittest discover -s tests -p test_snyk_file_touch.py -k test_real_tree_has_no_suppression'
    exit_code: 0
    stderr_match: 'Ran 1 test'
  - cmd: 'env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE ../../.venv/bin/python3 -m unittest discover -s tests -p test_snyk_file_touch.py'
    exit_code: 0
    stderr_match: 'Ran [1-9][0-9]* tests?[\s\S]*OK'
  - cmd: '../../.venv/bin/pyright scripts/snyk_file_touch.py tests/test_snyk_file_touch.py'
    exit_code: 0
  - cmd: 'bash -c ''PATH="$PWD/../../.venv/bin:$PATH" make lint'''
    exit_code: 0
  - cmd: 'grep -rlE "deepcode[[:space:]]+ignore" scripts tests'
    exit_code: 1
max_retries: 3
files_touched: [scripts/snyk_file_touch.py, tests/test_snyk_file_touch.py, .snyk-files]
depends_on: [1]
```

**`.snyk-files`** (root), exactly, after optional `#` comment lines naming the source (math#260 run-1 SARIF of master `d3ef01e`):

```text
scripts/mutation_gate_items.py 3
scripts/mutation_weakening.py 8
scripts/zeta_results.py 4
tests/test_mutation_weakening.py 1
tests/test_mutation_weakening_e2e.py 1
```

**Checks** (strings in the Judge contract): coverage per compared extension; presence = per-file count of results keyed by decoded first-location path, excluding results touched for an untracked or whitespace path, compared with the manifest over the union of paths (absent = 0); suppression = each tracked non-empty compared-extension file whose `read_text` matches the regex. Exit 1 when `t`, mismatches, presence differences or suppressions is non-zero; the `::error::` line last. `main` reads `.snyk-files` and file contents with `errors="replace"`.

**Tests:** mismatch in each direction (`a>b`, `a<b`) with and without a changed file of that extension; empty tracked file excluded; symlink excluded (`size_of` returns `None`); missing coverage entry = 0; extra `SUPPORTED` extension compared; presence equal, count up, count down, file appearing, file vanishing, each with and without the drift label; suppression in upper case, lower case and with a tab and extra spaces (text built as `"deep" + "code" + sep + "ignore"`); the `::error::` line's four counts; and a real-tree test named `test_real_tree_has_no_suppression`: real `git ls-files -z` (GIT_* stripped), real file reads, asserting 0 suppressions. Also assert the live `.snyk-files` parses and contains the five lines above.

- [ ] Red tests, implement, gates green, commit.

### Task 3: SARIF fixture replays

```yaml-task
id: 3
description: Commit the math#262 and d3ef01e SARIF fixtures plus the d3ef01e file list and replay them through judge()
role: executor
model: sonnet
tdd: required
requirements: [R10]
acceptance:
  - cmd: 'env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE ../../.venv/bin/python3 -m unittest discover -s tests -p test_snyk_file_touch.py -k test_replay_'
    exit_code: 0
    stderr_match: 'Ran 2 tests'
  - cmd: 'env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE ../../.venv/bin/python3 -m unittest discover -s tests -p test_snyk_file_touch.py'
    exit_code: 0
    stderr_match: 'Ran [1-9][0-9]* tests?[\s\S]*OK'
  - cmd: '../../.venv/bin/pyright tests/test_snyk_file_touch.py'
    exit_code: 0
  - cmd: 'bash -c ''PATH="$PWD/../../.venv/bin:$PATH" make lint'''
    exit_code: 0
max_retries: 3
files_touched: [tests/test_snyk_file_touch.py, tests/fixtures/snyk/sarif-262.json, tests/fixtures/snyk/sarif-d3ef01e.json, tests/fixtures/snyk/files-d3ef01e.tsv]
depends_on: [2]
```

The orchestrator places `sarif-262.json` (math#262, 16 results) and `sarif-d3ef01e.json` (math#260 run 1, 17 results) byte-for-byte before dispatch. The task generates the TSV:

```bash
git ls-tree -r -l d3ef01e | awk -F'\t' '{split($1,a," "); if (a[1] ~ /^100/) printf "%s\t%s\n", a[4], $2}' > tests/fixtures/snyk/files-d3ef01e.tsv
```

Two test methods, `test_replay_262` and `test_replay_d3ef01e`.

**Replay 262:** changed = `{"scripts/pip_audit_advisory.py"}`, tracked = every decoded uri in the SARIF; assert exactly one `touched:` line, starting `touched: warning python/CommandInjection scripts/pip_audit_advisory.py:147 `.

**Replay d3ef01e:** changed = `set()`, tracked and `size_of` from the TSV, manifest = the five bootstrap lines as a literal dict (not the live file, which may gain lines after V1), `read_text` returns `""`; assert the header contains `coverage .py 118/118, coverage .html 1/1`, `0 touched, 17 untouched`, no `snyk-scan:` line and exit 0.

- [ ] Red, implement, green, commit.

### Task 4: Workflow wiring

```yaml-task
id: 4
description: snyk-scan loses continue-on-error, joins auto-merge needs, scans to SARIF and runs the judge; workflow tests pin it
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R3, R4, R11]
acceptance:
  - cmd: 'env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE ../../.venv/bin/python3 -m unittest discover -s tests -p test_snyk_scan_workflow.py'
    exit_code: 0
    stderr_match: 'Ran [1-9][0-9]* tests?[\s\S]*OK'
  - cmd: 'env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE ../../.venv/bin/python3 -m unittest discover -s tests -p "test_*workflow*.py"'
    exit_code: 0
    stderr_match: 'OK'
  - cmd: 'env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE ../../.venv/bin/python3 -m unittest discover -s tests -p test_snyk_cli_pinned.py'
    exit_code: 0
  - cmd: '../../.venv/bin/pyright tests/test_snyk_scan_workflow.py tests/test_workflow_continue_on_error.py'
    exit_code: 0
  - cmd: 'bash -c ''PATH="$PWD/../../.venv/bin:$PATH" make lint'''
    exit_code: 0
max_retries: 3
files_touched: [.github/workflows/auto-merge.yml, tests/test_snyk_scan_workflow.py, tests/test_workflow_continue_on_error.py]
depends_on: [3]
```

In `auto-merge.yml`: delete `continue-on-error: true` from `snyk-scan`; checkout gets `with: fetch-depth: 2`; `Install Snyk CLI` untouched; `auto-merge` `needs: [secret-scan, bash-coverage, claude-md-budget, snyk-scan]`. Replace the scan step and add the judge:

```yaml
- name: Run Snyk Code scan
  id: scan
  env:
    SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}
  run: |
    set +e
    snyk code test --sarif-file-output="${RUNNER_TEMP}/snyk.sarif" > "${RUNNER_TEMP}/snyk.txt"
    rc=$?
    if [ "${rc}" -gt 1 ]; then
      echo "::error::snyk-scan: scanner error (exit ${rc})"
      cat "${RUNNER_TEMP}/snyk.txt"
      exit 1
    fi
    exit 0

- name: Judge findings against the files this PR changes
  if: ${{ !cancelled() && steps.scan.outcome == 'success' }}
  run: |
    set +e
    python3 -I scripts/snyk_file_touch.py < "${RUNNER_TEMP}/snyk.sarif" > "${RUNNER_TEMP}/judge.txt"
    rc=$?
    cat "${RUNNER_TEMP}/judge.txt"
    grep -v '^::error' "${RUNNER_TEMP}/judge.txt" >> "${GITHUB_STEP_SUMMARY}"
    exit "${rc}"
```

Add a short comment above the judge naming ADR-0049. `tests/test_workflow_continue_on_error.py`: remove the `snyk-scan` `ALLOWED` entry and its positive-control assertion (keep the `notify`/`dl` one). New `tests/test_snyk_scan_workflow.py` (`yaml.safe_load`) pins: `snyk-scan` in `needs`; no `continue-on-error` on the job or its steps; `fetch-depth` 2; `SNYK_TOKEN` in exactly one step's `env`, the one with `id: scan`; scan `run` contains `set +e`, the command with the stdout redirect, `-gt 1`, the `::error::` text and `exit 1`; judge `if` string exact, `set +e`, `python3 -I scripts/snyk_file_touch.py <`, `rc=$?`, `grep -v '^::error'`, `GITHUB_STEP_SUMMARY`, `exit "${rc}"`; and `git ls-files` (GIT_* stripped) lists no path whose basename is `.snyk` or `.dcignore`.

- [ ] Write the tests; run against the unchanged workflow and see them fail. Edit; gates green; commit.

### Task 5: Guard the judge and list

```yaml-task
id: 5
description: Add .snyk-files and scripts/snyk_file_touch.py to GATE_FILES with a test that an edit to each yields an uncleared gate item
role: executor
model: sonnet
tdd: required
requirements: [R12]
acceptance:
  - cmd: 'env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE ../../.venv/bin/python3 -m unittest discover -s tests -p test_mutation_gate_items.py -k test_snyk_judge_files_are_gate_items'
    exit_code: 0
    stderr_match: 'Ran [12] tests?[\s\S]*OK'
  - cmd: 'env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE ../../.venv/bin/python3 -m unittest discover -s tests -p test_mutation_gate_items.py'
    exit_code: 0
    stderr_match: 'OK'
  - cmd: '../../.venv/bin/pyright scripts/mutation_gate_items.py tests/test_mutation_gate_items.py'
    exit_code: 0
  - cmd: 'bash -c ''PATH="$PWD/../../.venv/bin:$PATH" make lint'''
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation_gate_items.py, tests/test_mutation_gate_items.py]
depends_on: [4]
```

Append `".snyk-files",` and `"scripts/snyk_file_touch.py",` to the `GATE_FILES` tuple (about line 78) with a one-line comment: the snyk-scan judge and its presence list (ADR-0049). Change nothing else in the file (N2). Test method(s) named `test_snyk_judge_files_are_gate_items` (one, or a pair with that prefix), modelled on `test_other_gate_file_has_no_hold_line`: in the fixture repo write each path, commit, `run_cli()`, assert exit 1 and `uncleared item: gate gate .snyk-files` (and `… scripts/snyk_file_touch.py`) in the text. Show the test red before the edit.

- [ ] Red, edit, green, commit.

**Orchestrator after Task 5:** run root `env PATH="$PWD/../../.venv/bin:$PATH" make test < /dev/null` once; it must exit 0.

### Task 6: ADR-0049, CLAUDE.md, Backlog row

```yaml-task
id: 6
description: Docs-only (ADR, CLAUDE.md prose, Backlog row; no behaviour change, so no TDD) recording the decision and rewriting the snyk-scan lines within the byte ceiling
role: executor
model: sonnet
tdd: not-applicable
requirements: [R13, R14, R15]
acceptance:
  - cmd: 'bash -c ''[ "$(wc -c < CLAUDE.md)" -le 30000 ]'''
    exit_code: 0
  - cmd: 'bash -c ''! grep -inE "snyk.*advisory|advisory.*snyk|snyk.*rust" CLAUDE.md'''
    exit_code: 0
  - cmd: 'bash -c ''grep -q "snyk_file_touch.py" CLAUDE.md && grep -q "ADR-0049" CLAUDE.md && grep -q "0049" docs/adr/README.md && ls docs/adr/0049-*.md'''
    exit_code: 0
  - cmd: 'grep -q "ADVISORY_CHECKS" docs/superpowers/README.md'
    exit_code: 0
max_retries: 2
files_touched: [docs/adr/0049-snyk-scan-blocks-on-changed-files.md, docs/adr/README.md, CLAUDE.md, docs/superpowers/README.md]
depends_on: [5]
```

**ADR-0049** (format of ADR-0048: Date 2026-11-28, Status Accepted, Context, Decision, Consequences, Related). Content from the spec's Problem, Design, Rejected alternatives and Known limits: the decision; evidence from math#250 and math#259 to #262; the three refuted judges (identity UUID, fingerprint `"1"`, flow-touch); the red procedure (spec § When `snyk-scan` is red, verbatim bullets); the Known limits; a `## Quota` line saying V4's reading is recorded after merge. Row in `docs/adr/README.md` after 0048.

**CLAUDE.md** (29993 bytes; measured result of these three edits is 29984):

- Line 160: delete the text `, then snyk-scan (advisory, not gated)`.
- Line 203: replace the first block below with the second.
- Line 217 (the `**snyk-scan**` paragraph): replace it with the third block.

```text
and fails on any non-advisory failure (`snyk-scan` is advisory; `secret-scan` and `auto-merge` are self-checks)
```

```text
and fails on any failure except `snyk-scan`; `secret-scan` and `auto-merge` are self-checks
```

```text
**snyk-scan** (`needs` of `auto-merge`, ADR-0049, `SNYK_TOKEN`): `scripts/snyk_file_touch.py` fails it on a finding in a file the PR changes, a coverage mismatch, a `.snyk-files` presence difference or an inline suppression.
```

**Backlog** (`docs/superpowers/README.md` § P3): append this row to the P3 table:

```text
| snyk-advisory-entry | `scripts/ci-gate.sh` still lists `snyk-scan` in `ADVISORY_CHECKS`, moot since ADR-0049 made it a `needs` of `auto-merge`; remove the entry and its `tests/scripts/ci_gate.bats` cases. |
```

- [ ] Edit, run gates, commit.

## Orchestrator steps

1. Before Task 1: `git worktree add .worktrees/snyk-file-touch -b ci/snyk-file-touch origin/master`.
2. Before Task 3: copy the session's `sarif4/snyk.sarif` to `tests/fixtures/snyk/sarif-262.json` and `sarif1/snyk.sarif` to `tests/fixtures/snyk/sarif-d3ef01e.json`; check `sha256sum` equal to source.
3. After Task 5: root `make test` (above). After Task 6: Phase 3 (`finishing-a-development-branch`).
4. Push; `gh pr create --draft`. Watch `gh pr checks <n> --watch`.
5. **V1:** read the judge step's log. Expect exactly 3 `touched:` lines for `scripts/mutation_gate_items.py` plus any in new files; `coverage .py <a>/<a>` (121 if exactly three new `.py` files), `.html 1/1`; no suppression; presence differences only in new files; `snyk-scan` red, `auto-merge` skipped, `mutation-gate-items` red. For each new file with results, add `<path> <count>` to `.snyk-files` (R16) in a new commit and push. Any other line: stop, do not merge, amend the spec.
6. When V1 holds and no open PR carries `gate-hold`: `gh pr ready <n>`; the operator admin-merges.
7. After merge: V2 (throwaway draft PR, two pushes per the spec), V3 (next unrelated PR), V4 (operator reads quota; record in ADR-0049, docs-only to master). Mark this plan Done in `docs/superpowers/README.md`; clean up worktrees and branches.

## Non-goal check

Reviewer (Opus, fresh context, plan and N list only), 2026-11-28: 5 CLEAR, 0 CONFLICT, 0 UNCLEAR. No plan revision or amendment needed.

- N1 CLEAR: no task edits `scripts/ci-gate.sh`, `tests/scripts/ci_gate.bats` or `.github/required-status-checks`; the `ADVISORY_CHECKS` removal is only a Backlog row.
- N2 CLEAR: Task 5's only edit to `scripts/mutation_gate_items.py` is the two `GATE_FILES` entries and their one-line comment.
- N3 CLEAR: no `.snyk`, `.dcignore` or `snyk ignore`; the suppression phrase is built at runtime.
- N4 CLEAR: stdlib-only judge run as `python3 -I`, no `setup-python`; PyYAML in tests only.
- N5 CLEAR: one scan; `startLine` appears only in printed output, never in the touch decision.
