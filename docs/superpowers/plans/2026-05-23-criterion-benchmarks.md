# Criterion Benchmarks — math Implementation Plan

> **Status: DONE**

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Criterion benchmarks to all 11 Rust math crates and publish historical trend charts to GitHub Pages via `benchmark-action/github-action-benchmark`, running monthly.

**Architecture:** Each binary-only crate gains a `src/lib.rs` (core compute functions extracted as `pub fn`) and a `benches/<crate>.rs` (Criterion benchmarks). A single `benchmarks.yml` CI workflow runs all 11 benches sequentially, pipes `--output-format bencher` output to the action, which auto-commits to the `gh-pages` branch. Chart.js renders time-series charts at `https://brujack.github.io/math/dev/bench/`.

**Tech Stack:** Criterion 0.5, `benchmark-action/github-action-benchmark@v1`, `dtolnay/rust-toolchain@stable`, `actions/checkout@v6`

---

### Task 1: Initialize gh-pages branch

**Files:**

- Creates: `gh-pages` orphan branch (remote only)

The `benchmark-action/github-action-benchmark` action requires a `gh-pages` branch to exist before it can push benchmark data.

- [ ] **Step 1: Create the orphan branch**

Run from the repo root:

```bash
cd ~/git-repos/personal/math
git checkout --orphan gh-pages
git rm -rf .
echo "# Benchmark Results" > README.md
git add README.md
git commit -m "chore: init gh-pages branch for benchmark results"
git push origin gh-pages
git checkout master
```

- [ ] **Step 2: Enable GitHub Pages via API**

```bash
gh api repos/brujack/math/pages \
  --method POST \
  --field source='{"branch":"gh-pages","path":"/"}' \
  --header "Accept: application/vnd.github.v3+json" 2>/dev/null || true
```

Expected: either success JSON or "already enabled". If it returns an error about Pages being already configured, that's fine — the branch exists and the action will populate it.

- [ ] **Step 3: Return to master and verify**

```bash
git checkout master
git branch -a | grep gh-pages
```

Expected: `remotes/origin/gh-pages` appears in the list.

---

### Task 2: factorial-rs — lib extraction + bench

**Files:**

- Create: `factorial/factorial-rs/src/lib.rs`
- Modify: `factorial/factorial-rs/src/main.rs`
- Modify: `factorial/factorial-rs/Cargo.toml`
- Create: `factorial/factorial-rs/benches/factorial.rs`

The crate is currently binary-only. Extract the core computation into a library target so the bench can call it.

- [ ] **Step 1: Create `factorial/factorial-rs/src/lib.rs`**

Cut lines 1–88 from `src/main.rs` (everything up to and including `calculate_factorial`) and paste into `src/lib.rs`. Change `fn calculate_factorial` to `pub fn calculate_factorial`. The file must start with:

```rust
use rug::ops::Pow;
use rug::Integer;
```

Then the five functions in order: `sieve`, `compute_swing_chunk`, `compute_swing`, `factorial_rec` (all private), and `pub fn calculate_factorial`. No other changes to function bodies.

- [ ] **Step 2: Update `factorial/factorial-rs/src/main.rs`**

At the top of `main.rs`, after the existing `use std::io::{self, BufRead, Write};` and `use std::path::{Path, PathBuf};` lines, add:

```rust
use factorial::calculate_factorial;
```

Remove the `use rug::ops::Pow;` and `use rug::Integer;` lines from `main.rs` if they are no longer used there (they move to lib.rs). If `run()` in main.rs still uses `Integer` directly, keep the import.

- [ ] **Step 3: Update `factorial/factorial-rs/Cargo.toml`**

Add a `[dev-dependencies]` entry for criterion and a `[[bench]]` section:

```toml
[dev-dependencies]
tempfile = "3"
proptest = "1"
criterion = "0.5"

[[bench]]
name = "factorial"
harness = false
```

(Add `criterion = "0.5"` to the existing `[dev-dependencies]` block. Add the `[[bench]]` block after `[dev-dependencies]`.)

- [ ] **Step 4: Create `factorial/factorial-rs/benches/factorial.rs`**

```rust
use criterion::{black_box, criterion_group, criterion_main, Criterion};
use factorial::calculate_factorial;

fn bench_factorial(c: &mut Criterion) {
    let mut group = c.benchmark_group("factorial");
    group.bench_function("n=100", |b| b.iter(|| calculate_factorial(black_box(100))));
    group.bench_function("n=1000", |b| b.iter(|| calculate_factorial(black_box(1_000))));
    group.bench_function("n=10000", |b| b.iter(|| calculate_factorial(black_box(10_000))));
    group.finish();
}

criterion_group!(benches, bench_factorial);
criterion_main!(benches);
```

- [ ] **Step 5: Run cargo test — verify no regressions**

```bash
cd factorial/factorial-rs
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$HOME/.cargo/bin:$PATH"
cargo test
```

Expected: all tests pass. If any test fails because it references a private function that was moved to lib.rs, move that test case into a `#[cfg(test)]` block at the bottom of `src/lib.rs`.

- [ ] **Step 6: Run cargo bench — verify it compiles and produces output**

```bash
cargo bench -- --output-format bencher 2>/dev/null
```

Expected: output lines like:

```
test factorial::n=100 ... bench:   NNNN ns/iter (+/- MMM)
test factorial::n=1000 ... bench:  NNNN ns/iter (+/- MMM)
test factorial::n=10000 ... bench: NNNN ns/iter (+/- MMM)
```

If the bench takes >30s for `n=10000`, replace it with `n=5000`.

