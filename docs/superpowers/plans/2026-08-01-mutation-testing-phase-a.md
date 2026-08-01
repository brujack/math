# Mutation Testing Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `mutation-testing.yml` produce its first green run in six months, and make a red one reach the maintainer.

**Architecture:** A memory cap in each crate's `Makefile` stops allocation-unbounded mutants from killing the runner. A tested shell classifier decides green/red from `outcomes.json` counts rather than the exit code alone. A separate `notify` job — on its own runner, so it survives the mutation job's death — files and closes a labelled issue. No matrix, no artifact aggregation, no per-PR changes; those are Phase B.

**Tech Stack:** GNU Make, Bash, BATS, GitHub Actions, cargo-mutants 27.x, cosmic-ray.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-01-mutation-testing-per-project-design.md`.
- Memory cap value is `8388608` (KiB, = 8 GiB) everywhere. Measured on `collatz/collatz-rs`: capped run gives exit 2 / 36 caught / 4 missed / 1 unviable; uncapped gives exit 3 / 35 caught / 4 missed / 1 identical unviable.
- `MUTANTS_UNCAPPED` is checked **before** the `ulimit`, never in its failure branch. Written the other way it is never consulted on Linux, where `ulimit -v` succeeds.
- Per-mutant timeout is `30` everywhere — Makefiles and workflows must not diverge again.
- `outcomes.json` top-level keys, verified against cargo-mutants 27.0.0: `total_mutants`, `caught`, `missed`, `timeout`, `unviable`, `success`, `cargo_mutants_version`.
- cargo-mutants exit codes, verified empirically: `0` all caught, `2` survivors, `3` timeouts present, `4` baseline tests failed.
- `mutation-pr.yml` is **not touched**. Leaving it alone preserves `factorial-rs`'s existing blocking in-diff bar.
- Shell per `~/.claude/standards/shell.md`: `#!/usr/bin/env bash`, no `set -e`, `[[ ]]`, `printf` not `echo`, `snake_case()`, `readonly` constants, sourcing guard for testability.
- BATS is the shell test standard here; `make test-hooks` runs `bats --recursive tests/`.

## Session-Level Verification

Per-task `acceptance:` blocks cover mechanical gates. The feature is verified when:

**Command:** `gh workflow run mutation-testing.yml --ref <branch> -f crate=collatz/collatz-rs`, then `gh run watch`.

**Expected:** the run is green; no exit 143 anywhere in the log; `outcomes.json` reports `caught == 36`, `missed == 4`, `unviable == 1`, matching the Docker measurement; the artifact uploads; the job summary names the survivor and timeout counts.

**Edge cases that must be exercised (these are Verification steps 2, 3, 6, 7 in the spec, and they run before merge):**

- Cap headroom on `factorial-rs`, `pi-rs`, `e-rs` — capped vs `MUTANTS_UNCAPPED=1` `unviable` counts must be identical.
- A full 11-crate dispatch reaching green — also the Phase B trigger and the first real sweep-time measurement.
- Notification both directions: red files one issue, a second red comments rather than duplicating, green closes it.
- Runner death: dispatch `collatz-rs` with `MUTANTS_UNCAPPED: 1` in the workflow env to reproduce the pre-fix OOM, and confirm `notify` still files an issue from its own runner with no artifact present.

---

### Task 1: ADR-0024 for the cap and classification contract

```yaml-task
id: 1
description: Record the memory-cap and stateless-classification decision as an ADR (docs-only, no behaviour change)
role: executor
model: haiku
tdd: not-applicable
acceptance:
  - cmd: test -f docs/adr/0024-mutation-testing-memory-cap.md
    exit_code: 0
  - cmd: 'grep -q "^\*\*Status:\*\* Accepted" docs/adr/0024-mutation-testing-memory-cap.md'
    exit_code: 0
max_retries: 3
files_touched:
  - docs/adr/0024-mutation-testing-memory-cap.md
depends_on: []
```

**TDD waiver:** documentation only.

