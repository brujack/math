# Shard the Rust Mutation Runs Implementation Plan

> **Status: DONE** — merged in math#247 (22e7761), 2026-11-24. V1 sweep run 45479226540 green (37 shards, longest 7.4 min); V2 is math#246's re-run under the sharded gate.

spec: docs/superpowers/specs/2026-11-23-shard-rust-mutation-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split both Rust mutation runs (per-PR `mutation-rs`, monthly sweep `mutants`) into shards of at most 75 mutants each, with a live per-mutant log and a post-run check that each shard tested its planned count.

**Architecture:** A crate Makefile accepts `MUTANT_SHARD=k/n`. One planner, `scripts/mutation-rs-plan.sh`, counts mutants per crate and emits matrix units for both workflows. `scripts/mutation-shard-count.sh` compares each shard's `outcomes.json` `total_mutants` with the plan. `mutation-pr-run.sh` gains `--shard` and `--expect`. ADR-0046 records the decision.

**Tech Stack:** bash, jq, GNU make, cargo-mutants 27.1.0, GitHub Actions, BATS, Python unittest + PyYAML.

## Global Constraints

- Work only in `/home/bruce/git-repos/personal/math/.worktrees/shard-rust-mutation/` on branch `ci/shard-rust-mutation`.
- Shard size B = 75: `n = max(1, ceil(K/75))`, round-robin, shard k holds `ceil((K-k)/n)` mutants. There is no per-crate cap. A plan whose shard total exceeds 256 is red: `error: plan needs <T> shards, over the 256-job matrix limit (ADR-0046)`.
- Shard value grammar, used in both the Makefile and `mutation-pr-run.sh`: `^(0|[1-9][0-9]{0,3})/([1-9][0-9]{0,3})$` with k < n.
- N1: keep `--timeout-multiplier 5 --minimum-test-timeout 30`. Never add a fixed `--timeout`.
- N2: do not edit `scripts/mutation-classify.sh`, the Python units, `mutation-py`, `mutation-py-canary` or their aggregator rules. Required by R5/R7 and outside N2: `mutation-py-plan` gains the `has_py`/`py_dirs` outputs, the Python baseline moves unchanged into `mutation-py-baseline`, and the aggregator gains that job's rule.
- N3: the aggregator job id stays `mutation-pr`.
- N4: one formula for every crate, with no per-crate override.
- Every crate `Makefile` is rendered from `scripts/crate_templates/Makefile`. Edit the template, then run `python3 scripts/render_crate_files.py --write`.
- Pin every remote `uses:` to a 40-hex SHA. taiki-e is `taiki-e/install-action@cfdb7ed4ccc7c7dce37759eae89dc5674b469b39 # v2.90.3` with `tool: cargo-mutants@27.1.0` and `fallback: none`.
- Shell: `#!/usr/bin/env bash`, no `set -e`, `[[ ]]`, `${VAR}`, `printf`, functions `|| return 1`, sourcing guard before `main`.
- Root `make test` takes 88 s at base (861 bats, 742 unittest). Run it as `make test </dev/null` with a 600000 ms timeout, synchronously. Activate `.venv` first: `. /home/bruce/git-repos/personal/math/.venv/bin/activate`.
- Root `CLAUDE.md` is 29991 bytes and must not grow.

## Verification (session level)

- `make test </dev/null` exits 0, and `make lint` exits 0 (actionlint included).
- `bash scripts/mutation-rs-plan.sh --whole $(git ls-files '*/*-rs/Cargo.toml' | xargs -n1 dirname)` run locally prints units whose `count` values sum, per crate, to that crate's `cargo mutants --list --json | jq length`. The shard total is 41 at 26dde61; expect it near that.
- The PR's own CI: the PR touches gate files, so `mutation-rs-canary` runs. It must plan one unit and catch at least 1 mutant. `mutation-rs` is skipped (no crate `src/` change), and `mutation-pr` is green.
- V1: dispatch `mutation-testing.yml` on the branch (`gh workflow run mutation-testing.yml --ref ci/shard-rust-mutation`). Every shard finishes under 60 min. Shard `total_mutants` sum to each crate's K, and the shards' mutant names are disjoint. Record the figures in ADR-0046. Any shard past about 50 min lowers B before merge.
- V3: while a `mutation-rs` or sweep shard runs, its live log shows `caught` or `unviable` lines.
- Edge cases: K=0 (no unit, green), a malformed `MUTANT_SHARD` (exit 2), `--expect` mismatch and missing `outcomes.json` (red), a fault unit in the sweep (red, without running).

