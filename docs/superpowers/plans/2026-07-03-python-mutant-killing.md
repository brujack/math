> **Status: DONE** — PR #84 merged 2026-07-03 (sq, fib, perfect-numbers; partial completion)

# Python Mutant Killing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kill all surviving cosmic-ray mutants in the 8 Python sub-projects by writing targeted tests for real behavioral gaps and documenting genuine equivalent mutations in `cosmic-ray.toml`.

**Architecture:** Each task runs cosmic-ray discovery on one module, reads the surviving-mutant report, classifies each mutant (real gap vs. equivalent mutation), then fixes with new `unittest.TestCase` tests or documents the equivalence. Tasks 1–6 (fast modules) dispatch in parallel wave 1. Tasks 7–8 (pi, e — 60 s/mutation) run sequentially after the wave.

**Tech Stack:** cosmic-ray 8.4.6, Python 3.14, pytest (Makefile test runner), `python3 -m unittest` (cosmic-ray test runner), hypothesis

## Global Constraints

- Branch: `test/kill-python-mutants` — create worktree at `.worktrees/kill-python-mutants` before dispatching
- All new test methods MUST be in an existing `unittest.TestCase` subclass — compatible with both `make test` (pytest) and cosmic-ray's `python3 -m unittest test_<module>`
- `cosmic-ray-session.sqlite` and `mutants-report.txt` are `.gitignored` — never commit them
- `make test` must pass BEFORE making any changes in a module directory
- Commit one commit per module using `caveman:caveman-commit` skill after all fixes for that module are green
- `pi` and `e` require gmpy2 — verify `python3 -c "import gmpy2"` succeeds before running those tasks
- All commands run from the repo root unless stated otherwise

## Verification

Complete when:

1. `make test` exits 0 in all 8 module directories
2. `make mutants` re-run in each module shows 0 surviving mutants (or all remaining survivors are documented as equivalents in `cosmic-ray.toml` comments)
3. PR CI green

## Triage Decision Tree (apply in every task)

Read each `SURVIVED` entry in `mutants-report.txt`. The entry shows: operator name, file+line, diff, and test output. Apply this decision:

**Real gap** — the mutation changes observable behavior that tests should detect:

- Wrong output value (list content, printed line, file content)
- Wrong comparison direction (includes/excludes a boundary value)
- Wrong arithmetic result (changed formula)
- Wrong control-flow branch taken
  → **Fix:** write a test that passes on real code and would fail on the mutant.

**Equivalent mutation** — code changes but all valid inputs produce identical output:

- Mathematical identity (e.g., `while b < 10^N` — no Fibonacci number equals exactly `10^N`, so `<` vs `<=` yields same sequence)
- Dead branch unreachable by domain values (e.g., negative Mersenne result in `lucas_lehmer`)
- Loop-bound over-estimate caught by a break/yield condition
  → **Fix:** confirm equivalence by tracing 2–3 boundary inputs by hand. Add a comment block to `cosmic-ray.toml`:

```toml
# Equivalent mutations — no observable difference for any valid input:
# Operator: <OperatorName> at line N: <diff summary>
# Reason: <mathematical invariant>
```

---

### Task 1: sq — discover and fix surviving mutants

```yaml-task
id: 1
description: Run cosmic-ray on sq.py, classify survivors, kill real gaps with tests
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C sq test
    exit_code: 0
max_retries: 3
files_touched:
  - sq/test_sq.py
  - sq/cosmic-ray.toml
depends_on: []
parallel_group: fast
```

**Directory:** `sq/`

**Key source:** `generate_squares(max_digits)` — yields `(k*k, k)` while `k*k < 10^max_digits`.

```python
def generate_squares(max_digits: int):
    limit = 10 ** max_digits
    k = 1
    while k * k < limit:
        yield k * k, k
        k += 1
```

CLI: `get_exponent` validates `1 ≤ N ≤ 10`, `main` writes to `sq_1eN.txt`.
Test classes: `TestGenerateSquares`, `TestParseArgs`, `TestGetExponent`, `TestGetExponentInteractive`, `TestMain`, `TestSquareProperties`.

**Steps:**

