# Triangle Solver Implementation Plan

spec: docs/superpowers/specs/2026-11-02-triangle-solver-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `triangle/`, a Python-only, template-rendered solver. It derives every missing side and angle plus the area and perimeter from any three of `a b c A B C`, and draws the triangle on a braille canvas.

**Architecture:** One module, `triangle/triangle.py`, in three sections (solver, renderer, CLI), tested by `triangle/test_triangle.py` (unittest). `scripts/cli_contract.py` gains a closed-form program kind. triangle joins `PYTHON_PROJECTS` and every list that names the Python projects. The work runs on branch `feat/triangle-solver` in `.worktrees/triangle` and ships as one draft PR.

**Tech Stack:** Python 3.14 standard library only (`math`, `argparse`, `shutil`, `sys`). Tests use unittest run under pytest. Tooling: ruff, pyright, cosmic-ray, bats.

## Global Constraints

- N1: no third-party runtime dependency in `triangle/`; standard library only.
- N2: no Rust crate for triangle, and no change to any Rust crate or Rust template.
- N3: no change to the six size-N contract cases or their checks for the existing eight programs.
- Read `~/.claude/standards/python.md` before writing any `.py` file.
- Root `CLAUDE.md` must stay ≤ 30,000 bytes (`wc -c CLAUDE.md`). It is 29,985 now.
- Never hand-edit a rendered file. Edit `scripts/crate_templates/python/*`, then run `python3 scripts/render_crate_files.py --write`.
- Run every gate synchronously with `< /dev/null`. Root `make test` takes about 60 s, under the 600 s cap.
- Kahan angle formula (spec §2). Label the sides so `p ≥ q`, with `r` opposite the wanted angle. Then `μ = r − (p − q)` if `q ≥ r`, else `μ = q − (p − r)`, and `angle = 2·atan(sqrt(((p − q) + r)·μ / ((p + (q + r))·((p − r) + q))))`. Keep the parentheses as written.
- SSA third side (spec §2): `z1 = y·cos X + sqrt((x − h)(x + h))` and `z2 = (y − x)(y + x)/z1`.
- High-precision test references are computed from the double inputs (`mpmath` is not a runtime dependency). Precompute them and paste them in as literals. Never compute them from decimal strings.

## Session verification (orchestrator, after Task 6)

- `make lint && make test`, run in the worktree, both exit 0.
- `make -C triangle test` and `make -C triangle coverage` both exit 0, with coverage ≥ 90%.
- `python3 triangle/triangle.py -a 3 -b 4 -c 5` prints area `6.0000`, perimeter `12.0000` and a braille drawing.
- `-a 6 -b 8 -A 30` prints `Solution 1` (B 41.8103) and `Solution 2` (B 138.1897).
- `-a 3 -b 4 -c 5 -B 53.13` prints `extra B given 53.13 solved 53.130102 diff +0.000102354` and exits 0.
- V1 is checked by the operator on the Mac. V2 is checked in CI. V3: `MUTANT_SHARD=0/10 make -C triangle mutants` reports `caught > 0`.

## Orchestrator steps

1. Run `git worktree add .worktrees/triangle -b feat/triangle-solver origin/master`.
2. Dispatch Tasks 1–6 in order. Start each prompt with: **IMPORTANT: All work must happen in `/home/bruce/git-repos/personal/math/.worktrees/triangle/`. Do not cd anywhere else.**
3. Run the session verification above, then Phase 3, then `gh pr create --draft`, then `gh pr checks --watch`. Once green, run `gh pr ready`.

---

### Task 1: cli_contract closed-form kind

```yaml-task
id: 1
description: Add the CONTRACT_ARGS/CONTRACT_EXPECT closed-form kind to scripts/cli_contract.py with its own check function, three cases and config errors, tested by stub fixtures
role: executor
model: sonnet
tdd: required
requirements: [R6]
acceptance:
  - cmd: python3 -m unittest tests.test_cli_contract_harness < /dev/null
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
  - cmd: make test < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/cli_contract.py, tests/test_cli_contract_harness.py, tests/fixtures/cli_contract/closed_form_ok.py, tests/fixtures/cli_contract/closed_form_silent.py, tests/fixtures/cli_contract/closed_form_wrong_area.py, tests/fixtures/cli_contract/closed_form_reader.py, tests/fixtures/cli_contract/closed_form_both_kinds.py, tests/fixtures/cli_contract/closed_form_empty_expect.py]
depends_on: []
```

