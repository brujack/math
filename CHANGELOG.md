# Changelog


## Bug Fixes

- end six months of dead mutation runs (#91)

- restore the standards @-include paths

- survive errexit so the classifier actually runs (#93)

- stop tee from swallowing the classifier's verdict (#94)

- capture red verdicts, which the classifier sends to stderr (#97)

- shellcheck hooks and bats, run them on a hook-only push (#103)

- scope each bench to its Criterion target, stop swallowing failures (#104)

- sync tracer with dotfiles PR #204 hardening (#108)

- restore the lint gate on make test (#109)

- run shell lint on the push path, and install what the Makefiles invoke (#110)

- pin dtolnay/rust-toolchain to a SHA digest (#113)

- inline the shared preset, which a public repo cannot fetch (#114)

- use std::hint::black_box, unblocking the criterion 0.8 bump (#122)



## CI

- lint all tracked shell at default severity (#105)

- hold unlabelled Renovate PRs for triage (#120)



## Documentation

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

- sync CLAUDE.md with the pytest migration and #109/#110

- backlog the download-artifact v8 / continue-on-error interaction

- cite action.yml for the download-artifact digest-mismatch option

- record the 53-test root suite and backlog the inert master ruleset

- backlog the undocumented bench black_box import convention



## Features

- enforce C-DEBUG and C-CONV across all 11 Rust crates (#101)

- adopt shared ruff rule set and pin 0.16.1 (#102)

- port the bash coverage tracer from dotfiles (#106)

- set the floor from CI's own measurement (#107)

- wire root-scope Python into make lint and the push path (#111)


