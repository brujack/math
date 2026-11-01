# Shared Push-Content Gate — PR8 (math) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** ai-config `docs/superpowers/specs/2026-10-30-shared-push-content-gate-design.md`, which is cross-repo, so this plan has no `spec:` line. R13 (amended 2026-10-31) is copied below. Spec alignment records SKIP for this PR (operator decision, 2026-10-31).

**Goal:** `scripts/pre-push` loads ai-config's shared push-content gate for every push to master or main. The existing bats suite proves the wiring and makes no network call.

**Architecture:**

- **Wiring block.** The canonical block goes into `scripts/pre-push` byte for byte, from ai-config `origin/master:docs/templates/pre-push-wiring`. It sits after the hook's setup (`REPO_ROOT`, symlink resolution to `HOOK_DIR`, the flag initialisers) and before `check_claude_md_budget` and the stdin loop at line 110.
- **Sourcing.** The hook has no sourcing path, so "runs only when executed" holds by construction.
- **Loop.** The loop at line 110 is wrapped in `if [[ -n "${_pcg_refs}" ]]` and reads `done <<< "${_pcg_refs}"`.
- **Shebang.** Line 1 becomes `#!/usr/bin/env -S bash -p`.
- **Harness.** It already exists:
  - `tests/scripts/pre_push.bats` and `tests/scripts/pre_push_budget.bats` use PATH-injected mocks from `tests/mocks/`, loaded by `load_mocks`: `git`, `make` and `gh` among them.
  - Local runs: `make test-hooks`. CI runs `bats --recursive tests/` in `scripts.yml`.
  - The hook's own push path runs root `make test` when `scripts/` or `tests/` changes.
  - So there is no Makefile or CI change.
- **The `gh` mock.** It exits 0 by default and prints `MOCK_GH_OUTPUT` (default empty). The wiring rejects an empty token, so today it refuses before reaching `/usr/bin/curl`, but only by accident. Every new wiring test sets `MOCK_GH_EXIT_AUTH_TOKEN=1` explicitly. One test asserts that no `gh` call other than `auth token` happens. No existing test pushes `main` or `master`, so no existing test reaches the gate.

**Tech Stack:** bash, bats, the repo's mock harness.

## Global Constraints

- **R13 (amended 2026-10-31).** The repo has the wiring block in its tracked pre-push script, byte-identical to ai-config's `docs/templates/pre-push-wiring` between its markers.
  - The block runs only when the script is executed, not when it is sourced.
  - It sits after any setup that must come before reading stdin, and before the script's first read of stdin.
  - Every later stdin read reads `${_pcg_refs}` behind a non-empty check.
  - The script's first line is `#!/usr/bin/env -S bash -p`.
- **Block hash.** The block's sha256 is `d556979bd64b72ca237e4bd3a8d4cf709e0db164ae155c18ab0eea86e39e221f` (ai-config `34cf3bee`). A test pins it.
- **No network.** No test makes a network call.
- **Isolation.** Keep `pre_push.bats`'s setup isolation (math#192): `GIT_*` unset, and `HOME`, `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` redirected.
- **Remote sha.** Use an existing remote sha in ref lines. An all-zeros remote sha exits 128 under the git mock.
- **Process groups.** Any timeout-based test kills its whole process group (`set -m`, then `kill -- -PGID`).
- **Bash coverage.** CI measures bash coverage with `FLOOR=24`, and `scripts/pre-push` is in the denominator. Measure it before and after with `make bash-coverage` (or the target the root Makefile names), and report both figures.
- **CLAUDE.md.** It is at 29,995 of 30,000 bytes, so this PR does not touch it. The gate is documented in `README.md`.
- **Hook behaviour.** The hook's own behaviour is unchanged: the CLAUDE.md budget refusals, sub-project selection, `RUN_HOOK_TESTS`, `RUN_SHELL_LINT` and `RUN_CLI_CONTRACT`.

## Verification Planning