**Files:** `docs/adr/0024-mutation-testing-memory-cap.md` (next free number; 0023 is the highest existing).

**Content**, Nygard format:

- **Context** — six consecutive failures, all exit 143 from runner death; `cargo mutants --timeout` is wall-clock with no memory bound; an allocation-unbounded mutant exhausts 16 GB well inside 30 seconds. Cite the collatz measurement table from the spec.
- **Decision** — cap address space at 8 GiB via `ulimit -v` in each crate's `Makefile` (not the workflow, so local and CI share one source of truth); classify on `outcomes.json` counts with the stateless rule `red if (caught + missed) == 0`; `MUTANTS_UNCAPPED=1` opts out, checked before the `ulimit`.
- **Consequences** — a runaway mutant is recorded CAUGHT rather than killing the runner; exit 2 and 3 are green because survivors and timeouts are the expected steady state; partial cap starvation is checked once at merge and not monitored after, with the `unviable` count surfaced in the job summary as the only ongoing signal; macOS cannot enforce `ulimit -v`, so local runs fail closed with an explicit override.
- **Related** — ADR-0022 (cosmic-ray), and the spec path.

Add the row to `docs/adr/README.md` in a later task (Task 8), not here — that file is outside this task's `files_touched`.

**Interfaces:**

- Consumes: nothing.
- Produces: the ADR path referenced by Task 8's index row.

---

### Task 2: Memory cap in all 11 crate Makefiles

```yaml-task
id: 2
description: Replace each crate's mutants target with a single-shell recipe carrying the memory cap, the override, and timeout 30
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'test "$(grep -c -- "--timeout 30 --no-shuffle" */*-rs/Makefile | grep -c ":1$")" -eq 11'
    exit_code: 0
  - cmd: 'test "$(grep -l "MUTANTS_UNCAPPED" */*-rs/Makefile | wc -l | tr -d " ")" -eq 11'
    exit_code: 0
  - cmd: '! grep -q -- "--timeout 120" */*-rs/Makefile'
    exit_code: 0
  - cmd: 'make -n -C collatz/collatz-rs mutants > /dev/null'
    exit_code: 0
max_retries: 3
files_touched:
  - amicable/amicable-rs/Makefile
  - collatz/collatz-rs/Makefile
  - e/e-rs/Makefile
  - factorial/factorial-rs/Makefile
  - fib/fib-rs/Makefile
  - goldbach/goldbach-rs/Makefile
  - perfect-numbers/perfect-numbers-rs/Makefile
  - pi/pi-rs/Makefile
  - prime/prime-rs/Makefile
  - sq/sq-rs/Makefile
  - twin-primes/twin-primes-rs/Makefile
depends_on: []
```

**TDD waiver:** Makefile recipe change with no unit-testable logic of its own; behaviour is covered by the session-level dispatch and by Task 3's classifier tests. `make -n` is in the acceptance gate as a parse check only — per `ci.md`, dry-run does **not** validate recipe execution.

**Files:** all 11 listed above. Every one currently reads identically:

```make
mutants:
	cargo mutants --timeout 120 --no-shuffle
```

**Replace with** (identical in all 11):

```make
mutants:
	@bash -c 'if [ -n "$${MUTANTS_UNCAPPED}" ]; then \
	    printf "warning: MUTANTS_UNCAPPED set — running without a memory cap.\n" >&2; \
	  else \
	    ulimit -v 8388608 2>/dev/null || { \
	      printf "error: this platform cannot enforce a memory cap (ulimit -v unsupported).\n" >&2; \
	      printf "  An allocation-unbounded mutant will consume system memory until the OS intervenes.\n" >&2; \
	      printf "  Re-run with MUTANTS_UNCAPPED=1 to proceed anyway, or use the Linux path.\n" >&2; \
	      exit 1; }; \
	  fi; exec cargo mutants --timeout 30 --no-shuffle'
```

Three things are load-bearing and must not be "tidied":

