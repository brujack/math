# Items Gate Fresh Base Implementation Plan

spec: docs/superpowers/specs/2026-11-27-items-gate-fresh-base-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The `mutation-gate-items` check always runs master's current gate script, and the items report tells the operator how to hold open PRs across an items-gate change.

**Architecture:** The workflow checks out `base.ref` and passes `git rev-parse HEAD` as BASE. `run()` in `scripts/mutation_gate_items.py` appends one `operator:` line when an item's path is an items-gate file. Docs record the `gate-hold` procedure in ADR-0048 and the agent rule in root `CLAUDE.md`.

**Tech Stack:** GitHub Actions YAML, Python 3.14 (`unittest`, `ast`), ruff 0.17.4, pyright 1.1.411, actionlint 1.7.12.

## Global Constraints

- `scripts/mutation-gate-items.sh`, `auto-merge.yml` and `scripts/ci-gate.sh` are unchanged; no new workflow file (N1, N3).
- `scripts/mutation_gate_items.py` changes only in the text `run()` returns; item computation is unchanged (N1).
- Branch protection is unchanged (N2).
- Root `CLAUDE.md` stays at or under 30,000 bytes; today 29,996.
- Work happens in worktree `.worktrees/items-fresh-base` on branch `ci/items-fresh-base`; never in the main checkout.
- The root suite runs longer than the Bash tool's 600 s cap, so task gates are scoped; the orchestrator runs root `make test` once after Task 3, in the worktree, with `.venv` activated (ruff, pyright).

## Verification

- Session gate: root `make test` (lint, bats, `make test-python` incl. root pyright) exits 0 on the branch head.
- PR: `mutation-gate-items` is red by design (gate files edited), listing `scripts/mutation_gate_items.py` and `.github/workflows/mutation-gate-items.yml`; every other required check is green. The operator admin-merges.
- Post-merge V1: draft throwaway PR, direct docs commit to master, confirm the API `base.sha` is still the old one, close and reopen; the `reopened` items run's line after `git log -1 --format=%H` equals master's tip and the run passes (smoke test if the payload was refreshed). V2: `gh label create gate-hold` if `gh label list --search gate-hold` is empty.
- Edge cases: an items-gate change lists the reminder once and before the operator line; a non-items gate file (`mutation-pr.yml`) and a non-gate item do not; no items stays green with the unchanged text.

---

### Task 1: Items workflow checks out base.ref

```yaml-task
id: 1
description: Check out base.ref and pass git rev-parse HEAD as BASE in mutation-gate-items.yml, with workflow tests
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R3]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_gate_items_workflow
    exit_code: 0
  - cmd: make lint-workflows
    exit_code: 0
  - cmd: 'bash -c "! grep -n base.sha .github/workflows/mutation-gate-items.yml"'
    exit_code: 0
max_retries: 3
files_touched: [.github/workflows/mutation-gate-items.yml, tests/test_mutation_gate_items_workflow.py]
depends_on: []
```

**Files:** `.github/workflows/mutation-gate-items.yml`, `tests/test_mutation_gate_items_workflow.py`.