- [ ] **Step 7: Commit**

```bash
cd ../..
git add factorial/factorial-rs/src/lib.rs \
        factorial/factorial-rs/src/main.rs \
        factorial/factorial-rs/Cargo.toml \
        factorial/factorial-rs/Cargo.lock \
        factorial/factorial-rs/benches/factorial.rs
git commit -m "feat(factorial): add lib target and criterion benchmarks"
```

---

### Task 3: pi-rs — lib extraction + bench

**Files:**

- Create: `pi/pi-rs/src/lib.rs`
- Modify: `pi/pi-rs/src/main.rs`
- Modify: `pi/pi-rs/Cargo.toml`
- Create: `pi/pi-rs/benches/pi.rs`

- [ ] **Step 1: Create `pi/pi-rs/src/lib.rs`**

Cut from `src/main.rs` and paste into `src/lib.rs`:

- The `use rayon::prelude::*;` and `use rug::{Float, Integer};` imports (plus any `std` imports those functions need — at minimum `use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};` and `use std::sync::Arc;` and `use std::thread;` and `use std::time::{Duration, Instant};`)
- `struct Pqt { ... }` (the full struct definition)
- `fn bs(a, b)`, `fn bs_leaf(a)`, `fn bs_merge(l, r)` (private)
- `fn pi_to_string(pi, digits)` (private)
- `fn compute_pi(digits: usize) -> String` — make this **`pub fn`**
- `fn format_series_progress(completed, n)` (private) — only if used by `compute_pi`

Do not move file I/O functions (`write_pi_file`, `save_pi`, `format_write_progress`), CLI parsing (`Cli` struct), `read_line_from`, `prompt_digits_with`, `confirm_large_digits_with`, `run`, or `main` — those stay in main.rs.

Add at the top of lib.rs:

```rust
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use rayon::prelude::*;
use rug::{Float, Integer};
```

- [ ] **Step 2: Update `pi/pi-rs/src/main.rs`**

Add at the top:

```rust
use pi::compute_pi;
```

Remove the imports that have moved to lib.rs. Keep all file I/O, CLI, and `run`/`main` functions.

- [ ] **Step 3: Update `pi/pi-rs/Cargo.toml`**

```toml
[dev-dependencies]
tempfile = "3"
proptest = "1"
criterion = "0.5"

[[bench]]
name = "pi"
harness = false
```

- [ ] **Step 4: Create `pi/pi-rs/benches/pi.rs`**

```rust
use criterion::{black_box, criterion_group, criterion_main, Criterion};
use pi::compute_pi;

fn bench_pi(c: &mut Criterion) {
    let mut group = c.benchmark_group("pi");
    group.bench_function("digits=100", |b| b.iter(|| compute_pi(black_box(100))));
    group.bench_function("digits=1000", |b| b.iter(|| compute_pi(black_box(1_000))));
    group.bench_function("digits=10000", |b| b.iter(|| compute_pi(black_box(10_000))));
    group.finish();
}

criterion_group!(benches, bench_pi);
criterion_main!(benches);
```

- [ ] **Step 5: Run cargo test**

```bash
cd pi/pi-rs
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$HOME/.cargo/bin:$PATH"
cargo test
```

Expected: all tests pass.

- [ ] **Step 6: Run cargo bench**

```bash
cargo bench -- --output-format bencher 2>/dev/null
```

Expected: 3 benchmark output lines. If `digits=10000` takes >30s, replace with `digits=5000`.

- [ ] **Step 7: Commit**

```bash
cd ../..
git add pi/pi-rs/src/lib.rs pi/pi-rs/src/main.rs \
        pi/pi-rs/Cargo.toml pi/pi-rs/Cargo.lock \
        pi/pi-rs/benches/pi.rs
git commit -m "feat(pi): add lib target and criterion benchmarks"
```

---

### Task 4: e-rs — lib extraction + bench

**Files:**

- Create: `e/e-rs/src/lib.rs`
- Modify: `e/e-rs/src/main.rs`
- Modify: `e/e-rs/Cargo.toml`
- Create: `e/e-rs/benches/e.rs`

- [ ] **Step 1: Create `e/e-rs/src/lib.rs`**

Cut from `src/main.rs` and paste into `src/lib.rs`:

- `struct Pq { ... }` (full struct definition)
- `fn bs(a, b)`, `fn bs_leaf(a)`, `fn bs_merge(l, r)` (private)
- `fn e_to_string(e, digits)` (private)
- `fn format_series_progress(completed, n)` (private) — only if used by `compute_e`
- `fn compute_e(digits: usize) -> String` — make this **`pub fn`**

Add at the top of lib.rs:

```rust
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use rayon::prelude::*;
use rug::{Float, Integer};
```

Keep in main.rs: `Cli` struct, file I/O functions (`write_e_file`, `save_e`, `format_write_progress`), `fmt_int`, `read_line_from`, `prompt_digits_with`, `confirm_large_digits_with`, `run`, `main`.

- [ ] **Step 2: Update `e/e-rs/src/main.rs`**

Add at the top:

```rust
use e::compute_e;
```

Remove the imports that have moved to lib.rs.

- [ ] **Step 3: Update `e/e-rs/Cargo.toml`**

```toml
[dev-dependencies]
tempfile = "3"
proptest = "1"
criterion = "0.5"

[[bench]]
name = "e"
harness = false
```

- [ ] **Step 4: Create `e/e-rs/benches/e.rs`**

