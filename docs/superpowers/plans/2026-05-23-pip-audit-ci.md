# pip-audit CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `pip-audit` as an advisory security step to all 9 Python CI workflows.

**Architecture:** Append `pip-audit` to the existing `pip install` line in each workflow, then add a `Run pip-audit` step with `continue-on-error: true` after the test step. No requirements files, no new jobs — one new step per workflow.

**Tech Stack:** pip-audit (PyPA), GitHub Actions

---

## Files Modified

- `.github/workflows/amicable-py.yml` — pip install line 20, new step after line 21
- `.github/workflows/collatz-py.yml` — pip install line 30, new step after line 33
- `.github/workflows/fib-py.yml` — pip install line 30, new step after line 33
- `.github/workflows/perfect-numbers-py.yml` — pip install line 30, new step after line 33
- `.github/workflows/sq-py.yml` — pip install line 30, new step after line 33
- `.github/workflows/e-py.yml` — pip install line 33, new step after line 36
- `.github/workflows/pi-py.yml` — pip install line 33, new step after line 36
- `.github/workflows/factorial-py.yml` — pip install line 33, new step after line 36
- `.github/workflows/scripts.yml` — pip install line 21, new step after line 25
- `CLAUDE.md` — document pip-audit as required standard for new Python sub-projects

---

### Task 1: Worktree setup

- [ ] **Create worktree on a feature branch**

```bash
git -C ~/git-repos/personal/math worktree add .worktrees/feat/pip-audit-ci -b feat/pip-audit-ci
```

All subsequent edits happen in `/Users/bruce/git-repos/personal/math/.worktrees/feat/pip-audit-ci/`.

---

### Task 2: Edit simple-deps workflows (amicable, collatz, fib, perfect-numbers, sq)

These five workflows use `pip install ruff coverage hypothesis pyright`. Same change in each.

**Files:**

- Modify: `.github/workflows/amicable-py.yml`
- Modify: `.github/workflows/collatz-py.yml`
- Modify: `.github/workflows/fib-py.yml`
- Modify: `.github/workflows/perfect-numbers-py.yml`
- Modify: `.github/workflows/sq-py.yml`

- [ ] **Edit amicable-py.yml**

`amicable-py.yml` uses compact step syntax (no `name:` fields). Read the file first, then:

Change line 20:

```yaml
- run: pip install ruff coverage hypothesis pyright
```

to:

```yaml
- run: pip install ruff coverage hypothesis pyright pip-audit
```

Add after the `- run: make test` / `working-directory: amicable` block and before the coverage badge step:

```yaml
- name: Run pip-audit
  run: pip-audit
  continue-on-error: true
```

- [ ] **Edit collatz-py.yml, fib-py.yml, perfect-numbers-py.yml, sq-py.yml**

All four follow the same pattern (`defaults.run.working-directory` set to the sub-project). For each:

Change the pip install step from:

```yaml
run: pip install ruff coverage hypothesis pyright
```

to:

```yaml
run: pip install ruff coverage hypothesis pyright pip-audit
```

Add after `run: make test` and before `- name: Check coverage (>=90%)`:

```yaml
- name: Run pip-audit
  run: pip-audit
  continue-on-error: true
```

- [ ] **Commit**

```bash
cd /Users/bruce/git-repos/personal/math/.worktrees/feat/pip-audit-ci
git add .github/workflows/amicable-py.yml \
        .github/workflows/collatz-py.yml \
        .github/workflows/fib-py.yml \
        .github/workflows/perfect-numbers-py.yml \
        .github/workflows/sq-py.yml
git commit -m "ci(pip-audit): add advisory pip-audit step to 5 simple-deps workflows"
```

---

### Task 3: Edit complex-deps workflows (e, pi, factorial)

These three workflows use `pip install mpmath gmpy2 coverage ruff hypothesis pyright`.

**Files:**

- Modify: `.github/workflows/e-py.yml`
- Modify: `.github/workflows/pi-py.yml`
- Modify: `.github/workflows/factorial-py.yml`

- [ ] **Edit e-py.yml, pi-py.yml, factorial-py.yml**

For each, change the pip install step from:

```yaml
run: pip install mpmath gmpy2 coverage ruff hypothesis pyright
```

to:

```yaml
run: pip install mpmath gmpy2 coverage ruff hypothesis pyright pip-audit
```

Add after `run: make test` and before `- name: Check coverage (>=90%)` (or before `- name: Generate test metrics` for factorial):

```yaml
- name: Run pip-audit
  run: pip-audit
  continue-on-error: true
```

