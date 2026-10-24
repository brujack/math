# Changelog


## Bug Fixes

- resolve ruff and clippy lint errors surfaced by CI

- correct div_ceil conversion for odd-integer count in sieve

- exclude fn main() from tarpaulin and collapse multi-line macros (#35)

- add shared Rust cargo check wrapper

- bump crossbeam-epoch to 0.9.20 across all Rust crates (#87)

- end six months of dead mutation runs (#91)

- use std::hint::black_box, unblocking the criterion 0.8 bump (#122)

- scale the mutant timeout, stop capping the baseline (#127)



## Documentation

- fill gaps in CLAUDE.md files identified by audit

- add CLAUDE.md self-maintenance instructions to all three files

- 2026-05-17 retrospective + execute findings



## Features

- add lint target to all Makefiles; test depends on lint

- add perfect squares calculator (Python + Rust) (#1)

- failure-mode test matrix for all compute CLIs (#47)

- add Criterion benchmarks to all 11 Rust crates (#70)

- enforce C-DEBUG and C-CONV across all 11 Rust crates (#101)



## Refactoring

- split install_deps.sh into per-project scripts



## Testing

- raise coverage from 57% to 96% with injectable I/O (#30)

- add Hypothesis and proptest property-based tests (#55)


