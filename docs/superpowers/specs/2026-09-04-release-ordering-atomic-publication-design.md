# Atomic release publication — sign before publishing, not after

**Date:** 2026-09-04
**Status:** Spec

## Context

`docs/superpowers/specs/2026-09-02-sbom-false-pass-and-dead-ruleset-design.md` went through
three full multi-lens review rounds trying to make the SBOM monitor report honestly. Every
round found real defects, and **every round's findings were defects created by the previous
round's fix.** Round 3 established why: all of them descend from a single ordering fact in
the release pipeline, and each round was a workaround for that fact rather than a fix to it.

**The release is published before the SBOM is attached.**

```
release-<name>-rs.yml
  release:                       # creates and pushes the tag, then publishes the release
    ...
    - Create and push tag        # git tag <name>-v<version>; git push origin <tag>
    - Create GitHub release      # softprops/action-gh-release  <- PUBLISHED HERE
  sign:
    needs: [release]             # so the release must already exist
    uses: ./.github/workflows/release-sign.yml
```

```
release-sign.yml
  - Download binary from release # gh release download <tag> --pattern <binary>
  - Install syft / Generate SBOM
  - Install cosign / Sign binary
  - Upload signatures and SBOM   # gh release upload  <- SBOM ATTACHED HERE, last step
```

Between those two points there is a published release carrying a binary and no SBOM. Three
separate defects in the sibling spec were faces of that window:

| round | the workaround                                      | how it failed                                                                                                                                                                                |
| ----- | --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     | `on: release: types: [published]` to check promptly | inert (`GITHUB_TOKEN` events start no workflow runs) and, if it fired, fired _inside_ the window                                                                                             |
| 2     | keep the trigger, add an issue channel              | same trigger, so every healthy release would file a spurious issue                                                                                                                           |
| 3     | `needs: [sign]` job instead of a trigger            | `sign` success implies the asset exists, and `sign` failure **skips** the job — so the only reachable verdict is `ready`, and `missing-asset` became unreachable on the path it was added to |

Round 3's goal-fit lens put the last one plainly: the most likely real generator of
`missing-asset` is a published release whose `sign` job failed, and `needs: [sign]` skips
the monitor in exactly that case.

**The window is the defect.** Three rounds produced three workarounds, each introducing
defects of the same magnitude as the one it fixed, and the design grew every round — the
opposite of convergence. This spec removes the window.

### Why the window exists at all

`release-sign.yml` is a **reusable workflow**, so it runs as its own job with its own
filesystem, and therefore has to fetch the binary with `gh release download`. That download
is the only reason the release must exist before signing. Remove the download and the
ordering constraint disappears — not narrowed, gone.

### Measurements this spec rests on

All taken 2026-09-04 against the live repo.

```
$ for f in .github/workflows/release-*-rs.yml; do ... done
all 11:  sign: needs: [release]  uses: ./.github/workflows/release-sign.yml
all 11:  workflow-level  permissions: contents: write, id-token: write

$ grep -c continue-on-error .github/workflows/release-sign.yml
0                          # so sign success implies the upload succeeded

$ gh api repos/brujack/math/releases --jq '.[].tag_name'
v0.1.0                     # one release, matching no <name>-v* pattern

$ for f in release-*-rs.yml release-sign.yml; do gh run list --workflow $f ...; done
0 runs, all 12             # nothing in this pipeline has ever executed
```

The last row is the reason Part 1 exists. This spec rewrites code that has never run, in a
pipeline that has never run, to fix an ordering nobody has observed.

## Decisions

| #   | Question                                          | Decision                                                                                               |
| --- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| 1   | How is the window removed?                        | A composite action signing **before** publication, so the release is created once with all four assets |
| 2   | What happens to `release-sign.yml`?               | Deleted. Its reusable-workflow shape is what forces the download that creates the window               |
| 3   | How is this verified, given nothing has ever run? | A throwaway release **before** the rewrite for a baseline, and a second one after as confirmation      |
| 4   | Where does the shell live?                        | `scripts/sbom-sign.sh`, bats-tested — not an inline `run:` block                                       |
| 5   | What keeps eleven callers in sync?                | A uniformity test over all eleven workflows                                                            |

Alternatives considered and rejected under decision 1:

- **Draft release, publish after signing.** Preserves the reusable-workflow structure, but
  carries an unresolved feasibility risk: GitHub's `GET /releases/tags/{tag}` does not
  resolve draft releases, so `gh release download "${RELEASE_TAG}"` inside `sign` may 404 —
  the step the whole approach depends on. It also introduces stuck drafts as a new silent
  failure state, and forces `--exclude-drafts` on the monitor or it starts resolving
  unpublished tags. More mechanism, and a new failure class, to preserve a window rather
  than remove it.
