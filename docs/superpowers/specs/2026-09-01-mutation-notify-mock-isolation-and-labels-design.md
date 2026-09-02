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

Give each workflow its own label and delete the title comparison. **The naming is
deliberately asymmetric: Rust keeps the incumbent label, only Python gets a new one.**

```yaml
# mutation-testing.yml notify step env:
  ISSUE_LABEL: mutation-failure          # incumbent, unchanged
# mutation-testing-python.yml notify step env:
  ISSUE_LABEL: mutation-failure-python   # new
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

`ISSUE_TITLE` still supplies `--title` on create. It is no longer a *lookup* input, which is
the point: the label becomes the discriminator, so there is no token matching to get wrong.

**Why asymmetric rather than `-rust`/`-python`.** Symmetry is the obvious shape and it costs a
manual, untestable, production-side migration step. Earlier drafts specified
`gh issue edit 98 --add-label mutation-failure-rust --remove-label mutation-failure` after
merge. Three independent review lenses found three different ways that fails, and keeping the
incumbent name for Rust removes all three at once:

- The step was **already stale when written**. #98 was closed by the operator at
  `2026-09-01T23:22:29Z`, four seconds after the commit that specified it
  (`22babba`, `23:22:25Z`). Zero open issues carry the label.
- Its **forgotten-observable on the green path is silence**, which is worse than the
  duplicate the Risks section named. A missed relabel makes the old issue invisible to the
  new lookup in both directions: a red run files a second issue (visible), and a *green* run
  does nothing at all — the old issue never closes and can never be closed by the machine
  again, while still reading as a live failure. With `cron: "0 4 1 * *"` the next run is
  ~30 days out and the session that owed the step is long gone.
- It **depends on repo state at merge time**, which no test can pin and which measurably
  moved inside four seconds.

Under asymmetric naming there is nothing to migrate: every existing issue already carries the
label Rust will keep looking for.

**One residual, stated rather than hidden.** `mutation-failure-python` does not exist —
measured: `gh label list` returns 15 labels including `mutation-failure` and neither
`-rust` nor `-python`. So Python's first red run must self-provision it, a path never
exercised here because the incumbent label always pre-existed. The chain is sound but worth
naming: `issues: write` **is** sufficient for label creation (GitHub's "Create a label"
endpoint documents Issues-write), `gh label create` is `2>/dev/null || true`, and
`gh issue create --label <nonexistent>` **fails** — so a swallowed label-create failure
resurfaces one line later as a red `notify` job that filed nothing, on precisely the run
where the notification is the product. It is loud rather than silent — but it is loud on **the one run where the notification is the
product**. The Python workflow's first red run is precisely when someone needs a tracking
issue, and that run would produce a red `notify` job and no issue at all. The cost asymmetry
settles it: one idempotent command now, against a failed notification on the single run that
matters.

**So pre-creating the label is the default, not an option**, and self-provisioning via
`gh label create` is the fallback that covers a forgotten step:

```bash
gh label create mutation-failure-python --repo brujack/math \
  --color B60205 --description "Monthly mutation run failed"
