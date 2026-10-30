# Changelog


## Bug Fixes

- install nextest and machete before tests (#157)

- ignore superseded check runs; record release backlog rows (#158)

- drop rejected CHANGELOG push; make SBOM monitor skips visible (#159)

- stop continue-on-error hiding failures (#160)

- handle closed stdin in fib.py and sq.py (#161)

- hold draft PRs green instead of failing (#162)

- stop building file paths from env and git output (#163)

- pin and checksum the Snyk CLI (#164)

- pin pyright and every cargo install to one version (#165)

- make <crate> only builds; make install to ~/.local/bin (#166)

- make all 11 Makefiles and rustfmt.toml identical (#167)

- render Makefile, rustfmt and release workflows from templates (#168)

- render the 11 CI workflows and nextest config from templates (#169)

- one tested install_deps.sh for all 11 crates (#170)

- keep mpmath precision through the spawn conversion worker (#174)

- stop holding the stderr lock across run() in pi, prime and e (#175)

- wake progress threads when work finishes instead of after a 200 ms sleep (#176)

- scan the crate templates with the github-actions manager (#179)



## CI

- prebuilt CI tools, parallel coverage job and parallel bats (#177)



## Documentation

- one CLI contract for all 19 programs, uniform Python files

- align math's direct-to-master docs rule with the fleet

- record Step 8 multi-lens review, round 1

- revision 2 after round-1 review dispositions

- revision 3 after round-2 review dispositions

- revision 4 after round-3 risk review

- record operator approval of uniform Python CLI spec

- uniform Python CLI and project files, 19 tasks

- collatz N>8 memory peak above its warning

- claude_md_budget gate takes a revision

- drop the pi/e closed-stdin row fixed by math#171

- mark uniform-python-cli Done

- describe the rendered Python installer in three READMEs

- uniform Rust CLI contract and Cargo.toml shape

- Rust spec round-1 revisions and parallel local tests

- Rust spec round-2 dispositions

- Rust spec adds system GMP and MPFR (R20)

- Rust spec adds the nextest time bound (R21)

- Rust spec round-2 review record

- Rust spec round 3, drop system GMP, bound coverage job

- Rust spec bound sized from CI (15 s x 3)

- approve the Rust CLI contract and Cargo.toml spec

- uniform Rust CLI contract and Cargo.toml plan, non-goal check

- record math#180 P1 merge and the removed pre-push skip



## Features

- one CLI contract for the 8 Python programs (#171)

- run every Python project at standard via an exact gmpy2 stub (#172)

- one Cargo.toml shape, crate CLAUDE.md, concurrent suites, bounded tests (#180)



## Refactoring

- render the 8 Python projects' files from templates (#173)


