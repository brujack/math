# Release SBOM Vulnerability Monitor Implementation Plan

> **Status: DONE** — merged via PR #88 (2026-07-16). Post-merge verification: manual workflow_dispatch on master succeeded, all 11 sub-project jobs green, 0 issues opened.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Monthly scheduled workflow that re-scans each of the 11 sub-projects' latest
published release SBOM against current CVE feeds and opens a deduplicated GitHub issue for
any Critical/High finding — same pattern as etch-cli's `release-sbom-monitor.yml`, fanned
out across all sub-projects.

**Architecture:** Reusable workflow (`release-sbom-monitor.yml`, `workflow_call` +
`workflow_dispatch`) does the scan for one binary — content identical to etch-cli's version
of the same file (this is a per-repo copy, not a cross-repo `uses:` reference, matching how
`release-sign.yml` is already duplicated per repo rather than shared). A single scheduling
caller (`release-sbom-monitor-schedule.yml`) has one job per sub-project, each calling the
reusable workflow with that sub-project's `binary_name` and `release_tag_pattern`.

**Tech Stack:** GitHub Actions, `gh` CLI, `jq`, `anchore/scan-action@v7`.

## Global Constraints

- Full design: `ai-config` `docs/superpowers/specs/2026-07-16-release-sbom-vuln-monitoring-design.md`
- Cross-cutting decision record: `dotfiles` ADR-0015
- Sub-projects in scope (11, one job each): `amicable`, `collatz`, `e`, `factorial`, `fib`,
  `goldbach`, `perfect-numbers`, `pi`, `prime`, `sq`, `twin-primes`. Confirmed exact
  `binary_name`/tag-prefix pairs from each `release-<name>-rs.yml`'s call into
  `release-sign.yml`: tag is always `<name>-v<version>`, `binary_name` is always `<name>`
  (e.g. `perfect-numbers-v1.2.0` / `perfect-numbers`).
- Only the **latest** release per sub-project matching its tag pattern is scanned.
- Severity gate for issue creation: **Critical + High only**.
- Missing SBOM asset on a sub-project's latest release → skip gracefully (`exit 0`).
- Dedup: search open issues labeled `sbom-monitor` with CVE ID + binary name in the title
  before creating a new one.
- Non-blocking, informational only — no PR gate, no `fail-build`.

---

## Verification Planning

Per `behavior.md`, session-level verification (above the per-task acceptance gates below):

- **Command:** after this branch is pushed and the PR is open, manually trigger the
  scheduled workflow against the branch:
  ```bash
  gh workflow run release-sbom-monitor-schedule.yml --ref <branch-name>
  sleep 5
  RUN_ID=$(gh run list --workflow=release-sbom-monitor-schedule.yml --branch <branch-name> \
    --limit 1 --json databaseId --jq '.[0].databaseId')
  gh run watch "${RUN_ID}" --exit-status
  ```
- **Expected output:** run concludes `success` across all 11 fanned-out jobs. Given math's
  current dependency sets have no known Critical/High CVEs (per existing `cargo-audit.yml`),
  expect **zero** issues created — confirms tag resolution, SBOM download, scan, and dedup
  query all work correctly for every sub-project's naming pattern.
