# Uniform Python CLI and Project Files Implementation Plan

spec: docs/superpowers/specs/2026-10-25-uniform-project-cli-and-python-files-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the 8 Python CLIs one non-interactive contract checked by a shared harness, type-check e and pi at pyright `standard` through a vendored gmpy2 stub, and render every per-project Python file from templates.

**Architecture:** Three PRs, in order. P1 adds `scripts/cli_contract.py` (stdlib only), converts each CLI to the contract and runs the harness from each project's `make test`. P2 adds `typings/gmpy2/__init__.pyi` and moves e and pi to `standard`. P3 extends `scripts/render_crate_files.py` with a Python project list and `@MODULE@`, and renders 5 file kinds for the 8 projects.

**Tech Stack:** Python 3.14, argparse, subprocess, `os.pipe()`, pytest, pyright 1.1.411, ruff 0.16.4, bats, GitHub Actions.

## Global Constraints

- Projects (dir: module): amicable: amicable, collatz: collatz, e: e, factorial: factorial, fib: fib, perfect-numbers: perfect_numbers, pi: pi, sq: sq.
- `SMOKE_SIZE`: amicable 5, collatz 5, e 10000, factorial 1000, fib 3, perfect-numbers 6, pi 10000, sq 1.
- `LARGE_RUN_THRESHOLD`: pi `1_000_001`, e `1_000_001`, fib `4`, the other 5 `None`.
- Output file names unchanged (N1). `SIZE` meaning and valid ranges unchanged (N2).
- No pyright suppression in any `pyrightconfig.json`; no `# type: ignore` or `# pyright: ignore` anywhere (N3).
- Template placeholders: only `@CRATE@` and `@MODULE@` (N4). No coverage floor lowered (N5). No Rust source file changes (N6).
- Pins (newest stable at least two weeks old, resolved from PyPI 2026-10-25 with cutoff 2026-10-11): `mpmath==1.4.1`, `gmpy2==2.3.2`, `coverage==7.16.2`, `cosmic-ray==8.7.0`, `hypothesis==6.168.5`, `pytest==9.1.1`, `pytest-cov==7.1.0`, `pip-audit==2.10.1`; existing `ruff==0.16.4`, `pyright==1.1.411`.
- Root `CLAUDE.md` is capped at 30,000 bytes (26,988 today); every edit to it must keep `python3 scripts/claude_md_budget.py HEAD` at exit 0.
- Read `~/.claude/standards/python.md` before any `.py`, `pyrightconfig.json`, `install_deps.sh` or `*-py.yml` change.

### CLI contract shape (every P1 CLI task implements exactly this)

```python
SMOKE_SIZE = <value>
LARGE_RUN_THRESHOLD: int | None = <value>


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="<existing description>",
        epilog="Run with no arguments at a terminal for interactive prompts.",
    )
    parser.add_argument("size", nargs="?", type=int, metavar="<existing name: N, X, DIGITS or n>",
                        help="<existing help text, meaning unchanged>")
    parser.add_argument("--show", action="store_true",
                        help="also print each result line to stdout")
    parser.add_argument("--yes", action="store_true",
                        help="confirm a large run (ignored when this program has none)")
    parser.add_argument("--smoke", action="store_true",
                        help=f"quick check at SMOKE_SIZE ({SMOKE_SIZE})")
    args = parser.parse_args(argv)
    if args.smoke:
        if args.size is not None:
            parser.error("--smoke takes no SIZE")
        args.size, args.show = SMOKE_SIZE, False
    elif args.size is None and not sys.stdin.isatty():
        parser.error("SIZE is required when stdin is not a terminal")
    return args


def refuse_large_run(size: int, yes: bool) -> None:
    """Exit 1 naming --yes when size needs confirmation and --yes is absent."""
    if LARGE_RUN_THRESHOLD is not None and size >= LARGE_RUN_THRESHOLD and not yes:
        print(f"Error: {size} is a large run; pass --yes to proceed.", file=sys.stderr)
        sys.exit(1)
```

- `main(argv: list[str] | None = None) -> None` calls `parse_args(argv)`. With a SIZE (or `--smoke`) it validates, calls `refuse_large_run` before any computation or file write, and never calls `input()`.
- With no SIZE (interactive, TTY only) the existing number prompt runs; EOF at a number prompt prints `Error: no input; pass SIZE as an argument (e.g. python3 <module>.py <SMOKE_SIZE>).` to stderr and exits 1; the large-run confirmation (pi, e, fib) stays a y/n prompt where EOF reads as no and exits 0.
- Every "Display all?" / "Also display?" prompt is deleted. The output file is always written. `--show` prints each result line exactly as written to the file, on its own line.
- Without `--show`, no stdout line equals the output file's longest line (amicable and collatz stop echoing result lines; print a count line instead).
- Each project's `test_<module>.py` gains `TestCliContractConstants` pinning `SMOKE_SIZE` and `LARGE_RUN_THRESHOLD` to the values above (R17).
- Each project's Makefile `test:` recipe gains a third line: `python3 ../scripts/cli_contract.py <module>.py`.

## Verification Planning