- [ ] **RED.** In `tests/test_cli_contract_harness.py`, follow the existing fixture pattern and add fixtures and cases:
  - `closed_form_ok.py` defines `CONTRACT_ARGS = ["-a", "3", "-b", "4", "-c", "5"]` and `CONTRACT_EXPECT = "6.0000"`. It prints `area 6.0000` for those args and for `--smoke`, and exits 2 with usage when run with no args. It passes.
  - `closed_form_silent.py` prints nothing and fails case 1.
  - `closed_form_wrong_area.py` prints `36.0000`, and a second variant prints `16.00001`. Both fail case 1.
  - `closed_form_reader.py` reads stdin and fails on timeout.
  - `closed_form_both_kinds.py` defines `SMOKE_SIZE` and `CONTRACT_ARGS`, which is a `ContractConfigError` and exits 2.
  - `closed_form_empty_expect.py` sets `CONTRACT_EXPECT = ""`, which is a config error. A program that defines only one of the two constants is also a config error.
  - Every existing size-N fixture keeps passing unchanged (N3).
- [ ] **GREEN.**
  - `load_constants` returns a tagged kind.
  - Add `_closed_form_problems`, which checks: no timeout; exit 0; no `?` on stdout; `re.search(r"(?<![\d.])" + re.escape(expect) + r"(?![\d.])", stdout)`; and no file written.
  - `_build_cases` returns 3 cases for the closed-form kind: `CONTRACT_ARGS`, `--smoke`, and no args (which must exit 2).
- [ ] Commit `feat(cli-contract): closed-form program kind`.

### Task 2: solver section

```yaml-task
id: 2
description: Write the solver section of triangle/triangle.py (normalisation, determining set, SSS/SAS/ASA/AAS/SSA, Kahan angles and area, post-check, input errors) with its tests
role: executor
model: sonnet
tdd: required
requirements: [R1]
acceptance:
  - cmd: bash -c 'cd triangle && python3 -m pytest test_triangle.py -q < /dev/null'
    exit_code: 0
  - cmd: pyright triangle/triangle.py triangle/test_triangle.py
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [triangle/triangle.py, triangle/test_triangle.py]
depends_on: [1]
```

- [ ] Implement spec Design §2 exactly, one behaviour at a time, writing each test RED before its code.
  - **API:** `solve(values: dict[str, float], radians: bool = False) -> Solved`. `Solved` has `solutions: list[Triangle]` and `extras: list[Extra]`. `Triangle` holds `a`, `b`, `c` and `A`, `B`, `C` in radians, plus `area` and `perimeter`. `Extra` holds `name`, `given` and `solved`.
  - **Errors:** raise `TriangleInputError(msg)` for exit-2 cases and `NoTriangle(msg)` for exit-1 cases, using the exact messages from spec §2.
- [ ] Write every solver test from spec §6:
  - SSS, SAS, ASA/AAS, SSA and AAA cases;
  - the extra-value determining-set examples `a, b, A, B` and `a, b, A, B, C`;
  - invalid values, each asserting its exact message;
  - units;
  - area and perimeter;
  - numerical accuracy against literal mpmath-from-double references: the 1e5 needle area, and angles on both thin triangles to ≤ 1e-12 relative;
  - SSA boundaries `7.9999999999, 8, 0.001°` (2 solutions; the second third side is `1.00000008e-10`) and `7.9999999999e12, 8e12, 0.001°` (third side `100.0000000152`);
  - the property test, which asserts the list is non-empty before checking that every angle is positive.
- [ ] Commit `feat(triangle): solver`.

### Task 3: braille renderer section

```yaml-task
id: 3
description: Write the braille renderer section of triangle/triangle.py (A at origin, B on x-axis, aspect-correct scaling, Bresenham on the 2x4 dot grid, A/B/C labels) with exact-string tests
role: executor
model: sonnet
tdd: required
requirements: [R3]
acceptance:
  - cmd: bash -c 'cd triangle && python3 -m pytest test_triangle.py -q < /dev/null'
    exit_code: 0
  - cmd: pyright triangle/triangle.py triangle/test_triangle.py
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [triangle/triangle.py, triangle/test_triangle.py]
depends_on: [2]
```

