# Mutation-notify: index-independent lookup, run serialisation, per-call mock

Date: 2026-09-01
Status: Spec

Bundles three backlog rows that share one file, one failure and one test harness — the
duplicate-issue lookup, the missing `concurrency` block on both mutation workflows, and
`tests/mocks/gh`'s inability to fail a single call — plus a second instance of the
lookup defect found during Multi-Lens Review and folded in by operator decision.

They are specified together because the mock change is a prerequisite for testing the
lookup change, and the serialisation was the suspected mechanism behind the lookup
failure.

> **Revision note.** This document was substantially revised after Multi-Lens Review
> round 1. Three claims in the original were wrong and are corrected in place: the race
> hypothesis (refuted — see below), the positive control's role (inverted), and the
> characterisation of the cross-workflow hazard as introduced-by-this-fix (it is
> already live). The review section at the foot records what was found and what was
> done about it.

## Problem

### The observed failure

Measured 2026-09-01 against the live tracker, not taken from the backlog row that
prompted this:

```
$ gh issue list --repo brujack/math --state all --label mutation-failure \
    --limit 20 --json number,title,state,createdAt \
    --jq '.[] | "\(.number) \(.state) \(.createdAt) \(.title)"'
99 CLOSED 2026-08-02T02:13:37Z mutation-testing: monthly run failed
98 OPEN   2026-08-02T01:57:03Z mutation-testing: monthly run failed
96 CLOSED 2026-08-02T01:11:51Z mutation-testing: monthly run failed
92 CLOSED 2026-08-01T23:31:34Z mutation-testing: monthly run failed
```

**The defect is three consecutive lookup misses, not one duplicate filing.** Correlating
the issues above with the workflow's own run record:

```
$ gh run list --repo brujack/math --workflow=mutation-testing.yml --limit 12 \
    --json startedAt,updatedAt,conclusion,event
23:25:43 -> 23:31:37  failure  workflow_dispatch    (files #92 @ 23:31:34)
23:36:04 -> 23:43:55  success  workflow_dispatch
23:44:16 -> 00:25:29  success  workflow_dispatch
00:30:45 -> 01:11:54  failure  workflow_dispatch    (files #96 @ 01:11:51)
01:16:24 -> 01:57:06  failure  workflow_dispatch    (files #98 @ 01:57:03)
01:58:05 -> 02:03:43  success  workflow_dispatch    <- should have CLOSED #98, did not
02:05:08 -> 02:10:38  success  workflow_dispatch    <- should have CLOSED #98, did not
02:11:22 -> 02:13:40  failure  workflow_dispatch    (files #99 @ 02:13:37) <- should have COMMENTED
```

#98 was open the whole time and was missed three times running — at roughly 7, 13 and
17 minutes of age.

**Two of those three misses are silent, and they are the more serious half.** A red run
that misses files a visible duplicate; that is how this was noticed. A _green_ run that
misses simply fails to close, and the observable is an absence — a tracking issue that
stays open with nothing anywhere recording that a close was attempted and lost. Both
green runs above did exactly that.

That has a consequence for housekeeping: **#98 being open today is an artifact of this
bug**, not an independent question about whether mutation runs are still failing.

### The race hypothesis is refuted

The originating backlog row offered overlapping dispatch runs as a candidate cause, and
an earlier draft of this spec called four-issues-in-three-hours "direct evidence" for
it. That was wrong, and the run record above is what refutes it: every run is strictly
sequential, with end-to-next-start gaps of 4m27s, 21s, 5m16s, 4m30s, 59s, 1m25s and
44s — all positive. Widening to all 12 runs in the workflow's history finds **no
overlap at any point, ever**.

All eight were `workflow_dispatch`: an operator hand-testing the OOM fix of ADR-0024.
Sequential runs, not concurrent ones.

**No race has occurred, so serialisation fixes nothing that has been observed.** It stays
in this spec as cheap prophylaxis — four lines of YAML against a hazard that is real in
principle — but it is labelled as such, the same way the title filter's status is
labelled below. A mechanism claiming measured backing it does not have inflates the
apparent size of the problem and misleads whoever reads this next.

### Why the search index is the wrong dependency

