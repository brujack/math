# ADR-0025: Attest mutation-run progress with a breadcrumb, not a step conclusion

**Status:** Accepted
**Date:** 2026-09-01

## Context

Both mutation workflows end in a `notify` job that files, comments on, or closes a
tracking issue. When the run was red, that job chose what to say with a single boolean:

```bash
if [[ -d artifact/status ]]; then
  crates=$(grep -l '^red' artifact/status/* | xargs -r -n1 basename | sed 's/^/- /')
  detail="Failing crates:"$'\n'"${crates:-- (none flagged; see run log)}"
else
  detail="No artifact was produced. The runner was terminated (exit 143) or the job timed out, ..."
fi
```

The `else` branch is reachable by at least four distinct causes and asserted one of them
as fact:

| #   | cause                                                                                                                                                                       | old message                                                                     |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| 1   | job terminated; the `if: always()` upload step never ran                                                                                                                    | correct                                                                         |
| 2   | job died before `mkdir -p "${GITHUB_WORKSPACE}/status"` — failed checkout, failed `cargo install`, or the `no crates found` guard at `mutation-testing.yml:52-54` exiting 1 | wrong: blames a runner kill for an install failure                              |
| 3   | artifact uploaded holding `mutants.out/` but no `status/`                                                                                                                   | wrong, and self-contradicting — claims no artifact about one it just downloaded |
| 4   | `actions/download-artifact` v8 digest-mismatch, swallowed by `continue-on-error: true`                                                                                      | wrong                                                                           |

Causes 2 and 3 predate the v8 bump. Cause 2 is structural: the guard exits five lines
upstream of the `mkdir`, and no workflow sets `if-no-files-found`, so the default `warn`
applies and the upload produces nothing.

The deeper defect is that the sentence had no supporting field. `needs.mutants.result` is
`failure` for a SIGTERM and `failure` for an ordinary step failure alike, and the exit code
appears only in the run log, which `notify` never reads. This is the two-valued-field
failure `behavior.md` describes: an outcome space with more members than the field chosen
to report it, so the reporter collapses the remainder into whichever member was written
down first.

The cost is diagnostic rather than a wrong verdict — the pass/fail comes from
`needs.mutants.result`, not from the artifact. But it is the same misattribution that sent
ADR-0024's investigation after the 360-minute job timeout instead of the missing memory
bound.

## Decision

**Have the job attest its own progress, and key the report on that attestation.**

The mutants job writes a breadcrumb immediately after checkout and before its tool install:

```yaml
- name: Mark job start
  run: mkdir -p "${GITHUB_WORKSPACE}/marker" && date -u > "${GITHUB_WORKSPACE}/marker/job-began"
```

`marker/` joins the upload `path:` list. The notify decision moves out of YAML into
`scripts/mutation-notify.sh`, shared by both workflows, which reads:

| artifact                                                             | reported cause                                                                                  |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| no `marker/` — download failed, or the artifact is empty or lacks it | `no-attestation` — the job's own reporting never ran; names four possibilities and asserts none |
| `marker/` + `status/`                                                | `verdicts-present` — names the failing units                                                    |
| `marker/` + other output, no `status/`                               | `loop-began-no-verdict`                                                                         |
| `marker/` only                                                       | `died-before-loop`                                                                              |

Placement is load-bearing: after checkout so the workspace exists, before the install so a
toolchain or install failure still leaves the breadcrumb. Every cause-2 route then runs with
the marker already on disk, and the message naming it is true because a file the job wrote
says so.

Each arm emits a stable `Cause: <slug>` token before its prose, so tests assert the token
and the wording stays free to change.

### Considered and rejected: probe the Actions API for step conclusions

The first design read the mutants job's per-step conclusions back through
`gh api /actions/runs/<id>/jobs`, treating `Upload: skipped` despite `if: always()` as the
termination signal. It was rejected during review:

- It needed `actions: read` on both notify jobs, a jobs-API probe with its own failure
  branch, and a job-identity selector — a duplicated reference that a job rename would break
  silently.
- It rested on two unmeasured claims: that `Upload: skipped` discriminates termination from
  an ordinary failure, and that `steps[]` is populated with terminal conclusions at the
  instant `notify` queries it for a **reaped** job, where the runner never reported. Settling
  the second required a probe branch and a deliberately OOM-reaped runner.
- Its own branch table reproduced the defect it was fixing: with the upload step concluding
  `success` on a zero-match glob, cause 2 landed in a row reading _"Artifact uploaded but not
  downloadable"_ — false, where master's text was at least true for that cause.

**The cost of deciding whether to build the probe exceeded the cost of building the
alternative.** A breadcrumb the job wrote is attestation; a step conclusion supports only an
inference about it, which is the standard `USER.md` sets for any trust signal.

The 2026-09-01 cron then answered the first claim for free: run 33468276278 was an ordinary
non-terminated `Run mutants` failure whose `Upload mutants output` step concluded `success`
— the negative sample this repository had never recorded. The second claim is now moot;
nothing queries `steps[]`.

## Consequences

**Positive.** Cause 2 is named from evidence rather than guessed. The two notify
implementations collapse to one tested script — `scripts/mutation-notify.sh` joins the
`bash-coverage` instrumented set (27 files, up from 26) and CI's figure rose from 30% to 33%.
`notify` permissions stay `issues: write` only; nothing reads the Actions API. `exit 143`
appears in no workflow.

**Negative.** A third string must now agree with two others — the workflow's write path, its
upload path, and the script's probe. `tests/scripts/mutation_notify.bats` asserts that
contract for both workflows and requires the conforming count to be exactly 2, so a third
mutation workflow added without a marker step fails rather than passing unnoticed.

**Neutral.** `digest-mismatch: error` is now explicit on both download steps. It restates the
v8 default and changes no verdict; it is written down because inheriting an upstream default
is how cause 4 arrived.

**Unchanged, deliberately.** The `--search`-based issue lookup keeps its dependence on
GitHub's issue search index, and neither workflow has a `concurrency:` block. Both are
recorded in `docs/superpowers/README.md`'s Backlog. `math#100` — a single-crate green run
closing the full-sweep issue — is likewise untouched, and the test suite asserts the
`--repo` safety property on that path without asserting the close is correct, so fixing #100
does not have to turn a passing test red.

## Related

- ADR-0024 — mutation testing memory cap; the misattribution this ADR fixes is what
  misdirected that investigation.
- ADR-0020 — dual-mode CI (pre-push hook + PR-only Actions).
- `docs/superpowers/specs/2026-08-31-mutation-notify-attribution-design.md` — full design,
  measurements, and two rounds of multi-lens review.
- `docs/superpowers/plans/2026-09-01-mutation-notify-attribution.md` — implementation plan.
