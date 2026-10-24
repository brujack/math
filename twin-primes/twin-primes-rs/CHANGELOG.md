# Changelog


## Bug Fixes

- exclude fn main() from tarpaulin and collapse multi-line macros (#35)

- add shared Rust cargo check wrapper

- bump crossbeam-epoch to 0.9.20 across all Rust crates (#87)

- end six months of dead mutation runs (#91)

- use std::hint::black_box, unblocking the criterion 0.8 bump (#122)

- scale the mutant timeout, stop capping the baseline (#127)



## Documentation

- 2026-05-17 retrospective + execute findings



## Features

- add twin-primes-rs binary (#11)

- failure-mode test matrix for all compute CLIs (#47)

- add Criterion benchmarks to all 11 Rust crates (#70)

- enforce C-DEBUG and C-CONV across all 11 Rust crates (#101)



## Testing

- raise coverage from 76% to 95% with injectable I/O (#32)

- add Hypothesis and proptest property-based tests (#55)