- [ ] `cd sq && make test` — baseline must pass before changes
- [ ] `cd sq && make mutants` — discovery; takes 10–30 minutes; produces `mutants-report.txt`
- [ ] Read `sq/mutants-report.txt`; list every `SURVIVED` entry with its operator and diff
- [ ] Apply the Triage Decision Tree (see Global Constraints) to each survivor
- [ ] For each **real gap**, add a test to the appropriate class in `sq/test_sq.py`:
  - Arithmetic mutation on `k*k` (e.g., `k*k → k+k`): assert exact square values
    ```python
    def test_squares_are_products_not_sums(self):
        result = list(generate_squares(1))
        self.assertIn((9, 3), result)    # 3*3=9
        self.assertNotIn((6, 3), result) # 3+3=6 would appear if mutated
    ```
  - Comparison mutation `<` → `<=` at `k*k < limit`: confirm the last yielded square is strictly below `10^N`
    ```python
    def test_max_square_below_limit(self):
        for n in [1, 2, 3]:
            limit = 10 ** n
            pairs = list(generate_squares(n))
            self.assertTrue(all(sq < limit for sq, _ in pairs))
    ```
  - Increment mutation on `k += 1` (e.g., `k += 2`): check no squares are skipped
    ```python
    def test_no_squares_skipped_max_digits_1(self):
        # Should be (1,1),(4,2),(9,3) — none skipped
        self.assertEqual(list(generate_squares(1)), [(1, 1), (4, 2), (9, 3)])
    ```
  - Run `cd sq && python3 -m pytest test_sq.py -v -k test_name` after writing each test — must be RED (test fails before mutant-equivalent code is the default). If GREEN, the test does not kill the mutant as written — revise.
  - The mutant is a hypothetical change to `sq.py`; `sq.py` itself does NOT change — the test kills the mutant by detecting behavior the mutation would break.
- [ ] For each **equivalent mutation**, add a comment block to `sq/cosmic-ray.toml` per the template in the Triage Decision Tree
- [ ] `cd sq && make test` — all tests must pass
- [ ] `cd sq && make mutants` — re-run; verify surviving count dropped; any remaining survivors must have corresponding `cosmic-ray.toml` comments
- [ ] Invoke `caveman:caveman-commit` skill to generate the commit message
- [ ] `git add sq/test_sq.py sq/cosmic-ray.toml && git commit -m "$(...)"`

**Interfaces:**

- Consumes: nothing from other tasks
- Produces: committed test additions in `sq/test_sq.py`; equivalent-mutation comments in `sq/cosmic-ray.toml`

---

### Task 2: fib — discover and fix surviving mutants

```yaml-task
id: 2
description: Run cosmic-ray on fib.py, classify survivors, kill real gaps with tests
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C fib test
    exit_code: 0
max_retries: 3
files_touched:
  - fib/test_fib.py
  - fib/cosmic-ray.toml
depends_on: []
parallel_group: fast
```

**Directory:** `fib/`

**Key source:** `generate_fibonacci(max_digits)` — yields Fibonacci numbers while `b < 10^max_digits`.

```python
def generate_fibonacci(max_digits: int):
    limit = 10 ** max_digits
    a, b = 1, 1
    while b < limit:
        yield a
        a, b = b, a + b
```

CLI: `get_exponent` validates `1 ≤ N ≤ 10`, `main` buffers (N≤2) or streams (N>2) to `fib_1eN.txt`.
Test classes: `TestGenerateFibonacci`, `TestParseArgs`, `TestGetExponent`, `TestGetExponentInteractive`, `TestMain`, `TestFibProperties`.

**Steps:**

- [ ] `cd fib && make test` — baseline must pass
- [ ] `cd fib && make mutants` — discovery; produces `fib/mutants-report.txt`
- [ ] Read `fib/mutants-report.txt`; list every SURVIVED entry
- [ ] Apply the Triage Decision Tree to each survivor
- [ ] Known likely equivalents (confirm by hand before documenting):
  - `while b < limit` → `while b <= limit`: no Fibonacci number equals exactly `10^N` for any valid N (the sequence grows exponentially and these powers of ten are never Fibonacci numbers), so `<` and `<=` yield the same sequence. This IS equivalent — document it.
- [ ] Known likely real gaps:
  - `a, b = b, a + b` → `a, b = b, a - b`: would produce 1,1,0,1,-1,2,... instead of Fibonacci. Assert first few values:
    ```python
    def test_first_five_fibonacci(self):
        result = list(generate_fibonacci(2))
        self.assertEqual(result[:5], [1, 1, 2, 3, 5])
    ```
  - `yield a` → `yield b`: would yield shifted sequence. Assert yield value matches first element:
    ```python
    def test_first_yielded_is_1_not_1(self):  # 1 is the first Fibonacci
        result = list(generate_fibonacci(1))
        self.assertEqual(result[0], 1)
    ```
  - Arithmetic on `limit`: mutation `10 ** max_digits` → `10 * max_digits` gives wrong limit. Assert count for known N:
    ```python
    def test_count_max_digits_1(self):
        # 1,1,2,3,5,8 (6 values below 10); 13 >= 10
        self.assertEqual(len(list(generate_fibonacci(1))), 6)
    ```
