# Changelog


## Bug Fixes

- always write output file in sq.py and sq-rs (#2)

- output format as "perfect square | square root" in sq.py and sq-rs (#3)

- exclude fn main() from tarpaulin and collapse multi-line macros (#35)

- add shared Rust cargo check wrapper

- apply cargo fmt to pi-rs, e-rs, fib-rs, sq-rs (#41)

- raise fib-rs and sq-rs coverage above 90% after cargo fmt (#42)

- bump crossbeam-epoch to 0.9.20 across all Rust crates (#87)

- end six months of dead mutation runs (#91)

- run shell lint on the push path, and install what the Makefiles invoke (#110)

- use std::hint::black_box, unblocking the criterion 0.8 bump (#122)

- scale the mutant timeout, stop capping the baseline (#127)



## CI

- add --fail-under=90 gate to all Python CLIs

- add PR title lint, coverage gates, and benchmarks to Python CLIs



## Documentation

- 2026-05-17 retrospective + execute findings

- update test counts and CI table for PR #84

- sync CLAUDE.md with the pytest migration and #109/#110



## Features

- add perfect squares calculator (Python + Rust) (#1)

- failure-mode test matrix for all compute CLIs (#47)

- add Python mutation testing with mutmut (#54)

- add pyright type checking to all Python sub-projects (#63)

- upgrade pyright to standard mode for 6 sub-projects (#64)

- add Criterion benchmarks to all 11 Rust crates (#70)

- swap mutmut → cosmic-ray for 8 Python sub-projects (#77)

- migrate to pytest and ruff format check

- enforce C-DEBUG and C-CONV across all 11 Rust crates (#101)

- adopt shared ruff rule set and pin 0.16.1 (#102)



## Testing

- bring all Python projects to >=90% coverage (#22)

- bring sq-rs to 96% coverage via trait-based DI (#25)

- add Hypothesis and proptest property-based tests (#55)

- kill surviving mutants in sq, fib, perfect-numbers (#84)


