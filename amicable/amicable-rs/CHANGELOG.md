# Changelog


## Bug Fixes

- add mutants target per math-new-cli skill requirement

- correct Hypothesis test oracle in test_pairs_within_limit (#57)

- flush BufWriter before returning Ok(()) (#86)

- bump crossbeam-epoch to 0.9.20 across all Rust crates (#87)

- end six months of dead mutation runs (#91)

- restore the lint gate on make test (#109)

- run shell lint on the push path, and install what the Makefiles invoke (#110)

- use std::hint::black_box, unblocking the criterion 0.8 bump (#122)

- scale the mutant timeout, stop capping the baseline (#127)



## CI

- add --fail-under=90 gate to all Python CLIs

- add PR title lint, coverage gates, and benchmarks to Python CLIs



## Documentation

- sync CLAUDE.md with the pytest migration and #109/#110



## Features

- amicable pairs — Python + Rust CLI with proper-divisor sum sieve (#52) (#52)

- add Python mutation testing with mutmut (#54)

- add pyright type checking to all Python sub-projects (#63)

- upgrade pyright to standard mode for 6 sub-projects (#64)

- add Criterion benchmarks to all 11 Rust crates (#70)

- swap mutmut → cosmic-ray for 8 Python sub-projects (#77)

- migrate to pytest and ruff format check

- enforce C-DEBUG and C-CONV across all 11 Rust crates (#101)

- adopt shared ruff rule set and pin 0.16.1 (#102)



## Testing

- add Hypothesis and proptest property-based tests (#55)

- add CLI entry-point integration tests for amicable, collatz, perfect-numbers, factorial (#67)

- kill surviving mutants in goldbach/perfect-numbers/amicable/collatz (#83)


