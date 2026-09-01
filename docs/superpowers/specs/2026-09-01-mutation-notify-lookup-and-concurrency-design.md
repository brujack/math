# Mutation-notify: index-independent lookup, run serialisation, per-call mock

Date: 2026-09-01
Status: Spec

Bundles three backlog rows that share one file, one failure, and one test harness:
the duplicate-issue lookup, the missing `concurrency` block on both mutation
workflows, and `tests/mocks/gh`'s inability to fail a single call. They are specified
together because the third is a prerequisite for testing the first, and the second is
the suspected mechanism behind the first.

## Problem

### The observed failure

Measured 2026-09-01 by this spec, against the live tracker rather than taken from the
backlog row that prompted it:

```
$ gh issue list --repo brujack/math --state all --label mutation-failure \
    --limit 20 --json number,title,state,createdAt \
    --jq '.[] | "\(.number) \(.state) \(.createdAt) \(.title)"'
99 CLOSED 2026-08-02T02:13:37Z mutation-testing: monthly run failed
98 OPEN   2026-08-02T01:57:03Z mutation-testing: monthly run failed
96 CLOSED 2026-08-02T01:11:51Z mutation-testing: monthly run failed
92 CLOSED 2026-08-01T23:31:34Z mutation-testing: monthly run failed
```

The backlog row's specific claim holds exactly: #99 was created at 02:13:37Z while
#98 — identical title, identical label — had been open since 01:57:03Z, and #98 is
open still. The notify job's whole purpose is to comment on an existing tracking issue
rather than file a second one, and it filed a second one sixteen minutes later.

**The measurement returns two things the row does not record, and both change how the
problem should be read.**

**Four issues carry that identical title inside three hours**, not one duplicate pair.
That is not four duplications — a file/close/file cycle is the _designed_ behaviour, so
#92→#96 (1h40m apart) and #96→#98 (45m) are consistent with runs alternating red and
green. Only #98/#99 overlap, because #98 was never closed. The wider window matters
anyway: it establishes that 2026-08-01/02 saw at least four notify runs in three hours
against a monthly cron, which is direct evidence for the row's overlapping-dispatch
hypothesis rather than an assumption about it.

**#99 is CLOSED and #98 is OPEN**, so the tracker's current state is a single open
`mutation-failure` issue. The row says "#98 ... still is [open]", which is true, and
implies nothing about #99, which is not.

The lookup is not broken. Run by hand on 2026-08-31 — reported in the backlog row, not
re-run here — the same query returned `98`. What differs between the two moments is the
state of GitHub's issue **search index**, which `--search 'in:title "..."'` depends on
and `--label` filtering does not.

Two causes are consistent with the evidence and the fix addresses both, which is why
no attempt is made here to decide between them:

- **Index lag.** The index had not yet observed #98 when the second run queried it.
- **A race.** Overlapping dispatch runs, two of which reached the lookup before either
  reached the create. The four-issues-in-three-hours figure above is what makes this
  more than speculation.

### The cross-workflow hazard is latent, not observed

The same query returns **no** `mutation-testing-python: monthly run failed` issue —
that workflow has never filed one. So the title-filter half of this design guards a
failure mode that has not yet happened: it becomes reachable the first time the Python
workflow files an issue, at which point a green Rust run would close it.

Stated plainly because it changes the justification. The `--search` removal is fixing a
**measured** defect; the client-side title filter is preventing a **structural** one
that the label-only fix would otherwise introduce. Neither is speculative, but only the
first has an incident behind it, and a reader should not infer that both do.

### Why the search index is the wrong dependency

`gh issue list --label` and `--state` are served from the issues API directly.
`--search` is served from the search index, which is eventually consistent and carries
no freshness guarantee. A lookup whose job is _"has this already been filed"_ cannot
be built on a source that is allowed to not know yet — and its failure mode is silent,
because an empty result is indistinguishable from a genuine absence.

### Why serialisation matters independently

Neither mutation workflow declares `concurrency`:

```
$ grep -n concurrency .github/workflows/mutation-testing*.yml
(no output)
```

So two runs of the same workflow can overlap — a `workflow_dispatch` landing on top of
the monthly cron is the ordinary case. Under overlap, two notify jobs can both observe
"no existing issue" and both create one, regardless of which source the lookup reads.
Fixing the lookup narrows the window; serialising the runs removes the overlap. They
are different causes and each is worth its own fix.

### Why the test suite cannot currently see any of this

`tests/mocks/gh:4` evaluates `MOCK_GH_EXIT` before any subcommand dispatch, so a test
that makes one `gh` call fail makes every `gh` call fail. `scripts/mutation-notify.sh`
has six `gh` call sites, five of which propagate with `|| return 1` and one
(`gh label create`, line 117) which is deliberately `|| true`:

