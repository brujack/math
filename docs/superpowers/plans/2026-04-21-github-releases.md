# GitHub Releases Implementation Plan

> **Status: DONE**

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `workflow_dispatch`-triggered GitHub release workflow for each of the five Rust projects, producing a tagged GitHub release with a built binary and auto-generated release notes.

**Architecture:** One workflow file per Rust project (`.github/workflows/release-<project>.yml`). Each workflow accepts a version number as input, runs tests, builds the release binary, auto-generates notes from git history, pushes a tag, and publishes a GitHub release with the binary attached.

**Tech Stack:** GitHub Actions, `softprops/action-gh-release@v2`, `dtolnay/rust-toolchain@stable`, `Swatinem/rust-cache@v2`, `actions/checkout@v5`

---

## File Structure

| File                                           | Action | Purpose                                             |
| ---------------------------------------------- | ------ | --------------------------------------------------- |
| `.github/workflows/release-pi-rs.yml`          | Create | Release workflow for pi-rs (needs GMP + MPFR)       |
| `.github/workflows/release-prime-rs.yml`       | Create | Release workflow for prime-rs (no extra deps)       |
| `.github/workflows/release-fib-rs.yml`         | Create | Release workflow for fib-rs (needs GMP)             |
| `.github/workflows/release-sq-rs.yml`          | Create | Release workflow for sq-rs (no extra deps)          |
| `.github/workflows/release-twin-primes-rs.yml` | Create | Release workflow for twin-primes-rs (no extra deps) |
| `CLAUDE.md`                                    | Modify | Update CI workflow count and table                  |
| `docs/superpowers/README.md`                   | Modify | Add plan link to superpowers index                  |

---

## Task 1: Create release-pi-rs.yml

**Files:**

- Create: `.github/workflows/release-pi-rs.yml`

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/release-pi-rs.yml` with this exact content:

```yaml
name: release-pi-rs

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Version number without the v prefix (e.g. 1.2.0)"
        required: true
        type: string

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

permissions:
  contents: write

jobs:
  release:
    name: Release pi-rs
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - name: Install GMP and MPFR
        run: sudo apt-get update && sudo apt-get install -y libgmp-dev libmpfr-dev

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: pi/pi-rs

      - name: Run tests
        run: make test
        working-directory: pi/pi-rs

      - name: Build release binary
        run: cargo build --release
        working-directory: pi/pi-rs

      - name: Generate release notes
        id: notes
        run: |
          PREV_TAG=$(git describe --tags --abbrev=0 --match="pi-v*" 2>/dev/null || true)
          if [ -n "$PREV_TAG" ]; then
            NOTES=$(git log "${PREV_TAG}..HEAD" --pretty=format:"- %s" -- pi/pi-rs/ || true)
          else
            NOTES=$(git log HEAD --pretty=format:"- %s" -- pi/pi-rs/ || true)
          fi
          DELIMITER="EOF_$(openssl rand -hex 8)"
          {
            printf 'notes<<%s\n' "${DELIMITER}"
            printf '%s\n' "${NOTES}"
            printf '%s\n' "${DELIMITER}"
          } >> "$GITHUB_OUTPUT"

      - name: Create and push tag
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git tag "pi-v${{ inputs.version }}"
          git push origin "pi-v${{ inputs.version }}"

      - name: Create GitHub release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: "pi-v${{ inputs.version }}"
          name: "pi v${{ inputs.version }}"
          body: "${{ steps.notes.outputs.notes }}"
          files: pi/pi-rs/target/release/pi
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-pi-rs.yml')); print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release-pi-rs.yml
git commit -m "ci: add manual release workflow for pi-rs"
```

---

## Task 2: Create release-prime-rs.yml

**Files:**

- Create: `.github/workflows/release-prime-rs.yml`

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/release-prime-rs.yml` with this exact content:

