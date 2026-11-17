# SVG output for descartes and triangle; re-prompt and end-of-input at the interactive prompts

- **Status:** Draft
- **Date:** 2026-11-17

## Context

Three operator complaints and one defect found while checking them.

1. **The braille drawing is a poor picture of an Apollonian packing.** A braille cell holds
   2 × 4 dots, so circles below a few dots across merge, and tangency — the property being
   drawn — is invisible. `descartes` (Python and Rust) and `triangle` (Python only) draw
   only in braille today. No sub-project writes SVG.
2. **`descartes` exits on bad interactive input instead of asking again.** Measured on
   master `9f19f3c`: `descartes.py:663-670` exits 2 on a non-integer answer and exits 2 on an
   out-of-range one; `descartes-rs/src/main.rs:304,319` does the same. The descartes spec
   chose this on purpose (R27: "a non-integer K at the prompt names the input … exit 2"),
   copying `amicable.py:103-108`, which exits 1 on both.
3. **Every other prompting CLI already re-prompts.** pi, fib, sq, e, factorial,
   perfect-numbers and collatz loop in Python and in their `-rs` crates; triangle re-prompts
   with a one-line reason. amicable.py and descartes are the only two that exit.
4. **Defect: 9 of 10 Rust prompts ignore end of input.** Measured 2026-11-17 on `claude`,
   binaries built fresh from master into a scratch target dir (the checked-in
   `target/debug` binaries are stale Mach-O builds and fail with `exec format error`), each
   run under a pty with `timeout 4 script -qec <bin> /dev/null </dev/null`:
   collatz, e, factorial, fib, goldbach, perfect-numbers, pi, prime and sq all timed out
   (rc 124). Each treated the empty `read_line` (return 0) as bad input, printed its
   re-prompt message and blocked on a second read. `descartes-rs`, which checks for 0, exited
   1 under the same probe (positive control). The nine Python twins checked under the same
   probe (pi, fib, sq, e, factorial, perfect-numbers, collatz, amicable, descartes) all exit 1
   with `Error: no input; pass SIZE as an argument (e.g. python3 <name>.py <SMOKE_SIZE>).`
   Population: the probe covered the nine Rust prompt loops that exist; amicable-rs and
   twin-primes-rs have no prompt. Non-TTY stdin is refused before the prompt in every
   crate, so the defect is reachable only by Ctrl-D at a terminal: Ctrl-D cannot end the
   prompt, only Ctrl-C can. It is a parity break, not a CPU spin.

## Design

Three PRs under this spec. Each stands alone; none depends on another.

### PR1 — re-prompt at the K / N prompt (`descartes.py`, `descartes-rs`, `amicable.py`)

The interactive path loops until it has a valid value or input ends:

- A non-integer answer prints the named message to stderr and asks again:
  descartes `Invalid input: 'abc' is not an integer K.`, amicable
  `Invalid input: 'abc' is not an integer N.` (replacing amicable's bare `Invalid input.`).
- An integer outside the range prints the range message to stderr and asks again:
  descartes `K must be between 1 and <K_MAX>, got <k>.` (`K_MAX` is 6 in Python, 8 in Rust,
  per descartes R22), amicable `N must be between 1 and 7, got <n>.`
- End of input exits 1 with the existing `Error: no input; …` message, unchanged.
- A value given on the command line is untouched: descartes still exits 2 out of range,
  amicable still exits 1.

Answers are trimmed of surrounding whitespace and a trailing CR before parsing, as
`descartes-rs` already does. `int()` in Python already accepts surrounding whitespace.

### PR2 — end of input at the nine Rust prompts

In collatz, e, factorial, fib, goldbach, perfect-numbers, pi, prime and sq, a `read_line`
returning 0 at the interactive prompt writes a newline to stdout, then
`Error: no input; pass SIZE as an argument (e.g. <bin> <v>).` to stderr, and exits 1 —
`descartes-rs`'s shape (`main.rs:296-300`). `<v>` is the Python twin's `SMOKE_SIZE`
(collatz 5, e 10000, factorial 1000, fib 3, perfect-numbers 6, pi 10000, sq 1); goldbach and
prime have no Python twin and use 1. Every `read_line` call reachable from an interactive
prompt in the crate gets the check, not only the first.

### PR3 — `--svg PATH`

A new option on `descartes.py`, `descartes-rs` and `triangle.py`. It writes an SVG file in
addition to whatever the terminal shows; braille stays the default terminal drawing and
`--no-draw` still suppresses only braille, so `--no-draw --svg out.svg` writes the file
and draws nothing.

**Common format.** UTF-8, LF line endings, one element per line, numbers formatted with
exactly 3 decimals and `-0.000` written `0.000`. The file is:

```
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" width="1000" height="1000">
<rect width="1000" height="1000" fill="white"/>
… elements …
</svg>
```

SVG y grows downwards, so every mapping flips y: `y_svg = 500 - (y - y0) * s`.

**descartes packing.** The outer (negative-curvature) circle of the root maps to centre
(500, 500), radius 500, so `s = 500 * |k_outer|`. Circles drawn: the outer circle and every
circle from `visible(root, limit)` with `limit = min(10^K, 1000 * |k_outer|)`, so the
smallest radius drawn is 0.5 units. The cut-off depends only on the root and K, never on
the terminal. Measured for the default root: `limit = 1000` gives 3,328 circles (about
230 KB); for comparison 500 gives 1,324 and 2000 gives 8,258. Each circle is
`<circle cx cy r fill="none" stroke="black" stroke-width="w"/>` with
`w = min(1, r / 4)`. A circle with `r >= 10` also gets
`<text x y font-size="f" text-anchor="middle" dominant-baseline="central">k</text>` at its
centre, `f = min(48, 0.6 * r)`, `k` its integer curvature.

**descartes `--solve`.** Drawn: the three given circles and every solution circle (a
curvature-0 solution is a line, which the table already omits; the SVG omits it too). The
square bounding box of all drawn circles, grown 5% on each side, maps to the 1000 × 1000
view. Given circles are `stroke="black"`; solutions are
`stroke="#c00" stroke-dasharray="6 4"`; `stroke-width` as for the packing. No labels:
the values are floats and the table already prints them.

**Python–Rust parity.** For the same arguments `descartes.py` and `descartes-rs` write
byte-identical files. Both languages format a double to fixed decimals with correct
rounding of the binary value, so `.3f` and `{:.3}` agree; the parity test proves it rather
than trusts it.

**triangle.** The solved triangle's three vertices, scaled uniformly to fit the view with a
5% margin and y flipped, are one
`<polygon points="…" fill="none" stroke="black" stroke-width="2"/>`. Side labels `a`, `b`, `c`
sit at each side's midpoint, moved 20 units away from the centroid; angle labels `A`, `B`,
`C` sit at each vertex, moved 25 units away from the centroid; all `font-size="24"
text-anchor="middle" dominant-baseline="central"`. These are the braille labels.
An SSA input with two solutions writes two files: `-1` and `-2` inserted before the last
extension of `PATH` (`t.svg` → `t-1.svg`, `t-2.svg`; no extension → `t-1`, `t-2`). One
solution writes `PATH` exactly.

**When the file is opened, and its errors.** descartes opens the file before `pack` or
`solve` runs, as it does the `.txt` output (R27), so a long run never ends on a bad path.
triangle solves first (it is instant and the file count depends on the solution count),
then opens every file before printing anything. A file that cannot be opened or written
prints `Error: cannot write SVG '<path>': <reason>` to stderr and exits 1.

### Rejected

- **Terminal graphics protocols (sixel, kitty, iTerm2 inline images).** macOS Terminal.app
  supports none; Windows needs Windows Terminal 1.22+ for sixel.
- **PNG.** Needs an encoder (the `png` crate in Rust) and brings back a resolution limit.
- **`--svg` with an optional value and auto-naming.** `descartes --svg 3` is ambiguous
  against the positional `K`.
- **Replacing braille.** The operator chose to keep both.

## Testing

- PR1: unit tests in `test_descartes.py`, `test_amicable.py` and the `descartes-rs` test
  module feeding a scripted stdin — non-integer then valid, out-of-range then valid, whitespace
  and CRLF, bad then end of input — each asserting stderr, stdout and the exit code.
- PR2: one unit test per crate passing an empty reader to the prompt function, asserting
  exit 1, the trailing newline on stdout and the exact stderr line.
- PR3: tests parse each SVG with `defusedxml` (already pinned, `requirements-dev.txt`) and
  assert element counts (3,329 circles for K=3 on the default root: outer plus 3,328) and
  one pinned element's exact text. A root-level parity test runs both descartes CLIs with
  `--svg` for K = 1, 2, 3, one non-default root and one `--solve` case, and compares the
  files byte for byte. A bad path (a directory) exits 1 with the exact message in all three
  CLIs.

## Requirements

- **R1.** `[PR1]` At the interactive prompt, `descartes.py` and `descartes-rs` answer a non-integer with `Invalid input: '<text>' is not an integer K.` on stderr and prompt again instead of exiting.
- **R2.** `[PR1]` At the interactive prompt, `descartes.py` and `descartes-rs` answer an integer outside 1..K_MAX (6 in Python, 8 in Rust) with `K must be between 1 and <K_MAX>, got <k>.` on stderr and prompt again instead of exiting.
- **R3.** `[PR1]` At the interactive prompt, `amicable.py` answers a non-integer with `Invalid input: '<text>' is not an integer N.` on stderr and prompts again, and an integer outside 1..7 with `N must be between 1 and 7, got <n>.` on stderr and prompts again.
- **R4.** `[PR1]` End of input at the descartes and amicable prompts still writes a newline to stdout and the existing `Error: no input; pass … as an argument (e.g. …).` line to stderr and exits 1, including after one or more rejected answers.
- **R5.** `[PR1]` A K or N given on the command line keeps its current exit code when out of range: 2 for descartes, 1 for amicable.
- **R6.** `[PR2]` In collatz-rs, e-rs, factorial-rs, fib-rs, goldbach-rs, perfect-numbers-rs, pi-rs, prime-rs and sq-rs, every interactive prompt treats a `read_line` returning 0 as end of input: it writes a newline to stdout, writes `Error: no input; pass SIZE as an argument (e.g. <bin> <v>).` to stderr and exits 1, where `<v>` is 5 for collatz, 10000 for e, 1000 for factorial, 3 for fib, 1 for goldbach, 6 for perfect-numbers, 10000 for pi, 1 for prime and 1 for sq.
- **R7.** `[PR3]` `descartes.py`, `descartes-rs` and `triangle.py` accept `--svg PATH` and write an SVG file to `PATH`; braille drawing is unchanged and `--no-draw` suppresses only braille.
- **R8.** `[PR3]` Every SVG file starts `<?xml version="1.0" encoding="UTF-8"?>`, then `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000" width="1000" height="1000">`, then `<rect width="1000" height="1000" fill="white"/>`, ends `</svg>` and a newline, uses LF line endings, puts one element per line, and writes every number with exactly 3 decimals, with `-0.000` written `0.000`.
- **R9.** `[PR3]` The descartes packing SVG maps the outer circle to centre (500, 500) radius 500 and draws it plus every circle with curvature at most `min(10^K, 1000 * |k_outer|)`, each as `<circle cx="…" cy="…" r="…" fill="none" stroke="black" stroke-width="…"/>` with stroke width `min(1, r / 4)`; the circle set does not depend on terminal size.
- **R10.** `[PR3]` Every packing circle with SVG radius at least 10 is followed by `<text x="…" y="…" font-size="…" text-anchor="middle" dominant-baseline="central">k</text>` at its centre, with font size `min(48, 0.6 * r)` and `k` its integer curvature.
- **R11.** `[PR3]` The descartes `--solve` SVG draws the three given circles with `stroke="black"` and every non-line solution with `stroke="#c00" stroke-dasharray="6 4"`, fitted so the square bounding box of all drawn circles grown 5% per side fills the 1000 × 1000 view, with no text elements.
- **R12.** `[PR3]` For the same arguments `descartes.py` and `descartes-rs` write byte-identical SVG files.
- **R13.** `[PR3]` The triangle SVG draws the solved triangle as one `<polygon points="…" fill="none" stroke="black" stroke-width="2"/>` scaled to fit with a 5% margin, with labels `a` `b` `c` at side midpoints moved 20 units from the centroid and `A` `B` `C` at vertices moved 25 units from the centroid, all `font-size="24" text-anchor="middle" dominant-baseline="central"`.
- **R14.** `[PR3]` When triangle has two solutions, it writes `PATH` with `-1` and `-2` inserted before the last extension (`t.svg` gives `t-1.svg` and `t-2.svg`; `t` gives `t-1` and `t-2`); with one solution it writes `PATH` exactly.
- **R15.** `[PR3]` descartes opens the SVG file before `pack` or `solve` runs; triangle opens every SVG file after solving and before printing anything; a file that cannot be opened or written prints `Error: cannot write SVG '<path>': <reason>` to stderr and exits 1.
- **V1.** Rebuild the nine PR2 crates and `descartes-rs` from the PR2 branch and run each under `timeout 4 script -qec <bin> /dev/null </dev/null`; all ten exit 1 (before the fix nine exit 124).
- **V2.** Open one packing SVG, one `--solve` SVG and one triangle SVG in a browser on Linux and on macOS; each renders with visible tangency and readable labels.
- **V3.** Root and per-sub-project `make test` pass on each PR branch, and the per-PR mutation gates report 0 survivors on changed lines.
- **N1.** No new runtime or test dependency in any Python sub-project or Rust crate.
- **N2.** No change to braille output, to `--no-draw`'s effect on the terminal, or to any `.txt` output file's content or name.
- **N3.** No change to any exit code or message on the non-interactive (command-line value) path, except the new `--svg` error.
- **N4.** No prompt added to amicable-rs or twin-primes-rs.
- **N5.** No terminal graphics protocol (sixel, kitty, iTerm2) and no PNG output.

## Multi-Lens Review

Reviewed at commit: `fd9bd8c` (Step 7 self-review commit, before Step 8 dispatch)

### Goal-Fit

Finding: (1) Premise false: Context item 4 says non-TTY stdin is refused before the prompt, so the end-of-input defect is Ctrl-D-only. Only `descartes-rs/src/main.rs:442` checks `is_terminal()`. The orchestrator re-measured all ten fresh binaries with `timeout 2 <bin> </dev/null`: the nine PR2 crates each wrote the 50 MB output cap within 2 s, an infinite re-prompt loop, while `descartes-rs` wrote 119 bytes. The original measurement ran stale Mach-O binaries, whose rc 2 came from the exec failure. Any piped, cron or CI run with closed stdin spins and fills the disk. V1 probes only the pty path and needs a non-TTY probe. (2) R6's "every `read_line`" also covers the y/n large-run confirmations (`fib-rs:60,118`, `sq-rs:98`, `e-rs:209,269`, `pi-rs:299`, `prime-rs:143`), where end of input already means "no". Checked and held: the Context items 2-3 behaviour, the 3,328-circle count, and `.3f`/`{:.3}` formatting agreement. Simpler path offered: SVG in Python only, which drops R12.
Assumption: R12 assumes both languages compute bit-identical centres, not just format them alike. Settle it by dumping `visible()` floats from both for several roots and diffing.
Disposition:

### Ergonomics

Finding: (1) At 1:1 scale most of the packing is invisible: of 3,328 circles, 2,004 have r < 1 unit (stroke ≤ 0.25), and `width="1000" height="1000"` overflows a laptop viewport. Drop width/height (viewBox only) or state that zoom is the intended reading. V2 is unfalsifiable without a zoom level. (2) The `--solve` fit to all circles breaks on a near-line solution (k ≈ 0.001, r ≈ 1000), which shrinks the givens to a dot. Fit to the givens instead. (3) No `Saved to <path>` line, and triangle SSA writes `t-1.svg`/`t-2.svg` but no `t.svg`, so the user cannot find the files. "Last extension" is ambiguous for `out.d/t`. (4) The flag interactions (`--svg` with `--solve`, `--smoke`, `--show`, `--precision`) are unspecified, and a bad `--svg` path is found only after the interactive prompt. (5) The byte-parity test passes on two header-only files. A root-level parity test is not triggered by `descartes/descartes.py` edits (the `scripts.yml` paths filter and the `scripts/pre-push:189` regex), and no root test builds a Rust binary. Python on Windows writes CRLF unless `newline="\n"` is set.
Assumption: same as Goal-Fit, centres bit-identical across languages.
Disposition:

### Risk

Finding: (1) R12 is already false for a valid root. Root (-12,25,25,28) differs at line 750: Python `436.563`, Rust `436.562`. The x is -203/19200, which maps to the exact tie 436.5625. Python computes `-0.010572916666666661` (orchestrator re-ran `visible((-12,25,25,28),12000)` and got this value) and Rust `-0.010572916666666663`, because the root-placement arithmetic differs (`descartes.py:180-210` Fraction/`cmath.sqrt` vs `lib.rs:274,488-509` i128/`c_sqrt`). Five other roots matched. Ties are structural in rational packings. (2) R6 at the y/n prompts breaks pi's documented "EOF reading as no with exit 0" and would exit 1 after a finished run at "Display all digits?". It is unnecessary there, because a declined confirmation returns to the number prompt. (3) The descartes spec's R27 "exit 2 at the prompt" clause is not amended (`2026-11-15-descartes-design.md:356`). (4) Parity cases without exit-0 and count assertions pass on two empty files. Checked and clean: the circle count is area-bounded (3,116-3,339 for every root tried, no K=8 blow-up), emission order is identical, open-before-pack truncation matches the existing `.txt` behaviour, BATS covers only the command-line path, and `main.rs` is not template-rendered.
Assumption: bit-identical centres for whatever parity cases are chosen, measured false for one root and true for six.
Disposition:

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger. The parity test is a test, not a judge.