1. **One recipe line.** Each `make` recipe line runs in its own shell, so a `ulimit` on one line and `cargo` on the next sets a limit in a shell that exits immediately — a probe presented as enforcement.
2. **`$${MUTANTS_UNCAPPED}`, doubled.** `$$` escapes to a literal `$` so the shell expands it at run time. `$(MUTANTS_UNCAPPED)` would be Make-time text substitution and expand to nothing.
3. **Override checked first**, not in the `ulimit` failure branch — otherwise it is never consulted on Linux and the flag means different things per platform.

Leave every other target in these files untouched.

**Interfaces:**

- Consumes: nothing.
- Produces: `make -C <crate> mutants` as the single entry point, honouring `MUTANTS_UNCAPPED`. Tasks 4 and 5 call it; Task 4's runner-death verification sets that variable.

---

### Task 3: The classifier and its BATS suite

```yaml-task
id: 3
description: Add scripts/mutation-classify.sh deciding green/red from outcomes.json counts, with full BATS coverage
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/mutation_classify.bats
    exit_code: 0
  - cmd: shellcheck scripts/mutation-classify.sh
    exit_code: 0
  - cmd: bash -n scripts/mutation-classify.sh
    exit_code: 0
  - cmd: make test-hooks
    exit_code: 0
max_retries: 3
files_touched:
  - scripts/mutation-classify.sh
  - tests/scripts/mutation_classify.bats
depends_on: []
```

**Files:** `scripts/mutation-classify.sh` (new), `tests/scripts/mutation_classify.bats` (new).

**Contract:** `mutation-classify.sh <exit_code> <outcomes_json_path> <label>`. Prints a one-line verdict to stdout, exits `0` green / `1` red. `<label>` is the crate or sub-project name, used in the message.

**Rules, in order:**

1. `outcomes.json` missing and exit code `0` → **green** ("no mutants to test"). This case is real: a `--in-diff` run whose diff has no mutable lines prints `INFO No mutants to filter`, exits 0, and writes no `mutants.out/` at all. Phase A never passes `--in-diff`, but the rule is written correctly now rather than rediscovered in Phase B.
2. `outcomes.json` missing and exit code non-zero → **red**.
3. `outcomes.json` present but unparseable → **red**.
4. `caught + missed == 0` → **red** ("nothing was evaluated"). Subsumes all-unviable, all-timeout, and zero-mutant.
5. exit code in `{0, 2, 3}` → **green**.
6. anything else (`4`, `143`, unknown) → **red**.

Green output always names `caught`, `missed`, `timeout`, and `unviable`. The `unviable` count is reported but never gated on — partial cap starvation is checked once at merge, and this line is the only ongoing signal that it has drifted.

**Structure** (sourcing guard so BATS can source without executing):

```bash
#!/usr/bin/env bash
readonly GREEN_EXIT_CODES=(0 2 3)

classify_mutation_run() {
    local exit_code="$1" outcomes="$2" label="$3"
    ...
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
classify_mutation_run "$@"
```

Parse with `jq -e`. Capture its status immediately on its own line — `local x=$(...)` discards the exit code (see `shell.md`).

**Tests — one behaviour per RED→GREEN cycle, both branches of every guard:**

- missing file + exit 0 → green; missing file + exit 2 → red
- unparseable JSON → red
- `caught=0, missed=0, unviable=5` + exit 0 → red (the measured all-unviable case)
- `caught=0, missed=0, timeout=7` + exit 3 → red (all-timeout)
- `total_mutants=0` → red
- `caught=36, missed=4, unviable=1` + exit 2 → green, output contains all four counts (the real collatz numbers)
- exit 0 with survivors → green; exit 3 with survivors → green
- exit 4 → red; exit 143 → red; exit 99 → red

Write fixtures as real JSON files in `BATS_TEST_TMPDIR`. Use `tests/helpers/common.bash` for `REPO_ROOT`.

**Interfaces:**

- Consumes: nothing.
- Produces: `scripts/mutation-classify.sh <exit_code> <outcomes_json> <label>`, exit 0 green / 1 red. Called by Tasks 4 and 5.

