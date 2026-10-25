# amicable

Find all amicable pairs (a, b) with a < b and b ≤ 10^N.

Two distinct integers are amicable when each equals the sum of the other's proper
divisors: s(a)=b and s(b)=a, where s(n) = σ(n) − n.

The smallest pair is (220, 284): s(220)=284, s(284)=220.

## Usage

```bash
python3 amicable.py           # interactive prompts (terminal only)
python3 amicable.py 4         # all pairs up to 10^4, written to file
python3 amicable.py 4 --show  # also print each pair
python3 amicable.py --smoke   # quick check at N=5
```

With SIZE given the program never reads stdin; with no arguments and stdin not a terminal it exits 2 with usage. `--yes` is accepted and ignored.

Output: one `a b` pair per line, ascending by a. Saved to `amicable_1eN.txt`.

## Build

```bash
make run       # python3 amicable.py
make lint      # ruff check .
make test      # lint + unittest
make coverage  # coverage run + report
```
