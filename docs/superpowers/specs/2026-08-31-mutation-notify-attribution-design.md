# Mutation-testing notify: attribute the failure instead of asserting one

Date: 2026-08-31
Status: Spec

## Problem

Both mutation workflows end in a `notify` job that files, comments on, or closes a
tracking issue. When the run is red, that job decides what to say about it with a single
boolean:

```bash
if [[ -d artifact/status ]]; then
  crates=$(grep -l '^red' artifact/status/* 2>/dev/null | xargs -r -n1 basename | sed 's/^/- /')
  detail="Failing crates:"$'\n'"${crates:-- (none flagged; see run log)}"
else
  detail="No artifact was produced. The runner was terminated (exit 143) or the job timed out, so the failing crate cannot be attributed from CI alone — inspect the run log."
fi
```

`.github/workflows/mutation-testing.yml:126-133` and
`.github/workflows/mutation-testing-python.yml:129-136`, identical apart from the noun.

The else branch is reachable by at least four distinct causes and states one of them as
fact. This is the two-valued-field failure described in `behavior.md`: the outcome space
has more members than the field chosen to report it, so the reporter collapses the
remainder into whichever member was written down first.

| #   | cause                                                                                                                                                                                         | today's message                                                                             |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| 1   | mutants job terminated; `if: always()` upload step never ran                                                                                                                                  | correct                                                                                     |
| 2   | job died before `mkdir -p "${GITHUB_WORKSPACE}/status"` — failed checkout, failed `cargo install cargo-mutants --locked`, or the `no crates found — refusing to report green` guard exiting 1 | wrong: asserts a runner kill for an install failure                                         |
| 3   | artifact uploaded containing `mutants.out/` but no `status/`                                                                                                                                  | wrong, and self-contradicting: claims no artifact was produced about one it just downloaded |
| 4   | `actions/download-artifact` v8 digest-mismatch failure, swallowed by `continue-on-error: true`                                                                                                | wrong                                                                                       |

Causes 2 and 3 are live today and predate v8. Cause 2 couples to the repo's separate
backlog item on 33 unpinned `cargo install` lines: a bad upstream `cargo-mutants` release
would produce an issue blaming the GitHub runner.

The deeper defect is that the sentence has no supporting field at all. `needs.mutants.result`
is `failure` for a SIGTERM and `failure` for an ordinary step failure alike, and the exit
code appears only in the run log, which the notify job never reads. The workflow asserts a
cause it has no instrument for.

### Why now

`actions/download-artifact` moved to v8 in #119 (`7e8241b`, 2026-08-24). The pinned tree at
`3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` carries a new input:

```yaml
digest-mismatch:
  description:
    "The behavior when a downloaded artifact's digest does not match the expected digest.
    Options: ignore, info, warn, error. Default is error which will fail the action."
  required: false
  default: "error"
```

Retrieved with `gh api "repos/actions/download-artifact/contents/action.yml?ref=3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"`.
Both call sites pair that new default with `continue-on-error: true`, adding cause 4 to a
branch that already misreported causes 2 and 3. The crons are `0 4 1 * *` (Rust) and
`0 6 1 * *` (Python), so 2026-09-01 is the first execution under v8.

There is no false-clean here: the verdict comes from `needs.mutants.result`, not from the
artifact. The cost is entirely diagnostic — an issue that names a cause which did not
occur, which is what sent ADR-0024's original investigation after the 360-minute job
timeout instead of the missing memory bound.

## Measurements

All figures below were taken on 2026-08-31 against `brujack/math`.

### The step conclusions discriminate; durations are not needed

`ci.md` documents identical job durations and `started_at == run created_at` as the tell
for a runner-reaped job. That heuristic is unnecessary here, because the jobs API carries
per-step conclusions directly:

```
gh api "repos/brujack/math/actions/runs/<id>/jobs" \
  --jq '.jobs[]|select(.name=="Mutation testing")|{conclusion, steps:[.steps[]|{name,conclusion}]}'
```

| run         | date                | `Run mutants` | `Upload mutants output` |
| ----------- | ------------------- | ------------- | ----------------------- |
| 28495704109 | 2026-07-01 cron     | `cancelled`   | `skipped`               |
| 30685027791 | 2026-08-01 cron     | `failure`     | `skipped`               |
| 30728417809 | 2026-08-02 dispatch | `failure`     | `skipped`               |
| 30728211305 | 2026-08-02 dispatch | `success`     | `success`               |