`gh issue list --label` and `--state` are served from the issues API. `--search` is
served from the search index, which is eventually consistent and carries no freshness
guarantee. A lookup whose entire job is _"has this already been filed"_ cannot rest on a
source permitted to not know yet — and its failure is silent, because an empty result
is indistinguishable from a genuine absence.

Run by hand on 2026-08-31 (reported in the backlog row) and again on 2026-09-01, the
same query returns `98`. The query is not permanently broken; it is intermittently
wrong, which is worse to diagnose and identical in effect.

Three misses spanning 17 minutes is a long lag. No further cause is asserted here — the
run record rules out the race, and nothing available distinguishes remaining candidates.
The fix does not depend on which it was.

### The query was never an exact match either

Separately from the index question, `in:title "..."` is **not** a phrase match. Measured
2026-09-01:

| search phrase                                         | returns |
| ----------------------------------------------------- | ------- |
| `mutation-testing: monthly run failed`                | 98      |
| `mutation-testing monthly run failed` (colon dropped) | 98      |
| `monthly run failed` (strict substring)               | 98      |
| `mutation-testing-python: monthly run failed`         | —       |
| `completely unrelated words here`                     | —       |

It is an AND over tokens, and hyphenated compounds split:

```
in:title "mutation"        -> 98,99,96,92
in:title "testing"         -> 98,99,96,92
in:title "mutation-testing"-> 98,99,96,92
```

**This makes the cross-workflow hazard already live in the shipped code, and
asymmetric.** The Rust query's tokens are `{mutation, testing, monthly, run, failed}`.
A Python issue titled `mutation-testing-python: monthly run failed` carries
`{mutation, testing, python, monthly, run, failed}` — a strict superset. So a Rust
lookup matches a Python issue, while a Python lookup does not match a Rust one (row 4
above: the extra `python` token is absent from the Rust title, so the AND fails).

The consequence is concrete: the first time the Python workflow files an issue, a green
Rust run can comment _"Green as of …. Closing."_ on it and close it.

This corrects an earlier draft, which described the cross-workflow hazard as one the
label-only fix would _introduce_. It does not introduce it — it inherits it. The title
filter is therefore repairing a defect that exists today, not preventing one the fix
would create. It remains unobserved only because the Python workflow has never filed an
issue (the query above returns no `mutation-testing-python` title, in any state).

### Why the test suite cannot currently see any of this

`tests/mocks/gh:4` evaluates `MOCK_GH_EXIT` before any subcommand dispatch, so a test
that makes one `gh` call fail makes every `gh` call fail. `scripts/mutation-notify.sh`
has six `gh` call sites, five propagating with `|| return 1` and one deliberately
`|| true`:

| line | call                            | guard                    |
| ---- | ------------------------------- | ------------------------ |
| 99   | `gh issue list`                 | `\|\| return 1`          |
| 104  | `gh issue comment` (green path) | `\|\| return 1`          |
| 105  | `gh issue close`                | `\|\| return 1`          |
| 115  | `gh issue comment` (red path)   | `\|\| return 1`          |
| 117  | `gh label create`               | `\|\| true` — deliberate |
| 119  | `gh issue create`               | `\|\| return 1`          |

Measured 2026-09-01 during `bug-scan`, and independently reproduced twice during
Multi-Lens Review: stripping `|| return 1` from the issue lookup, and separately from
`gh issue close`, each leaves the 29-case suite **fully green**. Both mutations assert
as landed. Three of the five propagation sites are pinned only collectively.

Production is correct today. The exposure is a future edit dropping a guard with no test
going red.

### The same defect at a second call site

`.github/workflows/release-sbom-monitor.yml:94-96` carries the identical construct:

```bash
EXISTING=$(gh issue list --label sbom-monitor --state open \
  --search "\"[SBOM Monitor] ${CVE_ID} in ${BINARY_NAME}\" in:title" \
  --json number --jq '.[0].number // empty')
```

It sits **inside a per-finding `while read` loop**, so a single index lag duplicates
every Critical/High CVE issue in the pass rather than one. It also carries two
aggravating differences from the mutation-notify site: no `--limit`, so the default page
size of 30 applies to a label that legitimately accumulates one issue per CVE per
binary across 11 binaries; and no `--repo`, unlike every `gh` call in
`mutation-notify.sh` (which adds it so a malformed value fails in gh's argument parser
rather than reaching a live tracker — `tdd.md` E2).

