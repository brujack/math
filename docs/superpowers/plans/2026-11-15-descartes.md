# Descartes Implementation Plan

spec: docs/superpowers/specs/2026-11-15-descartes-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `descartes` sub-project: a tangent-circle solver and an integral Apollonian packing enumerator, drawn in braille, in Python (PR1) and Rust (PR2).

**Architecture:** One module per language with the same functions: `descartes_fourth`, `validate_root`, `pack`, `root_centres`, `solve`, `visible`, `render`, then CLI glue. Per-project files are rendered from `scripts/crate_templates/`. Parity is checked by a Rust integration test that runs the Python program.

**Tech Stack:** Python 3.14 standard library (`argparse`, `cmath`, `math`, `shutil`), pytest, ruff, pyright 1.1.411; Rust edition 2024, clap 4, cargo-nextest, cargo-tarpaulin, cargo-mutants 27.1.0.

## Global Constraints

- All per-project files come from `scripts/render_crate_files.py --write`; never hand-edit a rendered copy (N5).
- No `rug`, `gmpy2`, `rayon`, threads, or arbitrary precision (N2, N4). No GUI/SVG back end (N1). No zero-curvature circles, no non-integral packings (N3).
- No change to any existing sub-project's source or tests; root `scripts/`, `tests/`, hooks and docs may change to register the project (N5).
- Python K 1-6, Rust K 1-8; `SMOKE_SIZE = 2`, `LARGE_RUN_THRESHOLD = None`.
- Exit 2 = malformed input, exit 1 = well-formed input with no answer; every message names the operation and the input.
- Elapsed time goes to stderr only.
- Solve tangency per pair: `|d_ij − (r_i ± r_j)| ≤ 1e-9 × (|r_i| + |r_j|)`; pairs checked 1-2, 1-3, 2-3.
- Piped canvas is 60 × 24 cells in both languages.
- Work from a per-worktree venv: `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt ruff==0.17.4 pytest==9.1.1 pytest-cov==7.1.0 hypothesis==6.168.5 cosmic-ray==8.7.0`. The shared pyenv `pyright` is 1.1.414 and fails `tests/test_root_pyright_scope.py`.
- Root `CLAUDE.md` is 29,991 bytes against a 30,000 ceiling (`scripts/claude_md_budget.py`); any addition must trim an equal amount whose facts already live in an ai-config knowledge file (grep there first).
- Bash coverage measured 49% against `FLOOR=24` (auto-merge run 42550879158); two new `install_deps.sh` add about 114 uncovered lines, about 47%.

## Verification

- `cd descartes && python3 descartes.py 3 --no-draw` prints `root -1 2 2 3`, `circles 3328`, `distinct 324`, `Saved to descartes_1e3.txt`; the file has 324 lines starting `2`, `3`, `6`.
- `python3 descartes.py --solve -1,0,0 2,0.5,0 3,0,0.6666666666666666 --no-draw` lists curvatures 2 and 6.
- The Rust binary gives the same lines; `cargo test` in `descartes/descartes-rs` runs `tests/parity.rs` green.
- Root `make test`, `make -C descartes test` and `make -C descartes/descartes-rs test` exit 0; CI green on both PRs, including `mutation-pr`.
- Edge cases: empty packing (`--root -11 21 24 28` at K=1), a non-root `--root` (`-1 2 3 6`), K out of range, a non-tangent `--solve`, a negative first `--solve` triple in Rust.

## Orchestrator steps

- PR1: worktree `.worktrees/descartes-py`, branch `feat/descartes-py`, Tasks 1-5. After Task 5 run root `make test </dev/null` once, then Phase 3, push, `gh pr create --draft`, watch CI, `gh pr ready` when green.
- PR2: after PR1 merges, worktree `.worktrees/descartes-rs`, branch `feat/descartes-rs` from `origin/master`, Tasks 6-11, root `make test </dev/null`, record V1 in the PR body, then Phase 3 and the same draft/ready sequence.

---

### Task 1: Python packing core

