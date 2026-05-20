> **Status: DONE**

# SBOM + Cosign Signing — math Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add keyless cosign signing and syft SBOM generation to all 7 math release workflows via a shared `release-sign.yml` reusable workflow.

**Architecture:** Copy `release-sign.yml` from etch-cli (identical content — same reusable workflow pattern). Add a `sign` job to each of the 7 sub-project release workflows. Each release gains `.sig`, `.pem`, `.sbom.spdx.json` as extra assets. Add verification instructions to README.

**Tech Stack:** `sigstore/cosign-installer@v3`, `anchore/sbom-action/download-syft@v0`, `gh release download/upload`, `actions/checkout@v5`

**Prerequisite:** etch-cli Plan 2 (release-sign.yml) should be complete first so the pattern is proven. Math `release-sign.yml` is an identical copy.

---

## Files

- **Create:** `.github/workflows/release-sign.yml`
- **Modify:** `.github/workflows/release-factorial-rs.yml`
- **Modify:** `.github/workflows/release-fib-rs.yml`
- **Modify:** `.github/workflows/release-pi-rs.yml`
- **Modify:** `.github/workflows/release-e-rs.yml`
- **Modify:** `.github/workflows/release-sq-rs.yml`
- **Modify:** `.github/workflows/release-prime-rs.yml`
- **Modify:** `.github/workflows/release-twin-primes-rs.yml`
- **Modify:** `README.md` — add "Verifying releases" section
- **Modify:** `docs/superpowers/README.md` — **post-merge on main only**

---

## Task 1: Create release-sign.yml (identical to etch-cli)

**Files:**

- Create: `.github/workflows/release-sign.yml`

- [ ] **Step 1: Create `.github/workflows/release-sign.yml`**

Identical content to etch-cli's `release-sign.yml`:

```yaml
name: Release Sign

on:
  workflow_call:
    inputs:
      release_tag:
        required: true
        type: string
      binary_name:
        required: true
        type: string

jobs:
  sign:
    name: SBOM + Sign
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: write
    steps:
      - uses: actions/checkout@v5

      - name: Download binary from release
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh release download "${{ inputs.release_tag }}" \
            --pattern "${{ inputs.binary_name }}"

      - name: Install syft
        uses: anchore/sbom-action/download-syft@v0

      - name: Generate SBOM
        run: |
          syft "${{ inputs.binary_name }}" \
            -o spdx-json \
            --file "${{ inputs.binary_name }}.sbom.spdx.json"

      - name: Install cosign
        uses: sigstore/cosign-installer@v3

      - name: Sign binary (keyless)
        run: |
          cosign sign-blob --yes "${{ inputs.binary_name }}" \
            --output-signature "${{ inputs.binary_name }}.sig" \
            --output-certificate "${{ inputs.binary_name }}.pem"

      - name: Upload signatures and SBOM to release
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          gh release upload "${{ inputs.release_tag }}" \
            "${{ inputs.binary_name }}.sig" \
            "${{ inputs.binary_name }}.pem" \
            "${{ inputs.binary_name }}.sbom.spdx.json"
```

- [ ] **Step 2: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-sign.yml'))" && echo "valid"
```

Expected: `valid`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release-sign.yml
git commit -m "ci: add reusable release-sign workflow (SBOM + cosign)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Add sign job to all 7 release workflows

**Files:**

- Modify: `.github/workflows/release-factorial-rs.yml`
- Modify: `.github/workflows/release-fib-rs.yml`
- Modify: `.github/workflows/release-pi-rs.yml`
- Modify: `.github/workflows/release-e-rs.yml`
- Modify: `.github/workflows/release-sq-rs.yml`
- Modify: `.github/workflows/release-prime-rs.yml`
- Modify: `.github/workflows/release-twin-primes-rs.yml`

Each workflow currently has `permissions: contents: write` at the top level and a single `release` job. Two changes per file:

1. Add `id-token: write` to the top-level `permissions` block
2. Append a `sign` job after the `release` job

**Pattern to apply (repeat for each workflow, substituting `SUBPROJECT`):**

For `release-{SUBPROJECT}-rs.yml`:

- `release_tag`: `"{SUBPROJECT}-v${{ inputs.version }}"`
- `binary_name`: `"{SUBPROJECT}"`

Sub-project → binary name mapping:
| Workflow file | SUBPROJECT value |
|---|---|
| `release-factorial-rs.yml` | `factorial` |
| `release-fib-rs.yml` | `fib` |
| `release-pi-rs.yml` | `pi` |
| `release-e-rs.yml` | `e` |
| `release-sq-rs.yml` | `sq` |
| `release-prime-rs.yml` | `prime` |
| `release-twin-primes-rs.yml` | `twin-primes` |

> **Note:** Rust converts hyphens to underscores in binary names. For `twin-primes`, verify the actual binary filename by checking the `files:` field in `release-twin-primes-rs.yml` — it may be `twin_primes` not `twin-primes`. Use whatever name is in the `files:` field as the `binary_name` input.

**For each workflow file, make these two edits:**

**Edit 1** — change `permissions` block from:

```yaml
permissions:
  contents: write