- **Artifact hand-off.** Release job uploads the binary via `actions/upload-artifact`; the
  sign job downloads it and creates the release itself. No draft, no window — but it moves
  release creation into the signing workflow, which is a surprising home for it, and
  `release-sign.yml` would need every release-notes and checksum input the release job
  currently holds.

## Part 1 — Baseline run, before any code changes

Cut one throwaway release against the pipeline **as it stands today**. This runs first, before
any edit, and it is the only step in this spec that produces evidence rather than inference.

**Binary: `sq`.** `sq/sq-rs/install_deps.sh` installs only the Rust toolchain — no GMP, no
MPFR, no Python dependencies — so it is the fastest path with the fewest confounds.
`release-sign.yml` is byte-identical across all eleven callers, so a finding from any one of
them transfers.

**The tag must be `sq-v<version>`.** `release-sq-rs.yml` calls the signing workflow with
`release_tag: "sq-v${{ inputs.version }}"` hardcoded, so a differently-named tag would not
exercise the real path.

What the run answers, none of which is currently known:

1. Does `release-sign.yml` work at all? `cosign-installer@v4.1.2`,
   `sbom-action/download-syft@v0`, and keyless OIDC in this repo are all unexercised.
2. How long is the window? `published_at` versus the sign job's upload-step completion. This
   is the interval round 3's risk lens flagged as an unobserved propagation assumption, and
   it is directly measurable here.
3. Does the finished release carry `sq.sbom.spdx.json` at all?

```bash
gh workflow run release-sq-rs.yml -f version=0.0.1-rc1
gh run watch <run-id>

# 2 — the window, measured rather than assumed
gh api repos/brujack/math/releases/tags/sq-v0.0.1-rc1 --jq '.published_at'
gh api repos/brujack/math/actions/runs/<run-id>/jobs \
  --jq '.jobs[] | select(.name|test("Sign")) | .completed_at'

# 3 — the asset list
gh release view sq-v0.0.1-rc1 --json assets --jq '.assets[].name'
```

### Cleanup is a verified step, not a tidy-up

The monitor resolves `gh release list --limit 50 | startswith("sq-v") | head -1`,
newest-first. A leftover throwaway therefore wins forever and produces exactly the silent
wrong answer this whole effort exists to eliminate.

```bash
gh release delete "sq-v0.0.1-rc1" --yes --cleanup-tag
gh release list --limit 50 --json tagName \
  --jq '.[] | select(.tagName | startswith("sq-v"))'   # MUST be empty
git ls-remote --tags origin 'sq-v*'                    # MUST be empty
```

The second assertion is not belt-and-braces. `--cleanup-tag` is _asserted_ to remove the git
tag; `git ls-remote` is what confirms it, and a tag surviving its release is precisely the
state that leaves `startswith("sq-v")` matching nothing while `git tag` disagrees.

**Two accepted side effects**, approved by the operator before this spec was written. The run
publishes a release on a public repository, briefly visible. And the `Commit CHANGELOG` step
pushes a `chore(changelog): update sq for v0.0.1-rc1` commit to master, which `--cleanup-tag`
does not revert — it needs reverting or accepting separately.

**A baseline that fails is a finding, not a formality.** If `release-sign.yml` is already
broken today, this spec is repairing rather than reordering, and Parts 2 and 3 should be
re-read against that before proceeding.

## Part 2 — The composite action

### `.github/actions/sbom-sign/action.yml`

```yaml
name: SBOM and Sign
description: Generate an SPDX SBOM and a keyless cosign bundle for a built binary
inputs:
  binary_path:
    description: "Directory holding the built binary (e.g. sq/sq-rs/target/release)"
    required: true
  binary_name:
    description: "Binary file name (e.g. sq)"
    required: true
runs:
  using: composite
  steps:
    - uses: anchore/sbom-action/download-syft@e22c389904149dbc22b58101806040fa8d37a610 # v0
    - uses: sigstore/cosign-installer@6f9f17788090df1f26f669e9d70d6ae9567deba6 # v4.1.2
    - shell: bash
      run: |
        "${GITHUB_WORKSPACE}/scripts/sbom-sign.sh" \
          "${{ inputs.binary_path }}" "${{ inputs.binary_name }}"
```

A composite action runs **in the caller's job**, so the freshly built binary is already on
disk. No download, no second job, no ordering constraint.