```yaml
name: release-prime-rs

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Version number without the v prefix (e.g. 1.2.0)"
        required: true
        type: string

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

permissions:
  contents: write

jobs:
  release:
    name: Release prime-rs
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: prime/prime-rs

      - name: Run tests
        run: make test
        working-directory: prime/prime-rs

      - name: Build release binary
        run: cargo build --release
        working-directory: prime/prime-rs

      - name: Generate release notes
        id: notes
        run: |
          PREV_TAG=$(git describe --tags --abbrev=0 --match="prime-v*" 2>/dev/null || true)
          if [ -n "$PREV_TAG" ]; then
            NOTES=$(git log "${PREV_TAG}..HEAD" --pretty=format:"- %s" -- prime/prime-rs/ || true)
          else
            NOTES=$(git log HEAD --pretty=format:"- %s" -- prime/prime-rs/ || true)
          fi
          DELIMITER="EOF_$(openssl rand -hex 8)"
          {
            printf 'notes<<%s\n' "${DELIMITER}"
            printf '%s\n' "${NOTES}"
            printf '%s\n' "${DELIMITER}"
          } >> "$GITHUB_OUTPUT"

      - name: Create and push tag
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git tag "prime-v${{ inputs.version }}"
          git push origin "prime-v${{ inputs.version }}"

      - name: Create GitHub release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: "prime-v${{ inputs.version }}"
          name: "prime v${{ inputs.version }}"
          body: "${{ steps.notes.outputs.notes }}"
          files: prime/prime-rs/target/release/prime
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-prime-rs.yml')); print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release-prime-rs.yml
git commit -m "ci: add manual release workflow for prime-rs"
```

---

## Task 3: Create release-fib-rs.yml

**Files:**

- Create: `.github/workflows/release-fib-rs.yml`

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/release-fib-rs.yml` with this exact content:

```yaml
name: release-fib-rs

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Version number without the v prefix (e.g. 1.2.0)"
        required: true
        type: string

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

permissions:
  contents: write

jobs:
  release:
    name: Release fib-rs
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - name: Install GMP
        run: sudo apt-get update && sudo apt-get install -y libgmp-dev

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: fib/fib-rs

      - name: Run tests
        run: make test
        working-directory: fib/fib-rs

      - name: Build release binary
        run: cargo build --release
        working-directory: fib/fib-rs

      - name: Generate release notes
        id: notes
        run: |
          PREV_TAG=$(git describe --tags --abbrev=0 --match="fib-v*" 2>/dev/null || true)
          if [ -n "$PREV_TAG" ]; then
            NOTES=$(git log "${PREV_TAG}..HEAD" --pretty=format:"- %s" -- fib/fib-rs/ || true)
          else
            NOTES=$(git log HEAD --pretty=format:"- %s" -- fib/fib-rs/ || true)
          fi
          DELIMITER="EOF_$(openssl rand -hex 8)"
          {
            printf 'notes<<%s\n' "${DELIMITER}"
            printf '%s\n' "${NOTES}"
            printf '%s\n' "${DELIMITER}"
          } >> "$GITHUB_OUTPUT"

      - name: Create and push tag
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git tag "fib-v${{ inputs.version }}"
          git push origin "fib-v${{ inputs.version }}"

      - name: Create GitHub release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: "fib-v${{ inputs.version }}"
          name: "fib v${{ inputs.version }}"
          body: "${{ steps.notes.outputs.notes }}"
          files: fib/fib-rs/target/release/fib
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-fib-rs.yml')); print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release-fib-rs.yml
git commit -m "ci: add manual release workflow for fib-rs"
```

---

## Task 4: Create release-sq-rs.yml

**Files:**

- Create: `.github/workflows/release-sq-rs.yml`

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/release-sq-rs.yml` with this exact content:

```yaml
name: release-sq-rs

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Version number without the v prefix (e.g. 1.2.0)"
        required: true
        type: string

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

permissions:
  contents: write

jobs:
  release:
    name: Release sq-rs
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: sq/sq-rs

      - name: Run tests
        run: make test
        working-directory: sq/sq-rs

      - name: Build release binary
        run: cargo build --release
        working-directory: sq/sq-rs

      - name: Generate release notes
        id: notes
        run: |
          PREV_TAG=$(git describe --tags --abbrev=0 --match="sq-v*" 2>/dev/null || true)
          if [ -n "$PREV_TAG" ]; then
            NOTES=$(git log "${PREV_TAG}..HEAD" --pretty=format:"- %s" -- sq/sq-rs/ || true)
          else
            NOTES=$(git log HEAD --pretty=format:"- %s" -- sq/sq-rs/ || true)
          fi
          DELIMITER="EOF_$(openssl rand -hex 8)"
          {
            printf 'notes<<%s\n' "${DELIMITER}"
            printf '%s\n' "${NOTES}"
            printf '%s\n' "${DELIMITER}"
          } >> "$GITHUB_OUTPUT"

      - name: Create and push tag
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git tag "sq-v${{ inputs.version }}"
          git push origin "sq-v${{ inputs.version }}"

      - name: Create GitHub release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: "sq-v${{ inputs.version }}"
          name: "sq v${{ inputs.version }}"
          body: "${{ steps.notes.outputs.notes }}"
          files: sq/sq-rs/target/release/sq
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-sq-rs.yml')); print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release-sq-rs.yml
git commit -m "ci: add manual release workflow for sq-rs"
```

