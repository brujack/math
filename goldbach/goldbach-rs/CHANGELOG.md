# Changelog


## Bug Fixes

- bump crossbeam-epoch to 0.9.20 across all Rust crates (#87)

- end six months of dead mutation runs (#91)

- use std::hint::black_box, unblocking the criterion 0.8 bump (#122)

- scale the mutant timeout, stop capping the baseline (#127)



## Documentation

- 2026-05-17 retrospective + execute findings

- update test count tables for goldbach-rs and perfect-numbers-rs



## Features

- Goldbach pairs — Rust CLI for all pairs up to 10^N (#50)

- add Criterion benchmarks to all 11 Rust crates (#70)

- enforce C-DEBUG and C-CONV across all 11 Rust crates (#101)



## Testing

- add Hypothesis and proptest property-based tests (#55)

- add CLI integration tests for collatz and goldbach (#61)

- kill surviving mutants in goldbach/perfect-numbers/amicable/collatz (#83)