| line | call                            | guard                    |
| ---- | ------------------------------- | ------------------------ |
| 99   | `gh issue list`                 | `\|\| return 1`          |
| 104  | `gh issue comment` (green path) | `\|\| return 1`          |
| 105  | `gh issue close`                | `\|\| return 1`          |
| 115  | `gh issue comment` (red path)   | `\|\| return 1`          |
| 117  | `gh label create`               | `\|\| true` — deliberate |
| 119  | `gh issue create`               | `\|\| return 1`          |

Measured 2026-09-01 during `bug-scan`: stripping `|| return 1` from the issue lookup,
and separately from `gh issue close`, each leaves the 29-case suite fully green. Both
mutations assert as landed. Three of the five propagation sites are pinned only
collectively — a single test that fails everything at once.

Production is correct today. The exposure is a future edit dropping a guard with no
test going red.

## Correction to the backlog rows

**The duplicate-issue row names two call sites that no longer exist.** It cites
`mutation-testing.yml:116` and `mutation-testing-python.yml:119`. The 2026-08-31
notify-attribution work replaced both inline blocks with the shared
`scripts/mutation-notify.sh`:

```
$ grep -n 'issue list' .github/workflows/mutation-testing.yml \
                        .github/workflows/mutation-testing-python.yml
(no output)
```

There is one call site: `scripts/mutation-notify.sh:99`. The fix is correspondingly
smaller than the row implies, and the row's line numbers must not be carried into the
plan.

**Both workflows share one label and are distinguished only by issue title.**

| workflow                      | `ISSUE_TITLE`                                 | label              |
| ----------------------------- | --------------------------------------------- | ------------------ |
| `mutation-testing.yml`        | `mutation-testing: monthly run failed`        | `mutation-failure` |
| `mutation-testing-python.yml` | `mutation-testing-python: monthly run failed` | `mutation-failure` |

This is load-bearing and is not stated in the backlog row. The row's proposed fix is
_"key on `--label mutation-failure --state open` and filter titles client-side"_ — and
the second half is not a refinement of the first. Drop the title filter and a green
Rust run closes the Python tracking issue, because the label alone cannot tell the two
apart.

## Design

### 1. Lookup — `scripts/mutation-notify.sh`

Replace the search-backed query with a label-backed query plus a client-side exact
title match:

```bash
_existing=$(gh issue list --repo "${REPO}" --state open --label mutation-failure \
    --limit 100 --json number,title \
    --jq '[.[] | select(.title == env.ISSUE_TITLE)] | .[0].number // empty') || return 1
```

Three deliberate choices:

- **`--search` removed.** That was the index dependency and the whole defect.
- **`env.ISSUE_TITLE` rather than shell interpolation of the title into the jq
  program.** The titles contain a colon and spaces, and interpolating a shell variable
  into a jq program is a quoting hazard with no upside. `ISSUE_TITLE` is already
  exported — by the notify step's `env:` block in both workflows, and by
  `mutation_notify.bats:20` in `setup()`.
- **`--limit 100`.** `gh issue list` defaults to 30. The bug being fixed is a lookup
  missing an issue that exists; a default page size is a second way to reproduce it
  under a different cause, and the label filter bounds the real result set to roughly
  two.

The rest of `main()` is unchanged — the `-n "${_existing}"` branch, the comment/close
green path, and the create red path all consume the same value as before.

### 2. Serialisation — both workflow files

Workflow-level, so it covers the `notify` job as well as `mutants`:

```yaml
concurrency:
  group: ${{ github.workflow }}
  cancel-in-progress: false
```

- **`cancel-in-progress: false`** because cancelling a run mid-flight would manufacture
  the terminated-job case the notify job exists to report on. The notify job would then
  file an issue describing a cancellation the concurrency rule itself caused.
- **Group key is bare `${{ github.workflow }}`, with no `${{ github.ref }}`.** The
  common idiom appends the ref, which partitions by branch — and a
  `workflow_dispatch` from a feature branch racing the cron on master is precisely the
  hazard. Both runs write the same tracking issue on the same repo, so they must share
  a lane whatever branch they were dispatched from.
- **The two workflows keep separate groups.** With the title filter in place they
  target different issues, so a shared group buys nothing for the duplicate — and the
  Rust run is multi-hour, so it would delay the 06:00 Python cron behind it for no
  benefit. The crons are already 2h apart (`0 4 1 * *` and `0 6 1 * *`).

A run cancelled while _pending_ never starts a job, so `if: always()` never evaluates
and no spurious issue is filed. Only in-progress cancellation could manufacture a false
report, and `cancel-in-progress: false` is what forbids it.

