# Changelog


## Bug Fixes

- stop tempdir leaks, cap file size (#211)

- signal-safe TMPDIR cleanup, diagnosable coverage flake (#212)

- read-only mutation-pr token, validated counts, gate ignores dispatch runs (#213)

- classifier rejects non-number counts; pi/e drop equivalent max; crate list checked (#215)

- badges publish after auto-merge; actionlint via install-deps; classifier rejects ambiguous outcomes (#216)

- disable core dumps in mutation runs (#218)



## CI

- per-PR Rust mutation ratchet on changed lines (#206)

- Rust sweep holds zero missed (#208)

- per-PR Python mutation gate on changed lines (#219)



## Documentation

- mark slice 5 rust PR mutation ratchet done

- worldclass slice 6 rust sweep ratchet

- slice 6 round 1 multi-lens review

- slice 6 round 1 lens revisions and dispositions

- slice 6 round 2 multi-lens review

- slice 6 round 2 lens revisions and dispositions

- slice 6 round 3 scoped review fixes

- approve slice 6 rust sweep ratchet spec

- slice 6 rust sweep ratchet plan

- mark slice 6 rust sweep ratchet done

- tracer-timing flake, runner-loss row update

- amend 0024 with file cap and run-local TMPDIR

- double-TERM can interrupt mutants TMPDIR cleanup

- math#212 shipped; tracer flake and crate-list rows

- math#213 shipped three rows; null/false count row

- runner loss persists after the file cap (run 42157905568)

- worldclass slice 7 sharded Rust sweep with hang guard

- slice 7 revised to 4 GiB cap and slice shards after round-1 review

- slice 7 re-specified to disable mutation core dumps

- slice 7 round-3 multi-lens review

- slice 7 round-3 dispositions applied; approved

- slice 7 R4 amended after scoped re-review

- slice 7 mutant core dumps implementation plan

- slice 7 done (math#218); Rust SIGTERM test flaked once under tracer

- runner loss fixed; V1 sweep 42328612206 11/11 green

- drop dead master ruleset row; ruleset deleted

- worldclass slice 8 per-PR Python mutation gate

- slice 8 round 1 lens findings and revisions

- slice 8 round 1 dispositions; mandatory row in equivalents

- slice 8 round 2 findings, dispositions and the above key

- slice 8 round 3 fixes; review closed

- approve slice 8 Python PR mutation gate

- slice 8 Python PR mutation gate plan

- mark slice 8 Done; backlog bash-coverage flake

- record slice-8 V1, V3, V4 and V6 evidence

- drop empty-plan backlog row, exercised by math#221

- record second bash-coverage SIGTERM flake



## Refactoring

- one exit-code reader and Rust setup macro; pin pi/e render values (#214)


