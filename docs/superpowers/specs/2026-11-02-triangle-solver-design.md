# Triangle solver

A new Python sub-project, `triangle/`. Give it any combination of side lengths and angles. It derives the missing sides and angles, the area and the perimeter, and draws the triangle in the terminal.

## Problem

math has eleven sub-projects, and every one of them generates N items of growing size. A triangle solver is the first closed-form tool: the input is a handful of numbers, not a size.

The repo's shared machinery assumes the size-N shape in two places:

- `scripts/cli_contract.py` requires `SMOKE_SIZE` and `LARGE_RUN_THRESHOLD`, and its six cases pass a size, `--show`, `--smoke` and `--yes`.
- Every Python project has a twin Rust crate, and several scripts enumerate the Python projects by name.

The operator chose these, in conversation on 2026-11-02:

- **Structure:** Python-only, rendered from the existing Python templates as the ninth Python project. No Rust crate, mirroring the Rust-only goldbach, prime and twin-primes.
- **Drawing:** a Unicode braille canvas. It works in macOS Terminal.app, which cannot show inline images, as well as in iTerm2 and over ssh. The operator ran a probe in Terminal.app on 2026-11-02: `⣿`×30, `#`×30, and `⠁`+28 blanks+`⠈`. All three lines end in the same column and the dots show at both ends, so the fallback font draws braille exactly one cell wide.
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

There is no `triangle-rs/`. The template `install_deps.sh` tells the reader to "run `@CRATE@/@CRATE@-rs/install_deps.sh` instead". For triangle that names a file that does not exist, so the line changes to wording that names no crate.

Every place that enumerates Python projects must include triangle. The Risk lens checked these and found no pairing assumption:
- `mutation-pr-detect.sh`, `mutation-python-cell.sh`, `mutation-testing-python.yml`, `pre-push` and `pre-commit` all list Python directories on their own.
- `crate_build_target.bats`, `test_deny_policy.py` and the release monitors iterate `CRATES` only.

Hard-coded counts do break:
- `test_crate_uniformity.py` (8);
- `test_tool_pins.py` (19 sites, which becomes 21);
- `test_mutation_workflows.py` (80 units, which becomes 90);
- `test_python_workflow_paths.py` (eight workflows). Every place that assumes a Python project has a paired crate must skip it, or must not assume a crate exists.

### 2. Solver

Sides are `a`, `b`, `c`. Angles are `A`, `B`, `C`, each opposite the side of the same letter. Angles are in degrees unless `--radians` is given. Every computation happens in radians internally.

**Normalisation.** When exactly two angles are given, the third is 180° minus their sum. When all three are given, the first two in `A, B, C` order determine the third, and the given third is treated as an extra value (see below).

**Case dispatch**, on the known values after normalisation:

| Known                              | Method                                                                     | Solutions                                                                                                           |
| ---------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| 3 sides (SSS) | Each angle from the sides by Kahan's formula (below), not `acos`, which loses digits on thin triangles | 1, or exit 1 "no triangle" if the triangle inequality fails (`a + b <= c` for any ordering, which includes degenerate triangles) |
| 2 sides + included angle (SAS) | Law of cosines for the third side, then the other angles as in SSS | 1 |
| 1 side + 2 angles (ASA/AAS)        | Third angle from the sum, then the law of sines                            | 1                                                                                                                   |
| 2 sides + non-included angle (SSA) | Law of sines for the second angle, counted by the ordered rule below | 0, 1 or 2 |
| 3 angles, no side (AAA)            | none                                                                       | error: "need at least one side"                                                                                     |

The SAS angles come from the side lengths, as in SSS, rather than from the law of sines, because the law of sines cannot tell an obtuse angle from its supplement.

**Kahan's angle formula** ("Miscalculating Area and Angles of a Needle-like Triangle"). Label the sides so that `p ≥ q`, and let `r` be the side opposite the wanted angle. Then:
- `μ = r − (p − q)` when `q ≥ r`, else `μ = q − (p − r)`;
- the angle is `2·atan(sqrt(((p − q) + r)·μ / ((p + (q + r))·((p − r) + q))))`.