---

### Task 1: Shardable crate Makefile targets

```yaml-task
id: 1
description: Template mutants and mutants-diff gain MUTANT_SHARD validation and --caught --unviable; re-render all 13 crates
role: executor
model: sonnet
tdd: required
requirements: [R1, R2]
acceptance:
  - cmd: make test </dev/null
    exit_code: 0
  - cmd: python3 scripts/render_crate_files.py --check
    exit_code: 0
  - cmd: >-
      bash -c 'test -z "$(git ls-files "*/*-rs/Makefile" | xargs grep -L -e "--sharding round-robin")"'
    exit_code: 0
max_retries: 3
files_touched:
  - scripts/crate_templates/Makefile
  - tests/scripts/makefile.bats
  - amicable/amicable-rs/Makefile
  - collatz/collatz-rs/Makefile
  - descartes/descartes-rs/Makefile
  - e/e-rs/Makefile
  - factorial/factorial-rs/Makefile
  - fib/fib-rs/Makefile
  - goldbach/goldbach-rs/Makefile
  - perfect-numbers/perfect-numbers-rs/Makefile
  - pi/pi-rs/Makefile
  - prime/prime-rs/Makefile
  - sq/sq-rs/Makefile
  - twin-primes/twin-primes-rs/Makefile
  - zeta/zeta-rs/Makefile
depends_on: []
```

**Files:** `scripts/crate_templates/Makefile` (lines 44–55), the tests in `tests/scripts/makefile.bats`, and the 13 rendered crate Makefiles.

Write the failing bats tests first, using the existing `_rs_stub_setup` / `_rs_make` / `${CALLS}` helpers. Cover both targets:

- `MUTANT_SHARD` unset: no `--shard`.
- `MUTANT_SHARD=` (empty): no `--shard`.
- `MUTANT_SHARD=0/1`: adds `--shard 0/1 --sharding round-robin`.
- `MUTANT_SHARD=3/5`: same mapping.
- Each of `5/5`, `6/5`, `0/0`, `a/b`, `1`, `-1/2`, `01/2`, `1/2/3` makes the recipe exit 2. stderr contains `error: MUTANT_SHARD must be k/n with 0 <= k < n, got <value>`. Cargo is never called. Assert that the target exits non-zero and that the stderr line is present; make itself exits 2.
- `--caught --unviable` is present on both targets.
- Update the two existing exact-string greps (`make mutants runs cargo mutants with the scaled timeout…`, `make mutants-diff passes --in-diff…`) to the new command form.

In the template, both recipes put the shard parse inside `bash -c`, before `$(MUTANTS_SETUP)` (a bad value must not clear `mutants.out`). The parse:

```make
	  s="$${MUTANT_SHARD-}"; shard=(); \
	  if [ -n "$${s}" ]; then \
	    if [[ "$${s}" =~ ^(0|[1-9][0-9]{0,3})/([1-9][0-9]{0,3})$$ ]] && [ "$${BASH_REMATCH[1]}" -lt "$${BASH_REMATCH[2]}" ]; then \
	      shard=(--shard "$${s}" --sharding round-robin); \
	    else printf "error: MUTANT_SHARD must be k/n with 0 <= k < n, got %s\n" "$${s}" >&2; exit 2; fi; \
	  fi; \
```

The cargo line becomes `cargo mutants [--in-diff "$${d}"] --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle --caught --unviable "$${shard[@]}"; $(MUTANTS_TAIL)`. Add one comment line above `mutants:` explaining why `--caught --unviable` is there: on a non-tty, cargo-mutants prints no line per caught mutant without it. Then run `python3 scripts/render_crate_files.py --write`.

**Interfaces:** Produces `make -C <crate> mutants|mutants-diff MUTANT_SHARD=k/n`, which Tasks 4 and 6 use.

### Task 2: Shard count checker

```yaml-task
id: 2
description: New scripts/mutation-shard-count.sh compares outcomes.json total_mutants with the planned count
role: executor
model: sonnet
tdd: required
requirements: [R4]
acceptance:
  - cmd: bats tests/scripts/mutation_shard_count.bats
    exit_code: 0
    stdout_match: 'ok 1 '
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched:
  - scripts/mutation-shard-count.sh
  - tests/scripts/mutation_shard_count.bats
depends_on: [1]
```