```yaml-task
id: 1
description: descartes_fourth, validate_root with reduction, and pack, with a test-only geometric oracle
role: executor
model: sonnet
tdd: required
requirements: [R2, R3, R4, R5, R20, R21]
acceptance:
  - cmd: python3 -m pytest descartes/test_descartes.py -q
    exit_code: 0
  - cmd: ruff check descartes && ruff format --check descartes/descartes.py descartes/test_descartes.py
    exit_code: 0
  - cmd: 'd=$(mktemp -d) && printf "{\"executionEnvironments\": [{\"root\": \"%s/descartes\"}], \"stubPath\": \"%s/typings\", \"typeCheckingMode\": \"standard\"}" "$PWD" "$PWD" > "$d/pyrightconfig.json" && pyright -p "$d/pyrightconfig.json" descartes/descartes.py descartes/test_descartes.py'
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes.py, descartes/test_descartes.py]
depends_on: []
```

**Files:** create `descartes/descartes.py`, `descartes/test_descartes.py`.

- `descartes_fourth(k1, k2, k3) -> tuple[float, float]`: `k1+k2+k3 ± 2√(k1k2+k2k3+k3k1)`; a radicand below `-1e-12 × max(|k|)` raises `NoSolution`, otherwise it is clamped at 0.
- `validate_root(a, b, c, d) -> tuple[int, int, int, int]`: integers only (`BadInput` else); `(Σk)² == 2Σk²` and exactly one negative value (`NoSolution` else, the message naming the root and both sides, e.g. `(Σk)²=49, 2Σk²=50`); then repeatedly reflect the largest while that lowers it; return ascending.
- `pack(root, n) -> tuple[int, bytearray]`: count each root curvature `0 < k ≤ n`; seed the four root reflections when `≤ n` with no growth test; then explicit-stack DFS keeping `k'` only when `k_i < k' ≤ n`; set bit `k` for each counted circle. The growth test is load-bearing even though no valid quadruple fails it (R21): never remove it as dead code. `pack` raises `BadInput` for `n > N_MAX = 10**6` (R20); ceiling tests lower `N_MAX` first.
- Tests: every R2 pair, the R3 set, R5 reductions, and an oracle class: breadth-first over geometric quadruples from `root_centres` (Task 2 adds it; until then build centres inline in the test), dedup by `(k, round(x,7), round(y,7))`, counting only `k ≤ n`, compared with `pack` for every R2 root at every n ≤ 1000.

**Interfaces:** Produces `NoSolution(Exception)`, `BadInput(Exception)`, `descartes_fourth`, `validate_root`, `pack` as above.

### Task 2: Python geometry

```yaml-task
id: 2
description: root_centres, solve with per-pair tangency, and visible
role: executor
model: sonnet
tdd: required
requirements: [R9, R10]
acceptance:
  - cmd: python3 -m pytest descartes/test_descartes.py -q
    exit_code: 0
  - cmd: ruff check descartes && ruff format --check descartes/descartes.py descartes/test_descartes.py
    exit_code: 0
  - cmd: 'd=$(mktemp -d) && printf "{\"executionEnvironments\": [{\"root\": \"%s/descartes\"}], \"stubPath\": \"%s/typings\", \"typeCheckingMode\": \"standard\"}" "$PWD" "$PWD" > "$d/pyrightconfig.json" && pyright -p "$d/pyrightconfig.json" descartes/descartes.py descartes/test_descartes.py'
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes.py, descartes/test_descartes.py]
depends_on: [1]
```