The parentheses are part of the formula and must be kept as written. Worked check, 3-4-5: `p=4, q=3, r=5`, so `μ = 4`, and the angle is `2·atan(sqrt(24/24)) = 90°`.

**SSA solution count.** Let the known angle be `X`, its opposite side `x`, and the other known side `y`. Let `ε` be machine epsilon. The cases are tested in this order:
1. **`X ≥ 90°`:** 1 solution if `x > y`, otherwise 0. The height does not enter.
2. **`X < 90°`, with `h = y·sin X`:**
   - `x ≥ y`: 1 solution.
   - `|x − h| ≤ 4ε·max(x, h)`: 1 solution, with a right angle opposite `y`. This catches `4, 8, 30°`, where `h = 3.9999999999999996` is 1 ulp low. It is deliberately no wider: near tangency the angle error grows like the square root of the side error, so a 1e-9 band would merge two distinct solutions that differ at the default precision.
   - `x < h`: 0 solutions.
   - otherwise: 2 candidates. The second uses the supplement of the first candidate angle. It is kept only when its third angle exceeds `1e-12` rad, because when `x` is just below `y` that angle rounds to 0 and would crash the post-check.

Every returned solution is checked: all three angles are positive and sum to 180°, and all sides are positive. A failed check raises an exception (a bug); it is never printed.

A zero-solution SSA exits 1. The message is "no triangle: side X is shorter than the height H", or for an obtuse `X`, "no triangle: side x must be longer than y opposite an angle of 90° or more".

**Extra values: reported, not judged.** With more than three values, the solver picks the determining set in this order: all sides, then SAS, then ASA/AAS. With four or more values and at least one side, one of these always exists. Every other given value is printed beside its solved value with the difference, for example:

```
extra  B  given 53.13  solved 53.130102  diff +0.000102
```

The run always exits 0. There is no tolerance, so there is no pass/fail rule to get wrong; the reader decides whether 37 against 36.8699 counts as a match. The solved value prints at `--precision + 2` decimals, so a non-zero difference is always visible.

**Area** uses Heron's formula in Kahan's numerically stable form: sort so `a >= b >= c`, then `0.25 * sqrt((a+(b+c))(c-(a-b))(c+(a-b))(a+(b-c)))`. **Perimeter** is `a + b + c`.

**Input errors exit 2** with a message. Every test asserts the exact text. They are:

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

- **Flags:** `-a -b -c -A -B -C`, each taking a float. Angles are read and printed in the input unit: degrees by default, radians with `--radians`. `--radians`, `--precision N`, `--no-draw` and `--smoke` (solve and draw a 3-4-5 triangle) are also accepted.
- **Bare run with stdin a TTY:** prompt for each of the six values in turn. An empty answer means unknown. An answer that is not a positive finite number re-prompts with a one-line reason. A prompt line ends in `: `, never a `?`, because `cli_contract`'s marker check rejects `?`.
- **Bare run with stdin not a TTY:** print usage to stderr and exit 2. This matches the other CLIs.

### 5. CLI contract: a second program kind

`cli_contract.py` gains a closed-form kind. Such a program declares `CONTRACT_ARGS: list[str]` and `CONTRACT_EXPECT: str` in place of `SMOKE_SIZE` and `LARGE_RUN_THRESHOLD`.

The size-N `_common_problems` cannot be reused. It fails a run that writes no output file, and its only check on content is the output-file comparison. The closed-form kind therefore gets its own check function, `_closed_form_problems`, which checks:
- not timed out;
- exit 0;
- no `?` on stdout;
- **`CONTRACT_EXPECT` appears on stdout as a whole numeric token**. The pattern is `(?<![\d.])` + the escaped value + `(?![\d.])`, so `6.0000` does not match inside `36.0000` or `16.00001`;
- no file written.

There are three cases:
1. `CONTRACT_ARGS` with the open, empty stdin pipe. This catches a stdin reader by timeout, and the expected-output check proves the program solved.
2. `--smoke` passes the same checks.
3. No arguments exits 2 with usage.

