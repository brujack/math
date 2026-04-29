# AGENTS.md

Cursor agent instructions for this repo.

## Source of truth (exhaustive)

- Top-level `CLAUDE.md` is exhaustive and authoritative.
- Sub-project `CLAUDE.md` files are also authoritative for their directories:
  - `pi/CLAUDE.md`
  - `prime/CLAUDE.md`
  - `fib/CLAUDE.md`
  - `sq/CLAUDE.md`
  - `twin-primes/twin-primes-rs/CLAUDE.md`
  - `e/CLAUDE.md`
  - `factorial/CLAUDE.md`
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
