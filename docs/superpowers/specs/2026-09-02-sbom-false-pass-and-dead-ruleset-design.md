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
| 6   | Delivery channel for `missing-asset` (round 2)    | A labelled issue, filed and closed by the workflow — not the job conclusion alone         |
| 7   | How the monitor runs on a release (round 2)       | A `needs: [sign]` job in each `release-<name>-rs.yml`, not an `on: release` trigger        |

Rationale for 3, since two options were live: the ruleset's `deletion` and
`non_fast_forward` rules are already enforced by classic protection's `allow_deletions:
false` and `allow_force_pushes: false`, and its `required_status_checks` block can never be
scoped for the reason above. It carries nothing classic protection does not already hold,
while reading to any future reader as protection that exists.

Rationale for 6, added after Step 8 round 1: the operator confirms failed scheduled runs do
**not** reliably reach them by email in this repo, which is consistent with the six
consecutive `mutation-testing.yml` exit-143 failures recorded in `CLAUDE.md` between
2026-06-01 and 2026-08-01. A red job conclusion is therefore not a delivery mechanism here,
only a record. `missing-asset` still exits 1, but the channel that carries it is a labelled
issue — the same mechanism `scripts/mutation-notify.sh` already implements in this repo and
the only durable consumer this design has. Decision 1's answer moved too: releases are
weeks away with no blocker, so the branches that were unreachable are shortly reachable,
which is what makes the channel worth building now rather than deferring.

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

`dormant` is green because it stays the steady state for the ten binaries not covered by
the first release, and a red monthly run for eleven jobs trains the reader to ignore the
workflow — the fatigue shape already recorded in this repo as issue #100 (`mutation: a
single-crate green run closes the full-sweep issue`). It files no issue.

`missing-asset` is red because it can only occur once a release exists, at which point a
missing SBOM means the signing pipeline is broken and no amount of green elsewhere should
conceal it. Its exit code is a record, not a notification — see Delivery below.

### Delivery: `missing-asset` files an issue

Round 1 established that neither half of the green/red split reaches the operator on its
own. Green is never emailed by GitHub, and the operator confirms red is not reliably
emailed either. So the red branch gets the channel this repo already uses for exactly this
purpose:

- On `missing-asset`, file an issue titled `[SBOM Monitor] SBOM asset missing for <binary>`
  under a new `sbom-asset-missing` label, distinct from the existing `sbom-monitor` label
  that carries CVE findings. Keeping the labels apart follows #128's per-workflow-label
  finding: one label per producer, so closing one producer's issue cannot close another's.
  Keeping the **binary** in the title is the same separation one level down — a label
  identifies the producer, the title identifies the subject within it.

  > **The title is the key, not a description. Do not add the tag, the date, the CVE count,
  > or anything else that varies between runs.** Filing looks for this exact string to avoid
  > a duplicate and closing looks for it to find what to close, so any component that changes
  > between two runs makes those two operations address different issues. The tag goes in
  > the body, where it is free to vary.

  This invariant is the reason the cited precedent works and is not obvious from reading it:
  `mutation-testing.yml:121` sets `ISSUE_TITLE: "mutation-testing: monthly run failed"`, a
  literal with no interpolation, and `mutation-notify.sh:101-107` finds by title over a
  label-filtered list and closes `.[0].number`. Round 2 found this spec had interpolated
  `<tag>` into the title while citing that precedent, breaking the exact property the
  precedent depends on. Adding useful detail to the title reads as an improvement and is the
  specific edit that reintroduces the defect.
- On the next run where that binary reaches `ready`, close its open issue. A binary whose
  SBOM reappears should not leave a stale issue behind.
- Idempotency by **local exact title match** over `gh issue list --label sbom-asset-missing
  --state open --json number,title`, never `--search ... in:title`. The search index lags,
  and the backlog already carries that construct as a known false-negative source
  (`2026-09-01-mutation-notify-mock-isolation-and-labels-design.md`, Out of scope). A
  duplicate issue is the failure mode a lagging index produces here, and a local match over
  a labelled list has no index between it and the answer.
- `dormant` files nothing and closes nothing. A binary that has never been released has no
  issue to open and no issue to leave stale.

The label must be created before the first run that needs it; `gh label create
sbom-asset-missing` is part of this change, alongside the three `gh api` calls in Section 2.

### Run after signing, as a job — not on an event

Each `release-<name>-rs.yml` gains a third job calling the monitor for its own binary:

```yaml
  sbom-monitor:
    needs: [sign]
    uses: ./.github/workflows/release-sbom-monitor.yml
    with:
      binary_name: <name>
      release_tag_pattern: "<name>-v"
    permissions:
      contents: read
      issues: write
