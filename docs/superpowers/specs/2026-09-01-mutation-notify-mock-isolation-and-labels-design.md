# Mutation-notify: per-call mock isolation and per-workflow issue labels

Date: 2026-09-01
Status: Spec

Two changes, each backed by a defect that was actually measured:

1. **`tests/mocks/gh` cannot fail one call at a time**, so three of five error-propagation
   guards in `scripts/mutation-notify.sh` are pinned only collectively. Two guard-strip
   mutations survive the suite fully green.
2. **The issue lookup discriminates two workflows by title, and title matching is
   AND-over-tokens**, so the Rust workflow's query matches a Python issue. A green Rust
   run can close the Python tracking issue.

> **Scope history — read this before citing the spec.** Earlier drafts bundled two further
> components, an index-independent lookup and a `concurrency` block, on the strength of a
> duplicate-issue incident. **That incident did not happen.** Multi-Lens Review round 2
> refuted it against the issue timelines; both components are now backlogged as prophylaxis
> against an unwitnessed hazard. The refutation is recorded below rather than deleted,
> because the way the false premise survived two drafts and one full review round is the
> most reusable thing this spec produced.

## The premise that was refuted

The originating backlog row read: _"#99 was created 2026-08-02T02:13:37Z while #98 —
identical title and label — was open since 01:57:03Z and still is."_ An earlier draft of
this spec strengthened that into three consecutive lookup misses, correlating issue states
against the workflow run record.

Both are false. The issue timeline settles it:

```
$ gh api repos/brujack/math/issues/98/timeline --paginate \
    --jq '.[] | select(.event=="closed" or .event=="reopened" or .event=="commented")
               | "\(.created_at) \(.event) by \(.actor.login // .user.login)"'
2026-08-02T02:03:39Z commented by github-actions[bot]
2026-08-02T02:03:40Z closed    by github-actions[bot]
2026-08-02T02:14:30Z commented by brujack
2026-08-02T02:14:31Z reopened  by brujack
2026-09-01T04:41:12Z commented by github-actions[bot]
```

**#98 was closed by the bot at 02:03:40 and reopened by the operator at 02:14:31 — 54
seconds _after_ #99 was created at 02:13:37.** So when #99 was filed, #98 was closed, and
filing it was correct. #98 reads `OPEN` today because a human reopened it, not because a
lookup missed it.

Across all four issues under the label, every one was filed when nothing was open; two were
closed by the bot, two by the operator. **Six correct notify decisions, zero duplicates,
zero misses.** The 2026-09-01 scheduled run commented on #98 correctly on the current
`--search` code, hours before this spec was first written.

**How it survived.** The same error was made twice, in two different drafts, and neither
time was the discriminating artifact consulted:

| draft | field read                        | history inferred                   | what settles it                                                |
| ----- | --------------------------------- | ---------------------------------- | -------------------------------------------------------------- |
| 1     | four issues in three hours        | overlapping dispatch runs (a race) | `gh run list` — no overlap in 12 runs, ever                    |
| 2     | `state: OPEN` today + `createdAt` | never closed, so three misses      | `gh api …/timeline` — closed at 02:03:40, reopened at 02:14:31 |

Draft 2 was itself the correction for draft 1, and reached for a run record rather than an
event record — a state field whose value is compatible with two histories, read as though it
carried the history. `behavior.md` calls this _"the artifact carries the field, and its value
is compatible with both causes"_; the tell is that `state` answers **now** and the claim was
about **then**. `gh issue list --json state` was already being run; adding `,closedAt` or one
`timeline` call would have refuted both drafts.

**Nothing below rests on that premise.** Both surviving components were measured
independently and neither involves the search index.

## Defect 1 — the mock cannot fail one call at a time

`tests/mocks/gh:4` evaluates `MOCK_GH_EXIT` before any subcommand dispatch, so a test that
makes one `gh` call fail makes every `gh` call fail. `scripts/mutation-notify.sh` has six
`gh` call sites, five propagating with `|| return 1` and one deliberately `|| true`:

| line | call                            | guard                    |
| ---- | ------------------------------- | ------------------------ |
| 99   | `gh issue list`                 | `\|\| return 1`          |
| 104  | `gh issue comment` (green path) | `\|\| return 1`          |
| 105  | `gh issue close`                | `\|\| return 1`          |
| 115  | `gh issue comment` (red path)   | `\|\| return 1`          |
| 117  | `gh label create`               | `\|\| true` — deliberate |
| 119  | `gh issue create`               | `\|\| return 1`          |

Measured 2026-09-01 by `bug-scan` and independently reproduced by two review lenses in
scratch trees: stripping `|| return 1` from the issue lookup, and separately from
`gh issue close`, each leaves the 29-case suite **fully green**. Both mutations assert as
landed.

Production is correct today. The exposure is a future edit dropping a guard with no test
going red.

## Defect 2 — title matching is AND-over-tokens, so Rust matches Python

Both workflows share the label `mutation-failure` and are distinguished only by
`ISSUE_TITLE`. `in:title "..."` is **not** a phrase match. Measured 2026-09-01:

| search phrase                                         | returns |
| ----------------------------------------------------- | ------- |
| `mutation-testing: monthly run failed`                | 98      |
| `mutation-testing monthly run failed` (colon dropped) | 98      |
| `monthly run failed` (strict substring)               | 98      |
| `mutation-testing-python: monthly run failed`         | —       |
| `completely unrelated words here`                     | —       |

and hyphenated compounds split:

```
in:title "mutation"         -> 98,99,96,92
in:title "testing"          -> 98,99,96,92
in:title "mutation-testing" -> 98,99,96,92
```

The Rust query's tokens are `{mutation, testing, monthly, run, failed}`. A Python issue
titled `mutation-testing-python: monthly run failed` carries a strict superset, so the Rust
lookup matches it — while the reverse fails, because the extra `python` token is absent from
the Rust title.

**Consequence: the first time the Python workflow files an issue, a green Rust run can
comment _"Green as of …. Closing."_ on it and close it.**

Latent, not observed: the Python workflow has filed no issue in any state, and all four of
its runs to date succeeded. That is why it is worth fixing cheaply rather than elaborately.

## Design

### 1. Per-workflow labels — `mutation-notify.sh` and both workflows

Give each workflow its own label and delete the title comparison entirely.

```yaml
# mutation-testing.yml notify step env:
ISSUE_LABEL: mutation-failure-rust
# mutation-testing-python.yml notify step env:
ISSUE_LABEL: mutation-failure-python
```

```bash
main() {
    : "${RESULT:?}"
    : "${REPO:?}"
    : "${ISSUE_TITLE:?}"
    : "${ISSUE_LABEL:?}"

    local _existing
    _existing=$(gh issue list --repo "${REPO}" --state open --label "${ISSUE_LABEL}" \
        --json number --jq '.[0].number // empty') || return 1
    ...
    gh label create "${ISSUE_LABEL}" --repo "${REPO}" --color B60205 \
        --description "Monthly mutation run failed" 2>/dev/null || true
    gh issue create --repo "${REPO}" --title "${ISSUE_TITLE}" --label "${ISSUE_LABEL}" ...
```

`ISSUE_TITLE` is still used for `--title` on create. It is no longer a _lookup_ input, which
is the whole point.

Why this rather than a client-side title filter, which earlier drafts specified:

- **It deletes the defect instead of compensating for it.** The label becomes the
  discriminator, so there is no token matching to get wrong.
- **It deletes the machinery where every review finding landed.** No jq filter program, no
  `env.ISSUE_TITLE` channel, no `export ISSUE_TITLE` (a set-but-unexported variable silently
  yields empty and files a duplicate — measured), no jq-aware mock arm, no `command -v jq`
  guard, no conversion of ten test fixtures to JSON, no gojq-vs-jq version question. Rounds 1
  and 2 each found a defect in that surface; removing it is worth more than defending it.
