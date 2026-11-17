# SVG output and prompt re-prompt / end-of-input Implementation Plan

spec: docs/superpowers/specs/2026-11-17-svg-output-and-prompt-reprompt-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-prompt on bad input at the descartes and amicable prompts (PR1), stop nine Rust prompts spinning on end of input (PR2), and add `--svg PATH` to descartes (Python and Rust) and triangle (PR3).

> **Status:** PR2 merged (math#229, 2026-11-17). Executing PR1 next, then PR3. The plan has no `scope:` line, so `spec-alignment-review` on each PR reports the other PRs' requirements as NOT-BUILT; answer each `reviewed:` naming the PR that builds it.

**Architecture:** Three independent PRs, one branch and worktree each, executed in order PR2, PR1, PR3 (PR2 is the disk-filling bug). Each PR's tasks touch disjoint files so its code tasks can run as a wave; a docs task closes each PR. SVG text is built by pure functions (`svg_packing`, `svg_solve`, triangle `svg`) that return a `str`/`String`, so tests pin exact elements without touching the filesystem; the CLI layer only checks the path, opens, writes and prints `Saved SVG to`.

**Tech Stack:** Python 3 standard library (`argparse`, `math`, `os`); tests check SVG text by string matching (no XML parser: `defusedxml` is pinned only at root scope, not in any sub-project's installer or workflow); Rust 2024 crates with `clap`, `tempfile` (dev), `cargo-nextest`; no new dependency anywhere (spec N1).

## Global Constraints

- No new runtime or test dependency in any Python sub-project or Rust crate (N1).
- No change to braille output, to `--no-draw`'s effect on the terminal, or to any `.txt` output file's content or name (N2).
- No change to any exit code or message on the non-interactive (command-line value) path, except the new `--svg` error (N3).
- No prompt added to amicable-rs or twin-primes-rs (N4). No sixel/kitty/iTerm2 and no PNG (N5).
- SVG numbers: exactly 3 decimals, `-0.000` written `0.000`; LF line endings on every platform (Python `open(..., "w", newline="\n")`).
- Stdout must never contain `?` on a non-prompt line (`scripts/cli_contract.py:317`).
- Test-name tokens, so a filtered run can prove the new tests exist (none matches an existing test on master, checked 2026-11-17): PR1 tests contain `reprompt`, PR2 tests start `prompt_eof_` (`fib-rs`/`sq-rs` already have `test_read_line_from_empty_eof`, so bare `eof` would match on base), PR3 tests contain `svg`. Filtered nextest gates set `CARGO_HOME` to `<worktree>/.cache/cargo-home`, as `scripts/rust-check.sh` does, so they reuse `make test`'s build instead of rebuilding GMP.
- Every Python task's gate includes `pyright` from the sub-project directory (CI-only in this repo, so no hook catches it) and `make -C <project> coverage` (floor 90).
- Every task whose diff touches a crate `src/` file runs `python3 -m unittest tests.test_mutants_exclusions` from the repo root: `.cargo/mutants.toml` `exclude_re` patterns embed line numbers.
- Mutation: CI `mutation-pr` requires 0 surviving mutants on changed lines (Python `mutation-py`, Rust `mutation-rs`). Every changed line needs an asserting test, glue included; `mutants-equivalent.toml` / `exclude_re` only for true equivalents, each with its mechanism.

## Verification (session level)

- **PR2 (V1):** in the PR2 worktree, build each of the nine crates plus `descartes-rs` (`cargo build --manifest-path <crate>/Cargo.toml`), then for each binary run `timeout 2 <bin> </dev/null | head -c 50000000 | wc -c` and `timeout 4 script -qec <bin> /dev/null </dev/null; echo $?`. Expected after the fix: all ten exit 1, closed-stdin output under 1024 bytes. Recorded before the fix (2026-11-17, master `9f19f3c`): nine print `50000000`, nine exit 124 under the pty. Also `printf '2000000\n' | timeout 2 <pi-bin> | wc -c` and the e equivalent: before, 5 MB+; after, under 1 KB with exit 0.
- **PR1:** `printf 'abc\n9\n3\n' | script -qec 'python3 descartes/descartes.py --no-draw' /dev/null` shows the prompt three times and ends `Saved to descartes_1e3.txt`; same for `descartes-rs` and `amicable.py` (`printf 'x\n9\n2\n'`).
- **PR3 (V2):** `descartes.py 3 --no-draw --svg /tmp/p.svg`, `descartes.py --solve -1,0,0 2,0.5,0 3,0,0.6666666666666666 --no-draw --svg /tmp/s.svg`, `triangle.py -a 3 -b 4 -c 5 --no-draw --svg /tmp/t.svg`, and an SSA two-solution run; open each in Chrome or Firefox on Linux and Safari on macOS. Expected: fits the window at 100% with no scrollbar, 26 curvature labels readable, the `--solve` enclosing circle fully visible, smallest circles visibly tangent at 800%.
- **Each PR:** root `make test` once after its last code task (orchestrator), plus every touched sub-project's `make test`; CI green including `mutation-pr`.

## Orchestrator steps (not dispatched)

- [ ] **O1.** Per PR, create a worktree from `origin/master`: `git worktree add .worktrees/<name> -b <branch> origin/master` — PR2 `fix/rust-prompt-eof`, PR1 `feat/prompt-reprompt`, PR3 `feat/svg-output`.
- [ ] **O2.** In each worktree: `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt mpmath==1.4.1 gmpy2==2.3.2 coverage==7.16.2 cosmic-ray==8.7.0 hypothesis==6.168.5 pytest==9.1.1 pytest-cov==7.1.0 ruff==0.17.4`. Dispatch every Python task with that venv active (pyenv's pyright 1.1.414 fails `test_root_pyright_scope`).
- [ ] **O3.** Pre-warm and prove the base green before dispatch, in the background: `make -C <crate> test` for every crate the PR touches (PR2: the nine; PR1 and PR3: `descartes/descartes-rs`), plus `make -C descartes test`, `make -C amicable test`, `make -C triangle test` as relevant. A cold `rug`/GMP build can take minutes; executors run gates with Bash `timeout: 600000`.
- [ ] **O4.** After each PR's last task: root `make test`, `git push -u origin <branch>`, `gh pr create --draft`, `gh pr checks <n> --watch`; Phase 3 (`finishing-a-development-branch`); `gh pr ready` only after Phase 3 passes.

---

## PR2 — end of input at the nine Rust prompts (`fix/rust-prompt-eof`)

Shared shape for Tasks 1-4 (R6). The number prompt returns `io::Result<Result<T, i32>>`: `Ok(Ok(n))` is a value, `Ok(Err(code))` means "end the run with exit `code`", already reported. On `read_line` returning 0 it writes `writeln!(out)` then `writeln!(err, "Error: no input; pass SIZE as an argument (e.g. <bin> <v>).")` and returns `Ok(Err(1))`. In `run`: `None => match prompt(...)? { Ok(n) => n, Err(code) => return Ok(code) },`. Where the crate has `read_line_from`, change it to `fn read_line_from<R: BufRead>(reader: &mut R) -> io::Result<Option<String>>` returning `None` when `read_line` returns 0, else `Some(line.trim().to_string())`; update every caller, including post-computation y/n callers, where `None` reads as "no" (unchanged behaviour). `<bin> <v>`: collatz 5, e 10000, factorial 1000, fib 3, goldbach 1, perfect-numbers 6, pi 10000, prime 1, sq 1.

Each task's tests go in the crate's `#[cfg(test)] mod tests` in `src/main.rs`, modelled on the crate's existing prompt tests, using `std::io::Cursor::new("")` / `Cursor::new("abc\n")` as the reader and `Vec<u8>` writers.

### Task 1: collatz-rs and goldbach-rs end of input

```yaml-task
id: 1
description: collatz-rs and goldbach-rs prompt_n exits 1 with the no-input message on end of input instead of looping
role: executor
model: sonnet
tdd: required
requirements: [R6]
acceptance:
  - cmd: make -C collatz/collatz-rs test
    exit_code: 0
  - cmd: make -C goldbach/goldbach-rs test
    exit_code: 0
  - cmd: bash -c "cd collatz/collatz-rs && CARGO_HOME=$(git rev-parse --show-toplevel)/.cache/cargo-home cargo nextest run --no-tests=fail prompt_eof"
    exit_code: 0
  - cmd: bash -c "cd goldbach/goldbach-rs && CARGO_HOME=$(git rev-parse --show-toplevel)/.cache/cargo-home cargo nextest run --no-tests=fail prompt_eof"
    exit_code: 0
  - cmd: python3 -m unittest tests.test_mutants_exclusions
    exit_code: 0
max_retries: 3
files_touched: [collatz/collatz-rs/src/main.rs, goldbach/goldbach-rs/src/main.rs]
depends_on: []
parallel_group: pr2
```

**Files:** `collatz/collatz-rs/src/main.rs` (`prompt_n` :19-30, `run` :36), `goldbach/goldbach-rs/src/main.rs` (`prompt_n` :19, `run` :36). `prompt_n` takes only `(reader, out)`; add `err: &mut E` so it can write the message.

- [ ] Write tests `prompt_eof_at_prompt_exits_1_with_no_input_message` (empty reader through `run` with no size: exit 1, stdout ends `"\n"` after the prompt, stderr exactly `Error: no input; pass SIZE as an argument (e.g. collatz 5).\n`; goldbach `(e.g. goldbach 1)`), `prompt_eof_after_a_rejected_answer_exits_1` (`"abc\n"` then end: one range message, then the no-input line, exit 1). Run `cargo nextest run prompt_eof`: today they hang to the 45 s cap (RED).
- [ ] Implement the shared shape; run the gates; commit (`caveman:caveman-commit`).

**Interfaces:** Produces `fn prompt_n<R: BufRead, W: Write, E: Write>(reader: &mut R, out: &mut W, err: &mut E) -> io::Result<Result<u64, i32>>` in both crates.

### Task 2: factorial-rs, perfect-numbers-rs and sq-rs end of input

```yaml-task
id: 2
description: factorial-rs, perfect-numbers-rs and sq-rs number prompts exit 1 on end of input; read_line_from returns Option
role: executor
model: sonnet
tdd: required
requirements: [R6]
acceptance:
  - cmd: make -C factorial/factorial-rs test
    exit_code: 0
  - cmd: make -C perfect-numbers/perfect-numbers-rs test
    exit_code: 0
  - cmd: make -C sq/sq-rs test
    exit_code: 0
  - cmd: bash -c "for c in factorial/factorial-rs perfect-numbers/perfect-numbers-rs sq/sq-rs; do (cd $c && CARGO_HOME=$(git rev-parse --show-toplevel)/.cache/cargo-home cargo nextest run --no-tests=fail prompt_eof) || exit 1; done"
    exit_code: 0
  - cmd: python3 -m unittest tests.test_mutants_exclusions
    exit_code: 0
max_retries: 3
files_touched: [factorial/factorial-rs/src/main.rs, perfect-numbers/perfect-numbers-rs/src/main.rs, sq/sq-rs/src/main.rs]
depends_on: []
parallel_group: pr2
```

**Files:** `factorial-rs` (`read_line_from` :22, `prompt_n_with` :28, `run` :50), `perfect-numbers-rs` (:40, :46, :65), `sq-rs` (:32, `prompt_exponent_with` :38, `run` :60, post-computation `Also display all …` read at :98 keeps "no" on `None`).

- [ ] Per crate write `prompt_eof_at_prompt_exits_1_with_no_input_message`, `prompt_eof_after_a_rejected_answer_exits_1`, and `prompt_eof_read_line_from_eof_differs_from_blank_line` (`Cursor::new("")` gives `None`, `Cursor::new("\n")` gives `Some("")`). sq also gets `prompt_eof_at_display_all_reads_as_no` (a valid size, then end of input at the post-computation prompt: exit 0, nothing echoed). Update the existing `read_line_from` tests to the `Option` type. RED: the new prompt tests hang.
- [ ] Implement the shared shape; run gates; commit.

**Interfaces:** Produces `read_line_from(...) -> io::Result<Option<String>>` and `prompt_*_with(...) -> io::Result<Result<T, i32>>` in each crate (T as today).

### Task 3: pi-rs and e-rs end of input, including the confirmation (R18)

```yaml-task
id: 3
description: pi-rs and e-rs exit 1 on end of input at the number prompt and exit 0 on end of input at the pre-computation confirmation
role: executor
model: sonnet
tdd: required
requirements: [R6, R18]
acceptance:
  - cmd: make -C pi/pi-rs test
    exit_code: 0
  - cmd: make -C e/e-rs test
    exit_code: 0
  - cmd: bash -c "for c in pi/pi-rs e/e-rs; do (cd $c && CARGO_HOME=$(git rev-parse --show-toplevel)/.cache/cargo-home cargo nextest run --no-tests=fail prompt_eof) || exit 1; done"
    exit_code: 0
  - cmd: python3 -m unittest tests.test_mutants_exclusions
    exit_code: 0
max_retries: 3
files_touched: [pi/pi-rs/src/main.rs, e/e-rs/src/main.rs]
depends_on: []
parallel_group: pr2
```

**Files:** pi-rs `read_line_from` :196, `confirm_large_digits_with` :202-217, `prompt_digits_with` :219-242, `run` :248, post-computation read :299; e-rs `read_line_from` :171, `prompt_digits_with` :179-197, `confirm_large_digits_with` :200-210 (writes `Warning:` to `err` before the prompt), post-computation read :269.

Confirmation returns a tri-state `enum Confirm { Yes, No, Eof }`. In `prompt_digits_with`: `Yes` returns the value, `No` `continue`s (today's behaviour), `Eof` returns `Ok(Err(0))` writing nothing more to `err`.

- [ ] Per crate write `prompt_eof_at_prompt_exits_1_with_no_input_message`, `prompt_eof_after_a_rejected_answer_exits_1`, `prompt_eof_read_line_from_eof_differs_from_blank_line`, `prompt_eof_at_confirmation_exits_0_without_computing` (`"2000000\n"` then end: exit 0, stdout has no `Calculating` line, stderr has nothing after the prompt — e-rs's `Warning:` line precedes it and stays), `prompt_eof_declined_confirmation_then_eof_reprompts_then_exits_1` (`"2000000\nn\n"`: number prompt shown twice, exit 1, no-input message), `prompt_eof_at_display_all_reads_as_no`. RED: the prompt tests hang.
- [ ] Implement; run gates; commit.

**Interfaces:** Produces `enum Confirm { Yes, No, Eof }` (derive `Debug, PartialEq`), `confirm_large_digits_with(...) -> io::Result<Confirm>`, `prompt_digits_with(...) -> io::Result<Result<usize, i32>>`.

### Task 4: fib-rs and prime-rs end of input; pin the confirmation

```yaml-task
id: 4
description: fib-rs and prime-rs exit 1 on end of input at the number prompt; tests pin exit 0 on end of input or decline at the confirmation
role: executor
model: sonnet
tdd: required
requirements: [R6, R18]
acceptance:
  - cmd: make -C fib/fib-rs test
    exit_code: 0
  - cmd: make -C prime/prime-rs test
    exit_code: 0
  - cmd: bash -c "for c in fib/fib-rs prime/prime-rs; do (cd $c && CARGO_HOME=$(git rev-parse --show-toplevel)/.cache/cargo-home cargo nextest run --no-tests=fail prompt_eof) || exit 1; done"
    exit_code: 0
  - cmd: python3 -m unittest tests.test_mutants_exclusions
    exit_code: 0
max_retries: 3
files_touched: [fib/fib-rs/src/main.rs, prime/prime-rs/src/main.rs]
depends_on: []
parallel_group: pr2
```

**Files:** fib-rs `read_line_from` :22, `prompt_exponent_with` :28, `confirm_large_n_with` :44-61, `run` :78 (confirmation gate :101-103), post-computation read :118; prime-rs `read_line_from` :53, `confirm_large_n_with` :59-77, `prompt_n_with` :79, `run` :99 (gate :122-124), post-computation read :143. The confirmation already ends the run with `Ok(0)` on a decline; `None` from `read_line_from` must keep reading as "no" there.

- [ ] Per crate write `prompt_eof_at_prompt_exits_1_with_no_input_message`, `prompt_eof_after_a_rejected_answer_exits_1`, `prompt_eof_read_line_from_eof_differs_from_blank_line`, `prompt_eof_at_confirmation_exits_0_without_computing` (fib `"4\n"`, prime `"11\n"`), `prompt_eof_declined_confirmation_exits_0_without_computing` (`"4\nn\n"` / `"11\nn\n"`), `prompt_eof_at_display_all_reads_as_no`. RED: the number-prompt tests hang; the confirmation tests pass on base (they pin behaviour, R18).
- [ ] Implement; run gates; commit.

**Interfaces:** Produces `read_line_from(...) -> io::Result<Option<String>>`, `prompt_*_with(...) -> io::Result<Result<u32, i32>>`.

### Task 5: PR2 docs

```yaml-task
id: 5
description: Record end-of-input behaviour in the nine crate CLAUDE.md files (docs-only, no behaviour change)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: bash -c "for c in collatz goldbach factorial perfect-numbers sq pi e fib prime; do grep -q 'no input; pass SIZE' $c/$c-rs/CLAUDE.md || { echo missing $c; exit 1; }; done"
    exit_code: 0
  - cmd: python3 scripts/claude_md_budget.py HEAD
    exit_code: 0
max_retries: 2
files_touched: [collatz/collatz-rs/CLAUDE.md, goldbach/goldbach-rs/CLAUDE.md, factorial/factorial-rs/CLAUDE.md, perfect-numbers/perfect-numbers-rs/CLAUDE.md, sq/sq-rs/CLAUDE.md, pi/pi-rs/CLAUDE.md, e/e-rs/CLAUDE.md, fib/fib-rs/CLAUDE.md, prime/prime-rs/CLAUDE.md]
depends_on: [1, 2, 3, 4]
```

- [ ] In each crate `CLAUDE.md`, under its behaviour section, add one line: end of input at the number prompt prints `Error: no input; pass SIZE as an argument (e.g. <bin> <v>).` and exits 1 (values above); for pi, e: end of input at `Continue with N digits? (y/n)` exits 0 without computing; for fib, prime: end of input or a decline at `Continue? (y/n)` exits 0. Update any existing line that says otherwise. Commit.

---

## PR1 — re-prompt at the K / N prompt (`feat/prompt-reprompt`)

### Task 6: descartes.py re-prompts

```yaml-task
id: 6
description: descartes.py get_exponent re-prompts on a non-integer or out-of-range answer and still exits 1 on end of input
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R4, R5]
acceptance:
  - cmd: make -C descartes test
    exit_code: 0
  - cmd: make -C descartes coverage
    exit_code: 0
  - cmd: bash -c "cd descartes && pyright"
    exit_code: 0
  - cmd: bash -c "cd descartes && python3 -m pytest test_descartes.py -q -k reprompt"
    exit_code: 0
  - cmd: python3 -m unittest tests.test_mutants_equivalent
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes.py, descartes/test_descartes.py, descartes/mutants-equivalent.toml]
depends_on: []
parallel_group: pr1
```

**Files:** `descartes/descartes.py` `get_exponent` :647-677; tests near `test_interactive_prompt` (:2116-2160, patch `sys.stdin.isatty` and `builtins.input` with `side_effect=[...]`).

Loop: `input(...)`; `EOFError` keeps today's exit 1 path verbatim; `int(text)` failure prints `Invalid input: {text!r} is not an integer K.` to stderr and continues; out of range prints `K must be between 1 and {K_MAX}, got {k}.` to stderr and continues. A K from `args.size` keeps the existing range check and exit 2 (R5). Replace the existing exit-2-at-prompt tests (:2152-2160) with: `test_reprompt_after_non_integer`, `test_reprompt_after_out_of_range`, `test_reprompt_then_end_of_input_exits_1` (`side_effect=["abc", EOFError]`), `test_reprompt_accepts_surrounding_whitespace`, and keep `test_k_argument_out_of_range_exits_2`-style coverage for R5. Each asserts the exact stderr lines and the prompt call count. If an edited line carries a `mutants-equivalent.toml` entry, re-confirm it in this task.

- [ ] Write tests (RED: they exit 2 today); implement; gates; commit.

### Task 7: descartes-rs re-prompts

```yaml-task
id: 7
description: descartes-rs prompts again on a non-integer or out-of-range K at the prompt
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R4, R5]
acceptance:
  - cmd: make -C descartes/descartes-rs test
    exit_code: 0
  - cmd: bash -c "cd descartes/descartes-rs && CARGO_HOME=$(git rev-parse --show-toplevel)/.cache/cargo-home cargo nextest run --no-tests=fail reprompt"
    exit_code: 0
  - cmd: python3 -m unittest tests.test_mutants_exclusions
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes-rs/src/main.rs]
depends_on: []
parallel_group: pr1
```

**Files:** `src/main.rs` `prompt_exponent` :288-306 and `exponent` :308-322; tests use `at_terminal(args, stdin)` (:~730).

Move the range check into the prompt loop for the prompt path only: `prompt_exponent` loops, writing `Invalid input: '{text}' is not an integer K.` or `K must be between 1 and {K_MAX}, got {k}.` to stderr and re-prompting; `read_line` returning 0 keeps today's exit-1 path. `exponent` keeps exit 2 for `Some(k)` out of range. Replace `prompt_non_integer_names_the_input` and `prompt_out_of_range_is_checked_too` with `reprompt_after_non_integer`, `reprompt_after_out_of_range` (stdin `"9\n3\n"`: one range line, prompt shown twice, exit 0), `reprompt_then_end_of_input_exits_1`, `reprompt_tolerates_crlf_between_answers`.

- [ ] Write tests (RED); implement; gates; commit.

### Task 8: amicable.py re-prompts

```yaml-task
id: 8
description: amicable.py re-prompts with named messages on a non-integer or out-of-range N at the prompt
role: executor
model: sonnet
tdd: required
requirements: [R3, R4, R5]
acceptance:
  - cmd: make -C amicable test
    exit_code: 0
  - cmd: make -C amicable coverage
    exit_code: 0
  - cmd: bash -c "cd amicable && pyright"
    exit_code: 0
  - cmd: bash -c "cd amicable && python3 -m pytest test_amicable.py -q -k reprompt"
    exit_code: 0
max_retries: 3
files_touched: [amicable/amicable.py, amicable/test_amicable.py]
depends_on: []
parallel_group: pr1
```

**Files:** `amicable/amicable.py` `get_exponent` :82-109; tests near `test_interactive_prompt` :179-212.

Same loop as Task 6 with `N`, range 1..7 and messages `Invalid input: {text!r} is not an integer N.` / `N must be between 1 and 7, got {n}.`. A CLI N out of range keeps exit 1 (R5). Replace the `Invalid input` exit test (:206-212) with `test_reprompt_after_non_integer`, `test_reprompt_after_out_of_range`, `test_reprompt_then_end_of_input_exits_1`.

- [ ] Write tests (RED); implement; gates; commit.

### Task 9: PR1 docs and the descartes R27 amendment

```yaml-task
id: 9
description: Amend descartes spec R27 and update descartes, descartes-rs and amicable CLAUDE.md for re-prompting (docs-only)
role: executor
model: sonnet
tdd: not-applicable
requirements: [R17]
acceptance:
  - cmd: python3 /home/bruce/.claude/scripts/spec_contract.py docs/superpowers/specs/2026-11-15-descartes-design.md
    exit_code: 0
  - cmd: bash -c "grep -q 'prompts again' docs/superpowers/specs/2026-11-15-descartes-design.md && grep -qi 'prompts again' descartes/CLAUDE.md && grep -qi 'prompts again' descartes/descartes-rs/CLAUDE.md && grep -qi 'prompts again' amicable/CLAUDE.md"
    exit_code: 0
max_retries: 2
files_touched: [docs/superpowers/specs/2026-11-15-descartes-design.md, descartes/CLAUDE.md, descartes/descartes-rs/CLAUDE.md, amicable/CLAUDE.md]
depends_on: [6, 7, 8]
```

- [ ] Append to the descartes spec's existing `## Amendments` one line `- R27 -> <the latest R27 text, verbatim, with "a non-integer K at the prompt names the input (`Invalid input: 'abc' is not an integer K.`, exit 2)" replaced by "a non-integer or out-of-range K at the prompt prints its message and prompts again"> — re-prompting adopted by docs/superpowers/specs/2026-11-17-svg-output-and-prompt-reprompt-design.md R1-R2.` Copy the latest R27 amendment (the third) as the base. Run `spec_contract.py` on it.
- [ ] In the three `CLAUDE.md` files move "non-integer at the prompt" out of the exit-2 list and state that the prompt prompts again on a non-integer or out-of-range answer. Commit.

---

## PR3 — `--svg PATH` (`feat/svg-output`)

### Task 10: descartes.py SVG builders

```yaml-task
id: 10
description: Pure functions in descartes.py that return packing and --solve SVG text per R8-R11
role: executor
model: sonnet
tdd: required
requirements: [R8, R9, R10, R11]
acceptance:
  - cmd: make -C descartes test
    exit_code: 0
  - cmd: make -C descartes coverage
    exit_code: 0
  - cmd: bash -c "cd descartes && pyright"
    exit_code: 0
  - cmd: bash -c "cd descartes && python3 -m pytest test_descartes.py -q -k svg"
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes.py, descartes/test_descartes.py]
depends_on: []
parallel_group: pr3-builders
```

Add, beside the braille renderer: `_fmt3(v: float) -> str` (`f"{v:.3f}"`, `"-0.000"` becomes `"0.000"`); `_svg_document(elements: list[str]) -> str` (R8 header lines, elements, `</svg>\n`, joined by `\n`); `_svg_circle(cx, cy, r, extra="") -> str` (`<circle cx="…" cy="…" r="…" fill="none" stroke="black" stroke-width="{_fmt3(min(1, r / 4))}"{extra}/>`); `svg_packing(root, k: int) -> str`: outer `(k0, x0, y0) = root_centres(root)[0]`, `s = 500 * abs(k0)`, `limit = min(10**k, 1000 * abs(k0))`, circles `[outer, *visible(root, limit)]`; map `x → 500 + (x - x0) * s`, `y → 500 - (y - y0) * s`, `r → s / abs(k)`; after each non-outer circle with `r >= 20` a `<text x="…" y="…" font-size="{_fmt3(min(48, 0.6 * r))}" text-anchor="middle" dominant-baseline="central">{int(k)}</text>`. `svg_solve(given, solutions) -> str`: box over the givens and every solution with `k < 0`, each `x ± 1/|k|`, `y ± 1/|k|`; `side = 1.1 * max(w, h)`, centre `(cx, cy)`, `s = 1000 / side`; givens black, solutions with ` stroke="#c00" stroke-dasharray="6 4"` (replace the stroke attribute), no text.

Tests (string matching on the returned text: `text.count("<circle ")`, `text.count("<text ")`, exact line equality; no XML parser, N1): `test_svg_packing_default_root_k3_counts` (3,329 circles, 26 texts), `test_svg_packing_first_lines_exact` (header lines and the outer circle `<circle cx="500.000" cy="500.000" r="500.000" … stroke-width="1.000"/>`), `test_svg_packing_k1_limit_is_10_pow_k`, `test_svg_negative_zero_printed_unsigned`, `test_svg_solve_counts_and_styles` (3 black, 2 dashed for the CLAUDE.md example), `test_svg_solve_enclosing_solution_inside_view` (default-root givens 2,2,3: every circle within 0..1000).

- [ ] Write tests (RED); implement; gates; commit.

**Interfaces:** Produces `svg_packing(root: tuple[int, int, int, int], k: int) -> str`, `svg_solve(given: list[Circle], solutions: list[Circle]) -> str`, `_fmt3(v: float) -> str`.

### Task 11: descartes-rs SVG builders

```yaml-task
id: 11
description: Rust lib functions svg_packing and svg_solve producing the same SVG as Task 10, with unit tests pinning geometry
role: executor
model: sonnet
tdd: required
requirements: [R8, R9, R10, R11]
acceptance:
  - cmd: make -C descartes/descartes-rs test
    exit_code: 0
  - cmd: bash -c "cd descartes/descartes-rs && CARGO_HOME=$(git rev-parse --show-toplevel)/.cache/cargo-home cargo nextest run --no-tests=fail svg"
    exit_code: 0
  - cmd: python3 -m unittest tests.test_mutants_exclusions
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes-rs/src/lib.rs]
depends_on: []
parallel_group: pr3-builders
```

Add to `src/lib.rs`: `fn fmt3(v: f64) -> String` (`format!("{v:.3}")`, `"-0.000"` becomes `"0.000"`), `pub fn svg_packing(root: [i64; 4], k: u32) -> Result<String, DescartesError>`, `pub fn svg_solve(given: &[Circle], solutions: &[Circle]) -> String`, with the exact element text, order and formulas of Task 10 (outer from `root_centres(root)?[0]`, circles from `visible(root, limit)?`, `limit = min(10^k, 1000 * |k0|)` as `i64`; label text is the curvature as an integer). Unit tests in `mod tests` with the same names and assertions as Task 10 (count by `matches("<circle ")`; pin the outer circle line and the first labelled circle's two lines exactly), because `tests/parity.rs` never runs under cargo-mutants. Every pub item stays `Debug`-clean and clippy `-D warnings` clean.

- [ ] Write tests (RED); implement; gates; commit.

**Interfaces:** Produces `descartes::svg_packing(root: [i64; 4], k: u32) -> Result<String, DescartesError>`, `descartes::svg_solve(given: &[Circle], solutions: &[Circle]) -> String`.

### Task 12: triangle.py SVG builder

```yaml-task
id: 12
description: Pure function in triangle.py returning the triangle SVG per R8 and R13
role: executor
model: sonnet
tdd: required
requirements: [R8, R13]
acceptance:
  - cmd: make -C triangle test
    exit_code: 0
  - cmd: make -C triangle coverage
    exit_code: 0
  - cmd: bash -c "cd triangle && pyright"
    exit_code: 0
  - cmd: bash -c "cd triangle && python3 -m pytest test_triangle.py -q -k svg"
    exit_code: 0
max_retries: 3
files_touched: [triangle/triangle.py, triangle/test_triangle.py]
depends_on: []
parallel_group: pr3-builders
```

Add `svg(t: Triangle) -> str`. Vertices as `_project` (:471-490) uses: `A=(0,0)`, `B=(t.c,0)`, `C=(t.b*cos(t.A), t.b*sin(t.A))` (radians internally). `scale = 900 / max(x_span, y_span)`, centre the bounding box on (500, 500), y flipped. One `<polygon points="x,y x,y x,y" fill="none" stroke="black" stroke-width="2"/>` (each number via a local `_fmt3`, same rule as descartes), then texts: `a` at the midpoint of B–C, `b` of C–A, `c` of A–B, each moved 20 units from the centroid along centroid→midpoint; `A`, `B`, `C` at the vertices moved 25 units; all `font-size="24" text-anchor="middle" dominant-baseline="central"`. Document via the R8 header/footer (copy the four-line shape; triangle and descartes are separate modules).

Tests: `test_svg_3_4_5_exact` (pin the full document text for `-a 3 -b 4 -c 5`), `test_svg_has_one_polygon_six_labels`, `test_svg_obtuse_fits_view` (a=b=1, C=179°: every coordinate within 0..1000).

- [ ] Write tests (RED); implement; gates; commit.

**Interfaces:** Produces `svg(t: Triangle) -> str`.

### Task 13: descartes.py `--svg` CLI

```yaml-task
id: 13
description: descartes.py --svg flag with pre-prompt path refusal, open-before-compute, write, and the Saved SVG to line
role: executor
model: sonnet
tdd: required
requirements: [R7, R15, R16]
acceptance:
  - cmd: make -C descartes test
    exit_code: 0
  - cmd: make -C descartes coverage
    exit_code: 0
  - cmd: bash -c "cd descartes && pyright"
    exit_code: 0
  - cmd: bash -c "cd descartes && python3 -m pytest test_descartes.py -q -k svg_cli"
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes.py, descartes/test_descartes.py]
depends_on: [10]
parallel_group: pr3-cli
```

`parse_args` (:549): `--svg PATH` (`metavar="PATH"`, help `also write the drawing as SVG to PATH`); allowed with every mode. New `_check_svg_path(path: str) -> None`: `parent = os.path.dirname(path) or "."`; refuse when `not os.path.isdir(parent)` or `os.path.isdir(path)`, via `_fail(f"cannot write SVG '{path}': <reason>", 1)` so stderr reads `Error: cannot write SVG '<path>': <reason>`. Call it in `main` before `get_exponent` (before any prompt). `_run_packing` (:711): open the SVG (`open(path, "w", newline="\n")`) beside the `.txt` open, before `pack`; after the `.txt` is written, write `svg_packing(root, k)`; print `Saved SVG to {path}` right after `Saved to {filename}`. `_run_solve` (:774): open before `solve`, write `svg_solve(given, solutions)` after it, print the line after the table, before braille. `OSError` exits 1 with the same message form.

Tests: `test_svg_cli_packing_writes_file_and_line_order`, `test_svg_cli_solve_writes_file`, `test_svg_cli_refuses_missing_dir_before_prompt` (patch `input` and assert it was never called), `test_svg_cli_refuses_existing_directory`, `test_svg_cli_refuses_file_as_dir_part`, `test_svg_cli_bare_name_accepted`, `test_svg_cli_no_draw_still_writes`, `test_svg_cli_precision_does_not_change_svg`.

- [ ] Write tests (RED); implement; gates; commit.

### Task 14: descartes-rs `--svg` CLI

```yaml-task
id: 14
description: descartes-rs --svg flag mirroring Task 13 (refusal before prompt, open before compute, Saved SVG to line)
role: executor
model: sonnet
tdd: required
requirements: [R7, R15, R16]
acceptance:
  - cmd: make -C descartes/descartes-rs test
    exit_code: 0
  - cmd: bash -c "cd descartes/descartes-rs && CARGO_HOME=$(git rev-parse --show-toplevel)/.cache/cargo-home cargo nextest run --no-tests=fail svg_cli"
    exit_code: 0
  - cmd: python3 -m unittest tests.test_mutants_exclusions
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes-rs/src/main.rs, descartes/descartes-rs/tests/cli.rs]
depends_on: [11]
parallel_group: pr3-cli
```

Add `#[arg(long, value_name = "PATH")] svg: Option<PathBuf>` to `Args`; `fn check_svg_path(path: &Path) -> Result<(), String>` with the Task 13 rules (empty parent means `.`); call it in `run` before `exponent`; `run_packing` / `run_solve` open with `File::create` before computing, write `svg_packing` / `svg_solve`, print `Saved SVG to {path}` in the Task 13 positions; failures `fail(stderr, format!("cannot write SVG '{}': {e}", path.display()), 1)`. Unit tests in `main.rs` with the Task 13 names (`svg_cli_…`); one binary test in `tests/cli.rs`, `svg_cli_binary_writes_svg_in_cwd`.

- [ ] Write tests (RED); implement; gates; commit.

### Task 15: triangle.py `--svg` CLI

```yaml-task
id: 15
description: triangle.py --svg with suffixed names for two solutions, pre-prompt refusal and Saved SVG to lines
role: executor
model: sonnet
tdd: required
requirements: [R7, R14, R15, R16]
acceptance:
  - cmd: make -C triangle test
    exit_code: 0
  - cmd: make -C triangle coverage
    exit_code: 0
  - cmd: bash -c "cd triangle && pyright"
    exit_code: 0
  - cmd: bash -c "cd triangle && python3 -m pytest test_triangle.py -q -k svg_cli"
    exit_code: 0
max_retries: 3
files_touched: [triangle/triangle.py, triangle/test_triangle.py]
depends_on: [12]
parallel_group: pr3-cli
```

`_build_parser` (:573): `--svg PATH`. In `main` (:665) check the path (same rules as Task 13, exit 1 with `Error: cannot write SVG '<path>': <reason>`) before `_prompt_values`. After `solve`, compute names: one solution `[path]`; two, `_suffixed(path, i)` inserting `-1`/`-2` before the extension of the basename only (`os.path.splitext(os.path.basename(...))`, rejoined to the dirname; `out.d/t` gives `out.d/t-1`); refuse any name that is an existing directory; open all before printing anything; in `_report` print `Saved SVG to {name}` right after each solution's table.

Tests (use the `_run` helper :917): `test_svg_cli_one_solution_exact_path`, `test_svg_cli_ssa_two_files_suffixed`, `test_svg_cli_suffix_skips_directory_dots`, `test_svg_cli_refuses_missing_dir_before_prompt`, `test_svg_cli_refuses_existing_directory`, `test_svg_cli_saved_line_after_each_table`.

- [ ] Write tests (RED); implement; gates; commit.

### Task 16: SVG parity in parity.rs

```yaml-task
id: 16
description: descartes-rs/tests/parity.rs compares Python and Rust SVG by structure and integer thousandths (R12)
role: executor
model: sonnet
tdd: required
requirements: [R12]
acceptance:
  - cmd: make -C descartes/descartes-rs test
    exit_code: 0
  - cmd: bash -c "cd descartes/descartes-rs && CARGO_HOME=$(git rev-parse --show-toplevel)/.cache/cargo-home cargo nextest run --no-tests=fail --test parity svg"
    exit_code: 0
max_retries: 3
files_touched: [descartes/descartes-rs/tests/parity.rs]
depends_on: [13, 14]
```

Add `fn svg_tokens(svg: &str) -> Vec<Token>` splitting the text into numeric and non-numeric runs (a number is `-?\d+\.\d{3}`; parse it as an integer count of thousandths, e.g. `436.563` → 436563, without going through `f64`), and `fn assert_svg_parity(args: &[&str], circles: usize)`: run both CLIs in temp dirs with `--svg out.svg --no-draw`, assert exit 0 on both, assert `matches("<circle ").count() == circles` on both, then assert equal token counts, equal non-numeric tokens, and `|py - rs| <= 1` per numeric token, naming the first differing line on failure. Cases (circle counts measured 2026-11-17 from `visible` plus the outer circle): `svg_parity_default_root_k1` (9), `svg_parity_default_root_k2` (169), `svg_parity_default_root_k3` (3,329), `svg_parity_tie_root_k5` (`--root -12 25 25 28 5`, 3,327), `svg_parity_solve` (the CLAUDE.md example: 3 givens + 2 solutions = 5). `stable_lines` keys on `starts_with("Saved to ")`, so the `Saved SVG to` line does not collide; leave it as is.

- [ ] Write tests (RED until Tasks 13-14 merge into the worktree; they do, by `depends_on`); confirm the tie case reports a 1-thousandth difference that passes; gates; commit.

### Task 17: PR3 docs

```yaml-task
id: 17
description: Document --svg in descartes, descartes-rs and triangle CLAUDE.md and README files and the root README (docs-only)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: bash -c "for f in descartes/CLAUDE.md descartes/README.md descartes/descartes-rs/CLAUDE.md descartes/descartes-rs/README.md triangle/CLAUDE.md triangle/README.md README.md; do grep -q -- '--svg' $f || { echo missing $f; exit 1; }; done"
    exit_code: 0
  - cmd: python3 scripts/claude_md_budget.py HEAD
    exit_code: 0
max_retries: 2
files_touched: [descartes/CLAUDE.md, descartes/README.md, descartes/descartes-rs/CLAUDE.md, descartes/descartes-rs/README.md, triangle/CLAUDE.md, triangle/README.md, README.md]
depends_on: [13, 14, 15, 16]
```

- [ ] Add `--svg PATH` to each flag list, a real example output block (`Saved SVG to p.svg` after `Saved to …`), the refusal rules and exit 1, the two-solution suffix rule (triangle), the label rule (r ≥ 20, outer unlabelled) and the parity rule (integer thousandths, ±1) in descartes-rs CLAUDE.md. Root `README.md`: mention SVG in the descartes and triangle rows. Commit.

## Non-goal check

Reviewer: one fresh subagent with `~/.claude/skills/writing-plans/nongoal-check.md`, 2026-11-17. N2, N3, N4, N5: CLEAR.

- **N1 — UNCLEAR.** Quote: "Tech Stack: `defusedxml` in tests only (already pinned) ... Task 10 Tests (`defusedxml.ElementTree.fromstring`)". Checked: `grep -n defusedxml descartes/install_deps.sh .github/workflows/descartes-py.yml .github/workflows/triangle-py.yml triangle/install_deps.sh` returned nothing, so the import would be a new test dependency of the sub-project (and fail CI with `ModuleNotFoundError`). Resolution: plan revised. Before: "`defusedxml` in tests only (already pinned)" and "Tests (`defusedxml.ElementTree.fromstring`):". After: tests check SVG text by string matching (`text.count("<circle ")`, exact line equality), no XML parser. The spec's Testing prose mentions `defusedxml`; it is not a requirement, and N1 governs.

