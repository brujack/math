# Mutation-testing notify: attribute the failure instead of asserting one

Date: 2026-08-31
Status: Spec (revised after Multi-Lens Review round 1)

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

`.github/workflows/mutation-testing.yml:127-133` and
`.github/workflows/mutation-testing-python.yml:130-136`, identical apart from the noun.

The else branch is reachable by at least four distinct causes and states one of them as
fact. This is the two-valued-field failure described in `behavior.md`: the outcome space
has more members than the field chosen to report it, so the reporter collapses the
remainder into whichever member was written down first.

| #   | cause                                                                                                                                                                                       | today's message                                                                             |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| 1   | mutants job terminated; `if: always()` upload step never ran                                                                                                                                | correct                                                                                     |
| 2   | job died before `mkdir -p "${GITHUB_WORKSPACE}/status"` — failed checkout, failed `cargo install cargo-mutants --locked`, or the `no crates found — refusing to report green` guard exiting 1 | wrong: asserts a runner kill for an install failure                                         |
| 3   | artifact uploaded containing `mutants.out/` but no `status/`                                                                                                                                | wrong, and self-contradicting: claims no artifact was produced about one it just downloaded |
| 4   | `actions/download-artifact` v8 digest-mismatch failure, swallowed by `continue-on-error: true`                                                                                              | wrong                                                                                       |

Causes 2 and 3 are live today and predate v8. Cause 2 is confirmed structurally: the
`no crates found` guard exits at `mutation-testing.yml:52-54`, five lines **upstream** of
the `mkdir -p` at line 58, and no workflow sets `if-no-files-found`, so the default `warn`
applies and a guard trip produces no artifact at all. Cause 2 also couples to the repo's
separate backlog item on 33 unpinned `cargo install` lines: a bad upstream `cargo-mutants`
release would produce an issue blaming the GitHub runner.

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

### How often the misattribution actually fires: unmeasured, not rare

This distinction decides the sizing and an earlier draft of this spec got it wrong by
calling the rate "low". Low would license shrinking the design against a known number.
Unmeasured licenses only measuring or deferring.

```
$ gh run list --workflow mutation-testing-python.yml --limit 20 --json event,conclusion
2026-08-01 schedule success
2026-07-01 schedule success
2026-06-01 schedule success
```

The Python workflow has **3 runs, 3 successes, and has never gone red**. The Rust workflow
shows 9 failures in 14 runs, but 8 of the 14 are `workflow_dispatch` from one debugging
session on 2026-08-01/02; its scheduled population is 3, all of them predating the
ADR-0024 memory-cap fix that removed the dominant cause. So the post-fix rate of the
artifact-absent branch is **not known**, in either direction.

## Measurements

Figures below were taken on 2026-08-31 against `brujack/math` unless marked otherwise.

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

### Two gating measurements, NOT YET RUN

The four runs above are the entire evidence base and **all three failures are exit-143
terminations**, taken post-hoc, days to weeks after each run finished. Two claims the design
depends on are therefore unestablished, and neither can be settled by re-reading old runs.
They are gates on tier 3 below, not follow-ups.

**G1 — does `Upload: skipped` discriminate termination from an ordinary failure?** There is
no sample in this repository of a non-terminated `Run mutants` failure. If GitHub also
reports a post-step as `skipped` when a job fails without being reaped, the branch table's
top row misattributes a plain build failure as a runner kill — the original defect relocated
one layer down rather than fixed.

Settle it with a dispatch against a crate whose baseline tests fail, producing an ordinary
non-terminated failure, then read that run's `steps[]`.

**G2 — is `steps[]` populated with terminal conclusions at the instant `notify` queries it,
for a reaped job?** Every measurement here is post-hoc. "Terminal in the workflow graph, so
`needs:` released the dependent job" and "finalised in the REST API's `steps[]`" are
different guarantees, and the SIGTERM case is exactly where they would diverge — the runner
never reported step completion, so the service must backfill. If the array is empty or
non-terminal at that moment, **every** red path falls into the probe-failure branch and the
design delivers less than tier 1's string edit. That is an inversion, not a degradation.

G2 needs a genuinely reaped job, so a clean failing-baseline dispatch cannot answer it — that
run exercises the path where the runner did report. The reproduction recipe already exists
and has been exercised: run 30728417809 carried `MUTANTS_UNCAPPED: "1"` at its `head_sha`,
commented `# PROBE BRANCH ONLY - reproduces the pre-fix OOM`, and each crate's `mutants`
recipe branches on that variable to skip the `ulimit -v 8388608` cap. Confirmed that variable
appears in **zero** workflows on master, so the cap is on in CI as ADR-0024 intends and this
is a probe-branch technique rather than a live defect.

