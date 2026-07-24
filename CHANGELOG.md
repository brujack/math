# Changelog


## Bug Fixes

- install cargo-machete in all Rust workflows (#74 partial) (#75)

- make cosmic-ray Python mutation check advisory, not a required gate (#82)

- flush BufWriter before returning Ok(()) (#86)

- bump crossbeam-epoch to 0.9.20 across all Rust crates (#87)

- use exact-phrase title search in SBOM issue dedup check (#89)



## CI

- add pytest and pytest-cov to all Python workflow pip installs

- add mutation-pr per-PR gate workflow (#81)



## Documentation

- ADR-0022 cosmic-ray supersedes mutmut

- pointer stub per ADR-0020 (#80)

- update README and add ADR-0023 for pytest migration

- add bug-scan to Phase 3 chain

- update test count tables for goldbach-rs and perfect-numbers-rs

- add two new equivalent-mutation patterns to CLAUDE.md

- remove content promoted to global standards

- add July 2026 retro action items

- mark python-mutant-killing Done (PR #84)

- update test counts and CI table for PR #84

- add release-sbom-monitor implementation plan

- mark release-sbom-monitor plan Done (PR #88)



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

- add release SBOM vulnerability monitor (#88)



## Refactoring

- adopt canonical .claude/memory + .claude/retrospectives layout (ADR-0014) (#78)



## Testing

- kill surviving mutants in goldbach/perfect-numbers/amicable/collatz (#83)

- kill surviving mutants in sq, fib, perfect-numbers (#84)