- [ ] Write tests for real gaps; confirm RED before implementation check; confirm GREEN on real code
- [ ] Document equivalent mutations in `fib/cosmic-ray.toml`
- [ ] `cd fib && make test` — must pass
- [ ] `cd fib && make mutants` — re-run; verify survivors dropped
- [ ] Invoke `caveman:caveman-commit`; `git add fib/test_fib.py fib/cosmic-ray.toml && git commit -m "$(...)"`

**Interfaces:**

- Consumes: nothing
- Produces: committed test additions in `fib/test_fib.py`; equivalents in `fib/cosmic-ray.toml`

---

### Task 3: factorial — discover and fix surviving mutants

```yaml-task
id: 3
description: Run cosmic-ray on factorial.py, classify survivors, kill real gaps with tests
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C factorial test
    exit_code: 0
max_retries: 3
files_touched:
  - factorial/test_factorial.py
  - factorial/cosmic-ray.toml
depends_on: []
parallel_group: fast
```

**Directory:** `factorial/`

**Key source:** prime swing algorithm — `_sieve(n)` returns primes ≤ n; `_factorial_rec` recurses with `swing`; `_compute_swing` computes prime exponents; `calculate_factorial(n)` is the public API.

```python
def calculate_factorial(n: int) -> int:
    if n < 0:
        raise ValueError(...)
    if n <= 1:
        result = 1
    else:
        primes = _sieve(n)
        result = _factorial_rec(n, primes)
    ...

def _factorial_rec(n: int, primes: list[int]) -> int:
    if n <= 1:
        return 1
    half_factorial = _factorial_rec(n // 2, primes)
    swing = _compute_swing(n, primes)
    return half_factorial * half_factorial * swing
```

Test classes: `TestSieve`, `TestComputeSwing`, `TestComputeSwingChunk`, `TestTreeCombineInt`, `TestCalculateFactorial`, `TestParseArgs`, `TestGetTargetN`, `TestWriteFactorialFile`, `TestMain`, `TestFactorialProperties`.

**Steps:**

- [ ] `cd factorial && make test` — baseline must pass
- [ ] `cd factorial && make mutants` — discovery; produces `factorial/mutants-report.txt`
- [ ] Read report; list each SURVIVED entry
- [ ] Apply Triage Decision Tree
- [ ] Likely real gaps:
  - `_sieve`: any mutation to the sieve loop (e.g., `<=` → `<`, wrong start index) produces incorrect prime list → wrong factorial. Assert exact primes for small n:
    ```python
    def test_sieve_12(self):
        self.assertEqual(_sieve(12), [2, 3, 5, 7, 11])
    def test_sieve_perfect_square(self):
        # n=9: 3 must be found despite 3*3=9 == n
        self.assertIn(3, _sieve(9))
    ```
  - `_factorial_rec`: mutation on `half_factorial * half_factorial * swing` (e.g., `*` → `+`) gives wrong result. Assert exact values from `KNOWN_FACTORIALS` dict already in the test file.
    ```python
    def test_factorial_10(self):
        self.assertEqual(int(calculate_factorial(10)), 3628800)
    def test_factorial_0(self):
        self.assertEqual(int(calculate_factorial(0)), 1)
    ```
  - `if n <= 1: return 1` → `if n < 1: return 1`: `_factorial_rec(1)` would fall through to the recursive branch instead of returning 1, causing stack deepening or wrong result. Assert `calculate_factorial(1) == 1`.
  - `n // 2` → `n // 3`: wrong split point gives wrong swing. Caught by exact factorial value assertions.
- [ ] Likely equivalents:
  - Mutations to the parallel-vs-serial branch selection (the `if _CPU_COUNT >= ...` style guards) — the output is identical regardless of parallel/serial path; only performance differs. Document as equivalent.
- [ ] Write failing tests, confirm RED on mutant-equivalent code, confirm GREEN on real code
- [ ] Document equivalents in `factorial/cosmic-ray.toml`
- [ ] `cd factorial && make test` — must pass
- [ ] `cd factorial && make mutants` — re-run; verify survivors dropped
- [ ] Invoke `caveman:caveman-commit`; `git add factorial/test_factorial.py factorial/cosmic-ray.toml && git commit -m "$(...)"`

**Interfaces:**

- Consumes: nothing
- Produces: committed test additions in `factorial/test_factorial.py`; equivalents in `factorial/cosmic-ray.toml`

---

### Task 4: collatz — discover and fix surviving mutants

