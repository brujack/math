# Changelog


## Bug Fixes

- flush BufWriter before returning Ok(()) (#86)

- bump crossbeam-epoch to 0.9.20 across all Rust crates (#87)

- use exact-phrase title search in SBOM issue dedup check (#89)

- end six months of dead mutation runs (#91)

- restore the standards @-include paths

- survive errexit so the classifier actually runs (#93)

- stop tee from swallowing the classifier's verdict (#94)

- capture red verdicts, which the classifier sends to stderr (#97)

- shellcheck hooks and bats, run them on a hook-only push (#103)

- scope each bench to its Criterion target, stop swallowing failures (#104)

- sync tracer with dotfiles PR #204 hardening (#108)



## CI

- lint all tracked shell at default severity (#105)



## Documentation

- update test count tables for goldbach-rs and perfect-numbers-rs

- add two new equivalent-mutation patterns to CLAUDE.md

- remove content promoted to global standards

- add July 2026 retro action items

- mark python-mutant-killing Done (PR #84)

- update test counts and CI table for PR #84

- add release-sbom-monitor implementation plan

- mark release-sbom-monitor plan Done (PR #88)

- add maintainability-pass backlog row

- spec per-project mutation testing split

- revise mutation spec after multi-lens review

- cut mutation spec to phase A after round 2 review

- fix three defects found in peer architectural review

- make MUTANTS_UNCAPPED work on the platform CI runs on

- plan for mutation testing phase A

- mark mutation testing phase A done

- record the ruff config adopted this cycle

- document the repo-level Python test runner and vendored triage_log

- name the tracer's real origin commit and expect re-syncs

- triage_log.py is vendored for its resolver, not availability



## Features

- add release SBOM vulnerability monitor (#88)

- enforce C-DEBUG and C-CONV across all 11 Rust crates (#101)

- adopt shared ruff rule set and pin 0.16.1 (#102)

- port the bash coverage tracer from dotfiles (#106)

- set the floor from CI's own measurement (#107)



## Testing

- kill surviving mutants in goldbach/perfect-numbers/amicable/collatz (#83)

- kill surviving mutants in sq, fib, perfect-numbers (#84)