A `ContractConfigError` (exit 2) is raised for a program that declares both kinds, neither, only one of `CONTRACT_ARGS`/`CONTRACT_EXPECT`, an empty `CONTRACT_ARGS`, or an empty `CONTRACT_EXPECT`. The size-N kind is unchanged, and so are its six cases for the existing eight programs. A program that runs but prints nothing fails case 1, and so does one that prints the area a missing `sqrt` would give (`36.0000`). The harness's tests pin that with a stub of each kind.

triangle's `CONTRACT_ARGS` is `["-a", "3", "-b", "4", "-c", "5"]` and its `CONTRACT_EXPECT` is `"6.0000"`, the area at the default precision. The pre-push loop and `scripts/cli_contract.py`'s callers gain `triangle:triangle`.

### 6. Tests

Everything lives in `test_triangle.py` and, for the contract change, in `tests/`. The cases are:

- **SSS:** 3-4-5, equilateral, and a needle triangle `1, 1, 1.9999999` (the area stays positive and finite). The triangle inequality fails on equality and on violation.
- **SAS:** an acute and an obtuse included angle, with the third angle checked against the law-of-cosines value, not the law-of-sines one.
- **ASA and AAS:** both orderings. Third-angle normalisation, including a given third angle that conflicts.
- **SSA:**
  - Solution counts:
    - 0 solutions.
    - 1 solution: the right angle `4, 8, 30°`, and the case `x ≥ y`.
    - 2 solutions: `a = 6, b = 8, A = 30°`, giving `B = 41.8103°` or `138.1897°`.
  - Obtuse or right known angle:
    - `7, 8, 120°` → 0
    - `8, 8, 120°` → 0
    - `8, 8, 90°` → 0
    - `9, 8, 120°` → 1
  - Boundaries:
    - `x = 7.9999999999, y = 8, A = 0.001°` returns 1 solution and does not raise.
    - `x = 4·(1 + 5e-10), y = 8, A = 30°` returns 2 distinct solutions.
  - Property: for each case, first assert that the returned list is non-empty, then that every angle in it is positive.
- **AAA:** refused, both with consistent and with inconsistent sums.
- **Extra values:**
  - `-a 3 -b 4 -c 5 -B 53.13` exits 0 and prints the line `extra B given 53.13 solved 53.130102 diff +0.000102`.
  - `-a 3 -b 4 -c 5 -A 37` exits 0 and shows a non-zero diff.
  - `-c 1 -A 60.1 -B 60 -C 60` solves from `A, B` and reports `C` as an extra.
  - Each extra line names the right letter and the right solved value.
- **Invalid values:** zero, negative, NaN and infinite values, and angles ≥ 180° or summing to ≥ 180°. Each exits 2. The test asserts the exact message.
- **Units:** degrees and radians give the same triangle. With `--radians`, the table prints angles in radians.
- **Area and perimeter:** checked against known values.
- **Numerical accuracy:** checked against precomputed high-precision references.
  - Kahan area on `1e5, 99999.99979, 0.00029`, where naive Heron is off by 2.7e-8.
  - Kahan angles within 1e-12 relative on `1e-4, 1, 1.00009` and on the `1e5` needle. On the needle the naive half-angle form is off by 2.7e-8, and `acos` loses the angle entirely.
- **Renderer:** a fixed 20×10 canvas of the 3-4-5 triangle produces an exact expected string. The vertex labels sit in their expected cells. A degenerate-looking needle still draws three edges.
- **CLI:**
  - prompt parsing with empty answers;
  - non-TTY bare run exits 2;
  - `--no-draw`;
  - `--precision`;
  - two-solution output headed `Solution 1`/`Solution 2`.
- **cli_contract:**
  - the closed-form kind passes on triangle;
  - stubs that exit 0 and print nothing, `36.0000` or `16.00001` all fail case 1;
  - an empty `CONTRACT_EXPECT` is a config error;
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
  - "All 11 projects" (lines 15 and 62) is about the Rust crates. It becomes "all 11 crates", or loses the count, because there are now 12 projects.
  - Pay for any added line with an equal deletion.
- `ai-config/docs/knowledge/math-*.md` belongs to the ai-config session, so changes there go to that session by message.

## Requirements

