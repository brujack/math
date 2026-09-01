# Mutation-testing notify: let the job attest its own progress

Date: 2026-08-31 (revised 2026-09-01 after Multi-Lens Review round 2)
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
applies and a guard trip uploads nothing.

The deeper defect is that the sentence has no supporting field at all. `needs.mutants.result`
is `failure` for a SIGTERM and `failure` for an ordinary step failure alike, and the exit
code appears only in the run log, which the notify job never reads. The workflow asserts a
cause it has no instrument for.

### Why now

`actions/download-artifact` moved to v8 in #119 (`7e8241b`, 2026-08-24). The pinned tree at
`3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` adds a `digest-mismatch` input with
`default: 'error'`, retrieved with
`gh api "repos/actions/download-artifact/contents/action.yml?ref=3e5f45b2..."`. Both call
sites pair that default with `continue-on-error: true`, adding cause 4 to a branch that
already misreported causes 2 and 3.

### How often the misattribution fires: unmeasured, not rare

An earlier draft called this rate "low", which is the wrong claim: low would license
shrinking the design against a known number, unmeasured licenses only measuring or
deferring. The Python workflow has **4 runs, 4 successes**, and has never gone red. The Rust
workflow's scheduled population is **4**, of which 3 predate the ADR-0024 memory-cap fix.
11 of its 14 non-scheduled runs are `workflow_dispatch` from one debugging session on
2026-08-01/02. So the post-fix rate of the artifact-absent branch is not known in either
direction.

## Measurements

### The 2026-09-01 cron settled the question the design was going to buy a probe branch for

The Rust cron ran at 04:01:01Z on 2026-09-01 — the first execution under v8 — and produced
the **ordinary non-terminated failure** this repository had never previously recorded:

```
run 33468276278 (schedule, failure)
  Run mutants:            failure        <- ordinary failure, not reaped
  Upload mutants output:  success        <- `if: always()` DID run
  Post Run actions/checkout: success
  artifacts: 1  (mutants-output, 3,073,920 bytes, not expired)
  notify: commented on the open #98 -- "Failing crates: e-e-rs, pi-pi-rs"
```

Set against the four prior runs, the discrimination is now measured in both directions:

| run         | date       | `Run mutants` | `Upload mutants output` | reading                  |
| ----------- | ---------- | ------------- | ----------------------- | ------------------------ |
| 28495704109 | 2026-07-01 | `cancelled`   | `skipped`               | terminated               |
| 30685027791 | 2026-08-01 | `failure`     | `skipped`               | terminated (exit 143)    |
| 30728417809 | 2026-08-02 | `failure`     | `skipped`               | terminated (exit 143)    |
| 30728211305 | 2026-08-02 | `success`     | `success`               | green                    |
| 33468276278 | 2026-09-01 | `failure`     | **`success`**           | **ordinary failure**     |

`if: always()` was present on the upload step in every case, verified by reading the
workflow at each run's own `head_sha` rather than at `master`.

Two consequences. The gate this spec previously called **G1** — does `Upload: skipped`
discriminate termination from an ordinary failure — is **answered yes, by the calendar**,
with no dispatch and no deliberately OOM-reaped runner. And the design below no longer
depends on the answer, which is the better outcome.

The same run also shows the dedup lookup working: notify commented on #98 rather than
opening a duplicate. Combined with the earlier finding that the same lookup returns `98`
when run by hand, that favours search-index lag over an overlapping-run race as the cause of
the 2026-08-02 duplicate. Recorded in the backlog row; not settled here.

### What the run did not settle

`RESULT=cancelled` has still never occurred. All four failures carry a **job** conclusion of
`failure`; `cancelled` is attested only at the **step** level, on run 28495704109's
`Run mutants`. An earlier draft asserted that a cancelled run is separable by
`needs.mutants.result` and cited that step as evidence — wrong field, and about a different
step than the one the claim was used to justify.

## Design

**Have the job attest its own progress instead of inferring it from platform semantics.**

