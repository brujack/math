# Atomic Release Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the SBOM catalogue real dependencies, and publish it in the same operation that publishes the release, so a published release always carries a meaningful SBOM.

**Architecture:** Eleven `release-<name>-rs.yml` workflows switch to `cargo auditable build --release` so syft can read an embedded `.dep-v0` dependency section. `release-sign.yml` — a reusable workflow whose separate job forced `gh release download`, which forced the release to exist before signing — is replaced by a composite action running in the release job itself. The release is then created once with binary, checksum, SBOM and signature bundle together.

**Tech Stack:** GitHub Actions composite actions, `cargo-auditable` 0.7.5, syft 1.51.1, cosign v4 (`--bundle`), `softprops/action-gh-release` v3, bats, Python `unittest`.

## Global Constraints

- `cargo auditable build --release` replaces `cargo build --release` in all eleven release workflows; `cargo install cargo-auditable --locked` is added to each.
- `fail_on_unmatched_files: true` MUST be set on every `softprops/action-gh-release` call. Measured from `action.yml` at pinned SHA `efb35369e0ad2afab669f228072c1b0d510eae64`: the input has **no default** and its description reads "Defaults to false", so `run.ts:14-21` takes the `console.warn` branch and publishes a release with missing assets. Without this input the atomic-publication guarantee is nominal.
- `Create and push tag` MUST move to after the sbom-sign step. Measured: all eleven order `Commit CHANGELOG` (line 59 or 62) → `Create and push tag` (76 or 79) → `Create GitHub release` (85 or 88), and no workflow guards a pre-existing tag (`grep -l 'ls-remote\|push --delete\|--force'` returns nothing). A signing failure after the tag push leaves an unshippable version.
- All action refs stay SHA-pinned with the version in a trailing comment (ADR-0006).
- Composite action `run:` steps anchor paths on `${GITHUB_WORKSPACE}`, never a bare relative path — a composite action's own bundled files resolve from `${{ github.action_path }}`.
- No count of cases, steps or files is restated outside the section that lists them.

## Measured baseline (2026-09-04)

| quantity                                             | current                                                    |
| ---------------------------------------------------- | ---------------------------------------------------------- |
| `cargo build --release` in release workflows         | 11 of 11                                                   |
| `cargo auditable build` in release workflows         | 0 of 11                                                    |
| `release-sign.yml` references                        | 11 of 11                                                   |
| syft packages, `sq` ELF x86-64, no cargo-auditable   | 1 (the binary itself), 1,208 B                             |
| syft packages, `sq` ELF x86-64, with cargo-auditable | 13, 22,554 B                                               |
| `sq/sq-rs/Cargo.lock` crates                         | 133                                                        |
| `.github/actions/`                                   | does not exist — this is the repo's first composite action |

13 against 133 is correct: `cargo-auditable` records what is linked, not what `Cargo.lock` resolves.

## Session-level verification

**Command:** `make test` from the repo root, plus `make lint-hooks`.

**Expected:** exit 0. `tests/test_release_workflows.py` passes, asserting all eleven workflows use `cargo auditable build --release`, reference `./.github/actions/sbom-sign`, reference `release-sign.yml` nowhere, set `fail_on_unmatched_files: true`, list four artifacts, and order the tag push after the sbom-sign step.

**Observable change:** `.github/workflows/release-sign.yml` no longer exists; `.github/actions/sbom-sign/action.yml` and `scripts/sbom-sign.sh` do.

**Edge cases exercised:** syft failure and cosign failure propagate; a missing binary fails before syft runs; the sbom-sign script writes both artifacts rather than merely exiting 0.

**Not verifiable in this plan, stated rather than worked around:** whether keyless cosign OIDC works inside a composite action's job context, and whether `softprops` accepts four files. No mock covers either. Both require a throwaway release, which is a separate operator-approved step after this plan merges.

---

### Task 1: SBOM and signing script with failure propagation

```yaml-task
id: 1
description: Add scripts/sbom-sign.sh generating an SPDX SBOM and cosign bundle, with a bats suite covering artifact production and failure propagation
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make lint-hooks
    exit_code: 0
  - cmd: bats tests/scripts/sbom_sign.bats
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched:
  - scripts/sbom-sign.sh
  - tests/scripts/sbom_sign.bats
depends_on: []
```

**Files:** `scripts/sbom-sign.sh` (new), `tests/scripts/sbom_sign.bats` (new).