### 3. Per-call failure control — `tests/mocks/gh`

Two independent changes to a mock shared with `ci_gate.bats`.

**(a) Exit code keyed on the subcommand, falling back to the existing variable.**

```bash
_key="MOCK_GH_EXIT_$(printf '%s_%s' "${1:-}" "${2:-}" \
    | tr 'a-z-' 'A-Z_' | tr -cd '[:alnum:]_')"
_rc="${!_key:-${MOCK_GH_EXIT:-0}}"
if [[ "${_rc}" -ne 0 ]]; then
    exit "${_rc}"
fi
```

The name is _derived_ from the subcommand rather than looked up in a hand-maintained
list, so a call site added later is pinnable without editing the mock. A literal
`case` naming each variable is the shape this fleet's standards warn about: the list
silently stops covering the script the moment someone adds a sixth call.

`MOCK_GH_EXIT` survives as the all-calls-fail case. `ci_gate.bats:65` uses it and needs
no edit, so **that suite staying green is the regression check** for this change.

`ci_gate.bats` calls `gh api repos/<owner>/<repo>/...`, which derives a long key
containing the flattened path. It is never set, so it falls back — harmless, and worth
stating so a reader is not surprised by the generated name.

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

Scoped to `issue list` specifically, so the `check-runs` arm and every `ci_gate.bats`
path are untouched, and so the other `issue` subcommands do not echo a JSON array on
stdout that nothing reads.

The `command -v jq` guard is not decoration. Without it an absent jq yields empty
stdout, the script reads that as "no existing issue", and the suite fails somewhere
downstream with a message about issue creation — a guard blaming the wrong subsystem
for a missing tool. Exiting 127 with a named cause is the point.

### 4. Tests — `tests/scripts/mutation_notify.bats`

`MOCK_GH_ISSUE_LIST` becomes a JSON array. Ten tests currently set it to `"98"`, `""`,
or `"null"` (lines 247, 272, 284, 297, 326, 348, 357, 372, 384, 392) and each must be
converted:

| current  | becomes                                                |
| -------- | ------------------------------------------------------ |
| `"98"`   | `'[{"number":98,"title":"<the test's ISSUE_TITLE>"}]'` |
| `""`     | `'[]'`                                                 |
| `"null"` | see below — this test's meaning changes                |

The title in each fixture must match that test's `ISSUE_TITLE`, which is
`setup()`'s default for most and a distinct value at lines 302 and 327.

**New coverage, none of which was previously expressible:**

1. **Cross-workflow selection.** List holds both the Rust and Python issues;
   `ISSUE_TITLE` is the Rust one; the lookup yields the Rust number and never the
   Python one.
2. **A green Rust run does not touch the Python issue.** `RESULT=success`, list holds
   only the Python issue, `ISSUE_TITLE` is the Rust one: exit 0, no `issue comment`,
   no `issue close` in the call log.
3. **Each propagation site fails alone.** One test per guarded call —
   `MOCK_GH_EXIT_ISSUE_LIST`, `MOCK_GH_EXIT_ISSUE_COMMENT`,
   `MOCK_GH_EXIT_ISSUE_CLOSE`, `MOCK_GH_EXIT_ISSUE_CREATE` — asserting `main` returns
   non-zero and that the call downstream of the failure never appears in the log. The
   two `issue comment` sites share a subcommand key and are discriminated by `RESULT`,
   which selects mutually exclusive branches.
4. **`gh label create` failing does not fail the run.** `MOCK_GH_EXIT_LABEL_CREATE=4`
   with `RESULT=failure` and an empty list: `main` still succeeds and `issue create`
   still runs. This is the **positive control** for the per-arm mechanism — without it,
   a mock that ignored the new variables entirely would pass every test in group 3 for
   the wrong reason, since those assert failure and an ignored variable yields success.
   Group 3 and this test disagree under a broken mock, which is what makes the pair
   discriminating.
5. **The emitted lookup carries no `--search` and no `in:title`.** Pins the regression
   directly rather than inferring it from behaviour.
6. **Both workflows declare the concurrency block** with `cancel-in-progress: false`,
   in the style of the existing workflow/script cross-check at
   `mutation_notify.bats:412`.

**The `null` test inverts, and this is intended.** `mutation_notify.bats:370` currently
asserts _"`MOCK_GH_ISSUE_LIST=null` is read as an existing issue number, not as
absent"_. That behaviour is an artifact of the mock never running jq — the script's
comment at lines 95–98 says so explicitly, noting the suite "cannot exercise the
`// empty` fallback itself". Once real jq runs, `[{"number":null,...}] | .[0].number
// empty` correctly yields empty and a null number reads as absent. The test is
rewritten to assert the real behaviour, and the stale comment at lines 95–98 is
removed with it.