So G2 requires a probe branch carrying `MUTANTS_UNCAPPED: "1"` plus a temporary step in
`notify` dumping `gh api repos/${REPO}/actions/runs/${GITHUB_RUN_ID}/jobs`.
`mutation-testing.yml` is registered on master, so `gh workflow run --ref <probe-branch>`
runs the branch's copy (per `ci.md`, a workflow that exists *only* on a feature branch would
404 instead).

**Cost, stated because it is not one line.** G1 and G2 are two dispatches, one of them
needing a probe branch and a deliberately OOM-reaped runner. Both write to the live issue
tracker — that is how #92, #96, #98 and #99 came to exist. The plan must name the cleanup of
whatever issues they file.

### The permissions block blocks the whole approach

Both `notify` jobs declare:

```yaml
permissions:
  issues: write
```

Specifying `permissions` sets every unlisted scope to none, so the `GITHUB_TOKEN` in that
job cannot read the Actions API. Without adding `actions: read`, every probe returns 403.

The basis for the two halves of that claim differs. That the block lists only
`issues: write` is measured — it is in the file. That an unlisted scope therefore resolves
to none is GitHub's documented behaviour for an explicit `permissions` block, **not**
reproduced here; no run has observed the 403. If it were wrong the change is one line
smaller and the probe already works. The design depends only on adding the scope being
harmless.

## Design

Three tiers. Tier 1 stands alone and needs nothing measured. Tier 2 is deliberately not in
this spec. Tier 3 is gated on G1 and G2.

### Tier 1 — remove the unsupported claim (no new premises)

Replace each workflow's `else` detail string with one that enumerates rather than asserts:

```bash
  detail="No status/ directory in the artifact. That is reachable several ways — the job was
terminated before its upload step ran, it failed before the crate loop began, the upload
produced nothing, or the download failed. CI cannot tell them apart today; inspect the run log."
```

Two strings, two files, no new file, no permission change, no API call, no test surface.
This is the substance of the whole change: the current sentence's defect is that it asserts
a cause the workflow has no field for, and enumeration cures that completely. Tier 3
supersedes this text later; landing it first removes a false statement from master without
waiting on G1 and G2.

### Tier 2 — the dedup defect (backlogged, not in this spec)

`gh issue list --search 'in:title "..."'` depends on GitHub's issue **search index**, and
#99 was created 2026-08-02T02:13:37Z while #98 — identical title, identical label — was open
since 01:57:03Z and still is. The same lookup run 2026-08-31 returns `98`, so the query is
not broken; the index is the dependency, and `--label` filtering does not use it.

That is a live production defect affecting what the operator sees monthly, it is independent
of everything else here, and it is now a row in `docs/superpowers/README.md`'s Backlog. It is
named in this section only so a reader does not conclude the omission was an oversight.

**Consequence for tier 3's test matrix:** with the dedup path unchanged, no case may assert
comment-not-create as *correct*. See the preserved-behaviour rule below.

### Tier 3 — attribution (gated on G1 and G2)

**Extract the notify logic into `scripts/mutation-notify.sh`; the workflows call it.**

Shell inside a `run:` block cannot be tested, and this repo's Definition of Done requires
boundary, error-path and state-transition tests for new logic. Note the argument's shape
honestly: extraction is required *because tier 3 adds logic*, so it is a consequence of
choosing tier 3, not an independent reason to choose it. Tier 1 adds no logic and needs no
script.

Given tier 3, the placement is right for three further reasons: `tests/mocks/gh` already
logs every invocation to `MOCK_CALLS_FILE`, which is what allows assertions on issue-body
content rather than on a return code; `scripts/*.sh` is inside the `bash-coverage`
instrumented predicate, so a tested script raises the reachable quarter of that measurement;
and `lint-hooks` shellcheck picks the file up through its `git ls-files`-derived scope with
no scope list to edit.

Inputs from the environment:

| variable                   | meaning                                                     |
| -------------------------- | ----------------------------------------------------------- |
| `RESULT`                   | `needs.mutants.result`                                      |
| `DL_OUTCOME`               | the download step's `outcome` (requires an `id:`)           |
| `RUN_ID`, `REPO`, `RUN_URL`| run identity, for the probe and the issue body              |
| `ARTIFACT_DIR`             | where the artifact was downloaded (`artifact`)              |
| `ISSUE_TITLE`              | `mutation-testing: monthly run failed` / `…-python: …`      |
| `UNIT_NOUN`                | `crate` / `sub-project`                                     |