- `Circle = tuple[float, float, float]` `(k, x, y)`.
- `root_centres(root) -> list[Circle]`: bounding circle at the origin, second on +x inside it, third from the centre-distance triangle with negative `y²` clamped to 0, fourth by the complex theorem; never calls the tangency check. Test the collinear root `(-2,3,6,7)`.
- `check_tangent(circles)`: pairs 1-2, 1-3, 2-3; first failure raises `NoSolution("circles i and j are not tangent ...")`, adding a full-precision hint when any input has 6 or fewer decimal places. Zero curvature raises `BadInput`.
- `solve(c1, c2, c3) -> list[Circle]`: complex theorem, keeping for each `k4` the centre tangent to all three.
- `visible(root, limit) -> list[Circle]`: the `pack` search carrying centres, `z' = (2·Σ(k·z) of the other three − k_i·z_i) / k'`, with the same growth test and a `limit ≤ N_MAX` check, so it is bounded like `pack` (R20, R21).
- Tests: R9 values within 1e-9; R10 scaled ×100 passes; `0.6667` fails naming 1 and 3 with the hint; `0.7` fails; zero curvature is `BadInput`; `visible((-1,2,2,3), 30)` returns the 38 circles of R2.

**Interfaces:** Consumes Task 1. Produces `Circle`, `root_centres`, `check_tangent`, `solve`, `visible`.

### Task 3: Python render

```yaml-task
id: 3
description: braille render of a circle list
role: executor
model: sonnet
tdd: required
requirements: [R11]
acceptance:
  - cmd: python3 -m pytest descartes/test_descartes.py -q
    exit_code: 0
  - cmd: ruff check descartes && ruff format --check descartes/descartes.py descartes/test_descartes.py
    exit_code: 0
  - cmd: 'd=$(mktemp -d) && printf "{\"executionEnvironments\": [{\"root\": \"%s/descartes\"}], \"stubPath\": \"%s/typings\", \"typeCheckingMode\": \"standard\"}" "$PWD" "$PWD" > "$d/pyrightconfig.json" && pyright -p "$d/pyrightconfig.json" descartes/descartes.py descartes/test_descartes.py'
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes.py, descartes/test_descartes.py]
depends_on: [2]
```

- `render(circles, width, height) -> list[str]`: `height` lines of `width` braille cells (base `0x2800`, 2×4 dots per cell); midpoint-circle rasterisation; scale to the bounding box of all circles. It reads only the `(k, x, y)` list.
- Tests: `render([], 60, 24)` gives 24 lines of 60 `'⠀'`; one circle gives at least one non-blank line; the R9 five circles at 60×24 match a pinned snapshot; widths below the minimum raise `BadInput`.

**Interfaces:** Consumes `Circle`. Produces `render`, `PIPE_WIDTH = 60`, `PIPE_HEIGHT = 24`.

### Task 4: Python CLI

```yaml-task
id: 4
description: ADR-0030 CLI with --root, --solve, --precision, --no-draw; outputs and exit codes
role: executor
model: sonnet
tdd: required
requirements: [R6, R7, R8, R9, R10, R11]
acceptance:
  - cmd: python3 -m pytest descartes/test_descartes.py -q
    exit_code: 0
  - cmd: python3 scripts/cli_contract.py descartes/descartes.py
    exit_code: 0
  - cmd: ruff check descartes && ruff format --check descartes/descartes.py descartes/test_descartes.py
    exit_code: 0
  - cmd: 'd=$(mktemp -d) && printf "{\"executionEnvironments\": [{\"root\": \"%s/descartes\"}], \"stubPath\": \"%s/typings\", \"typeCheckingMode\": \"standard\"}" "$PWD" "$PWD" > "$d/pyrightconfig.json" && pyright -p "$d/pyrightconfig.json" descartes/descartes.py descartes/test_descartes.py'
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes.py, descartes/test_descartes.py]
depends_on: [3]
```

- Copy `parse_args`, `refuse_large_run` and the prompt/end-of-input text from `amicable/amicable.py`, then add `--root A B C D`, `--solve K,X,Y ×3`, `--precision P`, `--no-draw`; `--solve` excludes SIZE. K outside 1-6 exits 2 naming the range.
- Packing stdout order: `root a b c d`, `circles N`, `distinct M`, `Saved to <file>`, drawing; elapsed time on stderr. File `descartes_1eK.txt` or `descartes_1eK_root_A_B_C_D.txt`, one curvature per line ascending; empty packing gives an empty file and no drawing.
- Solve prints the table at full precision (`repr`) or `--precision P` places, then the drawing.
- Canvas: terminal size on a TTY, else 60×24. Drawing filter: curvature `≤ min(N, 2 × width × 2)`.
- `NoSolution` exits 1, `BadInput` exits 2, message on stderr.
- Tests run `main([...])` with `capsys` and a `tmp_path` cwd for every R6-R11 case, asserting exit codes, stdout lines and file contents.