```

Idempotent, needs no ordering against the merge, and can be run while the plan is still open.

No `--limit` is specified. Steady state under a per-workflow label is one open issue, `.[0]`
takes the newest, and gh's default page of 30 is two orders of margin.

**The label is now the sole lookup key and gh does not validate it.** Measured:
`gh issue list --label does-not-exist-zzz` returns `[]` with rc 0. A typo in `ISSUE_LABEL`
yields "no open issue" forever — a fresh issue every month, never red, never noticed. That is
the class §1 exists to delete, re-entering through the new channel, so test 5 asserts the
**literal** values rather than merely that the two differ.

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

`CLAUDE.md:381`'s *"a red run files or updates a labelled `mutation-failure` issue"* stays
**true** under asymmetric naming and needs no edit — that is one of the things the asymmetry
buys. Add a clause naming Python's separate label rather than rewriting the sentence.

### 4. Tests — `tests/scripts/mutation_notify.bats`

**One fixture change, and it is not the one earlier drafts named.** Those drafts said
`mutation_notify.bats:314` and `:333` were in-diff because they assert the whole
`gh issue create` call including `--label mutation-failure`. Under asymmetric naming Rust
keeps that label, so **both assertions stand unchanged**. What does change is `setup()`:
adding `: "${ISSUE_LABEL:?}"` to `main()` breaks **8** pre-existing cases unless `setup()`
exports `ISSUE_LABEL`, exactly as it already exports `ISSUE_TITLE` at `:20`. Measured by a
review lens against a working implementation. A `setup()` fixture change is a fixture change
and is named here rather than discovered during implementation.

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

| # | command | expects |
| --- | --- | --- |
| V1 | `make test-hooks` | green, including `ci_gate.bats` unchanged |
| V2 | `bats tests/scripts/mutation_notify.bats` | green; case count risen from 29 |
| V3 | strip `\|\| return 1` from `gh issue list` (:99), run V2 | **red** |
| V4 | strip `\|\| return 1` from `gh issue close` (:105), run V2 | **red** |
| V5 | strip `\|\| return 1` from `gh issue comment` **green path** (:104), run V2 | **red** |
| V6 | neuter the mock's per-key lookup to `_rc="${MOCK_GH_EXIT:-0}"`, run V2 | **red** (group 1 only) |
| V7 | `! command grep -q 'mutation-failure' scripts/mutation-notify.sh` | exit 0 — no hardcoded label |
| V8 | `grep -c 'ISSUE_LABEL: mutation-failure$' .github/workflows/mutation-testing.yml` and `grep -c 'ISSUE_LABEL: mutation-failure-python$' .github/workflows/mutation-testing-python.yml` | `1` and `1` |

**V3–V6 must be run by mutation, not by reading.**

**Only three of the five guards are killable, and the spec says so rather than implying
five.** `gh issue comment` on the **red** path (:115) and `gh issue create` (:119) are each
the last statement of their branch in `main()`'s final `if/else`, which is `main()`'s last
statement. Stripping `|| return 1` there changes the return from `1` to the gh exit code
`4` — both non-zero, so an oracle of `status -ne 0` cannot discriminate. **These are
equivalent mutants.** Measured by a review lens against a working implementation, and
confirmed by control-flow reading: :99, :104 and :105 each have further flow or an explicit
`return 0` after them, so stripping those yields `0` and does discriminate.

Two consequences, both stated plainly because earlier drafts implied otherwise. **Defect 1
is 3-of-5 fixed, not 5-of-5** — three propagation sites gain a killing test and two cannot.
And **those two `|| return 1` are decoration**: nothing downstream distinguishes rc 1 from
rc 4, since Actions reads only non-zero. They stay for uniformity, recorded as equivalent
the way this repo already records equivalent cargo-mutants findings in `.cargo/mutants.toml`.
Do not invent an exact-rc assertion to manufacture a kill.

**Their decorative status is POSITIONAL, not structural, and that is the part to carry
forward.** It holds only while each is the last statement of its branch. Append anything after
`gh issue create` — a log line, a summary write, a second call — and the guard silently becomes
load-bearing, with no test covering it. Demonstrated:

```
guard is the last statement:   guarded rc=1, stripped rc=4   both non-zero -> oracle blind
one statement appended after:  guarded rc=1, stripped rc=0   oracle SEES it, and the
                                                             appended statement runs only
                                                             in the stripped version