- Session-level proof after P1: `for p in amicable collatz e factorial fib perfect-numbers pi sq; do make -C "$p" test </dev/null || break; done` exits 0, and `python3 scripts/cli_contract.py fib/fib.py` prints `cli_contract: fib.py: all cases pass`.
- Proof the harness can fail: `python3 scripts/cli_contract.py tests/fixtures/cli_contract/silent_reader.py` exits 1 naming the stdin case, and the same against master's unconverted `fib/fib.py` (before Task 7) exits 1.
- After P2: `(cd e && pyright) && (cd pi && pyright)` print `0 errors`, and `grep -c Any typings/gmpy2/__init__.pyi` prints `0`.
- After P3: `python3 scripts/render_crate_files.py --check` exits 0; `make test` (root) exits 0; V3 is the P1 loop above run in a clean clone of master on `claude`.
- Edge cases: closed-pipe EOF versus open-pipe block (Task 1 stubs); `--smoke` with SIZE (exit 2); threshold exactly at `LARGE_RUN_THRESHOLD` and one below; no-threshold `--yes`; non-TTY bare run (exit 2).

---

## PR 1 (P1): CLI contract

Orchestrator: branch `feat/uniform-python-cli-contract` in `.worktrees/uniform-cli-p1`. Open the PR with `gh pr create --draft` after Task 10; run Phase 3; `gh pr ready` only after Phase 3 passes.

### Task 1: Contract harness and its stub-program tests

```yaml-task
id: 1
description: Add scripts/cli_contract.py running the Design 2 matrix with an os.pipe stdin, plus stub programs proving every case can fail
role: executor
model: sonnet
tdd: required
requirements: [R6, R7]
acceptance:
  - cmd: python3 -m unittest tests.test_cli_contract_harness -v
    exit_code: 0
  - cmd: 'python3 scripts/cli_contract.py tests/fixtures/cli_contract/silent_reader.py; test $? -eq 1'
    exit_code: 0
  - cmd: python3 scripts/cli_contract.py tests/fixtures/cli_contract/conforming.py
    exit_code: 0
  - cmd: make lint
    exit_code: 0
  - cmd: pyright
    exit_code: 0
max_retries: 3
files_touched:
  - scripts/cli_contract.py
  - tests/test_cli_contract_harness.py
  - tests/fixtures/cli_contract/conforming.py
  - tests/fixtures/cli_contract/conforming_no_threshold.py
  - tests/fixtures/cli_contract/prompts.py
  - tests/fixtures/cli_contract/silent_reader.py
  - tests/fixtures/cli_contract/writes_nothing.py
  - tests/fixtures/cli_contract/no_refusal.py
  - tests/fixtures/cli_contract/rejects_yes.py
depends_on: []
```

**Interfaces (Produces):** `load_constants(path: pathlib.Path) -> tuple[int, int | None]` (imports the module with `importlib.util.spec_from_file_location`, reads `SMOKE_SIZE`, `LARGE_RUN_THRESHOLD`); `run_case(path, args: list[str], stdin_text: str = "", timeout: float = 60) -> CaseResult` (dataclass: `returncode`, `stdout`, `stderr`, `files: dict[str, str]`, `timed_out`); `run_matrix(path) -> list[str]` (failure messages, empty when conforming); `main(argv) -> int` (0 pass, 1 any failure, 2 usage). Constants `CASE_TIMEOUT = 60`, `REFUSAL_TIMEOUT = 5`.

**`run_case` mechanics (load-bearing):** fresh `tempfile.TemporaryDirectory()` as `cwd`; `r, w = os.pipe()`; write `stdin_text` to `w` but do NOT close `w` until the process exits; `subprocess.Popen([sys.executable, str(path.resolve()), *args], stdin=r, stdout=PIPE, stderr=PIPE, cwd=tmp, text=True)`; `communicate(timeout=...)`; on `TimeoutExpired` kill, collect, set `timed_out=True`. `files` = every file left in `cwd`. Never `stdin=subprocess.PIPE` (closes stdin at once; measured rc 0 in 0.01 s against an `input()` stub).

**Matrix (`run_matrix`):** let `longest(files)` be the longest stripped non-empty line across output files.

1. `[SMOKE_SIZE]`: exit 0, not timed out, at least one non-empty file, no stdout line containing `?` or `(y/n)`, no stdout line equal to `longest`.
2. `[SMOKE_SIZE, --show]`: exit 0 and `longest` is a stripped stdout line.
3. `[--smoke]`: same checks as case 1.
4. `[SMOKE_SIZE]` with `stdin_text="y\n"`: same checks as case 1.
5. threshold set: `[THRESHOLD]` with timeout 5: exit 1, `--yes` in stdout+stderr, no files. Threshold `None`: `[SMOKE_SIZE, --yes]` passes case 1 checks.
6. `[]`: exit 2.

