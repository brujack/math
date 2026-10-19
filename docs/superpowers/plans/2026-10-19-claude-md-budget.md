# CLAUDE.md Budget Implementation Plan

spec: docs/superpowers/specs/2026-10-19-claude-md-budget-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** math root `CLAUDE.md` at most 30,000 bytes, one line per rule, detail in ai-config knowledge files, with a ceiling enforced on every PR and on pushes that change `CLAUDE.md`.

**Architecture:** `scripts/claude_md_budget.py` is the checker; `scripts/pre-push` runs it from the pushed commit inside its ref loop; a `claude-md-budget` job in `auto-merge.yml`'s `needs:` runs it on every PR. Relocated text goes byte-identical to `ai-config/docs/knowledge/math-*.md`.

**Tech Stack:** Python 3 stdlib, unittest, bash, bats, GitHub Actions.

## Global Constraints

- math default branch `master`; worktree `/home/bruce/git-repos/personal/math-cmb`, branch `feat/claude-md-budget`. ai-config knowledge in `/home/bruce/git-repos/personal/ai-config-mathkn`, branch `docs/math-knowledge`, pushed direct to ai-config master by the orchestrator.
- `CEILING = 30_000`; checker reads only `git show <rev>:CLAUDE.md`; absence via `git ls-tree --full-tree`; exit 1 over (message names size, ceiling and `docs/adr/0028-claude-md-size-ceiling.md`), 0 within or absent, 2 git failure; no flag, env var or trailer changes it.
- Spec Design 6 rules stay full one-line rules (R11); templating of per-sub-project blocks is allowed (verified) only as a pointer-bearing line: each original per-sub-project block is relocated byte-identical to the knowledge files (it is absent from the new file, so relocation_check covers it), and the templated line states every value that differs per sub-project.
- Before any test or git command in a fixture: `unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE`.
- Read `~/.claude/standards/python.md` before Python edits; root suite `python3 -m unittest discover -s tests -p 'test_*.py'`; `make lint`; `pyright`.
- Subagents sharing a worktree do not commit; the orchestrator commits by exact path.

## Verification (session level)

- R1: `wc -c < CLAUDE.md` ≤ 30000; `python3 scripts/claude_md_budget.py HEAD` exit 0.
- V4 relocation check with non-zero counts; V2 rule-by-rule review; V5 operator read; draft PR until both.
- V7 `claude-md-budget` job log shows the "changes CLAUDE.md" branch and size; V3 `/context` after merge; V6 `merge-base --is-ancestor` on `claude`, `workstation`, `studio`.

---

### Task 1: Compress CLAUDE.md and relocate

```yaml-task
id: 1
description: One-line-per-rule root CLAUDE.md with verbatim relocation to ai-config math knowledge, convention line, AGENTS.md parity and the three comment retargets
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'test "$(wc -c < CLAUDE.md)" -le 30000'
    exit_code: 0
  - cmd: 'python3 /tmp/claude-1000/-home-bruce-git-repos-personal-ai-config/679cf0fc-4125-445f-ba6c-e91a2c2ada7a/scratchpad/math-reloc/relocation_check.py'
    exit_code: 0
  - cmd: 'cd /home/bruce/git-repos/personal/ai-config-mathkn && python3 .claude/scripts/validate_knowledge.py docs/knowledge'
    exit_code: 0
  - cmd: 'python3 -m unittest discover -s tests -p "test_*.py"'
    exit_code: 0
max_retries: 3
files_touched:
  - CLAUDE.md
  - AGENTS.md
  - tests/scripts/makefile.bats
  - tests/test_root_pyright_scope.py
  - scripts/run-bash-coverage.sh
  - /home/bruce/git-repos/personal/ai-config-mathkn/docs/knowledge/
  - /tmp/claude-1000/-home-bruce-git-repos-personal-ai-config/679cf0fc-4125-445f-ba6c-e91a2c2ada7a/scratchpad/math-reloc/relocation_check.py
depends_on: []
requirements: [R1, R2, R3, R4, R10, R11, R12]
```

TDD waiver: prose relocation; relocation check (written first) and byte gate are the tests.