The previous draft inferred the cause from the mutants job's *step conclusions*, read back
through the Actions API. That required `actions: read`, a jobs-API probe with its own
failure branch, and two gating measurements about what GitHub's step conclusions mean and
when they are populated. A file written by the job itself answers the same question by
attestation, which is the standard `USER.md` states for any trust signal: it must carry the
confidence its mechanism earned.

### The breadcrumb

In the mutants job, immediately after checkout and **before** `cargo install`:

```yaml
      - name: Mark job start
        run: mkdir -p "${GITHUB_WORKSPACE}/marker" && date -u > "${GITHUB_WORKSPACE}/marker/job-began"
```

and `marker/` added to the upload step's `path:`, beside `**/mutants.out/` and `status/`.

Placement is load-bearing. After checkout, so the workspace exists; before `cargo install`,
so a toolchain or install failure still leaves the breadcrumb. Every cause-2 route — the
`no crates found` guard, a failed `cargo install`, any failure inside `Run mutants` — now
runs with the marker already on disk.

### What notify reads

| artifact                                         | cause, as reported                                                                                                                                                                |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **no `marker/`** — download failed, or the artifact is empty or lacks it | `Cause: no-attestation`. The job's own reporting never ran. One of: terminated before the upload step; a checkout failure before the marker; the upload itself failed; the artifact was corrupt on download. |
| `marker/` + `status/`                            | `Cause: verdicts-present`. Normal red: name the failing `<UNIT_NOUN>`s. Unchanged from today.                                                                                     |
| `marker/` + `mutants.out`, no `status/`          | `Cause: loop-began-no-verdict`. At least one `<UNIT_NOUN>` ran `make mutants`; the job stopped before the first `tee`.                                                            |
| `marker/` only                                   | `Cause: died-before-loop`. Checkout succeeded and the job did not reach the first `make mutants`. Failing step is in the log.                                                     |

**The discriminator is the marker's presence, not the download step's outcome**, and that
ordering is deliberate. `actions/download-artifact` may fail when the named artifact does not
exist, or it may succeed having downloaded nothing — the spec does not depend on which,
because both land in row 1 by the same test. That removes an unstated assumption the previous
draft's branch table rested on, where a missing artifact and a corrupt one had to produce
different step outcomes for two of its rows to discriminate at all.

The `died-before-loop` row is the substance. Cause 2 — the one this spec confirms is live and
structural — is now **positively attested** rather than inferred, and the sentence naming it
is true because a file the job wrote says so.

`no-attestation`'s residual is four causes in one sentence, all rare, none asserted. That is
the honest floor: a job that died before it could report anything cannot be attributed from
the artifact, and no amount of probing changes that. The run log is linked in the same issue
body.

### What this design deletes, relative to the previous draft

`actions: read` on both jobs; the jobs-API probe and its own failure branch;
`select(.name != "notify")` and the duplicated job-identity reference it replaced; the
`Upload`-prefix step match and its count guard; the `MOCK_GH_JOBS`/`MOCK_GH_JOBS_EXIT` mock
arms, including the non-additive one that touched `ci_gate.bats`; and both gating
measurements, G1 and G2. G1 is now answered by the 2026-09-01 cron. G2 — whether `steps[]`
is populated at the instant notify queries it for a reaped job — is not answered and no
longer needs to be, because nothing queries it.

**It also removes a dependency on `upload-artifact`'s zero-match behaviour.** With the
marker written after checkout, the upload always has at least one file to match, so the
question of what `if-no-files-found: warn` does to the step's own conclusion stops
mattering for every post-checkout cause.

### `digest-mismatch`

`digest-mismatch: error` is set explicitly on both download steps. It restates the v8
default, so **no verdict can differ because of it** — documentation-as-config, not a fix,
and listed separately from the fixes for that reason. It is kept because inheriting an
upstream default is how cause 4 arrived.

`continue-on-error: true` stays. An absent artifact is a legitimate state the notify job
exists to report; dropping it would make a terminated run produce two red jobs and no issue.