- **R1.** The solver section of `triangle/triangle.py` solves SSS, SAS, ASA, AAS and SSA input given as any three of `a b c A B C` and returns every valid solution: 0 or 1 for SSS, 0, 1 or 2 for SSA by the ordered rule in Design §2, and exactly 1 for SAS, ASA and AAS. Angles from sides use Kahan's formula as given in Design §2, never `acos`. Each solution carries all six values, the area (Kahan-stable Heron) and the perimeter, and has only positive angles and sides.
- **R2.** `triangle.py` exits 2 with a stated message on fewer than three values, AAA, a non-finite, zero or negative value, an angle of 180° or more, or two angles summing to 180° or more. It exits 1 with a "no triangle" message on an SSS input that fails the triangle inequality and on an SSA input with no solution. With more than three values it solves from the determining set (sides, then SAS, then ASA/AAS), prints each extra value beside its solved value and the difference, and exits 0.
- **R3.** The renderer section of `triangle/triangle.py` renders a solved triangle onto a braille canvas of a given width and height, with vertex labels `A`, `B` and `C`. For the 3-4-5 triangle on a 20×10 canvas, `test_triangle.py` pins its output as an exact string.
- **R4.** `triangle.py` accepts `-a -b -c -A -B -C --radians --precision N --no-draw --smoke`. A bare run prompts for each value when stdin is a TTY, and exits 2 with usage when it is not. In the two-solution SSA case it prints and draws both solutions, headed `Solution 1` and `Solution 2`.
- **R5.** `"triangle"` is in `PYTHON_PROJECTS`. Its `Makefile`, `install_deps.sh`, `triangle-py.yml`, `pyrightconfig.json` and `cosmic-ray.toml` are rendered by `render_crate_files.py --write`. `tests/test_crate_uniformity.py` passes with the new count. No `triangle/triangle-rs/` exists.
- **R6.** `scripts/cli_contract.py` accepts a program that defines `CONTRACT_ARGS` and `CONTRACT_EXPECT` and runs the three closed-form cases on it. Case 1 fails a run whose stdout lacks `CONTRACT_EXPECT` as a whole numeric token. An empty `CONTRACT_ARGS` or `CONTRACT_EXPECT` is a config error. A program that defines both kinds, neither, or only one of the two closed-form constants exits 2 as a config error. The six size-N cases are unchanged for the existing programs.
- **R7.** Every script, workflow and test that enumerates the Python projects (re-derived by the plan, not taken from the Measurements count) includes triangle. Every one that pairs a Python project with a Rust crate does not require `triangle/triangle-rs`.
- **R8.** `triangle/test_triangle.py` covers every case listed in Design §6. `make coverage` in `triangle/` reports ≥ 90%.
- **R9.** Root `CLAUDE.md` names triangle among the sub-projects. It contains no restated Python-project count and no "all 11 projects". `wc -c CLAUDE.md` is ≤ 30,000.
- **V1.** On macOS Terminal.app, `python3 triangle/triangle.py -a 3 -b 4 -c 5` and the SSA two-solution example draw legible triangles with correct vertex labels.
- **V2.** This PR's CI is green, including `triangle-py.yml` and `scripts.yml`.
- **V3.** `make mutants` in `triangle/` completes with a non-zero `caught` count.
- **N1.** No third-party runtime dependency in `triangle/`: standard library only.
- **N2.** No Rust crate for triangle, and no change to any Rust crate or Rust template.
- **N3.** No change to the six size-N contract cases or their checks for the existing eight programs.

## Multi-Lens Review

Reviewed at commit: `e48dcac` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

**Finding.** As specified, the closed-form contract kind would pass a program that solves nothing.
- `_common_problems` (`cli_contract.py:179-194`) fails any run that writes no output file. That is the opposite of the spec's "no files written" claim, and it was the contract's only content check.
- Without it, a stub `sys.exit(2 if len(sys.argv) == 1 else 0)` passes all four proposed cases.
- Case 3 (`y\n` on stdin) duplicated case 1.

The single-module premise and the size-shaped contract were both confirmed from the code.

**Assumption.** Braille renders legibly in Terminal.app. This was settled by the operator's probe (see Problem).