**Usage:** `scripts/mutation-shard-count.sh <outcomes.json> <label> <count>`.

- Bad usage (wrong argc, or a count that is not a positive integer) prints usage to stderr and exits 2.
- Reads `total_mutants` with `jq -e '.total_mutants | numbers'`. A missing file counts as M=0. An unreadable or non-JSON file, or a missing or non-numeric key, prints `red: <label> cannot read total_mutants from <path>` and exits 1.
- M == count: prints nothing and exits 0.
- M != count: prints `red: <label> tested <M> mutants, plan expected <count>` to stdout and exits 1.

The script must be executable (`chmod +x`), with a header comment naming both callers (`mutation-pr-run.sh --expect`, and the sweep `mutants` job).

Write the bats tests first:

- equal (5/5);
- unequal (4 against 5, with the exact message);
- missing file (0 against 3, with the exact message);
- non-JSON file;
- JSON without `total_mutants`;
- count `0`, `x` and missing arguments each exit 2;
- running twice gives the same result, and the input file is unchanged.

**Interfaces:** Produces `mutation-shard-count.sh <outcomes> <label> <count>` with exit 0, 1 or 2 and the red line on stdout.

### Task 3: Rust mutation planner

```yaml-task
id: 3
description: New scripts/mutation-rs-plan.sh emits shard units for the PR gate (diff mode) and the sweep (--whole)
role: executor
model: sonnet
tdd: required
requirements: [R3]
acceptance:
  - cmd: bats tests/scripts/mutation_rs_plan.bats
    exit_code: 0
    stdout_match: 'ok 1 '
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched:
  - scripts/mutation-rs-plan.sh
  - tests/scripts/mutation_rs_plan.bats
depends_on: [2]
```

**Usage:** `mutation-rs-plan.sh <base-ref> <crate-dir>...` or `mutation-rs-plan.sh --whole <crate-dir>...`, run from the repo root. Exit 2 on no crate args.

Per crate:

- Diff mode builds the diff with `scripts/mutation-pr-diff.sh <base-ref> <dir> <tmpfile>`. A failure, or an empty diff, prints `red: <dir> - diff empty` (or `diff failed`) and the script exits 1.
- Diff mode then runs `(cd <dir> && cargo mutants --list --json --in-diff <tmpfile>)`. `--whole` runs `(cd <dir> && cargo mutants --list --json)`.
- K comes from stdout. Empty stdout with exit 0 is K=0. Otherwise use `jq -e 'if type=="array" then length else error end'`.
- In diff mode, a non-zero list exit or a non-array stdout prints `red: <dir> - mutant listing failed` and exits 1.
- In `--whole` mode, a list failure, a non-array stdout or K=0 emits one fault unit `{"crate":<dir>,"slug":"<basename>-plan","k":0,"n":0,"count":0,"fault":"<message>"}`. The script continues and exits 0.
- K>0: `n=(K+74)/75` (integer division). Emit k=0..n-1 with `count=(K-k+n-1)/n` and `slug=<basename of dir>-<k>`. stderr gets `plan: <dir> K=<K> n=<n> per-shard=<(K+n-1)/n>`.
- K=0 in diff mode emits no unit. stderr gets `plan: <dir> K=0 (no mutants on changed lines)`.
- After all crates: when the sum of n over units exceeds 256, print `error: plan needs <T> shards, over the 256-job matrix limit (ADR-0046)` to stderr and exit 1.
- Print the units as one compact JSON array line on stdout (`[]` when none). Use `jq -c`.

Use a `( )` subshell with `mktemp -d || exit 1` and an EXIT trap for temp files.

**Tests:** build them on the fixture-git-repo pattern of `tests/scripts/mutation_pr_run.bats` (the real `mutation-pr-diff.sh`). Add a PATH stub `cargo` that reads, per crate dir, a config holding the stdout to print and the exit code. The stub also writes its argv to a log, so tests can assert that diff mode passes `--in-diff` and `--whole` does not. Cases:

- 0 crates (exit 2);
- 1 crate and several crates;
- K=1, 75, 76, 1201 give n=1, 1, 2, 17;
- K=339 gives counts `[68,68,68,68,67]`, summing to 339;
- `--whole` with K=432 gives k 0..9 and counts `44,44,43×8`;
- shard total 257 (e.g. crates of K=75×256 and K=1) is red, and 256 is green;
- K=0 (empty stdout) gives `[]`, exit 0 and the stderr line;
- an empty diff is red;
- a list exit of 1 is red;
- stdout `{}` is red;
- `--whole` with one failing crate gives that crate's `-plan` fault unit plus the other crate's units, exit 0;
- `--whole` with K=0 gives a fault unit.