```yaml-task
id: 4
description: Run cosmic-ray on collatz.py, classify survivors, kill real gaps with tests
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C collatz test
    exit_code: 0
max_retries: 3
files_touched:
  - collatz/test_collatz.py
  - collatz/cosmic-ray.toml
depends_on: []
parallel_group: fast
```

**Directory:** `collatz/`

**Key source:**

```python
def collatz_next(n: int) -> int:
    return n // 2 if n % 2 == 0 else 3 * n + 1

def collatz_length(n: int, cache: array.array) -> int:
    limit = len(cache) - 1
    path: list[int] = []
    curr = n
    while not (curr <= limit and cache[curr] != 0):
        path.append(curr)
        curr = collatz_next(curr)
    base = cache[curr]
    for i, val in enumerate(reversed(path)):
        if val <= limit:
            cache[val] = base + i + 1
    return cache[n] - 1

def generate_records(limit: int):
    cache = array.array("I", [0] * (limit + 1))
    cache[1] = 1
    max_len = -1
    for n in range(1, limit + 1):
        length = collatz_length(n, cache)
        if length > max_len:
            max_len = length
            yield n, length
```

Test classes: `TestCollatzNext`, `TestCollatzLength`, `TestGenerateRecords`, `TestGetExponent`, `TestGetExponentInteractive`, `TestMain`, `TestCollatzProperties`.

**Steps:**

- [ ] `cd collatz && make test` — baseline must pass
- [ ] `cd collatz && make mutants` — discovery; produces `collatz/mutants-report.txt`
- [ ] Read report; list each SURVIVED entry
- [ ] Apply Triage Decision Tree
- [ ] Likely real gaps:
  - `n % 2 == 0` → `n % 2 != 0`: inverts even/odd check — applies `3n+1` to even numbers. `collatz_next(6)` should return 3 (not 19):
    ```python
    def test_even_6_gives_3(self):
        self.assertEqual(collatz_next(6), 3)
    def test_odd_5_gives_16(self):
        self.assertEqual(collatz_next(5), 16)  # 3*5+1=16, not 5//2=2
    ```
  - `3 * n + 1` → `3 * n - 1` or `3 * n + 2`: wrong odd-branch formula. Assert `collatz_next(3) == 10` (3*3+1=10).
  - `if length > max_len` → `if length >= max_len`: yields duplicate record-setters (same length as prior max). Assert exact records for `generate_records(10)`:
    ```python
    def test_records_10_exact(self):
        self.assertEqual(
            list(generate_records(10)),
            [(1, 0), (2, 1), (3, 7), (6, 8), (7, 16), (9, 19)],
        )
    ```
  - `cache[n] - 1` → `cache[n]`: returns chain length off by one. Assert `collatz_length(1, cache) == 0` (seed n=1 has length 0).
  - `curr <= limit and cache[curr] != 0` → `curr <= limit or cache[curr] != 0` (boolean operator): may loop differently. Covered by chain-length tests.
- [ ] Likely equivalents:
  - Warning threshold `if n > 7` — mutations here don't affect correctness, only the warning message. Could be equivalent if the warning text is not tested.
- [ ] Write tests for real gaps (RED → GREEN cycle)
- [ ] Document equivalents in `collatz/cosmic-ray.toml`
- [ ] `cd collatz && make test` — must pass
- [ ] `cd collatz && make mutants` — re-run; verify survivors dropped
- [ ] Invoke `caveman:caveman-commit`; `git add collatz/test_collatz.py collatz/cosmic-ray.toml && git commit -m "$(...)"`

**Interfaces:**

- Consumes: nothing
- Produces: committed test additions in `collatz/test_collatz.py`; equivalents in `collatz/cosmic-ray.toml`

---

### Task 5: amicable — discover and fix surviving mutants

```yaml-task
id: 5
description: Run cosmic-ray on amicable.py, classify survivors, kill real gaps with tests
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C amicable test
    exit_code: 0
max_retries: 3
files_touched:
  - amicable/test_amicable.py
  - amicable/cosmic-ray.toml
depends_on: []
parallel_group: fast
```

**Directory:** `amicable/`

**Key source:**

```python
def proper_divisor_sum_sieve(limit: int) -> list[int]:
    s = [0] * (limit + 1)
    for d in range(1, limit // 2 + 1):
        for multiple in range(2 * d, limit + 1, d):
            s[multiple] += d
    return s

def find_amicable_pairs(limit: int):
    s = proper_divisor_sum_sieve(limit)
    for a in range(2, limit + 1):
        b = s[a]
        if b > a and b <= limit and s[b] == a:
            yield a, b
```

