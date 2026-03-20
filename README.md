# math

High-performance mathematical computation tools.

| Project | Description | Implementation |
|---------|-------------|----------------|
| [`pi/`](pi/README.md) | Calculate π to N decimal places | Python + Rust |
| [`prime/`](prime/README.md) | Find all primes up to 10^N | Rust |

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
