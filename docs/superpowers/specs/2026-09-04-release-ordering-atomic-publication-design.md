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

## The syft probe — measured 2026-09-04, and it re-scopes this spec

Step 8 round 1's goal-fit lens raised an assumption it could not settle: that
`syft <stripped rust binary> -o spdx-json` produces an SBOM with a non-empty package list.
Its stated refutation condition was "if it returns 0 or 1, the ordering question is moot and
the real work is elsewhere." It returns **1**, and the 1 is the binary itself.

### Measured, both formats

```
                                              syft   sbom     lockfile
binary                        format         pkgs   bytes    crates
sq/sq-rs/target/release/sq    Mach-O arm64      1    1208       133
e/e-rs/target/release/e       Mach-O arm64      1       -       137
pi/pi-rs/target/release/pi    Mach-O arm64      1       -       137
prime/.../release/prime       Mach-O arm64      1       -       133
sq (built on workstation)     ELF x86-64        1    1208       133
```

syft 1.51.1 in every row. The single package is named for the binary and carries
`versionInfo: sha256:63df76fd…` with no `externalRefs` — it is syft's generic binary entry,
not a dependency.

The ELF row is the one that matters: `ubuntu-latest` builds ELF x86-64, and a macOS-only
measurement would have been `tdd.md` pitfall G — a local pass that is not evidence for the
class. Measured on the workstation (`ssh workstation`, Ubuntu, x86-64), same syft version,
same result, byte-identical SBOM size.

### What that means

`grype` scans the SBOM's package list. That list contains zero dependencies, so **the
monitor cannot find a CVE** — not because it is mis-ordered, mis-triggered, or
mis-delivered, but because there is nothing in the document to scan. Every mechanism across
this spec and its sibling guarantees the timely, atomic, correctly-named delivery of an
empty artifact.

The cause is that nothing here builds with `cargo-auditable`: `grep -rn auditable` across
`Cargo.toml`, `Makefile` and `*.yml` returns nothing, Rust binaries carry no package-manager
metadata, and syft's `rust-audit-binary` cataloger reads a `.dep-v0` ELF/Mach-O section that
is only present when `cargo-auditable` emits it.

### The remedy, also measured

On the workstation, same binary, same syft:

```
cargo build --release             .dep-v0 absent    ->  syft  1 package   1,208 bytes
cargo auditable build --release   .dep-v0 present   ->  syft 13 packages 22,554 bytes
                                  anstream anstyle anstyle-parse anstyle-query
                                  clap clap_builder clap_lex colorchoice
                                  is_terminal_polyfill strsim utf8parse … + sq
```

`cargo-auditable` 0.7.5, installed with `--locked`. **13 against 133 lockfile crates is
correct, not a second gap** — `cargo-auditable` records what is actually linked into the
binary, where `Cargo.lock` also carries dev-dependencies and unbuilt optional crates. Stated
because 13/133 invites being read as another shortfall.

The remedy is measured rather than proposed, deliberately: prescribing an unverified fix is
how the preceding four review rounds across two specs each produced their next defect.

### Re-scope

**Part 0, new, and it precedes everything:** eleven release workflows change
`cargo build --release` to `cargo auditable build --release`, and `cargo install
cargo-auditable --locked` is added to each. This is the change that makes any SBOM in this
repo worth producing, and it edits the same build step this spec was already going to touch —
for a different reason and with a different payload.

**Parts 1-3 keep their content but lose their billing.** The ordering defect is real and the
composite-action fix is still correct, but its stated purpose — making a meaningful SBOM
available atomically — was unearned. Atomic publication of an empty document is not worth
eleven job blocks. With Part 0 in place the purpose is earned and the ordering fix is worth
making; without it, this spec was a correct fix to a secondary problem.

**The verification bar moves accordingly.** Asserting the presence of `<binary>.sbom.spdx.json`
is what let this go unnoticed through three review rounds on the sibling spec and one on this
one. Part 3 must assert `jq '.packages | length' > 1` against the published asset and run a
real `cosign verify-blob --bundle`, and the bats mock-fidelity case must not pass on an empty
file.

### The durable lesson

Four review rounds across two specs, roughly 1.9M subagent tokens, debating how an artifact
gets delivered. **Not one lens asked what was in it.** Every question was about ordering,
triggering, channel, idempotency and state — the transport — because the spec framed the
subject as delivery and the reviews inherited that frame.

The check that settled it cost one `brew install` and four commands, needed no release, no
workflow run, and no code, and it was available on day one. It is the same shape as
`behavior.md`'s "the boundary can be wrong on the question, not the claim": every measurement
in both specs was correct and answered a question that could not decide anything, because the
population under review was the delivery mechanism rather than the payload.

**Before reviewing how a thing is delivered, open it.**

## Multi-Lens Review — Round 1

Reviewed at commit: `2cbed5c3984d6584fe45b8b8fcc34c02083770ee` (Step 7 self-review commit)

All three lenses were told the sibling spec's history and instructed to treat "I found the
root cause" skeptically, since a fourth attempt by the same author is where the same failure
recurs. All three findings were dispositioned **Addressed** by the operator on 2026-09-04.

Independently confirmed by this session rather than taken on report: the tag-before-release
ordering across all eleven workflows, the absence of any tag guard, `README.md:400-406`'s
verification command, `scripts.yml`'s `paths:` and `scripts/pre-push`'s pattern, and the
absence of `cargo-auditable` anywhere in the repo.

### Goal-Fit

Finding: the design guarantees the SBOM's **presence** and never its **content**. Four bats
cases assert files exist with syft and cosign mocked; the uniformity test greps YAML text;
Part 3's terminal assertion reads `.assets[].name`. Nothing — here or in
`release-sbom-monitor.yml` — asserts a non-empty package list or runs `cosign verify-blob`.
A syft run emitting valid SPDX with zero packages therefore yields four correctly-named
assets, a green suite, a literally-true atomic-publication claim, and a monitor that scans an
empty document and reports clean forever — the sibling spec's title, one level up.