**Interfaces:** Produces the units JSON `[{"crate","slug","k","n","count"(,"fault")}]` on stdout. Tasks 5 and 6 consume it in workflows via `jq`.

### Task 4: `--shard` and `--expect` on mutation-pr-run.sh

```yaml-task
id: 4
description: mutation-pr-run.sh gains --shard k/n (MUTANT_SHARD) and --expect N (mutation-shard-count.sh) plus the repro line
role: executor
model: sonnet
tdd: required
requirements: [R4]
acceptance:
  - cmd: bats tests/scripts/mutation_pr_run.bats
    exit_code: 0
    stdout_match: 'ok 1 '
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched:
  - scripts/mutation-pr-run.sh
  - tests/scripts/mutation_pr_run.bats
depends_on: [3]
```

Flags may appear anywhere after `<base-ref>`, beside `--min-caught`.

- `--shard v` is validated with the Global Constraints grammar. On failure, print usage and return 2.
- `--expect N` takes `^[1-9][0-9]{0,8}$`. Without `--shard`, print usage and return 2.
- In `run_crate`, before `make`, print `repro: scripts/mutation-pr-run.sh <base-ref> <dir>`. When sharded, print `repro: scripts/mutation-pr-run.sh <base-ref> --shard <k/n> --expect <N> <dir>`.
- When sharded, call `make -C "${dir}" mutants-diff DIFF=… MUTANT_SHARD="${shard}"`. Unsharded, pass no `MUTANT_SHARD` argument.
- After the exit-code read and before the classifier, when `--expect` is set: `"${script_dir}/mutation-shard-count.sh" "${dir}/mutants.out/outcomes.json" "${dir} shard ${shard}" "${expect}" || return 1`. Its stdout red line passes through.
- Update the header usage comment and `_usage`.

**Tests:** extend the stub `make` to log any `MUTANT_SHARD=` argument. Cases:

- `--shard 1/3` reaches make as `MUTANT_SHARD=1/3`;
- `--shard 3/3` and `--shard x` exit 2 without calling make;
- `--expect 5` without `--shard` exits 2, and `--expect 0` exits 2;
- `outcomes.json` `total_mutants` equal to `--expect` classifies as before;
- `total_mutants` 4 against `--expect 5` is red with `tested 4 mutants, plan expected 5`;
- no `outcomes.json` with `--expect 2` is red with `tested 0 mutants`;
- no flags: make gets no `MUTANT_SHARD`, and an existing test's output is unchanged;
- the repro line with and without a shard.

**Interfaces:** Produces `mutation-pr-run.sh <base> [--shard k/n --expect N] [--min-caught N] <crate>...`.

### Task 5: Sharded per-PR workflow

```yaml-task
id: 5
description: mutation-pr.yml splits mutation-rs into plan, shard matrix, canary and Python-baseline jobs; aggregator rules; detect canary paths
role: executor
model: sonnet
tdd: required
requirements: [R5, R6, R7, R13]
acceptance:
  - cmd: make test </dev/null
    exit_code: 0
  - cmd: make lint </dev/null
    exit_code: 0
  - cmd: 'bash -c "! test -e tests/fixtures/mutation-pr-former-job.yml"'
    exit_code: 0
max_retries: 3
files_touched:
  - .github/workflows/mutation-pr.yml
  - scripts/mutation-pr-detect.sh
  - tests/scripts/mutation_pr_detect.bats
  - tests/test_mutation_workflows.py
  - tests/fixtures/mutation-pr-former-job.yml
depends_on: [4]
```

**Workflow** (spec Design 3; keep the existing Python jobs unchanged except as noted):