`JOB_NAME` is deliberately **absent** from that table. An earlier draft carried it, and it
was a duplicated reference: `jobs.mutants.name` in the YAML and `JOB_NAME` in the notify
`env` are two strings in one file with nothing forcing them equal, so a job rename yields
rc=0, well-formed JSON and an **empty selection** — a probe outcome distinct from both
"probe failed" and any real conclusion. Both workflows have exactly two jobs, so the
selector is `select(.name != "notify")` and the string is gone rather than duplicated.

**Every `gh issue` and `gh label` call takes `--repo "${REPO}"`.** All six are repo-implicit
today (`mutation-testing.yml:116,121,122,137,139,141`), so `gh` resolves from the checkout's
remote. This is a test-safety requirement rather than a production fix — with no script
there are no tests and nothing reaches the tracker — but under tier 3 it is load-bearing:
`gh issue list --label mutation-failure --state open` returns an open #98 right now, so a
regressed test's reached branch is `gh issue comment 98` on a live issue, not a create that
might fail. `tdd.md` E2. With `--repo` on every call, a fixture `REPO` fails at gh's own
resolution.

#### Workflow changes, per file

```yaml
  notify:
    needs: [mutants]
    if: always()
    runs-on: ubuntu-latest
    permissions:
      issues: write
      actions: read              # NEW — without it the jobs API returns 403
    steps:
      - uses: actions/checkout@...
      - id: dl                   # NEW — makes steps.dl.outcome readable
        uses: actions/download-artifact@3e5f45b2... # v8
        continue-on-error: true
        with:
          name: mutants-output
          path: artifact
          digest-mismatch: error # NEW — explicit, not inherited
```

`continue-on-error: true` stays: an absent artifact is a legitimate state the notify job
exists to report, and dropping it would make a terminated run produce two red jobs and no
issue at all.

`digest-mismatch: error` restates the v8 default, so **no verdict can differ because of it**
— it is documentation-as-config, not a fix, and is listed here rather than among the fixes.
It is kept because inheriting an upstream default is how this defect arrived.

#### Attribution

The probe runs only on the red path, so the green path spends no API call:

```bash
jobs_json=$(gh api "repos/${REPO}/actions/runs/${RUN_ID}/jobs") || probe_rc=$?
```

Derived: the mutants job's `conclusion`; the first step whose conclusion is neither
`success` nor `skipped` (the last thing that actually ran); and the conclusion of the single
step whose name begins with `Upload`. Both workflows have exactly one such step
(`Upload mutants output` at `mutation-testing.yml:85`, `Upload mutants reports` at
`mutation-testing-python.yml:87`; `grep -c '^      - name: Upload'` returns 1 for each). A
third such step added later would break the match silently, so the script fails loudly when
the count is not 1 rather than taking the first.

| upload step   | `DL_OUTCOME` | artifact                             | message                                                                                                                                    |
| ------------- | ------------ | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `skipped`     | any          | any                                  | The upload step did not run although `if: always()` is declared on it, which is how a terminated job presents. Last step to run: `<name>` (`<conclusion>`). The exit code is in the run log. |
| `failure`     | any          | any                                  | The artifact upload itself failed.                                                                                                          |
| `success`     | `failure`    | —                                    | Artifact uploaded but not downloadable — digest mismatch or a transient failure. See the notify job's download step.                        |
| `success`     | `success`    | no `status/`, no `mutants.out`       | No `<UNIT_NOUN>` was reached: the loop had not started. Failing step: `<name>`.                                                             |
| `success`     | `success`    | no `status/`, `mutants.out` present  | The loop began and no verdict was written. At least one `<UNIT_NOUN>` ran `make mutants`; the job stopped before the first `tee`.           |
| `success`     | `success`    | `status/` present                    | Normal red: name the failing `<UNIT_NOUN>`s.                                                                                                |
| anything else | any          | any                                  | The upload step's conclusion could not be determined (`<value or empty>`). Attribution unavailable; inspect the run log.                    |

Three properties of that table are deliberate and were not true of the previous draft.