---

### Task 4: Rewrite mutation-testing.yml

```yaml-task
id: 4
description: Route the Rust workflow through make, classify each crate, and add a notify job on its own runner
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'python3 -c "import yaml; yaml.safe_load(open(''.github/workflows/mutation-testing.yml''))"'
    exit_code: 0
  - cmd: 'grep -q "make -C" .github/workflows/mutation-testing.yml'
    exit_code: 0
  - cmd: 'grep -q "mutation-classify.sh" .github/workflows/mutation-testing.yml'
    exit_code: 0
  - cmd: 'grep -q "issues: write" .github/workflows/mutation-testing.yml'
    exit_code: 0
  - cmd: '! grep -q -- "--timeout 30 --no-shuffle" .github/workflows/mutation-testing.yml'
    exit_code: 0
max_retries: 3
files_touched:
  - .github/workflows/mutation-testing.yml
depends_on: [2, 3]
```

**TDD waiver:** workflow configuration; the logic it invokes is covered by Task 3's BATS suite, and the runtime paths are covered by the session-level verification.

**Files:** `.github/workflows/mutation-testing.yml`.

**Changes to the `mutants` job:** keep the existing single job, the serial `find`-driven loop, `timeout-minutes: 360`, and the `crate` dispatch input. Replace the per-crate invocation so it goes through `make` and gets classified:

```bash
(cd "${crate_dir}" && make mutants); rc=$?
mkdir -p "${GITHUB_WORKSPACE}/status"
slug="$(printf '%s' "${crate_dir#./}" | tr '/' '-')"
if "${GITHUB_WORKSPACE}/scripts/mutation-classify.sh" \
     "${rc}" "${crate_dir}/mutants.out/outcomes.json" "${crate_dir}" \
     | tee -a "${GITHUB_STEP_SUMMARY}" "${GITHUB_WORKSPACE}/status/${slug}"; then
  :
else
  failed=1
fi
```

`rc=$?` is captured on its own line immediately after the command — inside a pipeline it would be the last stage's status (`shell.md`). Keep the existing `exit "${failed}"` at the end.

The upload step stays `if: always()` and additionally uploads `status/`.

The upload step's `path:` gains `status/` alongside the existing `**/mutants.out/`.

**Interfaces:**

- Consumes: `make -C <crate> mutants` (Task 2), `scripts/mutation-classify.sh` (Task 3).
- Produces: artifact `mutants-output` containing `mutants.out/` trees plus `status/<slug>` files whose first word is `green` or `red`. Task 5's notify job reads them; ai-config's `mutation_review.py --artifact mutants-output` reads the `outcomes.json` files.

---

### Task 5: Notify job for the Rust workflow

```yaml-task
id: 5
description: Add a notify job on its own runner that files, comments on, and closes a labelled tracking issue
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'python3 -c "import yaml; d=yaml.safe_load(open(''.github/workflows/mutation-testing.yml'')); assert ''notify'' in d[''jobs'']"'
    exit_code: 0
  - cmd: 'grep -q "issues: write" .github/workflows/mutation-testing.yml'
    exit_code: 0
  - cmd: 'grep -q "in:title" .github/workflows/mutation-testing.yml'
    exit_code: 0
  - cmd: 'grep -q "needs.mutants.result" .github/workflows/mutation-testing.yml'
    exit_code: 0
max_retries: 3
files_touched:
  - .github/workflows/mutation-testing.yml
depends_on: [4]
```

**TDD waiver:** workflow configuration; behaviour is verified by the session-level notification checks, both directions plus the runner-death path.

**Files:** `.github/workflows/mutation-testing.yml`.

**Why a separate job:** SIGTERM skips `if: always()` **steps** inside the job it kills — that is precisely why six months of artifacts never uploaded. An in-job notification step therefore cannot report runner death or a job timeout, which are the two failure classes with no other output. A separate job runs on a fresh runner and survives.