**Interfaces:** Consumes Tasks 1-3. Produces `main(argv: list[str] | None = None) -> None`, `SMOKE_SIZE`, `LARGE_RUN_THRESHOLD`.

### Task 5: Register the Python project

```yaml-task
id: 5
description: render descartes Python files and register the project in every project list, test and doc
role: executor
model: sonnet
tdd: required
requirements: [R1, R12, R18]
acceptance:
  - cmd: python3 scripts/render_crate_files.py --check
    exit_code: 0
  - cmd: make -C descartes test </dev/null
    exit_code: 0
  - cmd: make -C descartes coverage </dev/null
    exit_code: 0
  - cmd: make test-python </dev/null
    exit_code: 0
  - cmd: bats tests/scripts/mutation_pr_detect.bats tests/scripts/mutation_python_cell.bats tests/scripts/pre_push.bats tests/scripts/makefile.bats
    exit_code: 0
  - cmd: make lint
    exit_code: 0
  - cmd: '[ "$(wc -c < CLAUDE.md)" -le 30000 ]'
    exit_code: 0
max_retries: 3
files_touched: [scripts/render_crate_files.py, descartes/Makefile, descartes/install_deps.sh, descartes/pyrightconfig.json, descartes/cosmic-ray.toml, descartes/mutants-equivalent.toml, .github/workflows/descartes-py.yml, .github/workflows/mutation-testing-python.yml, scripts/mutation-pr-detect.sh, scripts/mutation-python-cell.sh, scripts/pre-commit, scripts/pre-push, tests/test_crate_uniformity.py, tests/test_mutants_equivalent.py, tests/test_mutation_workflows.py, tests/test_python_workflow_paths.py, tests/test_workflow_continue_on_error.py, tests/scripts/mutation_pr_detect.bats, tests/scripts/mutation_python_cell.bats, tests/scripts/pre_push.bats, tests/scripts/makefile.bats, .gitignore, descartes/CLAUDE.md, descartes/README.md, README.md, CLAUDE.md]
depends_on: [4]
```

- Add `descartes` to `PYTHON_PROJECTS`; run `--write`; create an empty `descartes/mutants-equivalent.toml`.
- Add `descartes` beside `triangle` in every list: `all_dirs` in `mutation-testing-python.yml`, `PYTHON_DIRS` in both scripts, `dirs=` in `scripts/pre-commit`, the `scripts/pre-push` dir loop, its line-204 module regex and its `_entry` harness loop (`descartes:descartes`).
- Update pinning tests: `test_crate_uniformity.py` Python counts 9 to 10 (lines 96 and 298), the `PROJECTS` tuples, `ALL9` (rename `ALL10`) and the loops in the bats files, `HARNESS_PROJECTS`, plus a `descartes` copy of the triangle-specific cases in `mutation_python_cell.bats` and `pre_push.bats`.
- `.gitignore`: `descartes_1e*.txt`. Docs: `descartes/CLAUDE.md` and `README.md` (usage, layout, the known solve paste-back limits), root `README.md` CLI table, root `CLAUDE.md` sub-project line within 30,000 bytes.

**Interfaces:** Consumes Task 4. Produces the registered Python project.

### Task 6: Rust scaffold, registration and descartes_fourth