Found by the Goal-fit lens. Originally scoped out of this spec; **folded in by operator
decision** at Step 9.

## Corrections to the backlog rows

**The duplicate-issue row names two call sites that no longer exist.** It cites
`mutation-testing.yml:116` and `mutation-testing-python.yml:119`. The 2026-08-31
notify-attribution work replaced both inline blocks with the shared
`scripts/mutation-notify.sh`:

```
$ grep -n 'issue list' .github/workflows/mutation-testing.yml \
                        .github/workflows/mutation-testing-python.yml
(no output)
```

There is **one call site in the mutation-notify path** — `scripts/mutation-notify.sh:99`
— and one further instance of the same construct at the sbom-monitor site above. The
row's line numbers must not be carried into the plan.

**Both mutation workflows share one label and are distinguished only by issue title.**

| workflow                      | `ISSUE_TITLE`                                 | label              |
| ----------------------------- | --------------------------------------------- | ------------------ |
| `mutation-testing.yml`        | `mutation-testing: monthly run failed`        | `mutation-failure` |
| `mutation-testing-python.yml` | `mutation-testing-python: monthly run failed` | `mutation-failure` |

Not stated in the row, and load-bearing: the row's proposed fix is _"key on
`--label mutation-failure --state open` and filter titles client-side"_, and the second
half is not a refinement of the first. Without it, the label alone cannot tell the two
apart.

## Design

### 1. Lookup and its environment dependency — `scripts/mutation-notify.sh`

```bash
main() {
    : "${RESULT:?}"
    : "${REPO:?}"
    : "${ISSUE_TITLE:?}"
    # The jq filter below reads ISSUE_TITLE via `env`, which reads the PROCESS
    # environment -- a set-but-unexported variable is invisible to it and yields
    # an empty result, i.e. a silent duplicate filing. The `:?` guard above does
    # NOT check exportedness. Export here so the dependency is self-satisfying
    # rather than assumed of every caller.
    export ISSUE_TITLE

    local _existing
    _existing=$(gh issue list --repo "${REPO}" --state open --label mutation-failure \
        --limit 100 --json number,title \
        --jq '[.[] | select(.title == env.ISSUE_TITLE)] | .[0].number // empty') || return 1
    ...
```

Four deliberate choices:

- **`--search` removed.** The index dependency, and the whole defect.
- **`env.ISSUE_TITLE` rather than interpolating the title into the jq program.** The
  titles contain a colon and spaces; interpolating a shell variable into a jq program is
  a quoting hazard with no upside. `gh --jq` has no `--arg`, so the environment is the
  only channel available.
- **`export ISSUE_TITLE`.** Measured 2026-09-01, and this is the reason the line exists:

  ```
  set but NOT exported -> (empty)
  exported             -> 98
  `: "${ISSUE_TITLE:?}"` on a non-exported var -> PASSES
  ```

  An empty result routes `main()` down the no-existing-issue branch and files a
  duplicate — the exact defect being fixed, reintroduced through a different mechanism
  with an identical silent signature. Production is safe today (both workflows set it in
  the step `env:` block) and `mutation_notify.bats:20` exports it in `setup()`, which
  means **no test in the suite can distinguish the two cases**. Making the dependency
  self-satisfying is one line and removes the class.

- **`--limit 100`.** The default is 30. The bug being fixed is a lookup missing an issue
  that exists; a default page size is a second route to the same silent absence.

The rest of `main()` is unchanged.

### 2. Lookup — `.github/workflows/release-sbom-monitor.yml`

Same removal of `--search`, with one structural difference: the created title is
`[SBOM Monitor] ${CVE_ID} in ${BINARY_NAME} ${LATEST_TAG}` while the lookup deliberately
omits the tag, so that a CVE already tracked from an earlier release is found again. So
this site needs a **prefix** match, not the equality match used above:

```yaml
env:
  # ... existing entries ...
  ISSUE_PREFIX: "" # set per-iteration in the loop body
```

