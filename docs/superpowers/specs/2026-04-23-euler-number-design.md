# Euler's Number (e) Design Spec

## Overview

Compute Euler's number _e_ to N decimal places using the Taylor series with binary splitting for arbitrary-precision arithmetic. Two implementations: Python and Rust, both parallelized. Follows the same structure and conventions as `pi/`.

## Algorithm

Taylor series: `e = sum(1/n! for n=0..N_terms)` computed via binary splitting.

Define accumulators over a range `[a, b)` with midpoint `m = (a+b)/2`:

Base case (`b - a == 1`): `P(a,b) = a+1`, `Q(a,b) = a+1` (special: `P(0,1) = 1, Q(0,1) = 1`).

`Q(a,b)` is defined as `S(a,b) * P(a,b)` where `S(a,b) = sum_{k=a}^{b-1} a!/k!`. This ensures that the merge formula uses only integer multiplication and addition.

Recursive case: compute left and right subtrees, merge:

```
P(a,b) = P(a,m) * P(m,b)
Q(a,b) = Q(a,m) * P(m,b) + Q(m,b)
```

Final result: `e = Q(0,N_terms) / P(0,N_terms)`. The `1/0!` term is included in the recursion (leaf 0 contributes `Q=1, P=1`).

**Number of terms:** Approximately `N / log10(N)` terms are needed for N decimal digits. Each term `1/n!` contributes roughly `log10(n)` new digits. Compute a safe upper bound and verify precision against a reference.

**Parallelization:** At the top level of the recursion tree, split the term range across CPU cores. Each core computes its `(P, Q)` subtree independently. Merge results with tree reduction — same pattern as pi's Chudnovsky binary splitting.

- Python: `multiprocessing` with subprocess chunks, tree-reduction merge
- Rust: `rayon::join()` for shared-memory parallel recursion

## Project Structure

```
e/
├── CLAUDE.md
├── Makefile
├── e.py
├── test_e.py
├── install_deps.sh
└── e-rs/
    ├── CLAUDE.md
    ├── Makefile
    ├── Cargo.toml
    ├── install_deps.sh
    └── src/
        └── main.rs
```

## CLI

Both implementations share the same interface:

```
python3 e.py [digits]
./e [digits]
```

- `digits` — positive integer; compute _e_ to that many decimal places
- No argument — prompt interactively
- `-h` / `--help` — usage info

## Output

**Small outputs (≤10,000 digits):** preview to stdout.

**Large outputs (>10,000 digits):** auto-save to `e_<digits>_digits.txt`, print summary to stdout.

Format: `2.` followed by decimal digits, matching pi's output style.

## Dependencies

**Python:** `mpmath` (verification oracle), `gmpy2` (arbitrary-precision arithmetic), `ruff` (linting), `coverage` (test coverage).

**Rust:** `rug` crate (GMP/MPFR bindings), `clap` (CLI), `rayon` (parallelism), `cargo-tarpaulin` (coverage).

Install scripts: `e/install_deps.sh` and `e/e-rs/install_deps.sh`, following the same pattern as pi's installers.

## Error Handling

- Invalid/missing argument (non-positive integer): print usage to stderr, exit code 1
- 0 digits: print "2" (just the integer part), exit 0
- Write failure: propagate error, print to stderr, exit code 1

## Testing

### Python (`test_e.py`)

**Known-value tests:**

- Verify first 50 digits against the known constant
- Small digit counts (1, 10, 100, 1000) verified against `mpmath.e`

**Boundary value tests:**

- 0 digits: returns "2"
- 1 digit: returns "2.7"
- Negative input: error
- Non-integer input: error

**Binary splitting correctness:**

- `P(a,b)` and `Q(a,b)` for small known ranges verified by hand

**Output format:**

- File creation for large outputs (>10,000 digits)
- Stdout preview for small outputs
- File content matches computation

**Parallelization:**

- Results match sequential computation for same digit count

### Rust (`src/main.rs` tests module)

- Same known-value and boundary tests as Python
- CLI argument parsing: valid, invalid, missing, help flag
- Binary splitting unit tests for small ranges
- Verify Rust output matches Python output for same digit count

**Error path tests:**

- Missing argument → error exit
- Non-integer argument → error exit
- Negative argument → error exit

**State transition tests:**

- Output file created after run
- Running twice overwrites file cleanly (idempotent)
- No extra output files created

## CI

**New workflows:**

| Workflow     | File                                 | Jobs                      |
| ------------ | ------------------------------------ | ------------------------- |
| e.py         | `.github/workflows/e-py.yml`         | test                      |
| e-rs         | `.github/workflows/e-rs.yml`         | test → build + artifact   |
| release-e-rs | `.github/workflows/release-e-rs.yml` | release (manual dispatch) |

All follow existing patterns: `pull_request: branches: [master]` trigger, Node.js 24, `actions/checkout@v5`, `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true`.

**Local testing gate:** The pre-push hook runs `make test` for changed sub-projects before the push reaches GitHub. All tests (Python and Rust) must pass locally before pushing the feature branch. GitHub Actions CI is the final merge gate on PRs, not the first line of defense.

## Repo Updates Required

| File                         | Change                                                                         |
| ---------------------------- | ------------------------------------------------------------------------------ |
| `README.md`                  | Add CI badges (e-py, e-rs); add row to project table                           |
| `CLAUDE.md`                  | Add to Repository Overview, CI table, Quick Reference, Dependency Installation |
| `scripts/pre-commit`         | Add `e` and `e/e-rs` to lint loop                                              |
| `scripts/pre-push`           | Add `e` and `e/e-rs` to test loop                                              |
| `e/CLAUDE.md`                | New file — implementation detail for Python project                            |
| `e/e-rs/CLAUDE.md`           | New file — implementation detail for Rust project                              |
| `docs/superpowers/README.md` | Move _e_ from backlog to All Plans table                                       |
| `auto-merge.yml`             | No change needed — auto-merge is repo-wide, not project-specific               |