- **Edge case to exercise:** confirm the 11 jobs actually run with distinct `binary_name`/
  `release_tag_pattern` pairs (not all resolving to the same sub-project by accident) —
  check the run's job list shows 11 distinct job names, each downloading a different SBOM
  filename (visible in each job's step log).
- This verification happens after push (workflow_dispatch --ref needs the workflow file on
  that ref remotely), as part of the normal PR/CI-monitoring flow — not a per-task gate.

---

## Task 1: `sbom-monitor` label + reusable `release-sbom-monitor.yml` workflow

```yaml-task
id: 1
description: Create sbom-monitor GitHub label and reusable release-sbom-monitor.yml workflow (resolve latest release, download SBOM, scan via anchore/scan-action, dedup + file issue on Critical/High)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'python3 -c "import yaml, sys; yaml.safe_load(open(sys.argv[1]))" .github/workflows/release-sbom-monitor.yml'
    exit_code: 0
  - cmd: 'yamllint -d relaxed .github/workflows/release-sbom-monitor.yml'
    exit_code: 0
  - cmd: 'gh label list --json name --jq ".[].name" | grep -qx sbom-monitor'
    exit_code: 0
max_retries: 3
files_touched:
  - .github/workflows/release-sbom-monitor.yml
depends_on: []
```

**Files:**

1. Create the label (idempotent, one-time repo setup):

   ```bash
   gh label create sbom-monitor --color B60205 \
     --description "Opened by the monthly release SBOM vulnerability monitor" \
     || gh label list --json name --jq '.[].name' | grep -qx sbom-monitor
   ```

2. Create `.github/workflows/release-sbom-monitor.yml` — **identical content to etch-cli's
   file of the same name** (see etch-cli `docs/superpowers/plans/2026-07-16-release-sbom-monitor.md`
   Task 1 for the byte-for-byte source; reproduced here so this task is self-contained):

   ```yaml
   name: Release SBOM Monitor

   on:
     workflow_call:
       inputs:
         binary_name:
           required: true
           type: string
         release_tag_pattern:
           required: true
           type: string
     workflow_dispatch:
       inputs:
         binary_name:
           required: true
           type: string
           description: "Binary name (e.g. factorial)"
         release_tag_pattern:
           required: true
           type: string
           description: "Tag prefix to match latest release (e.g. factorial-v)"

   env:
     FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"

   jobs:
     monitor:
       name: SBOM Vulnerability Scan
       runs-on: ubuntu-latest
       permissions:
         contents: read
         issues: write
       steps:
         - uses: actions/checkout@v6

         - name: Resolve latest matching release tag
           id: latest
           env:
             GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
             TAG_PATTERN: ${{ inputs.release_tag_pattern }}
           run: |
             LATEST_TAG=$(gh release list --limit 50 --json tagName \
               --jq ".[] | select(.tagName | startswith(\"${TAG_PATTERN}\")) | .tagName" \
               | head -1)
             if [[ -z "${LATEST_TAG}" ]]; then
               echo "No matching release found for pattern ${TAG_PATTERN} — skipping"
               echo "found=false" >> "$GITHUB_OUTPUT"
               exit 0
             fi
             echo "found=true" >> "$GITHUB_OUTPUT"
             echo "tag=${LATEST_TAG}" >> "$GITHUB_OUTPUT"

         - name: Download SBOM asset
           if: steps.latest.outputs.found == 'true'
           id: sbom
           env:
             GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
             LATEST_TAG: ${{ steps.latest.outputs.tag }}
             BINARY_NAME: ${{ inputs.binary_name }}
           run: |
             if gh release download "${LATEST_TAG}" \
                 --pattern "${BINARY_NAME}.sbom.spdx.json" 2>/dev/null; then
               echo "present=true" >> "$GITHUB_OUTPUT"
             else
               echo "No SBOM asset on ${LATEST_TAG} — pre-dates SBOM rollout, skipping"
               echo "present=false" >> "$GITHUB_OUTPUT"
             fi

         - name: Scan SBOM
           if: steps.latest.outputs.found == 'true' && steps.sbom.outputs.present == 'true'
           id: scan
           uses: anchore/scan-action@v7
           with:
             sbom: "${{ inputs.binary_name }}.sbom.spdx.json"
             output-format: json
             fail-build: false

         - name: Filter Critical/High and file issues
           if: steps.latest.outputs.found == 'true' && steps.sbom.outputs.present == 'true'
           env:
             GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
             BINARY_NAME: ${{ inputs.binary_name }}
             LATEST_TAG: ${{ steps.latest.outputs.tag }}
             SCAN_JSON: ${{ steps.scan.outputs.json }}
           run: |
             jq -c '.matches[] | select(.vulnerability.severity == "Critical" or .vulnerability.severity == "High")' \
               "${SCAN_JSON}" | while read -r finding; do
               CVE_ID=$(echo "${finding}" | jq -r '.vulnerability.id')
               SEVERITY=$(echo "${finding}" | jq -r '.vulnerability.severity')
               PACKAGE_NAME=$(echo "${finding}" | jq -r '.artifact.name')
               PACKAGE_VERSION=$(echo "${finding}" | jq -r '.artifact.version')
               FIX_VERSION=$(echo "${finding}" | jq -r '.vulnerability.fix.versions[0] // "none"')

               EXISTING=$(gh issue list --label sbom-monitor --state open \
                 --search "in:title \"${CVE_ID}\" \"${BINARY_NAME}\"" \
                 --json number --jq '.[0].number // empty')

               if [[ -n "${EXISTING}" ]]; then
                 echo "Issue already open for ${CVE_ID} in ${BINARY_NAME}: #${EXISTING}"
                 continue
               fi

               gh issue create \
                 --label sbom-monitor \
                 --title "[SBOM Monitor] ${CVE_ID} in ${BINARY_NAME} ${LATEST_TAG}" \
                 --body "Severity: ${SEVERITY}
   Package: ${PACKAGE_NAME} ${PACKAGE_VERSION}
   Fix available: ${FIX_VERSION}
   Release: ${LATEST_TAG}
   Source: monthly release-sbom-monitor.yml scan

   Non-blocking. Human judgment call on whether this warrants a patch release
   (reachability, exploitability, whether ${LATEST_TAG} is still actively downloaded)."
             done
   ```

**Interfaces:**

- Consumes: nothing from earlier tasks (first task in this plan).
- Produces: reusable workflow `release-sbom-monitor.yml` callable via
  `uses: ./.github/workflows/release-sbom-monitor.yml` with inputs `binary_name` (string)
  and `release_tag_pattern` (string). Task 2 calls it 11 times.

---

## Task 2: Scheduled caller `release-sbom-monitor-schedule.yml` (11 sub-project jobs)

```yaml-task
id: 2
description: Create monthly scheduled workflow with one job per sub-project (11 total), each calling release-sbom-monitor.yml with that sub-project's binary_name/release_tag_pattern
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'python3 -c "import yaml, sys; yaml.safe_load(open(sys.argv[1]))" .github/workflows/release-sbom-monitor-schedule.yml'
    exit_code: 0
  - cmd: 'yamllint -d relaxed .github/workflows/release-sbom-monitor-schedule.yml'
    exit_code: 0
  - cmd: 'python3 -c "import yaml; d = yaml.safe_load(open(\".github/workflows/release-sbom-monitor-schedule.yml\")); assert len(d[\"jobs\"]) == 11, len(d[\"jobs\"])"'
    exit_code: 0
max_retries: 3
files_touched:
  - .github/workflows/release-sbom-monitor-schedule.yml
depends_on: [1]
```

**Files:**

Create `.github/workflows/release-sbom-monitor-schedule.yml`:

```yaml
name: Release SBOM Monitor (scheduled)

on:
  schedule:
    - cron: "0 13 3 * *"
  workflow_dispatch:

jobs:
  amicable:
    uses: ./.github/workflows/release-sbom-monitor.yml
    with:
      binary_name: amicable
      release_tag_pattern: "amicable-v"
    permissions:
      contents: read
      issues: write
  collatz:
    uses: ./.github/workflows/release-sbom-monitor.yml
    with:
      binary_name: collatz
      release_tag_pattern: "collatz-v"
    permissions:
      contents: read
      issues: write
  e:
    uses: ./.github/workflows/release-sbom-monitor.yml
    with:
      binary_name: e
      release_tag_pattern: "e-v"
    permissions:
      contents: read
      issues: write
  factorial:
    uses: ./.github/workflows/release-sbom-monitor.yml
    with:
      binary_name: factorial
      release_tag_pattern: "factorial-v"
    permissions:
      contents: read
      issues: write
  fib:
    uses: ./.github/workflows/release-sbom-monitor.yml
    with:
      binary_name: fib
      release_tag_pattern: "fib-v"
    permissions:
      contents: read
      issues: write
  goldbach:
    uses: ./.github/workflows/release-sbom-monitor.yml
    with:
      binary_name: goldbach
      release_tag_pattern: "goldbach-v"
    permissions:
      contents: read
      issues: write
  perfect-numbers:
    uses: ./.github/workflows/release-sbom-monitor.yml
    with:
      binary_name: perfect-numbers
      release_tag_pattern: "perfect-numbers-v"
    permissions:
      contents: read
      issues: write
  pi:
    uses: ./.github/workflows/release-sbom-monitor.yml
    with:
      binary_name: pi
      release_tag_pattern: "pi-v"
    permissions:
      contents: read
      issues: write
  prime:
    uses: ./.github/workflows/release-sbom-monitor.yml
    with:
      binary_name: prime
      release_tag_pattern: "prime-v"
    permissions:
      contents: read
      issues: write
  sq:
    uses: ./.github/workflows/release-sbom-monitor.yml
    with:
      binary_name: sq
      release_tag_pattern: "sq-v"
    permissions:
      contents: read
      issues: write
  twin-primes:
    uses: ./.github/workflows/release-sbom-monitor.yml
    with:
      binary_name: twin-primes
      release_tag_pattern: "twin-primes-v"
    permissions:
      contents: read
      issues: write
```

**Interfaces:**

- Consumes: Task 1's `release-sbom-monitor.yml` reusable workflow (`binary_name`,
  `release_tag_pattern` inputs) — called 11 times, once per sub-project.
