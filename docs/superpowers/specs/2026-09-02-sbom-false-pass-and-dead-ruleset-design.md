# SBOM monitor false PASS and the dead master ruleset

**Date:** 2026-09-02
**Status:** Spec

## Context

Two backlog rows in `docs/superpowers/README.md` claimed a gate in this repo enforces
nothing. Both claims were measured before design. Both were wrong, and each was wrong in a
way that mattered more than the original row.

### Row 1 as written

> `release-sbom-monitor.yml` is `active` on a monthly schedule and has never run — zero
> runs ever, zero issues under its label. SBOM CVE monitoring is not live. Found
> 2026-09-01.

**Refuted.** `release-sbom-monitor.yml` carries no `schedule:` trigger at all — it is a
reusable workflow (`workflow_call` plus `workflow_dispatch`). A reusable workflow invoked
via `workflow_call` reports its runs under the _caller's_ run, never its own, so
`gh run list --workflow release-sbom-monitor.yml` returning `[]` is the expected output for
a healthy reusable workflow. It was read as evidence of absence and is not evidence of
anything.

The scheduler is a second file, `release-sbom-monitor-schedule.yml`, carrying
`cron: "0 13 3 * *"` and eleven `uses:` jobs. It has run:

```
$ gh run list --workflow release-sbom-monitor-schedule.yml \
    --json databaseId,status,conclusion,createdAt,event
2026-08-03T13:51:04Z  schedule           success  30819864731
2026-07-16T21:45:03Z  workflow_dispatch  success  29537180581
```

All eleven child jobs of the scheduled run concluded `success`:

```
$ gh api repos/brujack/math/actions/runs/30819864731/jobs \
    --jq '.jobs[] | "\(.name) | \(.conclusion)"'
amicable / SBOM Vulnerability Scan        | success
pi / SBOM Vulnerability Scan              | success
goldbach / SBOM Vulnerability Scan        | success
twin-primes / SBOM Vulnerability Scan     | success
e / SBOM Vulnerability Scan               | success
perfect-numbers / SBOM Vulnerability Scan | success
prime / SBOM Vulnerability Scan           | success
sq / SBOM Vulnerability Scan              | success
collatz / SBOM Vulnerability Scan         | success
factorial / SBOM Vulnerability Scan       | success
fib / SBOM Vulnerability Scan             | success
```

### The real defect

The repository holds exactly one release, and it does not match any of the eleven patterns
the scheduler passes:

```
$ gh api repos/brujack/math/releases --jq '.[] | .tag_name'
v0.1.0

$ git tag | wc -l
       1
```

Each job resolves its tag with
`gh release list --limit 50 --json tagName --jq '... startswith("<pattern>") ...' | head -1`.
No `amicable-v*`, `pi-v*`, or any `<name>-v*` tag exists, so `LATEST_TAG` is empty for all
eleven, the workflow prints `No matching release found ... — skipping`, writes
`found=false`, and exits 0. Every downstream step is gated on `found == 'true'` and is
skipped.

So the monitor is not dormant-and-silent. It is **running monthly, reporting green, and
examining nothing** — the false-PASS shape `behavior.md` names under "a check derived from
the same decision as the thing it checks cannot falsify it," arriving here through an empty
population rather than a circular oracle. A PASS from this gate is currently indistinguishable
from a PASS that scanned eleven SBOMs and found no Critical or High findings.

A second silent branch sits under the first. The download step is:

```bash
if gh release download "${LATEST_TAG}" \
    --pattern "${BINARY_NAME}.sbom.spdx.json" 2>/dev/null; then
  echo "present=true" >> "$GITHUB_OUTPUT"
else
  echo "No SBOM asset found for ${LATEST_TAG} (or download failed) — skipping scan for this binary"
  echo "present=false" >> "$GITHUB_OUTPUT"
fi
```