**Stubs:** each a 20-40 line stdlib program writing `out.txt`. `conforming.py` (SMOKE_SIZE 2, threshold 5), `conforming_no_threshold.py`, `prompts.py` (prints `Display all? (y/n): `), `silent_reader.py` (calls `sys.stdin.readline()` silently after its work), `writes_nothing.py`, `no_refusal.py` (ignores threshold), `rejects_yes.py` (no `--yes` argument, threshold None). Tests assert each bad stub's failure message names its case and `silent_reader` fails by timeout (use a module-level override so the test runs with timeout 2 s).

- [ ] Write failing tests in `tests/test_cli_contract_harness.py`; run; see failures.
- [ ] Implement harness and stubs; run the acceptance commands.
- [ ] Commit via `caveman:caveman-commit` (`feat(cli): add shared CLI contract harness`).

### Task 2: amicable on the contract

```yaml-task
id: 2
description: Convert amicable.py to the CLI contract shape; result lines only with --show; harness in make test; bats updated
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R4, R5, R8, R17]
acceptance:
  - cmd: python3 scripts/cli_contract.py amicable/amicable.py
    exit_code: 0
  - cmd: 'command grep -q "cli_contract.py amicable.py" amicable/Makefile'
    exit_code: 0
  - cmd: make -C amicable test
    exit_code: 0
  - cmd: make -C amicable coverage
    exit_code: 0
  - cmd: 'cd amicable && pyright'
    exit_code: 0
  - cmd: bats tests/scripts/amicable.bats
    exit_code: 0
max_retries: 3
files_touched: [amicable/amicable.py, amicable/test_amicable.py, amicable/Makefile, amicable/CLAUDE.md, tests/scripts/amicable.bats]
depends_on: [1]
parallel_group: cli
```

Apply the Global Constraints contract shape. Today `main()` prints every `a b` pair and `get_exponent` reads `args.N`; rename the attribute to `args.size`, print `Found <count> amicable pairs up to 10^<n>` and `Saved to amicable_1e<n>.txt`, and echo pairs only with `--show`. EOF at the interactive prompt keeps exit 1 with the contract message. `tests/scripts/amicable.bats` "N=3 produces exactly one pair" becomes `python3 amicable.py 3 --show` asserting a line equal to `220 284`. Update `amicable/CLAUDE.md` Code Layout and Important Behavior. TDD: each behaviour RED then GREEN (boundary: N=1, N=7, N=0, N=8; error: EOF prompt, PermissionError; state: rerun overwrites file).

- [ ] Failing tests, implement, run acceptance, commit (`feat(amicable): adopt the uniform CLI contract`).

### Task 3: collatz on the contract

```yaml-task
id: 3
description: Convert collatz.py to the CLI contract shape; records echoed only with --show; EOF at prompt exits 1
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R4, R5, R8, R17]
acceptance:
  - cmd: python3 scripts/cli_contract.py collatz/collatz.py
    exit_code: 0
  - cmd: 'command grep -q "cli_contract.py collatz.py" collatz/Makefile'
    exit_code: 0
  - cmd: make -C collatz test
    exit_code: 0
  - cmd: make -C collatz coverage
    exit_code: 0
  - cmd: 'cd collatz && pyright'
    exit_code: 0
max_retries: 3
files_touched: [collatz/collatz.py, collatz/test_collatz.py, collatz/Makefile, collatz/CLAUDE.md]
depends_on: [1]
parallel_group: cli
```

Contract shape; `args.exponent` becomes `args.size`. Today each record `num length` prints during the scan: buffer them, print `Saved <k> records to collatz_1e<n>.txt`, echo lines only with `--show`. The interactive loop catches only `ValueError`; add `EOFError` with the contract message. Keep the N > 7 memory warning. Update `collatz/CLAUDE.md`.

- [ ] Failing tests, implement, run acceptance, commit (`feat(collatz): adopt the uniform CLI contract`).

### Task 4: e on the contract

```yaml-task
id: 4
description: Convert e.py to the CLI contract; refuse 1,000,001+ digits without --yes; always write the file; mocked proceed test
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R3, R4, R5, R8, R17]
acceptance:
  - cmd: python3 scripts/cli_contract.py e/e.py
    exit_code: 0
  - cmd: 'command grep -q "cli_contract.py e.py" e/Makefile'
    exit_code: 0
  - cmd: make -C e test
    exit_code: 0
  - cmd: make -C e coverage
    exit_code: 0
  - cmd: 'cd e && pyright'
    exit_code: 0
max_retries: 3
files_touched: [e/e.py, e/test_e.py, e/Makefile, e/CLAUDE.md]
depends_on: [1]
parallel_group: cli
```

Contract shape; `args.digits` becomes `args.size`. In `get_target_digits` replace the >1,000,000 warning on the argument path with `refuse_large_run(size, args.yes)`; interactive path keeps the `Continue with N digits? (y/n)` prompt for `size >= LARGE_RUN_THRESHOLD`, EOF reads as no and returns to the prompt loop's caller with exit 0. In `main()` delete the `Would you like to display all` branch: always call the save function; with `--show` print the digit string (the same text as the file's digit line) on its own line. Keep the preview and the `MainProcess` guard. Mocked test: patch the calculation and save functions, run `main([str(LARGE_RUN_THRESHOLD), "--yes"])`, assert the calculation mock was called with `LARGE_RUN_THRESHOLD`; a second test without `--yes` asserts exit 1 and the mock not called. Keep the `# noqa: C901` on `save_*` (CLAUDE.md). Update `e/CLAUDE.md`.