- [ ] **API.** Add `render(t: Triangle, width: int, height: int) -> list[str]`, which is pure (no I/O).
  - Place the triangle with A at the origin, B at (c, 0) and C at (b cos A, b sin A).
  - Scale to fit while preserving the aspect ratio: 2 dots per cell across and 4 down, with a cell taken as 1 unit wide by 2 tall.
  - Draw edges with Bresenham.
  - Put the labels `A`, `B` and `C` in the cells next to their vertices.
- [ ] **Tests.**
  - The 3-4-5 triangle on a 20×10 canvas equals an exact expected list of strings. Generate it once, inspect it by eye, then pin it.
  - Each label sits in its expected cell.
  - A needle triangle still has dots set along all three edges.
  - A canvas with zero size raises.
- [ ] Commit with `feat(triangle): braille renderer`.

### Task 4: CLI section

```yaml-task
id: 4
description: Write the CLI section of triangle/triangle.py (flags, TTY prompts with re-prompt, non-TTY usage exit 2, table, extras lines, two-solution headings, --no-draw/--precision/--radians/--smoke, CONTRACT_ARGS/CONTRACT_EXPECT) with tests
role: executor
model: sonnet
tdd: required
requirements: [R2, R4, R8]
acceptance:
  - cmd: bash -c 'cd triangle && python3 -m pytest test_triangle.py -q < /dev/null'
    exit_code: 0
  - cmd: bash -c 'cd triangle && python3 -m pytest --cov=triangle --cov-fail-under=90 test_triangle.py -q < /dev/null'
    exit_code: 0
  - cmd: bash -c 'cd triangle && python3 ../scripts/cli_contract.py triangle.py < /dev/null'
    exit_code: 0
  - cmd: pyright triangle/triangle.py triangle/test_triangle.py
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [triangle/triangle.py, triangle/test_triangle.py]
depends_on: [3]
```

- [ ] Implement spec §3 and §4:
  - argparse flags `-a -b -c -A -B -C` (float) and `--radians --precision N --no-draw --smoke`;
  - with no args and a TTY on stdin, prompt for all six values. Prompt lines end `: ` and never contain `?`. An empty answer means unknown, and a bad answer re-prompts with a reason;
  - with no args and no TTY, print usage to stderr and exit 2;
  - print a table marking each value given or derived;
  - print `extra <N> given <text> solved <v:.{p+2}f> diff <solved-given:+.6g>` with single spaces;
  - under `Solution 1`/`Solution 2` headings, print each solution's table and drawing;
  - size the canvas from `shutil.get_terminal_size()`, capped at 20 rows; when stdout is not a TTY, use 60×20;
  - map `TriangleInputError` to exit 2 and `NoTriangle` to exit 1, each with its message on stderr;
  - set the module constants `CONTRACT_ARGS = ["-a", "3", "-b", "4", "-c", "5"]` and `CONTRACT_EXPECT = "6.0000"`.
- [ ] Write the spec §6 CLI tests through `main(argv)` and a subprocess:
  - prompt parsing with empty and bad answers (monkeypatch `sys.stdin.isatty` and `input`);
  - non-TTY bare run exits 2;
  - `--no-draw` and `--precision`;
  - two-solution headings;
  - exact extra line text;
  - `--radians` output.
- [ ] Commit `feat(triangle): CLI`.

### Task 5: project integration

```yaml-task
id: 5
description: Add triangle to PYTHON_PROJECTS and every hand-maintained Python project list, render the template files, make install_deps.sh crate-agnostic, and fix the count tests
role: executor
model: sonnet
tdd: required
requirements: [R5, R7]
acceptance:
  - cmd: python3 scripts/render_crate_files.py --check
    exit_code: 0
  - cmd: make -C triangle test < /dev/null
    exit_code: 0
  - cmd: make -C triangle coverage < /dev/null
    exit_code: 0
  - cmd: bash -c 'test ! -e triangle/triangle-rs'
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
  - cmd: make test < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [scripts/render_crate_files.py, scripts/crate_templates/python/install_deps.sh, triangle/Makefile, triangle/install_deps.sh, triangle/pyrightconfig.json, triangle/cosmic-ray.toml, .github/workflows/triangle-py.yml, amicable/install_deps.sh, collatz/install_deps.sh, e/install_deps.sh, factorial/install_deps.sh, fib/install_deps.sh, perfect-numbers/install_deps.sh, pi/install_deps.sh, sq/install_deps.sh, scripts/pre-push, scripts/pre-commit, scripts/mutation-pr-detect.sh, scripts/mutation-python-cell.sh, .github/workflows/mutation-testing-python.yml, tests/test_crate_uniformity.py, tests/test_tool_pins.py, tests/test_mutation_workflows.py, tests/test_python_workflow_paths.py, tests/test_workflow_continue_on_error.py, tests/scripts/pre_push.bats, tests/scripts/mutation_pr_detect.bats, tests/scripts/mutation_python_cell.bats]
depends_on: [4]
```

