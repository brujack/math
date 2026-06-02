# ADR 0014: SBOM generation and cosign keyless signing for releases

- **Date:** 2026-05-20
- **Status:** Accepted

## Context

Binary releases without provenance create supply-chain risk. A consumer downloading a release binary has no way to verify it was built from the claimed source by the claimed CI workflow, and no inventory of its transitive dependencies.

SBOM (Software Bill of Materials) documents the dependency graph. Cosign keyless signing attaches cryptographic provenance via the Sigstore transparency log — linking the binary to the specific GitHub Actions workflow run that produced it, without requiring the repo to manage signing keys.

## Decision

Add two steps to every release workflow:

**1. SBOM generation**

`anchore/sbom-action` generates a CycloneDX SBOM and uploads it as a release artifact alongside the binary.

**2. Cosign keyless signing**

`sigstore/cosign-installer` pinned to a specific tag (e.g. `v4.1.2`) — NOT a floating major tag. `@v4` does not exist and fails with "unable to find version". Unlike `actions/checkout`, cosign-installer does not maintain floating major version tags.

Sign command (cosign v4 format):

```bash
cosign sign-blob --yes "${BINARY_NAME}" \
  --bundle "${BINARY_NAME}.bundle"
```

The `.bundle` file replaces the old `.sig` + `.pem` pair. cosign v4 uses `--bundle` by default (`--new-bundle-format` is now the default). The old `--output-signature`/`--output-certificate` flags are deprecated and silently ignored.

**Verification:**

```bash
cosign verify-blob "${BINARY_NAME}" \
  --bundle "${BINARY_NAME}.bundle" \
  --certificate-identity "<workflow-ref>" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"
```

**Re-run note:** `gh run rerun --failed` uses the original workflow SHA. A fix pushed to main after a failed run does NOT apply to the re-run. Trigger a fresh run via `gh workflow run` to pick up fixes.

## Consequences

- Every release has a CycloneDX SBOM and a cosign bundle as release artifacts
- Consumers can verify binary provenance with cosign CLI — no key management required
- cosign-installer must be pinned to a specific tag per release (check for newer tags when creating new release workflows)
- `.bundle` format is cosign v4 and later — update verification instructions in README accordingly
- SBOM covers direct and transitive Rust dependencies as resolved at build time

## Related

- ADR 0010: Release workflow alignment with etch-cli strategy
- ADR 0006: Per-project CI workflows with test-before-build gate
- `.claude/standards/ci.md`: cosign keyless signing notes and `--bundle` flag guidance