## Verification

Commands that prove each part, with the expected observable:

| #   | command                                                            | expects                                              |
| --- | ------------------------------------------------------------------ | ---------------------------------------------------- |
| V1  | `make test-hooks`                                                  | all suites green, including `ci_gate.bats` unchanged |
| V2  | `bats tests/scripts/mutation_notify.bats`                          | green; case count risen from 29                      |
| V3  | strip `\|\| return 1` from `mutation-notify.sh:99`, run V2         | **red** — the mutation that was green before         |
| V4  | strip `\|\| return 1` from `gh issue close`, run V2                | **red** — the second measured mutation               |
| V5  | `grep -c 'in:title\|--search' scripts/mutation-notify.sh`          | `0`                                                  |
| V6  | `grep -A2 '^concurrency:' .github/workflows/mutation-testing*.yml` | both files, `cancel-in-progress: false`              |
| V7  | the `--jq` filter run under **gojq**, fixture holding both titles  | the matching number only                             |

**V3 and V4 are the point of the whole test half and must actually be run.** They are
the two mutations `bug-scan` measured as surviving; a suite that does not go red under
them has not fixed the thing this spec claims to fix. Run them by mutation, not by
reading the tests.

**V7 is an open item, not an assumption.** `gh --jq` uses embedded **gojq**, not jq.
The `env.ISSUE_TITLE` form was verified here against real jq 1.8.2:

```
$ ISSUE_TITLE='mutation-testing: monthly run failed' jq -n --argjson d '[…]' \
    '$d | [.[] | select(.title == env.ISSUE_TITLE)] | .[0].number // empty'
98
```

and the mock will also use real jq — so **every test can pass while production is
broken**, if gojq diverges. gojq documents `env`, so agreement is expected, but
expected is not measured. Verify against gojq or a live `gh` before merge. If it
diverges, the fallback is `--arg`-free interpolation with the title escaped, or
dropping `--jq` in favour of the script piping through external jq (rejected in design
for adding a production dependency, but available).

## Out of scope

Named so the omissions read as decisions:

- **Per-workflow labels** (`mutation-failure-rust` / `-python`). Would make the
  server-side query exact and remove the title dependency, at the cost of orphaning
  #98/#99 under the old label and adding a `LABEL` env var to the shared script.
  Rejected: the client-side filter achieves the same discrimination with no taxonomy
  change.
- **Housekeeping on #98.** #99 is already CLOSED (measured above), so there is nothing
  to merge — the tracker holds one open `mutation-failure` issue, #98, dating from
  2026-08-02. Whether it still reflects a real failure is a question about the
  mutation runs, not about this fix, and closing it would silently change the branch
  the next notify run takes.
- **The `:?` guard message row** from the backlog (`${RESULT:?must be set by the notify
job env block}`). Same file, and folding it in is tempting — but it is a message
  change with no behavioural test, and bundling it means V3/V4 mutation runs cover a
  diff larger than the defect. Stays in the backlog.
- **A shared concurrency group across both workflows.** Rejected in design above.

## Risks

- **The mock is shared.** `ci_gate.bats` is the only other consumer and its
  `MOCK_GH_EXIT` usage is preserved by the fallback, so V1 is the check. If V1 goes
  red, the fallback is wrong, not the caller.
- **Ten test conversions are mechanical and individually silent.** A fixture whose
  title does not match its test's `ISSUE_TITLE` yields an empty lookup, which routes
  the test down the no-existing-issue branch — and for the tests that already expect
  that branch, it passes for the wrong reason. Each converted fixture's title must be
  read against that test's `ISSUE_TITLE`, not against `setup()`'s default.
- **gojq divergence**, covered by V7 above.
- **`--limit 100` masks rather than fixes an unbounded list.** If the label ever
  accumulates more than 100 open issues the lookup silently misses again — the same
  silent-absence failure being fixed, arriving through pagination instead of the search
  index. Measured steady state is **one** open `mutation-failure` issue (#98), with a
  ceiling of two once the Python workflow files its first, so 100 is two orders of
  margin. Stated so it is not rediscovered as a novel defect.

## Related

- Backlog rows: duplicate issue; missing `concurrency`; `tests/mocks/gh` isolation —
  all three in `docs/superpowers/README.md`, removed by this spec.
- `docs/superpowers/specs/2026-08-31-mutation-notify-attribution-design.md` — created
  `scripts/mutation-notify.sh` and raised the duplicate-issue finding in its
  Multi-Lens Review (Ergonomics finding 1) while deliberately keeping it out of scope.
