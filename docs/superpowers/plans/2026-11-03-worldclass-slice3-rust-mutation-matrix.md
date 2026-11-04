# Worldclass Slice 3: Rust Mutation Matrix Implementation Plan

> **Status: DONE** (math#202, 4a76cb4)

spec: docs/superpowers/specs/2026-11-03-worldclass-slice3-rust-mutation-matrix-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `mutation-testing.yml` into `setup` → one `mutants` job per crate → `notify`, so a lost runner costs one crate and `notify` names it.

**Architecture:** `setup` lists crates from git and emits a `jq`-built `include` matrix of `crate`/`slug` pairs plus `units`. Each matrix job runs one crate and uploads `mutants-status-<slug>` and `mutants-output-<slug>`. `notify` merges the status artifacts, passes `EXPECTED_STATUS_UNITS`, files the issue, then re-aggregates one `mutants-output` artifact for ai-config's `mutation-review.yml`.

**Tech Stack:** GitHub Actions YAML, bash, jq, Python unittest with PyYAML.

## Global Constraints

- No change to any crate `Makefile` `mutants` target, `scripts/mutation-classify.sh`, `scripts/mutation-notify.sh`, `mutation-pr.yml` or `mutation-testing-python.yml` (N1).
- No GMP build cache in the mutants jobs (N2). No change to the cargo-mutants version (`--locked --version 27.1.0`) or the cron `"0 4 1 * *"` (N3).
- Keep every existing action SHA pin byte-identical (checkout `3d3c42e5…`, upload-artifact `cf430e03…`, download-artifact `90008277…`, rust-toolchain `b725eda5…`).
- Keep the `FULL_SWEEP` expression byte-identical: `tests/scripts/mutation_notify.bats` line 878 greps for it.
- Only the notify `dl` step may carry `continue-on-error` (`tests/test_workflow_continue_on_error.py`).
- No `${{ }}` expression inside any `run:` block; values reach shell through `env:`.
- Root `CLAUDE.md` must not grow: `wc -c CLAUDE.md` stays ≤ 30000 (it is exactly 30000 now).
- Tests that run git must use `clean_git_env()` (worktree hooks export `GIT_DIR`).

## Verification Planning

- **Whole change:** `python3 -m unittest tests.test_mutation_workflows -v`, `make lint`, `make test` (root: bats + unittest), all exit 0. actionlint is not installed locally, so the orchestrator runs a pinned, sha256-checked actionlint 1.7.12 from the scratchpad over `.github/workflows/mutation-testing.yml` (checksum from `tests/test_actionlint_install.py`); CI's `scripts` job enforces it too.
- **Red first:** the new test classes run against the base workflow and fail (no `setup` job), with exit 1 from unittest, not an import or usage error.
- **Discrimination:** Task 1 applies two mutations in a scratch copy and sees tests go red: (a) delete the `tee` target `status/${SLUG}` so green writes nothing; (b) change `gsub("/"; "-")` to `gsub("/"; "_")`.
- **Post-merge (V1):** dispatch a full sweep (`gh workflow run mutation-testing.yml`). Expect 11 `Mutation <crate>` jobs, `notify` with 11 statuses, a `mutants-output` artifact holding 11 `<crate>/mutants.out/` trees (`gh run download <id> -n mutants-output` then `find . -name outcomes.json | wc -l` = 11), and #195 closed if all are green.
- **Post-merge (V2):** on a run with one failed or cancelled crate job, use "Re-run failed jobs" and check whether attempt 2's `notify` sees attempt 1's green `mutants-status-*` artifacts (its `EXPECTED_STATUS_UNITS` section lists no missing crates). Record the answer in ADR-0040.

## Reference: target workflow

The full new `.github/workflows/mutation-testing.yml` below `env:`. The header comment, `on:` block and `env:` block stay as they are, except the header comment line about runs may say "one job per crate".

```yaml
jobs:
  setup:
    name: List crates and build matrix
    runs-on: ubuntu-latest
    permissions:
      contents: read
    outputs:
      matrix: ${{ steps.plan.outputs.matrix }}
      units: ${{ steps.plan.outputs.units }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7

      - name: List crates and build matrix
        id: plan
        env:
          CRATE: ${{ github.event.inputs.crate }}
        run: |
          # Tracked manifests only: `find` also matched tests/fixtures/**/Cargo.toml.
          tracked=()
          while IFS= read -r manifest; do
            tracked+=("$(dirname "${manifest}")")
          done < <(git ls-files '*/*-rs/Cargo.toml')

          if [[ -n "${CRATE}" ]]; then
            # Free text from a dispatch input must not reach GITHUB_OUTPUT
            # unchecked (a newline would write a second output line).
            match=0
            for dir in "${tracked[@]}"; do
              [[ "${dir}" == "${CRATE}" ]] && match=1
            done
            if [[ ${match} -eq 0 ]]; then
              printf 'error: unknown crate %q (not a tracked */*-rs crate)\n' "${CRATE}" >&2
              exit 1
            fi
            dirs=("${CRATE}")
          else
            dirs=("${tracked[@]}")
          fi

          # An empty list (a layout change or a git failure) would build an
          # empty matrix and report green having tested nothing.
          if [[ ${#dirs[@]} -eq 0 ]]; then
            printf "error: no crates found to test — refusing to report green\n" >&2
            exit 1
          fi

          # The one slug function: the directory with / replaced by -. Artifact
          # names cannot contain /, and expressions have no string replace, so
          # the slug travels in the matrix and units is read back from it.
          matrix=$(jq -n -c '{include: [$ARGS.positional[] | {crate: ., slug: gsub("/"; "-")}]}' --args "${dirs[@]}")
          units=$(jq -r '[.include[].slug] | join(" ")' <<< "${matrix}")
          printf 'matrix=%s\n' "${matrix}" >> "${GITHUB_OUTPUT}"
          printf 'units=%s\n' "${units}" >> "${GITHUB_OUTPUT}"

  mutants:
    name: Mutation ${{ matrix.crate }}
    needs: setup
    runs-on: ubuntu-latest
    timeout-minutes: 60
    permissions:
      contents: read
    strategy:
      fail-fast: false
      matrix: ${{ fromJSON(needs.setup.outputs.matrix) }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7

      - name: Mark job start
        run: mkdir -p "${GITHUB_WORKSPACE}/marker" && date -u > "${GITHUB_WORKSPACE}/marker/job-began"

      - uses: dtolnay/rust-toolchain@b725eda525362e7cf34af9a7243cac1e3f01a7ec # stable

      - name: Install cargo-mutants
        run: cargo install cargo-mutants --locked --version 27.1.0

      - name: Run mutants
        env:
          CRATE_DIR: ${{ matrix.crate }}
          SLUG: ${{ matrix.slug }}
        run: |
          mkdir -p "${GITHUB_WORKSPACE}/status"
          rc=0
          make -C "${CRATE_DIR}" mutants || rc=$?
          # (keep the existing three comments here: capture before any pipe,
          # `|| cls=$?` not `; cls=$?`, and 2>&1 because red verdicts go to stderr)
          cls=0
          verdict=$("${GITHUB_WORKSPACE}/scripts/mutation-classify.sh" \
            "${rc}" "${CRATE_DIR}/mutants.out/outcomes.json" "${CRATE_DIR}" 2>&1) || cls=$?
          printf '%s\n' "${verdict}" \
            | tee -a "${GITHUB_STEP_SUMMARY}" "${GITHUB_WORKSPACE}/status/${SLUG}"
          exit "${cls}"

      - name: Record unfinished crate
        if: cancelled()
        env:
          SLUG: ${{ matrix.slug }}
        run: |
          mkdir -p "${GITHUB_WORKSPACE}/status"
          status_file="${GITHUB_WORKSPACE}/status/${SLUG}"
          if [[ ! -e "${status_file}" ]]; then
            printf "red: %s — did not finish (cancelled or timed out)\n" "${SLUG}" > "${status_file}"
          fi

      - name: Upload crate status
        if: always()
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7
        with:
          name: mutants-status-${{ matrix.slug }}
          path: |
            status/
            marker/
          retention-days: 30

      - name: Upload crate output
        if: always()
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7
        with:
          name: mutants-output-${{ matrix.slug }}
          # marker/ keeps the artifact root at the workspace, so the crate
          # prefix survives and eleven trees do not collide when merged.
          path: |
            ${{ matrix.crate }}/mutants.out/
            marker/
          retention-days: 30

  notify:
    needs: [setup, mutants]
    if: always()
    runs-on: ubuntu-latest
    permissions:
      contents: read
      issues: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7
      - id: dl
        if: always()
        uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8
        continue-on-error: true
        with:
          pattern: mutants-status-*
          merge-multiple: true
          path: artifact
          digest-mismatch: error
      - name: File, comment, or close the tracking issue
        if: always()
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          RESULT: ${{ needs.mutants.result }}
          DL_OUTCOME: ${{ steps.dl.outcome }}
          ARTIFACT_DIR: artifact
          EXPECTED_STATUS_UNITS: ${{ needs.setup.outputs.units }}
          RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
          ISSUE_TITLE: "mutation-testing: monthly run failed"
          ISSUE_LABEL: mutation-failure
          UNIT_NOUN: crate
          REPO: ${{ github.repository }}
          FULL_SWEEP: ${{ format('{0}', inputs.crate) == '' && 'true' || 'false' }}
        run: scripts/mutation-notify.sh
      # ai-config's mutation-review.yml downloads the exact name mutants-output.
      # Into outputs/, never artifact/: mutation-notify.sh reads extra root
      # entries there as a different attestation cause.
      - name: Download crate outputs
        if: always()
        uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8
        with:
          pattern: mutants-output-*
          merge-multiple: true
          path: outputs
          digest-mismatch: error
      - name: Upload mutants output
        if: always()
        uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7
        with:
          name: mutants-output
          path: outputs/
          retention-days: 30
          overwrite: true
```

---

### Task 1: setup job and per-crate mutants matrix

```yaml-task
id: 1
description: Replace the single mutants job with a setup job and a per-crate matrix job, rebuilding the Rust tests on the setup/mutants shape
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R3, R4, R6]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_workflows -v
    exit_code: 0
  - cmd: make lint
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched:
  - .github/workflows/mutation-testing.yml
  - tests/test_mutation_workflows.py
depends_on: []
```

**Files:** `.github/workflows/mutation-testing.yml` (the `setup` and `mutants` jobs of the Reference; leave `notify` as is, it is Task 2), `tests/test_mutation_workflows.py` (the Rust section from `RS_WORKFLOW =` to the end).

**Tests first.** Replace `RustCrateDiscoveryTests`, `RunMutantsBehaviourTests`, `crates_step`, `run_crates`, `rs_steps` and `run_mutants_in_sandbox` with:

- `rs_job(name)` returning `yaml.safe_load(RS_WORKFLOW.read_text())["jobs"][name]`, and `rs_step(job, name)` asserting exactly one step with that `id` or `name`.
- `run_rs_setup(crate="", path=None)` → `(proc, outputs, lines)`: the `run_crates` body retargeted at `rs_step("setup", "plan")`, same `bash --noprofile --norc -eo pipefail`, `cwd=REPO_ROOT`, malformed-line check.
- `RustSetupJobTests`:
  - empty input: exit 0; exactly two lines, `matrix=` then `units=`; `units.split()` has 11 entries equal to `[d.replace("/", "-") for d in tracked_crate_dirs()]`; no `tests-` slug;
  - `json.loads(matrix)["include"]` crates equal `tracked_crate_dirs()`, slugs equal `units.split()`, each slug equals its crate with `/`→`-`;
  - known crate `sq/sq-rs`: `units == "sq-sq-rs"`, include is `[{"crate": "sq/sq-rs", "slug": "sq-sq-rs"}]`;
  - unknown crate: exit 1, name in stderr, no output lines; newline input `"sq/sq-rs\nevil=1"`: exit 1, no output lines;
  - empty listing (stub `git` that exits 0, as today's test): exit 1, `refusing to report green` in stderr, no output lines;
  - keep the fixture positive control; `CRATE` env reads `${{ github.event.inputs.crate }}`; outputs declared from `steps.plan.outputs`; no `${{` in the run block.
- `run_crate_job(crate, slug, red=False, pre_status=None)`: sandbox like today's `run_mutants_in_sandbox` with stub `make` and classifier, running `rs_step("mutants", "Run mutants")` with `CRATE_DIR`/`SLUG` env; returns `(proc, make_calls, {status filename: content})`.
- `RustMutantsJobTests`:
  - green crate: exit 0, one `make` call with `a/a-rs`, `status/a-a-rs` content `green: a/a-rs\n`;
  - red crate: exit 1, `status/a-a-rs` content `red: a/a-rs\n`;
  - cancelled step (run `Record unfinished crate` alone in a sandbox): no prior status → file reads `red: a-a-rs — did not finish (cancelled or timed out)\n`; existing status left byte-identical;
  - structure: `fail-fast` false, `timeout-minutes` 60, matrix `${{ fromJSON(needs.setup.outputs.matrix) }}`, `needs` setup, cancelled step `if` is `cancelled()`, upload names `mutants-status-${{ matrix.slug }}` and `mutants-output-${{ matrix.slug }}` both `if: always()`, status paths `{status/, marker/}`, output paths `{${{ matrix.crate }}/mutants.out/, marker/}`, run step env `CRATE_DIR`/`SLUG` from `matrix.crate`/`matrix.slug`, no `${{` in any `run:` of the job.

- [ ] Write the tests; run `python3 -m unittest tests.test_mutation_workflows -v`; confirm the new classes fail with KeyError `setup` (exit 1).
- [ ] Rewrite the jobs per the Reference; tests green.
- [ ] Discrimination in a scratch copy (`git archive HEAD | tar -x -C <scratch>` after committing, or `git stash create`): mutation (a) removes `"${GITHUB_WORKSPACE}/status/${SLUG}"` from `tee`, mutation (b) changes the jq slug to `_`; each makes a named test fail. Report both; delete the scratch copy.
- [ ] `make lint`, `make test`; commit via `caveman:caveman-commit`.

**Interfaces:** Produces job ids `setup` (outputs `matrix`, `units`), `mutants`; step id `plan`; helpers `rs_job`, `rs_step` for Task 2.

### Task 2: notify job wiring and mutants-output re-aggregation

```yaml-task
id: 2
description: Wire notify to the matrix (merged status download, EXPECTED_STATUS_UNITS) and re-aggregate one mutants-output artifact after the issue step
role: executor
model: sonnet
tdd: required
requirements: [R5, R8, R6]
acceptance:
  - cmd: python3 -m unittest tests.test_mutation_workflows -v
    exit_code: 0
  - cmd: python3 -m unittest tests.test_workflow_continue_on_error -v
    exit_code: 0
  - cmd: make lint
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched:
  - .github/workflows/mutation-testing.yml
  - tests/test_mutation_workflows.py
depends_on: [1]
```

**Files:** the `notify` job of `.github/workflows/mutation-testing.yml` exactly as in the Reference; a `RustNotifyJobTests` class in `tests/test_mutation_workflows.py`.

**Tests first** (`RustNotifyJobTests`, using `rs_job("notify")`):

- `needs == ["setup", "mutants"]`, `if == "always()"`, permissions `issues: write`;
- `dl`: `pattern: mutants-status-*`, `merge-multiple: true`, `path: artifact`, `continue-on-error: true`, no `name:` key;
- issue step: `if: always()`, `env.EXPECTED_STATUS_UNITS == "${{ needs.setup.outputs.units }}"`, `UNIT_NOUN: crate`, `ISSUE_LABEL: mutation-failure`, `run: scripts/mutation-notify.sh`;
- output download: `pattern: mutants-output-*`, `merge-multiple: true`, `path: outputs`, no `continue-on-error`;
- output upload: `name: mutants-output`, `path: outputs/`, `overwrite: true`, `retention-days: 30`, no `continue-on-error`;
- order: issue step index < output download index < output upload index, and all three `if: always()`;
- the status pattern does not match `mutants-output-x` and the output pattern does not match `mutants-status-x` (`fnmatch`).

- [ ] Write the tests; confirm they fail on Task 1's tree (exit 1).
- [ ] Rewrite `notify`; tests green; `tests.test_workflow_continue_on_error` green.
- [ ] `make lint`, `make test`; commit via `caveman:caveman-commit`.

### Task 3: ADR-0040, CLAUDE.md lines, plan index

```yaml-task
id: 3
description: Write ADR-0040 and update the root CLAUDE.md mutation lines and the plan index (docs-only, no behaviour change, so TDD does not apply)
role: executor
model: sonnet
tdd: not-applicable
requirements: [R7]
acceptance:
  - cmd: test -f docs/adr/0040-rust-mutation-matrix.md
    exit_code: 0
  - cmd: 'grep -q "0040-rust-mutation-matrix.md" docs/adr/README.md'
    exit_code: 0
  - cmd: '[ "$(wc -c < CLAUDE.md)" -le 30000 ]'
    exit_code: 0
  - cmd: 'grep -c "needs: \[mutants\]" CLAUDE.md'
    exit_code: 1
  - cmd: 'grep -q "needs: \[setup, mutants\]" CLAUDE.md'
    exit_code: 0
  - cmd: 'grep -q "2026-11-03-worldclass-slice3-rust-mutation-matrix.md" docs/superpowers/README.md'
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 2
files_touched:
  - docs/adr/0040-rust-mutation-matrix.md
  - docs/adr/README.md
  - docs/adr/0038-actionlint-gate-and-full-sweep-close.md
  - CLAUDE.md
  - docs/superpowers/README.md
depends_on: [2]
```

- **ADR-0040** "One mutation job per Rust crate", Date 2026-11-03, Status Accepted. Context: the two runs from the spec's Problem table, the Aug-01 Phase B trigger. Decision: setup/matrix/notify as built, slug in the matrix, `cancelled()` step, `EXPECTED_STATUS_UNITS` naming a lost runner's crate, `mutants-output` re-aggregated in `notify` for ai-config. Consequences: ~20 min wall-clock, one crate lost per lost runner, 11 cargo-mutants installs, and "V2 (re-run failed jobs): unverified — recorded after the first matrix run". Related: ADR-0033, ADR-0038, spec path. Add its index row in `docs/adr/README.md` matching the existing columns.
- **ADR-0038:** append one line under Related: "Decision 1's single `List crates` step and `crate_dirs=` output are superseded by ADR-0040." Do not edit its Decision text.
- **Root CLAUDE.md line 139:** replace "`List crates` uses `git ls-files '*/*-rs/Cargo.toml'`, rejects unknown `crate`" with wording that says a `setup` job lists crates from that command, rejects an unknown `crate`, and fans out one 60-minute job per crate. **Line 147:** `needs: [mutants]` becomes `needs: [setup, mutants]`. Trim words elsewhere in those two lines so `wc -c CLAUDE.md` stays ≤ 30000. Do not touch other lines.
- **Plan index:** add the row `| 2026-11-03 | [worldclass-slice3-rust-mutation-matrix](plans/2026-11-03-worldclass-slice3-rust-mutation-matrix.md) | [spec](specs/2026-11-03-worldclass-slice3-rust-mutation-matrix-design.md) | In progress |` after the slice 2 row.
- [ ] Make the edits; run the acceptance commands; commit via `caveman:caveman-commit`.

The suite does not read these files, so this task carries no `make test`; the orchestrator runs `make test` after Task 2.

## Orchestrator steps

1. Worktree: `git worktree add .worktrees/wc-slice3 -b ci/rust-mutation-matrix` from `master`.
2. Run Tasks 1–3 in order (each depends on the last; same two files in 1 and 2).
3. Run pinned actionlint 1.7.12 (sha256-checked, from the scratchpad) on `.github/workflows/mutation-testing.yml`; expect exit 0.
4. Phase 3 (`finishing-a-development-branch`), then `gh pr create --draft`, `gh pr checks --watch`, `gh pr ready` after all gates pass.
5. After merge: V1 dispatch and evidence; V2 when a crate job fails or by cancelling one crate job in a dispatched run and re-running failed jobs; record V2 in ADR-0040 (docs direct to master); close #195 on green; remove the Backlog row "Monthly Rust mutation sweep dies mid-run (runner lost)"; mark the plan Done; message the ai-config session about `math-testing-policy.md` § Mutation testing if it describes a single job.

## Non-goal check

Fresh reviewer (Opus), 2026-11-03. No plan revision or amendment needed.

- N1: CLEAR. The plan edits only `mutation-testing.yml`, `tests/test_mutation_workflows.py` and docs; it calls `make -C <crate> mutants`, `mutation-classify.sh` and `mutation-notify.sh` unchanged and leaves `mutation-pr.yml` and `mutation-testing-python.yml` alone.
- N2: CLEAR. No mutants job has a cache step.
- N3: CLEAR. `cargo install cargo-mutants --locked --version 27.1.0` and cron `"0 4 1 * *"` stay unchanged.