```

So the pair is decorative by adjacency, exactly as a `local _out=$(...)` / `_rc=$?` pair is
correct by adjacency. **Anyone appending to either branch of that final `if/else` is changing
what these guards do and owes them a test at that point.** Record it beside the code, not only
here — the next editor will read the function, not this spec.

**The provenance is worth keeping.** These rows were *added* by round 1's correction, *split*
by round 2's, and executed by nobody until round 3 — in a spec whose own verification section
says to run mutations rather than read them.

**V6 is the control for the control.** Without it, group 1 passing is consistent both with a
mock that honours the new keys and with one that ignores them in a way that happens to fail
anyway.

**V7 greps for `mutation-failure`, not `mutation-failure-python`.** The `-python` form was
written into an earlier draft of this table and is **vacuous**: that literal never appears in
`mutation-notify.sh` before *or* after the change — Python's label lives in workflow YAML, and
the script only ever sees `${ISSUE_LABEL}`. Measured on the base tree, the `-python` gate exits
**0**, i.e. it passes on a completely unmodified repo. The incumbent literal is the one the
change actually removes: 3 occurrences today (`:99`, `:117`, `:119`), so the corrected gate
exits 1 on base and 0 after.

**V7 is `! command grep -q`, not `grep -c`.****V8 has a command.** An earlier draft's row was prose — "both workflows declare distinct
`ISSUE_LABEL` values" — with no oracle, satisfiable by reading, and it was the only
verification §1 had. It now asserts the two **literal** values, because distinctness alone
would pass on two labels that are both wrong.

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
  wrong, not the caller. Three review lenses ran both suites against this change in scratch
  trees: 10/10, 39/39 and 37/37.
- **Python's label does not exist yet** and its first red run must self-provision it — see
  §1. Loud on failure, not silent, and removable with one pre-merge `gh label create`.
- **`ISSUE_LABEL` is now the sole lookup key and gh does not validate it** — a typo yields
  `[]` with rc 0, forever. V8 pins the literal values for this reason.
- **`setup()` gains an `ISSUE_LABEL` export**, without which 8 pre-existing cases fail — a
  fixture change, named in §4.
- **Two labels now exist where one did**, so the GitHub UI's `label:mutation-failure` filter
  shows only Rust history going forward. Asymmetric naming keeps that filter continuous for
  Rust; Python's archive starts empty, which is correct since it has never filed an issue.
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

### Round 3 — reviewed at commit `22babba`

Scoped to the newly adopted, never-reviewed label design; the mock component was excluded as
twice-reviewed and execution-verified.

| lens | finding | disposition |
| --- | --- | --- |
| Goal-Fit | **The migration step rests on a state claim already false** — #98 was closed 4s after the spec was committed, and 0 open issues carry the label. Third instance of the state-read-as-history error, in the paragraph instructing a future actor. Fix: keep `mutation-failure` for Rust, so there is nothing to migrate. Backlog rows render outside the table | **Addressed** — asymmetric naming adopted, migration deleted with its Risks row, the two bats edits and the `CLAUDE.md:381` edit; table rendering fixed |
| Ergonomics | **The forgotten-migration observable on the green path is silence**, not a duplicate: the old issue never closes and can never be closed by the machine again, ~30 days to the next cron. Three of four backlog rows violate `behavior.md`'s one-liner rule, and the spec *instructed* the violation. V9 is prose with no oracle | **Addressed** — the silent half is what makes asymmetric naming the fix rather than a preference; rows reshaped to one-liners with pointers; V8 (was V9) given a command asserting literal values |
| Risk | **V5b and V6 are equivalent mutants** — both are the last statement of `main()`, so stripping the guard returns 4 instead of 1 and no `status -ne 0` oracle can discriminate; Defect 1 is 3-of-5, and those two guards are decoration. Neither new label exists, so a swallowed `gh label create` failure resurfaces as a red job that filed nothing. `ISSUE_LABEL` is now the sole key and gh does not validate it. `: "${ISSUE_LABEL:?}"` breaks 8 cases unless `setup()` exports it. **V8 was dispositioned "replaced" in round 2 and was not replaced** | **Addressed** — equivalence recorded rather than papered over, table renumbered to three killable mutations; label bootstrap named with its pre-merge removal; V8 asserts literals; `setup()` export named in §4; the `grep -c` row actually replaced this time |

All three lenses independently converged on the migration step as the weakest part, by three
different routes. The asymmetric-naming fix removes all three at once — and it is a deletion,
which is why review stops here: round 3's findings sit in the verification apparatus and the
backlog prose rather than in the design, and every correction this round removes surface.

Two process failures are recorded rather than quietly fixed. A round-2 disposition asserted a
fix ("V8 replaced") that was never applied. And V5a/V5b/V6 were added by round 1, split by
round 2, and executed by nobody until round 3 — in a spec whose verification section says to
run mutations rather than read them.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger.
