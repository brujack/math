# ADR 0009: Criterion benchmarks for performance regression detection

- **Date:** 2026-05-23
- **Status:** Accepted

## Context

The math repo contains 11 Rust crates implementing high-performance algorithms (Chudnovsky π, prime swing factorial, segmented sieve, etc.). These are correctness-first but also performance-sensitive — regressions from dependency upgrades, compiler changes, or algorithm refactors should be visible before they reach master.

Without benchmarks, the only signal for a performance regression is manual observation ("it feels slower") or a user report. Coverage and mutation testing verify correctness; neither detects performance changes.

`cargo bench` with Criterion is the standard Rust micro-benchmark harness. It uses statistical analysis (sampling + outlier rejection) to produce stable, reproducible measurements and generates HTML reports. The `benchmark-action/github-action-benchmark` action can store results over time on a `gh-pages` branch and alert on regressions.

## Decision

Add Criterion benchmarks to all 11 Rust crates and a monthly CI workflow (`benchmarks.yml`) that runs them and tracks results over time.

**Each crate gets:**

- `benches/<name>_bench.rs` with a representative benchmark of the primary algorithm
- `make bench` target (`cargo bench`)
- `[[bench]]` + `criterion` dev-dependency in `Cargo.toml`

**CI workflow:**

- Trigger: `workflow_dispatch` + monthly schedule (`cron: "0 2 1 * *"`)
- Stores results in `gh-pages` branch under `dev/bench/`
- Alert threshold: **130%** (regression alert fires when a benchmark is >30% slower than the prior run)
- `fail-on-alert: true` — the monthly workflow fails when a regression exceeds the threshold, ensuring regressions create a visible GitHub Actions failure rather than a comment that is easy to miss. Does not block PRs — the benchmark workflow is not in the PR merge gate.

**Alert threshold rationale:** Criterion results on GitHub-hosted Ubuntu runners have inherent variance from shared hardware, thermal throttling, and load spikes. A 10–15% threshold generates constant false-positive alerts. 30% is large enough to signal real algorithmic or dependency regressions while ignoring normal measurement noise.

## Consequences

- Performance regressions of >30% fail the monthly benchmark workflow and surface as visible commit comments on the `gh-pages` branch push
- Results accumulate over time, making it possible to correlate regressions with specific commits or dependency bumps
- The workflow runs monthly, not on every PR — it is a monitoring tool, not a merge gate
- Developers can run `make bench` locally to get Criterion HTML reports in `target/criterion/`
- `fn main()` exclusion and `rustfmt.toml` settings already in place for tarpaulin coverage do not interfere with Criterion (benches are separate binary targets)

## Related

- ADR 0002: Python + Rust dual implementation strategy
- ADR 0006: Per-project CI workflows with test-before-build gate
- PR #70: `feat: add Criterion benchmarks to all 11 Rust crates`
- Commit `91c09bf`: `ci(benchmarks): enable regression alerts at 130% threshold`