After merge, run V1 on a throwaway clone. Copy only `scripts/pre-push` into `.git/hooks/pre-push`, put a `make` stub on `PATH`, and push to a local bare remote, checking that every commit succeeds. Expect:

- code pushed to master is refused with `[file rule R2]`;
- a docs-only push to master is permitted;
- a feature-branch push is permitted.

The main checkout's hook is a symlink, so it picks up the change on reset. Confirm with `ls -l .git/hooks/pre-push`.

---

### Task 1: Wire the hook and add the wiring tests

```yaml-task
id: 1
description: scripts/pre-push gets the wiring block before the budget check and stdin loop, the bash -p shebang and a ${_pcg_refs} loop; tests/scripts/pre_push.bats adds wiring tests with gh forced to fail
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/pre_push.bats tests/scripts/pre_push_budget.bats
    exit_code: 0
  - cmd: make test-hooks
    exit_code: 0
  - cmd: make lint-hooks
    exit_code: 0
  - cmd: 'test "$(sed -n "/^# >>> push-content-gate wiring$/,/^# <<< push-content-gate wiring$/p" scripts/pre-push | sha256sum | cut -d" " -f1)" = d556979bd64b72ca237e4bd3a8d4cf709e0db164ae155c18ab0eea86e39e221f'
    exit_code: 0
max_retries: 3
files_touched:
  - scripts/pre-push
  - tests/scripts/pre_push.bats
depends_on: []
```

- [ ] Write the tests first, in `tests/scripts/pre_push.bats`, using its existing `setup()`, mocks and assertion helpers. Every wiring test sets `MOCK_GH_EXIT_AUTH_TOKEN=1`. Add:
  - a feature push makes no `gh` call (no `gh` line in `MOCK_CALLS_FILE`);
  - a master push whose gate cannot load is refused before any make. Expect `cannot load the push-content gate`, `gh auth token` in the calls file, no other `gh` call, and no `make` line. Run it for main as well;
  - master on a later ref line is still judged;
  - an `awk` or `cat` placed first on `PATH` cannot hide a master push;
  - an unreadable stdin refuses: `bash -p hook <&-` under a `set -m` process-group watchdog that kills after 30s, expecting `cannot read the pushed refs`;
  - the shebang's `-p` takes effect: exec the script directly, with `BASH_ENV` pointing at a marker-writing file, and expect no marker. Include a control run as `bash script` that does write the marker;
  - the shebang string;
  - the pinned hash.
- [ ] Run the tests and see them fail on the unchanged hook.
- [ ] In `scripts/pre-push`:
  - change line 1 to `#!/usr/bin/env -S bash -p`;
  - paste the block after the setup and before `check_claude_md_budget`, marker to marker;
  - wrap the loop in `if [[ -n "${_pcg_refs}" ]]; then ... fi`, ending it with `done <<< "${_pcg_refs}"`;
  - update the header comment.
- [ ] Run the gates, then commit with `feat(pre-push): load the shared push-content gate`.

### Task 2: README

```yaml-task
id: 2
description: README names the shared gate where it describes the pre-push hook (docs only; CLAUDE.md is at its byte ceiling and is not touched)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'grep -q "push-content gate" README.md'
    exit_code: 0
max_retries: 2
files_touched:
  - README.md
depends_on: [1]
```

- [ ] Near `README.md:382-390`, add one sentence saying that pushes to master are also judged by ai-config's shared push-content gate (ADR-0091). The gate is loaded from GitHub and refuses the push when it cannot load. A feature push makes no network call.
- [ ] Commit with `docs: name the shared push-content gate`.

The orchestrator runs `make test-hooks` and the bash coverage measurement once after Task 2.

## Non-goal check

Run 2026-10-31 against the spec's six effective non-goals (one reviewer-role subagent, `nongoal-check.md`): N1–N6 all CLEAR, 0 CONFLICT, 0 UNCLEAR, no plan change. Only the wiring block is pasted and the gate loads from GitHub (N2, N5); `BASH_ENV` appears only in a test proving `-p` ignores it.