```yaml
notify:
  needs: [mutants]
  if: always()
  runs-on: ubuntu-latest
  permissions:
    issues: write
  steps:
    - uses: actions/checkout@v6
    - uses: actions/download-artifact@v7
      continue-on-error: true
      with:
        name: mutants-output
        path: artifact
    - name: File, comment, or close the tracking issue
      env:
        GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        RESULT: ${{ needs.mutants.result }}
        RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
      run: |
        set -u
        title="mutation-testing: monthly run failed"
        existing=$(gh issue list --state open --label mutation-failure \
          --search "in:title \"${title}\"" --json number --jq '.[0].number // empty')

        if [[ "${RESULT}" == "success" ]]; then
          if [[ -n "${existing}" ]]; then
            gh issue comment "${existing}" --body "Green as of ${RUN_URL}. Closing."
            gh issue close "${existing}"
          fi
          exit 0
        fi

        if [[ -d artifact/status ]]; then
          crates=$(grep -l '^red' artifact/status/* 2>/dev/null \
            | xargs -r -n1 basename | sed 's/^/- /')
          detail="Failing crates:"$'\n'"${crates:-- (none flagged; see run log)}"
        else
          detail="No artifact was produced. The runner was terminated (exit 143) or the job timed out, so the failing crate cannot be attributed from CI alone — inspect the run log."
        fi
        body="Run: ${RUN_URL}"$'\n\n'"${detail}"

        if [[ -n "${existing}" ]]; then
          gh issue comment "${existing}" --body "${body}"
        else
          gh label create mutation-failure --color B60205 \
            --description "Monthly mutation run failed" 2>/dev/null || true
          gh issue create --title "${title}" --label mutation-failure --body "${body}"
        fi
```

Three details are load-bearing:

1. **`in:title "…"` with the inner quotes.** This is the exact-phrase fix from #89; a bare search substring-matches unrelated issues and would comment on the wrong one.
2. **`continue-on-error: true` on the download.** The no-artifact case is not an error — it is the runner-death signal, and the step after it must still run.
3. **The `else` branch says the crate is unattributable** rather than guessing. In Phase A the mutation job uploads once, at the end, so SIGTERM leaves no artifact at all — not a partial set. Per-crate attribution on a dead runner needs one runner per crate, which is the matrix, which is Phase B.

**Interfaces:**

- Consumes: `status/<slug>` files and the `mutants-output` artifact from Task 4; `needs.mutants.result`.
- Produces: the notify-job shape Task 6 copies for the Python workflow.

---

### Task 6: Rewrite mutation-testing-python.yml

```yaml-task
id: 6
description: Delete the || true swallow, upload the session sqlite, classify each sub-project, and add the same notify job
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'python3 -c "import yaml; yaml.safe_load(open(''.github/workflows/mutation-testing-python.yml''))"'
    exit_code: 0
  - cmd: '! grep -q "mutants || true" .github/workflows/mutation-testing-python.yml'
    exit_code: 0
  - cmd: 'grep -q "cosmic-ray-session.sqlite" .github/workflows/mutation-testing-python.yml'
    exit_code: 0
  - cmd: 'grep -q "issues: write" .github/workflows/mutation-testing-python.yml'
    exit_code: 0
max_retries: 3
files_touched:
  - .github/workflows/mutation-testing-python.yml
depends_on: [3, 5]
```

**TDD waiver:** workflow configuration, as Task 4.

**Files:** `.github/workflows/mutation-testing-python.yml`.

**Changes:**

