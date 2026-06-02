# ADR 0010: Release workflow alignment with etch-cli strategy

- **Date:** 2026-05-23
- **Status:** Accepted

## Context

The math repo has 11 Rust crates, each with a `release-<name>-rs.yml` workflow triggered by `workflow_dispatch` with a `version` input (no `v` prefix). Before PR #72, release notes were generated with inline `git log` commands using a randomized `GITHUB_OUTPUT` delimiter pattern. This approach had several problems:

1. **No persistent CHANGELOG** — release notes existed only in the GitHub release body; no `CHANGELOG.md` was committed to the repo
2. **No SHA256 checksum** — binary artifacts had no integrity verification
3. **Cosign signing was broken** — `release-sign.yml` used the old `--output-signature`/`--output-certificate` flags, which are deprecated in cosign v4 (now uses `--bundle` format); the `.sig`/`.pem` pair was never actually produced
4. **Inconsistency with etch-cli** — etch-cli already used `git-cliff` for changelog generation; math was using a bespoke approach

## Decision

Align all 12 math release workflows with the etch-cli release strategy:

1. **Replace `git log` release notes with `git-cliff`** — two steps per release workflow:
   - Generate full `CHANGELOG.md` and commit it to master (using `orhun/git-cliff-action@v4`, pinned to a specific SHA)
   - Generate latest-only release notes (stripped header/footer) for the GitHub release body
   - Use `--include-path "<project>/**"` and `--tag-pattern "<project>-v.*"` so each workflow only sees its own history and tags

2. **Add SHA256 checksum** — `sha256sum` of the release binary, committed alongside the binary in the GitHub release

3. **Fix `release-sign.yml`** — update cosign to `sigstore/cosign-installer@v4.1.2` (pinned; floating `@v4` does not exist) and switch to `--bundle` format:

   ```bash
   cosign sign-blob --yes "${BINARY}" --bundle "${BINARY}.bundle"
   ```

4. **Single `cliff.toml` at repo root** — each workflow references it with `config: cliff.toml` and uses `--include-path` to scope to its sub-project

## Consequences

- Every release now produces a committed `CHANGELOG.md` in the crate directory, a SHA256 `.sha256` file, and a cosign `.bundle` file in the GitHub release assets
- `git-cliff` requires the `cliff.toml` config to exist at repo root — all workflows reference `config: cliff.toml`
- `--tag-pattern` scoping is essential: without it, `git-cliff` includes commits from all sub-projects in each crate's changelog
- Cosign pinning: `sigstore/cosign-installer@v4.1.2` (not `@v4` — the floating major tag does not exist for cosign-installer)
- `continue-on-error: true` on the `Commit CHANGELOG` step handles the no-op case (no changelog changes since last release)

## Related

- ADR 0006: Per-project CI workflows with test-before-build gate
- Memory: `project_cliff_toml_location.md` — single cliff.toml at repo root
- PR #72: `ci: align math release workflows with etch-cli strategy`
- ci.md standard: cosign keyless signing (sigstore) section
