# ADR-0030: One CLI Contract for the Python Programs, Checked by a Shared Harness

**Date:** 2026-10-25
**Status:** Accepted. Spec: `docs/superpowers/specs/2026-10-25-uniform-project-cli-and-python-files-design.md` (revision 4).

## Context

The operator rule (2026-10-24) is that all math projects are treated the same, all of the
time, and a per-project difference is a defect unless it is a declared, justified parameter.
The 8 Python CLIs (amicable, collatz, e, factorial, fib, perfect-numbers, pi, sq) broke that
rule in behaviour, not only in files. Each prompted at a different point after its work: pi
and e asked "Display all?" and only warned above 1,000,000 digits, fib confirmed X >= 4 even
when given an argument, and sq asked whether to display. Three of the eight benchmark recipes
had to pipe `printf "n\n" |` into the program, and each used a different size and timeout.

Nothing could check a CLI non-interactively. A test that closes stdin cannot tell a program
that never reads stdin from one that reads it and treats end of input as "no" (the math#161
behaviour), so a prompting program passes.

## Decision

Every Python CLI implements one contract, with one declared shape:

- `python3 <module>.py SIZE [--show] [--yes]` never reads stdin. The output file is always
  written. `--show` also prints each result line exactly as written to the file.
- `--smoke` runs at a module-level `SMOKE_SIZE`.
- A module-level `LARGE_RUN_THRESHOLD` (pi and e `1_000_001`, fib `4`, otherwise `None`)
  is the smallest size that needs `--yes`. Without `--yes` the program exits 1, naming
  `--yes`, before any computation or file write.
- With no arguments the program prompts only when stdin is a terminal, and otherwise exits 2.
- `parse_args`, `refuse_large_run`, `main`'s signature and the end-of-input message are
  textually identical across the 8 apart from the declared values.

`scripts/cli_contract.py` checks the contract. It reads the two constants by importing the
module and runs the program as a subprocess against one matrix. Stdin is an `os.pipe()`
whose write end stays open, so a program that reads stdin blocks and fails by timeout instead
of reading end of input. Each program runs in its own session, and the whole process group is
killed and reaped after every case, so pool workers cannot hold the pipes open or outlive the
run.

Each project's `make test` runs the harness on its own program. That places the check in the
workflow and pre-push hook that already fire when the program changes, with that project's
dependencies installed. The harness and `typings/**` are added to every Python workflow's
`paths:` filter. Pre-push runs the harness alone over the 8 programs when the harness changes.
It runs no pytest there, so the more-than-6-projects bail-out (the macOS resource_tracker
guard) is untouched.

"Proceeds with `--yes`" is tested in each project's pytest with the computation mocked, not
in the harness. fib's smallest refused size takes about 15.5 s and writes 239 MB.

## Consequences

- Any Python CLI can be run unattended: CI, a smoke run, or a pipe. The `benchmark` recipes
  no longer need a stdin hack. P3 of the spec deletes them, since the harness `--smoke` case
  already runs inside `make test`.
- pi and e above 1,000,000 digits now refuse without `--yes`, where they used to warn and
  continue. The operator accepted this behaviour change.
- The contract code is copied into 8 files rather than shared. Each project's tests run from
  its own directory, and a shared module would need import-path changes in every project. The
  copies are kept identical by review and by the harness, not by a renderer.
- The Rust binaries are out of scope. Nothing consumes a uniform Rust CLI yet, so that work is
  a Backlog row.
