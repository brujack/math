# Triangle solver

A new Python sub-project, `triangle/`. Give it any combination of side lengths and angles. It derives the missing sides and angles, the area and the perimeter, and draws the triangle in the terminal.

## Problem

math has eleven sub-projects, and every one of them generates N items of growing size. A triangle solver is the first closed-form tool: the input is a handful of numbers, not a size.

The repo's shared machinery assumes the size-N shape in two places:

- `scripts/cli_contract.py` requires `SMOKE_SIZE` and `LARGE_RUN_THRESHOLD`, and its six cases pass a size, `--show`, `--smoke` and `--yes`.
- Every Python project has a twin Rust crate, and several scripts enumerate the Python projects by name.

The operator chose these, in conversation on 2026-11-02:

- **Structure:** Python-only, rendered from the existing Python templates as the ninth Python project. No Rust crate, mirroring the Rust-only goldbach, prime and twin-primes.
- **Drawing:** a Unicode braille canvas. It works in macOS Terminal.app, which cannot show inline images, as well as in iTerm2 and over ssh.
- **Input:** flags, plus interactive prompts when run bare in a terminal.
- **Ambiguous and invalid input:** solve every case that has an answer and explain the rest. The full rules are in Design §2.

## Measurements

Measured 2026-11-02 on `claude`, math at `638bf6f`:

| Claim                                                 | Command                                                                                                                        | Result                                                                                                                                                                                                                    |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python projects are listed in `render_crate_files.py` | `sed -n '38,48p' scripts/render_crate_files.py`                                                                                | `PYTHON_PROJECTS` holds 8 names. `tests/test_crate_uniformity.py:238` asserts `len == 8`; `:95` asserts a group of 8.                                                                                                     |
| The CLI contract is size-shaped                       | `sed -n '246,272p' scripts/cli_contract.py`                                                                                    | Cases are `SIZE`, `SIZE --show`, `--smoke`, `y on stdin`, `THRESHOLD`/`--yes` and `no arguments`. `load_constants` requires `SMOKE_SIZE`.                                                                                 |
| Pre-push runs the contract over a hard-coded list     | `sed -n '219,225p' scripts/pre-push`                                                                                           | `for _entry in amicable:amicable ... sq:sq`: 8 entries.                                                                                                                                                                   |
| Other files name every Python project                 | `grep -rln 'perfect-numbers\|perfect_numbers' .github scripts tests Makefile README.md` (templates and `__pycache__` excluded) | 23 files, including `mutation-testing-python.yml`, `mutation-python-cell.sh`, `mutation-pr-detect.sh`, `pre-commit`, `pre-push`, `README.md` and several tests. Some are Rust lists, so the plan sorts them case by case. |
| Root `CLAUDE.md` is near its cap                      | `wc -c CLAUDE.md`                                                                                                              | 29,985 of 30,000 bytes. It restates "8 Python" in about a dozen places.                                                                                                                                                   |
| The interpreter has what the solver needs             | `python3 -c 'import sys; print(sys.version)'`                                                                                  | 3.14.8. `math`, `argparse`, `shutil` and `sys` are all stdlib.                                                                                                                                                            |

Population: one checkout of `638bf6f`, one machine. The file list is a name grep, so a script that builds the project list some other way would not appear. The plan re-derives the list instead of trusting this count.

## Design

### 1. Shape

`triangle/` holds `triangle.py`, `test_triangle.py`, `CLAUDE.md` and `README.md`.

`triangle.py` is one module in three sections, which are separable and tested separately:
- **Solver.** Pure functions, no I/O.
- **Renderer.** A pure function from a solved triangle and a canvas size to lines.
- **CLI.** Parses input, calls the solver, prints the table and calls the renderer.

It is one file because the Python template's `make mutants` copies only `@MODULE@.py`, `test_@MODULE@.py` and `cosmic-ray.toml` into its scratch directory, and `cosmic-ray.toml` mutates only `@MODULE@.py`. Separate solver and renderer modules would fail to import in the scratch copy, and they would never be mutated.