- [ ] Failing tests, implement, run acceptance, commit (`feat(e): adopt the uniform CLI contract`).

### Task 5: factorial on the contract

```yaml-task
id: 5
description: Convert factorial.py to the CLI contract; --show prints the digits; EOF at prompt exits 1
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R4, R5, R8, R17]
acceptance:
  - cmd: python3 scripts/cli_contract.py factorial/factorial.py
    exit_code: 0
  - cmd: 'command grep -q "cli_contract.py factorial.py" factorial/Makefile'
    exit_code: 0
  - cmd: make -C factorial test
    exit_code: 0
  - cmd: make -C factorial coverage
    exit_code: 0
  - cmd: 'cd factorial && pyright'
    exit_code: 0
max_retries: 3
files_touched: [factorial/factorial.py, factorial/test_factorial.py, factorial/Makefile, factorial/CLAUDE.md]
depends_on: [1]
parallel_group: cli
```

Contract shape; `args.n` becomes `args.size`. `get_target_n`'s loop gains `EOFError` handling with the contract message. With `--show`, print the decimal string written by `_write_factorial_file` (have it return the text alongside the filename, or re-read the file). Keep the `MainProcess` guard. Update `factorial/CLAUDE.md`.

- [ ] Failing tests, implement, run acceptance, commit (`feat(factorial): adopt the uniform CLI contract`).

### Task 6: fib on the contract

```yaml-task
id: 6
description: Convert fib.py to the CLI contract; X>=4 refused without --yes; display prompt removed; mocked proceed test
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R3, R4, R5, R8, R17]
acceptance:
  - cmd: python3 scripts/cli_contract.py fib/fib.py
    exit_code: 0
  - cmd: 'command grep -q "cli_contract.py fib.py" fib/Makefile'
    exit_code: 0
  - cmd: make -C fib test
    exit_code: 0
  - cmd: make -C fib coverage
    exit_code: 0
  - cmd: 'cd fib && pyright'
    exit_code: 0
max_retries: 3
files_touched: [fib/fib.py, fib/test_fib.py, fib/Makefile, fib/CLAUDE.md]
depends_on: [1]
parallel_group: cli
```

Contract shape; `args.exponent` becomes `args.size`. Argument path: `refuse_large_run(x, args.yes)` before `generate_fibonacci`; interactive path keeps `ask_yes("Continue? (y/n): ")` for `x >= LARGE_RUN_THRESHOLD`. Delete the `Display all` prompt: always write `fib_1e<X>.txt` (buffered for X <= 2, streamed otherwise); `--show` prints each number line. Keep `sys.set_int_max_str_digits(0)`. Delete tests that run a real X=4 generation (they cost about 15.5 s and 239 MB); replace with the mocked test: patch `generate_fibonacci` to yield `[1, 1, 2]`, run `main(["4", "--yes"])`, assert it was called with `10**LARGE_RUN_THRESHOLD`; and `main(["4"])` exits 1 with the mock not called. Update `fib/CLAUDE.md`.

- [ ] Failing tests, implement, run acceptance, commit (`feat(fib): adopt the uniform CLI contract`).

### Task 7: perfect-numbers on the contract

```yaml-task
id: 7
description: Convert perfect_numbers.py to the CLI contract; --show prints the perfect numbers; EOF at prompt exits 1
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R4, R5, R8, R17]
acceptance:
  - cmd: python3 scripts/cli_contract.py perfect-numbers/perfect_numbers.py
    exit_code: 0
  - cmd: 'command grep -q "cli_contract.py perfect_numbers.py" perfect-numbers/Makefile'
    exit_code: 0
  - cmd: make -C perfect-numbers test
    exit_code: 0
  - cmd: make -C perfect-numbers coverage
    exit_code: 0
  - cmd: 'cd perfect-numbers && pyright'
    exit_code: 0
max_retries: 3
files_touched: [perfect-numbers/perfect_numbers.py, perfect-numbers/test_perfect_numbers.py, perfect-numbers/Makefile, perfect-numbers/CLAUDE.md]
depends_on: [1]
parallel_group: cli
```

Contract shape; `args.exponent` becomes `args.size`. The `p=...` progress lines stay (none equals a file line). `--show` prints each perfect number line after the summary. Interactive loop gains `EOFError` handling. Makefile harness line uses `perfect_numbers.py`. Update `perfect-numbers/CLAUDE.md`.

- [ ] Failing tests, implement, run acceptance, commit (`feat(perfect-numbers): adopt the uniform CLI contract`).

### Task 8: pi on the contract