Test classes: `TestProperDivisorSumSieve`, `TestFindAmicablePairs`, `TestParseArgs`, `TestGetExponent`, `TestMain`, `TestAmicableProperties`.

**Steps:**

- [ ] `cd amicable && make test` — baseline must pass
- [ ] `cd amicable && make mutants` — discovery; produces `amicable/mutants-report.txt`
- [ ] Read report; list each SURVIVED entry
- [ ] Apply Triage Decision Tree
- [ ] Likely real gaps:
  - `limit // 2` → `limit // 3` in the sieve outer loop: misses some divisors, gives wrong sums. Assert exact sieve values:
    ```python
    def test_sieve_220_is_284(self):
        s = proper_divisor_sum_sieve(285)
        self.assertEqual(s[220], 284)
    def test_sieve_12_is_16(self):
        s = proper_divisor_sum_sieve(20)
        self.assertEqual(s[12], 16)  # 1+2+3+4+6=16
    ```
  - `b > a` → `b >= a`: would also yield pairs where b == a (perfect numbers). Assert perfect number 6 is not a pair:
    ```python
    def test_perfect_number_6_not_in_pairs(self):
        # s[6]=6, b=6, b>=a (if mutated): would yield (6,6) which is wrong
        pairs = list(find_amicable_pairs(10))
        self.assertNotIn((6, 6), pairs)
    ```
  - `s[b] == a` → `s[b] != a`: would invert the amicability check, yielding non-amicable pairs. Assert the exact first pair:
    ```python
    def test_first_pair_220_284(self):
        self.assertEqual(list(find_amicable_pairs(285)), [(220, 284)])
    ```
  - `range(2 * d, limit + 1, d)` start mutation: wrong multiples accumulated. Caught by sieve exact-value tests.