Script takes two positional arguments, `binary_path` (directory) and `binary_name`. It runs `syft "${binary_path}/${binary_name}" -o spdx-json --file "${binary_path}/${binary_name}.sbom.spdx.json"` then `cosign sign-blob --yes "${binary_path}/${binary_name}" --bundle "${binary_path}/${binary_name}.bundle"`.

Follow `shell.md`: `#!/usr/bin/env bash`, no `set -e`, `|| return 1` / `|| exit 1` propagation, `[[ ]]`, `${VAR}`, `printf`, `readonly` constants, sourcing guard so bats can source without executing.

Guard the binary's existence before invoking syft, and fail with a message naming the path.

**Tests** — mock `syft` and `cosign` on `PATH` via `tests/mocks/`:

- Writes both artifacts — assert both files exist at the expected paths. Assert on **files produced**, not on the mock having been called: a stub exiting 0 without writing passes a call-count assertion and fails this one, and only this one distinguishes a working script from one that ignores syft's result.
- syft failure propagates — mock exits non-zero; assert the script exits non-zero **and** cosign was not invoked.
- cosign failure propagates — assert non-zero.
- Missing binary — assert non-zero with the path named, and that syft was not invoked.

**Interfaces:**

- Consumes: nothing.
- Produces: `scripts/sbom-sign.sh <binary_path> <binary_name>`, writing `<binary_path>/<binary_name>.sbom.spdx.json` and `<binary_path>/<binary_name>.bundle`. Task 2 invokes it; Task 3 asserts those two filenames appear in each workflow's `files:` list.

---

### Task 2: Composite action wrapping syft, cosign and the script

```yaml-task
id: 2
description: Add .github/actions/sbom-sign/action.yml installing syft and cosign then invoking scripts/sbom-sign.sh
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'python3 -c "import yaml,sys; yaml.safe_load(open(\".github/actions/sbom-sign/action.yml\"))"'
    exit_code: 0
  - cmd: 'grep -q "GITHUB_WORKSPACE" .github/actions/sbom-sign/action.yml'
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched:
  - .github/actions/sbom-sign/action.yml
depends_on: [1]
```

**Files:** `.github/actions/sbom-sign/action.yml` (new; `.github/actions/` does not yet exist).

`tdd: not-applicable` — this is a declarative action manifest with no logic of its own; its behaviour is Task 1's script, which is bats-tested, and its wiring is asserted by Task 3's uniformity test.

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

Both SHAs are copied verbatim from the current `release-sign.yml`, which Task 3 deletes.

**Interfaces:**

- Consumes: `scripts/sbom-sign.sh` from Task 1.
- Produces: `./.github/actions/sbom-sign` with inputs `binary_path`, `binary_name`. Task 3 references this exact path in eleven workflows.

---

### Task 3: Uniformity test, eleven workflow rewrites, delete release-sign.yml

```yaml-task
id: 3
description: Add tests/test_release_workflows.py pinning the release-workflow contract, then rewrite all eleven workflows to satisfy it and delete release-sign.yml
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: 'python3 -m unittest tests.test_release_workflows -v'
    exit_code: 0
  - cmd: '[ ! -f .github/workflows/release-sign.yml ]'
    exit_code: 0
  - cmd: 'test "$(grep -l "cargo auditable build --release" .github/workflows/release-*-rs.yml | wc -l | tr -d " ")" = 11'
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched:
  - tests/test_release_workflows.py
  - .github/workflows/release-amicable-rs.yml
  - .github/workflows/release-collatz-rs.yml
  - .github/workflows/release-e-rs.yml
  - .github/workflows/release-factorial-rs.yml
  - .github/workflows/release-fib-rs.yml
  - .github/workflows/release-goldbach-rs.yml
  - .github/workflows/release-perfect-numbers-rs.yml
  - .github/workflows/release-pi-rs.yml
  - .github/workflows/release-prime-rs.yml
  - .github/workflows/release-sq-rs.yml
  - .github/workflows/release-twin-primes-rs.yml
  - .github/workflows/release-sign.yml
depends_on: [2]
```

**Files:** `tests/test_release_workflows.py` (new), eleven `release-<name>-rs.yml`, delete `.github/workflows/release-sign.yml`.

**Write the test first and watch it fail.** On the unmodified tree every assertion below fails for all eleven — that is the RED, and it is a real failure (exit 1), not a collection error, because the test discovers workflows with `glob` rather than importing anything.

The test derives its workflow list from `glob.glob(".github/workflows/release-*-rs.yml")` and asserts a count of 11, so a twelfth binary added later joins automatically. Per workflow:

