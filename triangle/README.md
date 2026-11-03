# triangle

Solve a triangle from any three of its sides and angles. It prints a table of all six values plus area and perimeter, then draws the triangle in braille.

Python only (`triangle.py`, standard library, no external dependencies). There is no Rust crate.

## Quick Start

```bash
cd triangle
bash install_deps.sh                       # pinned Python packages (one time)
make run                                   # interactive prompts (terminal only)
python3 triangle.py -a 3 -b 4 -c 5         # SSS
python3 triangle.py -a 6 -b 8 -A 30 --no-draw   # SSA, two solutions
python3 triangle.py --smoke                # solve and draw 3-4-5
make test
```

## Options

| Flag              | Meaning                                  |
| ----------------- | ---------------------------------------- |
| `-a -b -c`        | side lengths                             |
| `-A -B -C`        | angles, degrees (radians with `--radians`) |
| `--radians`       | angles in radians, input and output      |
| `--precision N`   | decimals in the table (default 4)        |
| `--no-draw`       | table only                               |
| `--smoke`         | solve and draw 3-4-5                     |

With no value flags at a terminal, the program prompts for `a`, `b`, `c`, `A (degrees)`, `B (degrees)`, `C (degrees)`; an empty answer means unknown. With no flags and stdin not a terminal, it prints usage and exits 2.

## Examples

```text
$ python3 triangle.py -a 3 -b 4 -c 5
a                   3.0000  given
b                   4.0000  given
c                   5.0000  given
A                  36.8699  derived
B                  53.1301  derived
C                  90.0000  derived
area                6.0000
perimeter          12.0000
(braille drawing follows)
```

An ambiguous side-side-angle case prints both triangles:

```text
$ python3 triangle.py -a 6 -b 8 -A 30 --no-draw
Solution 1
a                   6.0000  given
b                   8.0000  given
c                  11.4003  derived
A                  30.0000  given
B                  41.8103  derived
C                 108.1897  derived
area               22.8007
perimeter          25.4003
Solution 2
a                   6.0000  given
b                   8.0000  given
c                   2.4561  derived
A                  30.0000  given
B                 138.1897  derived
C                  11.8103  derived
area                4.9121
perimeter          16.4561
```

## Cases

SSS, SAS, ASA, AAS and SSA. SSA has 0, 1 or 2 solutions. Extra values beyond those that determine the triangle are never judged: each is reported as `extra <name> given <x> solved <y> diff <d>`.

## Exit codes

| Code | Meaning                                                  |
| ---- | -------------------------------------------------------- |
| 0    | solved                                                   |
| 1    | well-formed input but no triangle fits                   |
| 2    | unusable input (not enough values, bad value, usage)     |