**Row 1 is hedged, because the Boundary above says it must be.** The earlier draft asserted
"Job terminated before the upload step ran" as fact while its own measurements section
recorded that the reverse implication was unmeasured. That is the same distance between what
is known and what is said that this whole document is about. The row now states the
observation and names termination as how it presents. **G1 may allow the stronger wording;
until G1 runs, it may not.**

**The `mutants.out` split exists because the artifact discriminates.** Artifact upload elides
empty directories, so `status/` absent does not imply the loop never started: a run where
crate 1 produced `mutants.out/` and the job died before the first `tee` — under GitHub's
`bash -e`, a failing `tee` alone does it — lands here, and the single-row wording would have
been false. `artifact/**/mutants.out` present means the loop began. This was the previous
draft reproducing, in its own fix, the defect it was fixing.

**The last row is a real arm, not a fallback comment.** An empty or unrecognised conclusion
must not fall through into row 1. `cancelled` is attested in this repo — run 28495704109's
`Run mutants` is `cancelled` — so an enumeration of three values is not exhaustive over what
GitHub emits.

Every body carries the line its verdict was derived from:

```
Evidence — mutants job: failure · last step run: Run mutants (failure) · upload step: skipped · download step: failure
```

Two error-path rules follow from the class of defect being fixed.

**The probe's own failure gets its own branch.** A `gh api` that 403s, rate-limits, or
returns unparseable JSON produces *"attribution probe failed (rc=N) — inspect the run log"*
and names no cause. A bare `||` falling through into the termination message would recreate
the original bug one layer up.

**No branch asserts exit 143.** The jobs API does not carry an exit code. Removing the claim
the workflow cannot support is the substance; the branch table is how it stays useful
afterwards.

## Testing (tier 3)

`tests/scripts/mutation_notify.bats`, following the existing `ci_gate.bats` pattern.

### The shared `gh` mock needs three edits, and they are not all additive

Two output arms are additive: `*"actions/runs"*` → `MOCK_GH_JOBS` and an issue arm →
`MOCK_GH_ISSUE_LIST`, ahead of the existing fallback. Match on `$1` rather than `$*`,
because `gh issue comment --body "Run: …/actions/runs/123…"` would otherwise hit the
`actions/runs` arm and make arm order load-bearing.

The third is **not** additive and an earlier draft wrongly claimed the whole edit was.
`tests/mocks/gh:4` checks `MOCK_GH_EXIT` before any dispatch, so a non-zero exit applies to
every call — including the `gh issue` write whose body case 8a must assert on. Isolating a
failing probe needs a per-arm exit variable (`MOCK_GH_JOBS_EXIT`), which touches the branch
`ci_gate.bats` depends on. That suite is the regression check and must actually be re-run.

### Case matrix

| #   | inputs                                                | assertion                                                                    |
| --- | ----------------------------------------------------- | ---------------------------------------------------------------------------- |
| 2   | `RESULT=success`, no open issue                       | exits 0 with no `gh issue` write at all                                      |
| 3   | upload `skipped`                                      | body names the **literal last-step string from the fixture**, not the sentence |
| 4   | upload `failure`                                      | body states the upload failed, and its Evidence line names the fixture's step |
| 5   | upload `success`, `DL_OUTCOME=failure`                | body states uploaded-but-not-downloadable                                    |
| 6a  | upload `success`, dl `success`, no `status/`, no `mutants.out` | body states the loop had not started                                  |
| 6b  | upload `success`, dl `success`, no `status/`, `mutants.out` present | body states the loop began and no verdict was written            |
| 7   | full artifact with a `^red` status file               | **body names that specific crate**                                           |
| 8a  | `MOCK_GH_JOBS_EXIT` non-zero, issue calls unaffected  | body states the probe failed with its rc, **and names no cause**             |
| 8b  | jobs API returns malformed JSON                       | same: probe-failed body, no cause named                                      |
| 8c  | jobs JSON valid but the job selection is empty        | body states the conclusion could not be determined                           |
| 9   | `status/` present with no `^red` line                 | preserves today's `(none flagged; see run log)`                              |
| 11  | more than one step whose name begins with `Upload`    | script fails loudly rather than matching the first                           |
| 12  | `RESULT=cancelled`                                    | files an issue, as today — preserved behaviour, see below                    |
| 13  | any red path                                          | the **fully rendered `Evidence —` line**, four non-empty mutually distinct fields |