- **`--search` goes away as a side effect**, taking the search-index dependency with it. That
  is a _consequence_, not a motivation — no index failure has ever been witnessed here.

**One-time migration step, required and easy to forget.** #98 currently carries
`mutation-failure` and is open. After merge it must be relabelled or the next Rust run will
file a fresh issue beside it:

```bash
gh issue edit 98 --repo brujack/math \
  --add-label mutation-failure-rust --remove-label mutation-failure
```

The old label is left in place on the three closed issues as history.

No `--limit` is specified. Steady state under a unique label is one open issue, `.[0]` takes
the newest, and gh's default page of 30 is two orders of margin. An earlier draft added
`--limit 100`; under a shared label that was defensible, under a per-workflow label it is
arguing with a number that cannot be reached.

### 2. Per-call failure control — `tests/mocks/gh`

```bash
# Failure is selectable per subcommand via MOCK_GH_EXIT_<SUBCOMMAND>_<VERB>, derived
# from "$1_$2" upper-cased with non-alphanumerics stripped: `gh issue close` reads
# MOCK_GH_EXIT_ISSUE_CLOSE, `gh label create` reads MOCK_GH_EXIT_LABEL_CREATE.
# MOCK_GH_EXIT remains the all-calls-fail fallback (ci_gate.bats relies on it).
# An unset key falls through silently, so a mistyped name is a no-op rather than an
# error -- the propagation tests catch this, because an ignored key makes them go red.
_key="MOCK_GH_EXIT_$(printf '%s_%s' "${1:-}" "${2:-}" \
    | tr 'a-z-' 'A-Z_' | tr -cd '[:alnum:]_')"
_rc="${!_key:-${MOCK_GH_EXIT:-0}}"
if [[ "${_rc}" -ne 0 ]]; then
    exit "${_rc}"
fi
```

The name is derived rather than held in a hand-maintained list, so a call site added later is
pinnable without editing the mock.

`MOCK_GH_EXIT` survives as the all-calls-fail case; `ci_gate.bats:65` uses it and needs no
edit, so **that suite staying green is the regression check**. `ci_gate.bats` calls
`gh api repos/<owner>/<repo>/commits/<sha>/check-runs`, deriving a long SHA-dependent key
that is never set and collides with nothing it sets — verified by two lenses running both
suites against this change (39 cases, 0 failures).

**No `gh-key` log line.** An earlier draft added one so the derived key would be assertable.
It is not needed: the propagation tests below are the control, verified by mutation — with
the per-key lookup neutered, `_rc` resolves 0 for every call, `main` returns 0, and all four
go red. Adding the line would also put non-`gh ` text into `MOCK_CALLS_FILE`, which existing
assertions survive only because `assert_all_gh_calls_carry_repo` anchors on `^gh ` with a
trailing space and `gh-key` has a hyphen there. That is luck, and not worth relying on for a
line with no consumer.

### 3. Documentation

`CLAUDE.md:477` currently reads _"`gh` (sequential JSON responses via `MOCK_GH_PR_CHECKS_N`,
exits `$MOCK_GH_EXIT`)"_. Measured: `MOCK_GH_PR_CHECKS` appears **nowhere in the code** — the
live name is `MOCK_GH_CHECK_RUNS_N`. The one derived mock-variable family this repo already
has drifted out of its documentation and stayed wrong, which is the argument for fixing it in
the same change that adds a second family. Correct that line and add
`MOCK_GH_EXIT_<SUBCOMMAND>_<VERB>`. Required anyway by this repo's "Keeping CLAUDE.md Up To
Date" table.

`CLAUDE.md:381` also states *"a red run files or updates a labelled `mutation-failure`
issue"* — live documentation of the label name, which §1 changes. Update it in the same
commit.