- [ ] RED: in the test file, change `EXPECTED_RUNS`' gate entry to `'scripts/mutation-gate-items.sh "$(git rev-parse HEAD)" "${HEAD_SHA}"'`; rename `test_checkout_is_base_sha_without_credentials` to `test_checkout_is_base_ref_without_credentials` asserting `with_["ref"] == "${{ github.event.pull_request.base.ref }}"`; in `test_run_step_invokes_gate_with_env_values` assert the new run line, `env["HEAD_SHA"]` unchanged and `self.assertNotIn("BASE_SHA", env)`; add `test_no_base_sha_anywhere` asserting `"base.sha" not in load()[0]`. Run `python3 -m unittest tests.test_mutation_gate_items_workflow`: expect failures.
- [ ] GREEN: checkout `ref: ${{ github.event.pull_request.base.ref }}` (keep `fetch-depth: 0`, `persist-credentials: false`, rename the step "Check out the base branch tip"); gate step `run: scripts/mutation-gate-items.sh "$(git rev-parse HEAD)" "${HEAD_SHA}"`, `env` only `HEAD_SHA`. Update the header comment to say the base branch's tip is checked out because the payload's `base.sha` can be stale (math#238). No `if:` anywhere.
- [ ] Run the acceptance commands; commit (`caveman:caveman-commit`).

**Interfaces:** Produces nothing other tasks consume.

### Task 2: Items-gate reminder line in run()

```yaml-task
id: 2
description: run() appends the operator gate-hold line when an item's path is an items-gate file, with tests
role: executor
model: sonnet
tdd: required
requirements: [R4, R5]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_gate_items
    exit_code: 0
  - cmd: ruff check scripts/mutation_gate_items.py tests/test_mutation_gate_items.py
    exit_code: 0
  - cmd: ruff format --check scripts/mutation_gate_items.py tests/test_mutation_gate_items.py
    exit_code: 0
  - cmd: pyright scripts/mutation_gate_items.py tests/test_mutation_gate_items.py
    exit_code: 0
max_retries: 3
files_touched: [scripts/mutation_gate_items.py, tests/test_mutation_gate_items.py]
depends_on: []
```

**Files:** `scripts/mutation_gate_items.py`, `tests/test_mutation_gate_items.py`.

- [ ] RED: add class `ItemsGateReminderTest(ItemsCase)` in the test file:
  - for each of `scripts/mutation_gate_items.py`, `scripts/mutation-gate-items.sh`, `.github/workflows/mutation-gate-items.yml`, `scripts/cosmic_ray_prune.py` (subTest per path): write the path with `"x\n"`, commit, `code, text = self.run_cli()`; assert `code == 1`, `text.count(mgi.ITEMS_GATE_LINE) == 1`, and `lines.index(mgi.ITEMS_GATE_LINE) == len(lines) - 2` with `lines[-1] == mgi.OPERATOR_LINE` and `lines[-3].startswith("uncleared item: ")`;
  - `.github/workflows/mutation-pr.yml` edited alone (e.g. `MUTATION_PR.format(sha=SHA_OLD, version="v2")` or any byte change): `code == 1`, `"uncleared item: gate gate .github/workflows/mutation-pr.yml"` in text, `mgi.ITEMS_GATE_LINE not in text`;
  - non-gate item (`RunTest.change_timeout`-style edit of `sq/cosmic-ray.toml` timeout): `code == 1`, `"uncleared item: sq python-config"` in text, line absent;
  - no items (`README`): `(0, "mutation-gate-items: no uncleared items")`;
  - `ast` drift check: parse `ROOT / "scripts/mutation_gate_items.py"`; every `Call` whose func is `Name(id="_load_sibling")` has exactly one `Constant` `str` arg; `set(mgi.ITEMS_GATE_PATHS) == {"scripts/mutation_gate_items.py", "scripts/mutation-gate-items.sh", ".github/workflows/mutation-gate-items.yml"} | {f"scripts/{n}.py" for n in names}`.
    Run: expect `AttributeError` on `ITEMS_GATE_LINE`.
- [ ] GREEN: add module constants near `OPERATOR_LINE`:
  - `ITEMS_GATE_PATHS = ("scripts/mutation_gate_items.py", "scripts/mutation-gate-items.sh", ".github/workflows/mutation-gate-items.yml", "scripts/cosmic_ray_prune.py")` with a comment that it is the script, its wrapper, its workflow and every `_load_sibling` target;
  - `ITEMS_GATE_LINE = "operator: this PR changes the items gate; before the admin merge, run gh pr ready --undo <n> and then gh pr edit <n> --add-label gate-hold for every other open non-draft PR; after it, run gh pr ready <n> and gh pr edit <n> --remove-label gate-hold for each PR in gh pr list --label gate-hold."` (exact; implicit string concatenation is fine);
  - in `run()`: `extra = [ITEMS_GATE_LINE] if any(i.target == "gate" and i.key[0] in ITEMS_GATE_PATHS for i in items) else []`; return `1, "\n".join([*lines, *extra, OPERATOR_LINE])`. Nothing else changes.
- [ ] Run the acceptance commands; commit.

**Interfaces:** Produces `mgi.ITEMS_GATE_LINE`, `mgi.ITEMS_GATE_PATHS` (tuple of str).

### Task 3: CLAUDE.md, ADR-0048 and index docs

```yaml-task
id: 3
description: Docs-only (no behaviour); CLAUDE.md items line, ADR-0048 dated line, Backlog row removal
role: executor
model: sonnet
tdd: not-applicable
requirements: [R6, R7]
acceptance:
  - cmd: 'bash -c "[ $(wc -c < CLAUDE.md) -le 30000 ]"'
    exit_code: 0
  - cmd: 'grep -c "script from \`base.ref\`" CLAUDE.md'
    exit_code: 0
    stdout_match: '^1$'
  - cmd: 'grep -c "gate-hold" docs/adr/0048-pr-mutation-gates-see-test-weakening.md'
    exit_code: 0
  - cmd: 'bash -c "! grep -n \"stale \`base.sha\`\" docs/superpowers/README.md"'
    exit_code: 0
max_retries: 3
files_touched: [CLAUDE.md, docs/adr/0048-pr-mutation-gates-see-test-weakening.md, docs/superpowers/README.md]
depends_on: [1, 2]
```

**Files:** `CLAUDE.md`, `docs/adr/0048-pr-mutation-gates-see-test-weakening.md`, `docs/superpowers/README.md`.

Byte budget: the current line is 413 bytes with newline, headroom 4. Replace the whole line beginning `` `mutation-gate-items.yml` (`pull_request_target`, never skipped) `` with exactly this 410-byte line (measured; drops the repro clause, already in ADR-0048 `## Repro commands`):

```
`mutation-gate-items.yml` (`pull_request_target`, never skipped, script from `base.ref`) lists equivalents, exclusions, hidden code, gate-file edits; any item is red (`uncleared item: ...`), as is `weakened:` or `base suite unjudgeable` in `mutation-pr`; only the operator admin-merges; agents never `gh pr ready` while a PR has the `gate-hold` label. → docs/adr/0048-pr-mutation-gates-see-test-weakening.md
```

- [ ] ADR-0048: after the existing `Status 2026-11-27:` line under item 6, add a line `   Fresh base 2026-11-27:` stating: the items job checks out `base.ref` and passes `git rev-parse HEAD` as BASE, because math#238's `reopened` payload carried a base 53 commits behind master (run 46053939365, exit 127) while an `edited` payload on the same head carried master's tip (run 46055972031); around an items-gate admin merge (script, wrapper, workflow, `cosmic_ray_prune.py`) the operator drafts then labels `gate-hold` every other open non-draft PR before the merge, and readies then unlabels each `gate-hold` PR after it; agents never mark a PR ready while any PR carries `gate-hold`; a tightening of other gate files (e.g. `mutation-pr.yml`) is not re-judged; repro under `## Repro commands`. Also add to `## Related`: `docs/superpowers/specs/2026-11-27-items-gate-fresh-base-design.md`.
- [ ] `docs/superpowers/README.md`: delete the P1 row "mutation gate: items job runs the gate script from the PR's stale `base.sha`" and restore the P1 table's `| —       | No open P1 items. |` row. Leave the plan-index row as is (already `In progress`).
- [ ] Run acceptance; commit.

## Orchestrator steps

1. `git worktree add .worktrees/items-fresh-base -b ci/items-fresh-base origin/master`; `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt ruff==0.17.4` inside it (cosmic-ray, pyright and pyyaml come from the file; ruff does not, and pre-push needs it).
2. Dispatch Tasks 1 and 2 (disjoint files, no dependency), then Task 3.
3. Root `make test < /dev/null` in the worktree (venv active), backgrounded; must exit 0.
4. Phase 3 (`finishing-a-development-branch`), push, `gh pr create --draft`; `gh pr checks --watch`; expect only `mutation-gate-items` (and advisory `snyk-scan`) red; `gh pr ready` only after Phase 3; the operator admin-merges.
5. Post-merge: V1, V2, ai-config knowledge note (message ai-config first), cleanup, plan Done.

## Non-goal check

Reviewer verdicts (fresh subagent, `nongoal-check.md`):

- N1: CLEAR. Task 1 changes only the arguments passed to `scripts/mutation-gate-items.sh`; Task 2's two constants feed only the text `run()` returns. Resolution: none needed.
- N2: CLEAR. V2's label creation and the admin merge do not change branch protection. Resolution: none needed.
- N3: CLEAR. `mutation-gate-items.yml` is modified, not new; `auto-merge.yml` and `ci-gate.sh` are untouched. Resolution: none needed.