```yaml-task
id: 6
description: create descartes-rs, register it as crate 12, and implement descartes_fourth
role: executor
model: sonnet
tdd: required
requirements: [R13, R19]
acceptance:
  - cmd: python3 scripts/render_crate_files.py --check
    exit_code: 0
  - cmd: make -C descartes/descartes-rs test </dev/null
    exit_code: 0
  - cmd: make test-python </dev/null
    exit_code: 0
  - cmd: make lint
    exit_code: 0
max_retries: 3
files_touched: [scripts/render_crate_files.py, descartes/descartes-rs/Cargo.toml, descartes/descartes-rs/Cargo.lock, descartes/descartes-rs/src/lib.rs, descartes/descartes-rs/src/main.rs, descartes/descartes-rs/.cargo/mutants.toml, descartes/descartes-rs/Makefile, descartes/descartes-rs/install_deps.sh, descartes/descartes-rs/rustfmt.toml, descartes/descartes-rs/.config/nextest.toml, .github/workflows/descartes-rs.yml, .github/workflows/release-descartes-rs.yml, scripts/pre-commit, scripts/pre-push, tests/test_crate_uniformity.py, tests/test_mutation_workflows.py, tests/test_mutants_exclusions.py]
depends_on: [5]
```

- `Cargo.toml` as `amicable/amicable-rs/Cargo.toml`: edition 2024, `license = "MIT"`, `[lints.rust]` `unsafe_code = "forbid"`, `missing_debug_implementations = "warn"`, `unexpected_cfgs` with `cfg(tarpaulin_include)`; `[lints.clippy]` `wrong_self_convention = "warn"`; dependencies clap 4 (derive) only; no `rust-version`.
- Add `descartes` to `CRATES`; `--write`. `.cargo/mutants.toml`: `additional_cargo_test_args = ["--lib", "--bins", "--test", "cli"]` only.
- Counts 11 to 12 in `test_crate_uniformity.py` (lines 168, 177, 247) and `test_mutation_workflows.py` line 694; `test_mutants_exclusions.py`: add `descartes/descartes-rs` to `EXPECTED`, allow a file whose single key is `additional_cargo_test_args`, with a test that a file holding neither key still fails.
- `descartes/descartes-rs` in `scripts/pre-commit` and the `scripts/pre-push` dir loop.
- `lib.rs`: `pub fn descartes_fourth(k1: f64, k2: f64, k3: f64) -> Result<(f64, f64), DescartesError>` with unit tests; `main.rs` thin stub calling `run` with injectable writers.

**Interfaces:** Produces `DescartesError { BadInput(String), NoSolution(String) }` (derive Debug), `descartes_fourth`.

### Task 7: Rust packing core

```yaml-task
id: 7
description: validate_root with reduction and pack in i64 with a distinct bitmap
role: executor
model: sonnet
tdd: required
requirements: [R14, R22]
acceptance:
  - cmd: make -C descartes/descartes-rs test </dev/null
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes-rs/src/lib.rs]
depends_on: [6]
```

- `pub fn validate_root(q: [i64; 4]) -> Result<[i64; 4], DescartesError>` and `pub fn pack(root: [i64; 4], n: i64) -> (i64, Vec<u64>)`, same rules as Python Task 1, including the growth test and a core ceiling `n ≤ 10^8` (R22).
- Unit tests: every R2 pair, the R3 set, the R5 reductions, the R6 errors.

### Task 8: Rust geometry and render

```yaml-task
id: 8
description: root_centres, check_tangent, solve, visible and render in Rust
role: executor
model: sonnet
tdd: required
requirements: [R14]
acceptance:
  - cmd: make -C descartes/descartes-rs test </dev/null
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes-rs/src/lib.rs]
depends_on: [7]
```

- Same rules as Python Tasks 2-3, complex arithmetic hand-written on `(f64, f64)` (no new crate). Unit tests: R9 values within 1e-9, R10 tolerance cases, collinear root, `render(&[], 60, 24)` blank grid, a non-blank single circle.

### Task 9: Rust CLI

```yaml-task
id: 9
description: clap CLI matching Python, with tests/cli.rs failure modes
role: executor
model: sonnet
tdd: required
requirements: [R14, R17]
acceptance:
  - cmd: make -C descartes/descartes-rs test </dev/null
    exit_code: 0
  - cmd: 'cd descartes/descartes-rs && cargo tarpaulin --fail-under 90'
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes-rs/src/main.rs, descartes/descartes-rs/src/lib.rs, descartes/descartes-rs/tests/cli.rs]
depends_on: [8]
```