**Cases 1 and 10 from the previous draft are deleted, both for the same reason.** Case 1
asserted that a green run comments then closes the tracking issue. `math#100` is open and
describes exactly that as a defect — a single-crate green run closed #98 while `pi-rs` and
`e-rs` were still broken, destroying the tracking record for failures the run never looked
at. Case 10 asserted comment-not-create on the red path, which tier 2 records as broken.
Pinning either would make its bug harder to fix later, because a passing test's presence
reads as intent. Neither behaviour changes in tier 3; both are simply not asserted.

**Case 7 is the positive control and is not optional.** Cases 3–6b, 8a–8c and 9 all assert
on the content of a failure message, so a script emitting an empty body would satisfy every
one of them.

**Case 13 is the second positive control, and the previous draft had no equivalent.** The
`Evidence` line is the headline deliverable and its `mutants job:` and `download step:`
fields feed no branch selection, so a `jq` producing empty strings left every case green
while shipping a half-blank line to the operator. Case 3's assertion is on the literal
fixture step name for the same reason: cases 3–6b are otherwise satisfied by branch
selection alone, with the probe's own derivation never under test.

**Case 12 is preserved behaviour, stated rather than inherited.** Every `RESULT` other than
`success` is treated as red today, so a manually cancelled run files a "monthly run failed"
issue. `needs.mutants.result` is `cancelled` there, distinct from the `failure` every
measured termination produced, so the two are separable if that is ever wanted. This spec
changes nothing and case 12 pins the current behaviour.

### Failure-mode safety

Every case runs with `tests/mocks/` prepended to `PATH`, the script resolves `gh` through
`PATH` with no absolute-path default, **and every `gh issue`/`gh label` call carries
`--repo "${REPO}"`** so a fixture value fails at gh's own resolution. The third clause is
the one that actually protects: `PATH` alone does not, and an earlier draft claimed a
fixture `REPO` was sufficient when `REPO` governed only the probe.

## Verification

Already run, quoted in Measurements above:

- `gh api "repos/actions/download-artifact/contents/action.yml?ref=3e5f45b2..."` — confirms
  `digest-mismatch` exists with `default: 'error'`.
- `gh api "repos/brujack/math/actions/runs/<id>/jobs"` across four runs — confirms per-step
  conclusions are available.
- The workflow file at each run's `head_sha` — confirms `if: always()` was present.
- `grep -rn MUTANTS_UNCAPPED .github/workflows/` — empty; the cap is on in CI.

Gates on tier 3, not yet run: **G1** and **G2** above. Each is a dispatch; G2 needs a probe
branch. Both write to the live issue tracker and the plan must name the cleanup.

Requires the implementation:

- `bats tests/scripts/mutation_notify.bats` — all cases green, 7 naming a crate and 13
  rendering four distinct fields.
- `bats tests/scripts/ci_gate.bats` — unchanged after the mock edit, including the
  `MOCK_GH_EXIT` branch.
- `make lint` — shellcheck clean at default severity.
- `make bash-coverage` — not below `FLOOR=24` (CI measures 30, six points of slack).

## Scope

In scope: tier 1's two strings; and, gated on G1/G2, tier 3's extracted script, its tests,
the three `gh`-mock edits, and the two workflows' notify jobs.

Out of scope, each already a backlog row rather than a deferral invented here:

- The dedup defect (tier 2).
- `math#100`, the single-crate green run closing the full-sweep issue.
- Pinning the 33 unpinned `cargo install` lines — one input to cause 2; this change makes
  that cause legible rather than fixing it.
- Any change to `scripts/mutation-classify.sh` or the red/green rules. This alters what the
  issue *says*, never what the run *decides*.
- `mutation-pr.yml`, which has no notify job.

## Timing

The crons fire at 04:00 and 06:00 UTC on 2026-09-01, so nothing here lands first. That is
not a blocker — the current behaviour produces a misattributed body, not a wrong verdict —
and a run under the old text supplies a real fixture for the branch table. Tier 1 should
still land promptly rather than wait on G1/G2, since it removes a false statement from
master at a cost of two strings.

## Multi-Lens Review

Reviewed at commit: `25c8bce1ed6afc25f8632c1b28329593851f6342` (Step 7 self-review commit,
before Step 8 dispatch). Round 1. Dispositions are blank pending operator review.

Every lens verified the load-bearing premise with its own commands and all three confirmed
it: the misattributing `else` branch is live at `master` in both workflows, the `notify`
permissions block lists only `issues: write`, and `grep -c '^      - name: Upload'` returns
1 per file. The Risk lens additionally confirmed cause 2 structurally — the `no crates
found` guard exits at `mutation-testing.yml:52-54`, five lines *upstream* of the
`mkdir -p "${GITHUB_WORKSPACE}/status"` at line 58, and no workflow sets
`if-no-files-found`, so the default `warn` applies and a guard trip produces no artifact at
all.