```bash
ISSUE_PREFIX="[SBOM Monitor] ${CVE_ID} in ${BINARY_NAME} "
export ISSUE_PREFIX
EXISTING=$(gh issue list --repo "${GITHUB_REPOSITORY}" --label sbom-monitor \
  --state open --limit 100 --json number,title \
  --jq '[.[] | select(.title | startswith(env.ISSUE_PREFIX))] | .[0].number // empty')
```

- **Trailing space in the prefix is load-bearing.** Without it, `pi-rs` prefix-matches a
  hypothetical `pi-rs2` title. The created title always has a space before the tag, so
  the space is present in every real title and costs nothing.
- **`--limit 100` and `--repo` added**, closing the two aggravating differences named
  above.
- **`export`**, for the same reason as §1 — inside a `while read` loop body, an
  unexported assignment is exactly the shape that would be missed.

**Scoping decision, made here rather than asked.** `mutation-notify.sh` exists because
the equivalent inline block was extracted to make it testable. The consistent move would
be to extract this loop the same way. That is rejected for this spec as
disproportionate: it would roughly double the diff and put a second production script
under the V3/V4 mutation runs. Instead this site is pinned by two cheaper checks — a
workflow-shape test asserting `--search`/`in:title` is absent from the file, and a
real-jq test of the `startswith` filter against fixture titles including the
prefix-collision case. Extraction is recorded as the deferred alternative; if this site
grows a third behaviour it should be extracted rather than tested further in place.

### 3. Serialisation — both mutation workflow files

Workflow-level, so it covers the `notify` job as well as `mutants`:

```yaml
concurrency:
  group: ${{ github.workflow }}
  cancel-in-progress: false
```

**Prophylactic, not a fix for anything measured** — see the refutation above.

- **`cancel-in-progress: false`** because cancelling a run mid-flight would manufacture
  the terminated-job case the notify job exists to report on: it would file an issue
  describing a cancellation the concurrency rule itself caused.
- **Group key is bare `${{ github.workflow }}`, no `${{ github.ref }}`.** The common
  idiom appends the ref, which partitions by branch — and a `workflow_dispatch` from a
  feature branch racing the cron on master is precisely the hazard. Both write the same
  tracking issue, so they must share a lane whatever branch dispatched them.
  `${{ github.workflow }}` resolves to the `name:` field; the two are distinct and no
  two workflows in the repo share a name.
- **Separate groups per workflow.** With the title filter they target different issues,
  so a shared group buys nothing — and the Rust run is multi-hour, so it would delay the
  06:00 Python cron behind it for no benefit. Crons are already 2h apart.

### 4. Per-call failure control — `tests/mocks/gh`

Two independent changes to a mock shared with `ci_gate.bats`.

**(a) Exit code keyed on the subcommand, falling back to the existing variable.**

```bash
# Failure is selectable per subcommand: MOCK_GH_EXIT_<SUBCOMMAND>_<VERB>, derived
# from "$1_$2" upper-cased with non-alphanumerics stripped. So `gh issue close`
# reads MOCK_GH_EXIT_ISSUE_CLOSE, `gh label create` reads MOCK_GH_EXIT_LABEL_CREATE.
# MOCK_GH_EXIT remains the all-calls-fail fallback. Unset keys fall through
# SILENTLY -- a mistyped name is a no-op, not an error -- so the resolved key is
# logged below and is assertable.
_key="MOCK_GH_EXIT_$(printf '%s_%s' "${1:-}" "${2:-}" \
    | tr 'a-z-' 'A-Z_' | tr -cd '[:alnum:]_')"
_rc="${!_key:-${MOCK_GH_EXIT:-0}}"
printf 'gh-key %s=%s\n' "${_key}" "${_rc}" >> "${MOCK_CALLS_FILE:-/tmp/mock_calls}"
if [[ "${_rc}" -ne 0 ]]; then
    exit "${_rc}"
fi
```

The name is _derived_ rather than looked up in a hand-maintained list, so a call site
added later is pinnable without editing the mock. `MOCK_GH_EXIT` survives as the
all-calls-fail case; `ci_gate.bats:65` uses it and needs no edit, so **that suite
staying green is the regression check**.