- Same flags and outputs as Python Task 4; K 1-8; `--solve` sets `allow_hyphen_values`; `run<W: Write, E: Write>` holds all logic; `main` is `#[cfg(not(tarpaulin_include))]`.
- `tests/cli.rs` uses `env!("CARGO_BIN_EXE_descartes")` and `tempfile`: missing K, K 0 and 9, non-integer K, `--root -1 2 2 4`, the non-tangent `--solve`, each asserting exit code and stderr; plus R8's empty packing and R11's 24×60 non-blank drawing.

### Task 10: Python BATS failure modes and parity

```yaml-task
id: 10
description: BATS failure modes for the Python CLI and the Rust parity test
role: executor
model: sonnet
tdd: required
requirements: [R15, R17]
acceptance:
  - cmd: bats tests/scripts/descartes.bats
    exit_code: 0
    stdout_match: 'ok 5 '
  - cmd: make -C descartes/descartes-rs test </dev/null
    exit_code: 0
max_retries: 3
files_touched: [tests/scripts/descartes.bats, descartes/descartes-rs/tests/parity.rs]
depends_on: [9]
```

- `tests/scripts/descartes.bats` (pattern of `tests/scripts/amicable.bats`): missing K, K out of range, non-integer K, bad root, non-tangent `--solve`, exit code and stderr each.
- `tests/parity.rs`: runs `python3 ../descartes.py` from the crate dir and the binary in temp dirs for the R15 cases; asserts both exit 0 and print `circles`, then byte-identical files and count lines, and solve tables within 1e-12; no drawing comparison.

### Task 11: Rust docs

```yaml-task
id: 11
description: crate CLAUDE.md and README, root README and CLAUDE.md rows for the crate (docs-only, no behaviour change)
role: executor
model: sonnet
tdd: not-applicable
requirements: [R19]
acceptance:
  - cmd: '[ "$(wc -c < CLAUDE.md)" -le 30000 ]'
    exit_code: 0
  - cmd: grep -q 'descartes/descartes-rs' README.md
    exit_code: 0
max_retries: 2
files_touched: [descartes/descartes-rs/CLAUDE.md, descartes/descartes-rs/README.md, README.md, CLAUDE.md]
depends_on: [10]
```

- Crate docs: commands, K 1-8, the `mutants.toml` parity exclusion and why, paste-back limits. Root rows within the 30,000-byte budget. The orchestrator runs root `make test` after this task.

## Requirements coverage note

R16 is withdrawn by amendment and split into R18 (PR1) and R19 (PR2), because rendering `descartes` as a Python project writes `descartes-py.yml` in PR1 and `render_crate_files.py --check` fails until it exists.

## Execution notes

- 2026-11-15, Task 1 re-plan (swap approach): `pyright descartes/descartes.py ...` from the repo root resolves `import descartes` to the `descartes/` directory as a namespace package (triangle shows the same 14 errors from root), so Tasks 1-4 gate pyright through a temporary config rooted at `descartes/` until Task 5 renders `descartes/pyrightconfig.json`. Proven: 0 errors on Task 1's code, 1 error on a seeded `BAD: int = "x"`.

## Non-goal check

Run 2026-11-15 by a fresh reviewer against N1-N5: CLEAR 5, CONFLICT 0, UNCLEAR 0.

- N1 CLEAR: the braille render (Tasks 3, 8) is terminal text, not a window, SVG or plotting back end.
- N2 CLEAR: Task 8 adds no crate and no task adds threads.
- N3 CLEAR: Task 2 makes zero curvature in `--solve` a `BadInput`.
- N4 CLEAR: Python native ints in `validate_root` are not deliberate arbitrary precision; Rust uses `i64`/`f64`.
- N5 CLEAR, on the assumption that `mutation-testing-python.yml` is not rendered; confirmed: `render_crate_files.py --kind` renders only per-project files (`python/py.yml` and the other `python/*` kinds).