`if: always()` was present on the upload step in all four cases. That was verified by
reading the workflow file at each run's own `head_sha` rather than at `master`, because a
run executes the file at its own ref and reading master would have answered about a
different artifact:

```
gh api "repos/brujack/math/contents/.github/workflows/mutation-testing.yml?ref=<head_sha>"
```

All three failures returned `if: always()` at the upload step. Run 30728417809's log
confirms the mechanism directly: `##[error]Process completed with exit code 143`, preceded
by `ERROR interrupted` from cargo-mutants.

So `Upload: skipped` while `if: always()` is declared is evidence the job was terminated
before its post-steps ran.

### Boundary on that claim

The population measured is three failed runs, and **all three are exit-143 terminations**.
There is no sample in this repository of an ordinary, non-terminated `Run mutants` failure,
so the reverse implication — `Upload: success` means the job was not terminated — is
reasoned from documented `if: always()` semantics and from the single successful run above,
not measured against a negative case.

The design therefore prints the step conclusions it derived the verdict from, rather than
asserting a mapping that has not been falsified in both directions. A reader can disagree
with the attribution without opening the run.

### The permissions block blocks the whole approach

Both `notify` jobs declare:

```yaml
permissions:
  issues: write
```

Specifying `permissions` sets every unlisted scope to none, so the `GITHUB_TOKEN` in that
job cannot read the Actions API. Without adding `actions: read`, every probe returns 403
and the design is inert.

The basis for the two halves of that claim differs and is worth separating. That the block
lists only `issues: write` is measured — it is in the file. That an unlisted scope
therefore resolves to none is GitHub's documented behaviour for an explicit `permissions`
block, **not** something reproduced here; no run has been made to observe the 403. If it
were wrong the change would merely be one line smaller, and the probe would already work —
the design depends only on adding the scope being harmless, not on which way that goes.

## Design

### Extract the notify logic into `scripts/mutation-notify.sh`

The two notify blocks are near-identical shell embedded in YAML. Shell inside a `run:` block
cannot be tested, and this repo's Definition of Done requires boundary, error-path and
state-transition tests for new logic. Extraction is what makes the change gateable; it is
not a tidiness preference, and it is the only reason the change touches a new file at all.

Three consequences follow from that placement, all of which favour it:

- `tests/mocks/gh` already exists and already logs every invocation to `MOCK_CALLS_FILE`,
  which is the harness needed to assert on issue-body content rather than on a return code.
- `scripts/*.sh` is inside the `bash-coverage` instrumented predicate, so a tested script
  raises the reachable quarter of that measurement. An untested one would lower the reported
  figure — honest in either direction, but there is no reason to choose the lower one.
- `lint-hooks` shellcheck picks the file up automatically through its `git ls-files`-derived
  scope; no scope list needs editing.

The script reads its inputs from the environment and owns the entire decision — green-close,
red-attribute, issue create versus comment:

| variable                    | meaning                                                               |
| --------------------------- | --------------------------------------------------------------------- |
| `RESULT`                    | `needs.mutants.result`                                                |
| `DL_OUTCOME`                | the download step's `outcome` (requires an `id:` on that step)        |
| `RUN_ID`, `REPO`, `RUN_URL` | run identity, for the probe and the issue body                        |
| `ARTIFACT_DIR`              | where the artifact was downloaded (`artifact`)                        |
| `ISSUE_TITLE`               | `mutation-testing: monthly run failed` / `mutation-testing-python: …` |
| `UNIT_NOUN`                 | `crate` / `sub-project`                                               |
| `JOB_NAME`                  | `Mutation testing` / `Python mutation testing`                        |

`UNIT_NOUN`, `ISSUE_TITLE` and `JOB_NAME` are the only differences between the two callers,
so both workflows collapse onto one implementation.

### Workflow changes, per file

```yaml
notify:
  needs: [mutants]
  if: always()
  runs-on: ubuntu-latest
  permissions:
    issues: write
    actions: read # NEW — without it the jobs API returns 403
  steps:
    - uses: actions/checkout@...
    - id: dl # NEW — makes steps.dl.outcome readable
      uses: actions/download-artifact@3e5f45b2... # v8
      continue-on-error: true
      with:
        name: mutants-output
        path: artifact
        digest-mismatch: error # NEW — explicit, not inherited
    - name: File, comment, or close the tracking issue
      env:
        GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        RESULT: ${{ needs.mutants.result }}
        DL_OUTCOME: ${{ steps.dl.outcome }}
        RUN_ID: ${{ github.run_id }}
        REPO: ${{ github.repository }}
        RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
        ARTIFACT_DIR: artifact
        ISSUE_TITLE: "mutation-testing: monthly run failed"
        UNIT_NOUN: crate
        JOB_NAME: "Mutation testing"
      run: scripts/mutation-notify.sh
```