```yaml-task
id: 8
description: Convert pi.py to the CLI contract; refuse 1,000,001+ digits without --yes; always write the file; mocked proceed test
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R3, R4, R5, R8, R17]
acceptance:
  - cmd: python3 scripts/cli_contract.py pi/pi.py
    exit_code: 0
  - cmd: 'command grep -q "cli_contract.py pi.py" pi/Makefile'
    exit_code: 0
  - cmd: make -C pi test
    exit_code: 0
  - cmd: make -C pi coverage
    exit_code: 0
  - cmd: 'cd pi && pyright'
    exit_code: 0
max_retries: 3
files_touched: [pi/pi.py, pi/test_pi.py, pi/Makefile, pi/CLAUDE.md]
depends_on: [1]
parallel_group: cli
```

Same changes as described for e, applied to `pi/pi.py`: `args.digits` becomes `args.size`; `get_target_digits` calls `refuse_large_run` on the argument path and keeps the `Continue with N digits? (y/n)` prompt interactively; `main()` loses the `Would you like to display all` branch, always calls `save_pi_to_file`, and with `--show` prints `_pi_to_str(pi_result, target_digits)` on its own line. Mocked test patches `calculate_pi_high_precision` and `save_pi_to_file`, runs `main([str(LARGE_RUN_THRESHOLD), "--yes"])`, asserts the calculation mock was called with `LARGE_RUN_THRESHOLD`; without `--yes`, exit 1 and not called. Keep the `# noqa: C901` and the `MainProcess` guard. Update `pi/CLAUDE.md`.

- [ ] Failing tests, implement, run acceptance, commit (`feat(pi): adopt the uniform CLI contract`).

### Task 9: sq on the contract

```yaml-task
id: 9
description: Convert sq.py to the CLI contract; delete ask_yes and the display prompt; --show prints the squares
role: executor
model: sonnet
tdd: required
requirements: [R1, R2, R4, R5, R8, R17]
acceptance:
  - cmd: python3 scripts/cli_contract.py sq/sq.py
    exit_code: 0
  - cmd: 'command grep -q "cli_contract.py sq.py" sq/Makefile'
    exit_code: 0
  - cmd: make -C sq test
    exit_code: 0
  - cmd: make -C sq coverage
    exit_code: 0
  - cmd: 'cd sq && pyright'
    exit_code: 0
max_retries: 3
files_touched: [sq/sq.py, sq/test_sq.py, sq/Makefile, sq/CLAUDE.md]
depends_on: [1]
parallel_group: cli
```

Contract shape; `args.exponent` becomes `args.size`. `ask_yes` has no remaining caller once the `Also display` prompt goes: delete it and `TestAskYes`, keeping the EOF-at-N-prompt test. `--show` prints the buffer. Update `sq/CLAUDE.md`.

- [ ] Failing tests, implement, run acceptance, commit (`feat(sq): adopt the uniform CLI contract`).

### Task 10: Shared inputs trigger every project, and pre-push runs the harness alone

```yaml-task
id: 10
description: Add scripts/cli_contract.py and typings/** to the 8 py.yml paths; pre-push runs only the harness over the 8 CLIs when the harness changes
role: executor
model: sonnet
tdd: required
requirements: [R16]
acceptance:
  - cmd: bats tests/scripts/pre_push.bats
    exit_code: 0
  - cmd: make test
    exit_code: 0
  - cmd: python3 scripts/claude_md_budget.py HEAD
    exit_code: 0
max_retries: 3
files_touched: [scripts/pre-push, tests/scripts/pre_push.bats, tests/test_python_workflow_paths.py, CLAUDE.md, .github/workflows/amicable-py.yml, .github/workflows/collatz-py.yml, .github/workflows/e-py.yml, .github/workflows/factorial-py.yml, .github/workflows/fib-py.yml, .github/workflows/perfect-numbers-py.yml, .github/workflows/pi-py.yml, .github/workflows/sq-py.yml]
depends_on: [2, 3, 4, 5, 6, 7, 8, 9]
```

Each `*-py.yml` `paths:` gains `"scripts/cli_contract.py"` and `"typings/**"`; `tests/test_python_workflow_paths.py` (yaml.safe_load) asserts both in all 8. In `scripts/pre-push`, set `RUN_CLI_CONTRACT=1` when the pushed range touches `^scripts/cli_contract\.py$`; after the root hook tests and independent of `DIRS_TO_TEST` and the `-gt 6` bail-out, run `(cd "${REPO_ROOT}/<p>" && python3 ../scripts/cli_contract.py <module>.py) </dev/null` for each of the 8, failing the push on the first failure. The bail-out block stays byte-identical. bats cases with `tests/mocks/git` diff output: harness-only push runs the 8 harness invocations and no project `make test`; a push touching 8 project dirs plus the harness still prints the skip line for suites yet runs the harness; a push not touching the harness runs none. Prove each new case fails against the unmodified hook first. Edit the root `CLAUDE.md` pre-push line to add "and `scripts/cli_contract.py` alone over the 8 Python CLIs when the push touches it"; keep the budget.

- [ ] Failing bats and pytest cases, implement, run acceptance, commit (`ci(pre-push): run the CLI harness on harness changes`).

**Orchestrator after Task 10:** run the session-level P1 loop from Verification Planning; open the draft PR; Phase 3; merge; clean up. On master, delete the Backlog row "pi.py and e.py report \"Error occurred during calculation\" when stdin is closed" (the display prompt it describes is gone).