```rust
use criterion::{black_box, criterion_group, criterion_main, Criterion};
use e::compute_e;

fn bench_e(c: &mut Criterion) {
    let mut group = c.benchmark_group("e");
    group.bench_function("digits=100", |b| b.iter(|| compute_e(black_box(100))));
    group.bench_function("digits=1000", |b| b.iter(|| compute_e(black_box(1_000))));
    group.bench_function("digits=10000", |b| b.iter(|| compute_e(black_box(10_000))));
    group.finish();
}

criterion_group!(benches, bench_e);
criterion_main!(benches);
```

- [ ] **Step 5: Run cargo test**

```bash
cd e/e-rs
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$HOME/.cargo/bin:$PATH"
cargo test
```

- [ ] **Step 6: Run cargo bench**

```bash
cargo bench -- --output-format bencher 2>/dev/null
```

- [ ] **Step 7: Commit**

```bash
cd ../..
git add e/e-rs/src/lib.rs e/e-rs/src/main.rs \
        e/e-rs/Cargo.toml e/e-rs/Cargo.lock \
        e/e-rs/benches/e.rs
git commit -m "feat(e): add lib target and criterion benchmarks"
```

---

### Task 5: fib-rs — lib extraction + bench

**Files:**

- Create: `fib/fib-rs/src/lib.rs`
- Modify: `fib/fib-rs/src/main.rs`
- Modify: `fib/fib-rs/Cargo.toml`
- Create: `fib/fib-rs/benches/fib.rs`

- [ ] **Step 1: Create `fib/fib-rs/src/lib.rs`**

Cut from `src/main.rs` and paste into `src/lib.rs`:

- `fn generate_fibonacci<W: Write>(max_digits: usize, out: &mut W) -> io::Result<u64>` — make this **`pub fn`**

Add at the top of lib.rs:

```rust
use std::io::{self, Write};

use rug::ops::PowAssign;
use rug::Integer;
```

Keep in main.rs: `Cli` struct, `fmt_int`, `read_line_from`, `prompt_exponent_with`, `confirm_large_n_with`, `write_fib_file`, `stream_fib_to_file`, `run`, `main`, tests.

- [ ] **Step 2: Update `fib/fib-rs/src/main.rs`**

Add at the top:

```rust
use fib::generate_fibonacci;
```

- [ ] **Step 3: Update `fib/fib-rs/Cargo.toml`**

```toml
[dev-dependencies]
tempfile = "3"
proptest = "1"
criterion = "0.5"

[[bench]]
name = "fib"
harness = false
```

- [ ] **Step 4: Create `fib/fib-rs/benches/fib.rs`**

`generate_fibonacci` writes output to a writer. Pass `io::sink()` to discard output.

```rust
use std::io;

use criterion::{black_box, criterion_group, criterion_main, Criterion};
use fib::generate_fibonacci;

fn bench_fib(c: &mut Criterion) {
    let mut group = c.benchmark_group("fib");
    group.bench_function("max_digits=10", |b| {
        b.iter(|| generate_fibonacci(black_box(10), &mut io::sink()).unwrap())
    });
    group.bench_function("max_digits=100", |b| {
        b.iter(|| generate_fibonacci(black_box(100), &mut io::sink()).unwrap())
    });
    group.bench_function("max_digits=1000", |b| {
        b.iter(|| generate_fibonacci(black_box(1_000), &mut io::sink()).unwrap())
    });
    group.finish();
}

criterion_group!(benches, bench_fib);
criterion_main!(benches);
```

- [ ] **Step 5: Run cargo test**

```bash
cd fib/fib-rs
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$HOME/.cargo/bin:$PATH"
cargo test
```

- [ ] **Step 6: Run cargo bench**

```bash
cargo bench -- --output-format bencher 2>/dev/null
```

If `max_digits=1000` takes >30s, replace with `max_digits=500`.

- [ ] **Step 7: Commit**

```bash
cd ../..
git add fib/fib-rs/src/lib.rs fib/fib-rs/src/main.rs \
        fib/fib-rs/Cargo.toml fib/fib-rs/Cargo.lock \
        fib/fib-rs/benches/fib.rs
git commit -m "feat(fib): add lib target and criterion benchmarks"
```

---

### Task 6: collatz-rs — lib extraction + bench

**Files:**

- Create: `collatz/collatz-rs/src/lib.rs`
- Modify: `collatz/collatz-rs/src/main.rs`
- Modify: `collatz/collatz-rs/Cargo.toml`
- Create: `collatz/collatz-rs/benches/collatz.rs`

- [ ] **Step 1: Create `collatz/collatz-rs/src/lib.rs`**

Cut from `src/main.rs` and paste into `src/lib.rs`:

- `fn collatz_next(n: u64) -> u64` (private)
- `fn chain_length(n: u64, cache: &mut [u32], limit: u64) -> u32` (private)
- `fn generate_records<W: Write, E: Write>(limit: u64, out: &mut W, _err: &mut E) -> io::Result<Vec<(u64, u32)>>` — make this **`pub fn`**

Add at the top of lib.rs:

```rust
use std::io::{self, Write};
```

Keep in main.rs: `Cli` struct, `prompt_n`, `run`, `main`, tests.

- [ ] **Step 2: Update `collatz/collatz-rs/src/main.rs`**

Add at the top:

```rust
use collatz::generate_records;
```

- [ ] **Step 3: Update `collatz/collatz-rs/Cargo.toml`**

```toml
[dev-dependencies]
tempfile = "3"
proptest = "1"
criterion = "0.5"

[[bench]]
name = "collatz"
harness = false
```

- [ ] **Step 4: Create `collatz/collatz-rs/benches/collatz.rs`**