Note on independence: three lenses of the same model class reading the same spec text is
not ensemble confirmation. Where they converged — on proportionality — that is evidence
they were not contradicted, not that the point is independently established. Each claim
below was re-verified against the repository by the author before being recorded here.

### Goal-Fit

Finding: three parts.

1. **Proportionality.** The spec states its own substance is the removal of an unsupported
   claim, which a two-line string edit achieves — no new file, no new permission scope, no
   API call, no shared-mock edit, no test surface. Everything beyond that buys *which* of
   four causes fired. Measured against the event rate, that is thin: the Python workflow has
   **3 runs, 3 successes, never red** (`gh run list --workflow mutation-testing-python.yml`,
   re-verified), so half the blast radius serves a branch that has never executed. The Rust
   workflow's 9 failures in 14 runs are dominated by one debugging session on 2026-08-01/02;
   its scheduled population is 3, all predating the ADR-0024 memory-cap fix, so the post-fix
   base rate of the artifact-absent branch is unmeasured. The lens also holds that the
   extraction argument is circular as written — "extraction is what makes the change
   gateable" is true only because the change adds logic, and a string edit adds none.
2. **Branch-table row 4 reproduces the defect it fixes.** *"Artifact contains no `status/`
   — the job failed before the loop began"* is another unconditional cause assertion from
   evidence that does not determine it. Artifact upload elides empty directories, so a run
   where the loop *did* begin, crate 1 produced `mutants.out/`, and the job died before the
   first `tee` wrote `status/<slug>` lands in this row with the message false. The artifact
   itself discriminates: `artifact/**/mutants.out` present means the loop began. Split the
   row on that or hedge it as every other row is hedged.
3. **Case 1 pins an open bug as intended behaviour.** `math#100` is open — *"mutation: a
   single-crate green run closes the full-sweep issue"* — and describes a defect in the exact
   green branch this spec rewrites: notify closed #98 on a single-crate green run while
   `pi-rs` and `e-rs` were still broken. Verified open. Case 1 asserts comment-then-close is
   correct, which makes #100 harder to fix later, since fixing it turns a passing test red
   and a test's presence reads as intent. The spec already has the right machinery — it
   handles `RESULT=cancelled` with an explicit preserved-behaviour paragraph — and should
   apply it here or drop case 1.

Reads-it test: every mechanism's consumer is the body of a `mutation-failure` issue, which
persists after the session, so none is pure decoration. The exception is
`digest-mismatch: error`, which restates the v8 default and cannot make any verdict differ;
defensible as documentation-as-config, but not a fix, and the spec presents it beside the
fixes.

Verdict count: 12 cases, 7 satisfied by an empty body. The spec identifies this and names
case 7 as the positive control. Residual the spec misses: case 7 pins the `status/`
derivation and nothing pins the *probe's* derivation — cases 3–6 are satisfied by branch
selection alone. Case 3 closes this at zero cost if its assertion is on the fixture's
literal step-name string rather than on the sentence.

Assumption: that the jobs API, queried by `notify` **during the same run**, returns the
`mutants` job's `steps[]` already populated with terminal conclusions — specifically for a
runner-reaped job, where the runner never reported step completion and the service must
backfill. Every measurement in this spec was taken post-hoc, days to weeks after the run
finished; none establishes what the array looks like at the instant `notify` executes.
"Terminal in the workflow graph, so `needs:` released the dependent job" and "finalised in
the REST API's `steps[]`" are different guarantees, and the SIGTERM case is where they are
most likely to diverge. If the array is empty or non-terminal at that moment, every red path
falls into the probe-failure branch and the design delivers less than the two-line edit
would. Settle it with a `workflow_dispatch` run carrying a temporary step in `notify` that
dumps `gh api repos/${REPO}/actions/runs/${GITHUB_RUN_ID}/jobs` and asserts the `Mutation
testing` job's `steps[]` is non-empty with terminal conclusions at that moment — one extra
`run:` line on a dispatch the Verification section already calls for.

Disposition: **Addressed** (operator, 2026-08-31, via relayed architectural review).

