# Mutation Notify Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the mutation workflows' tracking issue report a cause the run actually attested, instead of asserting a runner kill the workflow has no field to observe.

**Architecture:** The mutants job writes `marker/job-began` immediately after checkout and before `cargo install`, and uploads it alongside `status/` and `**/mutants.out/`. The notify job's decision logic moves out of YAML into `scripts/mutation-notify.sh`, which keys on the marker's presence in the downloaded artifact — not on step conclusions read back through the Actions API, and not on the download step's outcome. Each arm emits a stable `Cause: <slug>` token that tests assert on, leaving the prose free to be reworded.

**Tech Stack:** GitHub Actions, bash, bats-core 1.14.0, `gh` CLI (mocked in tests via `tests/mocks/gh`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-31-mutation-notify-attribution-design.md`.
- Every `gh issue` and `gh label` call must carry `--repo "${REPO}"`. All six are repo-implicit today; `gh issue list --label mutation-failure --state open` returns an open #98, so a regressed test's reached branch is a live `gh issue comment 98`. (`tdd.md` E2.)
- No message may assert a cause the artifact does not attest, and no message may name exit 143 — the jobs API does not carry an exit code and nothing in notify reads the log.
- The discriminator is the marker's presence, never the download step's outcome. A missing artifact and a corrupt one must land in the same arm by the same test.
- `continue-on-error: true` stays on both download steps; `digest-mismatch: error` is stated explicitly.
- Shell per `shell.md`: `#!/usr/bin/env bash`, no `set -e`, `[[ ]]`, `${VAR}`, `printf` not `echo`, `snake_case()`, sourcing guard so bats can source without executing.
- Do NOT add `actions: read`, a jobs-API probe, or a job-identity selector. The spec deleted all three in round 2; re-introducing any of them reverts the design.
- Do NOT add a `concurrency:` block, fix the dedup lookup, or touch `scripts/mutation-classify.sh`. All three are backlog rows in `docs/superpowers/README.md`.

**Base-tree state, measured 2026-09-01 before this plan was written:**

```
make lint                              exit 0  ("All checks passed!", 23 files formatted)
ls scripts/mutation-notify.sh          No such file or directory
ls tests/scripts/mutation_notify.bats  No such file or directory
bats tests/scripts/mutation_notify.bats  exit 1   <- MISSING FILE, not a real failure
```

**That last line is why every task pairs a `test -f` gate with its `bats` gate.** bats exits 1 for an absent file, which is indistinguishable from a failing suite. The `test -f` entry is what makes "the gate could not run" report differently from "the gate ran and found the defect".

## Session-level verification

Beyond the per-task gates, the completed change is proven by:

- **Command:** `make test` at the repo root (runs `lint` → `test-hooks` → `test-python`).
- **Expected:** exit 0, with `tests/scripts/mutation_notify.bats` contributing its cases to the bats total and `tests/scripts/ci_gate.bats` unchanged.
- **Command:** `bash scripts/run-bash-coverage.sh` via `make bash-coverage`.
- **Expected:** not below `FLOOR=24`. `scripts/mutation-notify.sh` joins the instrumented set automatically through the `git ls-files 'scripts/*.sh'` predicate, and arrives tested, so the figure should rise rather than fall.
- **Edge cases that must be exercised:** an artifact with no marker (both when the download failed and when it succeeded — same token, different inputs); two red crates in one `status/` directory; a `status/` directory with no `^red` line.
- **Post-merge, not a gate:** one `workflow_dispatch` per workflow against a green crate, confirming `marker/` reaches the artifact and the normal-red path is unaffected. Against a green crate this writes nothing to the issue tracker.

---

### Task 1: Add an `issue` dispatch arm to the shared `gh` mock

```yaml-task
id: 1
description: Add an additive issue arm to tests/mocks/gh so issue lookups and jobs-free calls return distinct fixtures
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: make test
    exit_code: 0
  - cmd: bats tests/scripts/ci_gate.bats
    exit_code: 0
max_retries: 3
files_touched:
  - tests/mocks/gh
depends_on: []
```

`tdd: not-applicable` — this is test-harness infrastructure with no production behaviour of its own; its correctness is established by `ci_gate.bats` continuing to pass and by Task 2's suite consuming it.

**Files:** `tests/mocks/gh`

Current dispatch, in order: a `MOCK_GH_EXIT` check _before_ any dispatch, then `*"check-runs"*`, then `*"pulls"*`, then a `MOCK_GH_OUTPUT` fallback.

Add one arm before the fallback, matching on `$1` rather than `$*`:

```bash
elif [[ "$1" == "issue" ]]; then
    printf '%s\n' "${MOCK_GH_ISSUE_LIST:-}"
```

**Match on `$1`, not `$*`.** A body containing a run URL (`.../actions/runs/123`) would otherwise be matched by any substring arm, making arm order load-bearing. `$1` is the subcommand and cannot collide.

Leave the pre-dispatch `MOCK_GH_EXIT` check exactly as it is. No per-arm exit variable is needed — the design has no API probe, so no test needs one `gh` call to fail while another succeeds. This is what makes the edit additive, unlike the version the spec's round 1 proposed.

**Interfaces:**

- Consumes: nothing.
- Produces: `MOCK_GH_ISSUE_LIST` — a string returned verbatim for any `gh issue …` invocation. Empty (the default) means "no open issue found". Task 2 and Task 3 set it.

---

### Task 2: Red-path attribution in `scripts/mutation-notify.sh`

```yaml-task
id: 2
description: Create the notify script with the four artifact-keyed red-path arms and their bats cases
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: test -f scripts/mutation-notify.sh
    exit_code: 0
  - cmd: test -f tests/scripts/mutation_notify.bats
    exit_code: 0
  - cmd: bats tests/scripts/mutation_notify.bats
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched:
  - scripts/mutation-notify.sh
  - tests/scripts/mutation_notify.bats
depends_on: [1]
```

**Files:** `scripts/mutation-notify.sh` (new), `tests/scripts/mutation_notify.bats` (new)

Environment inputs: `RESULT`, `DL_OUTCOME`, `ARTIFACT_DIR`, `RUN_URL`, `ISSUE_TITLE`, `UNIT_NOUN`, `REPO`.

Red-path decision, keyed on the artifact and nothing else:

```bash
attribute() {
    local _dir="${ARTIFACT_DIR}"
    if [[ ! -d "${_dir}/marker" ]]; then
        printf 'no-attestation'
    elif [[ -d "${_dir}/status" ]]; then
        printf 'verdicts-present'
    elif compgen -G "${_dir}/**/mutants.out" > /dev/null 2>&1 \
      || find "${_dir}" -type d -name mutants.out -print -quit | grep -q .; then
        printf 'loop-began-no-verdict'
    else
        printf 'died-before-loop'
    fi
}
```

`DL_OUTCOME` is **not** read by `attribute()`. A failed download leaves `ARTIFACT_DIR` without a `marker/`, so it reaches `no-attestation` by the same test as an empty or marker-less artifact. That is the point: `download-artifact` may fail on a missing artifact or succeed having downloaded nothing, and the design must not depend on which.

Bodies, each opening with its token on its own line:

| token                   | body                                                                                                                                                                                                                       |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `verdicts-present`      | `Failing <UNIT_NOUN>s:` then one `- <name>` per `status/` file whose first line matches `^red`. When none match, the existing `- (none flagged; see run log)`.                                                             |
| `loop-began-no-verdict` | The loop began and no verdict was written. At least one `<UNIT_NOUN>` ran `make mutants`; the job stopped before the first status file was written.                                                                        |
| `died-before-loop`      | The job ran and failed before the loop. Checkout succeeded and it did not reach the first `make mutants`. The failing step is in the run log.                                                                              |
| `no-attestation`        | The job's own reporting never ran. One of: terminated before the upload step; a checkout failure before the marker was written; the upload itself failed; the artifact was corrupt on download. None of these is asserted. |

Every body ends with `Run: ${RUN_URL}`.

Bats cases (fixtures are real directories under `BATS_TEST_TMPDIR`; no API response is mocked):

- `red, marker/ + status/ with one ^red file` → token `verdicts-present` **and the crate's name appears in the body**
- `red, marker/ + status/ with two ^red files` → **both** names appear
- `red, marker/ + status/ with no ^red line` → `- (none flagged; see run log)`
- `red, marker/ + <crate>/mutants.out/, no status/` → token `loop-began-no-verdict`
- `red, marker/ only` → token `died-before-loop`
- `red, DL_OUTCOME=failure, ARTIFACT_DIR empty` → token `no-attestation`
- `red, DL_OUTCOME=success, artifact populated but no marker/` → token `no-attestation`, **same token as the previous case**

**The two-`^red`-crates case is a required positive control and must not be reduced to a token assertion.** Every other red case asserts only that a token appears, so a script emitting the right token and an empty body satisfies all of them. Naming both crates pins a value derived from fixture content and is the only case that fails if the `status/` parsing silently produces nothing. The one-crate and two-crate cases together also prove the derivation enumerates rather than returning a fixed string.

**The last two cases must assert the same token.** That is what proves the marker, not `DL_OUTCOME`, is the discriminator. If they diverge, the script is reading the download outcome.

Shell requirements: sourcing guard (`[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0`) so bats can source and call `attribute()` directly; no `set -e`; `printf` not `echo`; `|| return 1` propagation.

**Interfaces:**

- Consumes: `MOCK_GH_ISSUE_LIST` from Task 1 (unused in this task's cases, which make no `gh` call).
- Produces: `attribute()` returning one of exactly `verdicts-present|loop-began-no-verdict|died-before-loop|no-attestation` on stdout; `build_body <token>` returning the full issue body. Task 3 calls both.

---

### Task 3: Green path, tracker calls, and `--repo` on every one

```yaml-task
id: 3
description: Add the green-path close, the issue create/comment dispatch, and --repo on all six tracker calls
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/mutation_notify.bats
    exit_code: 0
  - cmd: 'bash -c ''n=$(grep -cE "gh (issue|label) " scripts/mutation-notify.sh); r=$(grep -E "gh (issue|label) " scripts/mutation-notify.sh | grep -c -- "--repo"); [ "$n" -gt 0 ] && [ "$n" -eq "$r" ]'''
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched:
  - scripts/mutation-notify.sh
  - tests/scripts/mutation_notify.bats
depends_on: [2]
```

**Files:** `scripts/mutation-notify.sh`, `tests/scripts/mutation_notify.bats`

> **Gate corrected 2026-09-01, before dispatch.** The original form was
> `! grep -nE "gh (issue|label) [a-z]+" … | grep -qv -- "--repo"`, which passes vacuously
> when the first `grep` matches nothing — the state the task starts in. It also used the
> `-q`+`-v` combination `shell.md` records as diverging between the ugrep an agent shell
> resolves and the POSIX grep CI runs. The replacement counts both sides and requires the
> count to be non-zero and equal, so an empty result now fails.

Add `main "$@"` as the file's final statement — the sourcing guard is currently last, so `&&` short-circuits and direct execution exits 1, which is exactly how Task 4 invokes it. Then port the existing dispatch from `mutation-testing.yml:113-142` unchanged in behaviour, adding `--repo "${REPO}"` to all six calls: `gh issue list`, `gh issue comment` (green), `gh issue close`, `gh issue comment` (red), `gh label create`, `gh issue create`.

The lookup keeps `--search "in:title \"${ISSUE_TITLE}\""` exactly as it is. Its index dependency is a backlog row and **must not** be fixed here.

Bats cases:

- `RESULT=success` with `MOCK_GH_ISSUE_LIST=98` → comments then closes; **assert every logged `gh` call contains `--repo`**
- `RESULT=success` with `MOCK_GH_ISSUE_LIST=` → exits 0 with **no** `gh issue` write in `MOCK_CALLS_FILE`
- `RESULT=cancelled` → files an issue, as today

**The green case is a characterization test and asserts nothing about whether closing is correct.** `math#100` is open and describes that path as a defect — a single-crate green run closed #98 while `pi-rs` and `e-rs` were still red, which the 2026-09-01 cron confirms is still true. Asserting comment-then-close as _intended_ would make #100 harder to fix, because a passing test reads as intent. Asserting nothing at all would leave `gh issue close`, the only destructive call, untested in a change whose purpose is to make it testable — and would drop the `--repo` assertion with it. So: assert `--repo` and the absence of a second issue; say nothing about the close being right. Put that reasoning in a comment above the case, naming #100.

`RESULT=cancelled` has never occurred — all four measured failures carry a **job** conclusion of `failure`, and `cancelled` is attested only at the step level. The case pins current behaviour without claiming the shape has been observed; say so in a comment.

**Failure-mode safety:** every case sets `REPO` to a fixture value and runs with `tests/mocks/` on `PATH`. The `--repo` flag is what actually protects — `PATH` alone does not, and a fixture `REPO` alone does not either unless the flag carries it.

**Interfaces:**

- Consumes: `attribute()` and `build_body()` from Task 2; `MOCK_GH_ISSUE_LIST` from Task 1.
- Produces: the complete script. Tasks 4 and 5 invoke it as `scripts/mutation-notify.sh` with no arguments.

---

### Task 4: Generalise the "loop began" probe so it is not cargo-mutants-specific

```yaml-task
id: 4
description: Replace attribute()'s mutants.out probe with a tool-agnostic test so the shared script attributes the Python workflow's artifact correctly
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/mutation_notify.bats
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched:
  - scripts/mutation-notify.sh
  - tests/scripts/mutation_notify.bats
depends_on: [3]
```

**Files:** `scripts/mutation-notify.sh`, `tests/scripts/mutation_notify.bats`

**Why this task exists.** `attribute()` decides `loop-began-no-verdict` by looking for a directory named `mutants.out`. That is a cargo-mutants artifact and the script is shared between both workflows. The Python workflow uploads `**/mutants-report.txt` and `**/cosmic-ray-session.sqlite` — `grep -c mutants.out .github/workflows/mutation-testing-python.yml` is **0**. So a cosmic-ray run that began the loop and wrote no verdict is currently attributed `died-before-loop`, which is false, and is exactly the class of wrong statement this whole change exists to remove. Measured 2026-09-01:

```
marker/ + pi/pi-rs/mutants.out         -> loop-began-no-verdict   (correct)
marker/ + amicable/mutants-report.txt  -> died-before-loop        (WRONG)
```

This is a spec defect, not an implementation miss — neither review could see it, because both were scoped to a diff and the evidence lives in the other workflow's upload path.

**The fix.** "The loop began" is *the artifact contains any entry other than `marker/` and `status/`*. No new environment variable, no per-workflow configuration, correct for both tools and for any tool added later:

```bash
if find "${_dir}" -mindepth 1 -maxdepth 1 ! -name marker ! -name status -print -quit | grep -q .; then
    printf 'loop-began-no-verdict'
    return 0
fi
```

Validated against five artifact shapes before this task was written — the three below plus `marker/` alone and `marker/` + empty `status/`, which must both stay `died-before-loop`.

**Tests.** Keep every existing case green. Add three that fail against the current implementation:

- `marker/` + `amicable/mutants-report.txt`, no `status/` → `loop-began-no-verdict`
- `marker/` + `amicable/cosmic-ray-session.sqlite`, no `status/` → `loop-began-no-verdict`
- `marker/` + an arbitrarily-named entry (e.g. `some-future-tool/output.json`) → `loop-began-no-verdict`, pinning that the probe is tool-agnostic rather than a longer list of known filenames

Verify the third by mutation: replacing the generalised probe with any fixed-name list must turn it red. A probe that merely adds `mutants-report.txt` and `cosmic-ray-session.sqlite` to a hardcoded set satisfies the first two cases and is the wrong fix.

Also update the comment above the `status/` non-empty guard, which currently says "Fall through to the mutants.out / died-before-loop checks below" and names a file that is no longer probed for.

**Interfaces:**

- Consumes: `attribute()` and `build_body()` from Tasks 2 and 3.
- Produces: no signature change. Tasks 5 and 6 invoke the script unchanged.

---

### Task 5: Wire `mutation-testing.yml` to the marker and the script

```yaml-task
id: 5
description: Add the marker step, extend the upload path, and replace the inline notify shell with the script in the Rust workflow
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: make test
    exit_code: 0
  - cmd: 'python3 -c "import yaml,sys; yaml.safe_load(open(''.github/workflows/mutation-testing.yml''))"'
    exit_code: 0
  - cmd: 'bash -c ''! grep -q "exit 143" .github/workflows/mutation-testing.yml'''
    exit_code: 0
max_retries: 3
files_touched:
  - .github/workflows/mutation-testing.yml
depends_on: [4]
```

`tdd: not-applicable` — workflow YAML has no unit-test surface in this repo, and a `grep` gate asserting the marker step's exact text would dictate its formatting rather than test it (see `writing-plans`, literal-match gates). Behaviour is covered by Task 2/3's suite plus the post-merge dispatch named in Session-level verification.

**Files:** `.github/workflows/mutation-testing.yml`

Three edits:

1. After the `actions/checkout` step and **before** `dtolnay/rust-toolchain`, add:

   ```yaml
   - name: Mark job start
     run: mkdir -p "${GITHUB_WORKSPACE}/marker" && date -u > "${GITHUB_WORKSPACE}/marker/job-began"
   ```

   Placement is load-bearing. After checkout so the workspace exists; before `cargo install` so a toolchain or install failure still leaves the breadcrumb. Every cause-2 route — the `no crates found` guard at lines 52-54, a failed `cargo install`, any failure inside `Run mutants` — then runs with the marker already on disk.

2. Add `marker/` to the upload step's `path:` list, beside `**/mutants.out/` and `status/`.

3. In `notify`, give the download step `id: dl` and `digest-mismatch: error`, keep `continue-on-error: true`, and replace the whole inline `run:` block with:

   ```yaml
   env:
     GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
     RESULT: ${{ needs.mutants.result }}
     DL_OUTCOME: ${{ steps.dl.outcome }}
     ARTIFACT_DIR: artifact
     RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
     ISSUE_TITLE: "mutation-testing: monthly run failed"
     UNIT_NOUN: crate
     REPO: ${{ github.repository }}
   run: scripts/mutation-notify.sh
   ```

Do **not** add `actions: read` — the permissions block stays `issues: write` only. Nothing reads the Actions API.

The `exit 143` gate is the one falsifiable assertion available here: that string is present on the base tree and must be gone.

**Interfaces:**

- Consumes: `scripts/mutation-notify.sh` from Task 3.
- Produces: nothing consumed by later tasks. Task 5 is the same change to the Python workflow and is independent of this one.

---

### Task 6: Wire `mutation-testing-python.yml` to the marker and the script

```yaml-task
id: 6
description: Add the marker step, extend the upload path, and replace the inline notify shell with the script in the Python workflow
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: make test
    exit_code: 0
  - cmd: 'python3 -c "import yaml,sys; yaml.safe_load(open(''.github/workflows/mutation-testing-python.yml''))"'
    exit_code: 0
  - cmd: 'bash -c ''! grep -q "exit 143" .github/workflows/mutation-testing-python.yml'''
    exit_code: 0
max_retries: 3
files_touched:
  - .github/workflows/mutation-testing-python.yml
depends_on: [4]
```

`tdd: not-applicable` — same justification as Task 5.

**Files:** `.github/workflows/mutation-testing-python.yml`

Identical to Task 5 with three substitutions: the marker step goes after checkout and before the `cosmic-ray` install; the artifact name is `mutants-report-python`; and the env block carries `ISSUE_TITLE: "mutation-testing-python: monthly run failed"` and `UNIT_NOUN: sub-project`.

Read the file's own step names rather than copying Task 5's — the upload step here is `Upload mutants reports`, not `Upload mutants output`, and its `path:` list differs.

**Interfaces:**

- Consumes: `scripts/mutation-notify.sh` from Task 3.
- Produces: nothing.

---

### Task 7: Documentation and index

```yaml-task
id: 7
description: Update CLAUDE.md's CI and bash-coverage sections, mark the spec Done, and fill the plan index row (docs-only, no behavior change)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: make test
    exit_code: 0
  - cmd: 'grep -q "mutation-notify.sh" CLAUDE.md'
    exit_code: 0
max_retries: 3
files_touched:
  - CLAUDE.md
  - docs/superpowers/README.md
  - docs/superpowers/specs/2026-08-31-mutation-notify-attribution-design.md
depends_on: [5, 6]
```

`tdd: not-applicable` — documentation only.

**Files:** `CLAUDE.md`, `docs/superpowers/README.md`, `docs/superpowers/specs/2026-08-31-mutation-notify-attribution-design.md`

- `CLAUDE.md`, Mutation testing section: replace the **Notification** bullet. It currently says a red run files or updates the issue and explains the `needs: [mutants], if: always()` split. Add that the body's cause comes from `scripts/mutation-notify.sh` keyed on a `marker/job-began` breadcrumb the mutants job writes before `cargo install`, that each arm emits a `Cause: <slug>` token, and that nothing reads the Actions API.
- `CLAUDE.md`, Bash Coverage section: the instrumented set moves from **26 files to 27** and tracked shell from 28 to 29. `scripts/mutation-notify.sh` joins via the existing `git ls-files 'scripts/*.sh'` predicate — no predicate edit. Update both counts and the `4 scripts/*.sh files` enumeration to five, naming the new file.
- `CLAUDE.md`, `tests/scripts/` bullet: add `mutation_notify.bats` to the list.
- `CLAUDE.md`, repo-level Python tests bullet: the stated **53 tests** is stale — measured
  2026-09-01, `python3 -m unittest discover -s tests` reports **51** (17 + 3 + 11 + 20 across
  the four files it names). Pre-existing drift, unrelated to this change, folded in here
  because this task is already correcting counts in the same file. Update the number and the
  as-of date; do not change the file list, which is still correct.
- Spec: change `Status: Spec` to `Status: Done`.
- `docs/superpowers/README.md`: fill the plan column of the `2026-08-31` row with a link to this plan, and set status to `Done`.

Do **not** touch the three backlog rows added during this spec's review (dedup, concurrency, the `black_box` convention).

**Interfaces:**

- Consumes: the completed implementation.
- Produces: nothing.
