# Changelog


## Bug Fixes

- exclude fn main() from tarpaulin and collapse multi-line macros (#35)

- fallback to serial mode when process pools unavailable (#36)

- add shared Rust cargo check wrapper

- standardize parallel fallback message and add factorial-rs Backend line (#43)

- use mutants.toml exclusions for equivalent mutations (#71)

- bump crossbeam-epoch to 0.9.20 across all Rust crates (#87)

- end six months of dead mutation runs (#91)

- run shell lint on the push path, and install what the Makefiles invoke (#110)

- use std::hint::black_box, unblocking the criterion 0.8 bump (#122)

- scale the mutant timeout, stop capping the baseline (#127)



## CI

- add --fail-under=90 gate to all Python CLIs

- add PR title lint, coverage gates, and benchmarks to Python CLIs



## Documentation

- mark parallel-fallback-consistency done, update test counts

- 2026-05-17 retrospective + execute findings

- update factorial-rs test table; remove resolved mutants backlog

- sync CLAUDE.md with the pytest migration and #109/#110



## Features

- add factorial calculator (Python + Rust, prime swing algorithm) (#19)

- failure-mode test matrix for all compute CLIs (#47)

- add Python mutation testing with mutmut (#54)

- flaky-test tracking via nextest CI profile and test-metrics artifacts (#59)

- add pyright type checking and fix macOS spawn deadlock (#62)

- upgrade pyright to standard mode for 6 sub-projects (#64)

- add Criterion benchmarks to all 11 Rust crates (#70)

- swap mutmut → cosmic-ray for 8 Python sub-projects (#77)

- migrate to pytest and ruff format check

- enforce C-DEBUG and C-CONV across all 11 Rust crates (#101)

- adopt shared ruff rule set and pin 0.16.1 (#102)



## Testing

- raise coverage from 68% to 97.58% with injectable I/O (#31)

- add Hypothesis and proptest property-based tests (#55)

- add CLI entry-point integration tests for amicable, collatz, perfect-numbers, factorial (#67)

- kill <=→< sieve mutant; skip equivalent mutants


