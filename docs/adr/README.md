# Architectural Decision Records

Repo-specific decisions for the `math` repository. Cross-cutting decisions (CI tooling, testing frameworks, secrets guardrails) live in [`dotfiles/docs/adr/`](https://github.com/brujack/dotfiles/tree/master/docs/adr).

| ADR                                                                 | Title                                                          | Date       | Status   |
| ------------------------------------------------------------------- | -------------------------------------------------------------- | ---------- | -------- |
| [0001](0001-chudnovsky-algorithm-for-pi.md)                         | Chudnovsky algorithm with binary splitting for π               | 2026-03-20 | Accepted |
| [0002](0002-python-rust-dual-implementation.md)                     | Python + Rust dual implementation strategy                     | 2026-03-20 | Accepted |
| [0003](0003-parallel-segmented-sieve-for-primes.md)                 | Parallel segmented Sieve of Eratosthenes for primes            | 2026-03-20 | Accepted |
| [0004](0004-gmp-rug-crate-for-arbitrary-precision.md)               | GMP/MPFR via rug crate for arbitrary-precision Rust arithmetic | 2026-03-20 | Accepted |
| [0005](0005-rayon-for-shared-memory-parallelism.md)                 | rayon for shared-memory parallelism in Rust                    | 2026-03-20 | Accepted |
| [0006](0006-per-project-ci-workflows-with-test-gate.md)             | Per-project CI workflows with test-before-build gate           | 2026-03-21 | Accepted |
| [0007](0007-prime-swing-factorial.md)                               | Prime swing algorithm for factorial                            | 2026-04-24 | Accepted |
| [0008](0008-recursive-squaring-over-level-product-for-factorial.md) | Recursive squaring over iterative level-product for factorial  | 2026-04-24 | Accepted |
