# GitHub Releases Design

**Date:** 2026-04-21
**Status:** In Progress

## Overview

Add per-project automated GitHub release workflows for the five Rust projects in this repo. Each workflow is manually triggered, builds the release binary, auto-generates release notes from git history, creates a version tag, and publishes a GitHub release with the binary attached as an asset.

## Scope

Five new workflow files, one per Rust project:

```
.github/workflows/release-pi-rs.yml
.github/workflows/release-prime-rs.yml
.github/workflows/release-fib-rs.yml
.github/workflows/release-sq-rs.yml
.github/workflows/release-twin-primes-rs.yml
```

The Python-only projects (`pi.py`, `fib.py`, `sq.py`) produce no binary and get no release workflow.

## Trigger

Each workflow uses `workflow_dispatch` with a single required input:

```yaml
on:
  workflow_dispatch:
    inputs:
      version:
        description: "Version (e.g. v1.2.0)"
        required: true
        type: string
```

The user triggers from the GitHub Actions UI → "Run workflow" → enters the version string. No format validation is enforced in the workflow.

## Tag Format

Tags include the project name prefix to avoid collisions across projects:

| Project        | Tag example          |
| -------------- | -------------------- |
| pi-rs          | `pi-v1.2.0`          |
| prime-rs       | `prime-v1.2.0`       |
| fib-rs         | `fib-v1.2.0`         |
| sq-rs          | `sq-v1.2.0`          |
| twin-primes-rs | `twin-primes-v1.2.0` |

## Job Steps

Each release job runs as a single `release` job with the following ordered steps:

1. **Checkout** — full history (`fetch-depth: 0`) so `git log` can generate notes from the full commit graph
2. **Install dependencies** — project-specific system packages (GMP + MPFR for pi-rs; nothing extra for the others)
3. **Set up Rust toolchain** — `dtolnay/rust-toolchain@stable`
4. **Run tests** — `make test` in the project directory; gates the release on passing tests
5. **Build release binary** — `cargo build --release` in the project directory
6. **Find previous tag** — `git describe --tags --abbrev=0 --match="<project>-v*"` to locate the last release tag for this project
7. **Generate release notes** — `git log <prev-tag>..HEAD --pretty=format:"- %s" -- <project-dir>/`; if no previous tag exists (first release), uses all commits touching the project directory
8. **Create and push tag** — `git tag <project>-v${{ inputs.version }}` + `git push origin <tag>`
9. **Create GitHub release** — uses `softprops/action-gh-release` to publish the release with generated notes and attach the binary as an asset

## Release Notes Format

One bullet per commit subject, auto-generated from commits that touched the project directory since the previous tag. Example:

```
- fix: handle zero-digit edge case in write_pi_file
- feat: add --threads flag for parallel digit computation
- test: add boundary tests for digit count
```

## Dependencies

- `softprops/action-gh-release` — creates the GitHub release and uploads assets in one step
- Existing `make test` and `cargo build --release` targets in each project's Makefile
- `GITHUB_TOKEN` — standard Actions token, no additional secrets needed

## Error Handling

- Tests failing at step 4 aborts the job before any tag is created — no partial release state
- Tag push failure (e.g., tag already exists) aborts before release creation
- Release creation failure leaves an orphan tag; the user must manually delete it and re-run

## What Is Not In Scope

- Automatic triggering on tag push or merge to master
- Cross-platform builds (Linux only, matching existing CI)
- Changelog file generation or CHANGELOG.md maintenance
- Release for Python projects