### Message text

Each arm emits a stable machine token before its prose:

```
Cause: loop-began-no-verdict

The loop began and no verdict was written. At least one crate ran `make mutants`;
the job stopped before the first status file was written. Run: <url>
```

The token is what tests assert on. Prose about a failure is the single most likely thing an
operator asks to reword, and a script whose entire purpose is message wording should not
have six tests go red when its messages are reworded. The token also gives the operator a
greppable key across #98's comment history.

No message asserts a cause the artifact does not attest, and no message names exit 143 —
the run log carries the exit code and nothing in the notify job can see it.

### Extraction

`scripts/mutation-notify.sh`, called by both workflows. The two notify bodies are
near-identical shell embedded in YAML, shell inside a `run:` block cannot be tested, and
this repo's Definition of Done requires boundary, error-path and state-transition tests for
new logic. The argument's shape is stated honestly: extraction is required *because this
change adds branching logic*, not as an independent virtue.

Inputs from the environment: `RESULT`, `DL_OUTCOME`, `ARTIFACT_DIR`, `RUN_URL`,
`ISSUE_TITLE`, `UNIT_NOUN`, `REPO`.

**Every `gh issue` and `gh label` call takes `--repo "${REPO}"`.** All six are repo-implicit
today (`mutation-testing.yml:116,121,122,137,139,141`), so `gh` resolves from the checkout's
remote. `gh issue list --label mutation-failure --state open` returns an open #98 right now,
so a regressed test's reached branch is `gh issue comment 98` on a live issue — not a create
that might fail. `tdd.md` E2. With `--repo` on every call, a fixture `REPO` fails at gh's own
resolution, and that assertion is itself a test case rather than a claim.

Placement consequences, all favourable: `scripts/*.sh` is inside the `bash-coverage`
instrumented predicate, so a tested script raises the reachable quarter of that measurement;
`lint-hooks` shellcheck picks it up through its `git ls-files`-derived scope; and
`tests/mocks/gh` already logs every invocation to `MOCK_CALLS_FILE`, which is what allows
assertions on issue-body content rather than on a return code.

## Testing

`tests/scripts/mutation_notify.bats`, following the existing `ci_gate.bats` pattern.

### The `gh` mock needs one arm, and it is additive

An arm for `issue` returning `MOCK_GH_ISSUE_LIST`, ahead of the existing fallback, matching
on `$1` rather than `$*`. No jobs-API arm and no per-arm exit variable are needed, because
there is no probe — which is what makes this edit genuinely additive, unlike the previous
draft's. `ci_gate.bats` is still the regression check for the shared file and must be re-run.

### Case matrix

Artifact-shaped cases build a real fixture directory; none needs a mocked API response.

| #   | inputs                                                          | assertion                                                                             |
| --- | --------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| 1   | `RESULT=success`, open issue exists                             | **no new issue created**, and every `gh` call carries `--repo`. Characterization only — see below |
| 2   | `RESULT=success`, no open issue                                 | exits 0 with no `gh issue` write at all                                                 |
| 3   | red, `marker/` + `status/` with a `^red` file                   | **body names that specific crate**; token `Cause: verdicts-present`                     |
| 4   | red, `marker/` + `mutants.out`, no `status/`                    | token `Cause: loop-began-no-verdict`                                                    |
| 5   | red, `marker/` only                                             | token `Cause: died-before-loop`                                                          |
| 6   | red, `DL_OUTCOME=failure`                                       | token `Cause: no-attestation`; body names all four residual causes and asserts none      |
| 7   | red, `DL_OUTCOME=success` but the artifact has no `marker/`     | token `Cause: no-attestation` — **same token as case 6**, proving the marker and not the download outcome is the discriminator |
| 8   | red, `status/` present with no `^red` line                      | preserves today's `(none flagged; see run log)`                                          |
| 9   | red, `status/` with two `^red` files                            | **both** crate names appear                                                             |
| 10  | `RESULT=cancelled`                                              | files an issue, as today — preserved behaviour, see below                               |