**The `gh-key` log line is not decoration** — it is what makes the derivation itself
assertable, and it is the fix for the failure the review found in the original design
(see §5, and the Multi-Lens section). It also documents the naming scheme in the one
place a reader will already be looking: the call log they are debugging against.

`ci_gate.bats` calls `gh api repos/<owner>/<repo>/commits/<sha>/check-runs`, deriving a
long SHA-dependent key that is never set and collides with nothing that suite sets.

**(b) The `issue list` arm runs the real `--jq` program.**

```bash
elif [[ "$1" == "issue" && "$2" == "list" ]]; then
    command -v jq >/dev/null 2>&1 || {
        printf 'mock gh: jq not installed; the issue-list arm needs it\n' >&2
        exit 127
    }
    _prog=""; _prev=""
    for _a in "$@"; do
        [[ "${_prev}" == "--jq" ]] && _prog="${_a}"
        _prev="${_a}"
    done
    if [[ -n "${_prog}" ]]; then
        printf '%s' "${MOCK_GH_ISSUE_LIST:-[]}" | jq -r "${_prog}"
    else
        printf '%s\n' "${MOCK_GH_ISSUE_LIST:-}"
    fi
```

Scoped to `issue list`, so the `check-runs` arm and every `ci_gate.bats` path are
untouched.

The `command -v jq` guard is load-bearing rather than defensive. Without it an absent jq
yields empty stdout, the script reads that as "no existing issue", and several of the
new tests below pass for that reason — the guard is what stops an absent tool
manufacturing the very silence being tested for.

**(c) Documentation.** `CLAUDE.md:477` currently reads _"`gh` (sequential JSON responses
via `MOCK_GH_PR_CHECKS_N`, exits `$MOCK_GH_EXIT`)"_. Measured: `MOCK_GH_PR_CHECKS` appears
**nowhere in the code** — the variable is `MOCK_GH_CHECK_RUNS_N`. The one derived
mock-variable family this repo already has has drifted out of its documentation and
stayed wrong, which is the argument for fixing it in the same change that adds a second
family rather than after. Correct that line and add `MOCK_GH_EXIT_<SUBCOMMAND>_<VERB>`
and `MOCK_GH_ISSUE_LIST`'s new JSON shape to it. Required anyway by this repo's own
"Keeping CLAUDE.md Up To Date" table (new test infrastructure → Testing section).

### 5. Tests — `tests/scripts/mutation_notify.bats`

`MOCK_GH_ISSUE_LIST` becomes a JSON array. Ten tests currently set it to `"98"`, `""` or
`"null"` (lines 247, 272, 284, 297, 326, 348, 357, 372, 384, 392) and each converts:

| current  | becomes                                                 |
| -------- | ------------------------------------------------------- |
| `"98"`   | `'[{"number":98,"title":"<that test's ISSUE_TITLE>"}]'` |
| `""`     | `'[]'`                                                  |
| `"null"` | see below — this test's meaning changes                 |

The fixture title must match **that test's** `ISSUE_TITLE`, which is `setup()`'s default
for most and a distinct value at lines 302 and 327.

**New coverage:**

1. **Cross-workflow selection.** List holds both the Rust and Python issues;
   `ISSUE_TITLE` is the Rust one. Assert the **positive** — `gh issue comment 98` appears
   in the call log — not merely that the Python number is absent. An absence-only
   assertion passes whenever the filter returns empty for any reason, including a filter
   that never ran.
2. **A green Rust run does not touch the Python issue.** `RESULT=success`, list holds
   only the Python issue, `ISSUE_TITLE` is the Rust one: exit 0, no comment, no close.
   This one is unavoidably an absence assertion; it is the `command -v jq` guard in §4(b)
   that stops it passing under a missing jq, and test 1 that stops it passing under a
   wrong filter. Neither alone is sufficient and both are required.
3. **Each propagation site fails alone.** One test per guarded call —
   `MOCK_GH_EXIT_ISSUE_LIST`, `MOCK_GH_EXIT_ISSUE_COMMENT`, `MOCK_GH_EXIT_ISSUE_CLOSE`,
   `MOCK_GH_EXIT_ISSUE_CREATE` — asserting `main` returns non-zero and the call
   downstream of the failure is absent from the log. The two `issue comment` sites share
   a subcommand key and are discriminated by `RESULT`, which selects mutually exclusive
   branches.

   **This group is the positive control for the whole per-arm mechanism.** A mock that
   ignored the new variables would let every `gh` call exit 0, `main` would return 0, and
   every test here goes **red**. That is correct detection.