Its own message concedes the ambiguity in parentheses. `gh release download` exits non-zero
for an absent asset, for a network failure, and for an auth failure alike, and all three
land in the same branch, which then exits 0. This is `behavior.md`'s "a guard's failure
branch absorbs the failure of the guard itself" — the handler names one cause and catches
several, and here the named cause is the _benign_ one while the others are silently
downgraded to it.

The SBOM assets themselves are produced by `release-sign.yml:32-41` (`syft ... -o spdx-json
--file "${BINARY_NAME}.sbom.spdx.json"`), which runs only as part of a release. With no
per-binary release ever cut, no `<name>.sbom.spdx.json` exists anywhere to be scanned.

The operator has confirmed per-binary releases are intended eventually. The eleven
`release-<name>-rs.yml` workflows, `release-sign.yml`, and the SBOM monitor pair are
therefore correct-but-dormant infrastructure, not dead weight — so the fix is to make the
dormancy legible rather than to delete the machinery.

### Row 2 as written

> Ruleset 14955025 is `enforcement: active` with `conditions.ref_name.include: []`, so it
> targets no branch and `gh api repos/brujack/math/rules/branches/master` returns empty. Its
> 7 `Test *` contexts name 4 of 11 sub-projects and have never been enforced — measured
> 2026-08-24 when #123 merged with 7 of the 8 absent. Decide whether to scope it to `master`
> (making those contexts real, which would then need the other 7 sub-projects added) or
> delete it as dead config. Not a blocker: it gates nothing today.

**Half confirmed, and the missing half removes one of the two options.** The ruleset is
dead exactly as described:

```
$ gh api repos/brujack/math/rulesets --jq '.[] | "\(.id) \(.name) \(.enforcement)"'
14955025 master active

$ gh api repos/brujack/math/rulesets/14955025 --jq '.conditions.ref_name'
{"exclude":[],"include":[]}

$ gh api repos/brujack/math/rules/branches/master
[]
```

What the row omitted is that master carries live **classic branch protection**, which is a
separate mechanism from rulesets and is enforcing today:

```
$ gh api repos/brujack/math/branches/master/protection
required_status_checks.contexts : ["secret-scan", "mutation-pr"]
required_linear_history         : true
allow_force_pushes              : false
allow_deletions                 : false
enforce_admins                  : false
required_signatures             : false
```

So master is protected. But the enforced set contains **no test check**, and cannot. Every
per-sub-project test workflow is `paths:`-filtered, and a required status check that never
reports blocks a PR permanently — GitHub has no "skip if the workflow did not run"
semantics for required checks. Measured over all 41 tracked workflow files, exactly three
trigger on `pull_request` with no `paths:` filter:

```
auto-merge.yml       (jobs: secret-scan, snyk-scan, bash-coverage, auto-merge)
mutation-pr.yml
pr-title-lint.yml
```