For factorial specifically, the order is: `Run tests` → `Run pyright` → [insert here] → `Generate test metrics`. Insert the `Run pip-audit` step after `Run pyright`.

- [ ] **Commit**

```bash
git add .github/workflows/e-py.yml \
        .github/workflows/pi-py.yml \
        .github/workflows/factorial-py.yml
git commit -m "ci(pip-audit): add advisory pip-audit step to e, pi, factorial workflows"
```

---

### Task 4: Edit scripts.yml

`scripts.yml` has no test framework for Python — only bats tests and pyright. The pip-audit step goes after pyright.

**Files:**

- Modify: `.github/workflows/scripts.yml`

- [ ] **Edit scripts.yml**

Change line 21:

```yaml
run: pip install pyright
```

to:

```yaml
run: pip install pyright pip-audit
```

Add after the `Run pyright` step (the last step in the file):

```yaml
- name: Run pip-audit
  run: pip-audit
  working-directory: scripts
  continue-on-error: true
```

- [ ] **Commit**

```bash
git add .github/workflows/scripts.yml
git commit -m "ci(pip-audit): add advisory pip-audit step to scripts workflow"
```

---

### Task 5: Update CLAUDE.md

**Files:**

- Modify: `CLAUDE.md`

- [ ] **Add pip-audit to the type checking section in CLAUDE.md**

In the `### Type checking (Python — pyright)` section, after the table and before the closing paragraph, add:

````markdown
### Security audit (Python — pip-audit)

Every Python sub-project CI workflow must include `pip-audit` in the pip install step and a `Run pip-audit` step with `continue-on-error: true` after the test step.

`pip-audit` scans the installed Python environment for known CVEs. It is advisory — findings surface in CI logs but do not block auto-merge. The step is identical across all sub-projects:

```yaml
- name: Run pip-audit
  run: pip-audit
  continue-on-error: true
```
````

When adding a new Python sub-project, copy this step from any existing workflow.

````

- [ ] **Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): document pip-audit as required standard for Python sub-projects"
````

---

### Task 6: Push, open PR, monitor CI

- [ ] **Push branch from worktree**

```bash
git -C /Users/bruce/git-repos/personal/math/.worktrees/feat/pip-audit-ci push origin feat/pip-audit-ci
```

- [ ] **Open PR**

```bash
cd /Users/bruce/git-repos/personal/math/.worktrees/feat/pip-audit-ci
gh pr create \
  --title "feat(ci): add pip-audit advisory security step to all Python workflows" \
  --body "Adds pip-audit as an advisory step to all 9 Python CI workflows. Non-blocking (continue-on-error: true). Fills the Python security audit gap — Rust already has cargo deny/audit. Documents as required standard for new Python sub-projects in CLAUDE.md."
```

- [ ] **Watch CI to completion**

```bash
gh pr checks <PR_NUMBER> --watch
```

Expected: all Test jobs pass. pip-audit step visible in each job log. `auto-merge` triggers and squash-merges.

If any `Test *.py` job fails on the `Run pip-audit` step (not just advisory warning): the `continue-on-error: true` should prevent this — investigate if seen.

---

### Task 7: Post-merge cleanup and docs update

**Do this directly on master after the PR merges — not inside the worktree.**

- [ ] **Remove worktree and clean up branches**

```bash
git -C ~/git-repos/personal/math worktree remove /Users/bruce/git-repos/personal/math/.worktrees/feat/pip-audit-ci
git -C ~/git-repos/personal/math branch -D feat/pip-audit-ci
git -C ~/git-repos/personal/math push origin --delete feat/pip-audit-ci
git -C ~/git-repos/personal/math fetch --prune
git -C ~/git-repos/personal/math pull
```

- [ ] **Update plan index on master**

In `docs/superpowers/README.md`, add a row to the All Plans table:

```markdown
| 2026-05-23 | [pip-audit-ci](plans/2026-05-23-pip-audit-ci.md) | [spec](specs/2026-05-23-pip-audit-ci-design.md) | Done |
```

Add `> **Status: DONE**` banner at the top of `docs/superpowers/plans/2026-05-23-pip-audit-ci.md`.

Also remove the `pip-audit in CI` row from the Backlog table in `docs/superpowers/README.md` in `ai-config`.

- [ ] **Commit**

```bash
cd ~/git-repos/personal/math
git add docs/superpowers/README.md docs/superpowers/plans/2026-05-23-pip-audit-ci.md
git commit -m "chore(docs): mark pip-audit-ci plan done"
git push
```