- Start from the dry run at `scratchpad/math-dryrun/CLAUDE.md` as a guide; rebuild from `origin/master:CLAUDE.md`. Comment retargets change only the cited comment lines.
- relocation_check.py: every base block absent from the new file is byte-identical in the knowledge files; every pointer resolves to exactly one `###` heading; counts non-zero.

### Task 2: Budget checker

```yaml-task
id: 2
description: scripts/claude_md_budget.py with unittest
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: 'python3 -m unittest tests.test_claude_md_budget -v'
    exit_code: 0
  - cmd: make lint
    exit_code: 0
  - cmd: pyright
    exit_code: 0
max_retries: 3
files_touched:
  - scripts/claude_md_budget.py
  - tests/test_claude_md_budget.py
depends_on: []
requirements: [R5]
```

- Port `git -C /home/bruce/git-repos/personal/terraform_ansible show origin/master:scripts/claude_md_budget.py` and its tests; ceiling 30,000, ADR path per Global Constraints.

### Task 3: Pre-push integration

```yaml-task
id: 3
description: scripts/pre-push runs the checker in its ref loop with a git diff --quiet change test, refusing before test dispatch and early exits
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: 'bats tests/scripts/pre_push.bats tests/scripts/pre_push_budget.bats < /dev/null'
    exit_code: 0
  - cmd: 'shellcheck --severity=warning scripts/pre-push tests/scripts/pre_push_budget.bats'
    exit_code: 0
max_retries: 3
files_touched:
  - scripts/pre-push
  - tests/scripts/pre_push.bats
  - tests/scripts/pre_push_budget.bats
depends_on: [2]
requirements: [R6, R8]
```

- Per spec Design 5 and R6/R8: new real-git cases in `pre_push_budget.bats` with a stub `make` only (never `tests/mocks/` on PATH); tighten the existing merge-base test in `pre_push.bats` to assert the range use specifically.

### Task 4: CI job

```yaml-task
id: 4
description: auto-merge.yml claude-md-budget job in auto-merge needs, fail on change over, warn otherwise
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'python3 -c "import yaml; yaml.safe_load(open(\".github/workflows/auto-merge.yml\"))"'
    exit_code: 0
  - cmd: 'python3 -m unittest tests.test_automerge_bot_hold -v'
    exit_code: 0
  - cmd: 'grep -q "claude_md_budget.py HEAD" .github/workflows/auto-merge.yml'
    exit_code: 0
max_retries: 3
files_touched:
  - .github/workflows/auto-merge.yml
depends_on: [2]
requirements: [R7]
```

TDD waiver: workflow YAML; the orchestrator simulates the step under `bash -eo pipefail`; V7 proves it on the PR.

### Task 5: ADR-0028

```yaml-task
id: 5
description: ADR-0028 and README row (docs-only; tdd not-applicable)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'grep -q "30,000" docs/adr/0028-claude-md-size-ceiling.md && grep -q "0028" docs/adr/README.md'
    exit_code: 0
max_retries: 2
files_touched:
  - docs/adr/0028-claude-md-size-ceiling.md
  - docs/adr/README.md
depends_on: []
requirements: [R9]
```

## Orchestrator steps

- [ ] Worktrees; Tasks 1, 2, 5 in parallel (no commits), then 3 and 4; commit each by exact path.
- [ ] Push ai-config knowledge to master; re-run relocation check.
- [ ] `make test` in the worktree; simulate the CI step; push; `gh pr create --draft`.
- [ ] Phase 3 gates; V2; V5; `gh pr ready`; watch CI.
- [ ] After merge: V3, V6, plan Done, notify math session.

## Non-goal check

Reviewer: one fresh Opus subagent with `nongoal-check.md`, 2026-10-19. 3 CLEAR, 1 UNCLEAR, 0 CONFLICT.

- **N1** UNCLEAR: "templating of per-sub-project blocks is allowed (verified)." Resolution, plan text before: that sentence; after: templating allowed only as a pointer-bearing line, each original per-sub-project block relocated byte-identical (covered by relocation_check as an absent block), and the templated line states every per-sub-project value.
- **N3** CLEAR, conditional on Task 1's three extra files being spec Design 8's three comment lines: they are (`tests/scripts/makefile.bats:96`, `tests/test_root_pyright_scope.py:10`, `scripts/run-bash-coverage.sh:85`).
- **N2, N4** CLEAR.