### 4. Tests — `tests/scripts/mutation_notify.bats`

**Two existing assertions are in-diff.** `mutation_notify.bats:314` and `:333` assert the
whole `gh issue create` call as one literal string including `--label mutation-failure`;
both must move to the new label with §1 or they fail. They are the only existing cases
this change touches.

Existing fixtures are otherwise unchanged: `MOCK_GH_ISSUE_LIST` stays a bare number/empty string,
because the lookup keeps `--jq '.[0].number // empty'` and the mock keeps echoing it verbatim.
The pre-existing limitation documented at `mutation-notify.sh:95-98` — that the suite cannot
exercise `// empty` because the mock never runs jq — is untouched by this change and stays.

1. **Each propagation site fails alone.** One test per guarded call —
   `MOCK_GH_EXIT_ISSUE_LIST`, `MOCK_GH_EXIT_ISSUE_COMMENT`, `MOCK_GH_EXIT_ISSUE_CLOSE`,
   `MOCK_GH_EXIT_ISSUE_CREATE` — asserting `main` returns non-zero and that the call
   downstream of the failure is absent from the log. The two `issue comment` sites share a
   key and are discriminated by `RESULT`, which selects mutually exclusive branches.

   **This group is the positive control for the whole mechanism**, verified by mutation
   rather than by reading.

2. **`gh label create` failing does not fail the run.** `MOCK_GH_EXIT_LABEL_CREATE=4`,
   `RESULT=failure`, empty list: `main` still succeeds and `issue create` still runs. A
   regression test for the deliberate `|| true` — explicitly **not** a control, since
   `|| true` makes the failure unobservable by construction and a mock ignoring the new keys
   produces an identical observable.
3. **The lookup queries the workflow's own label.** `ISSUE_LABEL=mutation-failure-rust`;
   assert `gh issue list … --label mutation-failure-rust` appears in the call log — a
   positive assertion, so it cannot pass on an empty log.
4. **`main` fails visibly when `ISSUE_LABEL` is unset**, matching the existing guard tests
   for `RESULT`, `REPO` and `ISSUE_TITLE`.
5. **Each workflow declares a distinct `ISSUE_LABEL`,** and `mutation-notify.sh` hardcodes
   no label. Pair the absence half with a positive assertion from the same file — a bare
   `! grep -q PAT file` returns **0** when the file is missing (grep exits 2, `!` inverts
   it), so a rename or path typo would make the check pass while reading nothing. Measured.

## Verification

| #   | command                                                                         | expects                                   |
| --- | ------------------------------------------------------------------------------- | ----------------------------------------- |
| V1  | `make test-hooks`                                                               | green, including `ci_gate.bats` unchanged |
| V2  | `bats tests/scripts/mutation_notify.bats`                                       | green; case count risen from 29           |
| V3  | strip `\|\| return 1` from `gh issue list`, run V2                              | **red**                                   |
| V4  | strip `\|\| return 1` from `gh issue close`, run V2                             | **red**                                   |
| V5a | strip `\|\| return 1` from `gh issue comment` **line 104** (green path), run V2 | **red**                                   |
| V5b | strip `\|\| return 1` from `gh issue comment` **line 115** (red path), run V2   | **red**                                   |
| V6  | strip `\|\| return 1` from `gh issue create`, run V2                            | **red**                                   |
| V7  | neuter the mock's per-key lookup to `_rc="${MOCK_GH_EXIT:-0}"`, run V2          | **red** (group 1 only)                    |
| V8  | `grep -c 'mutation-failure' scripts/mutation-notify.sh`                         | `0` — no hardcoded label                  |
| V9  | both workflows declare distinct `ISSUE_LABEL` values                            | rust / python                             |

**V3–V7 must be run by mutation, not by reading.** V3 and V4 are the two `bug-scan` measured
as surviving; V5a/V5b/V6 cover the remaining guarded sites.