`continue-on-error: true` stays. An absent artifact is a legitimate state that the notify
job exists in order to report, not an error that should take the job down — dropping it
would make a terminated mutants run produce two red jobs and no issue at all.

`digest-mismatch: error` keeps the current v8 behaviour and writes it down. Inheriting an
upstream default is how this defect arrived; an explicit value means a future change to
that default cannot move this workflow's behaviour with no diff to show for it.

### Attribution

The probe runs only on the red path, so the green path spends no API call:

```bash
jobs_json=$(gh api "repos/${REPO}/actions/runs/${RUN_ID}/jobs") || probe_rc=$?
```

Derived from it: the mutants job's `conclusion`; the first step whose conclusion is neither
`success` nor `skipped` (the last thing that actually ran); and the conclusion of the single
step whose name begins with `Upload`. Both workflows have exactly one such step
(`Upload mutants output` at `mutation-testing.yml:85` and `Upload mutants reports` at
`mutation-testing-python.yml:87`; `grep -c '^      - name: Upload'` returns 1 for each), so
the prefix match is stable across the pair without hardcoding either name. A third such
step added later would break the match silently, so the script fails loudly when the count
is not 1 rather than taking the first.

| upload step | `DL_OUTCOME` | `status/` | message                                                                                                                                                                            |
| ----------- | ------------ | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `skipped`   | any          | any       | Job terminated before the upload step ran — `if: always()` is declared on it and it did not execute. Last step to run: `<name>` (`<conclusion>`). The exit code is in the run log. |
| `failure`   | any          | any       | The artifact upload itself failed.                                                                                                                                                 |
| `success`   | `failure`    | —         | Artifact was uploaded but could not be downloaded — digest mismatch or a transient failure. See the notify job's download step.                                                    |
| `success`   | `success`    | absent    | Artifact contains no `status/` — the job failed before the `<UNIT_NOUN>` loop began. Failing step: `<name>`.                                                                       |
| `success`   | `success`    | present   | Normal red: name the failing `<UNIT_NOUN>`s from `status/`.                                                                                                                        |

Every body carries the line its verdict was derived from:

```
Evidence — mutants job: failure · last step run: Run mutants (failure) · upload step: skipped · download step: failure
```

Two error-path rules, both following from the class of defect being fixed.

**The probe's own failure gets its own branch.** A `gh api` call that 403s, hits a rate
limit, or returns unparseable JSON must produce _"attribution probe failed (rc=N) — inspect
the run log"_ and name no cause. A bare `||` falling through into the termination message
would recreate the original bug one layer up, which is the specific hazard `behavior.md`
describes as a guard branch absorbing the guard's own failure.

**No branch asserts exit 143.** The jobs API does not carry an exit code. `Upload: skipped`
is evidence of termination and the body says so in those terms. Removing the claim the
workflow cannot support is the substance of this change; the branch table is how it stays
useful afterwards.

## Testing

`tests/scripts/mutation_notify.bats`, following the existing `ci_gate.bats` pattern.

### The shared `gh` mock needs two dispatch arms

`tests/mocks/gh` currently branches on `check-runs` and `pulls` and sends everything else to
a single `MOCK_GH_OUTPUT`. The script under test issues two structurally different calls —
`gh api .../actions/runs/<id>/jobs` and `gh issue list` — which would both collect the same
fixture, making every assertion meaningless. Add:

- `*"actions/runs"*` → `MOCK_GH_JOBS`
- `*"issue "*` → `MOCK_GH_ISSUE_LIST`

placed ahead of the existing fallback so the change is purely additive. Neither pattern
appears in anything `ci_gate.bats` sends, but that suite is the regression check for this
edit and must actually be re-run rather than reasoned about.

### Case matrix

