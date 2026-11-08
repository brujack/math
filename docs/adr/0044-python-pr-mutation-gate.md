# ADR-0044: Per-PR Python mutation gate on changed lines

**Date:** 2026-11-08
**Status:** Accepted

## Context

The per-PR Python leg of `mutation-pr.yml` ran only `mutants-baseline` and evaluated no mutant. Python carries roughly 1,250 survivors (issue #184) and had no ratchet, while Rust has held 0 missed on changed lines since ADR-0041. cosmic-ray 8.7.0 offers no usable exclusion or diff filter: `cr-filter-git` needs a git working directory (math runs mutants in a non-git `.mutants-tmp` copy), and `cr-filter-lines` and `cr-filter-git` mark filtered work `SKIPPED`, which `scripts/cosmic_ray_cell_status.py` deliberately scores red. A 0-survivor gate also deadlocks on any line that carries a true equivalent mutant unless equivalents can be declared.

Spec: `docs/superpowers/specs/2026-11-07-worldclass-slice8-python-pr-mutation-gate-design.md`.

## Decision

1. **Strict changed-line rule (operator, 2026-11-07).** Edit a line and you own its mutants: any survivor on a changed new-side line is red until a test kills it or `mutants-equivalent.toml` declares it equivalent. No survivor is grandfathered; a text-keyed baseline would exempt nothing, because the gate only sees lines whose text the PR changed.
2. **Deletion-based pruning.** The canonical `cosmic_ray_prune.py` (ai-config) deletes rows from a fresh session instead of marking them `SKIPPED`. `diff` keeps only mutants on changed lines and prints `kept K of T (lines L)`; `equivalents` removes declared equivalents and prints `excluded E of T`. Both check the 8.7.0 schema exactly and exit 1 with the session byte-identical on invalid input. `SKIPPED` was rejected because the cell-status script correctly treats it as red, and weakening that rule would weaken the sweep.
3. **Equivalents file.** `<project>/mutants-equivalent.toml` in all 9 Python projects, with `[[equivalent]]` entries keyed by `operator`, `function`, `line` (stripped text), `col` and `above` (stripped text of the nearest non-blank line above), plus `row` only when the group spans rows, `variant` only when more than one spec matches, and a non-empty `reason`. The layout is strict. Entries are true equivalents only. The `above` key makes an entry fail loudly, matching 0, when its line or the line above is edited or moved. **Re-confirm rule:** in `--diff` mode an entry whose mutant sits on a changed line exits 1 unless the same diff edits one of that entry's own lines, so an author who edits a line re-confirms its declared equivalents in the same PR. `mutants` (the sweep) also runs `equivalents --full-run`. pi and e hold three entries each.
4. **Sharding with an aggregator.** `mutation-py-plan` runs `mutants-diff-plan` per dir and emits units `{dir, k, n}` with `n = min(10, max(1, ceil(K/150)))`. `mutation-py` is a matrix over those units (`make mutants-diff DIFF=... MUTANT_SHARD=k/n`), each uploading a status artifact. The aggregator job `mutation-pr` keeps the name of the required status check on `master` (classic branch protection), so the protection needs no change; the former single job becomes `mutation-rs`. The aggregator is green only when every needed job succeeded (or was skipped for a reason its own `if:` explains) and `scripts/mutation-pr-verdict-python.sh` exits 0; `cancelled` and `failure` are always red.
5. **Canary.** `mutation-py-canary` runs on changes to gate files (`py_canary`), diffs against `HEAD~1` on the `limit` line in `sq/sq.py` and requires at least one killed mutant (`--min-killed 1`), so a gate that silently tests nothing goes red.
6. **Vendoring and drift test.** `scripts/cosmic_ray_prune.py` is a copy of the ai-config file, identical except line 2, which names the source sha. `tests/test_vendored_prune.py` compares against the commit line 2 names (not the live file), is skipped when that checkout or sha is absent, and warns without failing when ai-config master has moved on. Re-sync is a copy plus a line-2 edit, one math PR per canonical change.
7. **Known gap.** A PR that weakens or deletes tests creates survivors on unchanged lines and is not gated, in Python as in Rust. The monthly sweep sees it; a Backlog row records it.

## Consequences

- Touching a survivor-bearing line now costs a killing test or a declared equivalent; the roughly 1,250 existing survivors are paid down as a side effect, and slices 9..N shrink.
- The pruned diff run is far cheaper than a full run, but a large refactor still shards to up to 10 jobs per project.
- A stale or moved equivalents entry fails the author's own gate instead of silently matching nothing.
- The vendored copy can lag ai-config; the drift test detects local edits, and a re-sync PR is required for upstream changes.
- Moving pi/e progress timing to `time.monotonic()` made four declared equivalents true.
- The sweep keeps scoring survivors red as before; making the Python sweep hold 0 is a later slice.

## Related

- ADR-0041: per-PR Rust mutation ratchet on changed lines
- ADR-0042: Rust sweep holds zero missed
- ADR-0028: CLAUDE.md byte budget
- ai-config spec `2026-11-07-cosmic-ray-prune-design.md` (canonical prune script)