- `mutation-py-plan` adds outputs `has_py: ${{ steps.detect.outputs.has_py }}` and `py_dirs: ${{ steps.detect.outputs.py_dirs }}`.
- `mutation-rs-plan` has no `if:` and `timeout-minutes: 30`. Steps: checkout with `fetch-depth: 0`, detect (as today), taiki install, then a plan step. When `rs_dirs` is empty, the plan step writes `units=[]`. Otherwise it runs `scripts/mutation-rs-plan.sh "origin/${GITHUB_BASE_REF}" "${rs_dirs[@]}" > "${RUNNER_TEMP}/units.json"` and writes `units=$(cat …)`. Outputs are `units` and `rs_canary`.
- `mutation-rs` has `needs: mutation-rs-plan`, `if: needs.mutation-rs-plan.outputs.units != '[]'`, `name: mutation-rs ${{ matrix.slug }}`, `strategy.fail-fast: false`, `matrix.include: ${{ fromJSON(needs.mutation-rs-plan.outputs.units) }}` and `timeout-minutes: 60`. Steps: checkout, rust-toolchain, taiki install, the GMP key step, and the cache restore (copy today's, without the `detect` conditions). The run step has env `CRATE`, `K`, `N` and `COUNT` from the matrix, and the body exactly:
  ````bash
  set +e
  scripts/mutation-pr-run.sh "origin/${GITHUB_BASE_REF}" --shard "${K}/${N}" --expect "${COUNT}" "${CRATE}" 2>&1 | tee "${RUNNER_TEMP}/rs.log"
  rc=${PIPESTATUS[0]}
  set -e
  {
    printf '```\n'
    { grep -E '^(red|green|repro):|MISSED|TIMEOUT|^error:' "${RUNNER_TEMP}/rs.log" || [ $? -eq 1 ]; }
    printf '```\n'
  } >> "${GITHUB_STEP_SUMMARY}"
  exit "${rc}"
  ````
  The step passes no `--min-caught`.
- `mutation-rs-canary` has `needs: mutation-rs-plan`, `if: needs.mutation-rs-plan.outputs.rs_canary == 'true'` and `timeout-minutes: 30`. Steps: checkout, toolchain, taiki, the GMP key step and restore. It keeps today's edit, count check and commit. It then runs `scripts/mutation-rs-plan.sh HEAD~1 amicable/amicable-rs > "${RUNNER_TEMP}/canary-units.json"`. It requires `jq length` == 1, else it prints `red: canary planned <n> units, expected exactly 1` and exits 1. It reads `k/n/count` with jq, then runs the `mutation-pr-run.sh HEAD~1 --shard … --expect … --min-caught 1 amicable/amicable-rs` with the same `set +e`/`PIPESTATUS` form.
- `mutation-py-baseline` has `needs: mutation-py-plan`, `if: needs.mutation-py-plan.outputs.has_py == 'true'` and `timeout-minutes: 30`. Steps: checkout, GMP/MPFR apt, setup-python, today's pip line, and today's baseline loop with env `PY_DIRS` from `needs.mutation-py-plan.outputs.py_dirs`.
- `mutation-pr` `needs` lists all eight jobs. Add the Rust rules from R7 in the same `case` style, reading env `RS_PLAN_RESULT`, `RS_RESULT`, `RS_UNITS`, `RS_CANARY_RESULT`, `RS_CANARY`, `PYB_RESULT` and `HAS_PY`.

**Detect:** append `scripts/mutation-rs-plan.sh scripts/mutation-exit-code.sh scripts/mutation-shard-count.sh` to `RS_CANARY_PATHS`. Add a bats case per new path asserting `rs_canary=true`.

**Tests** (`tests/test_mutation_workflows.py`):

- Delete `FORMER_JOB`, `former_pr_job` and `test_mutation_rs_equals_former_job`, and `git rm` the fixture.
- Rewrite the `MutationPrTests`, `PrJobGraphTests`, `PrCanaryJobTests` and `PrAggregatorTests` assertions that read the old single job, so they pin:
  - the job graph, every `if:`, the `name:` templates and the timeouts;
  - the taiki step (SHA, `cargo-mutants@27.1.0`, `fallback: none`) in the three Rust jobs;
  - the toolchain and GMP restore in `mutation-rs` and the canary;
  - no `cargo install cargo-mutants`;
  - no `--min-caught` in `mutation-rs`.
- Execute the `mutation-rs` run block with a stub `scripts/mutation-pr-run.sh` that exits 3. Assert `rc` 3 under both `bash -e` and `bash -eo pipefail`, and assert the summary is fenced. Use the existing `run_pr_step_block` style. Then run the stub with exit 0 and no matching lines: the step exits 0.
- Execute the aggregator block for each R7 rule: one green case and one red case per rule, including `skipped` with units `[]` (green) and `skipped` with non-empty units (red).
- Execute the canary block with stub planner output of 0, 1 and 2 units.

`tests/test_tool_pins.py` is not touched here; Task 6 owns it.

**Interfaces:** Consumes Tasks 3 and 4. Produces the job ids used by the CLAUDE.md text in Task 7.

### Task 6: Sharded monthly sweep

```yaml-task
id: 6
description: mutation-testing.yml setup plans with mutation-rs-plan.sh --whole; mutants runs one shard per job with the count check
role: executor
model: sonnet
tdd: required
requirements: [R8, R9]
acceptance:
  - cmd: make test </dev/null
    exit_code: 0
  - cmd: make lint </dev/null
    exit_code: 0
  - cmd: 'bash -c "! grep -rn \"cargo install cargo-mutants\" .github/workflows"'
    exit_code: 0
max_retries: 3
files_touched:
  - .github/workflows/mutation-testing.yml
  - tests/test_mutation_workflows.py
  - tests/test_tool_pins.py
depends_on: [5]
```

**`setup`:**

- Add the taiki install step before the plan step.
- Keep today's tracked-crate list, unknown-crate check and empty-list check. Then run `scripts/mutation-rs-plan.sh --whole "${dirs[@]}" > "${RUNNER_TEMP}/units.json"`. Its non-zero exit fails `setup`; that is the only other red path (over 256).
- Write `matrix={"include": <units>}` (`jq -c '{include: .}'`) and `units=$(jq -r '[.[].slug] | join(" ")')`.

**`mutants`:**

- `name: Mutation ${{ matrix.slug }}`. Keep the job-start marker.
- Steps: toolchain, taiki install (replacing `cargo install`), the GMP key step and the read-only restore copied from `mutation-pr.yml`.
- The run step has env `CRATE_DIR`, `SLUG`, `K`, `N`, `COUNT` and `FAULT` from the matrix (`${{ matrix.fault }}` is empty for normal units).
- When `FAULT` is non-empty: write `red: ${SLUG} - plan fault: ${FAULT}` to the summary and `status/${SLUG}`, then exit 1.
- Otherwise:
  - run `make -C "${CRATE_DIR}" mutants MUTANT_SHARD="${K}/${N}" || true`;
  - read the exit code as today;
  - run `scripts/mutation-shard-count.sh "${CRATE_DIR}/mutants.out/outcomes.json" "${SLUG}" "${COUNT}"`. On a non-zero exit, tee its line to the summary and status, then exit 1;
  - classify with `… 0 1` as today.
- Artifact names stay `mutants-status-${{ matrix.slug }}` / `mutants-output-${{ matrix.slug }}`. `notify` is unchanged.

**Tests:**

- Update `RustSetupJobTests` (`run_rs_setup`) to stub `scripts/mutation-rs-plan.sh` in the copied workspace. Assert the matrix and units for a stub returning 2 crates × 2 shards plus a fault unit, and that a stub exit of 1 fails setup.
- Update `RustMutantsJobTests` / `run_crate_job`:
  - make is called with `MUTANT_SHARD=k/n`;
  - a count mismatch (stub `mutation-shard-count.sh`, or the real one with a written `outcomes.json`) is red, with its line in the status;
  - a `FAULT` unit is red and make is never called;
  - the name template.
- `tests/test_tool_pins.py`: replace `test_taiki_cargo_mutants_matches_mutation_workflow_install` with a test that requires the taiki `cargo-mutants@` version set to have exactly one member. The test also requires both `mutation-testing.yml` and `mutation-pr.yml` to carry that taiki tool. Keep the `> 30` cargo-install site floor valid: re-measure it after the removal and adjust only if it fails, stating the new count.

### Task 7: ADR-0046, CLAUDE.md, indexes

```yaml-task
id: 7
description: Docs-only — ADR-0046 with empty V1/V2 measurement rows, ADR index, root CLAUDE.md Rust mutation lines with no net byte growth, plan-index row
role: executor
model: sonnet
tdd: not-applicable
requirements: [R10, R11, R12]
acceptance:
  - cmd: test -f docs/adr/0046-shard-the-rust-mutation-runs.md
    exit_code: 0
  - cmd: grep -q '0046-shard-the-rust-mutation-runs.md' docs/adr/README.md
    exit_code: 0
  - cmd: 'bash -c "[ $(wc -c < CLAUDE.md) -le 29991 ]"'
    exit_code: 0
  - cmd: grep -qF '[--shard <k>/<n> --expect <count>]' CLAUDE.md
    exit_code: 0
  - cmd: grep -q '2026-11-24-shard-rust-mutation.md' docs/superpowers/README.md
    exit_code: 0
  - cmd: make test </dev/null
    exit_code: 0
max_retries: 3
files_touched:
  - docs/adr/0046-shard-the-rust-mutation-runs.md
  - docs/adr/README.md
  - CLAUDE.md
  - docs/superpowers/README.md
depends_on: [6]
```

**ADR-0046** follows `docs/adr/0044-python-pr-mutation-gate.md`'s layout (Status, Date, Context, Decision, Consequences, Related). Its Decision section carries:

- the formula, B=75, the 256-shard total, and no per-crate cap;
- round-robin assignment;
- the `--expect` / `mutation-shard-count.sh` check, and why PR shards take no `--min-caught`;
- baseline test time as the cost driver;
- the spec's measurements: 0.23 s listing, 21–30 s/mutant, 108.6 s cold build, 339 = 68×4+67, 432 = 44,44,43×8, 2537 mutants and 41 shards at 26dde61;
- both job graphs.

Add a `## Measurements` table with columns crate | shards | baseline test time | longest shard | source. Its rows are `V1 (sweep)` and `V2 (math#246)`, holding `pending` cells.

**ADR index:** add a row in `docs/adr/README.md`, dated 2026-11-24, Accepted.

**CLAUDE.md:** rewrite the three Rust mutation lines (`Mutation CI is…`, the `mutation-pr.yml job mutation-rs…` line, and, if needed, the sweep-leg line).

- State: plan job, one job per shard (B=75, `--expect` per shard), `--min-caught 1` on the canary only, and the sweep's one job per shard.
- Repro: `scripts/mutation-pr-run.sh origin/master [--shard <k>/<n> --expect <count>] <crate>`; for one mutant, `cargo mutants --in-diff <diff> -F '<regex>'` from the crate dir.
- Detail lives behind `→ docs/adr/0046-shard-the-rust-mutation-runs.md`.
- `wc -c CLAUDE.md` must be ≤ 29991. Trim the replaced lines' wording, not other rules.

**Plan index:** in `docs/superpowers/README.md`, add a row for this plan and spec with status `In progress`. Do not touch the Backlog. The `zeta monthly mutation sweep budget` row is removed in math#246's rebase (R12, `[#246]`).

## Orchestrator steps after Task 7

1. Run `make test </dev/null` and `make lint </dev/null` once more. Then run the Verification `--whole` local check.
2. Run Phase 3 (`finishing-a-development-branch`). Open the PR with `gh pr create --draft`.
3. Watch CI with `gh pr checks <n> --watch`.
4. Run V1: `gh workflow run mutation-testing.yml --ref ci/shard-rust-mutation`. Fill ADR-0046's V1 row with a `fix(docs)` commit, then push.
5. Run `gh pr ready <n>` only after V1 is recorded and no shard ran past about 50 min.

## Non-goal check

Reviewer run 2026-11-24 (one fresh Opus subagent, `nongoal-check.md`): N1 CLEAR, N3 CLEAR, N4 CLEAR, N2 UNCLEAR.

- **N2 — UNCLEAR.** Quote: "`mutation-py-plan` adds outputs `has_py` ... `mutation-py-baseline` has `needs: mutation-py-plan` ... reading env ... `PYB_RESULT` and `HAS_PY`". Why: the plan's Global Constraint said "do not edit ... any Python mutation unit, job or rule", which Task 5 contradicts.
  Resolution: plan revision. Spec R5 requires the `has_py`/`py_dirs` outputs and the `mutation-py-baseline` job, and R7 requires that job's aggregator rule. N2 names only the Python units, `mutation-py`, `mutation-py-canary` and their aggregator rules, so the work is in scope. The constraint paraphrased N2 too broadly.
  Before: "N2: do not edit `scripts/mutation-classify.sh` or any Python mutation unit, job or rule."
  After: "N2: do not edit `scripts/mutation-classify.sh`, the Python units, `mutation-py`, `mutation-py-canary` or their aggregator rules. Required by R5/R7 and outside N2: `mutation-py-plan` gains the `has_py`/`py_dirs` outputs, the Python baseline moves unchanged into `mutation-py-baseline`, and the aggregator gains that job's rule."