The required-check universe for this repo is therefore those three files' jobs and nothing
else. (`benchmarks.yml` also carries no `paths:` filter and is _not_ in this set — it
triggers on `workflow_dispatch` and a monthly `cron`, never on `pull_request`. It was
wrongly included in the first draft of this spec, because the population was derived by
grepping all 41 files for an absent `paths:` key and then asserting the `pull_request`
subset without reading each trigger. That error can only over-count, which is the
correlated-sign shape `behavior.md` warns about: every fault pointed toward "more checks
are eligible", and a one-sided result reads as clean.) The
current choice of `secret-scan` + `mutation-pr` is coherent rather than accidental: both
always run. The row's "scope it to master" option is unavailable on mechanism, not on
preference — scoping the ruleset would make seven `Test *` contexts required, and a PR
touching only `collatz/` would then wait forever for `Test pi-rs` to report.

One incidental correction, so it is not rediscovered: the seven context names in the dead
ruleset **do** match real job display names (`pi-rs.yml:16` is `name: Test pi-rs`,
`fib-py.yml:19` is `name: Test fib.py`, and so on for all seven). The context strings were
never the problem. Separately, `amicable-rs.yml` and `scripts.yml` declare no job `name:`,
so both report as the bare context `test` — visible in PR #128's check list — which would
be an additional collision if anyone tried to enumerate all eleven sub-projects as
contexts.

The real gate is `auto-merge` (the job that runs `scripts/ci-gate.sh`), which polls whatever
checks actually reported and merges on that basis. It is not a required check, and cannot
be one: the job performs the merge itself, so requiring it deadlocks.

Neither of these two configurations lives in a tracked file. That is why a ruleset created
2026-04-11 sat `active` and empty for nearly five months with nothing reporting it.

## Decisions

| #   | Question                                          | Decision                                                                                  |
| --- | ------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| 1   | Will `math` cut per-binary releases?              | Yes, eventually — repair the monitor, do not delete it                                    |
| 2   | How should the monitor report its three outcomes? | Split the silent branches: dormant stays green with a marker; missing SBOM asset goes red |
| 3   | What happens to ruleset 14955025?                 | Delete it                                                                                 |
| 4   | Change the required-check set?                    | Add `bash-coverage`; leave `secret-scan` and `mutation-pr`                                |
| 5   | Durable repo-side record of protection state?     | A `CLAUDE.md` subsection, no drift-check machinery                                        |

Rationale for 3, since two options were live: the ruleset's `deletion` and
`non_fast_forward` rules are already enforced by classic protection's `allow_deletions:
false` and `allow_force_pushes: false`, and its `required_status_checks` block can never be
scoped for the reason above. It carries nothing classic protection does not already hold,
while reading to any future reader as protection that exists.

Rationale for 5: a drift check's output goes to a terminal nobody is watching on the day
the config changes, and this is a single-repo, single-operator setting that changes perhaps
twice a year. The `CLAUDE.md` paragraph is read by every session. Its load-bearing content
is not the current values but the constraint — paths-filtered workflows can never be
required checks — which is the fact that will otherwise be re-derived from scratch.

## Section 1 — SBOM monitor

### Extract before fixing

The logic lives in inline `run:` blocks, which no test can reach. This repo has the
pattern already: `scripts/mutation-classify.sh`, `scripts/mutation-notify.sh`, and
`scripts/ci-gate.sh` were each extracted into `scripts/` so bats could test them, and
`tests/mocks/gh` supports per-verb failure injection via
`MOCK_GH_EXIT_<SUBCOMMAND>_<VERB>`.

New `scripts/sbom-resolve.sh`, invoked by `release-sbom-monitor.yml`, replacing the
`Resolve latest matching release tag` and `Download SBOM asset` steps.

### Three-valued state, replacing two booleans

The current workflow carries two independent booleans, `found` and `present`, each with a
silent-skip branch that exits 0. They collapse three distinguishable outcomes into one
`success`. Replace them with a single `state` output:

| state           | exit  | condition                             | meaning                                                                   |
| --------------- | ----- | ------------------------------------- | ------------------------------------------------------------------------- |
| `dormant`       | 0     | no tag matches `<pattern>`            | expected until the first per-binary release; nothing to scan              |
| `missing-asset` | **1** | tag exists, SBOM not among its assets | `release-sign.yml` failed or did not run — a real release-pipeline defect |
| `ready`         | 0     | tag and asset both present            | proceed to scan                                                           |

The two downstream steps currently gated on `steps.latest.outputs.found == 'true' &&
steps.sbom.outputs.present == 'true'` become a single `steps.resolve.outputs.state ==
'ready'`.

`dormant` is green because under decision 1 it is the steady state for an unknown number of
months, and a red monthly run for eleven jobs trains the reader to ignore the workflow —
the fatigue shape already recorded in this repo as issue #100 (`mutation: a single-crate
green run closes the full-sweep issue`).

`missing-asset` is red because it can only occur once a release exists, at which point a
missing SBOM means the signing pipeline is broken and no amount of green elsewhere should
conceal it.

### Asset membership, not download failure

The absent-asset test must not be inferred from a failed download. Query the release's
asset list and test for membership:

```bash
gh release view "${LATEST_TAG}" --json assets \
  --jq '.assets[].name' | grep -Fxq "${BINARY_NAME}.sbom.spdx.json"
```

A failed `gh release view` (network, auth, rate limit) is then a distinct condition from an
asset that is genuinely absent, and each gets its own message naming its own cause. Both
are non-zero, but a reader is told which happened. This is the direct remedy for the
guard-absorbs-its-own-failure defect quoted above.

The download itself still runs after membership is confirmed, and a failure there is also
red with a third distinct message.

### Make a dormant run say so

A `dormant` result writes to `$GITHUB_STEP_SUMMARY`:

```
SBOM monitor: dormant — no release matching '<pattern>' (nothing scanned)
```

Green, no issue filed, no noise. The point is that green stops being ambiguous when read.

### Prove the scan computed something

When `state=ready` and the scan runs, write the SBOM's package count to the summary as
well — read from the downloaded SPDX file itself (`jq '.packages | length'`), not from the
scan action's output, since an empty SBOM and a clean scan produce the same scan output. `{"matches":[]}` over an empty or malformed SBOM is otherwise indistinguishable from a
genuinely clean scan — the same false-PASS class as the outer defect, one level down. This
is a summary line only; it adds no branch and no failure mode.

### Tests

`tests/scripts/sbom_resolve.bats`, using `tests/mocks/gh`:

- `dormant` — `gh release list` returns no matching tag; assert `state=dormant`, exit 0, and
  the summary marker present.
- `ready` — tag and asset both present; assert `state=ready`, exit 0.
- `missing-asset` — tag present, asset list does not contain the filename; assert
  `state=missing-asset` and **exit 1**.
- Discrimination — `gh release view` itself fails (`MOCK_GH_EXIT_RELEASE_VIEW=1`); assert
  the message names a lookup failure and not an absent asset. This is the case that
  distinguishes the fix from the bug, so it is the one that must go red first.
- Download failure after confirmed membership; assert its own distinct message.

A positive control is required, per `bug-scan` Step 6: a `dormant` assertion passes equally
against a script that does nothing at all, so at least one case must pin a specific non-zero
derived value — `state=ready` reaching the scan, and the package count being written — rather
than only a verdict.

`scripts/sbom-resolve.sh` joins `SHELL_SOURCES` and the bash-coverage instrumented set
automatically through the existing `git ls-files 'scripts/*.sh'` predicate. The coverage
figure is expected to move up; the `FLOOR=24` in `auto-merge.yml` is not changed by this
work.

## Section 2 — Branch protection

Three actions, in this order. No code diff.

### 1. Capture the ruleset before deleting it

Ruleset deletion is not reversible from the UI, and after step 3 this spec is the only
record of what existed. Captured 2026-09-02:

```json
{
  "id": 14955025,
  "name": "master",
  "target": "branch",
  "source_type": "Repository",
  "source": "brujack/math",
  "enforcement": "active",
  "conditions": { "ref_name": { "exclude": [], "include": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": false,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          { "context": "Test fib-rs", "integration_id": 15368 },
          { "context": "Test fib.py", "integration_id": 15368 },
          { "context": "Test pi-rs", "integration_id": 15368 },
          { "context": "Test pi.py", "integration_id": 15368 },
          { "context": "Test prime-rs", "integration_id": 15368 },
          { "context": "Test sq-rs", "integration_id": 15368 },
          { "context": "Test sq.py", "integration_id": 15368 },
          { "context": "secret-scan", "integration_id": 15368 }
        ]
      }
    }
  ],
  "node_id": "RRS_lACqUmVwb3NpdG9yec5Dxcq7zgDkMhE",
  "created_at": "2026-04-11T14:38:14.496-04:00",
  "updated_at": "2026-04-11T14:38:14.540-04:00",
  "bypass_actors": [],
  "current_user_can_bypass": "never"
}
```

### 2. Add `bash-coverage` to the required contexts

`PATCH` on `required_status_checks` **replaces** the contexts array rather than appending,
so all three must be sent:

```bash
gh api -X PATCH repos/brujack/math/branches/master/protection/required_status_checks \
  -F strict=false \
  -f 'contexts[]=secret-scan' \
  -f 'contexts[]=mutation-pr' \
  -f 'contexts[]=bash-coverage'