1. `cargo auditable build --release` present; `cargo build --release` absent.
2. `cargo install cargo-auditable --locked` present.
3. `./.github/actions/sbom-sign` referenced.
4. `release-sign.yml` not referenced; no `sign:` job.
5. `fail_on_unmatched_files: true` present.
6. The `files:` list contains the binary, `.sha256`, `.sbom.spdx.json`, `.bundle` for that workflow's own binary, derived from the filename.
7. The `Create and push tag` step's line number is greater than the `sbom-sign` step's.

Also assert no file under `.github/workflows/` references `release-sign.yml`.

> **On assertion 6's four artifacts:** the set is hardcoded. Deriving it from the composite action's inputs or from `sbom-sign.sh`'s output filenames would be circular — the test would agree with whatever those produce. The invalidating condition: **a fifth artifact (an attestation, a second signature format) added to eleven workflows leaves this test green while asserting an incomplete set.** Put that sentence in the test as a comment.

**Workflow edits, uniform across all eleven:**

- `cargo build --release` → `cargo auditable build --release`.
- Add `cargo install cargo-auditable --locked` as a step before the build.
- Delete the `sign:` job.
- Insert the composite step after `Generate SHA256 checksum`, with `binary_path` and `binary_name` for that workflow's binary.
- **Move `Create and push tag` to after the composite step**, immediately before `Create GitHub release`. Nothing needs the tag earlier — `softprops` creates it from `tag_name`.
- Extend `files:` to four entries.
- Add `fail_on_unmatched_files: true`.

**Interfaces:**

- Consumes: `./.github/actions/sbom-sign` from Task 2.
- Produces: eleven workflows with no `sign:` job. Task 4 adds `.github/workflows/release-*` to the gate paths so this test runs when they change; Task 6 updates `CLAUDE.md`'s CI table for the deleted workflow.

---

### Task 4: Route release-workflow changes through the gate that tests them

```yaml-task
id: 4
description: Add .github/workflows/release-* to scripts.yml paths and the pre-push pattern so the uniformity test runs on the change class it guards
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: bats tests/scripts/pre_push.bats
    exit_code: 0
  - cmd: 'grep -q "release-\*" .github/workflows/scripts.yml'
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched:
  - .github/workflows/scripts.yml
  - scripts/pre-push
  - tests/scripts/pre_push.bats
depends_on: [3]
```

**Files:** `.github/workflows/scripts.yml`, `scripts/pre-push`, `tests/scripts/pre_push.bats`.

Measured: `scripts.yml`'s `paths:` is `scripts/**`, `tests/**`, `Makefile`, `.github/workflows/scripts.yml`; `scripts/pre-push:52` matches `^scripts/|^tests/|^Makefile$|^\.github/workflows/mutation-testing.*\.yml$`. A PR editing only `.github/workflows/release-*.yml` matches **neither**, so Task 3's uniformity test would never run on the change class it exists to catch — silent by construction, the property it was written to prevent.

Add `.github/workflows/release-*` to `scripts.yml`'s `paths:`, and `|^\.github/workflows/release-.*\.yml$` to the pre-push pattern.

**Test first:** add a `pre_push.bats` case asserting that a push range touching only `.github/workflows/release-sq-rs.yml` triggers the root test path. It fails on the current pattern — that is the RED, and it fails as a real assertion failure rather than an error because the harness and mocks already exist in that file.

**Interfaces:**

- Consumes: Task 3's test file must exist so the gate has something to run.
- Produces: nothing later tasks depend on.

---

### Task 5: Repair the documented cosign verification command

```yaml-task
id: 5
description: Fix README verification command — cosign v4 bundle form and the eleven per-workflow certificate identities (docs-only, no behavior change)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'grep -q -- "--bundle" README.md'
    exit_code: 0
  - cmd: '! grep -q "release-sign.yml" README.md'
    exit_code: 0
  - cmd: '! grep -q -- "--signature" README.md'
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched:
  - README.md
depends_on: [3]
```

**Files:** `README.md` lines 398-409.

Two defects, one pre-existing. The command reads `--signature factorial.sig --certificate factorial.pem` — the deprecated cosign v3 form naming two assets the pipeline has never produced, while `release-sign.yml` writes `--bundle`. `ci.md` records this exactly: cosign v4 uses `--bundle`. So the documented command is already broken today, independent of this plan.

