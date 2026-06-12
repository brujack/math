# Changelog


## Bug Fixes

- replace xml.etree with defusedxml in test_metrics.py (#69)

- use mutants.toml exclusions for equivalent mutations (#71)

- strip directory prefix from sha256sum output in release workflows (#73)

- install cargo-machete in factorial-rs workflow and use CARGO_BIN (#74)

- install cargo-machete in all Rust workflows (#74 partial) (#75)



## CI

- make snyk-scan advisory (continue-on-error)

- add release workflows for collatz, goldbach, amicable, perfect-numbers (#68)

- standardize upload-artifact to @v7 across all Rust workflows

- bump checkout →v6, cosign →v4, upload-artifact stragglers →v7

- enable regression alerts at 130% threshold

- fix rust-cache error and input injection

- align math release workflows with etch-cli strategy (#72)

- reduce per-mutant timeout 120s → 30s

- fail workflow on regression alert

- add cargo-machete and ruff C901 to lint gates



## Documentation

- complete README coverage for all 11 projects

- document pyright setup and mode table

- pip-audit CI per-sub-project advisory step

- pip-audit CI implementation plan

- CLI integration tests for amicable, collatz, perfect-numbers, factorial

- CLI integration tests implementation plan

- mark criterion-benchmarks Done

- document defusedxml pip install requirement in factorial-rs workflow

- add dev-cycle improvements to backlog

- remove benchmark alerts — done

- add Criterion benchmarks, pyright, pip-audit, and CLI tests to README

- add surviving mutants from 2026-06-01 run

- update factorial-rs test table; remove resolved mutants backlog

- add ADRs and update CLAUDE.md after learnings audit

- add ADR-0011 through ADR-0017 for recent decisions

- add ADR-0018 through ADR-0021 for April decisions

- trim DoD to repo-specific addenda

- remove sections duplicated in global CLAUDE.md

- add 2026-06-05 retrospective and update knowledge index



## Features

- add pyright type checking and fix macOS spawn deadlock (#62)

- add pyright type checking to all Python sub-projects (#63)

- upgrade pyright to standard mode for 6 sub-projects (#64)

- add pip-audit advisory security step to all Python workflows (#65)

- add git-cliff config and make target (#66)

- add Criterion benchmarks to all 11 Rust crates (#70)



## Testing

- add CLI integration tests for collatz and goldbach (#61)

- add CLI entry-point integration tests for amicable, collatz, perfect-numbers, factorial (#67)

- kill <=→< sieve mutant; skip equivalent mutants