```rust
use std::io;

use criterion::{black_box, criterion_group, criterion_main, Criterion};
use collatz::generate_records;

fn bench_collatz(c: &mut Criterion) {
    let mut group = c.benchmark_group("collatz");
    group.bench_function("limit=1000", |b| {
        b.iter(|| generate_records(black_box(1_000), &mut io::sink(), &mut io::sink()).unwrap())
    });
    group.bench_function("limit=100000", |b| {
        b.iter(|| generate_records(black_box(100_000), &mut io::sink(), &mut io::sink()).unwrap())
    });
    group.bench_function("limit=1000000", |b| {
        b.iter(|| generate_records(black_box(1_000_000), &mut io::sink(), &mut io::sink()).unwrap())
    });
    group.finish();
}

criterion_group!(benches, bench_collatz);
criterion_main!(benches);
```

- [ ] **Step 5: Run cargo test**

```bash
cd collatz/collatz-rs
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$HOME/.cargo/bin:$PATH"
cargo test
```

- [ ] **Step 6: Run cargo bench**

```bash
cargo bench -- --output-format bencher 2>/dev/null
```

If `limit=1000000` takes >30s, replace with `limit=500000`.

- [ ] **Step 7: Commit**

```bash
cd ../..
git add collatz/collatz-rs/src/lib.rs collatz/collatz-rs/src/main.rs \
        collatz/collatz-rs/Cargo.toml collatz/collatz-rs/Cargo.lock \
        collatz/collatz-rs/benches/collatz.rs
git commit -m "feat(collatz): add lib target and criterion benchmarks"
```

---

### Task 7: amicable-rs — lib extraction + bench

**Files:**

- Create: `amicable/amicable-rs/src/lib.rs`
- Modify: `amicable/amicable-rs/src/main.rs`
- Modify: `amicable/amicable-rs/Cargo.toml`
- Create: `amicable/amicable-rs/benches/amicable.rs`

The `run()` function creates a `File` which is unsuitable for benchmarking. Benchmark `proper_divisor_sum_sieve` directly — it is the core O(N log N) algorithm.

- [ ] **Step 1: Create `amicable/amicable-rs/src/lib.rs`**

Cut from `src/main.rs` and paste into `src/lib.rs`:

- `fn proper_divisor_sum_sieve(limit: usize) -> Vec<u32>` — make this **`pub fn`**

Add at the top of lib.rs:

```rust
// no external imports needed — uses only primitive types
```

Keep in main.rs: `Args` struct, `run`, `main`, all tests (they test `run` and `proper_divisor_sum_sieve` — add `use amicable::proper_divisor_sum_sieve;` to the test module if needed).

- [ ] **Step 2: Update `amicable/amicable-rs/src/main.rs`**

Add at the top:

```rust
use amicable::proper_divisor_sum_sieve;
```

Remove the `fn proper_divisor_sum_sieve` definition from main.rs.

In the test module (`mod tests`), the `use crate::proper_divisor_sum_sieve` reference (via `use crate::*`) now resolves through the re-import. If any test fails with "function not found", add explicitly: `use amicable::proper_divisor_sum_sieve;` inside the test module.

- [ ] **Step 3: Update `amicable/amicable-rs/Cargo.toml`**

```toml
[dev-dependencies]
tempfile = "3"
proptest = "1"
criterion = "0.5"

[[bench]]
name = "amicable"
harness = false
```

- [ ] **Step 4: Create `amicable/amicable-rs/benches/amicable.rs`**

```rust
use criterion::{black_box, criterion_group, criterion_main, Criterion};
use amicable::proper_divisor_sum_sieve;

fn bench_amicable(c: &mut Criterion) {
    let mut group = c.benchmark_group("amicable");
    group.bench_function("limit=1000", |b| {
        b.iter(|| proper_divisor_sum_sieve(black_box(1_000)))
    });
    group.bench_function("limit=10000", |b| {
        b.iter(|| proper_divisor_sum_sieve(black_box(10_000)))
    });
    group.bench_function("limit=100000", |b| {
        b.iter(|| proper_divisor_sum_sieve(black_box(100_000)))
    });
    group.finish();
}

criterion_group!(benches, bench_amicable);
criterion_main!(benches);
```

- [ ] **Step 5: Run cargo test**

```bash
cd amicable/amicable-rs
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$HOME/.cargo/bin:$PATH"
cargo test
```

- [ ] **Step 6: Run cargo bench**

```bash
cargo bench -- --output-format bencher 2>/dev/null
```

- [ ] **Step 7: Commit**

```bash
cd ../..
git add amicable/amicable-rs/src/lib.rs amicable/amicable-rs/src/main.rs \
        amicable/amicable-rs/Cargo.toml amicable/amicable-rs/Cargo.lock \
        amicable/amicable-rs/benches/amicable.rs
git commit -m "feat(amicable): add lib target and criterion benchmarks"
```

---

### Task 8: prime-rs — lib extraction + bench

**Files:**

- Create: `prime/prime-rs/src/lib.rs`
- Modify: `prime/prime-rs/src/main.rs`
- Modify: `prime/prime-rs/Cargo.toml`
- Create: `prime/prime-rs/benches/prime.rs`

- [ ] **Step 1: Create `prime/prime-rs/src/lib.rs`**

Cut from `src/main.rs` and paste into `src/lib.rs`:

