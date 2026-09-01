# Architectural Decision Records

Repo-specific decisions for the `math` repository. Cross-cutting decisions (CI tooling, testing frameworks, secrets guardrails) live in [`dotfiles/docs/adr/`](https://github.com/brujack/dotfiles/tree/master/docs/adr).

| ADR                                                                       | Title                                                           | Date       | Status                 |
| ------------------------------------------------------------------------- | --------------------------------------------------------------- | ---------- | ---------------------- |
| [0001](0001-chudnovsky-algorithm-for-pi.md)                               | Chudnovsky algorithm with binary splitting for π                | 2026-03-20 | Accepted               |
| [0002](0002-python-rust-dual-implementation.md)                           | Python + Rust dual implementation strategy                      | 2026-03-20 | Accepted               |
| [0003](0003-parallel-segmented-sieve-for-primes.md)                       | Parallel segmented Sieve of Eratosthenes for primes             | 2026-03-20 | Accepted               |
| [0004](0004-gmp-rug-crate-for-arbitrary-precision.md)                     | GMP/MPFR via rug crate for arbitrary-precision Rust arithmetic  | 2026-03-20 | Accepted               |
| [0005](0005-rayon-for-shared-memory-parallelism.md)                       | rayon for shared-memory parallelism in Rust                     | 2026-03-20 | Accepted               |
| [0006](0006-per-project-ci-workflows-with-test-gate.md)                   | Per-project CI workflows with test-before-build gate            | 2026-03-21 | Accepted               |
| [0007](0007-prime-swing-factorial.md)                                     | Prime swing algorithm for factorial                             | 2026-04-24 | Accepted               |
| [0008](0008-recursive-squaring-over-level-product-for-factorial.md)       | Recursive squaring over iterative level-product for factorial   | 2026-04-24 | Accepted               |
| [0009](0009-criterion-benchmarks-for-performance-regression-detection.md) | Criterion benchmarks for performance regression detection       | 2026-05-23 | Accepted               |
| [0010](0010-release-workflow-alignment-with-etch-cli-strategy.md)         | Release workflow alignment with etch-cli strategy               | 2026-05-23 | Accepted               |
| [0011](0011-cargo-nextest-rust-test-runner.md)                            | cargo-nextest as Rust test runner                               | 2026-05-18 | Accepted               |
| [0012](0012-python-mutation-testing-mutmut.md)                            | Python mutation testing with mutmut                             | 2026-05-18 | Superseded by ADR-0022 |
| [0013](0013-hypothesis-proptest-property-based-tests.md)                  | Hypothesis and proptest for property-based testing              | 2026-05-18 | Accepted               |
| [0014](0014-sbom-cosign-keyless-signing.md)                               | SBOM generation and cosign keyless signing for releases         | 2026-05-20 | Accepted               |
| [0015](0015-pyright-type-checking-python.md)                              | Pyright type checking for Python sub-projects                   | 2026-05-22 | Accepted               |
| [0016](0016-pip-audit-advisory-security-scan.md)                          | pip-audit advisory security scan in CI                          | 2026-05-22 | Accepted               |
| [0017](0017-defusedxml-xxe-safe-xml-parsing.md)                           | defusedxml for XXE-safe XML parsing in scripts                  | 2026-05-23 | Accepted               |
| [0018](0018-injectable-io-rust-cli-testability.md)                        | Injectable I/O pattern for Rust CLI testability                 | 2026-04-26 | Accepted               |
| [0019](0019-90-percent-coverage-gate-ci.md)                               | ≥90% line coverage gate enforced in CI                          | 2026-04-27 | Accepted               |
| [0020](0020-dual-mode-ci-prepush-github-actions.md)                       | Dual-mode CI — permanent pre-push hook + PR-only GitHub Actions | 2026-04-21 | Accepted               |
| [0021](0021-processpool-serial-fallback.md)                               | ProcessPoolExecutor serial fallback for Python availability     | 2026-04-29 | Accepted               |
| [0022](0022-python-mutation-testing-cosmic-ray.md)                        | Python mutation testing with cosmic-ray (supersedes ADR-0012)   | 2026-06-13 | Accepted               |
| [0023](0023-pytest-as-python-test-runner.md)                              | pytest as Python test runner (replaces python3 -m unittest)     | 2026-06-19 | Accepted               |
| [0024](0024-mutation-testing-memory-cap.md)                               | Mutation testing memory cap and stateless classification        | 2026-08-01 | Accepted               |
| [0025](0025-attest-mutation-run-progress-with-a-breadcrumb.md)            | Attest mutation-run progress with a breadcrumb, not a step conclusion | 2026-09-01 | Accepted               |