1. Proportionality — the design is now three tiers. Tier 1 is the two-string edit and needs
   nothing measured; tier 3 is retained by operator decision and gated on G1/G2. The
   base-rate wording is corrected from "low" to **unmeasured**, which the reviewer flagged as
   the load-bearing distinction: low would license shrinking the design against a known
   number, unmeasured licenses only measuring or deferring. The circularity is conceded in
   the text — extraction is a consequence of choosing tier 3, not a reason to choose it.
2. Row 4 — split on `artifact/**/mutants.out` presence into rows 6a/6b, with the mechanism
   (upload elides empty directories; a failing `tee` under `bash -e`) stated. The relayed
   review generalised this to **row 1**, which no lens did: the spec hedged in its Boundary
   section and then asserted in the table three pages later. Row 1 is now hedged to match,
   and G1 is what would license the stronger wording.
3. Case 1 — **deleted**, with `math#100` named as the reason. Case 10 deleted on the same
   grounds.

Assumption (G2, `steps[]` terminal at notify time) — **Addressed**: promoted to a named gate
on tier 3 rather than a follow-up, with the probe-branch mechanism worked out. Verified while
doing so that `MUTANTS_UNCAPPED` appears in zero workflows on master, so the reproduction is
a probe-branch technique and not a live defect.

### Ergonomics

Finding: five parts.

1. **The dedup lookup does not work in production, and case 10 would pin the failure as
   passing.** Verified: #99 was created 2026-08-02T02:13:37Z while #98 — identical title,
   identical label — was open, created 01:57:03Z and still open four weeks later. A mock
   that faithfully returns a number cannot express that, so case 10 is green forever while
   the operator gets a new issue per red run instead of one thread. Re-checked by the author:
   the workflow's exact lookup run today **does** return `98`, so the query is not broken —
   the dependency is on GitHub's issue **search index**, which `--search` uses and `--label`
   filtering does not. The fix does not require settling whether the 2026-08-02 event was
   index lag or a race between three overlapping dispatch runs: keying on the label and
   filtering titles client-side removes the index from the path either way.
2. **`JOB_NAME` is a duplicated reference with no equality check and no case.**
   `jobs.mutants.name` and the notify `env` are two strings in one file with nothing forcing
   them equal — the displaced-reference shape. Rename the job and the probe returns rc=0,
   well-formed JSON, and an **empty selection**, a third probe outcome cases 8a/8b do not
   cover. Both workflows have exactly two jobs, so `select(.name != "notify")` removes the
   duplicate string entirely.
3. **Case 8a is unwritable against the current mock.** `tests/mocks/gh:4` checks
   `MOCK_GH_EXIT` *before* any dispatch, so a non-zero exit applies to every call including
   the `gh issue` write whose body 8a must assert on. Expressing it needs a per-arm exit
   variable — a third mock edit the Scope section does not list, and one touching the branch
   `ci_gate.bats` depends on. The claim that the mock edit is "purely additive" is true of
   the two output arms and false of what 8a requires.
4. **The `Evidence —` line is asserted by zero cases** while being the headline deliverable.
   Its `mutants job:` and `download step:` fields feed no branch selection, so a `jq`
   producing empty strings leaves every case green and ships a half-blank line to the
   operator. Needs one case asserting the fully rendered line against a fixture whose four
   fields are non-empty and mutually distinct.
5. **The Verification section's `workflow_dispatch` step writes to the live tracker** —
   which is how #92/#96/#98/#99 came to exist. Name the cleanup, or the implementer
   reproduces the 2026-08-02 pattern while verifying a change about issue quality. Also
   `gh issue comment --body "Run: …/actions/runs/123…"` matches the proposed
   `*"actions/runs"*` mock arm, so arm order is load-bearing; match on `$1`, not `$*`.

Assumption: that the operator reads one accumulating tracking issue. The whole
comment-on-existing / close-on-green design rests on the dedup lookup finding the open
issue, and there is one measured counter-example whose mechanism is unestablished — search
index lag, which would be intrinsic and make the comment path mostly dead, versus a race
between overlapping dispatch runs, which would be a testing artifact and harmless monthly.
Those point opposite ways. The proposed discriminator is to create an issue and immediately
run the workflow's exact lookup against it; the author declined to run that unprompted
because it writes to the live tracker, and notes the label-only fix is correct under either
mechanism.

Disposition: **Addressed** (operator, 2026-08-31).

1. Dedup — **backlogged** per the operator's standing rule that all features and bug fixes
   go to the backlog so they sit in one place. Row added to `docs/superpowers/README.md`.
   Tier 2 of this spec names it so the omission reads as a decision. Consequence carried into
   the matrix: case 10 is deleted rather than pinning the broken path.