---

## Task 5: Create release-twin-primes-rs.yml

**Files:**

- Create: `.github/workflows/release-twin-primes-rs.yml`

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/release-twin-primes-rs.yml` with this exact content:

```yaml
name: release-twin-primes-rs

on:
  workflow_dispatch:
    inputs:
      version:
        description: "Version number without the v prefix (e.g. 1.2.0)"
        required: true
        type: string

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

permissions:
  contents: write

jobs:
  release:
    name: Release twin-primes-rs
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0

      - uses: dtolnay/rust-toolchain@stable

      - uses: Swatinem/rust-cache@v2
        with:
          workspaces: twin-primes/twin-primes-rs

      - name: Run tests
        run: make test
        working-directory: twin-primes/twin-primes-rs

      - name: Build release binary
        run: cargo build --release
        working-directory: twin-primes/twin-primes-rs

      - name: Generate release notes
        id: notes
        run: |
          PREV_TAG=$(git describe --tags --abbrev=0 --match="twin-primes-v*" 2>/dev/null || true)
          if [ -n "$PREV_TAG" ]; then
            NOTES=$(git log "${PREV_TAG}..HEAD" --pretty=format:"- %s" -- twin-primes/twin-primes-rs/ || true)
          else
            NOTES=$(git log HEAD --pretty=format:"- %s" -- twin-primes/twin-primes-rs/ || true)
          fi
          DELIMITER="EOF_$(openssl rand -hex 8)"
          {
            printf 'notes<<%s\n' "${DELIMITER}"
            printf '%s\n' "${NOTES}"
            printf '%s\n' "${DELIMITER}"
          } >> "$GITHUB_OUTPUT"

      - name: Create and push tag
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git tag "twin-primes-v${{ inputs.version }}"
          git push origin "twin-primes-v${{ inputs.version }}"

      - name: Create GitHub release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: "twin-primes-v${{ inputs.version }}"
          name: "twin-primes v${{ inputs.version }}"
          body: "${{ steps.notes.outputs.notes }}"
          files: twin-primes/twin-primes-rs/target/release/twin-primes
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release-twin-primes-rs.yml')); print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release-twin-primes-rs.yml
git commit -m "ci: add manual release workflow for twin-primes-rs"
```

---

## Task 6: Update CLAUDE.md

**Files:**

- Modify: `CLAUDE.md`

The CI table in `CLAUDE.md` currently says "Nine workflow files" and lists them in a table. Add the five new release workflows.

- [ ] **Step 1: Update the workflow count and CI table**

In `CLAUDE.md`, find the CI section. Change "Nine workflow files" to "Fourteen workflow files". Then add these five rows to the table (after the existing `twin-primes-rs` row, before the `auto-merge` row):

```markdown
| release-pi-rs | `.github/workflows/release-pi-rs.yml` | release (manual dispatch) |
| release-prime-rs | `.github/workflows/release-prime-rs.yml` | release (manual dispatch) |
| release-fib-rs | `.github/workflows/release-fib-rs.yml` | release (manual dispatch) |
| release-sq-rs | `.github/workflows/release-sq-rs.yml` | release (manual dispatch) |
| release-twin-primes-rs | `.github/workflows/release-twin-primes-rs.yml` | release (manual dispatch) |
```

Also update the superpowers plan index at `docs/superpowers/README.md`: add the plan file path in the Plan column for the `2026-04-21` row (currently shows `—`).

Update that row from:

```
| 2026-04-21 | —                                                      | [spec](specs/2026-04-21-github-releases-design.md) | In Progress |
```

to:

```
| 2026-04-21 | [github-releases](plans/2026-04-21-github-releases.md) | [spec](specs/2026-04-21-github-releases-design.md) | In Progress |
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md docs/superpowers/README.md
git commit -m "docs: update CI table and superpowers index for release workflows"
```