1. Delete `|| true` from `make -C "${dir}" mutants || true`. It made the workflow green regardless of what happened — its 2026-08-01 "success" carried no information. Capture `rc=$?` on its own line and set `failed=1`, mirroring Task 4's loop, so one sub-project's failure still lets the rest run.
2. Parse the survivor count into the summary: `cr-report cosmic-ray-session.sqlite | grep -c 'Outcome.SURVIVED'` (guard with `|| true` on the `grep` only — a zero count is not an error), and write a per-sub-project line to `$GITHUB_STEP_SUMMARY` and `status/<dir>`.
3. Red only when `make mutants` fails or the sqlite is absent. Survivors never turn it red — cosmic-ray has no `--in-diff` and every sub-project has pre-existing survivors.
4. Upload path becomes `**/cosmic-ray-session.sqlite` **in addition to** `**/mutants-report.txt`. The consumer reads the sqlite and it has never been uploaded, which is why the cosmic-ray path has never worked end to end.
5. Add the same `notify` job as Task 5, copied verbatim except: title `mutation-testing-python: monthly run failed`, download artifact `mutants-report-python`, `needs: [mutants]` referring to this file's own job, and "Failing sub-projects:" in the detail line. Same `mutation-failure` label, same `in:title` dedup, same three states.

`scripts/mutation-classify.sh` is **not** used here — it reads `outcomes.json`, which is a cargo-mutants artifact. Python classification is the rule in point 3.

**Interfaces:**

- Consumes: Task 5's notify-job shape (copy it, adjusting title and artifact name).
- Produces: artifact `mutants-report-python` containing 8 sqlite files, consumed by ai-config's cosmic-ray invocation.

---

### Task 7: Update CLAUDE.md

```yaml-task
id: 7
description: Correct the workflow count and the wrong root-cause note, and document the cap and override (docs-only)
role: executor
model: haiku
tdd: not-applicable
acceptance:
  - cmd: 'grep -q "MUTANTS_UNCAPPED" CLAUDE.md'
    exit_code: 0
  - cmd: '! grep -q "Thirty-nine workflow files" CLAUDE.md'
    exit_code: 0
  - cmd: 'grep -q "ulimit -v" CLAUDE.md'
    exit_code: 0
max_retries: 3
files_touched:
  - CLAUDE.md
depends_on: [4, 6]
```

**TDD waiver:** documentation only.

**Files:** `CLAUDE.md`.

**Changes:**

1. "Thirty-nine workflow files" → "Forty-one workflow files". Derived, not recalled: `ls .github/workflows | wc -l` returns 41.
2. In the mutation-testing section, replace the note attributing the failures to the 360-minute CI timeout plus infinite-loop mutations. That diagnosis was wrong — time was never the binding constraint, the job died 119 seconds in, and reducing `--timeout` from 120 to 30 did not help. State the real cause: no memory bound, so an allocation-unbounded mutant exhausts the runner well inside the per-mutant timeout.
3. Document the cap: `ulimit -v 8388608` lives in each crate's `Makefile` `mutants` target, so local and CI share one source of truth, and the per-mutant timeout is 30 in both.
4. Document `MUTANTS_UNCAPPED=1` — required on macOS, which cannot enforce `ulimit -v` and therefore fails closed; also the way to reproduce the pre-fix OOM deliberately.
5. Note that a red monthly run now files a labelled `mutation-failure` issue and a green run closes it.

**Interfaces:**

- Consumes: the behaviour built in Tasks 2-6.
- Produces: nothing downstream.

---

### Task 8: Index updates

```yaml-task
id: 8
description: Add the ADR index row and mark the plan in progress in the superpowers index (docs-only)
role: executor
model: haiku
tdd: not-applicable
acceptance:
  - cmd: 'grep -q "0024" docs/adr/README.md'
    exit_code: 0
  - cmd: make validate-plan PLAN=docs/superpowers/plans/2026-08-01-mutation-testing-phase-a.md
    exit_code: 0
max_retries: 3
files_touched:
  - docs/adr/README.md
depends_on: [1]
```

**TDD waiver:** index maintenance only.

**Files:** `docs/adr/README.md`.

**Change:** add the ADR-0024 row to the status table, matching the existing column layout, status `Accepted`, title "Mutation testing memory cap and stateless classification".

`docs/superpowers/README.md` already carries this plan's row from the spec commit; update its status to `In Progress` at dispatch and `Done` at merge as part of the normal flow, not in this task — that file is outside `files_touched` here to keep the haiku scope guard satisfied.

**Interfaces:**

- Consumes: Task 1's ADR file.
- Produces: nothing downstream.
