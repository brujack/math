# math

[![pi.py](https://github.com/brujack/math/actions/workflows/pi-py.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/pi-py.yml)
[![pi-rs](https://github.com/brujack/math/actions/workflows/pi-rs.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/pi-rs.yml)
[![prime-rs](https://github.com/brujack/math/actions/workflows/prime-rs.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/prime-rs.yml)
[![fib.py](https://github.com/brujack/math/actions/workflows/fib-py.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/fib-py.yml)
[![fib-rs](https://github.com/brujack/math/actions/workflows/fib-rs.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/fib-rs.yml)
[![sq.py](https://github.com/brujack/math/actions/workflows/sq-py.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/sq-py.yml)
[![sq-rs](https://github.com/brujack/math/actions/workflows/sq-rs.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/sq-rs.yml)

High-performance mathematical computation tools.

| Project | Description | Implementation | CI |
|---------|-------------|----------------|----|
| [`pi/`](pi/README.md) | Calculate π to N decimal places | Python + Rust | [![pi.py](https://github.com/brujack/math/actions/workflows/pi-py.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/pi-py.yml) [![pi-rs](https://github.com/brujack/math/actions/workflows/pi-rs.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/pi-rs.yml) |
| [`prime/`](prime/README.md) | Find all primes up to 10^N | Rust | [![prime-rs](https://github.com/brujack/math/actions/workflows/prime-rs.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/prime-rs.yml) |
| [`fib/`](fib/README.md) | Generate all Fibonacci numbers with up to 10^X digits | Python + Rust | [![fib.py](https://github.com/brujack/math/actions/workflows/fib-py.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/fib-py.yml) [![fib-rs](https://github.com/brujack/math/actions/workflows/fib-rs.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/fib-rs.yml) |
| [`sq/`](sq/README.md) | Generate all perfect squares with up to 10^N digits (N=1 max) | Python + Rust | [![sq.py](https://github.com/brujack/math/actions/workflows/sq-py.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/sq-py.yml) [![sq-rs](https://github.com/brujack/math/actions/workflows/sq-rs.yml/badge.svg?branch=master)](https://github.com/brujack/math/actions/workflows/sq-rs.yml) |

---

## pi

Calculates π to an arbitrary number of decimal places using the **Chudnovsky algorithm** with binary splitting.

- Python implementation (`pi/pi.py`) — best for up to ~50M digits
- Rust implementation (`pi/pi-rs/`) — best for 50M+ digits; shared-memory rayon parallelism with zero IPC overhead

See [`pi/README.md`](pi/README.md) for full details.

---

## prime

Finds every prime number up to 10^N using a **parallel segmented Sieve of Eratosthenes**.

- Rust implementation (`prime/prime-rs/`) — packed bitset segments (32 KB each, fits in L2 cache), rayon-parallelised across all cores, streams output to file to keep peak RAM ≤ ~50 MB

See [`prime/README.md`](prime/README.md) for full details.

---

## fib

Generates every Fibonacci number with at most 10^X decimal digits.

- Python implementation (`fib/fib.py`) — uses Python's built-in arbitrary-precision `int`; no external dependencies
- Rust implementation (`fib/fib-rs/`) — uses `rug`/GMP for best performance at large digit counts

See [`fib/README.md`](fib/README.md) for full details.

---

## sq

Generates every perfect square with at most 10^N decimal digits. N=1 is the only valid value (produces 99,999 squares up to 10 digits).

- Python implementation (`sq/sq.py`) — Python stdlib only, no external dependencies
- Rust implementation (`sq/sq-rs/`) — plain u64 arithmetic, no GMP required

---

## Architectural Decisions

Key decisions are recorded in [`docs/adr/`](docs/adr/README.md): algorithm choices (Chudnovsky, segmented sieve), language strategy (Python vs Rust), library choices (GMP/rug, rayon), and CI structure.