- `fn small_sieve(limit: u64) -> Vec<u64>` (private)
- `fn sieve_segment(lo: u64, limit: u64, small_primes: &[u64]) -> Vec<u64>` (private)
- `fn format_phase2_progress(n: u64, phase2_total: u64, elapsed: f64) -> String` (private) — only if used by `find_primes`
- `fn find_primes<W: Write>(limit: u64, out: &mut W) -> io::Result<u64>` — make this **`pub fn`**

Add at the top of lib.rs:

```rust
use std::io::{self, Write};
use std::time::Instant;

use rayon::prelude::*;
```

Keep in main.rs: `Cli` struct, `fmt_int`, `read_line_from`, `confirm_large_n_with`, `prompt_n_with`, `run`, `main`, tests.

- [ ] **Step 2: Update `prime/prime-rs/src/main.rs`**

Add at the top:

```rust
use prime::find_primes;
```

- [ ] **Step 3: Update `prime/prime-rs/Cargo.toml`**

```toml
[dev-dependencies]
tempfile = "3"
proptest = "1"
criterion = "0.5"

[[bench]]
name = "prime"
harness = false
```

- [ ] **Step 4: Create `prime/prime-rs/benches/prime.rs`**

```rust
use std::io;

use criterion::{black_box, criterion_group, criterion_main, Criterion};
use prime::find_primes;

fn bench_prime(c: &mut Criterion) {
    let mut group = c.benchmark_group("prime");
    group.bench_function("limit=1000", |b| {
        b.iter(|| find_primes(black_box(1_000), &mut io::sink()).unwrap())
    });
    group.bench_function("limit=100000", |b| {
        b.iter(|| find_primes(black_box(100_000), &mut io::sink()).unwrap())
    });
    group.bench_function("limit=1000000", |b| {
        b.iter(|| find_primes(black_box(1_000_000), &mut io::sink()).unwrap())
    });
    group.finish();
}

criterion_group!(benches, bench_prime);
criterion_main!(benches);
```

- [ ] **Step 5: Run cargo test**

```bash
cd prime/prime-rs
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$HOME/.cargo/bin:$PATH"
cargo test
```

- [ ] **Step 6: Run cargo bench**

```bash
cargo bench -- --output-format bencher 2>/dev/null
```

- [ ] **Step 7: Commit**

```bash
cd ../..
git add prime/prime-rs/src/lib.rs prime/prime-rs/src/main.rs \
        prime/prime-rs/Cargo.toml prime/prime-rs/Cargo.lock \
        prime/prime-rs/benches/prime.rs
git commit -m "feat(prime): add lib target and criterion benchmarks"
```

---

### Task 9: perfect-numbers-rs — lib extraction + bench

**Files:**

- Create: `perfect-numbers/perfect-numbers-rs/src/lib.rs`
- Modify: `perfect-numbers/perfect-numbers-rs/src/main.rs`
- Modify: `perfect-numbers/perfect-numbers-rs/Cargo.toml`
- Create: `perfect-numbers/perfect-numbers-rs/benches/perfect_numbers.rs`

Note: Cargo.toml package name is `perfect-numbers`; the Rust crate name (for `use`) is `perfect_numbers` (hyphens → underscores).

- [ ] **Step 1: Create `perfect-numbers/perfect-numbers-rs/src/lib.rs`**

Cut from `src/main.rs` and paste into `src/lib.rs`:

- `fn is_prime(n: u64) -> bool` (private)
- `fn lucas_lehmer(p: u64) -> bool` (private)
- `fn verify_perfect(p: u64) -> bool` (private)
- `fn generate_perfect_numbers(limit: &Integer) -> Vec<(u64, Integer)>` — make this **`pub fn`**

Add at the top of lib.rs:

```rust
use rug::Integer;
```

Keep in main.rs: `Cli` struct, `read_line_from`, `prompt_n_with`, `run`, `main`, tests.

- [ ] **Step 2: Update `perfect-numbers/perfect-numbers-rs/src/main.rs`**

Add at the top:

```rust
use perfect_numbers::generate_perfect_numbers;
```

Remove the `use rug::Integer;` from main.rs only if Integer is no longer used there (the `run` function likely still uses it for the limit parameter).

- [ ] **Step 3: Update `perfect-numbers/perfect-numbers-rs/Cargo.toml`**

```toml
[dev-dependencies]
tempfile = "3"
proptest = "1"
criterion = "0.5"

[[bench]]
name = "perfect_numbers"
harness = false
```

- [ ] **Step 4: Create `perfect-numbers/perfect-numbers-rs/benches/perfect_numbers.rs`**

`generate_perfect_numbers` takes a `&rug::Integer`. Create the limit once outside the iter closure and borrow it.

```rust
use criterion::{black_box, criterion_group, criterion_main, Criterion};
use perfect_numbers::generate_perfect_numbers;
use rug::Integer;

fn bench_perfect_numbers(c: &mut Criterion) {
    let mut group = c.benchmark_group("perfect-numbers");
    group.bench_function("limit=10000", |b| {
        let limit = Integer::from(10_000u64);
        b.iter(|| generate_perfect_numbers(black_box(&limit)))
    });
    group.bench_function("limit=1e9", |b| {
        let limit = Integer::from(1_000_000_000u64);
        b.iter(|| generate_perfect_numbers(black_box(&limit)))
    });
    group.bench_function("limit=1e18", |b| {
        let limit = Integer::from(1_000_000_000_000_000_000u64);
        b.iter(|| generate_perfect_numbers(black_box(&limit)))
    });
    group.finish();
}

criterion_group!(benches, bench_perfect_numbers);
criterion_main!(benches);
```

- [ ] **Step 5: Run cargo test**