**Case 3 is the positive control and is not optional.** Cases 4–8 assert only that a token
appears in a failure body, so a script emitting the right token and nothing else satisfies
all of them. Case 3 pins a value derived from fixture content — the crate name read out of
`status/` — and is the only case that fails if that derivation silently produces nothing.

**Case 9 is the second control, and it replaces a requirement the previous draft could not
satisfy.** That draft asked for four "mutually distinct" Evidence fields; the value domains
are too small for distinctness to hold on any natural fixture, so the cheapest reconciliation
would have been to weaken the assertion to "non-empty", which is the vacuity the case existed
to prevent. Two red crates in one fixture tests the same property — that the derivation
enumerates rather than returning a fixed string — and is satisfiable.

**Case 1 is a characterization test and asserts nothing about closing.** `math#100` is open
and describes the green path as buggy: a single-crate green run closed #98 while `pi-rs` and
`e-rs` were still broken, and the 2026-09-01 cron confirms those two crates are still red.
Asserting comment-then-close as correct would make #100 harder to fix, because a passing
test reads as intent. But asserting *nothing* would leave `gh issue close` — the only
destructive call — with no coverage in a change whose purpose is to make that code testable,
and would drop the `--repo` safety assertion with it. So the case asserts the safety property
and the absence of a new issue, and is silent on the behaviour #100 disputes.

**Case 10 is preserved behaviour, stated rather than inherited.** Every `RESULT` other than
`success` is treated as red today, so a manually cancelled run would file a "monthly run
failed" issue. This has never occurred — all four measured failures carry a job conclusion of
`failure` — so the case pins current behaviour without claiming the shape has been observed.

### Failure-mode safety

Every case runs with `tests/mocks/` prepended to `PATH`, the script resolves `gh` through
`PATH` with no absolute-path default, **and every `gh issue`/`gh label` call carries
`--repo "${REPO}"`** so a fixture value fails at gh's own resolution. The third clause is the
one that protects; `PATH` alone does not, and an earlier draft claimed a fixture `REPO` was
sufficient when `REPO` governed only a probe that no longer exists.

## Verification

Already run, quoted above:

- The five-run step-conclusion table, including the 2026-09-01 ordinary failure.
- The workflow at each run's `head_sha`, confirming `if: always()`.
- `gh api .../actions/runs/33468276278/artifacts` — 1 artifact, 3,073,920 bytes.
- `grep -rn MUTANTS_UNCAPPED .github/workflows/` — empty; the memory cap is on in CI.
- `grep -rn if-no-files-found .github/workflows/` — empty; the default `warn` applies.

Requires the implementation:

- `bats tests/scripts/mutation_notify.bats` — all cases green, 3 naming a crate, 9 naming two.
- `bats tests/scripts/ci_gate.bats` — unchanged after the mock edit.
- `make lint` — shellcheck clean at default severity.
- `make bash-coverage` — not below `FLOOR=24` (CI measures 30, six points of slack).
- One `workflow_dispatch` per workflow against a green crate, confirming the marker reaches
  the artifact and the normal-red path is unaffected. This writes to the live tracker only if
  the run is red; against a green crate it does not.

No probe branch, no deliberately reaped runner, and no measurement whose failure mode is an
issue-tracker write.

## Scope

In scope: the marker step and upload path in both workflows; the extracted script; its tests;
one additive `gh`-mock arm; `--repo` on the six tracker calls; explicit `digest-mismatch`.

Out of scope, each a backlog row rather than a deferral invented here:

- The dedup defect — `--search` depends on GitHub's issue search index and `--label` does not.
- `math#100`, the single-crate green run closing the full-sweep issue.
- Pinning the 33 unpinned `cargo install` lines — one input to cause 2; this change makes that
  cause legible rather than fixing it.
