# SVG output for descartes and triangle; re-prompt and end-of-input at the interactive prompts

- **Status:** Approved
- **Approved:** 2026-11-17
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
4. **Defect: 9 of 10 Rust prompts spin forever on end of input.** Measured 2026-11-17 on
   `claude`, binaries built fresh from master into a scratch target dir (the checked-in
   `target/debug` binaries are stale Mach-O builds that fail with `exec format error`; a first
   probe that ran them measured nothing). With closed stdin, `timeout 2 <bin> </dev/null`,
   collatz, e, factorial, fib, goldbach, perfect-numbers, pi, prime and sq each wrote the
   probe's 50 MB output cap within 2 s: the empty `read_line` (return 0) is treated as bad
   input, the re-prompt message is printed, and the loop reads 0 again forever. Only
   `descartes-rs` checks `is_terminal()` (`main.rs:442`) and checks for 0; it wrote 119 bytes
   and exited (positive control). Under a pty (`timeout 4 script -qec <bin> /dev/null
   </dev/null`) the same nine time out (rc 124) and `descartes-rs` exits 1. The nine Python
   twins (pi, fib, sq, e, factorial, perfect-numbers, collatz, amicable, descartes) all exit 1
   under the pty probe with `Error: no input; pass SIZE as an argument (e.g. python3
   <name>.py <SMOKE_SIZE>).` Population: the nine Rust number-prompt loops that exist;
   amicable-rs and twin-primes-rs have no prompt. Consequence: any piped, cron or CI run with
   closed stdin spins a core and writes stdout until the disk fills. PR2 is the most urgent
   of the three.

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
returning 0 at the number prompt (the prompt whose answer is parsed as the size) writes a newline to stdout, then
`Error: no input; pass SIZE as an argument (e.g. <bin> <v>).` to stderr, and exits 1 —
`descartes-rs`'s shape (`main.rs:296-300`). `<v>` is the Python twin's `SMOKE_SIZE`
(collatz 5, e 10000, factorial 1000, fib 3, perfect-numbers 6, pi 10000, sq 1); goldbach and
prime have no Python twin and use 1.