```bash
cd perfect-numbers/perfect-numbers-rs
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$HOME/.cargo/bin:$PATH"
cargo test
```

- [ ] **Step 6: Run cargo bench**

```bash
cargo bench -- --output-format bencher 2>/dev/null
```

- [ ] **Step 7: Commit**

```bash
cd ../..
git add perfect-numbers/perfect-numbers-rs/src/lib.rs \
        perfect-numbers/perfect-numbers-rs/src/main.rs \
        perfect-numbers/perfect-numbers-rs/Cargo.toml \
        perfect-numbers/perfect-numbers-rs/Cargo.lock \
        perfect-numbers/perfect-numbers-rs/benches/perfect_numbers.rs
git commit -m "feat(perfect-numbers): add lib target and criterion benchmarks"
```

---

### Task 10: twin-primes-rs — lib extraction + bench

**Files:**

- Create: `twin-primes/twin-primes-rs/src/lib.rs`
- Modify: `twin-primes/twin-primes-rs/src/main.rs`
- Modify: `twin-primes/twin-primes-rs/Cargo.toml`
- Create: `twin-primes/twin-primes-rs/benches/twin_primes.rs`

Note: package name is `twin-primes`; Rust crate name is `twin_primes`.

- [ ] **Step 1: Create `twin-primes/twin-primes-rs/src/lib.rs`**

Cut from `src/main.rs` and paste into `src/lib.rs`:

- `fn small_sieve(limit: u64) -> Vec<u64>` (private)
- `fn sieve_segment(lo: u64, limit: u64, small_primes: &[u64]) -> Vec<u64>` (private)
- `fn find_twin_primes<W: Write>(limit: u64, out: &mut W) -> io::Result<u64>` — make this **`pub fn`**

Add at the top of lib.rs:

```rust
use std::io::{self, Write};
```

Keep in main.rs: `Cli` struct, `fmt_int`, `run`, `main`, tests.

- [ ] **Step 2: Update `twin-primes/twin-primes-rs/src/main.rs`**

Add at the top:

```rust
use twin_primes::find_twin_primes;
```

- [ ] **Step 3: Update `twin-primes/twin-primes-rs/Cargo.toml`**

```toml
[dev-dependencies]
tempfile = "3"
proptest = "1"
criterion = "0.5"

[[bench]]
name = "twin_primes"
harness = false
```

- [ ] **Step 4: Create `twin-primes/twin-primes-rs/benches/twin_primes.rs`**

```rust
use std::io;

use criterion::{black_box, criterion_group, criterion_main, Criterion};
use twin_primes::find_twin_primes;

fn bench_twin_primes(c: &mut Criterion) {
    let mut group = c.benchmark_group("twin-primes");
    group.bench_function("limit=1000", |b| {
        b.iter(|| find_twin_primes(black_box(1_000), &mut io::sink()).unwrap())
    });
    group.bench_function("limit=100000", |b| {
        b.iter(|| find_twin_primes(black_box(100_000), &mut io::sink()).unwrap())
    });
    group.bench_function("limit=1000000", |b| {
        b.iter(|| find_twin_primes(black_box(1_000_000), &mut io::sink()).unwrap())
    });
    group.finish();
}

criterion_group!(benches, bench_twin_primes);
criterion_main!(benches);
```

- [ ] **Step 5: Run cargo test**

```bash
cd twin-primes/twin-primes-rs
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$HOME/.cargo/bin:$PATH"
cargo test
```

- [ ] **Step 6: Run cargo bench**

```bash
cargo bench -- --output-format bencher 2>/dev/null
```

- [ ] **Step 7: Commit**

```bash
cd ../..
git add twin-primes/twin-primes-rs/src/lib.rs \
        twin-primes/twin-primes-rs/src/main.rs \
        twin-primes/twin-primes-rs/Cargo.toml \
        twin-primes/twin-primes-rs/Cargo.lock \
        twin-primes/twin-primes-rs/benches/twin_primes.rs
git commit -m "feat(twin-primes): add lib target and criterion benchmarks"
```

---

### Task 11: goldbach-rs — lib extraction + bench

**Files:**

- Create: `goldbach/goldbach-rs/src/lib.rs`
- Modify: `goldbach/goldbach-rs/src/main.rs`
- Modify: `goldbach/goldbach-rs/Cargo.toml`
- Create: `goldbach/goldbach-rs/benches/goldbach.rs`

Benchmark `build_sieve` (the expensive O(N log log N) pre-computation). `goldbach_pairs` requires a pre-built sieve — benchmark it separately with a fixed sieve.

- [ ] **Step 1: Create `goldbach/goldbach-rs/src/lib.rs`**

Cut from `src/main.rs` and paste into `src/lib.rs`:

- `fn build_sieve(limit: u64) -> Vec<u64>` — make this **`pub fn`**
- `fn is_prime(n: u64, sieve: &[u64]) -> bool` (private)
- `fn goldbach_pairs<W: Write>(limit: u64, sieve: &[u64], out: &mut W) -> io::Result<u64>` — make this **`pub fn`**

Add at the top of lib.rs:

```rust
use std::io::{self, Write};
```

Keep in main.rs: `Cli` struct, `prompt_n`, `run`, `main`, tests.

- [ ] **Step 2: Update `goldbach/goldbach-rs/src/main.rs`**

Add at the top:

```rust
use goldbach::{build_sieve, goldbach_pairs};
```

- [ ] **Step 3: Update `goldbach/goldbach-rs/Cargo.toml`**

```toml
[dev-dependencies]
tempfile = "3"
proptest = "1"
criterion = "0.5"

[[bench]]
name = "goldbach"
harness = false
```