`test_triangle.py` uses `unittest.TestCase`. The template runs it under pytest (`make test`) and under `python3 -m unittest` (cosmic-ray's `test-command`).

`"triangle"` is added to `PYTHON_PROJECTS`. The templates then render its `Makefile`, `install_deps.sh`, `.github/workflows/triangle-py.yml`, `pyrightconfig.json` and `cosmic-ray.toml`.

The template `install_deps.sh` installs GMP and gmpy2, which triangle does not need. They are installed anyway, because the operator rule is to treat every project identically.

There is no `triangle-rs/`. Every place that enumerates Python projects must include triangle. Every place that assumes a Python project has a paired crate must skip it, or must not assume a crate exists.

### 2. Solver

Sides are `a`, `b`, `c`. Angles are `A`, `B`, `C`, each opposite the side of the same letter. Angles are in degrees unless `--radians` is given. Every computation happens in radians internally.

**Normalisation.** When exactly two angles are known, the third is set to 180° minus their sum. When three are given, their sum must be within 1e-9 relative of 180°.

**Case dispatch**, on the known values after normalisation:

| Known                              | Method                                                                     | Solutions                                                                                                           |
| ---------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| 3 sides (SSS)                      | Law of cosines for each angle                                              | 1, or an error if the triangle inequality fails: `a + b <= c` for any ordering, which includes degenerate triangles |
| 2 sides + included angle (SAS)     | Law of cosines for the third side, then the angles from the law of cosines | 1                                                                                                                   |
| 1 side + 2 angles (ASA/AAS)        | Third angle from the sum, then the law of sines                            | 1                                                                                                                   |
| 2 sides + non-included angle (SSA) | Law of sines for the second angle                                          | 0, 1 or 2                                                                                                           |
| 3 angles, no side (AAA)            | none                                                                       | error: "need at least one side"                                                                                     |

The angles in SAS use the law of cosines rather than the law of sines, because the law of sines cannot tell an obtuse angle from its supplement.

**SSA counts as 2** when the known angle is acute, the side opposite it is shorter than the other known side, and the height `other_side * sin(angle)` is less than the opposite side. The second solution uses the supplementary angle. **It counts as 1** when the height equals the opposite side (a right triangle, within tolerance) or when the opposite side is at least the other side. **It counts as 0** when the opposite side is shorter than the height; this exits 1 with "no triangle: side X is shorter than the height H".

**Overdetermined input** (more than three values): pick three values that determine the triangle uniquely, preferring all sides, then SAS, then ASA/AAS. If the only determining set is SSA, pick it, and report both solutions only when both are consistent with every given value. Every other given value must match the solution within relative tolerance `1e-9`. On a mismatch, exit 1 and name the value, for example "B = 50 conflicts: solution gives B = 36.8699".

**Area** uses Heron's formula in Kahan's numerically stable form: sort so `a >= b >= c`, then `0.25 * sqrt((a+(b+c))(c-(a-b))(c+(a-b))(a+(b-c)))`. **Perimeter** is `a + b + c`.

**Input errors exit 2** with a message. They are:

- fewer than three values;
- fewer than three values after normalisation that still determine nothing, such as one side and one angle;
- any value that is non-finite, zero or negative;
- an angle of 180° or more;
- two angles that sum to 180° or more.

### 3. Output

The table lists the six values, the area and the perimeter, to `--precision N` decimals (default 4). It marks the values that were given and the values that were derived.

The braille drawing comes next:

- **Coordinates.** A is at the origin, B at `(c, 0)`, and C at `(b cos A, b sin A)`.
- **Scaling.** The drawing is scaled to fit the canvas with the aspect ratio preserved. A braille cell holds 2×4 dots, so a cell is treated as one unit wide by two units tall.
- **Edges.** Lines between vertices are drawn with Bresenham's algorithm on the dot grid.
- **Labels.** `A`, `B` and `C` are printed in the cells next to their vertices.
- **Canvas size** comes from `shutil.get_terminal_size()`, capped at the terminal width and at 20 rows. When stdout is not a TTY the canvas is 60×20.

In the two-solution SSA case, both solutions are printed and drawn, headed `Solution 1` and `Solution 2`. `--no-draw` prints the table only.

### 4. Input

- **Flags:** `-a -b -c -A -B -C`, each taking a float. `--radians`, `--precision N`, `--no-draw` and `--smoke` (solve and draw a 3-4-5 triangle) are also accepted.
- **Bare run with stdin a TTY:** prompt for each of the six values in turn. An empty answer means unknown. A prompt line ends in `: `, never a `?`, because `cli_contract`'s marker check rejects `?`.
- **Bare run with stdin not a TTY:** print usage to stderr and exit 2. This matches the other CLIs.

### 5. CLI contract: a second program kind

`cli_contract.py` gains a closed-form kind. A program declares `CONTRACT_ARGS: list[str]` in place of `SMOKE_SIZE` and `LARGE_RUN_THRESHOLD`. For that kind, `load_constants` returns the args and `_build_cases` builds four cases:

1. `CONTRACT_ARGS` runs quietly and exits 0.
2. `--smoke` exits 0.
3. `CONTRACT_ARGS` with `y\n` on stdin exits 0, so stdin is never read.
4. No arguments exits 2 with usage.

Every case keeps the common checks: no `?` on stdout, no files written, and the open-stdin timeout.

A program that declares both kinds, or neither, is a `ContractConfigError` (exit 2). The size-N kind is unchanged, and so are its six cases for the existing eight programs.

triangle's `CONTRACT_ARGS` is `["-a", "3", "-b", "4", "-c", "5"]`. The pre-push loop and `scripts/cli_contract.py`'s callers gain `triangle:triangle`.

### 6. Tests

Everything lives in `test_triangle.py` and, for the contract change, in `tests/`. The cases are:

- **SSS:** 3-4-5, equilateral, and a needle triangle `1, 1, 1.9999999` (the area stays positive and finite). The triangle inequality fails on equality and on violation.
- **SAS:** an acute and an obtuse included angle, with the third angle checked against the law-of-cosines value, not the law-of-sines one.
- **ASA and AAS:** both orderings. Third-angle normalisation, including a given third angle that conflicts.
- **SSA:** 0, 1 (right angle, and opposite side ≥ other side) and 2 solutions. The two-solution case is `a = 6, b = 8, A = 30°`, which gives `B ≈ 41.81°` or `138.19°`.
- **AAA:** refused, both with consistent and with inconsistent sums.
- **Overdetermined:** a consistent fourth value passes. An inconsistent one exits 1 and names the value.
- **Invalid values:** zero, negative, NaN and infinite values, and angles ≥ 180° or summing to ≥ 180°. Each exits 2 with its message.
- **Units:** degrees and radians give the same triangle.
- **Area and perimeter:** checked against known values. The Kahan form is checked against a high-precision reference on the needle triangle.
- **Renderer:** a fixed 20×10 canvas of the 3-4-5 triangle produces an exact expected string. The vertex labels sit in their expected cells. A degenerate-looking needle still draws three edges.
- **CLI:**
  - prompt parsing with empty answers;
  - non-TTY bare run exits 2;
  - `--no-draw`;
  - `--precision`;
  - two-solution output headed `Solution 1`/`Solution 2`.
- **cli_contract:**
  - the closed-form kind passes on triangle;
  - a program declaring both kinds, or neither, is a config error;
  - a closed-form stub that reads stdin fails on timeout;
  - the existing eight programs still pass.

Coverage is held at ≥ 90% (`make coverage`). `make mutants` runs through the template.

### 7. Docs

- `triangle/CLAUDE.md` and `triangle/README.md`.
- A row in the root `README.md` CLI table, with its badge.
- Root `CLAUDE.md` changes, kept under the 30,000-byte cap:
  - Add triangle to the sub-project list.
  - Replace restated counts ("8 Python", "19 install sites") with count-free wording. A restated count is fixed by deleting the number.
  - Pay for any added line with an equal deletion.
- `ai-config/docs/knowledge/math-*.md` belongs to the ai-config session, so changes there go to that session by message.

## Requirements

- **R1.** The solver section of `triangle/triangle.py` solves SSS, SAS, ASA, AAS and SSA input given as any three of `a b c A B C`. It returns every valid solution: 0, 1 or 2 for SSA and exactly 1 for the others. Each solution carries all six values, the area (Kahan-stable Heron) and the perimeter.
- **R2.** `triangle.py` exits 2 with a message on fewer than three values, AAA, a non-finite, zero or negative value, an angle of 180° or more, or two angles summing to 180° or more. It exits 1 on an SSA case with no solution and on an overdetermined input whose extra value disagrees beyond `1e-9` relative. That message names the conflicting value.
- **R3.** The renderer section of `triangle/triangle.py` renders a solved triangle onto a braille canvas of a given width and height, with vertex labels `A`, `B` and `C`. For the 3-4-5 triangle on a 20×10 canvas, `test_triangle.py` pins its output as an exact string.
- **R4.** `triangle.py` accepts `-a -b -c -A -B -C --radians --precision N --no-draw --smoke`. A bare run prompts for each value when stdin is a TTY, and exits 2 with usage when it is not. In the two-solution SSA case it prints and draws both solutions, headed `Solution 1` and `Solution 2`.
- **R5.** `"triangle"` is in `PYTHON_PROJECTS`. Its `Makefile`, `install_deps.sh`, `triangle-py.yml`, `pyrightconfig.json` and `cosmic-ray.toml` are rendered by `render_crate_files.py --write`. `tests/test_crate_uniformity.py` passes with the new count. No `triangle/triangle-rs/` exists.
- **R6.** `scripts/cli_contract.py` accepts a program that defines `CONTRACT_ARGS` and runs the four closed-form cases on it. A program defining both kinds, or neither, exits 2 as a config error. The six size-N cases are unchanged for the existing programs.
- **R7.** Every script, workflow and test that enumerates the Python projects (re-derived by the plan, not taken from the Measurements count) includes triangle. Every one that pairs a Python project with a Rust crate does not require `triangle/triangle-rs`.
- **R8.** `triangle/test_triangle.py` covers every case listed in Design §6. `make coverage` in `triangle/` reports ≥ 90%.
- **R9.** Root `CLAUDE.md` names triangle among the sub-projects and contains no restated Python-project count. `wc -c CLAUDE.md` is ≤ 30,000.
- **V1.** On macOS Terminal.app, `python3 triangle/triangle.py -a 3 -b 4 -c 5` and the SSA two-solution example draw legible triangles with correct vertex labels.
- **V2.** This PR's CI is green, including `triangle-py.yml` and `scripts.yml`.
- **V3.** `make mutants` in `triangle/` completes with a non-zero `caught` count.
- **N1.** No third-party runtime dependency in `triangle/`: standard library only.
- **N2.** No Rust crate for triangle, and no change to any Rust crate or Rust template.
- **N3.** No change to the six size-N contract cases or their checks for the existing eight programs.