```

Uniform across all eleven: each already carries `sign: needs: [release], uses:
./.github/workflows/release-sign.yml`, measured 2026-09-04, so `needs: [sign]` hangs off
existing structure rather than introducing a new dependency shape.

**Round 2 rejected the obvious alternative, `on: release: types: [published]` on the
scheduler, and the reasons are worth keeping because both are invisible from the YAML.**

1. **It never fires.** All eleven release workflows publish via `softprops/action-gh-release`
   with no `token:` override, i.e. `GITHUB_TOKEN`, and GitHub does not start new workflow
   runs from `GITHUB_TOKEN`-triggered events.
2. **If it did fire, it would fire too early.** `release: published` is emitted by the
   `release` job; the SBOM is uploaded by the downstream `sign` job's *last* step, after a
   checkout, a syft install, a cosign install and a keyless sign. The monitor would read the
   asset list before the asset existed and report `missing-asset` on every healthy release —
   a spurious red plus a spurious issue, on the one event chosen because the operator is
   watching. That is issue #100's fatigue shape reintroduced by the mechanism added to avoid
   it.

`needs: [sign]` removes both by construction rather than by timing: same-workflow job
dependencies are unaffected by the `GITHUB_TOKEN` rule, and the asset exists before the job
starts because the job that uploads it has completed. It also removes the ten superfluous
`dormant` jobs a release-wide event would run, and it makes a failed `sign` skip the monitor
rather than misreport it — a `sign` that never ran cannot produce an absent-asset verdict
that reads as a signing defect.

`release-sbom-monitor-schedule.yml` keeps its `cron` unchanged. It is the sweep over
already-released binaries; the per-release job is the prompt check on the one that just
shipped.

**A note on mechanism versus surface, since the two disagree here.** This change deletes one
trigger and adds eleven job blocks: the mechanism shrinks (no event semantics, no
`GITHUB_TOKEN` rule, no ordering race) while the touched surface widens from one file to
eleven. Recorded because a "is the design getting smaller" signal is unfalsifiable unless it
names which quantity it reads. This one reads mechanism.

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

`{"matches":[]}` over an empty or malformed SBOM is indistinguishable from a genuinely
clean scan — the same false-PASS class as the outer defect, one level down. So on
`state=ready`, `scripts/sbom-resolve.sh` reads the downloaded SPDX file itself
(`jq '.packages | length'`) and emits a second output, `packages=<N>`, alongside `state`.
The workflow writes it to the summary.

**The count belongs in the script, not in the workflow's scan step.** Round 1 found all
three lenses converging here: the first draft placed it in an inline `run:` block, so the
positive control the spec itself mandates was unsatisfiable by the suite named to contain
it — the exact untestable layer "Extract before fixing" exists to escape. `packages` is an
output of the script for one reason: so a bats case can assert a specific number against a
fixture.

A `packages=0` on a `ready` state is not itself an error — an SBOM legitimately containing
zero packages is possible — but it is written and visible, which is the whole point. It
adds no branch.

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
- **Derived value** — `ready` against a fixture SPDX containing a known number of packages;
  assert `packages=<that number>` exactly. This is the positive control.

Three further cases cover the issue file/close arm, which round 2 found was the newest and
most delivery-critical machinery in the spec and the only part with no named test:

- **Files once** — `missing-asset` with no open issue under the label; assert
  `gh issue create` was called with the exact tag-free title and the `sbom-asset-missing`
  label.
- **Does not duplicate** — `missing-asset` with an issue already open under that exact
  title; assert `gh issue create` was **not** called. Run this case a second time with the
  release tag changed and assert it still does not duplicate — that is the assertion that
  fails if anyone reintroduces the tag into the title, so it is the regression test for the
  invariant, not just for the dedup.
- **Closes only its own subject** — `ready` for `pi` while an open issue exists for
  `factorial`; assert `factorial`'s issue is untouched. This is the case that would have
  caught round 2's third failure mode, where an implementer following
  `mutation-notify.sh` literally closes `.[0].number` off a label-filtered list.

A positive control is required, per `bug-scan` Step 6, and round 1 showed the first draft's
nominated control did not qualify. Every other case in this list asserts a string constant
(`state=dormant`, `state=ready`) or an exit code, and a stub with a hardcoded lookup table
passes all of them — including `state=ready`, which is itself the constant. Only the
`packages=<N>` case pins a value the script had to compute from an input it actually read.
The fixture SPDX lives beside the suite and its package count is asserted from the fixture's
own content, derived in the test rather than copied from the script's output.

`scripts/sbom-resolve.sh` joins `SHELL_SOURCES` and the bash-coverage instrumented set
automatically through the existing `git ls-files 'scripts/*.sh'` predicate. The coverage
figure is expected to move up; the `FLOOR=24` in `auto-merge.yml` is not changed by this
work.

## Section 2 — Branch protection

The numbered steps below, in order. No code diff.

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

### 1b. Capture classic protection before the PATCH

Raised in round 1: the spec captured the ruleset before the irreversible DELETE but no
pre-image before the `PATCH`, and the `PATCH` is the operation that replaces an array.
`enforce_admins: false` means a bad result is recoverable rather than a brick, but the
pre-image costs one read and belongs beside the ruleset JSON.

```bash
gh api repos/brujack/math/branches/master/protection > protection-pre-image.json
```

State as of 2026-09-02, to be re-read and pasted at implementation time in case it has
moved:

```
required_status_checks.contexts : ["secret-scan", "mutation-pr"]
required_status_checks.strict   : false
required_linear_history         : true
allow_force_pushes              : false
allow_deletions                 : false
enforce_admins                  : false
required_signatures             : false
block_creations                 : false
required_conversation_resolution: false
lock_branch                     : false
allow_fork_syncing              : false
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
bats tests/scripts/sbom_resolve.bats             # every case listed under Tests
make test                                        # lint + test-hooks + test-python
```

Each bats case must be seen red before its implementation exists — in particular the
`gh release view` failure-discrimination case, which is the one the current workflow gets
wrong and therefore the one whose RED proves the fix is real.

Section 2 is verified by the `gh api` reads in its own Verification subsection, run after
its numbered steps.

The end-to-end behaviour of Section 1 cannot be verified before the first per-binary
release exists: `dormant` is the only state reachable in production today. That is stated
rather than worked around — the bats cases cover all three states against the `gh` mock,
and the `ready` and `missing-asset` paths remain unexercised against real GitHub until a
release is cut. Under decision 7 the first per-binary release exercises them on its own:
the `sbom-monitor` job runs inside that release's workflow run, so its verdict appears in
the run the operator is already watching rather than on a later scheduled run.

**No count of cases, steps, or reads is restated outside the section that lists them.**
Three had already drifted by 2026-09-04 — "the five cases above" against a list that had
grown to nine, and "three actions" twice against a Section 2 that had grown to five numbered
steps. Each was written true and became false when a different section grew, which is the
same shape as the Risks bullet that claimed absent apparatus: a document asserting something
about itself that another edit invalidated. Restating a count is what creates the drift, so
these now point at the section instead of counting it.

## Scope

**In scope:** `scripts/sbom-resolve.sh` (new), `tests/scripts/sbom_resolve.bats` (new)
plus its fixture SPDX, `.github/workflows/release-sbom-monitor.yml` (the two resolution
steps, the summary lines, and the issue file/close arm),
all eleven `.github/workflows/release-<name>-rs.yml` (one `sbom-monitor` job each),
`CLAUDE.md` (Branch protection subsection, and the CI table if the new script warrants a
row), one `gh label create`, the `gh api` calls enumerated in Section 2, and the two
backlog rows this spec closes.

**Out of scope:**

- Cutting a per-binary release. That is the trigger for the `ready` path, not part of this
  change.
- `release-sbom-monitor.yml:94-96`'s `--search in:title` construct and the sibling row about
  it in the backlog. That is a separate finding with its own reasoning
  (`2026-09-01-mutation-notify-mock-isolation-and-labels-design.md`, Out of scope) and is
  untouched here.
- ~~Filing an issue on `missing-asset`.~~ **Moved in scope by decision 6** after round 1
  established that a red job conclusion is not a delivery mechanism in this repo. A job
  failure is a record, not a notification.
- ~~`on: release: types: [published]` on the scheduler.~~ **Rejected in round 2** — inert
  under `GITHUB_TOKEN` and mis-ordered against the `sign` job. Replaced by decision 7.
- Proving the *scanner* read the SBOM. `packages=<N>` proves `sbom-resolve.sh` parsed the
  SPDX; `anchore/scan-action` opens the file independently, so `{"matches":[]}` from an
  inert scan step still reads as clean. All three lenses raised this in round 2 and none
  would block on it. Backlogged rather than fixed, and named here so `packages` is not
  mistaken for a live check on the scanner — it is a test handle.
- Adding job `name:` to `amicable-rs.yml` and `scripts.yml` so they stop reporting as the
  bare context `test`. Real, but unrelated to either row — backlogged.
- Migrating classic protection to rulesets. GitHub's forward direction and a genuine
  migration; it deserves its own spec, not a rider on a dead-config cleanup.
- `gh release list --limit 50 ... | head -1` selects the most recently published matching
  release, not the highest semver. Correct for the current one-release-per-binary model and
  worth revisiting if backports ever ship — backlogged, not fixed here.

## Risks

- **`missing-asset` is unreachable until the first release**, so the branch ships untested
  against real GitHub. Mitigated by the bats `missing-asset` case, by the `needs: [sign]`
  job running it on the release itself rather than up to 30 days later, and by the
  operator's answer that a release is weeks away with no blocker. `release-sign.yml` has
  never run once, so its first execution is also its first test — but `needs: [sign]` means
  a failed `sign` skips the monitor rather than producing an absent-asset verdict, so a
  `missing-asset` from that job is a real signing defect and not an artifact of `sign`
  having failed.
- **The issue file/close arm is new machinery on a path that has never executed.** A defect
  in it produces either a missing issue (silent, the failure this spec exists to end) or a
  duplicate every month (fatigue, issue #100's shape). The local-exact-title-match choice
  over `--search in:title` bounds the duplicate side; the three issue-arm cases in Tests
  cover the missing side.

  Round 2 found this bullet asserting bats coverage that the test list did not contain — a
  risk mitigation named against apparatus that was never specified. That is checkable
  cheaply and generally: **take the noun a Risks bullet cites as its mitigation and grep the
  test list for it.** It answers a different question from a mutation check — not "does this
  test discriminate" but "does this test exist." Every mitigation-naming bullet in this
  section was swept that way on 2026-09-04; this was the only false one, and the stale
  reference to the deleted trigger in the bullet above was the only other correction.
- **A `PATCH` to `required_status_checks` replaces rather than appends.** Sending an
  incomplete array silently drops a required context. The verification read of
  `.required_status_checks.contexts` is what catches this and is not optional.
- **Deleting the ruleset is irreversible from the UI.** Mitigated by the captured JSON
  above, which is the reason step 1 exists.
- **The `CLAUDE.md` paragraph is the only record of the protection state**, by decision 5.
  It goes stale silently if the contexts change and nobody edits it. Accepted: the
  alternative was a drift check whose output nothing reads.
- **Decision 5 and decision 6 now answer the same question in opposite directions** — a
  prose record for protection state, a labelled issue for `missing-asset`. That is
  deliberate rather than inconsistent: protection changes are made *by a person who is
  already looking*, so a record suffices, while `missing-asset` fires unattended on a
  schedule and must reach someone who is not looking. Stated because round 1 correctly
  flagged the first draft for answering it two ways without saying why.

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

Disposition: **Accepted in part, Addressed in part.** Accepted on proportionality: the
operator confirms a per-binary release is weeks away with no blocker, which removes the
"deferred value with no trigger" objection — the branches that change a verdict become
reachable shortly rather than never. Addressed on the reads-it half: decision 6 gives
`missing-asset` a durable consumer (a labelled issue) instead of a job summary. The lens was
right that the `dormant` marker alone changes no verdict, and it does not claim to — it is
the cheap half, and the issue arm is the mechanism.

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

Disposition: **Addressed.** The operator confirms failed scheduled runs do not reliably
reach them by email, so the finding is stronger than stated: neither side had a channel, not
just green. Decision 6 gives the red side a labelled issue. The lens's own proposed remedy
for the transition-day half — an `on: release` trigger — was adopted here and then refuted by
all three lenses in round 2; see decision 7 and the round 2 process note.

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

Disposition: **Addressed.** `packages=<N>` moves out of the workflow's inline `run:` block
and becomes an output of `scripts/sbom-resolve.sh`, with a bats case asserting it against a
fixture SPDX — so the positive control is reachable by the suite named to contain it. The
smaller item is addressed too: Section 1b now captures a classic-protection pre-image before
the `PATCH` that replaces its contexts array.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger. No arms, no judge
component; acceptance criteria are concrete exit codes, state strings, and API reads.

## Multi-Lens Review — Round 2

Reviewed at commit: `ac2f9ac00cf9b4794deb87ac90be765fb89f2cd2` (round 1 dispositions applied)

Round 2 was a full re-run of all three lenses rather than a scoped one, because the round 1
revision changed design substance — a new issue file/close arm, a new trigger, and an output
moved between layers — and a correction is new design carrying its own new defects. It was
justified: **every round 2 finding is a defect the round 1 fix introduced.** None existed in
the text round 1 read.

All three lenses independently confirmed round 1's `packages=<N>` fix closed properly: six
cases, three expecting exit 0 and three non-zero, with `packages=<N>` a genuine derived
quantity that a parser returning `{}` would fail. The verdict count is no longer
PASS-dominated.

All three findings were dispositioned **Addressed** on 2026-09-04, after the operator
circulated round 2 to an independent architectural reviewer whose reading is folded into the
notes below.

**A process finding this round produced, which belongs with the others: the defect round 2
killed was a remedy round 1's own ergonomics lens proposed verbatim.** It entered the design
without being subjected to the verification applied to the author's text, and was then
refuted by all three lenses one round later. A fix proposed by a review lens carries review
authority while being itself unreviewed — it arrives inside the document whose purpose is
scrutiny, which is exactly what makes it feel already-checked. Treat a reviewer's suggested
remedy as new design with no standing, not as a finding that has already passed review. The
separately-nameable half, owed to the independent reviewer: the trigger was chosen for *the
moment it fires* rather than for *what it can observe at that moment* — a delivery argument
and an observability question, never checked against each other.

### Goal-Fit

Finding: `on: release: types: [published]`, the mechanism added in round 1 to collapse the
deferral, is inert in the common case and wrong in the other. All eleven
`release-<name>-rs.yml` workflows publish via `softprops/action-gh-release` with no `token:`
override, i.e. `GITHUB_TOKEN`, and GitHub does not start new workflow runs from
`GITHUB_TOKEN`-triggered events — so the trigger never fires for a release this repo cuts.
If it did fire (a UI or PAT-cut release), `release: published` is emitted by the `release`
job while the SBOM is uploaded by the downstream `sign` job's _last_ step, so the monitor
reads the asset list before the asset exists and reports `missing-asset` deterministically.
The spec predicted that first run would likely be `missing-asset` and gave the wrong reason:
not because `release-sign.yml` is unproven, but because the ordering guarantees it. Cheaper
path that keeps the value: delete the trigger and call `release-sbom-monitor.yml` as a job
in each `release-<name>-rs.yml` with `needs: [sign]` — same-workflow job dependencies are
unaffected by the `GITHUB_TOKEN` rule, fire in the operator's line of sight, and make the
ordering correct by construction.

Also noted, not raised as a finding: the `dormant` marker and `packages=<N>` remain
decoration in production by the reads-it test — `packages` earns its place as a test handle
rather than a live signal, and the spec should say so or a later reader will treat it as a
check.

Assumption: that a `release: published` event reaches this workflow at a moment when the
SBOM asset already exists. Both halves are uncertain and they fail independently. Refuted
by cutting one throwaway release through the documented `workflow_dispatch` path and
checking `gh run list --workflow release-sbom-monitor-schedule.yml --event release` for a
run; an empty list refutes the first half.

Disposition: **Addressed.** The trigger is deleted. Decision 7 replaces it with a
`needs: [sign]` job in each of the eleven `release-<name>-rs.yml`, removing both halves of
the defect by construction rather than by timing. The reads-it observation is addressed too:
`packages` is now named in Out of scope as a test handle rather than a live check on the
scanner.

### Ergonomics

Finding: the same trigger defect, reached independently, plus its downstream consequence —
every release would produce a spurious red job and a spurious `sbom-asset-missing` issue on
the one event chosen because the operator is already watching, which is issue #100's fatigue
shape reintroduced by the trigger added to avoid it. Compounding it: that issue cannot
self-heal, because the title embeds the tag while the close arm matches exactly and
`gh release list | head -1` resolves the newest tag — so once a newer tag lands, the run
reconstructs a different title and the old issue is unmatchable forever. Over several
releases the stream converges on one permanently-open, manually-closed issue per release.

Second finding: none of the six bats cases touches the issue file/close arm, while the Risks
section asserts "the missing side is covered by bats cases over the `gh` mock." No such case
is specified. The newest and most delivery-critical machinery is the only part with no named
test, and the spec claims coverage it does not have.

Assumption: that `release-sign.yml` succeeds at all on its first-ever execution (0 runs
ever; its `cosign`/`syft` pins have never been exercised). If it fails, `missing-asset` is a
true positive rather than a race artifact — and the design cannot tell those two apart,
because both produce an absent asset at the same moment. Settled by cutting the first
release and recording whether the asset appears, and how many seconds after `published_at`.

Disposition: **Addressed.** The same trigger deletion resolves the spurious-red-per-release
consequence. The stale-issue half is resolved by the tag-free title rather than by the
proposed prefix match — with the tag out of the title, file-key and close-key are the same
string, so nothing goes stale and no prefix matching is needed. The missing coverage is
addressed by three named issue-arm cases in Tests, and the false claim that prompted the
finding is corrected in Risks, along with a sweep of every other mitigation-naming bullet in
that section.

### Risk

Finding: the issue arm keys "file" and "close" on two different identities, and the
precedent it cites survives only because that precedent's title is a constant. Verified:
`mutation-testing.yml:121` sets `ISSUE_TITLE: "mutation-testing: monthly run failed"` — a
literal with no interpolation — and `mutation-notify.sh:101-107` finds by
`--search "in:title \"${ISSUE_TITLE}\""` over a label-filtered list and closes
`.[0].number`. That find/close pair is correct _because_ the title is invariant across runs.
This spec interpolates `<tag>` and breaks that invariant while claiming the precedent. Three
concrete failures: a `ready` at a newer tag never closes the older tag's issue (permanent
stale issue — the silent failure this spec exists to end); a still-broken newer tag does not
match the existing issue either, so a second issue is filed for the same binary; and an
implementer following the precedent literally would close `.[0].number` off a label list, so
a `ready` on `pi` closes `factorial`'s live issue — #128's shape one level down, since the
spec separated labels per producer and never separated issues per subject within a producer.
Fix: make the title tag-free (`[SBOM Monitor] SBOM asset missing for <binary>`), put the tag
in the body, and add the missing cases.

Not raised, deliberately, each checked: `issues: write` already exists on the reusable
workflow and all eleven caller jobs, so the parallel-jobs permission concern is moot; titles
are distinct per binary so eleven concurrent creates do not race; `bash-coverage` reports
under exactly that context string with no `if:` and no `paths:`, so decision 4 cannot
deadlock master; and `sbom-asset-missing` does not exist as a label today, so the
`gh label create` step is genuinely required.

Assumption: that the SBOM asset is attached to the release before the monitor reads the
asset list. If it holds false, the trigger's very first firing is a guaranteed false
positive, and the trigger being inert is currently the only thing preventing it. Confirmed
by timing the first real per-binary release — compare `published_at` against the sign job's
asset-upload completion.

Disposition: **Addressed, and this finding produced the most durable change in the spec.**
The title is now tag-free with the tag in the body, and the design states the invariant
explicitly — *the title is the key, not a description* — because the fix is a state while the
sentence is what keeps it. Adding the tag back reads as an improvement to anyone scanning an
issue list, so the property belongs next to the field rather than in a review section. The
"does not duplicate" bats case is specified to re-run with a changed tag, which makes it the
regression test for the invariant rather than only for the dedup.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.

## Multi-Lens Review — Round 3

Reviewed at commit: `58049c2b7a16331fdbf5a94254ee96ce1119a105` (round 2 dispositions applied)

Full re-run of all three lenses. **Third consecutive round in which every finding is a defect
created by the previous round's fix**, and the second in which a lens refuted a claim written
during the previous round's own corrective sweep.

Both load-bearing measurements were independently reproduced by this session rather than
taken on the lenses' report.

### Goal-Fit

Finding: **decision 7 makes `missing-asset` unreachable on the release path, and the Risks
section claims the opposite.** `release-sign.yml`'s last step is
`gh release upload ... "${BINARY_NAME}.sbom.spdx.json"` with no `continue-on-error`
(`grep -c continue-on-error` → 0), so `sign` success implies the asset is present. And
`needs: [sign]` means a failed or cancelled `sign` **skips** the monitor job. The per-release
job's only reachable verdict is therefore `ready`.

The scenario this suppresses is the most likely real generator of `missing-asset`: in all
eleven workflows `sign: needs: [release]`, so the release is published *before* signing, and
`release-sign.yml` downloads the binary *from* that release — it must be. A failed `sign`
therefore leaves a **published release carrying the binary and no SBOM**. The spec argued
the skip as a virtue — "a `sign` that never ran cannot produce an absent-asset verdict that
reads as a signing defect" — which treats the true positive as a false one. The Risks bullet
then asserts the inverse, naming `needs: [sign]` as the mitigation for `missing-asset` being
unreachable. That bullet was rewritten during the 2026-09-04 sweep this spec cites as having
checked every mitigation-naming bullet: same sweep, same defect class, one revision later.

Assumption: that `missing-asset` is a state this pipeline can reach at all. Its most
plausible generator is a published release whose `sign` failed, and decision 7 skips the
monitor in exactly that case.

Disposition: **Addressed by redesign.** The operator has directed that the release pipeline
change as well. See "Round 3 outcome" below — the finding is not patched with `if: always()`
but removed at its source.

### Ergonomics

Finding: the round 2 fix moved the tag out of the title and into the body, but nothing ever
writes the body again, so the operator's one durable channel freezes at the first failure and
silently misnames the broken release thereafter. The cited precedent does not have this
problem and the spec took half of it: `mutation-notify.sh` comments the current run onto an
existing issue (`:125`) and comments before closing (`:106-107`), and this spec cites
`:101-107` for the constant-title property while dropping both `gh issue comment` arms — the
two calls that carry the varying detail a constant title can no longer hold. Live evidence:
issue #98 (`mutation-testing: monthly run failed`) was open 2026-08-02 → 2026-09-01 and
accumulated **3 comments**; under this design that span produces zero.

Second limb: **no case asserts a close actually happens.** "Does not duplicate" asserts
`create` was not called and "closes only its own subject" asserts a sibling issue is
untouched — both pass trivially if `gh issue close` is never invoked. An implementation that
files and never closes is green across all nine cases, and its production symptom is the
permanently-open stale issue the arm exists to prevent. Third: eleven hand-maintained job
blocks with no test asserting all eleven carry one; a twelfth binary added later ships
unmonitored, and the failure is `dormant`-shaped.

Assumption: that an SBOM-missing condition resolves inside roughly one release cycle. The
in-repo counter-evidence points the other way — `mutation-testing.yml` failed six consecutive
times across two months, and #98 spanned 30 days.

Disposition:

### Risk

Finding: round 1 moved `packages=<N>` *into* `sbom-resolve.sh`; round 2 moved
`sbom-resolve.sh` *onto the release path*. The pair was never reviewed together, and it gives
a value the spec explicitly calls a test handle rather than a live check the power to fail a
release run in a state the design has no name for. Reproduced independently by this session:

```
jq '.packages | length'
  well-formed with packages   rc=0  out=[2]
  well-formed, no .packages   rc=0  out=[0]     <- indistinguishable from a real empty SBOM
  truncated / malformed       rc=5  out=[]      <- UNMODELLED
  zero-byte file              rc=0  out=[]      <- packages= , neither a number nor an error
