# Factorial Design Spec

## Overview

Add a `factorial/` project to the math repo that computes N! to arbitrary precision for very large N (10^6 and beyond). Both a Python CLI and a Rust CLI are provided, following the established repo pattern. Always saves output to a file.

---

## Algorithm: Prime Swing

The prime swing algorithm decomposes N! into a closed-form product that is fully parallelizable:

```
n! = ∏ swing(⌊n/2^k⌋)^(2^k)   for k = 0, 1, 2, … until ⌊n/2^k⌋ < 2
```

`swing(m)` is computed directly from the prime sieve:

```
swing(m) = ∏ p^e_p   for all primes p ≤ m

e_p = Σ_{j≥1} (⌊m/p^j⌋ mod 2)
```

`e_p` counts how many levels of the base-p representation of m have an odd digit — equivalently, the exponent of p in N! / (⌊N/2⌋!)².

**Parallelism opportunities:**

1. **Across levels** — all `swing(⌊n/2^k⌋)` values are independent; compute concurrently
2. **Within a swing** — split the prime range into chunks; each worker computes a partial product; tree-combine results

For n = 10^6: ~20 levels, ~78,498 primes.
For n = 10^9: ~30 levels, ~50M primes (Rust handles this scale; Python targets up to ~10^7).

---

## Project Structure

```
factorial/
├── factorial.py          # Python CLI — prime swing via gmpy2 (fast path) + mpmath fallback
├── test_factorial.py     # Python unit tests
├── install_deps.sh       # GMP + MPFR, gmpy2, mpmath, ruff, coverage
├── Makefile              # run, lint, test, coverage, clean
├── CLAUDE.md
└── factorial-rs/
    ├── src/main.rs       # Rust CLI — prime swing via rug + Rayon
    ├── Cargo.toml
    ├── install_deps.sh   # GMP + MPFR, Rust toolchain, cargo-tarpaulin
    ├── Makefile          # factorial, lint, test, clean
    └── CLAUDE.md
```

Output files: `factorial_<N>.txt` in the working directory. Added to `.gitignore`.

New CI workflows:

- `.github/workflows/factorial-py.yml` — test job
- `.github/workflows/factorial-rs.yml` — test → build + artifact
- `.github/workflows/release-factorial-rs.yml` — manual dispatch release

---

## Python Implementation (`factorial.py`)

Mirrors `e.py` in structure. gmpy2 is the fast path; mpmath is the fallback.

### Sieve

`_sieve(n)` — Sieve of Eratosthenes returning a `list[int]` of primes up to n. Suitable for n up to ~10^7 in Python; the Rust implementation handles larger N.

### Swing computation

`_compute_swing_chunk(m, prime_chunk)` — module-level subprocess worker. Iterates over a subrange of primes, computes each prime's exponent via the bit-counting loop, returns a plain Python `int` (pickling-safe):

```python
def _compute_swing_chunk(m, prime_chunk):
    result = 1
    for p in prime_chunk:
        if p > m:
            break
        exp = 0
        q = m
        while q >= p:
            q //= p
            if q % 2 == 1:
                exp += 1
        if exp > 0:
            result *= p ** exp
    return result
```

`_compute_swing(m, primes)` — splits primes into `_CPU_COUNT` chunks, dispatches to `ProcessPoolExecutor`, tree-combines partial products via `_tree_combine` (same pairwise reduction as `e.py`).

### Factorial

`calculate_factorial(n)`:

1. Sieve primes up to n
2. Build levels: `[(n, 0), (n//2, 1), (n//4, 2), ...]` until value < 2
3. Compute `swing(⌊n/2^k⌋)` for each level (parallelized across levels and within each swing)
4. Combine: `result = ∏ gmpy2.mpz(swing_k) ** (2**k)`
5. Return as `gmpy2.mpz`

**Fallback path:** if gmpy2 not installed, delegates to `int(mpmath.factorial(n))` — correct but slow for large N.

### CLI

- `parse_args(argv)` — argparse, optional positional `n` integer
- `get_target_n(args)` — returns n from CLI args or interactive prompt; validates positive integer
- `main()` — calls `parse_args`, `get_target_n`, `calculate_factorial`, writes `factorial_<n>.txt`, prints digit count and wall-clock time

Auto-save threshold: always saves to file (no terminal output of digits).

### Module-level constants

- `_HAS_GMPY2` — True if gmpy2 imported successfully
- `_CPU_COUNT` — `os.cpu_count()`

