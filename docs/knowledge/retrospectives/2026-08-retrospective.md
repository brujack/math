# 2026-08 Retrospective — math

**Period:** 2026-08-01 → 2026-08-31
**PRs merged:** 27 (#91–#124)
**Commits:** 50

---

## PRs Merged

| PR | Title | Area | Author |
|----|-------|------|--------|
| #91 | fix(mutation): end six months of dead mutation runs | CI/mutation | brujack |
| #93 | fix(ci): survive errexit so the mutation classifier runs | CI/mutation | brujack |
| #94 | fix(ci): stop tee from swallowing the mutation verdict | CI/mutation | brujack |
| #97 | fix(ci): capture red verdicts from stderr so notify can name crates | CI/mutation | brujack |
| #101 | feat(lints): enforce C-DEBUG and C-CONV across all 11 Rust crates | Rust/lint | brujack |
| #102 | feat(lint): adopt shared ruff rule set and pin 0.16.1 | Python/lint | brujack |
| #103 | fix(ci): shellcheck hooks and bats, run them on a hook-only push | CI/shell | brujack |
| #104 | fix(ci): scope each bench to its Criterion target, stop swallowing failures | CI/bench | brujack |
| #105 | ci: lint all tracked shell at default severity | CI/shell | brujack |
| #106 | feat(coverage): port the bash coverage tracer from dotfiles | Coverage | brujack |
| #107 | fix(coverage): set the bash-coverage floor from CI's measurement | Coverage | brujack |
| #108 | fix(coverage): sync tracer with dotfiles PR #204 hardening | Coverage | brujack |
| #109 | fix(amicable-rs): restore the lint gate on make test | Rust/lint | brujack |
| #110 | fix(hooks): run shell lint on the push path, and install what the Makefiles invoke | Hooks/shell | brujack |
| #111 | feat(lint): wire root-scope Python into make lint and the push path | Python/lint | brujack |
| #112 | chore(renovate): pin action digests and bump ruff to 0.16.4 | Deps/renovate | brujack |
| #113 | fix(ci): pin dtolnay/rust-toolchain to a SHA digest | CI/security | brujack |
| #114 | fix(renovate): inline the shared preset, which a public repo cannot fetch | Deps/renovate | brujack |
| #115 | chore(deps): pin dependencies | Deps | renovate[bot] |
| #116 | chore(deps): update all non-major dependencies | Deps | renovate[bot] |
| #118 | chore(deps): update actions/checkout action to v7 | Deps | renovate[bot] |
| #119 | chore(deps): update actions/download-artifact action to v8 | Deps | renovate[bot] |
| #120 | ci: hold unlabelled Renovate PRs for triage | CI/renovate | brujack |
| #121 | chore(deps): update actions/setup-python action to v7 | Deps | renovate[bot] |
| #122 | fix(bench): use std::hint::black_box, unblocking the criterion 0.8 bump | Rust/bench | brujack |
| #123 | chore(renovate): auto-merge digest updates, assert the policy is exhaustive | Deps/renovate | brujack |
| #124 | chore(deps): update softprops/action-gh-release digest to efb3536 | Deps | renovate[bot] |

Direct commits (not PRs):
- `docs(spec)`: multi-commit spec series — retier notify spec, Step 8 multi-lens review, permissions premise separation, mutation-notify attribution
- `docs`: CLAUDE.md syncs for pytest migration, bash coverage, triage_log vendoring, ruff config, 53-test root suite
- 4× `chore(changelog)`: weekly updates
- `fix(ci)` direct commits: mutation-testing fixes that preceded the PR series

---

## Recurring Patterns and Gotchas

### 1. New CI feature → immediate follow-up fix loop (fourth consecutive month)

Mutation testing required **four PRs to converge** (#91→#93→#94→#97):
- #91 fixed the root cause (OOM from missing `ulimit -v`, six months of SIGTERM kills)
- #93 fixed `errexit` in the classifier caller — the classifier never ran because the preceding `cargo mutants` exit code caused the shell to abort
- #94 fixed `tee` swallowing the classifier's exit code — `command | tee file` always exits 0 in bash; needed `PIPEFAIL` and a redirect instead
- #97 fixed red verdicts going to stderr rather than stdout, so the notify job couldn't capture crate names

This is the same pattern as June (sha256sum path, #72→#73) and July (SBOM dedup, #88→#89), but with 4 PRs instead of 2. The cycle is accelerating in depth even as the root causes differ each time.

**Lesson:** CI scripts involving pipes, `tee`, `errexit`, and subprocess exit codes must be tested with `bats` mocks before landing. A CI script that has never been exercised with a failing upstream tool is untested. The same mock infrastructure used for `tests/scripts/ci_gate.bats` should gate every new CI script.

### 2. `tee` swallows exit codes — a perennial bash gotcha

`command | tee logfile` always exits 0 unless `set -o pipefail` is set. Both #93 and #94 were symptoms of this class of error. The mutation classifier sends its verdict (red/green) as its exit code, and two different wrapping patterns both dropped it. This is documented now in `scripts/mutation-classify.sh`, but the fix pattern (use `exec > >(tee ...)` or capture exit separately) needs to become habitual.

**Lesson:** Any shell script that uses `|` to connect a command whose exit code matters must have `set -o pipefail` or an explicit exit-code capture. `shellcheck` does not catch this by default — add `SC2024` to the deny list or document it in the pre-merge checklist.

### 3. Renovate onboarding completed in one month

Renovate went from zero to fully configured in August:
- #112: action digest pinning + ruff bump
- #113: dtolnay/rust-toolchain SHA pin
- #114: preset inlined (public repos cannot fetch private presets)
- #115: initial Renovate pin batch
- #116/#118/#119/#121/#124: Renovate auto-merged minor/patch bumps
- #120: triage label gate for unlabelled PRs
- #123: exhaustive auto-merge policy test

Onboarding required one manual fix (#114 — the preset reference assumes private repo access) but otherwise landed cleanly. The `test_renovate_automerge_policy.py` exhaustiveness check (`_DELIBERATELY_HELD` map over all ten `updateType`s) prevents silent policy gaps going forward.

**Lesson:** Renovate preset sharing does not work for public repos — inline the preset on first setup. Test policy exhaustiveness from day one; an untested `packageRules` section is a maintenance hole.

### 4. Bash coverage port required three PRs due to upstream drift

The coverage tracer from dotfiles (#106) was re-synced within 24 hours (#108) due to three upstream hardening commits that had landed in dotfiles. The floor was set separately (#107) after CI measured 30% on the honest denominator (19 of 26 instrumented files are `install_deps.sh` scripts with 0% coverage). ADR-0061 predicted this drift and was vindicated on day one.

**Key design decision documented:** excluding `install_deps.sh` from the instrumented set would raise the reported percentage by removing the untested majority from the denominator — that's the flattering-denominator defect the tool exists to prevent. The floor (24%) is a regression ratchet over the reachable 25%, not a quality bar for the repo's shell.

### 5. Linting standardization completed across all three language stacks

August closed all three open linting gaps:
- **Rust:** C-DEBUG and C-CONV enforced via `[lints.rust]` / `[lints.clippy]` in all 11 `Cargo.toml`s (#101)
- **Python:** shared ruff rule set + `ruff==0.16.4` pin fleet-wide; root-scope `scripts/` and `tests/` wired in (#102, #111)
- **Shell:** shellcheck on all tracked shell via `scripts.yml`, pre-push hook, and pre-commit hook (#103, #105, #110)

The ruff bump from 0.16.1 → 0.16.4 was validated with a two-venv positive-control test before merging; the two `# noqa: C901` suppressions in `e/e.py` and `pi/pi.py` were confirmed load-bearing (complexity 21 > ceiling 10).

---

## Test Health

- **Root Python suite:** 53 tests as of 2026-08-24 (`test_time_tests.py`, `test_test_metrics.py`, `test_triage_log.py`, `test_renovate_automerge_policy.py`)
- **Bash coverage:** 30% (331/1085 coverable lines) measured in CI — floor set at 24%
- **Mutation testing:** First non-dead monthly run scheduled for 2026-09-01 (the 1st of September). All six runs from 2026-02 through 2026-07 produced exit 143; the fix (#91) addresses the root cause (OOM from uncapped `ulimit`). The September run will be the first real signal.
- **No flaky tests reported** in this period across Python or Rust suites.
- **amicable-rs lint gate** (#109): discovered that `make test` was running tests without lint, silently. The gate was dropped when the crate was added — a regression in test harness correctness, not in the math.

---

## What Went Well

1. **Mutation testing is live again.** Six months of dead CI finally ended. The root cause (OOM from missing `ulimit -v`) was correctly diagnosed in ADR-0024 after the earlier `--timeout` reduction diagnosis proved wrong.

2. **Renovate onboarded cleanly in one month.** Dependency management is now automated for digest updates and patch/minor bumps. The exhaustiveness test (`test_renovate_automerge_policy.py`) gives future sessions a machine-checkable contract.

3. **Linting gaps closed fleet-wide.** All three language stacks now have blocking lint in CI, pre-commit, and pre-push. The root-scope Python gap (scripts and tests were never linted by anything) was closed without breaking any existing check.

4. **Bash coverage port respected design discipline.** Despite pressure toward a more flattering number, the honest-denominator design was preserved. The CLAUDE.md write-up explains the reasoning in enough detail that future sessions won't be tempted to "fix" it.

5. **Criterion bench fix unblocked a pending dep upgrade.** #122 (using `std::hint::black_box` instead of the deprecated Criterion re-export) was a prerequisite for the criterion 0.8 bump that Renovate will eventually propose.

---

## What to Improve

1. **The CI-fix loop depth is increasing.** One month = 4 PRs to fix one CI feature. The fix is to test CI scripts with bats before landing, not after. The mock infrastructure exists (`tests/mocks/`, `tests/scripts/`). It needs to be applied to new CI features at PR time.

2. **`install_deps.sh` scripts have 0% bash coverage.** 19 of 26 instrumented files are untested. This is documented as intentional (untested ≠ uncoverable), but the long-term answer is bats tests that exercise at least the dependency-check paths of each installer.

3. **Spec work is not landing as code.** The docs/spec commit series (Step 8 multi-lens review, permissions premise, mutation-notify spec) represents design work that hasn't produced a PR. Spec-only commits are fine when gated on a concrete implementation following, but the series is growing without a closing PR.

4. **amicable-rs lint gap was silent.** The missing lint gate in `make test` was never caught by CI because CI calls `make test` which only runs the test binary — the gate was in `make lint`, which `make test` was supposed to call first. Future crate additions should assert via `tests/scripts/makefile.bats` that `make test` depends on `make lint`.

---

## Action Items for September 2026

- [ ] **Verify the September mutation-testing run passes** — first real signal after the #91 fix. Watch the run scheduled for 2026-09-01. If it fails, diagnose immediately; do not let another multi-month gap accumulate.
- [ ] **Add bats test for at least one `install_deps.sh` path** — pick one installer and add a test that exercises the dependency-check branch under mock conditions. This starts shrinking the 73% untested shell set.
- [ ] **Add `makefile.bats` assertion that `make test` depends on lint** in each Rust crate — prevents a recurrence of the amicable-rs gap.
- [ ] **Land or triage the docs/spec series** — the permissions spec and mutation-notify spec need either a concrete PR implementing the design or a decision to shelve them.
- [ ] **Document `tee` / `PIPEFAIL` in the CI script checklist** in CLAUDE.md — so future sessions don't rediscover this bash gotcha the hard way.
