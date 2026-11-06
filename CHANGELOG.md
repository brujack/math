# Changelog


## Bug Fixes

- stop tempdir leaks, cap file size (#211)

- signal-safe TMPDIR cleanup, diagnosable coverage flake (#212)

- read-only mutation-pr token, validated counts, gate ignores dispatch runs (#213)

- classifier rejects non-number counts; pi/e drop equivalent max; crate list checked (#215)

- badges publish after auto-merge; actionlint via install-deps; classifier rejects ambiguous outcomes (#216)



## CI

- one rust mutation job per crate (#202)

- per-PR Rust mutation ratchet on changed lines (#206)

- Rust sweep holds zero missed (#208)



## Documentation

- approve worldclass slice 3

- worldclass slice 3 rust mutation matrix

- mark worldclass slice 3 done (math#202)

- record first matrix sweep and V2 result

- record slice 2 mutation V1 result

- worldclass slice 4 rust mutation survivors

- slice 4 multi-lens review round 1

- slice 4 round-1 dispositions and fixes

- slice 4 multi-lens review round 2

- slice 4 round-2 fixes to drift test

- approve worldclass slice 4

- worldclass slice 4 rust mutation survivors

- mark worldclass slice 4 done (math#203)

- correct e-rs cfg(unix) row line-shift note

- record slice 4 V1 sweep result

- worldclass slice 5 per-PR Rust mutation ratchet

- slice 5 round 1 lens revisions

- slice 5 round 2 lens revisions and timeout classification

- slice 5 round 3 lens revisions

- slice 5 round 4 lens revisions

- slice 5 scoped re-review wording fixes

- approve slice 5 rust PR mutation ratchet spec

- slice 5 rust PR mutation ratchet plan

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



## Refactoring

- one exit-code reader and Rust setup macro; pin pi/e render values (#214)



## Testing

- kill surviving mutants in five crates (#203)

- kill host-dependent mutation survivors (#204)