The large-run confirmation asked before the computation (`Continue with N digits? (y/n)` in
pi-rs and e-rs) is a second spin path today: a declined or empty answer returns to the
number prompt, which then spins. Measured: `printf '2000000\n' | timeout 2 pi`
wrote 5 MB in 2 s. The Python twins end the run there: `pi.py:501` and `e.py` exit 0 on
end of input, and `fib.py:106` reads it as "no" and `return`s from `main` (exit 0). So end
of input at that confirmation in pi-rs and e-rs exits 0 without computing and with nothing
on stderr after the prompt (e-rs's `Warning:` line is printed before it), matching Python
and pi's documented "EOF reading as no with exit 0". A typed "n" keeps today's behaviour
(back to the number prompt). fib-rs and prime-rs already end the run with exit 0 on a
declined or empty confirmation (`fib-rs main.rs:101-103`, `prime-rs main.rs:122-124`,
matching `fib.py:136`); they change only by tests that pin it. The prompts asked after the computation ("Display
all digits?", "Also display all … perfect squares?") already end the run on end of input
and are unchanged. Seven crates (e, factorial, fib, perfect-numbers, pi, prime, sq) read
through a shared `read_line_from` that returns a trimmed `String` and so cannot tell end
of input from a blank line; its return type changes to carry end of input (for example
`io::Result<Option<String>>`), and every caller is updated.

### PR3 — `--svg PATH`

A new option on `descartes.py`, `descartes-rs` and `triangle.py`. It writes an SVG file in
addition to whatever the terminal shows; braille stays the default terminal drawing and
`--no-draw` still suppresses only braille, so `--no-draw --svg out.svg` writes the file
and draws nothing. `--svg` combines with every other flag: packing (`K`, `--root`,
`--smoke`, `--show`, `--yes`) and `--solve`; `--precision` changes only the table, never the
SVG. Each file written prints `Saved SVG to <path>` on stdout, a prefix distinct from the
existing `Saved to <file>.txt` line. descartes prints it directly after that `.txt` line
(packing) or directly after the table (`--solve`), before `Elapsed` and before any braille
drawing; triangle prints it directly after the table of the solution it draws.

**Common format.** UTF-8, LF line endings on every platform (Python opens with
`newline="\n"`), one element per line, numbers formatted with
exactly 3 decimals and `-0.000` written `0.000`. The file is:

```
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">
<rect width="1000" height="1000" fill="white"/>
… elements …
</svg>
```

No `width` or `height`: a browser scales the view to fit the window, and zoom shows the
detail. SVG y grows downwards, so every mapping flips y: `y_svg = 500 - (y - y0) * s`.

**descartes packing.** The outer (negative-curvature) circle of the root maps to centre
(500, 500), radius 500, so `s = 500 * |k_outer|`. Circles drawn: the outer circle and every
circle from `visible(root, limit)` with `limit = min(10^K, 1000 * |k_outer|)`, so the
smallest radius drawn is 0.5 units. The cut-off depends only on the root and K, never on
the terminal. Measured for the default root: `limit = 1000` gives 3,328 circles (about
230 KB); for comparison 500 gives 1,324 and 2000 gives 8,258. 2,004 of the 3,328 have
r < 1 unit and appear only under zoom; that is intended: the file is vector so the reader
zooms into the packing rather than re-running at a larger size. The count is area-bounded
(radius ≥ R/1000), measured 3,116-3,339 circles for every root tried, so K up to 8 in Rust
does not grow it. Each circle is
`<circle cx cy r fill="none" stroke="black" stroke-width="w"/>` with
`w = min(1, r / 4)`. Every circle except the outer one with `r >= 20` also gets
`<text x y font-size="f" text-anchor="middle" dominant-baseline="central">k</text>` at its
centre, `f = min(48, 0.6 * r)` (so at least 12), `k` its integer curvature. The outer
circle is not labelled: its centre is a tangency point of two inner circles. Measured for
the default root at K=3: 26 labels (68 at `r >= 10`, of which 30 had a font under 10 units,
unreadable at 100% zoom).

**descartes `--solve`.** Drawn: the three given circles and every solution circle (a
curvature-0 solution is a line, which the table already omits; the SVG omits it too). The
square bounding box of the three given circles and every negative-curvature (enclosing)
solution, each circle taken as centre ± |r|, grown 5% on each side, maps to the 1000 × 1000
view. An enclosing solution contains the givens and is not much larger, so including it
costs little; fitting the givens alone clipped the
enclosing circle in four of five measured cases (default root: bottom at 1069). A large
positive-curvature solution (near-line, curvature close to 0) is not in the box and is
clipped by the view rather than shrinking the givens to a dot. Given circles are `stroke="black"`; solutions are
`stroke="#c00" stroke-dasharray="6 4"`; `stroke-width` as for the packing. No labels:
the values are floats and the table already prints them.

**Python–Rust parity.** For the same arguments `descartes.py` and `descartes-rs` write the
same elements in the same order with the same non-numeric text, and every number agrees
to within one unit of the last printed digit, compared as integers: each printed number is
read as an integer count of thousandths (`436.563` → 436563) and the two counts differ by at
most 1. Comparing parsed floats against `0.001` is wrong: one printed step parses to a
difference just above 0.001 for 384,932 of the 1,000,000 adjacent pairs in 0..1000
(measured), and `436.563 - 436.562` passes only because it happens to give
`0.0009999999999763531`. Byte identity is not achievable cheaply:
the two languages place the root circles with different arithmetic (`descartes.py:180-210`
Fraction and `cmath.sqrt`; `lib.rs:274,488-509` i128 and `c_sqrt`), so a centre can differ
by one ulp, and rational packings land on exact `.xxx5` ties. Measured: root
(-12, 25, 25, 28) has x = -203/19200, which maps to 436.5625; Python computes
`-0.010572916666666661` and writes `436.563`, Rust computes `-0.010572916666666663` and
writes `436.562`. Five other roots matched byte for byte.

**triangle.** The solved triangle's three vertices, scaled uniformly to fit the view with a
5% margin and y flipped, are one
`<polygon points="…" fill="none" stroke="black" stroke-width="2"/>`. Side labels `a`, `b`, `c`
sit at each side's midpoint, moved 20 units away from the centroid; angle labels `A`, `B`,
`C` sit at each vertex, moved 25 units away from the centroid; all `font-size="24"
text-anchor="middle" dominant-baseline="central"`. These are the braille labels.
An SSA input with two solutions writes two files: `-1` and `-2` inserted before the
extension of the file name, never a directory component (`t.svg` → `t-1.svg`, `t-2.svg`;
`out.d/t` → `out.d/t-1`, `out.d/t-2`). One solution writes `PATH` exactly. The
`Saved SVG to` lines name the files actually written.

**When the path is checked, and its errors.** Before any prompt, every CLI refuses a
`--svg` path whose directory part does not exist or is not a directory (an empty directory
part, as in a bare `t.svg`, means `.`), and refuses a `PATH` that is itself an existing
directory (for triangle, each suffixed name is checked too once solved). A user never
answers prompts and then loses the run to those mistakes. Permission is not pre-checked
(`os.access` is unreliable on Windows directories); a permission error surfaces at open. descartes then opens the file before `pack` or `solve` runs, as
it does the `.txt` output (R27). triangle solves first (it is instant and the file count
depends on the solution count), then opens every file before printing anything. A file that cannot be opened or written
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
- PR2: one unit test per crate passing an empty reader to the number prompt, asserting
  exit 1, the trailing newline on stdout and the exact stderr line. On current code each
  test hangs to nextest's 45 s cap, which is its RED. In pi-rs and e-rs, a test feeding a
  size above the confirmation threshold and then end of input asserts exit 0, no
  computation and nothing on stderr after the prompt; one feeding that size then `n` then
  end of input asserts the number prompt is shown twice and the run exits 1 with the R6
  message. In fib-rs and prime-rs, tests pin today's behaviour: that size then end of
  input, and that size then `n`, each exit 0 without computing. Each
  updated `read_line_from` test asserts end of input and a blank line now differ.
- PR3, Python: tests parse each SVG with `defusedxml` (already pinned) and assert exact
  element counts (default root K=3: 3,329 circles, outer plus 3,328, and 26 text elements;
  each `--solve` case: 3 givens plus its exact solution count) and one pinned element's exact
  text per kind. They also assert the `Saved SVG to` line's text and its position in stdout.
- PR3, Rust: unit tests in `descartes-rs` pin the same counts and pinned elements, so Rust
  geometry is covered under cargo-mutants, whose `.cargo/mutants.toml` runs only
  `--lib --bins --test cli` and never `tests/parity.rs`.
- PR3, parity: in the existing `descartes-rs/tests/parity.rs`, which already runs
  `../descartes.py` and which `descartes-rs.yml` and `scripts/pre-push` trigger on
  `descartes/*.py` changes. Its `stable_lines` helper (`parity.rs:37-46`) asserts exactly
  one `Saved to ` line; it keys on that prefix only, so the distinct `Saved SVG to` prefix
  leaves it valid, and a new helper reads the SVG path. Cases: K = 1, 2, 3 on the default
  root, `--root -12 25 25 28` at K = 5 (the measured tie) and one `--solve` case. Each asserts
  exit 0 on both sides and the exact circle count on each side before comparing.
- PR3, paths: one test per refusal branch in each CLI — missing directory, directory part
  that is a file, `PATH` that is an existing directory, and a bare `t.svg` accepted — each
  refusal exiting 1 with the exact message before any prompt.

## Requirements

- **R1.** `[PR1]` At the interactive prompt, `descartes.py` and `descartes-rs` answer a non-integer with `Invalid input: '<text>' is not an integer K.` on stderr and prompt again instead of exiting.
- **R2.** `[PR1]` At the interactive prompt, `descartes.py` and `descartes-rs` answer an integer outside 1..K_MAX (6 in Python, 8 in Rust) with `K must be between 1 and <K_MAX>, got <k>.` on stderr and prompt again instead of exiting.
- **R3.** `[PR1]` At the interactive prompt, `amicable.py` answers a non-integer with `Invalid input: '<text>' is not an integer N.` on stderr and prompts again, and an integer outside 1..7 with `N must be between 1 and 7, got <n>.` on stderr and prompts again.
- **R4.** `[PR1]` End of input at the descartes and amicable prompts still writes a newline to stdout and the existing `Error: no input; pass … as an argument (e.g. …).` line to stderr and exits 1, including after one or more rejected answers.
- **R5.** `[PR1]` A K or N given on the command line keeps its current exit code when out of range: 2 for descartes, 1 for amicable.
- **R6.** `[PR2]` In collatz-rs, e-rs, factorial-rs, fib-rs, goldbach-rs, perfect-numbers-rs, pi-rs, prime-rs and sq-rs, the number prompt (whose answer is parsed as the size) treats a `read_line` returning 0 as end of input: it writes a newline to stdout, writes `Error: no input; pass SIZE as an argument (e.g. <bin> <v>).` to stderr and exits 1, where `<v>` is 5 for collatz, 10000 for e, 1000 for factorial, 3 for fib, 1 for goldbach, 6 for perfect-numbers, 10000 for pi, 1 for prime and 1 for sq.
- **R7.** `[PR3]` `descartes.py`, `descartes-rs` and `triangle.py` accept `--svg PATH` alongside every other flag (`K`, `--root`, `--smoke`, `--show`, `--yes`, `--solve`, `--precision`, triangle's value flags) and write an SVG file to `PATH`; braille drawing is unchanged, `--no-draw` suppresses only braille, and `--precision` does not change the SVG.
- **R8.** `[PR3]` Every SVG file starts `<?xml version="1.0" encoding="UTF-8"?>`, then `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 1000">` (no `width` or `height` attribute), then `<rect width="1000" height="1000" fill="white"/>`, ends `</svg>` and a newline, uses LF line endings on every platform, puts one element per line, and writes every number with exactly 3 decimals, with `-0.000` written `0.000`.
- **R9.** `[PR3]` The descartes packing SVG maps the outer circle to centre (500, 500) radius 500 and draws it plus every circle with curvature at most `min(10^K, 1000 * |k_outer|)`, each as `<circle cx="…" cy="…" r="…" fill="none" stroke="black" stroke-width="…"/>` with stroke width `min(1, r / 4)`; the circle set does not depend on terminal size.
- **R10.** `[PR3]` Every packing circle other than the outer circle with SVG radius at least 20 is followed by `<text x="…" y="…" font-size="…" text-anchor="middle" dominant-baseline="central">k</text>` at its centre, with font size `min(48, 0.6 * r)` and `k` its integer curvature.
- **R11.** `[PR3]` The descartes `--solve` SVG draws the three given circles with `stroke="black"` and every non-line solution with `stroke="#c00" stroke-dasharray="6 4"`, fitted so the square bounding box of the three given circles and every negative-curvature solution, each taken as centre ± |r|, grown 5% per side, fills the 1000 × 1000 view, with no text elements.
- **R12.** `[PR3]` For the same arguments `descartes.py` and `descartes-rs` write SVG files with the same elements in the same order and the same non-numeric text, and every number, read as an integer count of thousandths (`436.563` is 436563), differs by at most 1 between the two files; `descartes-rs/tests/parity.rs` checks this for K = 1, 2, 3 on the default root, for `--root -12 25 25 28` at K = 5, and for one `--solve` case, asserting exit 0 and the exact circle count on both sides before comparing.
- **R13.** `[PR3]` The triangle SVG draws the solved triangle as one `<polygon points="…" fill="none" stroke="black" stroke-width="2"/>` scaled to fit with a 5% margin, with labels `a` `b` `c` at side midpoints moved 20 units from the centroid and `A` `B` `C` at vertices moved 25 units from the centroid, all `font-size="24" text-anchor="middle" dominant-baseline="central"`.
- **R14.** `[PR3]` When triangle has two solutions, it writes `PATH` with `-1` and `-2` inserted before the extension of the file name, never in a directory component (`t.svg` gives `t-1.svg` and `t-2.svg`; `out.d/t` gives `out.d/t-1` and `out.d/t-2`); with one solution it writes `PATH` exactly.
- **R15.** `[PR3]` Before any interactive prompt, all three CLIs refuse a `--svg` path whose directory part does not exist or is not a directory (an empty directory part means `.`) and a `PATH` that is an existing directory, and triangle also refuses a suffixed name (R14) that is an existing directory before writing; descartes opens the SVG file before `pack` or `solve` runs; triangle opens every SVG file after solving and before printing anything; a path that fails the check, or a file that cannot be opened or written, prints `Error: cannot write SVG '<path>': <reason>` to stderr and exits 1.
- **R16.** `[PR3]` Each SVG file written prints `Saved SVG to <path>` on stdout, naming the file actually written (for a two-solution triangle, both suffixed paths and not `PATH`); descartes prints it directly after the `Saved to <file>.txt` line (packing) or after the table (`--solve`), before `Elapsed` and any braille drawing, and triangle prints it directly after the table of the solution it draws.
- **R17.** `[PR1]` `docs/superpowers/specs/2026-11-15-descartes-design.md` gains an `## Amendments` line restating R27 with its prompt clause changed from "a non-integer K at the prompt names the input (`Invalid input: 'abc' is not an integer K.`, exit 2)" to "a non-integer or out-of-range K at the prompt prints its message and prompts again", with a reason naming this spec.
- **R18.** `[PR2]` In pi-rs and e-rs, end of input at the large-run confirmation asked before the computation (`Continue with N digits? (y/n)`) exits 0 without computing and with nothing written to stderr after the prompt, and a typed answer other than `y` or `yes` still returns to the number prompt; in fib-rs and prime-rs the `Continue? (y/n)` confirmation keeps exiting 0 without computing on end of input or a declined answer; the prompts asked after the computation are unchanged in all four.
- **V1.** Rebuild the nine PR2 crates and `descartes-rs` from the PR2 branch and run each two ways: `timeout 2 <bin> </dev/null | head -c 50000000 | wc -c` (closed stdin; before the fix nine print 50000000) and `timeout 4 script -qec <bin> /dev/null </dev/null` (pty; before the fix nine exit 124). After the fix all ten exit 1 under both, and the closed-stdin output is under 1 KB.
- **V2.** Open one packing SVG (K=3, default root), one `--solve` SVG and one triangle SVG in Chrome or Firefox on Linux and in Safari on macOS; each fits the window without scrolling at 100% zoom (a viewBox-only SVG must scale to the window in Safari too; if it does not, R8's no-width/height choice is revisited), the 26 curvature labels and the triangle labels are readable at 100%, the `--solve` enclosing circle is fully visible, and at 800% zoom the smallest circles are visibly tangent.
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
Disposition: Addressed (operator 2026-11-17, "Accept all") — Context item 4 rewritten with the closed-stdin measurement; V1 probes closed stdin and pty; R6 limited to the number prompt. Simpler path (Python-only SVG) declined: operator chose tolerant parity.

### Ergonomics

Finding: (1) At 1:1 scale most of the packing is invisible: of 3,328 circles, 2,004 have r < 1 unit (stroke ≤ 0.25), and `width="1000" height="1000"` overflows a laptop viewport. Drop width/height (viewBox only) or state that zoom is the intended reading. V2 is unfalsifiable without a zoom level. (2) The `--solve` fit to all circles breaks on a near-line solution (k ≈ 0.001, r ≈ 1000), which shrinks the givens to a dot. Fit to the givens instead. (3) No `Saved to <path>` line, and triangle SSA writes `t-1.svg`/`t-2.svg` but no `t.svg`, so the user cannot find the files. "Last extension" is ambiguous for `out.d/t`. (4) The flag interactions (`--svg` with `--solve`, `--smoke`, `--show`, `--precision`) are unspecified, and a bad `--svg` path is found only after the interactive prompt. (5) The byte-parity test passes on two header-only files. A root-level parity test is not triggered by `descartes/descartes.py` edits (the `scripts.yml` paths filter and the `scripts/pre-push:189` regex), and no root test builds a Rust binary. Python on Windows writes CRLF unless `newline="\n"` is set.
Assumption: same as Goal-Fit, centres bit-identical across languages.
Disposition: Addressed (operator 2026-11-17, "Accept all") — viewBox only and zoom stated (R8, V2); `--solve` fits the givens (R11); `Saved to` lines (R16); basename suffix (R14); path checked before prompts and flag interactions stated (R7, R15); LF on every platform (R8); parity moved to `descartes-rs/tests/parity.rs` with exit and count assertions (R12).

### Risk

Finding: (1) R12 is already false for a valid root. Root (-12,25,25,28) differs at line 750: Python `436.563`, Rust `436.562`. The x is -203/19200, which maps to the exact tie 436.5625. Python computes `-0.010572916666666661` (orchestrator re-ran `visible((-12,25,25,28),12000)` and got this value) and Rust `-0.010572916666666663`, because the root-placement arithmetic differs (`descartes.py:180-210` Fraction/`cmath.sqrt` vs `lib.rs:274,488-509` i128/`c_sqrt`). Five other roots matched. Ties are structural in rational packings. (2) R6 at the y/n prompts breaks pi's documented "EOF reading as no with exit 0" and would exit 1 after a finished run at "Display all digits?". It is unnecessary there, because a declined confirmation returns to the number prompt. (3) The descartes spec's R27 "exit 2 at the prompt" clause is not amended (`2026-11-15-descartes-design.md:356`). (4) Parity cases without exit-0 and count assertions pass on two empty files. Checked and clean: the circle count is area-bounded (3,116-3,339 for every root tried, no K=8 blow-up), emission order is identical, open-before-pack truncation matches the existing `.txt` behaviour, BATS covers only the command-line path, and `main.rs` is not template-rendered.
Assumption: bit-identical centres for whatever parity cases are chosen, measured false for one root and true for six.
Disposition: Addressed (operator 2026-11-17: "Tolerant parity", "Accept all") — R12 is now structural equality plus numbers within 0.001, with the tie root as a parity case; R6 limited to the number prompt; R17 amends the descartes spec's R27; parity cases assert exit 0 and a circle count.

### Adversarial Spec Review (comparison/judge designs only)

N/A — spec has no comparison/evaluator/ambiguous-criteria trigger. The parity test is a test, not a judge.

### Round 2

Reviewed at commit: `a2b68ff` (all three lenses; round-1 revision changed design substance)

**Goal-Fit.** Finding: (1) R12's "within 0.001" on parsed floats fails on one printed step for 384,932 of 1,000,000 adjacent pairs in 0..1000; the pinned tie passes by luck (`0.0009999999999763531`). Compare integer thousandths. (2) R10 labels the outer circle too (69, not V2's 68), and its "-1" lands on a tangency point. (3) "At least one circle" can never fail; nothing catches zero solutions. (4) Seven crates share `read_line_from`, which cannot signal end of input. Premise held: fresh `fib` with closed stdin wrote 50,000,000 bytes, `descartes` 119. Assumption: R12 will be implemented as an integer-thousandth comparison, not as a float abs-diff. Disposition: Addressed (operator 2026-11-17, "Accept all") — integer-thousandth rule in R12; outer circle unlabelled and threshold r ≥ 20 (26 labels) in R10; exact counts; `read_line_from` return change named in PR2.

**Ergonomics.** Finding: (1) Fitting `--solve` to the givens clips the enclosing solution in 4 of 5 measured cases (default root bottom at 1069). (2) 30 of 68 labels have font < 10 units, unreadable at 100%, so V2 cannot pass. (3) `Saved to` would print below a screen-tall braille drawing, and nothing tests it. (4) The pre-prompt check misses a `PATH` that is an existing directory and the bare-filename case, and `os.access` is unreliable on Windows. Assumption: a viewBox-only SVG scales to fit the window in Safari. Disposition: Addressed (operator 2026-11-17, "Accept all") — fit includes negative-curvature solutions (R11); label threshold r ≥ 20 (R10); `Saved SVG to` placed and tested (R16); path refusals defined per branch with tests and no permission pre-check (R15); Safari named in V2 as the check on the assumption.

**Risk.** Finding: (1) The same 0.001 float flaw (54,990 of 142,858 sampled pairs fail). (2) `parity.rs:37-46` asserts exactly one `Saved to ` line, so a second `Saved to` line breaks every SVG case. (3) `parity.rs` never runs under cargo-mutants (`.cargo/mutants.toml`), so Rust SVG geometry mutants survive V3. (4) The PR2 text was false: a declined confirmation returns to the number prompt, which spins (`printf '2000000\n' | timeout 2 pi` wrote 5 MB), while the Python twin exits 0 on end of input there. (5) `read_line_from` hides end of input in 7 crates. Clean: N3 allows the `--svg` error; `cli_contract.py` never passes `--svg`; R17 maps onto the amendment form; no partial state on an R6 exit. Assumption: cross-language drift never exceeds one printed step for the parity cases. Disposition: Addressed (operator 2026-11-17, "Accept all") — integer-thousandth rule; distinct `Saved SVG to` prefix keeps `stable_lines` valid; Rust unit tests pin SVG geometry; R18 makes end of input at the pre-computation confirmation exit 0; `read_line_from` change named. The drift assumption is checked by the parity cases themselves (a drift above one step fails them).

### Round 3 (scoped Risk)

Reviewed at commit: `762851c` (Risk lens on the round-2 changes only; operator chose scoped review)

**Risk.** Finding: (1) R18 held only for pi-rs and e-rs: fib-rs and prime-rs already exit 0 on a declined or empty confirmation (`fib-rs main.rs:101-103`, `prime-rs main.rs:122-124`; `printf '4\n' | fib` and `printf '11\n' | prime` stopped at the prompt), matching `fib.py:136`, so the "`n` returns to the number prompt" test would fail there. (2) "No stderr" fails in e-rs, fib-rs and prime-rs, whose `Warning:` precedes the prompt. (3) R11 said the enclosing solution is "bounded by" the givens (it contains them) and gave no |r| for a negative given. Clean: no other crate has a pre-computation confirmation; `parity.rs:41` matches by `starts_with`, so `Saved SVG to` does not collide; no R/N conflict; 3,329 circles and 26 labels (minimum font 13.04) reproduced. Assumption: Python and Rust centres stay within one SVG thousandth at every circle. Measured by the orchestrator over six valid roots at `limit = 1000 * |k_outer|`: maximum integer-thousandth difference 1 (`-12 25 25 28`), 0 for `-1 2 2 3`, `-11 21 24 28`, `-6 11 14 15`, `-2 3 6 7`, `-3 4 12 13`. Disposition: Addressed (operator 2026-11-17, "Apply and approve") — R18 split into pi/e fix and fib/prime pinned behaviour; "nothing on stderr after the prompt"; R11 says "contains" and uses centre ± |r|.

Review stopped after round 3: its findings were wording corrections that removed claims, and the remaining open assumption was measured.

