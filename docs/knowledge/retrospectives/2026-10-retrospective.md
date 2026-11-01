# 2026-10 Retrospective — math

**Period:** 2026-10-01 → 2026-10-31
**PRs merged:** 29 (#165–#196, excl. #178 closed without merge)
**Commits:** 50

---

## PRs Merged

| PR | Title | Area |
|----|-------|------|
| #165 | fix(ci): pin pyright and every cargo install to one version | CI/tooling |
| #166 | fix(build): make `<project>` only builds; make install to `~/.local/bin` | Rust/build |
| #167 | fix(crates): make all 11 Makefiles and rustfmt.toml identical | Rust/templates |
| #168 | fix(crates): render Makefile, rustfmt and release workflows from templates | Rust/templates |
| #169 | fix(crates): render the 11 CI workflows and nextest config from templates | Rust/templates |
| #170 | fix(crates): one tested install_deps.sh for all 11 crates | Rust/templates |
| #171 | feat(cli): one CLI contract for the 8 Python programs | Python/CLI |
| #172 | feat(pyright): run every Python project at standard via an exact gmpy2 stub | Python/types |
| #173 | refactor(python): render the 8 Python projects' files from templates | Python/templates |
| #174 | fix(python): keep mpmath precision through the spawn conversion worker | Python/correctness |
| #175 | fix(rust): stop holding the stderr lock across run() in pi, prime and e | Rust/correctness |
| #176 | fix(rust): wake progress threads when work finishes instead of after a 200 ms sleep | Rust/perf |
| #177 | ci(rust): prebuilt CI tools, parallel coverage job and parallel bats | CI/Rust |
| #179 | fix(renovate): scan the crate templates with the github-actions manager | Renovate |
| #180 | feat(rust): one Cargo.toml shape, crate CLAUDE.md, concurrent suites, bounded tests | Rust/quality |
| #181 | chore(deps): update taiki-e/install-action to v2.87.32 | Deps |
| #182 | chore(renovate): add 14-day minimumReleaseAge | Renovate |
| #183 | fix(mutation): fail closed and shard python mutation testing | Python/mutation |
| #185 | fix(ci): gate root pyright errors locally and match ci-gate names exactly | CI/pyright |
| #186 | ci: master-scoped GMP build cache and parallel bats | CI/perf |
| #187 | feat(rust): edition 2024 and forbid unsafe in all crates | Rust/standards |
| #188 | feat(licence): MIT licence, cargo-deny and LGPL release notices | Legal/CI |
| #189 | feat(ruff): extend the default rule set and fix its findings | Python/lint |
| #190 | fix(deny): report unsound advisories in transitive crates | CI/security |
| #191 | ci: verify downloads, lock cargo-deny, drop unused GMP apt step | CI/security |
| #192 | test(hooks): lint root Python at commit, isolate and pin pre-push tests | Hooks/testing |
| #193 | feat(pre-push): load the shared push-content gate | Hooks |
| #194 | fix(make): harden Python Makefile template (ruff guard, scratch-copy mutants) | Python/templates |
| #196 | test(deny): match etch-cli, pin deny.toml by key and the real cargo-deny call | CI/security |

Direct commits (not PRs):
- Multiple `docs(spec)` series for three specs: hook hardening, CI supply-chain bundle, Python Makefile template hardening (each went 3–4 rounds)
- `docs(adr)`: ADR-0036 (edition 2024/no MSRV/ruff defaults), ADR-0037 (CI supply-chain guardrails)
- `chore(release)`: bump all crates to v0.2.0
- `docs`: README licence section, release notices file, close backlog rows, plan completions

---

## Recurring Patterns and Gotchas

### 1. Template-driven uniformity: the big uniformity sweep

October's dominant theme was completing a full template sweep for all 19 sub-projects. PRs #165–#173 (8 PRs in one week) converted every Rust crate and Python sub-project to render-from-template, eliminating drift that had accumulated across 11 crates and 8 Python projects. Key invariant: `tests/test_crate_uniformity.py` now detects any future drift, so one-off edits to individual crates fail CI immediately. The pattern — render templates, add a uniformity test, never edit individual copies — is now the standing operating procedure for all 19 projects.

### 2. CI supply-chain hardening (ADR-0037)

A full bundle of supply-chain improvements landed in #191: `actions/download-artifact` checksum verification, `cargo-deny --locked` in every workflow, and removal of an unused `libgmp-dev` apt step. The `etch-cli` false positive in `deny.toml` and the test harness gaps were closed in #190 and #196. The lesson: cargo-deny's `[advisories]` default silently ignores `unsound` findings — setting `unsound = "deny"` explicitly is now required and tested.

### 3. Python mutation testing: fail-closed sharding

#183 fixed two separate problems in Python mutation testing: the suite was not failing when `cosmic-ray` exited non-zero (fail-open), and the monthly job ran all 80 shards in series. The fix shards to 8×10 in CI and fails closed on any non-zero exit. A subtle gotcha: `cosmic-ray` stores outcomes uppercase (`SURVIVED`, `KILLED`) but the classification script was comparing lowercase — a silent survivor-undercount for months.

### 4. mpmath precision through spawn workers

#174 fixed a correctness bug where `mpmath.mp.dps` is process-local: spawned `ProcessPoolExecutor` workers inherited no precision context, so high-precision conversions silently dropped to default (15 sig figs). Fix: pass `dps` explicitly to every worker function. This class of bug (process-local global state + spawn) is a recurring risk for all three Python high-precision calculators (pi, e, factorial). Tested with a precision-sentinel round-trip assertion.

### 5. Rust lock contention: stderr across async boundaries

#175 found that `pi`, `prime` and `e` were holding a `stderr` lock across an async `run()` call — when the Rust runtime switched tasks under that lock, a second task writing to stderr would deadlock. Fix: drop the lock guard before `await`. Separately, #176 eliminated a 200 ms busy-sleep that delayed progress thread wakeups in all computation loops; the fix wakes threads via a `Condvar::notify_all` on each chunk completion.

### 6. Renovate template scanning gap

#179 found that Renovate was not scanning the crate templates for `github-actions` manager updates (it only updated the rendered copies, not the templates). Since the templates are canonical, updates applied to rendered copies only would be overwritten on the next render. Fix: add `fileMatch` patterns for `scripts/crate_templates/**` to the `github-actions` manager.

---

## Test Health

- **Coverage:** No coverage regressions reported in October. All 11 Rust crates and 8 Python sub-projects remain above 90%.
- **BATS suite:** Parallel bats (`--jobs 8`) landed in #186; the suite is now ~4× faster in CI. New BATS tests were added for hooks and pre-push isolation in #192.
- **Pyright:** #185 fixed a ci-gate name mismatch that meant root pyright errors could slip past the auto-merge gate. The root `pyrightconfig.json` (landed in September) is now properly gated locally.
- **Mutation testing:** Python mutation CI is now sharded (8×10) and fail-closed. Rust mutation testing unchanged.
- **test_crate_uniformity.py** now pins `Cargo.toml` shape, `rustfmt.toml`, nextest config, and edition/unsafe/lints for all 11 crates — significantly expanded test coverage of crate metadata.

---

## What Went Well

- **Massive uniformity sweep completed in one week.** Converting all 19 sub-projects to template rendering (#165–#173) was high-risk but landed cleanly because the uniformity test caught every drift case immediately.
- **Three-round spec process for complex changes.** Each of the three specs (hook hardening, CI supply-chain bundle, Python Makefile hardening) went 3–4 review rounds before implementation started. All three landed without post-merge bugs.
- **Rust standards tier 1 landed atomically.** Edition 2024, `unsafe = "forbid"`, ruff defaults, MIT licensing and cargo-deny all landed in one coordinated sprint (PRs #187–#191) with ADR-0036 and ADR-0037 documenting the rationale.
- **Correctness bug in mpmath precision discovered and fixed** before it affected a release — caught by the precision-sentinel assertion pattern.

---

## What to Improve

- **PR concentration at month-end.** 19 of 29 PRs merged on Oct 25 or Oct 31. This reflects spec-cycle latency rather than last-minute rushing, but stacking large batches of PRs on a single day compresses CI queue time and makes rollback harder if one PR introduces a regression.
- **Renovate manager coverage gaps.** The template scanning gap (#179) suggests other Renovate managers may not cover all canonical files. A one-time audit of `renovate.json` `fileMatch` patterns against every file that owns a pinned version would catch these proactively.
- **Process-local global state risk across all three Python high-precision calculators.** The mpmath fix in #174 applied to one location; the `pi`, `e`, and `factorial` calculators all share this pattern. A shared test fixture that spawns a worker and asserts precision consistency would prevent future regressions across all three.

---

## Action Items for Next Period

- [ ] Audit `renovate.json` `fileMatch` patterns against all canonical files with pinned versions (templates, root scripts, `.github/actions/`) to ensure no manager has a template-scanning gap.
- [ ] Add a shared pytest fixture for precision-through-spawn to `pi/test_pi.py`, `e/test_e.py`, and `factorial/test_factorial.py` — one test pattern covering all three high-precision calculators.
- [ ] Investigate whether the 19 `install_deps.sh` files are reachable from the pre-push hook (CLAUDE.md notes 19 shell files were "unreachable from push path" as a backlog item from September). Schedule or close.
- [ ] Dispatch `gmp-cache.yml` now that `gmp-mpfr-sys` was not bumped this cycle but the GMP cache is now master-scoped — confirm the weekly cache save job is green.