- [ ] **Step 4: Create `goldbach/goldbach-rs/benches/goldbach.rs`**

```rust
use std::io;

use criterion::{black_box, criterion_group, criterion_main, Criterion};
use goldbach::{build_sieve, goldbach_pairs};

fn bench_goldbach(c: &mut Criterion) {
    let mut group = c.benchmark_group("goldbach");
    group.bench_function("sieve=10000", |b| {
        b.iter(|| build_sieve(black_box(10_000)))
    });
    group.bench_function("sieve=100000", |b| {
        b.iter(|| build_sieve(black_box(100_000)))
    });
    group.bench_function("sieve=1000000", |b| {
        b.iter(|| build_sieve(black_box(1_000_000)))
    });
    group.bench_function("pairs=10000", |b| {
        let sieve = build_sieve(10_000);
        b.iter(|| goldbach_pairs(black_box(10_000), &sieve, &mut io::sink()).unwrap())
    });
    group.finish();
}

criterion_group!(benches, bench_goldbach);
criterion_main!(benches);
```

- [ ] **Step 5: Run cargo test**

```bash
cd goldbach/goldbach-rs
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$HOME/.cargo/bin:$PATH"
cargo test
```

- [ ] **Step 6: Run cargo bench**

```bash
cargo bench -- --output-format bencher 2>/dev/null
```

- [ ] **Step 7: Commit**

```bash
cd ../..
git add goldbach/goldbach-rs/src/lib.rs goldbach/goldbach-rs/src/main.rs \
        goldbach/goldbach-rs/Cargo.toml goldbach/goldbach-rs/Cargo.lock \
        goldbach/goldbach-rs/benches/goldbach.rs
git commit -m "feat(goldbach): add lib target and criterion benchmarks"
```

---

### Task 12: sq-rs — lib extraction + bench

**Files:**

- Create: `sq/sq-rs/src/lib.rs`
- Modify: `sq/sq-rs/src/main.rs`
- Modify: `sq/sq-rs/Cargo.toml`
- Create: `sq/sq-rs/benches/sq.rs`

- [ ] **Step 1: Create `sq/sq-rs/src/lib.rs`**

Cut from `src/main.rs` and paste into `src/lib.rs`:

- `fn generate_squares<W: Write>(max_digits: u32, out: &mut W) -> io::Result<u64>` — make this **`pub fn`**

Add at the top of lib.rs:

```rust
use std::io::{self, Write};
```

Keep in main.rs: `Cli` struct, `fmt_int`, `read_line_from`, `prompt_exponent_with`, `write_squares_file`, `run`, `main`, tests.

- [ ] **Step 2: Update `sq/sq-rs/src/main.rs`**

Add at the top:

```rust
use sq::generate_squares;
```

- [ ] **Step 3: Update `sq/sq-rs/Cargo.toml`**

```toml
[dev-dependencies]
tempfile = "3"
proptest = "1"
criterion = "0.5"

[[bench]]
name = "sq"
harness = false
```

- [ ] **Step 4: Create `sq/sq-rs/benches/sq.rs`**

`max_digits` is the exponent X where squares with ≤ 10^X digits are generated. `max_digits=1` → squares with ≤10 digits; `max_digits=2` → ≤100 digits; `max_digits=3` → ≤1000 digits.

```rust
use std::io;

use criterion::{black_box, criterion_group, criterion_main, Criterion};
use sq::generate_squares;

fn bench_sq(c: &mut Criterion) {
    let mut group = c.benchmark_group("sq");
    group.bench_function("max_digits=1", |b| {
        b.iter(|| generate_squares(black_box(1), &mut io::sink()).unwrap())
    });
    group.bench_function("max_digits=2", |b| {
        b.iter(|| generate_squares(black_box(2), &mut io::sink()).unwrap())
    });
    group.bench_function("max_digits=3", |b| {
        b.iter(|| generate_squares(black_box(3), &mut io::sink()).unwrap())
    });
    group.finish();
}

criterion_group!(benches, bench_sq);
criterion_main!(benches);
```

- [ ] **Step 5: Run cargo test**

```bash
cd sq/sq-rs
export PATH="$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/bin:$HOME/.cargo/bin:$PATH"
cargo test
```

- [ ] **Step 6: Run cargo bench**

```bash
cargo bench -- --output-format bencher 2>/dev/null
```

- [ ] **Step 7: Commit**

```bash
cd ../..
git add sq/sq-rs/src/lib.rs sq/sq-rs/src/main.rs \
        sq/sq-rs/Cargo.toml sq/sq-rs/Cargo.lock \
        sq/sq-rs/benches/sq.rs
git commit -m "feat(sq): add lib target and criterion benchmarks"
```

---

### Task 13: CI workflow — benchmarks.yml

**Files:**

- Create: `.github/workflows/benchmarks.yml`

- [ ] **Step 1: Create `.github/workflows/benchmarks.yml`**

