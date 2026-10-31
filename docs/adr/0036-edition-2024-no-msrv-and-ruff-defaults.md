# ADR-0036: Edition 2024 with unsafe forbidden and no MSRV; ruff extends its default rules

**Date:** 2026-10-31
**Status:** Accepted

## Context

An audit of math's Rust and Python standards against upstream guidance (spec `docs/superpowers/specs/2026-10-31-rust-python-standards-tier1-design.md`) found several gaps:

- **Rust edition:** all 11 crates were on edition 2021. Edition 2024 shipped with Rust 1.85, and no later edition exists.
- **Rust lints:** none of the 11 crates forbade `unsafe`, even though none used it.
- **ruff:** math pinned ruff 0.16.4 but used an explicit `select`. That replaces ruff's default rule set (413 rules since 0.16.0), so none of the defaults applied.

Measured costs, all in the spec:

- **Edition 2024:** `cargo fix --edition` changed 0 source lines. The work was `cargo fmt` under the 2024 style edition, plus one clippy `collapsible_if` that 2024 let-chains now flag.
- **ruff defaults:** 89 findings, all fixable without changing behaviour.

**Declaring `rust-version` (an MSRV) was considered and rejected.** Two independent review lenses gave different reasons:

- **Nothing reads it.** math ships binaries built on stable, publishes nothing to crates.io, and its crates have no consumers.
- **It would stall Renovate.** Renovate groups the caret-range cargo updates into one PR of `--precise` lock bumps, and `--precise` bypasses resolver 3's MSRV fallback. So the first dependency that raised its own MSRV past ours would fail a blocking MSRV job. That would hold back the whole group and force a hand-edited bump across all 11 crates. `clap_builder` 4.6 already requires 1.85, edition 2024's floor.

## Decision

- **Rust (all 11 crates, math#187):**
  - `edition = "2024"`.
  - `[lints.rust] unsafe_code = "forbid"`.
  - No `rust-version`, and no MSRV CI job.
  - `style_edition = "2024"` in the rustfmt template, so editors format the same way cargo does.
  - `tests/test_crate_uniformity.py` pins all of this. It also fails if any crate declares `rust-version`.
- **Python (math#189):**
  - The root `ruff.toml` uses `extend-select` with the existing extras, so the pinned ruff's default rule set applies.
  - `tests/test_ruff_config.py` compares the whole parsed file to one expected value, so any key that could switch the defaults off fails it, `extend-ignore` included.
  - New defaults arrive only with a deliberate ruff pin bump, gated by that PR's `make lint`.

## Consequences

- **Rust edition:** the crates are on the current edition, and new `unsafe` code cannot land without changing the lint.
- **No MSRV:** documentation names "current stable Rust" instead of a minimum version, and a toolchain floor is never an unchecked claim. The cost is that nothing tells someone on an old toolchain why their build fails. That is accepted because math distributes binaries, not source crates.
- **ruff:** math receives ruff's curated defaults, including the SIM, FURB, PERF and PT subsets, without hand-maintaining the list. A ruff pin bump can now add new findings, and that bump's PR has to fix them.
- **Left for later:** clippy `pedantic` (about 300 warnings), an `unwrap_used`/`expect_used` policy (729 hits, mostly tests) and pyright `strict` (2,412 errors). These are Backlog rows that carry the spec's measurements.

## Related

- Spec: [`docs/superpowers/specs/2026-10-31-rust-python-standards-tier1-design.md`](../superpowers/specs/2026-10-31-rust-python-standards-tier1-design.md)
- Plan: [`docs/superpowers/plans/2026-10-31-rust-python-standards-tier1.md`](../superpowers/plans/2026-10-31-rust-python-standards-tier1.md)
- [ADR-0032](0032-per-project-files-rendered-from-templates.md): per-project files rendered from templates (the rustfmt template).
- [ADR-0035](0035-mit-licence-cargo-deny-and-lgpl-notices.md): MIT licence, cargo-deny and LGPL notices (PR 2 of the same plan).