- Adding a `concurrency` block to either workflow. Neither has one, which is what makes
  overlapping runs possible at all; it is the suspected mechanism behind the 2026-08-02
  duplicate and is worth its own change.
- `e-e-rs` and `pi-pi-rs` failing their mutation runs, per #95 and the 2026-09-01 cron. This
  spec changes how failures are reported, never what fails.
- Any change to `scripts/mutation-classify.sh` or the red/green rules.

## Timing

The 2026-09-01 crons have fired. The Rust run was red, took the normal path, and produced a
correct message, so no misattribution occurred and there is no deadline pressure. The
previously proposed "tier 1" string edit is dropped: it existed to remove a false sentence
before that cron, the cron has passed, and this design replaces the sentence anyway.

## Multi-Lens Review — Round 1

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


## Multi-Lens Review — Round 2

Reviewed at commit: `03ce65d762c14481ca521fa6461c79580e5c232e`. All three lenses re-run,
not only the ones that raised round 1's findings, because the round 1 revision changed
design substance and a correction is new design carrying its own defects. That judgement is
vindicated here: **every round 2 finding below is about text the round 1 revision
introduced.**

All three verified the premise independently and all three confirmed it. Between dispatch
and disposition the 2026-09-01 cron fired, which answered one of the two gates the round 1
design rested on and made the other unnecessary.

### Goal-Fit

Finding: the tiering is a false dichotomy — the spec only ever considered inferring the
cause from outside the job, never having the job attest it. The jobs-API probe's entire
marginal contribution is separating cause 1 from cause 2, and both gates existed for that
one distinction; a breadcrumb file written before `cargo install` names cause 2 positively
in ~5 lines of YAML and folds cause 1 into an honest residual. **The cost of deciding
whether to build the probe exceeds the cost of building the alternative outright.** Also:
deleting case 1 left `gh issue close` — the only destructive call — with zero coverage in a
change whose stated purpose is making that code testable; the assertion had to go, not the
case. Also: G1/G2 had no named destination for their answers. Also: "tier 2" is not a tier
of this design and numbering it between two deliverables makes the sequence read as
non-monotonic.

Assumption: that automatic cause attribution is worth building at all once the false
sentence is removed, since the one attested cost of this defect — ADR-0024's investigation
chasing the 360-minute timeout — is cured by enumeration alone.

Disposition: **Addressed** (operator, 2026-09-01, choosing the breadcrumb over the probe).
The breadcrumb is now the design; the probe, `actions: read`, the jobs API, G1 and G2 are
all deleted. One correction to the lens's own proposal, made by the author: its residual is
four causes rather than two, because `download-artifact` failure absorbs digest mismatch and
a pre-marker checkout failure as well as a reap. That is named in the `no-attestation` row
and asserted of none of them. Case 1 restored as a characterization test asserting the
`--repo` safety property and the absence of a new issue, silent on the behaviour `math#100`
disputes. Tiers collapsed to a single design. The assumption is moot rather than answered:
the breadcrumb makes attribution nearly free, so it no longer has to justify two dispatches.

### Ergonomics

Finding: five parts, all in round 1's new text. **Case 13 was unsatisfiable** — it required
four "mutually distinct" Evidence fields, and the value domains (job conclusion ∈ {failure,
cancelled}, upload ∈ {skipped, failure, success}, download ∈ {success, failure}) collide on
every natural fixture, so an implementer's cheapest reconciliation is to weaken it to
"non-empty with four colons", precisely the vacuity the case existed to prevent. **The
`download step:` field carries no information whenever upload ≠ `success`** and reads to the
operator as a second independent fault. **`JOB_NAME` was not removed but converted** into a
duplicated reference to the job *id*, whose failure mode is a selection of two rather than
zero — and case 8c guarded only the empty case, while the identical "fail loudly when the
count is not 1" discipline was applied to the `Upload` step one paragraph earlier. **Tier
1's replacement sentence presupposed an artifact** ("No `status/` directory in the artifact")
in exactly the case where none exists, the same shape as the sentence it replaced, and as
drafted its continuation lines terminated the `run: |` block scalar. **The tests were coupled
to operator-facing prose**, which is the single most likely maintenance request for a script
whose whole purpose is message wording.

