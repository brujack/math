# Changelog


## Bug Fixes

- use checked_div in format_series_progress for clippy 1.95 (#28)

- correct Taylor series term count for e (Stirling undercount) (#34)

- exclude fn main() from tarpaulin and collapse multi-line macros (#35)

- fallback to serial mode when process pools unavailable (#36)

- add shared Rust cargo check wrapper

- apply cargo fmt to pi-rs, e-rs, fib-rs, sq-rs (#41)

- standardize parallel fallback message and add factorial-rs Backend line (#43)

- bump crossbeam-epoch to 0.9.20 across all Rust crates (#87)

- end six months of dead mutation runs (#91)

- run shell lint on the push path, and install what the Makefiles invoke (#110)

- use std::hint::black_box, unblocking the criterion 0.8 bump (#122)

- scale the mutant timeout, stop capping the baseline (#127)



## CI

- add --fail-under=90 gate to all Python CLIs

- add PR title lint, coverage gates, and benchmarks to Python CLIs

- add cargo-machete and ruff C901 to lint gates



## Documentation

- mark parallel-fallback-consistency done, update test counts

- 2026-05-17 retrospective + execute findings

- sync CLAUDE.md with the pytest migration and #109/#110



## Features

- add Euler's number (e) calculator (Python + Rust) (#18)

- failure-mode test matrix for all compute CLIs (#47)

- add Python mutation testing with mutmut (#54)

- add pyright type checking to all Python sub-projects (#63)

- add Criterion benchmarks to all 11 Rust crates (#70)

- swap mutmut → cosmic-ray for 8 Python sub-projects (#77)

- migrate pi and e to pytest and ruff format check

- enforce C-DEBUG and C-CONV across all 11 Rust crates (#101)

- adopt shared ruff rule set and pin 0.16.1 (#102)



## Testing

- bring all Python projects to >=90% coverage (#22)

- bring e-rs to 95% coverage via trait-based DI (#27)

- add Hypothesis and proptest property-based tests (#55)