2. `JOB_NAME` — **Addressed**: removed entirely; the selector is `select(.name != "notify")`,
   so the duplicated string no longer exists. New case 8c covers an empty selection.
3. Case 8a / mock — **Addressed**: a third edit (`MOCK_GH_JOBS_EXIT`) is now named, and the
   "purely additive" claim is retracted in the text. `$1` matching adopted so an issue body
   containing `actions/runs` cannot hit the wrong arm.
4. Evidence line — **Addressed**: new case 13 asserts the fully rendered line with four
   non-empty mutually distinct fields, and case 3 now asserts the literal fixture step string
   rather than the sentence.
5. Live tracker — **Addressed**: the cost is stated in the G1/G2 section and the plan must
   name the cleanup.

Assumption (one accumulating tracking issue) — **Addressed**: the label-only fix is correct
under either mechanism, so the spec does not need to settle lag-versus-race. The author
re-ran the workflow's exact lookup and got `98`, which is recorded in the backlog row.

### Risk

Finding: four parts.

1. **The stated failure-mode safety does not hold — a regressed test writes to
   `brujack/math`.** Verified and corrected inline above: `REPO` governs only the probe, all
   six issue-tracker calls are repo-implicit, and an open #98 means the reached branch is a
   live `gh issue comment`, not a create that might fail. `tdd.md` E2. One flag per call
   site fixes it.
2. **Proportionality**, reached independently of the Goal-Fit lens: the spec concedes its
   own substance is a string replacement and then builds a mechanism around it without
   stating why the one-liner was rejected. Three of the four defects in this list are
   introduced by the mechanism and none exists in the one-liner.
3. **No default arm for an unmatched upload conclusion.** On `JOB_NAME` drift the selector
   matches nothing and the conclusion is the empty string — `set -u` does not fire, because
   the variable is set and empty — and none of the table's three enumerated values match.
   There is also no arm for `cancelled`, which is attested in this repo: run 28495704109's
   `Run mutants` is `cancelled` and this spec's own measurements table prints it. The script
   needs a default arm saying the upload conclusion could not be determined, plus a case.
   Case 11 as written guards the wrong drift — a third `Upload` step, which nobody is about
   to add.
4. **The mock edit is not additive**, same finding as Ergonomics 3, reached independently.

Verdict count: 13 rows, 7 asserting a fixed literal in a failure body; the spec's own
positive-control reasoning is correct as far as it goes. Gap one level down: cases 4, 5 and
6 discriminate on the upload conclusion but nothing pins the jobs-JSON parse producing
anything at all except case 3.

Assumption: that `Upload: skipped` discriminates termination from an ordinary `Run mutants`
failure. The spec flags this boundary honestly — all three measured failures are exit-143,
there is no negative sample — and then builds the branch table's top row on the reverse
implication anyway. If GitHub also reports a post-step as `skipped` when a job fails without
being reaped, that row misattributes a plain build failure as a runner kill, which is the
original defect relocated one layer down rather than fixed. Falsifiable cheaply:
`gh workflow run mutation-testing.yml -f crate=<a crate whose baseline tests fail>` produces
an ordinary non-terminated failure, then read that run's `steps[]`. It should run before the
branch table is written, not after.

Disposition: **Addressed** (operator, 2026-08-31).

1. `--repo` — **Addressed**: moved into the design section rather than living only in a
   correction note, per the relayed review. One refinement the lens did not make: its
   necessity is **contingent on extraction**. With no script there are no tests and nothing
   reaches the tracker, so this is a tier 3 requirement that reads like a standing hazard fix.
   Recorded as such.
2. Proportionality — see Goal-Fit 1.
3. Default arm — **Addressed**: the table's last row is a real arm for an empty or
   unrecognised conclusion, `cancelled` is named as attested in this repo, and case 8c pins
   it. Case 11 is kept but is explicitly the weaker guard.
4. Mock not additive — see Ergonomics 3.

Assumption (G1, `Upload: skipped` discriminates) — **Addressed**: promoted to a named gate.
The relayed review's sharper framing is adopted — G1 and G2 need **two different dispatches**,
not one, because a clean failing-baseline run exercises the path where the runner did report
and therefore cannot answer G2.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison, evaluator, or ambiguous-criteria trigger. The branch table is
a classifier over observed fields, not an evaluator comparing arms, and every acceptance
criterion names a concrete assertion.

Disposition: N/A — trigger does not apply.
