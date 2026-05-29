# Changelog


## Bug Fixes

- close git fds 3-9 before running Python tests in pre-push

- kill resource_tracker daemons after each test run

- remove local keyword outside function scope

- only test dirs with changed .py/.rs source files

- skip local tests when >6 sub-projects changed

- correct Hypothesis test oracle in test_pairs_within_limit (#57)

- correct Hypothesis test oracle in test_perfect_numbers_below_limit (#58)

- replace xml.etree with defusedxml in test_metrics.py (#69)



## CI

- add PR title lint, coverage gates, and benchmarks to Python CLIs

- add per-sub-project coverage badges (#56)

- make snyk-scan advisory (continue-on-error)

- add release workflows for collatz, goldbach, amicable, perfect-numbers (#68)

- standardize upload-artifact to @v7 across all Rust workflows

- bump checkout →v6, cosign →v4, upload-artifact stragglers →v7

- enable regression alerts at 130% threshold



## Documentation

- document ProcessPoolExecutor resource_tracker gotcha in pre-push

- add test-metrics plan

- mark test-metrics plan done

- add sbom-cosign plan

- mark sbom-cosign plan done

- complete README coverage for all 11 projects

- document pyright setup and mode table

- pip-audit CI per-sub-project advisory step

- pip-audit CI implementation plan

- CLI integration tests for amicable, collatz, perfect-numbers, factorial

- CLI integration tests implementation plan

- mark criterion-benchmarks Done

- document defusedxml pip install requirement in factorial-rs workflow

- add dev-cycle improvements to backlog

- remove benchmark alerts — done

- add Criterion benchmarks, pyright, pip-audit, and CLI tests to README



## Features

- adopt cargo-nextest as test runner (#53)

- add Python mutation testing with mutmut (#54)

- switch from Dependabot to Renovate

- flaky-test tracking via nextest CI profile and test-metrics artifacts (#59)

- SBOM generation and cosign signing for releases (#60)

- add pyright type checking and fix macOS spawn deadlock (#62)

- add pyright type checking to all Python sub-projects (#63)

- upgrade pyright to standard mode for 6 sub-projects (#64)

- add pip-audit advisory security step to all Python workflows (#65)

- add git-cliff config and make target (#66)

- add Criterion benchmarks to all 11 Rust crates (#70)



## Testing

- add Hypothesis and proptest property-based tests (#55)

- add CLI integration tests for collatz and goldbach (#61)

- add CLI entry-point integration tests for amicable, collatz, perfect-numbers, factorial (#67)