| #   | inputs                                                         | assertion                                                        |
| --- | -------------------------------------------------------------- | ---------------------------------------------------------------- |
| 1   | `RESULT=success`, open issue exists                            | comments, then closes, in that order                             |
| 2   | `RESULT=success`, no open issue                                | exits 0 with no `gh issue` write at all                          |
| 3   | upload `skipped`                                               | body states terminated-before-upload and names the last step run |
| 4   | upload `failure`                                               | body states the upload failed                                    |
| 5   | upload `success`, `DL_OUTCOME=failure`                         | body states uploaded-but-not-downloadable                        |
| 6   | upload `success`, dl `success`, no `status/`                   | body states the job died before the loop                         |
| 7   | full artifact with a `^red` status file                        | **body names that specific crate**                               |
| 8a | jobs API exits non-zero | body states the probe failed with its rc, and names no cause |
| 8b | jobs API returns malformed JSON | same: probe-failed body, no cause named |
| 9 | `status/` present with no `^red` line | preserves today's `(none flagged; see run log)` |
| 10 | red path with an existing open issue | comments; does not create a second issue |
| 11 | more than one step whose name begins with `Upload` | script fails loudly rather than matching the first |
| 12 | `RESULT=cancelled` | files an issue, as today — see below |

**Case 7 is the positive control and is not optional.** Cases 3 through 6 and case 8 all
assert on the content of a failure message, so a script emitting an empty body would satisfy
every one of them — the same shape as a verification suite whose cases all expect the same
verdict. Case 7 pins a specific derived value and is the only case that fails if `status/`
parsing silently produces nothing.

Case 8 must also assert the negative — that no cause string appears in the body. A probe
failure falling through into an attribution is the original defect reintroduced, and only an
absence assertion detects it.

### One preserved behaviour, stated rather than inherited

The current script treats every `RESULT` other than `success` as red, so a manually
cancelled run files a "monthly run failed" issue. `needs.mutants.result` is `cancelled` in
that case, distinct from the `failure` that a terminated job produced in every run measured
above, so the two are separable if that is ever wanted.

This spec preserves the existing behaviour unchanged and case 12 pins it. Changing it is a
different decision about what the tracking issue is for, and folding it into a change about
misattribution would make both harder to review.

### Failure-mode safety

Every case runs with `tests/mocks/` prepended to `PATH`, and the script resolves `gh` through
`PATH` with no absolute-path default. Both halves are required: a `PATH` mock does not shadow
an absolute path, and a script that reached the real `gh` would call `gh issue create` against
a live repository on the day the test regresses. `REPO` is set to a fixture value in every
case so that the destructive branch fails at an earlier guard rather than reaching
`brujack/math`.

## Verification

Runnable before implementation:

- `gh api "repos/actions/download-artifact/contents/action.yml?ref=3e5f45b2..."` — confirms
  `digest-mismatch` exists with `default: 'error'`. Run; output quoted above.
- `gh api "repos/brujack/math/actions/runs/<id>/jobs"` across the four runs above — confirms
  per-step conclusions are available and discriminate. Run; table above.
- `grep -n -A2 "Upload mutants output"` against each run's `head_sha` — confirms
  `if: always()` was present, so `skipped` is meaningful. Run; all three positive.

Requires the implementation:

- `bats tests/scripts/mutation_notify.bats` — all ten cases green, case 7 naming a crate.
- `bats tests/scripts/ci_gate.bats` — unchanged behaviour after the mock edit.
- `make lint` — shellcheck clean on the new script at default severity.
- `make bash-coverage` — the reported figure does not fall below the `FLOOR=24` gate.
- A `workflow_dispatch` run of each workflow with a deliberately failing crate, confirming
  the green path and at least one red branch end to end. The dispatch input `crate` already
  exists for exactly this.

## Scope

In scope: the two mutation workflows' `notify` jobs, the extracted script, its tests, and the
two new arms on the shared `gh` mock.

Out of scope, and each is an existing backlog row rather than a deferral introduced here:

- Pinning the 33 unpinned `cargo install` lines. It is one input to cause 2, and this change
  makes that cause legible rather than fixing it.
- Any change to `scripts/mutation-classify.sh` or to the red/green rules. This change alters
  what the issue _says_, never what the run _decides_.
- The `mutation-pr.yml` workflow, which has no notify job.

## Timing

The crons fire at 04:00 and 06:00 UTC on 2026-09-01, hours from this spec, so the change
will very likely not land first. That is not a blocker — the current behaviour produces a
misattributed issue body, not a wrong verdict. A run under the old text is mildly useful:
its jobs API response becomes a real fixture to check the branch table against, rather than
a hand-built one.