**`${GITHUB_WORKSPACE}` is explicit rather than relying on a relative path.** A composite
action's `run:` steps and its own bundled files resolve from different roots —
`${{ github.action_path }}` for the latter — and a bare `scripts/sbom-sign.sh` is the kind of
path that works until someone moves the action. The script lives in the repository, not in
the action directory, so the workspace root is the correct anchor and stating it removes the
question.

### Each release workflow

The `sign:` job is deleted. One step is added between the checksum and the release:

```yaml
- uses: ./.github/actions/sbom-sign
  with:
    binary_path: sq/sq-rs/target/release
    binary_name: sq

- name: Create GitHub release
  uses: softprops/action-gh-release@efb35369e0ad2afab669f228072c1b0d510eae64 # v3
  with:
    tag_name: "sq-v${{ inputs.version }}"
    name: "sq v${{ inputs.version }}"
    body_path: /tmp/release-notes.md
    files: |
      sq/sq-rs/target/release/sq
      sq/sq-rs/target/release/sq.sha256
      sq/sq-rs/target/release/sq.sbom.spdx.json
      sq/sq-rs/target/release/sq.bundle
```

Four files, one call, one atomic publication. `release-sign.yml` is deleted.

Three properties worth stating, because each was a failure mode elsewhere in this effort:

**Permissions already exist.** All eleven workflows carry `permissions: contents: write,
id-token: write` at workflow level — measured, all eleven — so keyless cosign has OIDC in the
release job with no new grant. A composite action inherits the job's permissions and cannot
narrow them. That is fine here and is the constraint to revisit if signing ever needs a
tighter scope.

**The SBOM comes from the built binary rather than a downloaded copy.** Same bytes, one less
round trip, and it removes the `gh release download` step that was the sole reason the
release had to exist first.

**The shell is extracted, not inline.** `scripts/sbom-sign.sh` is two commands, and inline
`run:` blocks are the untestable layer that produced round 3's defects in the sibling spec.
Extracted, it joins `SHELL_SOURCES`, is shellchecked by `make lint-hooks`, and enters the
bash-coverage instrumented set through the existing `git ls-files 'scripts/*.sh'` predicate.

### Tests

`tests/scripts/sbom_sign.bats`, with `syft` and `cosign` mocked on `PATH`:

- **Writes both artifacts** — assert `<binary>.sbom.spdx.json` and `<binary>.bundle` exist at
  the expected paths after a successful run.
- **Propagates a syft failure** — mock exits non-zero; assert the script exits non-zero and
  does **not** proceed to cosign.
- **Propagates a cosign failure** — assert non-zero.
- **Missing binary** — the named binary does not exist at `binary_path`; assert a non-zero
  exit with a message naming the path, rather than syft being invoked on nothing.

Both binaries the script calls are mocked, so `shell.md`'s usual PATH-mock hazard — a stub
shadowing a real binary the production code needs — does not arise. The hazard that does
apply is its mock-fidelity sibling: **the first case must assert on the files produced, not
on the mock having been called.** A stub that exits 0 without writing anything passes a
call-count assertion and fails the artifact assertion, and only the second distinguishes a
working script from one that invokes syft and ignores the result.

### Uniformity test

`tests/test_release_workflows.py`, precedent `tests/test_renovate_automerge_policy.py`:

- No workflow references `release-sign.yml`.
- All eleven `release-<name>-rs.yml` reference `./.github/actions/sbom-sign`.
- Each passes its own `binary_name`, matching the workflow's own binary.
- Each `softprops` `files:` list contains all four artifacts for that binary.

This exists because round 3 found eleven hand-maintained job blocks with nothing asserting
they stay in sync. Without it, a twelfth binary added later ships unsigned and nothing says
so — a `dormant`-shaped failure, silent by construction.

**What no test here covers**, stated so a green suite is not misread: whether keyless cosign
OIDC works inside a composite action's job context, and whether `softprops` accepts four
files. Neither is knowable from a mock. That is what Part 3's confirmation run is for.

## Part 3 — Confirmation, and the knock-on

### Confirmation run

A second throwaway release after the rewrite, same binary, same verified cleanup.

```bash
gh workflow run release-sq-rs.yml -f version=0.0.2-rc1
gh release view sq-v0.0.2-rc1 --json assets --jq '.assets[].name'   # all four present
```

The assertion that matters is that **no interval exists** between publication and asset
presence. With a single job the two are simultaneous by construction — the point of measuring
it is to observe that rather than assert it, and to compare against Part 1's recorded window.

### What this does to the sibling spec

With publication atomic, _published implies SBOM present_ holds by construction:

- **Decision 7 of the sibling spec is not fixed — it is unnecessary.** No per-release
  monitoring job, no eleven job blocks, no `if: always()` question.
- `missing-asset` on the release path becomes **impossible** rather than skipped, which is
  the distinction round 3 identified and could not reach from inside that design.
- What survives is `missing-asset` as a monthly-cron signal for **out-of-band causes only**:
  a hand-cut release, or a deleted asset. There are zero releases predating this change, so
  the state starts genuinely empty.
- The issue file/close arm, the fourth `unreadable-sbom` state, the two dropped
  `gh issue comment` arms, and the tag-free-title invariant collapse to whatever a monthly
  sweep over out-of-band causes actually warrants — which is much less than three rounds of
  review built.

That is the first time in this effort a fix has made the design smaller rather than larger.

**The sibling spec is not edited by this one.** Its Section 1 is already marked on hold
pending this change, and rewriting it before this lands would be a fourth revision against an
unverified premise. Its Section 2 (branch protection) is independent, has drawn zero findings
across three rounds, and ships on its own schedule.

## Verification plan

| stage        | commands                                                                                                                   |
| ------------ | -------------------------------------------------------------------------------------------------------------------------- |
| Baseline     | Part 1 in full, including both cleanup assertions returning empty                                                          |
| Build        | `make lint-hooks` · `bats tests/scripts/sbom_sign.bats` · `python3 -m unittest tests.test_release_workflows` · `make test` |
| Confirmation | Part 3's run, all four assets present, window compared against baseline                                                    |

Each bats case must be seen red before its implementation exists — in particular the
syft-failure case, since propagation through a two-command script is the thing most likely to
be written as an unchecked sequence.

## Scope

**In scope:** `.github/actions/sbom-sign/action.yml` (new), `scripts/sbom-sign.sh` (new),
`tests/scripts/sbom_sign.bats` (new), `tests/test_release_workflows.py` (new), all eleven
`.github/workflows/release-<name>-rs.yml` (delete the `sign:` job, add the composite step,
extend `files:`), deletion of `.github/workflows/release-sign.yml`, `CLAUDE.md` (the CI table
row for `release-sign`, the workflow count, and a note on the atomic-publication invariant),
and the two throwaway releases with their verified cleanup.

**Out of scope:**

- Cutting a real per-binary release. The throwaways exist to exercise the pipeline, not to
  ship anything.
- The sibling spec's Section 2 (branch protection) — independent and already clean.
- Rewriting the SBOM monitor. Its scope collapses once this lands, and rewriting it first
  would be a fourth revision against an unverified premise.
- Reverting the `chore(changelog)` commits the throwaway runs leave on master. Accepted by
  the operator; named here so the decision is visible rather than implied.

## Risks

- **Cleanup incompleteness poisons the monitor permanently.** `head -1` over a newest-first
  list means a surviving throwaway wins forever. Both cleanup assertions must return empty,
  and `git ls-remote` is the one that catches a tag outliving its release.
- **The baseline may reveal today's pipeline is already broken.** A legitimate outcome. It
  would mean this spec repairs rather than reorders, and Parts 2 and 3 should be re-read
  against that finding before proceeding.
- **A composite action cannot declare its own `permissions`.** It inherits the job's. Fine
  today; the constraint to revisit if signing ever needs a narrower scope than the release
  job's `contents: write`.
- **Eleven files change.** The uniformity test is the mitigation, and it is named in Tests
  rather than only asserted here — the sibling spec shipped a Risks bullet claiming coverage
  its test list did not contain, and this bullet is written to be checkable against that list.
- **Two throwaway releases are briefly public**, and each leaves a `chore(changelog)` commit.
  Accepted; listed so neither is a surprise.
- **`softprops/action-gh-release` with four files is unexercised.** No test can cover it; the
  confirmation run is the only evidence, which is why Part 3 is a stage rather than a
  footnote.

## Related

- `docs/superpowers/specs/2026-09-02-sbom-false-pass-and-dead-ruleset-design.md` — the three
  review rounds that located this ordering as the shared cause; its Section 1 is on hold
  pending this spec
- `.github/workflows/release-sign.yml` (to be deleted), `release-<name>-rs.yml` (eleven),
  `release-sbom-monitor.yml`, `release-sbom-monitor-schedule.yml`
- `~/.claude/standards/ci.md` — cosign v4 `--bundle` semantics, SHA256 checksum generation,
  action SHA pinning
- `~/.claude/standards/shell.md` — the PATH-mock hazard the bats suite must avoid
