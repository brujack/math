# Knowledge Directory — math

Reference material for the math repo. Not instructions, not workflows, not coding conventions — reference documents for understanding algorithms, performance characteristics, and curated research.

## Categories

### Architecture docs (non-ADR)

Descriptions of how the repo works that are too detailed for CLAUDE.md but don't rise to the level of an architectural _decision_ record. Examples:

- How the BATS failure-mode test infrastructure is wired (shared fixtures, PATH mocks)
- The injectable I/O pattern and why it's used across all Rust CLIs
- How Python and Rust CLIs are structured and how coverage is measured for each
- The CI matrix structure (per-language jobs, tarpaulin Linux vs macOS gap)

ADRs (`docs/adr/`) record _decisions_. Architecture docs here describe _how things work_.

### Saved web research

Curated findings from the web-research skill (Exa + Firecrawl) worth preserving across sessions. Save here instead of re-fetching next time. Examples:

- Algorithm complexity notes (Chudnovsky, Lucas-Lehmer, prime sieve trade-offs)
- Numerical library behavior (GMP, MPFR, mpmath precision limits)
- Rust math crate comparisons and API notes

Use file names like `research-<topic>.md` to distinguish from architecture docs.

### Other reference material

Reference sheets for algorithms, library choices, or cross-cutting patterns that don't fit the above categories.

## What does not belong here

| Content type                         | Where it lives                                                 |
| ------------------------------------ | -------------------------------------------------------------- |
| Instructions / behavioral directives | `CLAUDE.md`                                                    |
| Reusable workflows                   | `~/.claude/skills/math-new-cli/`                               |
| Coding conventions                   | `~/.claude/standards/rust.md`, `~/.claude/standards/python.md` |
| Plans and specs                      | `docs/superpowers/` or `docs/cursor/`                          |
| Architectural decisions              | `docs/adr/`                                                    |

## File naming

`<topic>.md` or `research-<topic>.md` — lowercase with hyphens. One topic per file.

## Index

Add a row to this table when you create a file:

| File                                                                               | Category      | Contents                                                                  |
| ---------------------------------------------------------------------------------- | ------------- | ------------------------------------------------------------------------- |
| [retrospectives/2026-05-17.md](retrospectives/2026-05-17.md)                       | Retrospective | 30-day review: coverage push + 5 new CLI velocity sprint                  |
| [retrospectives/2026-06-retrospective.md](retrospectives/2026-06-retrospective.md) | Retrospective | 15-day quality sprint: benchmarks, pyright, mutation testing, SBOM/cosign |
| [retrospectives/2026-06-05.md](retrospectives/2026-06-05.md)                       | Retrospective | 4-day follow-through: ADR catch-up, mutation fixes, sha256sum CI fix      |