**Disposition.** Addressed. The operator chose to fix as proposed: `CONTRACT_EXPECT` on stdout, its own check function, and 3 cases.

### Ergonomics

**Finding.** The tool rejects its own printed output. The 1e-9 tolerance against 4-dp output means `-a 3 -b 4 -c 5 -B 53.1301` exits 1 with two identical numbers in the message, and rounded textbook angle sums are rejected too. Checked and fine:
- argparse keeps `-a` and `-A` distinct;
- degrees are the default.

Minor points left to the plan:
- a re-prompt on bad interactive input;
- a two-solution layout.

**Assumption.** That the overdetermined path is for checking rounded answers, so the operator's choice of tolerance settles it.

**Disposition.** Addressed. The operator chose a tolerance set by input precision: half a unit in the last typed digit, plus a read-back test. Superseded in round 2 (below).

### Risk

**Findings.**
- The SSA rule was wrong for an obtuse or right known angle. `8, 8, 120°` and `8, 8, 90°` were counted 1 instead of 0. `7, 8, 120°` matched no rule and would have printed `C = −21.8°`.
- The float ordering problem at `4, 8, 30°`.
- 1e-9 is tighter than acos's own error, measured against mpmath: 1.1e-9 on the needle and 7.3e-8 on `1e-4, 1, 1.00009`.
- The contract stub problem, the same as Goal-Fit's.

Checked and clean:
- No Python-crate pairing assumption anywhere; only the hard-coded counts break.
- The template `install_deps.sh` points at a `-rs` installer that will not exist.
- "All 11 projects" in CLAUDE.md.
- The SSA example values and the Kahan-Heron formula are correct.

**Assumption.** Braille cell alignment in Terminal.app. Settled by the operator's probe.

**Disposition.** Addressed. The operator accepted the proposed fixes:
- ordered SSA rule;
- obtuse tests;
- Kahan atan2 angles;
- the precision-based tolerance;
- count-free docs;
- crate-agnostic `install_deps.sh` wording.

### Adversarial Spec Review (comparison/judge designs only)

N/A — the spec has no comparison, evaluator or ambiguous-criteria trigger.

### Round 2 (all three lenses)

Reviewed at commit: `e1a48ba`.

Goal-Fit, Ergonomics and Risk each independently found that the round-1 tolerance rule fails:
- bare integers get ±0.5, so `-A 37` is accepted against 36.87;
- `1e3` gets ±500;
- §6's "`60.1 + 60 + 60` fails" test contradicts the rule;
- the read-back promise is false: feeding back a printed side switches the solve to SSS, and rounding then shifts the typed angle, so 74 of 80 probed SAS cases are rejected;
- argparse `float` would lose the typed digits that the rule needs.

Risk also found:
- an SSA crash when `x` is just below `y`, because the second solution's third angle rounds to 0;
- a 1e-9 tangency band about 10⁶ too wide, which merges distinct solutions;
- an underspecified Kahan formula that the test could not tell from the naive form;
- a dead overdetermined-SSA branch;
- no exit code for the triangle inequality;
- R1's "exactly 1" for SSS, which can be 0.

Goal-Fit and Risk found that `"6.0000"` matches inside `36.0000` (a missing-`sqrt` bug) and that an empty `CONTRACT_EXPECT` was not rejected.

Checked and fine:
- the ordered SSA rule's counts;
- the visibility of the conflict message;
- stdout decoding of braille;
- the template trigger for the contract.

Assumption, named by all three: whether extra values are rounded measurements or exact claims. The operator settled it by removing the judgement entirely.

Disposition: Addressed (operator, 2026-11-02). Extra values are reported, not judged: each is printed with its solved value and the difference, the run exits 0, and the tolerance mechanism is removed. The other fixes, as listed:
- the explicit Kahan formula, with needle tests;
- a `4ε` tangency band;
- the SSA second-solution guard;
- an exit code for the triangle inequality;
- angles printed in the input unit;
- a whole-token `CONTRACT_EXPECT`, rejected when empty;
- exact message text in reject tests;
- non-empty-first property assertions;
- a re-prompt on bad interactive input.