```

The `rc=5` row is the risk and the spec says nothing about it. If it propagates, `state` is
never written, the issue arm never fires, and the result is a **red release run with no
issue** — the silent failure this spec exists to end, relocated onto the path the operator
was told is now in their line of sight. If it is swallowed, the positive control returns
empty rather than failing. Round 2's confirmation that "a parser returning `{}` would fail
it" was the wrong probe: `{}` is well-formed and returns `0` at rc=0. The failing input is
malformed and was never tested.

Smaller, same seam: `missing-asset → exit 1` makes the whole `release-<name>-rs` run report
failed for a release whose tag, binary, checksum and CHANGELOG all shipped, so
"release-pi-rs failed" acquires two meanings.

Not raised, checked and clean: permissions and secrets on the `needs: [sign]` call — job-level
`permissions` replaces rather than is bounded by the workflow-level block, `secrets.GITHUB_TOKEN`
reaches a called workflow without `secrets: inherit`, and the scheduler already calls this exact
reusable workflow with an identical block and authenticated successfully on 2026-08-03.

Assumption: that there is no read-after-write propagation lag between the `sign` job's
`gh release upload` and the monitor's `gh release view --json assets`. `needs: [sign]`
removes the *job-ordering* race; it does not remove an *API propagation* race, and the spec
treats the two as one problem. Nothing in this repo has observed the interval — zero release
workflow runs, ever.

Disposition:

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.

### Round 3 outcome — the findings share one upstream cause

None of the three lenses reached this, and it is the reason round 3 does not get patched the
way rounds 1 and 2 were. **Every round 3 finding, and both earlier trigger defects, descend
from a single ordering fact: the release is published before the SBOM is attached.**

- Round 2's rejected trigger fired between publication and attachment.
- Round 3's `needs: [sign]` skip exists because a failed `sign` can leave a *published*
  release without an SBOM.
- Risk's propagation-lag assumption only matters because a consumer reads the asset list
  immediately after publication.

Three rounds have produced three workarounds for one cause, each introducing defects of the
same magnitude as the one it fixed, and the design has grown every round — the opposite of
the convergence signal. The operator has directed that the release pipeline change as well.

Publishing the release as a **draft**, attaching the SBOM and signature during `sign`, and
flipping it to published only after `sign` succeeds makes *published implies SBOM present*
true by construction. That removes the class rather than working around it a fourth time, and
it collapses most of Section 1: with the invariant holding, `missing-asset` on the release
path is not merely skipped but genuinely impossible, and the state becomes a monthly-sweep
signal for out-of-band causes only — a manually-cut release, a deleted asset, or a release
published before this change.

That is a change to the release pipeline rather than to the monitor, with its own blast
radius, and it is specified separately. This spec's Section 1 is **on hold pending that
change**; Section 2 is independent, has drawn zero findings across three rounds, and is
unaffected.

---

## Section 1's premise is refuted — measured 2026-09-04

Everything above about the SBOM monitor assumes the SBOM it scans has content. It does not.

```
                                          syft   sbom     lockfile
