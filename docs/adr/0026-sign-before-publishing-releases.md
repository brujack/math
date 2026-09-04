# ADR-0026: Sign before publishing releases, via a composite action

**Status:** Accepted
**Date:** 2026-09-04

## Context

Release signing ran as a reusable workflow, `release-sign.yml`, called by each of the
eleven `release-<name>-rs.yml` files:

```yaml
  release:
    ...
    - name: Create and push tag
    - name: Create GitHub release      # softprops/action-gh-release  <- PUBLISHED HERE
  sign:
    needs: [release]                   # so the release must already exist
    uses: ./.github/workflows/release-sign.yml
```

A reusable workflow runs as its own job with its own filesystem, so it had to fetch the
binary back out of the release it was signing:

```yaml
  - name: Download binary from release
    run: gh release download "${RELEASE_TAG}" --pattern "${BINARY_NAME}"
  ...
  - name: Upload signatures and SBOM to release   # <- SBOM ATTACHED HERE, last step
```

That download is the only reason the release had to exist first. Between publication and
the final upload there was a published release carrying a binary and no SBOM.

Three separate attempts to detect that window from outside each failed, and each failure
was a defect of the same magnitude as the one it fixed:

| attempt                                                  | why it failed                                                                                                                                                                                                                                                                       |
| -------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `on: release: types: [published]` trigger on the monitor | Inert — all eleven publish via `softprops/action-gh-release` with the default `GITHUB_TOKEN`, and GitHub does not start workflow runs from `GITHUB_TOKEN` events. Had it fired, it would have fired _inside_ the window and reported a false missing-asset on every healthy release |
| the same trigger plus an issue-filing channel            | Same trigger, so every healthy release would have filed a spurious issue                                                                                                                                                                                                            |
| a `needs: [sign]` monitoring job                         | `sign` success implies the asset exists, and `sign` failure **skips** the job — so the only reachable verdict was `ready`, and the state it was added to detect became unreachable on that path                                                                                     |

A fourth consideration settled it: a signing failure after the tag push leaves the tag on
origin with no release, and no workflow guards a pre-existing tag, so a re-run dies on
`fatal: tag already exists` and that version is unshippable. "Tag pushed, no release" is
also invisible to the SBOM monitor, which reads releases.

Separately, the artifact being published was empty. Measured 2026-09-04 on both Mach-O
arm64 and ELF x86-64, syft 1.51.1:

```
cargo build --release             .dep-v0 absent    ->  syft  1 package   1,208 bytes
cargo auditable build --release   .dep-v0 present   ->  syft 13 packages 22,554 bytes
```

The single package is the binary itself, against a 133-crate lockfile. `grype` scanning
that SBOM can never find a CVE, so every mechanism built to deliver it promptly was
delivering nothing.

## Decision

**Sign before publishing, in the release job, via a composite action.**

`.github/actions/sbom-sign` is a composite action, so it runs in the caller's job where
the freshly built binary is already on disk. No download, no second job, no ordering
constraint. The release is then created once with all four assets:

```yaml
- uses: ./.github/actions/sbom-sign
  with: { binary_path: sq/sq-rs/target/release, binary_name: sq }
- name: Create and push tag
- name: Create GitHub release
  with:
    files: |
      .../sq
      .../sq.sha256
      .../sq.sbom.spdx.json
      .../sq.bundle
    fail_on_unmatched_files: true
```

Four supporting decisions:

- **`cargo auditable build --release`** replaces `cargo build --release`, with
  `cargo-auditable` pinned to `--version 0.7.5`. It generates the provenance data the SBOM
  is derived from, so an unpinned install would let that tool change between releases.
- **`fail_on_unmatched_files: true`** on every `softprops` call. Read from the action's own
  `action.yml` at the pinned SHA: the input has no default and its description reads
  "Defaults to false", so `run.ts` takes a `console.warn` branch and publishes a release
  with missing assets. Without this input the guarantee is nominal.
- **`Create and push tag` moves after the signing step.** A signing failure then leaves the
  repository as it was, rather than stranding a tag.
- **`release-sign.yml` is deleted.** Its reusable-workflow shape is what forced the
  download that created the window; keeping it as a wrapper would preserve the cause.

## Consequences

**Published implies SBOM present, by construction.** `softprops/action-gh-release` creates
the release as a draft, uploads assets, then flips it — verified by reading `src/run.ts`
and `src/github.ts` at the pinned SHA rather than inferred. Combined with signing before
publication, there is no interval in which a published release lacks its SBOM.

**The SBOM monitor's scope collapses.** `missing-asset` on the release path is not merely
skipped but impossible; it survives only as a monthly-sweep signal for out-of-band causes —
a hand-cut release, or a deleted asset. The apparatus designed for it across three review
rounds (a three-valued state machine, a labelled issue channel, a title invariant) is
superseded. See
`docs/superpowers/specs/2026-09-02-sbom-false-pass-and-dead-ruleset-design.md`.

**Availability is traded for integrity, deliberately.** Previously a signing failure left a
complete-but-unsigned release. Now it blocks the release entirely. That is the intended
direction — an unsigned release that looks complete is worse than an absent one — but it is
a real behaviour change and is recorded here rather than discovered later.

**A composite action cannot declare its own `permissions`.** It inherits the job's. All
eleven workflows carry `contents: write` and `id-token: write` at workflow level with no
job-level override, so keyless cosign has OIDC. This is the constraint to revisit if
signing ever needs a narrower scope than the release job's.

**The certificate identity changes.** Keyless cosign's SAN names the workflow that
requested the token. A reusable workflow had its own ref; a composite action does not, so
the identity becomes `release-<name>-rs.yml@refs/heads/master` — the calling workflow, at
the branch the dispatch ran from, not the release tag. `README.md` is updated accordingly,
and notes that the identity is derived rather than observed, because no release has been
cut with this pipeline.

**Eleven files must stay in sync by hand.** `tests/test_release_workflows.py` pins the
contract structurally — parsing each workflow rather than matching text — and
`.github/workflows/release-*` was added to `scripts.yml`'s `paths:` and the pre-push
pattern so that test runs on the change class it guards.

**Unverified until a release is cut.** Nothing in this repo has ever run these workflows:
zero runs across all twelve release files. Whether keyless cosign works inside a composite
action's job context, and whether `softprops` accepts four files, cannot be established by
any test here. The first per-binary release is the verification step, and this is stated
rather than implied.

## Related

- ADR-0010 — release workflow alignment with etch-cli strategy
- ADR-0006 — per-project CI workflows with test gate
- `docs/superpowers/specs/2026-09-04-release-ordering-atomic-publication-design.md`
- `docs/superpowers/plans/2026-09-04-release-ordering-atomic-publication.md`
- `docs/superpowers/specs/2026-09-02-sbom-false-pass-and-dead-ruleset-design.md` — the
  three review rounds that located this ordering as the shared cause
- `~/.claude/standards/ci.md` — cosign v4 `--bundle` semantics, action SHA pinning