4. **`gh label create` failing does not fail the run.** `MOCK_GH_EXIT_LABEL_CREATE=4`,
   `RESULT=failure`, empty list: `main` still succeeds and `issue create` still runs.

   **This is not a control and must not be described as one.** Production swallows
   label-create failure with `|| true` by design, so a working mock and an ignoring mock
   produce identical observables — it is invariant under exactly the mutation it would
   need to detect. It is retained as a regression test for the `|| true`, and it asserts
   `gh-key MOCK_GH_EXIT_LABEL_CREATE=4` in the call log, which is the only way this
   particular derived key is ever shown to resolve at all.

5. **The emitted lookup carries no `--search` and no `in:title`.**
6. **Both mutation workflows declare the concurrency block** with
   `cancel-in-progress: false`, in the style of the existing workflow/script cross-check
   at `mutation_notify.bats:412`.
7. **`release-sbom-monitor.yml` carries no `--search`/`in:title`**, and a real-jq test of
   the `startswith` filter against fixture titles — including a prefix-collision pair
   (`pi-rs` vs `pi-rs2`) that the trailing space is there to separate.
8. **The lookup works with `ISSUE_TITLE` set but not exported.** Directly pins §1's
   `export` line; without it the suite cannot distinguish the two cases.

**The `null` test inverts, and this is intended.** `mutation_notify.bats:370` asserts
_"`MOCK_GH_ISSUE_LIST=null` is read as an existing issue number, not as absent"_ — an
artifact of the mock never running jq, as the script's own comment at lines 95–98 says
(_"cannot exercise the `// empty` fallback itself"_). Once real jq runs,
`[{"number":null,…}] | .[0].number // empty` correctly yields empty. Confirmed under jq
1.8.2 during review. The test is rewritten to assert real behaviour and the stale
comment is removed with it.

## Verification

| #   | command                                                                                                | expects                                   |
| --- | ------------------------------------------------------------------------------------------------------ | ----------------------------------------- |
| V1  | `make test-hooks`                                                                                      | green, including `ci_gate.bats` unchanged |
| V2  | `bats tests/scripts/mutation_notify.bats`                                                              | green; case count risen from 29           |
| V3  | strip `\|\| return 1` from the issue lookup, run V2                                                    | **red**                                   |
| V4  | strip `\|\| return 1` from `gh issue close`, run V2                                                    | **red**                                   |
| V5  | strip `\|\| return 1` from `gh issue comment`, run V2                                                  | **red**                                   |
| V6  | strip `\|\| return 1` from `gh issue create`, run V2                                                   | **red**                                   |
| V7  | remove `export ISSUE_TITLE`, run V2                                                                    | **red**                                   |
| V8  | `! grep -q 'in:title\|--search' scripts/mutation-notify.sh .github/workflows/release-sbom-monitor.yml` | exit 0                                    |
| V9  | `grep -A2 '^concurrency:' .github/workflows/mutation-testing*.yml`                                     | both files, `cancel-in-progress: false`   |
| V10 | the `--jq` filter under CI's gh, both titles present                                                   | the matching number only                  |

**V3–V7 are the point of the test half and must be run by mutation, not by reading.**
V3 and V4 are the two `bug-scan` measured as surviving; V5 and V6 cover the other two
guarded sites the new tests claim to pin, and an earlier draft verified those by reading
while forbidding exactly that two lines later. V7 pins the export line.

**V8 is written `! grep -q`, deliberately.** An earlier draft used
`grep -c ... | expect 0`, which is wrong twice: `grep -c` counts _lines_, so the pre-fix
baseline is 1 rather than 2 (both patterns sit on one line), and it exits **1** when the
count is zero — so the command signalling success returns non-zero and inverts under
`set -e` or a make target.

**V10 is a version boundary, not an open feasibility question.** An earlier draft called
gojq compatibility a pre-merge blocker. Settled three times independently during review,
against gh 2.98.0's embedded gojq on this machine:

```
$ ISSUE_TITLE='mutation-testing: monthly run failed' gh issue list --repo brujack/math \
    --state open --label mutation-failure --limit 100 --json number,title \
    --jq '[.[] | select(.title == env.ISSUE_TITLE)] | .[0].number // empty'
98
```

gojq honours `env`. The residual risk is narrower: **CI's `gh` version is not this
machine's.** V10 is therefore a check to run once on a CI runner, not a design question.

## Out of scope

- **Per-workflow labels** (`mutation-failure-rust` / `-python`). Would delete the title
  filter, the jq program, the `export` dependency and the gojq question outright. Cost
  is one manual relabel of #98 (**not two** — #99 is already closed; an earlier draft
  overstated this) plus a `LABEL` env var in both workflows. Rejected at Step 9 with the
  corrected cost in hand: the tokenization finding shows the title discriminator is doing
  live work today, so the filter repairs an existing defect rather than merely enabling
  a label change.
- **Closing #98.** It is open as an artifact of this bug (see the run correlation), so
  closing it is a judgement about whether mutation runs are still failing — a separate
  question, and closing it would silently change the branch the next notify run takes.
- **Extracting the sbom-monitor loop to a script.** Named and rejected in §2, with the
  condition under which it should be revisited.
- **The `:?` guard message row** from the backlog (`${RESULT:?must be set by the notify
job env block}`). Same file, but a message change with no behavioural test; bundling it
  widens the diff V3–V7's mutation runs must cover. Stays in the backlog.
- **A shared concurrency group across both workflows.** Rejected in §3.

## Risks

- **The mock is shared.** `ci_gate.bats` is the only other consumer and its
  `MOCK_GH_EXIT` usage is preserved by the fallback, so V1 is the check. A red V1 means
  the fallback is wrong, not the caller.
- **Ten test conversions are mechanical and individually silent.** A fixture whose title
  does not match its test's `ISSUE_TITLE` yields an empty lookup, routing the test down
  the no-existing-issue branch — and for tests that already expect that branch, it passes
  for the wrong reason. Each converted fixture's title must be read against that test's
  `ISSUE_TITLE`, not `setup()`'s default.
- **Serialisation can silently discard a run, and the notify mechanism is blind to it.**
  GitHub keeps at most one _pending_ run per group; a third arrival cancels the queued
  one. A pending-cancelled run files no spurious issue — correct — but it is also
  **never reported**, because the notify job attributes runs that die, not runs that
  never start. With `timeout-minutes: 360`, a dispatch landing during a monthly cron may
  also wait up to six hours, and the natural moment to dispatch is right after a red run.
  The run record shows 3-deep sequencing on this workflow is not hypothetical. Accepted:
  a skipped cron is recoverable by dispatch, and the alternative (`cancel-in-progress:
true`) manufactures false failure reports.
- **`--limit 100` masks rather than fixes an unbounded list.** The same silent-absence
  failure arriving through pagination. Steady state is one open `mutation-failure` issue,
  ceiling two — but the sbom-monitor label is one issue per CVE per binary across 11
  binaries, where 100 is a real ceiling rather than a nominal one. Revisit if that label
  ever approaches it.
- **`.[0]` picks the newest matching open issue** (gh lists descending), so two
  simultaneously-open duplicates leave the older permanently unclosed. Pre-existing and
  bounded by this fix rather than introduced by it.
- **CI's gh version**, per V10.

## Related

- Backlog rows absorbed: duplicate issue; missing `concurrency`; `tests/mocks/gh`
  isolation — all three removed from `docs/superpowers/README.md` by this spec.
- `docs/superpowers/specs/2026-08-31-mutation-notify-attribution-design.md` — created
  `scripts/mutation-notify.sh` and raised the duplicate-issue finding in its own
  Multi-Lens Review (Ergonomics finding 1) while deliberately keeping it out of scope.
- ADR-0024 — the OOM fix whose hand-testing produced the eight dispatch runs above.

## Multi-Lens Review