---

## PR 2 (P2): pyright standard for e and pi

Orchestrator: branch `feat/gmpy2-stub-pyright-standard` from master after PR 1 merges.

### Task 11: Vendored gmpy2 stub and e at standard

```yaml-task
id: 11
description: Add typings/gmpy2/__init__.pyi without Any, a no-Any test, and move e to pyright standard with per-function narrowing
role: executor
model: sonnet
tdd: required
requirements: [R9]
acceptance:
  - cmd: python3 -m unittest tests.test_gmpy2_stub -v
    exit_code: 0
  - cmd: 'cd e && pyright'
    exit_code: 0
    stdout_match: '0 errors'
  - cmd: make -C e test
    exit_code: 0
  - cmd: make -C e coverage
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [typings/gmpy2/__init__.pyi, tests/test_gmpy2_stub.py, e/e.py, e/test_e.py, e/pyrightconfig.json, e/CLAUDE.md]
depends_on: [10]
```

Baseline: `standard` on master gives e 41 errors (23 attribute, 18 Optional). The stub types every name, class and method e, pi and their tests use: `mpz`, `mpfr` (arithmetic and comparison operators, `__neg__`, `digits() -> tuple[str, int, int]`), `context` with `precision`, `get_context`, `sqrt`, `version`, `mp_version`, `mpfr_version`; find the full list with `grep -ohE '_?gmpy2\.[a-z_]+' e/*.py pi/*.py | sort -u`. `tests/test_gmpy2_stub.py` asserts the stub parses (`ast.parse`) and contains no `Any` token. e: replace `_HAS_GMPY2` checks with `_gmpy2 is not None` in each function that uses it; update tests that patch `_HAS_GMPY2` to patch `_gmpy2` with `None`. `e/pyrightconfig.json`: `"typeCheckingMode": "standard"`, `"stubPath": "../typings"`, no report overrides.

- [ ] Failing test and RED pyright, implement, run acceptance, commit (`feat(e): type-check at pyright standard via gmpy2 stub`).

### Task 12: pi at standard

```yaml-task
id: 12
description: Move pi to pyright standard against the shared stub with per-function narrowing; extend the stub only where pi needs it
role: executor
model: sonnet
tdd: required
requirements: [R9]
acceptance:
  - cmd: 'cd pi && pyright'
    exit_code: 0
    stdout_match: '0 errors'
  - cmd: 'cd e && pyright'
    exit_code: 0
  - cmd: make -C pi test
    exit_code: 0
  - cmd: make -C pi coverage
    exit_code: 0
  - cmd: python3 -m unittest tests.test_gmpy2_stub -v
    exit_code: 0
max_retries: 3
files_touched: [pi/pi.py, pi/test_pi.py, pi/pyrightconfig.json, pi/CLAUDE.md, typings/gmpy2/__init__.pyi]
depends_on: [11]
```

Baseline 78 errors (46 attribute, 32 Optional). Same mechanism as Task 11 for `pi/`.

- [ ] RED pyright, implement, run acceptance, commit (`feat(pi): type-check at pyright standard via gmpy2 stub`).

### Task 13: stubPath in the other six configs, docs

```yaml-task
id: 13
description: Point the remaining 6 pyrightconfig.json files at ../typings and update the pyright-modes docs line
role: executor
model: sonnet
tdd: not-applicable
requirements: [R9]
acceptance:
  - cmd: 'for p in amicable collatz factorial fib perfect-numbers sq; do (cd "$p" && pyright) || exit 1; done'
    exit_code: 0
  - cmd: 'python3 -c "import json,sys; ps=\"amicable collatz e factorial fib perfect-numbers pi sq\".split(); sys.exit(0 if all(json.load(open(p+\"/pyrightconfig.json\")).get(\"stubPath\")==\"../typings\" for p in ps) else 1)"'
    exit_code: 0
  - cmd: python3 scripts/claude_md_budget.py HEAD
    exit_code: 0
max_retries: 2
files_touched: [amicable/pyrightconfig.json, collatz/pyrightconfig.json, factorial/pyrightconfig.json, fib/pyrightconfig.json, perfect-numbers/pyrightconfig.json, sq/pyrightconfig.json, CLAUDE.md, README.md]
depends_on: [12]
```

Config-only change (TDD not applicable: no behaviour; the acceptance loop is the check). Root `CLAUDE.md` "Modes:" line becomes "`standard` for all 8 (gmpy2 typed by `typings/gmpy2/__init__.pyi`, `stubPath: ../typings`)"; same in README if it states modes.

- [ ] Edit, run acceptance, commit (`chore(pyright): point every project at the gmpy2 stub`).

---

## PR 3 (P3): rendered Python project files

After PR 2 merges, delete the Backlog row "Pyright standard mode for pi and e" on master.

Orchestrator: branch `feat/render-python-project-files` from master after PR 2 merges.

### Task 14: Renderer learns Python projects and @MODULE@

