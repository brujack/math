# ADR-0039: pi and e mirror their display helpers in-file, guarded by an AST test

**Date:** 2026-11-03
**Status:** Accepted

## Context

The 2026-11-01 Python mutation run reported 710 survivors in `pi/pi.py` and 735 in
`e/e.py`. Most sat in display code (ETA estimate, progress tick, write-progress line,
progress bar) held in closures inside `save_*_to_file`, where no test could assert a
value. The two files carry near-identical copies of that code and of a mantissa
formatter whose pi and e copies had already drifted (`[exp : digits + 1]` against
`[exp : digits + exp]`).

The obvious refactor, one shared helper module, is ruled out by mutation scope:
cosmic-ray's `module-path` names one file per project (`pi/cosmic-ray.toml`:
`module-path = "pi.py"`), so code moved to another file leaves mutation testing and
its survivors vanish without being killed.

Spec: `docs/superpowers/specs/2026-11-03-worldclass-slice2-pi-e-mutation-survivors-design.md`.

## Decision

1. **Six helpers become module-level in both files, with identical bodies:**
   `_io_workers`, `estimate_conversion_time`, `render_conversion_tick`,
   `render_write_progress`, `render_bar` and `_format_mantissa`. The only per-file
   difference, the bar glyphs, lives in the module constants `_BAR_FULL` and
   `_BAR_EMPTY`.
2. **`tests/test_pi_e_mirror.py` keeps the copies identical** by comparing each
   function's `ast.dump` across the two files, with no normaliser, and fails when one
   copy changes alone.
3. **Display constants are not restated in tests.** The ETA coefficients are tuning
   guesses, so `estimate_conversion_time` is tested by ordering properties only; its
   threshold and constant mutants are accepted survivors.
4. **`_format_mantissa` raises `ValueError` for `exp < 1`**, which no π or e value
   reaches, instead of silently formatting it wrong.

## Consequences

- An edit to a mirrored helper must be made in both files; the AST test names the
  function that drifted.
- Mutation kill rates for pi and e measure the display code honestly; the remaining
  survivors there are the accepted ETA constants and the precision-margin equivalents
  listed in the spec.
- `save_*_to_file` still scores C901 12 (from 21), so its `# noqa: C901` stays.

## Related

- ADR-0038 (mutation monitors).
- `pi/CLAUDE.md` and `e/CLAUDE.md`, "Mirrored helpers".