- [ ] **Re-derive the list. Do not trust this plan.** Run `git grep -nE 'perfect-numbers|perfect_numbers' -- .github scripts tests Makefile ':!scripts/crate_templates' ':!*.pyc'`. For each hit, decide whether it enumerates Python projects (add triangle) or Rust crates (leave it). If a hit is outside `files_touched`, stop and report it; do not edit it.
- [ ] **RED.** Update the count tests first and run them, so they fail on the current tree:
  - `test_crate_uniformity` `len(PYTHON_PROJECTS)` 8→9, and the group at `:95`;
  - `test_tool_pins` sites 19→21;
  - `test_mutation_workflows` 80→90 units, renaming "eighty" to "ninety";
  - `test_python_workflow_paths` eight→nine.

  Where a test checks a list, add triangle to the bats list tests too.

- [ ] **GREEN.**
  - Add `"triangle"` to `PYTHON_PROJECTS`.
  - Change the template `install_deps.sh` `-rs` pointer line to wording that names no crate, e.g. "Rust crates have their own `<project>-rs/install_deps.sh`".
  - Run `render_crate_files.py --write`.
  - Add triangle (dir only, no `-rs`) to:
    - `pre-push` (both lists, with `triangle:triangle` in the contract loop);
    - `pre-commit`;
    - `PYTHON_DIRS` in both mutation scripts;
    - `all_dirs` in `mutation-testing-python.yml`.
- [ ] Commit `feat(triangle): integrate as the ninth Python project`.

### Task 6: docs

```yaml-task
id: 6
description: Write triangle/CLAUDE.md and README.md, add the root README CLI row and badge, and update root CLAUDE.md to name triangle with count-free wording under the byte cap (docs-only, no behaviour change, so TDD does not apply)
role: executor
model: sonnet
tdd: not-applicable
requirements: [R9]
acceptance:
  - cmd: bash -c '[ "$(wc -c < CLAUDE.md)" -le 30000 ]'
    exit_code: 0
  - cmd: bash -c 'grep -q "triangle/" CLAUDE.md && ! grep -qE "8 Python|all 11 projects|19 install sites|19 total" CLAUDE.md'
    exit_code: 0
  - cmd: bash -c 'grep -q "triangle" README.md'
    exit_code: 0
  - cmd: python3 scripts/claude_md_budget.py
    exit_code: 0
  - cmd: make lint < /dev/null
    exit_code: 0
max_retries: 3
files_touched: [CLAUDE.md, README.md, triangle/CLAUDE.md, triangle/README.md]
depends_on: [5]
```

- [ ] **Root `CLAUDE.md`.**
  - Add `triangle/` Python to the sub-project line.
  - Replace "8 Python", "19 install sites", "19 total" and "8 × 10" with count-free wording.
  - Change "all 11 projects" to "all 11 crates".
  - Pay for every addition with a deletion so the byte total does not grow, and confirm with `wc -c`.
- [ ] **Root `README.md`.** Add a CLI table row and a `triangle-py.yml` badge (`badge.svg?event=pull_request`), following the existing rows.
- [ ] **`triangle/CLAUDE.md` and `triangle/README.md`.** Cover usage, the cases, the extra-value report and the braille drawing.
- [ ] Commit `docs(triangle): CLAUDE.md, README`.

## Non-goal check

Verdicts from the reviewer: 2 CLEAR, 1 UNCLEAR, 0 CONFLICT.

- **N1, UNCLEAR.**
  - Reviewer's finding: "triangle.py uses only the standard library ... Task 5 generates triangle/install_deps.sh from the shared Python template, and that template installs GMP/MPFR and every pinned package."
  - Resolution: an amendment in the spec. N1 now limits only runtime imports in `triangle/triangle.py`, and exempts the shared template installer as Design §1 already intended. The plan is unchanged.
- **N2, CLEAR.** The only template edit is the Python `install_deps.sh` wording, and the plan checks with `test ! -e triangle/triangle-rs`.
- **N3, CLEAR.** The closed-form kind is a separate path, and every existing size-N fixture keeps passing unchanged.
