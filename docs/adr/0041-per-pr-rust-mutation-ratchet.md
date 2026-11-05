# ADR-0041: Per-PR Rust mutation ratchet on changed lines

**Date:** 2026-11-05
**Status:** Accepted

## Context

Slice 4 brought all 11 Rust crates to 0 missed mutants (full sweep run 41952665142). Nothing
held that line. `scripts/mutation-classify.sh` scores survivors (cargo-mutants exit 2) green,
so the monthly sweep (ADR-0040) never goes red for a new survivor.

The only per-PR mutation step never tested anything. `mutation-pr.yml` wrote a repo-root diff
(`factorial/factorial-rs/src/lib.rs`) and ran `cargo mutants --in-diff` inside the crate, where
cargo-mutants matches paths against `src/lib.rs`. They never matched: the output was
`INFO No mutants to filter`, exit 0 (measured 2026-11-05, cargo-mutants 27.1.0). Only
factorial-rs had a step at all, with a fixed `--timeout 30`.

Separately, GNU make exits 2 whenever a recipe fails, and 2 is in the classifier's green set.
A baseline failure (4), timeouts (3) or a memory-cap kill therefore read as "survivors found".

The 2026-08-01 per-project spec rejected two things this design could resemble:

- **A committed per-crate missed baseline.** A hand-tuned number drifts with source edits and
  rustc updates, loosens only upward, and its false reds blank a month's report.
- **Advisory per-PR legs.** No verdict could differ, and they cost 11 `cargo install` runs per
  PR. It deferred a blocking gate until after a first completed sweep, which ADR-0040 delivered.

Spec: `docs/superpowers/specs/2026-11-05-worldclass-slice5-rust-pr-mutation-ratchet-design.md`.

## Decision

1. **Block on missed mutants of changed lines.** `mutation-pr.yml` runs
   `scripts/mutation-pr-run.sh "origin/${GITHUB_BASE_REF}" <rs_dirs>` for every crate whose
   `src/**/*.rs` the PR changes (selected by `scripts/mutation-pr-detect.sh`, crates from
   `git ls-files '*/*-rs/Cargo.toml'`). The missed limit is 0; timeouts stay green.
2. **The diff is per crate and crate-relative**, so cargo-mutants paths match.
3. **No stored number.** The rule is "0 missed among mutants of the changed lines".
4. **A canary guards the gate.** When a gate file changes, an amicable-rs run with
   `--min-caught 1` proves the gate still catches mutants.
5. **Verdicts read `mutants.out/exit-code`.** `make mutants` and `make mutants-diff` both write
   cargo-mutants' status there, and both workflows classify on it. A missing file is red.
   `scripts/mutation-classify.sh` takes optional `max_missed` and `min_caught` arguments; the
   monthly sweep passes neither.
6. **Every missed mutant on a changed line gets a killing test**, glue included. `exclude_re`
   is only for true equivalents.
7. **Local repro:** `scripts/mutation-pr-diff.sh origin/master <crate> /tmp/d.diff && make -C <crate> mutants-diff DIFF=/tmp/d.diff`.

## Consequences

- A PR that adds an unkilled mutant on a changed line fails `mutation-pr`, which
  `scripts/ci-gate.sh` treats as required, so auto-merge holds it.
- A crate's PR runs only that crate's mutants, with one `cargo install`.
- The monthly sweep's verdict rules are unchanged; only its exit-code source changed, which can
  only turn a broken run red.
- **Not covered:** drift the gate cannot see. A PR that deletes tests yields no mutants, and a
  rustc update or a cargo-mutants bump that adds operators changes mutants on unchanged lines.
  The sweep still scores those green; a narrowed Backlog row tracks them.
- Timeouts are green on the assumption that a timed-out mutant never terminates; a slow but
  correct mutant could be a host-dependent false red or miss.

## Related

- ADR-0028 (CLAUDE.md byte ceiling)
- ADR-0040 (one mutation job per Rust crate)
- `docs/superpowers/specs/2026-11-05-worldclass-slice5-rust-pr-mutation-ratchet-design.md`