binary                    format          pkgs   bytes    crates
sq  (this repo, Mach-O arm64)                1    1208       133
e   (Mach-O arm64)                           1       -       137
pi  (Mach-O arm64)                           1       -       137
prime (Mach-O arm64)                         1       -       133
sq  (ELF x86-64, workstation — CI's format)  1    1208       133
```

syft 1.51.1 throughout. The single package is named for the binary and carries no
`externalRefs` — syft's generic binary entry, not a dependency. `grype` scans that list, so
**the monitor cannot find a CVE**: there is nothing in the document to scan. Nothing in this
repo builds with `cargo-auditable`, whose `.dep-v0` section is what syft's
`rust-audit-binary` cataloger reads.

Three full multi-lens rounds on this spec — nine lens dispatches, roughly 1.3M subagent
tokens — argued about when the monitor fires, what it files, how it dedups, which state it
reports and how it closes an issue. **None asked what the document contains.** The check that
settled it needed no release, no workflow run and no code, and was available before round 1.

**Section 1 is superseded, not merely on hold.** Its whole apparatus — the three-valued
state, the `sbom-asset-missing` label, the file/close arm, the title invariant, the fourth
`unreadable-sbom` state — describes the handling of an artifact that catalogues nothing. What
survives is the observation that a green run currently means "examined nothing", which is
true for a second and more fundamental reason than the one this spec found.

The fix and the re-scoped work live in
`docs/superpowers/specs/2026-09-04-release-ordering-atomic-publication-design.md`, whose
Part 0 changes the build so an SBOM is worth producing. Rewriting Section 1 before that
lands would be a fourth revision against a premise now known false.

**Section 2 (branch protection) is unaffected.** It is independent of the SBOM entirely, drew
zero findings across all three rounds, and remains ready to ship on its own.