```yaml
name: Benchmarks

on:
  workflow_dispatch:
  schedule:
    - cron: "0 2 1 * *"

env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true

jobs:
  benchmark:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v6

      - name: Install GMP/MPFR/MPC
        run: sudo apt-get install -y libgmp-dev libmpfr-dev libmpc-dev

      - uses: dtolnay/rust-toolchain@stable

      - name: Run all benchmarks
        run: |
          for dir in \
            factorial/factorial-rs \
            pi/pi-rs \
            e/e-rs \
            fib/fib-rs \
            collatz/collatz-rs \
            amicable/amicable-rs \
            prime/prime-rs \
            perfect-numbers/perfect-numbers-rs \
            twin-primes/twin-primes-rs \
            goldbach/goldbach-rs \
            sq/sq-rs; do
            echo "Benchmarking $dir..."
            cargo bench --manifest-path "$dir/Cargo.toml" \
              -- --output-format bencher 2>/dev/null >> output.txt || true
          done

      - name: Store benchmark results
        uses: benchmark-action/github-action-benchmark@v1
        with:
          tool: cargo
          output-file-path: output.txt
          github-token: ${{ secrets.GITHUB_TOKEN }}
          auto-push: true
          gh-pages-branch: gh-pages
          benchmark-data-dir-path: dev/bench
          comment-on-alert: false
```

- [ ] **Step 2: Verify YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/benchmarks.yml'))" && echo "YAML valid"
```

Expected: `YAML valid`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/benchmarks.yml
git commit -m "ci: add monthly benchmark workflow publishing to gh-pages"
```

---

### Task 14: Add bench targets to crate Makefiles

**Files:**

- Modify: `factorial/factorial-rs/Makefile`
- Modify: `pi/pi-rs/Makefile`
- Modify: `e/e-rs/Makefile`
- Modify: `fib/fib-rs/Makefile`
- Modify: `collatz/collatz-rs/Makefile`
- Modify: `amicable/amicable-rs/Makefile`
- Modify: `prime/prime-rs/Makefile`
- Modify: `perfect-numbers/perfect-numbers-rs/Makefile`
- Modify: `twin-primes/twin-primes-rs/Makefile`
- Modify: `goldbach/goldbach-rs/Makefile`
- Modify: `sq/sq-rs/Makefile`

Add a `bench` target to each crate's Makefile. The pattern is the same for all 11 crates.

- [ ] **Step 1: Update each Makefile**

For each of the 11 crates, open its Makefile and:

1. Add `bench` to the `.PHONY` line
2. Add this target after the `mutants` target:

```makefile
bench:
	cargo bench -- --output-format bencher
```

Example — `factorial/factorial-rs/Makefile` after edit:

```makefile
.PHONY: factorial lint test clean mutants bench

factorial:
	cargo build --release
	cp target/release/factorial ~/Downloads/factorial

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

mutants:
	cargo mutants --timeout 120 --no-shuffle

bench:
	cargo bench -- --output-format bencher

clean:
	cargo clean
	rm -f ~/Downloads/factorial
```

Apply the same pattern to all 11 crate Makefiles (adjusting the binary name and `rm` target for each).

- [ ] **Step 2: Verify one bench target**

```bash
cd factorial/factorial-rs
make bench 2>/dev/null | head -5
cd ../..
```

Expected: bench output lines.

- [ ] **Step 3: Commit**

```bash
git add \
  factorial/factorial-rs/Makefile \
  pi/pi-rs/Makefile \
  e/e-rs/Makefile \
  fib/fib-rs/Makefile \
  collatz/collatz-rs/Makefile \
  amicable/amicable-rs/Makefile \
  prime/prime-rs/Makefile \
  perfect-numbers/perfect-numbers-rs/Makefile \
  twin-primes/twin-primes-rs/Makefile \
  goldbach/goldbach-rs/Makefile \
  sq/sq-rs/Makefile
git commit -m "chore: add bench Makefile target to all Rust crates"
```

---

### Task 15: PR, smoke test, and docs update

**Files:** none new in the worktree; docs updates go directly on master after merge.

- [ ] **Step 1: Open PR**

```bash
git push origin <branch>
gh pr create \
  --repo brujack/math \
  --title "feat: add criterion benchmarks to all 11 Rust crates" \
  --body "Adds lib target + criterion bench to factorial, pi, e, fib, collatz, amicable, prime, perfect-numbers, twin-primes, goldbach, sq. Monthly benchmarks.yml publishes Chart.js trend charts to gh-pages. Run locally: \`make bench\` in any crate dir."
```

- [ ] **Step 2: Monitor CI**

```bash
gh pr checks <number> --repo brujack/math --watch
```

Expected: all checks pass and PR auto-merges.

- [ ] **Step 3: Trigger benchmark workflow manually**

After the PR merges, trigger a manual run to verify the full pipeline:

```bash
gh workflow run benchmarks.yml --repo brujack/math
sleep 30
gh run list --repo brujack/math --workflow benchmarks.yml --limit 1
```

Wait for the run to complete:

```bash
gh run watch <run-id> --repo brujack/math
```

Expected: run completes successfully. Visit `https://brujack.github.io/math/dev/bench/` — benchmark charts should be visible.

- [ ] **Step 4: Post-merge cleanup**

```bash
git worktree remove /path/to/worktree
git branch -D <branch>
git push origin --delete <branch>
git fetch --prune
git reset --hard origin/master
```

- [ ] **Step 5: Update docs/superpowers/README.md on master** _(do this directly on master — not inside the worktree)_

In `math/docs/superpowers/README.md`, add the plan row and set status to `Done`:

```markdown
| 2026-05-23 | [criterion-benchmarks](plans/2026-05-23-criterion-benchmarks.md) | [spec](https://github.com/brujack/ai-config/blob/master/docs/superpowers/specs/2026-05-23-criterion-benchmarks-design.md) | Done |
```

Add `> **Status: DONE**` banner at the top of this plan file.

Also update `ai-config/docs/superpowers/README.md`: change the criterion-benchmarks row status from `In Progress` to `Done` (the spec row, not a plan row — math plan links go in math repo's README).

Commit directly on master in both repos.