```yaml-task
id: 14
description: Add PYTHON_PROJECTS, PYTHON_KINDS and the @MODULE@ placeholder to render_crate_files.py with unit tests
role: executor
model: sonnet
tdd: required
requirements: [R10]
acceptance:
  - cmd: python3 -m unittest tests.test_crate_uniformity -v
    exit_code: 0
  - cmd: python3 scripts/render_crate_files.py --check
    exit_code: 0
  - cmd: make lint
    exit_code: 0
  - cmd: pyright
    exit_code: 0
max_retries: 3
files_touched: [scripts/render_crate_files.py, tests/test_crate_uniformity.py]
depends_on: [13]
```

`PYTHON_PROJECTS` = the 8 dirs; `PYTHON_KINDS` maps `python/<template>` to output patterns `{project}/Makefile`, `{project}/install_deps.sh`, `.github/workflows/{project}-py.yml`, `{project}/pyrightconfig.json`, `{project}/cosmic-ray.toml` (empty dict in this task; Tasks 15-18 add entries). `render(template, project, module=None)`: `@CRATE@` to the dir name, `@MODULE@` to the dir with `-` replaced by `_`; `@MODULE@` in a Rust kind and any other `@NAME@` raise `ValueError`. `--kind` choices include the Python kinds. Tests: `perfect-numbers` renders `@MODULE@` as `perfect_numbers`; unknown placeholder errors; check/write cover a Python kind in a temp root.

- [ ] Failing tests, implement, run acceptance, commit (`feat(render): add Python projects and @MODULE@`).

### Task 15: Makefile template

```yaml-task
id: 15
description: Render the 8 Python Makefiles from one template with no benchmark target
role: executor
model: sonnet
tdd: required
requirements: [R10, R11]
acceptance:
  - cmd: python3 scripts/render_crate_files.py --check --kind python/Makefile
    exit_code: 0
  - cmd: '! command grep -l "^benchmark:" amicable/Makefile collatz/Makefile e/Makefile factorial/Makefile fib/Makefile perfect-numbers/Makefile pi/Makefile sq/Makefile'
    exit_code: 0
  - cmd: 'for p in amicable collatz e factorial fib perfect-numbers pi sq; do make -C "$p" test </dev/null || exit 1; done'
    exit_code: 0
  - cmd: bats tests/scripts/makefile.bats
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/python/Makefile, scripts/render_crate_files.py, amicable/Makefile, collatz/Makefile, e/Makefile, factorial/Makefile, fib/Makefile, perfect-numbers/Makefile, pi/Makefile, sq/Makefile, tests/scripts/makefile.bats]
depends_on: [14]
```

Template from fib's Makefile (after Task 6) with `fib` to `@MODULE@`; keep `clean:` (sq lacks it today); delete `benchmark:`. Register the kind. `makefile.bats` patterns must still match only `*/*-rs/Makefile` where they mean crates.

- [ ] Failing check, implement, run acceptance, commit (`refactor(python): render the 8 Makefiles from a template`).

### Task 16: install_deps.sh template with pinned packages

```yaml-task
id: 16
description: Render the 8 Python installers from one template installing GMP, MPFR and every pinned package; extend test_tool_pins
role: executor
model: sonnet
tdd: required
requirements: [R10, R12]
acceptance:
  - cmd: python3 scripts/render_crate_files.py --check --kind python/install_deps.sh
    exit_code: 0
  - cmd: python3 -m unittest tests.test_tool_pins -v
    exit_code: 0
  - cmd: make lint-hooks
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/python/install_deps.sh, scripts/render_crate_files.py, tests/test_tool_pins.py, amicable/install_deps.sh, collatz/install_deps.sh, e/install_deps.sh, factorial/install_deps.sh, fib/install_deps.sh, perfect-numbers/install_deps.sh, pi/install_deps.sh, sq/install_deps.sh]
depends_on: [15]
```

Template from `pi/install_deps.sh` (macOS brew and Linux apt GMP/MPFR branches), shell standard (`#!/usr/bin/env bash`, no `set -e`, functions `|| return 1`), installing `mpmath gmpy2 coverage cosmic-ray hypothesis pytest pytest-cov ruff pyright pip-audit` at the Global Constraints pins. `tests/test_tool_pins.py` gains `pip_installs()` over the 8 installers and 8 `*-py.yml`: every `pip install` argument is `name==X.Y.Z`, one version per package; prove it fails on master first.

- [ ] Failing test, implement, run acceptance, commit (`refactor(python): render the 8 installers with pinned packages`).

### Task 17: py.yml template, test metrics, no benchmark step

```yaml-task
id: 17
description: Render the 8 Python workflows from one template with pinned deps, GMP/MPFR, test metrics and no benchmark step; scripts.yml triggers
role: executor
model: sonnet
tdd: required
requirements: [R10, R11, R12, R13, R15, R16]
acceptance:
  - cmd: python3 scripts/render_crate_files.py --check --kind python/py.yml
    exit_code: 0
  - cmd: python3 -m unittest tests.test_crate_uniformity tests.test_tool_pins tests.test_workflow_continue_on_error tests.test_python_workflow_paths -v
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/python/py.yml, scripts/render_crate_files.py, tests/test_workflow_continue_on_error.py, tests/test_crate_uniformity.py, .github/workflows/scripts.yml, .github/workflows/amicable-py.yml, .github/workflows/collatz-py.yml, .github/workflows/e-py.yml, .github/workflows/factorial-py.yml, .github/workflows/fib-py.yml, .github/workflows/perfect-numbers-py.yml, .github/workflows/pi-py.yml, .github/workflows/sq-py.yml]
depends_on: [16]
```