**V5 is split deliberately.** `gh issue comment` has two call sites on mutually exclusive
branches. An earlier draft had a single "strip `|| return 1` from `gh issue comment`" row,
which is satisfied by stripping either one — so one site could be marked verified while
staying exactly as unpinned as before.

**V7 is the control for the control.** Without it, group 1 passing is consistent with a mock
that honours the new keys and with one that ignores them in a way that happens to fail
anyway.

## Out of scope — backlogged, with reasons

Each of these was in an earlier draft of this spec and is removed on evidence, not on effort.
Rows go to `docs/superpowers/README.md`.

- **Index-independent lookup** (replacing `--search` with a label + client-side filter, on
  the grounds that `--search` reads GitHub's eventually-consistent search index). The
  mechanism is real; the hazard is unwitnessed. Six correct notify decisions, zero observed
  misses, and the query has returned `98` on every hand-run. Note this spec removes
  `--search` from `mutation-notify.sh` anyway as a consequence of §1 — so the row is about
  the _other_ call site.
- **`concurrency` block on both mutation workflows.** The race it guards has never occurred:
  all 12 runs in the workflow's history are strictly sequential. The row must carry two
  things a future author will need — that workflow-level scope serialises a 360-minute
  `mutants` job to protect a seconds-long `notify` job, so **job-level scope on `notify` is
  the right shape**; and that `cancel-in-progress: false` still permits pending-run eviction,
  which the notify mechanism is structurally blind to because it attributes runs that die,
  not runs that never start.
- **`.github/workflows/release-sbom-monitor.yml:94-96`** carries the same `--search in:title`
  construct inside a per-finding loop, with no `--repo` and no `--limit`. Folded in by
  operator decision at one point and removed again on measurement: **that workflow has 0 runs
  and its label has 0 issues, in any state, ever.** Its per-CVE titles genuinely need title
  matching, so it needs a different fix from §1 — a `startswith` prefix filter. The row must
  record the trap that cost a review round here: declaring `ISSUE_PREFIX: ""` in the step
  `env:` block converts a noisy failure into a silent one, because `startswith("")` is true
  for every string, so the loop `continue`s and the CVE issue is **never filed**. Measured.
- **That `release-sbom-monitor.yml` has never run** despite being `active` with a monthly
  schedule. Separate finding, separate row.
- **The `:?` guard message row** already in the backlog — a message change with no
  behavioural test; bundling it widens the diff V3–V7 must cover.

## Risks

- **The mock is shared.** `ci_gate.bats` is the only other consumer and its `MOCK_GH_EXIT`
  usage is preserved by the fallback, so V1 is the check. A red V1 means the fallback is
  wrong, not the caller.
- **The label migration is a manual step outside the diff.** Forget it and the next Rust run
  files a second open issue beside #98. It cannot be tested; it goes in the PR description as
  a merge step, not in a test.
- **Two labels now exist where one did, and three live sites hardcode the old name.** An
  earlier draft of this line asserted that nothing outside `mutation-notify.sh` keys on the
  label and flagged itself for re-check. The re-check refuted it. Measured:

  ```
  tests/scripts/mutation_notify.bats:314  grep -qF -- "... --label mutation-failure --body"
  tests/scripts/mutation_notify.bats:333  grep -qF -- "... --label mutation-failure --body"
  CLAUDE.md:381                           "a red run files or updates a labelled
                                           `mutation-failure` issue"
  scripts/mutation-notify.sh:99,117,119   the three call sites §1 changes
  ```

  The two bats assertions are **in-diff and will fail** unless updated with §1 — they assert
  the whole `gh issue create` call as a single literal string, label included. `CLAUDE.md:381`
  is live documentation of the label name and is covered by §3. Hits in
  `docs/superpowers/plans/2026-08-01-*`, `plans/2026-09-01-*` and
  `specs/2026-08-31-*` are historical records of what was built at the time and are correctly
  left alone. Nothing else — no skill, no workflow, no script — keys on the label. Note the
  workflows themselves never name it; `mutation-notify.sh` hardcodes it, which is what §1
  replaces with `ISSUE_LABEL`.

- **`[[ "${_rc}" -ne 0 ]]` reads a non-numeric value as 0 silently** and errors on `4abc`.
  Identical to the existing `MOCK_GH_EXIT` line it replaces, so not a regression.

## Related

- Backlog rows absorbed: `tests/mocks/gh` isolation (fixed here); duplicate-issue lookup and
  missing `concurrency` (both **rewritten** rather than removed — the original rows assert an
  incident that did not occur).
- `docs/superpowers/specs/2026-08-31-mutation-notify-attribution-design.md` — created
  `scripts/mutation-notify.sh`.
- ADR-0024 — the OOM fix whose hand-testing produced the eight dispatch runs of 2026-08-01/02.

## Multi-Lens Review

### Round 1 — reviewed at commit `0ba8e6f8`

Findings and dispositions are preserved in git history at that SHA. Summary of what was
found and where it went:

| lens       | finding                                                                                                                                                                                                     | disposition                                                                                                                         |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Goal-Fit   | Race hypothesis refuted by the run record; V7/gojq resolved live; second call site at `release-sbom-monitor.yml`; V3/V4 covered 2 of 4 guard sites                                                          | **Addressed** — race retracted; sbom site now backlogged on later evidence; V5a/V5b/V6 added                                        |
| Ergonomics | Positive control inverted; derived variable undocumented and `CLAUDE.md:477` already wrong; V7 had no consumer; `grep -c` exits non-zero on success; pending-eviction unaddressed                           | **Addressed** — control corrected, docs fixed in §3, V-table rewritten; concurrency backlogged so eviction is now a row, not a risk |
| Risk       | Same inverted control, found independently; `env.ISSUE_TITLE` requires export and nothing enforced it; serialisation trades a visible failure for an invisible one; half the new assertions pass on nothing | **Addressed** — the export hazard is deleted outright by §1 rather than defended                                                    |

### Round 2 — reviewed at commit `7bc7e77`

| lens       | finding                                                                                                                                                                                                                                                                                                                                                                         | disposition                                                                                                                                                      |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Goal-Fit   | **The run-record correlation is refuted** — #98 was closed by the bot at 02:03:40 and reopened by the operator at 02:14:31, 54s after #99 was filed. Zero misses, zero duplicates, six correct decisions. Per-workflow labels are the cheaper fix for the one real defect, and the spec's rejection of them was a non-sequitur. V5 collapsed two guard sites into one row       | **Addressed** — verified independently against all four timelines, premise retracted in full, spec reduced to the two measured defects, labels adopted, V5 split |
| Ergonomics | Concurrency should be **job-level on `notify`**, not workflow-level: serialising a 360-min job to protect a seconds-long one, and both accepted risks evaporate under job scope. `gh-key` measured harmless but safe only via a `^gh ` anchor. `ISSUE_PREFIX: ""` is inert decoration. Tests 5/7/V8 pass on a missing file                                                      | **Addressed** — concurrency backlogged with the job-scope insight recorded in the row; `gh-key` dropped; missing-file hole fixed in test 5                       |
| Risk       | **`ISSUE_PREFIX: ""` converts a noisy failure into silent CVE suppression** — `startswith("")` matches everything, so the loop `continue`s and no issue is filed. `--limit 100` mitigates an exposure the change itself creates. The per-workflow-label rejection is a non-sequitur — the tokenization finding argues _for_ splitting the label. V8 self-absorbs on grep exit 2 | **Addressed** — sbom component removed entirely and the suppression trap recorded in its backlog row; labels adopted; V8 replaced                                |

Both round-2 lenses independently reached per-workflow labels from different directions, and
the `ISSUE_PREFIX: ""` defect was introduced by round 1's own correction — the third measured
instance in this corpus of a review round finding a defect created by the previous round's fix.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
