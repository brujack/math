# ADR-0040: One mutation job per Rust crate

**Date:** 2026-11-03
**Status:** Accepted; decision 6 (`mutants-output` re-aggregated in `notify`) is superseded by ADR-0042

## Context

`mutation-testing.yml` ran all 11 Rust crates one after another in a single job. Two
measured runs on that workload:

- **Run 41271402669 (2026-11-01).** The job ran 70 minutes. All 11 real crates were green.
  The longest were `e-rs` at 18 minutes, `pi-rs` at 14 and `prime-rs` at 10.
- **Run 41720704930 (2026-11-03).** `Run mutants` was cancelled at 78 minutes with the
  annotation `The hosted runner lost communication with the server`. GitHub kept no job log.

The 360-minute timeout was not reached, and the earlier run finished the same work on one
runner. The evidence points to a transient runner loss. One job still makes any loss total:
a dead runner discards every crate's result, and `notify` can only report `no-attestation`
for the whole run without naming the crate that was running.

The 2026-08-01 per-project spec deferred a per-crate matrix as "Phase B", to start after
one successful full run on master. Run 36937484307 (2026-10-01) was that run, so the trigger
is met. `mutation-testing-python.yml` already runs as setup, matrix, notify (ADR-0033), and
`scripts/mutation-notify.sh` already supports a matrix through `EXPECTED_STATUS_UNITS`.

Spec: `docs/superpowers/specs/2026-11-03-worldclass-slice3-rust-mutation-matrix-design.md`.

## Decision

1. **Three jobs: `setup`, `mutants`, `notify`.** `setup` lists crates with
   `git ls-files '*/*-rs/Cargo.toml'`, rejects a dispatch `crate` input that is not one of
   them, refuses an empty list, and writes `matrix` and `units` to `GITHUB_OUTPUT`.
2. **One 60-minute `mutants` job per crate**, with `fail-fast: false`. Each job runs
   `make -C <crate> mutants`, then `scripts/mutation-classify.sh`, and writes its verdict
   to `status/<slug>`.
3. **The slug travels in the matrix.** It is the crate directory with `/` replaced by `-`,
   built once in `setup` with `jq`. Artifact names cannot contain `/`, and expressions have
   no string replace.
4. **A `cancelled()` step records an unfinished crate.** If a job is cancelled or times out
   before it writes its status file, the step writes a `red:` line naming the crate.
5. **`notify` names a lost runner's crate.** It passes `EXPECTED_STATUS_UNITS` (the slugs
   from `setup`), so a crate whose status artifact never arrived is reported by name.
6. **`mutants-output` is re-aggregated in `notify`.** Each job uploads
   `mutants-output-<slug>`. `notify` downloads them all with `merge-multiple` into
   `outputs/` and uploads one artifact named `mutants-output`, the exact name ai-config's
   `mutation-review.yml` downloads. It uses `outputs/`, not `artifact/`, because
   `mutation-notify.sh` reads extra root entries in `artifact/` as a different cause.
7. **The sweep rules from ADR-0038 are unchanged.** `FULL_SWEEP` is true only when the
   `crate` input is empty, and only a full sweep closes the tracking issue.

## Consequences

- Wall-clock for a full sweep is about the longest crate plus setup and install, roughly
  20 minutes, instead of 70.
- A lost runner costs one crate, and `notify` names it.
- Each of the 11 jobs installs cargo-mutants (`cargo install --locked --version 27.1.0`),
  so total runner minutes rise.
- Per-crate results are in `mutants-status-<slug>` artifacts, kept 30 days.
- `notify` downloads only the status artifacts, so `mutation-notify.sh` can no longer report
  `loop-began-no-verdict` for this workflow. When no crate writes a status, the cause reads
  `died-before-loop` or `no-attestation`; missing crates are still named by `EXPECTED_STATUS_UNITS`.
- **First matrix sweep (run 41769558239, 2026-11-04).** 8 crates finished green in 2 to 19
  minutes. `collatz`, `fib` and `sq` were still in `Run mutants` at 48 minutes (3 to 4 minutes
  each on 2026-11-01) and all three lost their runners within the same two minutes. `notify`
  filed `missing-status` naming exactly those three crates, then rebuilt `mutants-output` from
  the 8 that finished.
- **Re-running failed jobs recovers a lost crate (V2, verified).** "Re-run failed jobs" on that
  run re-ran only the three crates and `notify`. Attempt 2's `notify` saw attempt 1's eight
  `mutants-status-*` artifacts beside the three new ones: 11 statuses, 11 `outcomes.json` in
  `mutants-output`, and #195 closed. The re-runs took 4 to 7 minutes, so the losses look
  transient rather than a property of those crates. A full re-dispatch is not needed.

## Related

- ADR-0033 (Python mutation fails closed and runs sharded)
- ADR-0038 (actionlint gate and full-sweep close)
- `docs/superpowers/specs/2026-11-03-worldclass-slice3-rust-mutation-matrix-design.md`