Second: **the uniformity test never runs on the change class it exists to catch.**
`tests/test_release_workflows.py` executes only via `make test-python`, reached by
`scripts.yml` (`paths:` = `scripts/**`, `tests/**`, `Makefile`,
`.github/workflows/scripts.yml`) and by `scripts/pre-push`
(`^scripts/|^tests/|^Makefile$|^\.github/workflows/mutation-testing.*\.yml$`). A PR editing
only `.github/workflows/release-*.yml` matches neither, so the named mitigation for the top
fan-out risk is silent by construction — the exact property it was written to prevent.

Third: Part 1 is the simpler-path cut. Two of its three questions are answered identically by
Part 3, which runs regardless; the window measurement has no consumer and no durable home.

Assumption: that `syft <stripped rust binary> -o spdx-json` yields a non-empty package list.
Refutation condition stated as "0 or 1 makes the ordering question moot."

Disposition: **Addressed.** The assumption was measured and **refuted** — see "The syft probe"
above. Part 0 is added, Parts 1-3 are re-billed, the verification bar moves from filenames to
`packages | length > 1` plus a real `cosign verify-blob --bundle`, and
`.github/workflows/release-*` is added to both `scripts.yml`'s `paths:` and `scripts/pre-push`'s
pattern so the uniformity test runs on the change class it guards.

### Ergonomics

Finding: Part 1 is the only irreversible-cost step and no outcome of it can change the plan —
broken means delete `release-sign.yml`, working means delete it — while its cost is larger
than stated. `sq/sq-rs/CHANGELOG.md` does not exist (only root `CHANGELOG.md` is tracked), so
the run creates a new tracked 80-line file covering sq's entire history, pushes it to master,
and publishes that same text as the public release body of a throwaway release on a public
repo. Drop Part 1, keep Part 3, cut a baseline only if Part 3 fails.

Second: every one of roughly 17 verification cases expects PASS, and the uniformity test
would pass unchanged if `scripts/sbom-sign.sh` were `exit 0`, because all four of its
assertions read YAML text.

Assumption: that `softprops/action-gh-release` publishes atomically rather than creating a
published release and then uploading assets into it.

Disposition: **Addressed, and the assumption refuted in the design's favour.** Part 1 is
dropped. The assumption was settled by reading the action at its pinned SHA rather than by
inference: `src/github.ts:1058` is
`const draft = prerelease === true ? config.input_draft === true : true;` and
`finalizeRelease` calls `updateRelease({ draft: false })` — so it already creates as a draft,
uploads, then publishes. The atomicity claim holds on a stronger basis than the spec gave.

### Risk

Finding: the spec removes a visible degraded state and installs an invisible unrecoverable
one, and never names the trade. Measured across all eleven workflows: `Commit CHANGELOG`
(line 59 or 62) precedes `Create and push tag` (76 or 79) precedes `Create GitHub release`
(85 or 88), and `grep -l 'ls-remote\|push --delete\|--force'` over the eleven returns
nothing. So after the rewrite, a signing failure leaves the CHANGELOG commit already on
master under `continue-on-error: true`, the tag already on origin, and **no release at all** —
and a re-run hits `fatal: tag already exists`, making that version unshippable until someone
deletes the remote tag by hand. The monitor reads releases; "tag pushed, no release" is
invisible to it. `missing-asset` did not become impossible, it relocated to a state with zero
monitoring.

Second: `README.md:400-406` documents `cosign verify-blob` with
`--certificate-identity ".../release-sign.yml@refs/tags/factorial-vTAG"`. Deleting that
workflow replaces one identity with eleven, invalidating the only published verification
command.

Assumption: that `softprops/action-gh-release@v3` fails the step when a `files:` entry matches
nothing. If it warns and publishes, a path mismatch ships a partial release silently.

Disposition: **Addressed.** `Create and push tag` moves to after the composite step —
`softprops` creates the tag from `tag_name`, so nothing needs it earlier — leaving a signing
failure with the repo where it started. The README finding is accepted and **widened**: that
command also specifies `--signature factorial.sig --certificate factorial.pem`, the deprecated
cosign v3 form, while `release-sign.yml` writes `--bundle`. So it names two assets that have
never existed and is already broken today, independent of this change; `README.md` joins the
scope. The `files:`-miss assumption remains **unmeasured** and is carried into the plan as a
pre-implementation probe rather than assumed favourable.

### Adversarial Spec Review (comparison/judge designs only)

N/A — no comparison arms, no judge component; acceptance criteria are exit codes, package
counts, and API reads.

### Independent architectural review

The operator circulated the spec to a separate reviewer. Three findings, all accepted:

1. **`completed_at` is job-level, not step-level** — it answers publication-to-job-completion
   rather than publication-to-asset-presence. Correct, and **moot**: Part 1 is dropped, and
   `softprops`'s draft-then-finalize behaviour makes the current window plainly job-scale, so
   measuring it precisely buys nothing.
2. **"All four artifacts" is a number established nowhere.** Deriving the expected set from
   the composite's outputs or from `sbom-sign.sh`'s filenames is circular. The plan hardcodes
   the set **with a comment naming what invalidates it** — a fifth artifact added to eleven
   workflows leaves the test green while asserting an incomplete set.
3. **The draft-alternative rejection rests on a "may".** The `GET /releases/tags/{tag}` 404
   claim was inferred, not measured, in a document careful about that distinction elsewhere.
   Recorded as unmeasured; settling it requires creating a draft release, and the rejection
   stands on the stuck-draft failure class regardless.