- [ ] Likely equivalents:
  - `for d in range(1, limit // 2 + 1)` → `for d in range(1, limit // 2)`: misses last value of d. For most limits `limit // 2` is not a divisor of anything meaningful. However, this IS a real gap for some inputs (e.g., d = limit//2 = 5, multiple = 10 when limit=10: `s[10] += 5` would be missed). So this is likely a real gap, not equivalent.
- [ ] Write tests for real gaps (RED → GREEN cycle)
- [ ] Document equivalents in `amicable/cosmic-ray.toml`
- [ ] `cd amicable && make test` — must pass
- [ ] `cd amicable && make mutants` — re-run; verify survivors dropped
- [ ] Invoke `caveman:caveman-commit`; `git add amicable/test_amicable.py amicable/cosmic-ray.toml && git commit -m "$(...)"`

**Interfaces:**

- Consumes: nothing
- Produces: committed test additions in `amicable/test_amicable.py`; equivalents in `amicable/cosmic-ray.toml`

---

### Task 6: perfect-numbers — discover and fix surviving mutants

```yaml-task
id: 6
description: Run cosmic-ray on perfect_numbers.py, classify survivors, kill real gaps with tests
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C perfect-numbers test
    exit_code: 0
max_retries: 3
files_touched:
  - perfect-numbers/test_perfect_numbers.py
  - perfect-numbers/cosmic-ray.toml
depends_on: []
parallel_group: fast
```

**Directory:** `perfect-numbers/`

**Key source:**

```python
def is_prime(n: int) -> bool:
    if n < 2: return False
    if n == 2: return True
    if n % 2 == 0: return False
    i = 3
    while i * i <= n:
        if n % i == 0: return False
        i += 2
    return True

def lucas_lehmer(p: int) -> bool:
    if p == 2: return True
    mp = (1 << p) - 1
    s = 4
    for _ in range(p - 2):
        s = (s * s - 2) % mp
    return s == 0

def generate_perfect_numbers(limit: int):
    if limit < 6: return
    max_p = (limit.bit_length() // 2) + 3
    for p in range(2, max_p + 1):
        if not is_prime(p): continue
        if not lucas_lehmer(p): continue
        mp = (1 << p) - 1
        n = (1 << (p - 1)) * mp
        if n > limit: return
        yield p, n
```

Known perfect numbers for testing: p=2→6, p=3→28, p=5→496, p=7→8128, p=13→33550336.

Test classes: `TestIsPrime`, `TestLucasLehmer`, `TestVerifyPerfect`, `TestGeneratePerfectNumbers`, `TestGetExponent`, `TestMain`, `TestPerfectNumbersProperties`.

**Steps:**

- [ ] `cd perfect-numbers && make test` — baseline must pass
- [ ] `cd perfect-numbers && make mutants` — discovery; produces `perfect-numbers/mutants-report.txt`
- [ ] Read report; list each SURVIVED entry
- [ ] Apply Triage Decision Tree
- [ ] Likely real gaps:
  - `is_prime`: `i * i <= n` → `i * i < n` misses composite detection when `i*i == n`:
    ```python
    def test_9_is_not_prime(self):
        self.assertFalse(is_prime(9))   # 3*3=9 must be caught by i<=√n
    def test_25_is_not_prime(self):
        self.assertFalse(is_prime(25))  # 5*5=25
    ```
  - `lucas_lehmer`: `s = (s * s - 2) % mp` → arithmetic mutations give wrong sequence. Assert known non-Mersenne exponents return False:
    ```python
    def test_p11_not_mersenne(self):
        self.assertFalse(lucas_lehmer(11))
    ```
  - `generate_perfect_numbers`: `max_p = (limit.bit_length() // 2) + 3` → mutation to `// 2` or `+ 3` may truncate the search. Assert p=7 (n=8128) is found when limit=10^4:
    ```python
    def test_n4_finds_four_numbers(self):
        result = [n for _, n in generate_perfect_numbers(10**4)]
        self.assertEqual(result, [6, 28, 496, 8128])
    ```
  - `if limit < 6: return` → `if limit <= 6: return`: would exclude limit=6 from finding 6. Assert `generate_perfect_numbers(6)` returns `[(2, 6)]`:
    ```python
    def test_limit_exactly_6_finds_6(self):
        self.assertEqual(list(generate_perfect_numbers(6)), [(2, 6)])
    ```
- [ ] Likely equivalents (per ADR on Rust perfect-numbers-rs):
  - `verify_perfect(p)` always returns True by Euler's theorem — mutations to the sigma check are equivalent. Document them.
  - `lucas_lehmer` dead branch: rug Integer always non-negative in Python too; `(s * s - 2) % mp` is always non-negative for valid p. Mutations to a non-existent negative branch are equivalent.
- [ ] Write tests for real gaps (RED → GREEN cycle)
- [ ] Document equivalents in `perfect-numbers/cosmic-ray.toml`
- [ ] `cd perfect-numbers && make test` — must pass
- [ ] `cd perfect-numbers && make mutants` — re-run; verify survivors dropped
- [ ] Invoke `caveman:caveman-commit`; `git add perfect-numbers/test_perfect_numbers.py perfect-numbers/cosmic-ray.toml && git commit -m "$(...)"`

**Interfaces:**

- Consumes: nothing
- Produces: committed test additions in `perfect-numbers/test_perfect_numbers.py`; equivalents in `perfect-numbers/cosmic-ray.toml`

---

### Task 7: pi — discover and fix surviving mutants

```yaml-task
id: 7
description: Run cosmic-ray on pi.py, classify survivors, kill real gaps with tests
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C pi test
    exit_code: 0
max_retries: 3
files_touched:
  - pi/test_pi.py
  - pi/cosmic-ray.toml
depends_on: [1, 2, 3, 4, 5, 6]
```

**Directory:** `pi/`

**Key source:** Chudnovsky algorithm. Constants used:

```python
_CHU_A = 13591409
_CHU_B = 545140134
_CHU_C3_OVER_24 = 10939058860032000  # (640320^3)/24
```

Binary splitting: `_chudnovsky_bs(a, b)` returns `(P, Q, T)` where `π = 426880√10005 · Q/T`.
Tree combine: `_tree_combine(pqt_list)` merges `(P,Q,T)` chunks with `T(a,b) = Q(m,b)*T(a,m) + P(a,m)*T(m,b)`.
Public API: `calculate_pi_high_precision(digits)`.

**Prerequisite:** `python3 -c "import gmpy2"` must succeed. If not, `pip install gmpy2`.

**Runtime warning:** cosmic-ray uses 60 s/mutation; this may take 90–180 minutes. Run in background or in a long-lived shell session. If it times out, re-run `make mutants` — cosmic-ray resumes from the sqlite session.

Test classes and imports are at top of `pi/test_pi.py` — includes `_tree_combine`, `_pwrite_all`, `calculate_pi_high_precision`, `get_target_digits`, `parse_args`.

`PI_REF = "3.14159265358979323846264338327950288419716939937510"` is available in the test file.

**Steps:**

- [ ] `cd pi && make test` — baseline must pass
- [ ] `cd pi && make mutants` — discovery; takes 90–180 minutes; produces `pi/mutants-report.txt`
- [ ] Read report; list each SURVIVED entry
- [ ] Apply Triage Decision Tree
- [ ] Likely real gaps:
  - Mutations to Chudnovsky constants (`_CHU_A`, `_CHU_B`, `_CHU_C3_OVER_24`): any change produces wrong π digits. Assert first 10 digits:
    ```python
    def test_pi_50_digits_matches_ref(self):
        result = _quiet_pi(50)
        pi_str = _pi_to_str(result, 50) if _HAS_GMPY2 else str(result)
        self.assertTrue(pi_str.startswith("3.14159265"))
    ```
  - `_tree_combine` merge rule mutation (`Qr * Tl + Pl * Tr` → `Qr * Tl - Pl * Tr`): gives wrong intermediate results. The existing `test_two_elements` or `test_four_elements_tree_order` may already cover this; if not:
    ```python
    def test_tree_combine_two_chunks_known_value(self):
        # For a=0,b=1: P=1, Q=1, T=_CHU_A (from _chudnovsky_bs leaf)
        # This is gmpy2-dependent; test the merge formula directly
        P1, Q1, T1 = _gmpy2.mpz(1), _gmpy2.mpz(2), _gmpy2.mpz(3)
        P2, Q2, T2 = _gmpy2.mpz(4), _gmpy2.mpz(5), _gmpy2.mpz(6)
        # Merge: P=P1*P2, Q=Q1*Q2, T=Q2*T1+P1*T2
        P, Q, T = _tree_combine([(P1,Q1,T1),(P2,Q2,T2)])
        self.assertEqual(P, 4)   # 1*4
        self.assertEqual(Q, 10)  # 2*5
        self.assertEqual(T, 36)  # 5*3 + 1*6
    ```
  - `_chudnovsky_bs` leaf case (`if a == 0`) → wrong P/Q/T seed:
    ```python
    def test_bs_leaf_a0(self):
        from pi import _chudnovsky_bs
        P, Q, T = _chudnovsky_bs(0, 1)
        self.assertEqual(int(P), 1)
        self.assertEqual(int(Q), 1)
        self.assertEqual(int(T), _CHU_A)
    ```
- [ ] Likely equivalents:
  - Parallel/serial path selection guards (performance only — output identical)
  - Mutations to progress-bar formatting strings (stdout cosmetic — not tested)
  - `m = (a + b) >> 1` → `m = (a + b) // 2`: identical for non-negative integers. Document as equivalent.
- [ ] Write tests for real gaps (RED → GREEN cycle; `_quiet_pi` suppresses progress output)
- [ ] Document equivalents in `pi/cosmic-ray.toml`
- [ ] `cd pi && make test` — must pass
- [ ] `cd pi && make mutants` — re-run; verify survivors dropped
- [ ] Invoke `caveman:caveman-commit`; `git add pi/test_pi.py pi/cosmic-ray.toml && git commit -m "$(...)"`

**Interfaces:**

- Consumes: nothing from other tasks (depends_on is CPU-sequencing only)
- Produces: committed test additions in `pi/test_pi.py`; equivalents in `pi/cosmic-ray.toml`

---

### Task 8: e — discover and fix surviving mutants

```yaml-task
id: 8
description: Run cosmic-ray on e.py, classify survivors, kill real gaps with tests
role: executor
model: sonnet
tdd: required
acceptance:
  - cmd: make -C e test
    exit_code: 0
max_retries: 3
files_touched:
  - e/test_e.py
  - e/cosmic-ray.toml
depends_on: [7]
```

**Directory:** `e/`

**Key source:** Taylor series binary splitting. Constants: none (unlike pi).

```python
def _taylor_bs(a, b):
    if b - a == 1:
        if a == 0:
            return _gmpy2.mpz(1), _gmpy2.mpz(1)
        val = _gmpy2.mpz(a + 1)
        return val, val
    m = (a + b) >> 1
    Pl, Ql = _taylor_bs(a, m)
    Pr, Qr = _taylor_bs(m, b)
    return Pl * Pr, Ql * Pr + Qr    # e = Q(0,N) / P(0,N)
```

Tree combine: `_tree_combine(pq_list)` merges with `Q(a,b) = Q(a,m)*P(m,b) + Q(m,b)`.
Public API: `calculate_e(digits)`.

**Prerequisite:** `python3 -c "import gmpy2"` must succeed.

**Runtime warning:** same as pi — 60 s/mutation, 90–180 minutes. Run in background.

Test classes: check top of `e/test_e.py` for imports. `E_REF` known decimal expansion is available.

**Steps:**

- [ ] `cd e && make test` — baseline must pass
- [ ] `cd e && make mutants` — discovery; produces `e/mutants-report.txt`
- [ ] Read report; list each SURVIVED entry
- [ ] Apply Triage Decision Tree
- [ ] Likely real gaps:
  - `_taylor_bs` leaf: `val = _gmpy2.mpz(a + 1)` → `a + 2` gives wrong term weight. Assert specific leaf values:
    ```python
    def test_taylor_bs_leaf_a1(self):
        from e import _taylor_bs
        P, Q = _taylor_bs(1, 2)
        self.assertEqual(int(P), 2)  # a+1=2
        self.assertEqual(int(Q), 2)
    ```
  - `_taylor_bs` merge: `Ql * Pr + Qr` → `Ql * Pr - Qr` gives wrong sum. Assert `_tree_combine` output:
    ```python
    def test_tree_combine_merge_formula(self):
        from e import _tree_combine
        P1, Q1 = _gmpy2.mpz(2), _gmpy2.mpz(3)
        P2, Q2 = _gmpy2.mpz(4), _gmpy2.mpz(5)
        # Q(a,b) = Q(a,m)*P(m,b) + Q(m,b) = 3*4 + 5 = 17
        P, Q = _tree_combine([(P1,Q1),(P2,Q2)])
        self.assertEqual(int(P), 8)   # 2*4
        self.assertEqual(int(Q), 17)  # 3*4+5
    ```
  - `calculate_e` result accuracy: assert first 10 digits of e:
    ```python
    def test_e_20_digits_matches_ref(self):
        # E_REF is defined at top of test_e.py
        result = _quiet_e(20)
        # Use _e_to_str or mpfr str as appropriate
        e_str = str(result)[:12]
        self.assertTrue(e_str.startswith("2.718281828"))
    ```
- [ ] Likely equivalents:
  - `m = (a + b) >> 1` → `m = (a + b) // 2`: identical for non-negative integers. Document.
  - `if a == 0: return mpz(1), mpz(1)`: leaf returning (1,1) regardless of `a`'s value — mutation to `a == 1` may produce same P/Q for most recursive paths. Trace to confirm equivalence before documenting.
  - Parallel/serial path selection (performance only, output identical).
- [ ] Write tests for real gaps (RED → GREEN cycle; use `_quiet_e` wrapper to suppress progress)
- [ ] Document equivalents in `e/cosmic-ray.toml`
- [ ] `cd e && make test` — must pass
- [ ] `cd e && make mutants` — re-run; verify survivors dropped
- [ ] Invoke `caveman:caveman-commit`; `git add e/test_e.py e/cosmic-ray.toml && git commit -m "$(...)"`

**Interfaces:**

- Consumes: nothing from other tasks
- Produces: committed test additions in `e/test_e.py`; equivalents in `e/cosmic-ray.toml`

---

### Task 9: Update plan index, remove backlog entry, open PR

```yaml-task
id: 9
description: Update superpowers/cursor README plan tables and open PR (docs-only, no behavior change)
role: executor
model: sonnet
tdd: not-applicable
acceptance:
  - cmd: test -f docs/superpowers/plans/2026-07-03-python-mutant-killing.md
    exit_code: 0
  - cmd: 'grep -q "In Progress" docs/superpowers/README.md'
    exit_code: 0
max_retries: 2
files_touched:
  - docs/superpowers/README.md
  - docs/cursor/README.md
depends_on: [8]
```

**Steps:**

- [ ] Edit `docs/superpowers/README.md`: update the `2026-07-03` row — add `[plan](plans/2026-07-03-python-mutant-killing.md)` to the Plan column; set Status to `In Progress`
- [ ] Edit `docs/cursor/README.md`: remove "Kill surviving mutants in remaining Python modules" from the Backlog table
- [ ] Invoke `caveman:caveman-commit`; `git add docs/superpowers/README.md docs/cursor/README.md && git commit -m "$(...)"`
- [ ] `git push -u origin test/kill-python-mutants`
- [ ] `gh pr create --title "test(mutation): kill surviving mutants in Python modules" --body "$(cat <<'EOF' ... EOF)"`

PR body sections:

```
## Summary
- Kill surviving cosmic-ray mutants in all 8 Python sub-projects
- Real gaps: new unittest.TestCase tests targeting specific behavioral boundaries
- Equivalent mutations: documented in each module's cosmic-ray.toml

## Test plan
- [ ] make test passes in all 8 module directories
- [ ] make mutants re-run shows 0 surviving (or documented equivalents)
- [ ] CI green

🤖 Generated with Claude Code
EOF
```

- [ ] `gh pr checks <PR_NUMBER> --watch` — monitor until all checks green or red
- [ ] If any check fails: read `gh run view <run-id> --log-failed`, fix, push, re-check

**Interfaces:**

- Consumes: all committed module fixes from Tasks 1–8
- Produces: open PR; updated plan index