Assumption: that `download-artifact@v8` fails rather than succeeding with a warning when the
named artifact does not exist — load-bearing for round 1's row 3 and never stated.

Disposition: **Addressed.** Case 13 is replaced by case 9, a two-red-crate fixture testing
the same property (the derivation enumerates rather than returning a fixed string) by a
satisfiable means. The Evidence line, `download step:` and the job selector are all gone with
the probe. Tier 1 is dropped — the cron it was racing has passed and this design replaces the
sentence anyway. Machine tokens (`Cause: <slug>`) adopted, with tests asserting the token and
prose left free to be reworded. The assumption is **structurally removed rather than
answered**: the design now keys on the marker's presence, not the download step's outcome, so
a missing artifact and a corrupt one land in the same row by the same test and it no longer
matters which outcome GitHub reports. The lens also caught a factual error — 11 of 14 runs
are `workflow_dispatch`, not 8 — verified and corrected.

### Risk

Finding: **round 1's row 3 misattributed cause 2, the one cause the spec confirms is live,
and did so more falsely than master.** With no `if-no-files-found` set, the `if: always()`
upload step runs on a cause-2 failure, matches zero files, warns, and concludes `success`
with no artifact created; the download then fails, and row 3 asserted "Artifact uploaded but
not downloadable — digest mismatch or a transient failure". Master's text says "No artifact
was produced", which is **true** for cause 2 and false only in its second clause. **Case 12's
factual premise is false**: `cancelled` is attested at the step level only, all four measured
failures carry a job conclusion of `failure`, so `RESULT=cancelled` has never occurred and
the default arm's stated evidence was about a different step than the field it justified.
**G1/G2's tracker writes were avoidable** — the probe branch already edits `notify` and could
replace the issue-write step outright — and neither workflow has a `concurrency` block, so a
gating dispatch overlapping the 2026-09-01 crons would have reproduced the very
overlapping-run condition the backlog names as the suspected cause of the duplicate.
**Deleting case 1 left the only destructive call untested**, including its `--repo` assertion.

Assumption: that `upload-artifact` concludes `success` when its glob matches zero files —
documented under `if-no-files-found: warn` but unmeasured in this repository, and decisive
for two of round 1's seven rows.

Disposition: **Addressed.** Row 3 no longer exists. Verified the job-level conclusions
directly (`28495704109`, `30685027791`, `30728417809` all `job=failure`; `30728211305`
`job=success`), confirming the case 12 finding, and the claim is retired rather than repaired
— case 10 now pins current behaviour without asserting the shape has been observed. Verified
`grep -n concurrency` returns nothing in both workflows; adding one is a backlog row rather
than a silent inclusion here. Case 1 restored per Goal-Fit. The assumption is **structurally
removed**: with the marker written after checkout, every post-checkout upload has at least
one file to match, so what a zero-match upload concludes stops mattering for every cause the
design attributes.

### Adversarial Spec Review (comparison/judge designs only)

N/A — no comparison, evaluator, or ambiguous-criteria trigger. The branch table is a
classifier over files present in an artifact, not an evaluator comparing arms, and every
acceptance criterion names a concrete assertion.

Disposition: N/A — trigger does not apply.

### Stopping

Round 2's findings are design findings, and the skill's criterion says to continue while that
holds. Review stops here anyway, for a reason the criterion does not cover: the findings were
concentrated in a mechanism that has now been **replaced rather than repaired**. Reviewing
round 1's probe further would have been review of text that no longer exists. The breadcrumb
design is materially smaller than what either round reviewed — no API, no permissions change,
no gating measurements, one additive mock arm — and its remaining risk is concentrated in
apparatus (fixture directories, the `gh` mock) that Phase 2's first red test examines faster
and more reliably than a third round of prose review.