Reviewed at commit: `0ba8e6f8` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: The race hypothesis is refuted by the run record, and the spec had the
discriminating artifact one command away — all eight runs are strictly sequential, all
`workflow_dispatch`, with every end-to-next-start gap positive. The concurrency block
fixes nothing observed and claimed measured backing it did not have. The same command
upgrades the problem statement in the spec's favour: #98 was missed three consecutive
times, twice on the green path where the failure is silent, making #98's open state an
artifact of the bug rather than the independent question Out-of-scope called it. V7
(gojq) resolved in the spec's favour against live gh 2.98.0. A second call site with the
identical defect exists at `release-sbom-monitor.yml:95`, inside a per-finding loop.
Verdict counting clean, but V3/V4 covered only two of the four sites group 3 claims to
pin, verifying the other two by reading — which the spec forbids two lines later. The
per-workflow-label rejection overstated its cost roughly 2x (#99 is already closed).

Assumption: That GitHub's search index, not the query itself, is what failed — the spec
asserts "the lookup is not broken" on one successful hand-run. Settled by testing whether
`in:title` matches exactly or on tokens.

Disposition: **Addressed.** The assumption was tested and the query is **not** an exact
match — AND-over-tokens with hyphen splitting, measured. That produced a finding neither
the lens nor the spec had: the cross-workflow hazard is already live in shipped code
rather than introduced by the fix. Race refutation, problem-statement upgrade, V10
downgrade, V5/V6 added, corrected label cost all incorporated. The sbom call site was
folded into scope by operator decision at Step 9 rather than backlogged.

### Ergonomics

Finding: (F1) The designated positive control is the one test that cannot detect the
mechanism and its rationale is inverted — group 3 is the control; group 4 is invariant
under the mutation it claims to catch, because `|| true` makes label-create failure
unobservable by construction. (F2) The derived variable name is undocumented, and
`CLAUDE.md:477` is already wrong about the existing derived family — `MOCK_GH_PR_CHECKS_N`
appears nowhere in the code. (F3) V7 fails the reads-it test: no file, field or record
holds the gojq answer afterwards. (F4) V5 signals success by exiting non-zero and counts
lines, not occurrences. (F5) Pending-run eviction and up-to-six-hour operator wait are
unaddressed.

Assumption: That gh's embedded gojq resolves `env.ISSUE_TITLE` as jq 1.8.2 does — could
not be settled from that lens's environment (no gojq installed).

Disposition: **Addressed.** F1 corrected — group 4's claim removed, group 3 named as the
control, and the mock now logs its resolved key so the derivation is assertable and F1's
underlying gap (that `MOCK_GH_EXIT_LABEL_CREATE` was never shown to resolve) is closed.
F2: `CLAUDE.md:477` correction and a mock header comment added as §4(c). F3: V10 restated
as a CI-version check with the measured basis recorded in the spec. F4: V8 rewritten as
`! grep -q`. F5: added to Risks. The assumption was settled independently by two other
sources against live gh 2.98.0.

### Risk

Finding: (1) Same inverted positive control as Ergonomics F1, found independently. (2)
The design converts `ISSUE_TITLE` from an argument into an environment dependency and
nothing enforces the export — a set-but-unexported variable yields empty, files a
duplicate, and `: "${ISSUE_TITLE:?}"` passes on it; the suite exports in `setup()` so no
test can distinguish the cases. (3) Serialisation trades a visible failure for an
invisible one: a pending-cancelled run is silently discarded and the notify mechanism is
structurally blind to runs that never start. (4) Half the new assertions pass if the
measurement produces nothing — absence assertions need pairing with positives. Verified
V3/V4 reproduce, the bash snippets behave as claimed, key derivation collides with
nothing in `ci_gate.bats`, and `${{ github.workflow }}` resolves distinctly.

Assumption: That `ISSUE_TITLE` remains in the process environment at every future call
path into `main()` — undefended and unfalsifiable by the current suite.

Disposition: **Addressed.** (2) is the most valuable finding of the round; reproduced
independently before acting on it, and fixed with `export ISSUE_TITLE` in `main()` plus
test 8, which is exactly the falsification the assumption line asked for. (1) as above.
(3) added to Risks with the accept-reason stated. (4) test 1 now asserts the positive,
and test 2's two independent guards are named.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
