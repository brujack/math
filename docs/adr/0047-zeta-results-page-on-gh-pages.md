# ADR-0047: Publish the zeta results page on gh-pages from a local generator

**Date:** 2026-11-25
**Status:** Accepted

## Context

The `zeta` runs that matter (`zeta 7 --refine` takes tens of hours and several gigabytes of zero tables) are far too large and too slow for CI. The repository already serves GitHub Pages from the legacy `gh-pages` branch, which `benchmarks.yml` writes under `dev/bench/`, so a results page has to share that branch without disturbing the benchmark output.

Spec: `docs/superpowers/specs/2026-11-24-zeta-results-page-design.md`. Plan: `docs/superpowers/plans/2026-11-24-zeta-results-page.md`.

## Decision

1. **Local generator.** `scripts/zeta_results.py` runs on the operator's machine over finished run directories. It takes `--runs-toml`, one or more `--run <id>=<run dir>`, `--out` and `--runs-out`, and writes a static page (no JavaScript, no external request) into `zeta/results/site/` and a copy of each run's `out.txt` and `err.txt` into `zeta/results/runs/`.
2. **Committed site.** The generated site is committed under `zeta/results/site/`, so the page that is published is the page that was reviewed in the pull request.
3. **Dispatch-only deploy.** The workflow `zeta results pages` (`.github/workflows/zeta-results-pages.yml`) is `workflow_dispatch` only and runs only from `master`. It replaces `zeta/` on `gh-pages` with a copy of the committed site, writes `deployed-from.txt` with the master SHA, and `scripts/gh-pages-zeta-guard.sh` refuses any change outside `zeta/`.
4. **Shared concurrency group.** The deploy job uses `concurrency: group: gh-pages` with `cancel-in-progress: false`, the same group as `benchmarks.yml`, so the two writers of `gh-pages` never run at once and neither is cancelled.
5. **Fail closed.** The generator refuses any input that fails a check: provenance read from `/usr/bin/time -v`, and an exact-midpoint cross-check of every derived figure against the values the CLI itself printed. A refusal means the input is wrong, not the generator.
6. **Guarded output targets.** The generator refuses `.`, `..` and the current directory, symlinked targets, `.tmp` and `.old` siblings, targets that overlap an input or each other, and any existing non-empty directory that lacks the `.zeta-results` marker.

## Consequences

- Page figures are operator-attested: the raw runs never enter the repository. They are cross-checked against the CLI's own printed values at generation time, and CI re-verifies the tables derived from the committed `out.txt` and `err.txt`.
- The generator writes a `.zeta-results` marker into every tree it produces and only replaces a non-empty directory that carries it. A mis-aimed `--out` therefore cannot replace a directory the generator did not create. The deploy step deletes the marker, so it is never published.
- Publishing is a deliberate act: a new page needs a regenerate, a pull request and a manual dispatch.
- The workflow and the benchmark job serialise on one group, so a deploy can wait behind a benchmark run.
- matplotlib is a build-time dependency of the generator only; the pinned version is shared across install sites.

## Related

- ADR-0046: Shard the Rust mutation runs (CI cannot hold long runs).
- `zeta/README.md` section "Results page".