Template from `factorial-py.yml` (it has GMP/MPFR and the `Generate test metrics` / `Upload test metrics` steps, artifact `test-metrics-@CRATE@-py`), `paths:` including `scripts/cli_contract.py` and `typings/**`, pins from Global Constraints, no `Benchmark (timeout gate)` step. Remove `TestBenchmarkGatesCanFail` and its benchmark allow-list handling from `tests/test_workflow_continue_on_error.py`; the factorial metrics `continue-on-error` allow-list entry generalises to all 8 `Generate test metrics` steps. Add the rendered workflow paths and `scripts/crate_templates/python/**` to `scripts.yml` `paths:` so `test_scripts_workflow_runs_on_every_rendered_file` passes.

- [ ] Failing tests, implement, run acceptance, commit (`refactor(python): render the 8 workflows from a template`).

### Task 18: pyrightconfig and cosmic-ray templates

```yaml-task
id: 18
description: Render the 8 pyrightconfig.json and cosmic-ray.toml files from templates; cosmic-ray timeout 60 everywhere
role: executor
model: sonnet
tdd: required
requirements: [R10, R14]
acceptance:
  - cmd: python3 scripts/render_crate_files.py --check
    exit_code: 0
  - cmd: 'for p in amicable collatz e factorial fib perfect-numbers pi sq; do (cd "$p" && pyright) || exit 1; done'
    exit_code: 0
  - cmd: 'test "$(command grep -l "^timeout = 60" */cosmic-ray.toml | wc -l)" -eq 8'
    exit_code: 0
  - cmd: make test
    exit_code: 0
max_retries: 3
files_touched: [scripts/crate_templates/python/pyrightconfig.json, scripts/crate_templates/python/cosmic-ray.toml, scripts/render_crate_files.py, amicable/pyrightconfig.json, collatz/pyrightconfig.json, e/pyrightconfig.json, factorial/pyrightconfig.json, fib/pyrightconfig.json, perfect-numbers/pyrightconfig.json, pi/pyrightconfig.json, sq/pyrightconfig.json, amicable/cosmic-ray.toml, collatz/cosmic-ray.toml, e/cosmic-ray.toml, factorial/cosmic-ray.toml, fib/cosmic-ray.toml, perfect-numbers/cosmic-ray.toml, pi/cosmic-ray.toml, sq/cosmic-ray.toml]
depends_on: [17]
```

The prose exclusion comments in fib, sq and perfect-numbers `cosmic-ray.toml` move to each project's `CLAUDE.md` only if a project-specific statement survives; the template carries none.

- [ ] Failing check, implement, run acceptance, commit (`refactor(python): render pyright and cosmic-ray configs`).

### Task 19: Docs

```yaml-task
id: 19
description: Update root CLAUDE.md and README for rendered Python files and the removed benchmark target (docs-only, no behaviour)
role: executor
model: sonnet
tdd: not-applicable
requirements: [R18]
acceptance:
  - cmd: '! command grep -n "make benchmark" CLAUDE.md README.md'
    exit_code: 0
  - cmd: python3 scripts/claude_md_budget.py HEAD
    exit_code: 0
  - cmd: 'command grep -q "crate_templates/python" CLAUDE.md'
    exit_code: 0
max_retries: 2
files_touched: [CLAUDE.md, README.md]
depends_on: [18]
```

Root `CLAUDE.md`: drop "written by `make benchmark` too"; extend the "All 11 crates are treated identically" line to name the 5 Python kinds and `@MODULE@`; the ruff-pin line becomes one version per package enforced by `tests/test_tool_pins.py`; the installer line drops "(plus GMP + MPFR, `mpmath`, `gmpy2` for pi/e/factorial)". Net size must stay under the cap.

- [ ] Edit, run acceptance, commit (`docs: document rendered Python project files`).

**Orchestrator after Task 19:** run V3 in a clean clone; draft PR; Phase 3; merge; mark plan Done.

## Non-goal check

One fresh reviewer subagent (`~/.claude/skills/writing-plans/nongoal-check.md`) read this plan against N1-N6 on 2026-10-25: 6 CLEAR, 0 CONFLICT, 0 UNCLEAR. It also read the 8 Python Makefiles and 8 `*-py.yml` workflows on `origin/master` for N5: every Makefile uses `--cov-fail-under=90` and every workflow runs `make coverage`, so the Task 15 template cannot lower a floor, and Task 18 changes only the cosmic-ray timeout. N3: `stubPath` and a no-`Any` stub are not suppressions, and Task 11 forbids report overrides. N4: Task 14 rejects any other `@NAME@`. N6: no task lists a `*-rs/` path. No resolution needed.
