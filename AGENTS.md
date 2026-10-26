# AGENTS.md

Cursor agent instructions for this repo.

## Source of truth

- Top-level `CLAUDE.md` is authoritative and holds one line per rule, with detail behind pointers to `ai-config/docs/knowledge/math-*.md`.
- Sub-project `CLAUDE.md` files are also authoritative for their directories:
  - `pi/CLAUDE.md`, `pi/pi-rs/CLAUDE.md`
  - `prime/CLAUDE.md`, `prime/prime-rs/CLAUDE.md`
  - `fib/CLAUDE.md`, `fib/fib-rs/CLAUDE.md`
  - `sq/CLAUDE.md`, `sq/sq-rs/CLAUDE.md`
  - `twin-primes/twin-primes-rs/CLAUDE.md`
  - `e/CLAUDE.md`, `e/e-rs/CLAUDE.md`
  - `factorial/CLAUDE.md`, `factorial/factorial-rs/CLAUDE.md`
  - `perfect-numbers/CLAUDE.md`, `perfect-numbers/perfect-numbers-rs/CLAUDE.md`
  - `collatz/CLAUDE.md`, `collatz/collatz-rs/CLAUDE.md`
  - `goldbach/CLAUDE.md`, `goldbach/goldbach-rs/CLAUDE.md`
  - `amicable/CLAUDE.md`, `amicable/amicable-rs/CLAUDE.md`
- If this file conflicts with any relevant `CLAUDE.md`, follow the relevant `CLAUDE.md`.

## Required compliance behavior

- Before editing, read the relevant project `CLAUDE.md`.
- Enforce repository TDD policy exactly as written.
- Follow project-specific lint/test/coverage requirements exactly, including Rust tarpaulin guidance and coverage floors.
- Keep changes scoped to requested work; avoid unrelated refactors and avoid committing generated output artifacts.
- Keep docs synchronized where required (`README.md`, top-level `CLAUDE.md`, and relevant project `CLAUDE.md` files).

## Workflow and release policy

- Use feature branches and PR workflow except for explicitly allowed documentation-only exceptions.
- Preserve hook and CI conventions defined in `CLAUDE.md`.
- Run repo review gates required by `CLAUDE.md` before pushing feature work.

## Security and hygiene

- Never commit secrets, tokens, or local machine-only files.
- Keep secret scanning protections and hook behavior intact.

## Drift control

- When any relevant `CLAUDE.md` changes, update this file in the same change to keep parity.
