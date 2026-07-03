# Changelog


## Bug Fixes

- use mutants.toml exclusions for equivalent mutations (#71)

- strip directory prefix from sha256sum output in release workflows (#73)

- install cargo-machete in factorial-rs workflow and use CARGO_BIN (#74)

- install cargo-machete in all Rust workflows (#74 partial) (#75)

- make cosmic-ray Python mutation check advisory, not a required gate (#82)



## CI

- align math release workflows with etch-cli strategy (#72)

- reduce per-mutant timeout 120s → 30s

- fail workflow on regression alert

- add cargo-machete and ruff C901 to lint gates

- add pytest and pytest-cov to all Python workflow pip installs

- add mutation-pr per-PR gate workflow (#81)



## Documentation

- add ADRs and update CLAUDE.md after learnings audit

- add ADR-0011 through ADR-0017 for recent decisions

- add ADR-0018 through ADR-0021 for April decisions

- trim DoD to repo-specific addenda

- remove sections duplicated in global CLAUDE.md

- add 2026-06-05 retrospective and update knowledge index

- ADR-0022 cosmic-ray supersedes mutmut

- pointer stub per ADR-0020 (#80)

- update README and add ADR-0023 for pytest migration

- add bug-scan to Phase 3 chain

- update test count tables for goldbach-rs and perfect-numbers-rs

- add two new equivalent-mutation patterns to CLAUDE.md

- remove content promoted to global standards



## Features

- adopt 10-80-10 execution cycle (ai-config ADR-0009/0010) (#76)

- swap mutmut → cosmic-ray for 8 Python sub-projects (#77)

- migrate to pytest and ruff format check

- migrate to pytest and ruff format check

- migrate pi and e to pytest and ruff format check

- migrate to pytest and ruff format check

- migrate to pytest and ruff format check

- migrate to pytest and ruff format check

- migrate to pytest and ruff format check

- math adds python.md + rust.md language standards



## Refactoring

- adopt canonical .claude/memory + .claude/retrospectives layout (ADR-0014) (#78)



## Testing

- kill surviving mutants in goldbach/perfect-numbers/amicable/collatz (#83)