Second, `--certificate-identity ".../release-sign.yml@refs/tags/factorial-vTAG"` names a workflow Task 3 deletes. Keyless cosign's identity is the workflow that requested the token, so one identity becomes eleven — `release-<name>-rs.yml`.

Rewrite to the v4 form, parameterised over the sub-project name so the reader substitutes once:

```bash
cosign verify-blob factorial \
  --bundle factorial.bundle \
  --certificate-identity \
    "https://github.com/brujack/math/.github/workflows/release-factorial-rs.yml@refs/tags/factorial-vTAG" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com"
```

Keep the existing "Replace `factorial` and `factorial-vTAG`…" sentence and extend it to cover the workflow filename.

**Interfaces:** none.

---

### Task 6: Update CLAUDE.md for the new pipeline shape

```yaml-task
id: 6
description: Update CLAUDE.md CI table, workflow count, and record the atomic-publication and cargo-auditable invariants (docs-only, no behavior change)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: 'grep -q "cargo-auditable" CLAUDE.md'
    exit_code: 0
  - cmd: 'grep -q "sbom-sign" CLAUDE.md'
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched:
  - CLAUDE.md
depends_on: [3]
```

**Files:** `CLAUDE.md` — the CI table, the workflow count sentence, and a new note.

- Remove the `release-sign` row from the CI workflow table; the workflow count drops by one from its stated forty-one. State the new count by re-deriving it (`git ls-files .github/workflows/ | wc -l`) rather than by subtracting.
- Add a note under CI recording both invariants and why they exist:
  - **The SBOM is only meaningful under `cargo-auditable`.** Measured 2026-09-04: `syft` over a stripped Rust binary reports 1 package — the binary itself — on both Mach-O arm64 and ELF x86-64, against a 133-crate lockfile. With `cargo auditable build --release` it reports 13 with real dependency names. A release built without it publishes an SBOM that `grype` scans to no effect.
  - **Signing happens before publication, in the release job.** `release-sign.yml` was a reusable workflow, so it ran as its own job and had to `gh release download` the binary, which forced the release to exist first — leaving a window where a published release carried no SBOM. The composite action removes the window rather than narrowing it. Do not reintroduce a separate signing job.
  - **`fail_on_unmatched_files: true` is required** on every `softprops/action-gh-release` call. The input defaults to false, so without it a `files:` entry matching nothing publishes the release anyway with only a warning.

**Interfaces:** none.

---

## Self-review notes

- **Spec coverage:** Part 0 → Task 3; composite action → Tasks 1-2; tag reorder → Task 3; gate paths → Task 4; README → Task 5; `CLAUDE.md` → Task 6. Parts 1 and 3 of the spec (throwaway baseline and confirmation releases) are deliberately **not** tasks — they are operator-run steps requiring a public release, sequenced after this plan merges.
- **Gate falsifiability — measured, not asserted.** Every gate naming an existing file was run
  against this tree with `command grep` (bypassing the session's ugrep wrapper, so the result
  describes the program CI runs). All exit **1** — real assertion failures, not usage errors:

  ```
  T3 cargo-auditable count = 11                                  exit=1
  T3 release-sign.yml absent                                     exit=1
  T5 README has --bundle                                         exit=1
  T5 README lacks release-sign.yml                               exit=1
  T5 README lacks --signature                                    exit=1
  T4 scripts.yml paths has release-*                             exit=1
  T6 CLAUDE.md mentions cargo-auditable                          exit=1
  T6 CLAUDE.md mentions sbom-sign                                exit=1
  ```

  The three gates naming files their own task creates — `tests/scripts/sbom_sign.bats`,
  `.github/actions/sbom-sign/action.yml`, `tests.test_release_workflows` — error rather than
  fail on this tree. That is the ordinary TDD shape for a new file, not the "names a path that
  will never exist" defect: each path is created by the task that gates on it.

- **What a passing gate here cannot see.** Task 3's uniformity test compares workflow text to
  workflow text, so it would pass unchanged if `scripts/sbom-sign.sh` were `exit 0`. That is
  why Task 1's first bats case asserts on **files produced** rather than on the mock having
  been called — it is the only case in the plan that fails if the script computes nothing.
- **No magic numbers:** the one count gate (`= 11`) is the measured population of `release-*-rs.yml`, asserted in Task 3's test by globbing rather than by a literal, so a twelfth binary joins automatically.
- **Task 2 has no test file** because `tdd: not-applicable` — justified in its description; its behaviour is Task 1's script.
- **No task uses `model: haiku`** — every task touches either a workflow file or more than one file, both of which the scope guard rejects.