```

`bash-coverage` runs unconditionally in `auto-merge.yml`, gates a real floor (24%), and is
already in the `auto-merge` job's `needs:` — so a failure there already stops the automatic
merge. Requiring it closes the manual-UI-merge path that currently skips it.

This runs before the deletion. It strengthens protection, and since the ruleset enforces
nothing today there is no interval in which master is weaker than it is now.

### 3. Delete the ruleset

```bash
gh api -X DELETE repos/brujack/math/rulesets/14955025
```

### Verification

```bash
gh api repos/brujack/math/rulesets                          # expect []
gh api repos/brujack/math/rules/branches/master             # expect [] (unchanged)
gh api repos/brujack/math/branches/master/protection \
  --jq '.required_status_checks.contexts'                   # expect the three contexts
```

`rules/branches/master` is `[]` both before and after; it is checked to confirm the
deletion removed nothing that was in force, not to detect a change.

### 4. `CLAUDE.md` — new "Branch protection" subsection under CI

Content, with the constraint leading because it is the part that will otherwise be
re-derived:

> **Branch protection.** Every per-sub-project test workflow is `paths:`-filtered, and a
> required status check that never reports blocks the PR permanently — GitHub has no
> "skip if the workflow did not run" semantics. So no `Test <sub-project>` context can ever
> be a required check in this repo. The required set is drawn from the checks that run
> unconditionally on `pull_request` (`auto-merge.yml`, `mutation-pr.yml`,
> `pr-title-lint.yml`) and is currently `secret-scan`, `mutation-pr`,
> `bash-coverage`. The real gate is the `auto-merge` job running `scripts/ci-gate.sh`, which
> polls whatever actually reported; it cannot itself be a required check, because it
> performs the merge and would deadlock.
>
> Ruleset 14955025 (`master`, `enforcement: active`, `conditions.ref_name.include: []`) was
> deleted 2026-09-02 as dead config — it targeted no branch, and its `deletion` /
> `non_fast_forward` rules duplicated classic protection's `allow_deletions: false` and
> `allow_force_pushes: false`. Its full JSON is preserved in
> `docs/superpowers/specs/2026-09-02-sbom-false-pass-and-dead-ruleset-design.md`. Do not
> re-create it believing protection is missing.

## Verification plan

Section 1, runnable locally before and after:

```bash
make lint-hooks                                  # shellcheck the new script
bats tests/scripts/sbom_resolve.bats             # the five cases above
make test                                        # lint + test-hooks + test-python
```

Each bats case must be seen red before its implementation exists — in particular the
`gh release view` failure-discrimination case, which is the one the current workflow gets
wrong and therefore the one whose RED proves the fix is real.

Section 2 is verified by the three `gh api` reads above, run after the three actions.

The end-to-end behaviour of Section 1 cannot be verified before the first per-binary
release exists: `dormant` is the only state reachable in production today. That is stated
rather than worked around — the bats cases cover all three states against the `gh` mock,
and the `ready` and `missing-asset` paths remain unexercised against real GitHub until a
release is cut. The first per-binary release is therefore the moment to re-read a scheduled
run's job summary.

## Scope

**In scope:** `scripts/sbom-resolve.sh` (new), `tests/scripts/sbom_resolve.bats` (new),
`.github/workflows/release-sbom-monitor.yml` (the two resolution steps and the scan step's
summary line), `CLAUDE.md` (Branch protection subsection, and the CI table if the new script
warrants a row), three `gh api` calls, and the two backlog rows this spec closes.

**Out of scope:**

- Cutting a per-binary release. That is the trigger for the `ready` path, not part of this
  change.
- `release-sbom-monitor.yml:94-96`'s `--search in:title` construct and the sibling row about
  it in the backlog. That is a separate finding with its own reasoning
  (`2026-09-01-mutation-notify-mock-isolation-and-labels-design.md`, Out of scope) and is
  untouched here.
- Filing an issue on `missing-asset`. Deferred until a release exists and the red branch is
  reachable; a job failure is a durable enough channel until then.
- Adding job `name:` to `amicable-rs.yml` and `scripts.yml` so they stop reporting as the
  bare context `test`. Real, but unrelated to either row — backlogged.
- Migrating classic protection to rulesets. GitHub's forward direction and a genuine
  migration; it deserves its own spec, not a rider on a dead-config cleanup.
- `gh release list --limit 50 ... | head -1` selects the most recently published matching
  release, not the highest semver. Correct for the current one-release-per-binary model and
  worth revisiting if backports ever ship — backlogged, not fixed here.

## Risks

- **`missing-asset` turning red is unreachable today**, so the branch ships untested against
  real GitHub. Mitigated by the bats coverage and by naming the first release as the moment
  to re-read a run.
- **A `PATCH` to `required_status_checks` replaces rather than appends.** Sending an
  incomplete array silently drops a required context. The verification read of
  `.required_status_checks.contexts` is what catches this and is not optional.
- **Deleting the ruleset is irreversible from the UI.** Mitigated by the captured JSON
  above, which is the reason step 1 exists.
- **The `CLAUDE.md` paragraph is the only record of the protection state**, by decision 5.
  It goes stale silently if the contexts change and nobody edits it. Accepted: the
  alternative was a drift check whose output nothing reads.

## Related

- `docs/superpowers/README.md` — the two backlog rows this closes, both corrected here
- `.github/workflows/release-sbom-monitor.yml`, `release-sbom-monitor-schedule.yml`,
  `release-sign.yml`, `auto-merge.yml`
- `scripts/ci-gate.sh`, `scripts/mutation-notify.sh` (the extraction pattern followed here)
- `~/.claude/standards/behavior.md` — "a guard's failure branch absorbs the failure of the
  guard itself"; "a two-valued field cannot report a three-valued outcome"
- `~/.claude/standards/ci.md` — `required_status_checks` contexts are case-sensitive
- Issue #100 — the alert-fatigue precedent behind keeping `dormant` green

## Multi-Lens Review

Reviewed at commit: `38e26426abb2d6a8226bc7a0eeac19fe0d326fc9` (Step 7 self-review commit, before Step 8 dispatch)

Round 1. All three lenses independently re-verified the spec's factual premises against
the live repo and API; every premise held, including the corrected exclusion of
`benchmarks.yml` from the `pull_request` set (one lens confirmed it by parsing all 41
tracked workflows with PyYAML rather than by grep). Two lenses independently confirmed a
claim the spec asserted without evidence: `bash-coverage` reports under exactly that
context string and its job carries no `if:`, so decision 4 cannot deadlock master on a
name mismatch.

### Goal-Fit

Finding: Section 1 builds a script and a five-case suite whose only production-reachable
outcome is `dormant`, and `dormant`'s entire delta over today is moving an existing log
line into a step summary — `release-sbom-monitor.yml:44` already prints
`No matching release found for pattern ${TAG_PATTERN} — skipping` into the job log. Applying
the reads-it test to each Section 1 mechanism: the `dormant` marker and the package-count
line change no verdict and have no durable channel (the workflow's real consumer is the
`sbom-monitor` issue label, which stays at zero before and after); `missing-asset → exit 1`
and the view-vs-download discrimination do change a verdict, but are unreachable until a
`<name>-v*` release exists. So the two reachable mechanisms are decoration and the two
load-bearing ones are deferred. The stated defect is not closed at the level anyone reads —
a green check in the Actions list, zero labelled issues — only for a reader who deliberately
opens a green run, who is the same reader who could already read the log. Simpler path:
Section 2 is the whole immediately-real deliverable, and Section 1's readable-today value is
one sentence in the same `CLAUDE.md` subsection.

Assumption: that per-binary releases will actually be cut (decision 1). Everything in
Section 1 pays out only when a `<name>-v*` tag exists; if that never happens, the correct
action was to retire the eleven-job monthly no-op, not repair it. The lens sampled seven
`release-*-rs.yml` workflows and found 0 runs ever. **Confirmed and widened by this session:
all 12 release workflows, `release-sign.yml` included, report 0 runs ever** — so the SBOM
producer has never executed. Settled by a sharper question than the one asked in
brainstorming: is a per-binary release planned within a stated horizon, and what event
triggers it?

Disposition:

### Ergonomics

Finding: only the red side of decision 2 has a delivery mechanism. GitHub emails on
scheduled-workflow failure, never success, so a green `dormant` marker on one of eleven jobs
inside a monthly cron run is delivered nowhere — the change converts an unread ambiguous
green into an unread unambiguous green. The transition day is invisible at the same level:
cutting `factorial-v1.0.0` yields 1 `ready` + 10 `dormant`, all eleven green, so
"11 dormant" and "1 scanned clean + 10 dormant" are the same observable, and the next
scheduled run is up to 30 days out. The dormant-green / missing-asset-red split is drawn in
the right place — dormancy is per-binary steady state for years on the ten never-released
binaries, and a monthly 11-job red is exactly issue #100's fatigue — the defect is the
missing channel, not the split. Three lines address the transition specifically:
`on: release: types: [published]` on `release-sbom-monitor-schedule.yml`, so the
`ready`/`missing-asset` verdict lands at the one moment the operator is already watching
Actions.

Assumption: that a red monthly scheduled run actually reaches the operator. The value of
`missing-asset → exit 1` rests entirely on red producing a notification green does not, and
GitHub emails scheduled-run failures only to the user who last modified the workflow file,
only if their Actions notification setting is on — neither visible in the repo.
Counter-evidence in `CLAUDE.md`: six consecutive `mutation-testing.yml` runs failed with
exit 143 between 2026-06-01 and 2026-08-01 and were misdiagnosed once before being fixed.
Settled by checking the operator's Actions notification settings, or asking whether email
arrived for any of those six failures.

Disposition:

### Risk

Finding: the one observable that would distinguish a real scan from an empty one lives in
the layer the spec itself declares untestable, so the fix reproduces the false-PASS shape
one level down. The spec's own positive-control clause names "the package count being
written" as the derived value a case must pin, but Scope places that count in the workflow's
inline `run:` scan step while the suite is `tests/scripts/sbom_resolve.bats` against the
script — so the mandated control is unsatisfiable by the suite that is meant to contain it.
Counting verdicts: five cases, two asserting exit 0 with a verdict string and three
asserting non-zero plus message text; **zero assert a derived quantity**, and all five pass
against a script whose downstream scan reads an empty or malformed SPDX. Separately, the
spec answers one question two ways: decision 5 rejects a drift check because "its output
goes to a terminal nobody is watching," while Section 1 relies on a summary line in the same
category. Smaller, and not raised as a finding because the fix is one read: the spec
captures the ruleset JSON before the irreversible DELETE but captures **no pre-image of
classic protection before the PATCH**, and the PATCH is the operation that replaces an
array.

Assumption: that a `dormant` marker written to `$GITHUB_STEP_SUMMARY` on a monthly
scheduled run will actually be read. If it is, the false PASS is cured today; if not, the
deliverable is textual and nothing observable changes until the first release, at which
point `missing-asset` — the untested branch — becomes the only real mechanism. Settled by
asking the operator directly whether they have ever opened, or would open, the job summary
of a scheduled run in this repo.

Disposition:

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger. No arms, no judge
component; acceptance criteria are concrete exit codes, state strings, and API reads.