```

to:

```yaml
permissions:
  contents: write
  id-token: write
```

**Edit 2** — append after the closing of the `release` job (at the same `jobs:` indentation level):

```yaml
sign:
  needs: [release]
  uses: ./.github/workflows/release-sign.yml
  with:
    release_tag: "{SUBPROJECT}-v${{ inputs.version }}"
    binary_name: "{SUBPROJECT}"
  permissions:
    id-token: write
    contents: write
```

- [ ] **Step 1: Edit release-factorial-rs.yml**

Apply both edits with `SUBPROJECT = factorial`. Validate:

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-factorial-rs.yml'))" && echo "valid"
```

- [ ] **Step 2: Edit release-fib-rs.yml**

Apply both edits with `SUBPROJECT = fib`. Validate YAML.

- [ ] **Step 3: Edit release-pi-rs.yml**

Apply both edits with `SUBPROJECT = pi`. Validate YAML.

- [ ] **Step 4: Edit release-e-rs.yml**

Apply both edits with `SUBPROJECT = e`. Validate YAML.

- [ ] **Step 5: Edit release-sq-rs.yml**

Apply both edits with `SUBPROJECT = sq`. Validate YAML.

- [ ] **Step 6: Edit release-prime-rs.yml**

Apply both edits with `SUBPROJECT = prime`. Validate YAML.

- [ ] **Step 7: Edit release-twin-primes-rs.yml**

Apply both edits with `SUBPROJECT = twin-primes`. Validate YAML.

- [ ] **Step 8: Confirm all 7 workflows have sign job**

```bash
for f in .github/workflows/release-*-rs.yml; do
  jobs=$(python3 -c "import yaml; print(list(yaml.safe_load(open('${f}'))['jobs'].keys()))")
  printf "%s: %s\n" "${f}" "${jobs}"
done
```

Expected: each file shows `['release', 'sign']`

- [ ] **Step 9: Commit**

```bash
git add .github/workflows/release-factorial-rs.yml \
        .github/workflows/release-fib-rs.yml \
        .github/workflows/release-pi-rs.yml \
        .github/workflows/release-e-rs.yml \
        .github/workflows/release-sq-rs.yml \
        .github/workflows/release-prime-rs.yml \
        .github/workflows/release-twin-primes-rs.yml
git commit -m "ci: add sign job to all math release workflows

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Add verification docs to README

**Files:**

- Modify: `README.md`

- [ ] **Step 1: Find insertion point**

```bash
grep -n "^## " README.md | tail -5
```

Insert the verification section near the end of the README.

- [ ] **Step 2: Add "Verifying releases" section**

````markdown
## Verifying releases

Release binaries are signed with [cosign](https://docs.sigstore.dev/cosign/overview/) using keyless Sigstore signing. Each release includes the binary plus:

- `{name}.sig` — detached signature
- `{name}.pem` — signing certificate
- `{name}.sbom.spdx.json` — SPDX bill of materials

To verify a release binary (example for `factorial`):

```bash
cosign verify-blob factorial \
  --signature factorial.sig \
  --certificate factorial.pem \
  --certificate-identity \
    "https://github.com/brujack/math/.github/workflows/release-sign.yml@refs/tags/factorial-vTAG" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"
```
````

Replace `factorial` and `factorial-vTAG` with the sub-project name and tag (e.g. `fib`, `fib-v1.0.0`).

````

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add release verification instructions

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
````

---

## Task 4: Post-merge docs update

> **Do this directly on main after the PR merges — not inside the worktree.**

- [ ] **Step 1: Update plan index**

In `docs/superpowers/README.md`, update the math sbom-cosign row: add plan link, set status to Done.

- [ ] **Step 2: Add Done banner**

Add `> **Status: DONE**` at the top of `docs/superpowers/plans/2026-05-20-sbom-cosign.md`.

- [ ] **Step 3: Commit on main**

```bash
git add docs/superpowers/README.md docs/superpowers/plans/2026-05-20-sbom-cosign.md
git commit -m "docs: mark math sbom-cosign plan done

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push
```