---

## Rust Implementation (`factorial-rs/src/main.rs`)

### Sieve

`sieve(n: u64) -> Vec<u32>` — segmented sieve of Eratosthenes (same approach as `prime-rs`). Primes stored as `u32` to keep memory at ~200MB for n = 10^9 (~50M primes × 4 bytes).

### Swing computation

`compute_swing(m: u64, primes: &[u32]) -> Integer` — iterates primes ≤ m, computes exponent via the bit-counting loop, returns `rug::Integer`. Internally uses `rayon::iter` to parallelize across prime chunks:

```rust
primes.par_chunks(chunk_size)
    .map(|chunk| compute_swing_chunk(m, chunk))
    .reduce(|| Integer::from(1), |a, b| a * b)
```

### Factorial

`calculate_factorial(n: u64, primes: &[u32]) -> Integer`:

1. Build levels: `[(n, 0u32), (n/2, 1), (n/4, 2), ...]`
2. Compute all swings in parallel: `levels.par_iter().map(|(m, _)| compute_swing(*m, primes))`
3. Combine: `∏ swing_k.pow(exponent)` where `exponent = 1u64 << k` cast to `u32`. Levels where `m < 2` produce `swing(m) = 1` and are skipped (no primes ≤ 1), so k is bounded in practice to at most `floor(log2(n)) ≤ 63`; the cast to `u32` is safe as long as the levels list stops before m < 2.

### Output

Convert to decimal string via `.to_string_radix(10)`, write via `std::io::BufWriter<File>`. Print digit count and elapsed time via `std::time::Instant`.

### CLI

`std::env::args()` — consistent with other Rust projects in this repo. Accepts optional positional argument; falls back to interactive stdin prompt. Always writes `factorial_<N>.txt`.

### Dependencies (`Cargo.toml`)

```toml
[dependencies]
rug = { version = "1", features = ["integer"] }
rayon = "1"
```

---

## Testing

### Known reference values

```python
FACTORIAL_REF = {
    0: 1, 1: 1, 2: 2, 3: 6, 4: 24,
    5: 120, 10: 3628800, 20: 2432902008176640000
}
```

### Python test classes (`test_factorial.py`)

| Class                    | Tests | Coverage                                                                            |
| ------------------------ | ----- | ----------------------------------------------------------------------------------- |
| `TestSieve`              | 5     | n<2 (empty), n=2, small known primes, boundary prime/composite, count check         |
| `TestComputeSwing`       | 6     | swing(0), swing(1), swing(2), swing(6) vs manual, exponent formula, prime boundary  |
| `TestTreeCombine`        | 4     | empty list, single element, two elements, many elements                             |
| `TestCalculateFactorial` | 6     | 0! through 20! vs FACTORIAL_REF; gmpy2 path                                         |
| `TestMpmathFallback`     | 3     | fallback correct for small N, produces int, digit count matches                     |
| `TestGetTargetN`         | 5     | CLI arg, interactive, zero rejected, negative rejected, non-integer rejected        |
| `TestParseArgs`          | 3     | no args, positional arg, `--help`                                                   |
| `TestDigitCount`         | 3     | digit count of 10!, Stirling approximation check for n=1000                         |
| `TestOutputFile`         | 4     | file created, filename correct, content is digits-only string, idempotent overwrite |

### Rust tests (`src/main.rs` `#[cfg(test)]`)

Same coverage: sieve correctness, swing boundary values, factorial against reference values, digit count, file write.

---

## CI and Repo Updates

When adding this project:

1. Create `.github/workflows/factorial-py.yml` — triggers on PR to master; runs `make test` in `factorial/`
2. Create `.github/workflows/factorial-rs.yml` — test job → build job with artifact upload
3. Create `.github/workflows/release-factorial-rs.yml` — `workflow_dispatch`; same pattern as `release-e-rs.yml`
4. Add badge to `README.md` top and CI column of project table
5. Update `CLAUDE.md` — Repository Overview table, CI workflow count and table, Quick Reference
6. Update `README.md` — project table, CI badges, Makefile targets
7. Add `factorial` and `factorial/factorial-rs` to the dir loops in `scripts/pre-commit` and `scripts/pre-push`
8. Add `factorial_*.txt` to `.gitignore`
9. Write an ADR for the prime swing algorithm choice (`docs/adr/`)
10. Update `docs/superpowers/README.md` — add row with status In Progress, move backlog item to All Plans table