- Produces: nothing consumed by further tasks — this is the last task in this plan.

---

## Self-Review

1. **Spec coverage:** design spec's math scope (11 sub-projects, one reusable workflow,
   one fanned-out caller, grype scan, dedup, Critical/High gate, graceful skip) — all
   covered across Task 1 (scan logic) and Task 2 (11-job schedule). ✓
2. **Placeholder scan:** none — both workflow files are complete; all 11 jobs fully
   written out (no "repeat for remaining sub-projects" shorthand).
3. **Type consistency:** `binary_name`/`release_tag_pattern` values verified against each
   sub-project's actual `release-<name>-rs.yml` → `release-sign.yml` call (see Global
   Constraints) — not guessed.
4. **YAML block:** both tasks have `yaml-task` fences; run `make validate-plan` (ai-config)
   before dispatch.
5. **TDD `files_touched`:** N/A — both tasks are `tdd: not-applicable` (CI YAML, no test
   harness for GH Actions logic in this repo; math has no root Makefile/lint target
   covering workflow files either).
6. **Token-budget check:** Task 2's block is large because 11 jobs are structurally
   near-identical but each needs its own literal `binary_name`/`release_tag_pattern` —
   collapsing to a matrix `strategy:` was considered and rejected: reusable-workflow calls
   (`uses:` at job level) don't support `strategy: matrix` (GitHub Actions limitation — jobs
   that call a reusable workflow can't also declare a matrix), so one job per sub-project is
   the only way to keep each call fully static and inspectable at a glance.
7. **ADR-significance check:** yes — covered by `dotfiles` ADR-0015 (cross-cutting, shared
   with etch-cli), not duplicated here as a repo-specific ADR.
