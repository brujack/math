use std::io::{self, Write};

// ---------------------------------------------------------------------------
// Sieve
// ---------------------------------------------------------------------------

/// Build a packed bitset covering odd numbers 3..=limit.
/// Bit index i represents 2i+3. Bit set (1) = composite; clear (0) = prime.
/// Callers must only pass n ≤ limit to is_prime; no bounds check is performed.
pub fn build_sieve(limit: u64) -> Vec<u64> {
    if limit < 3 {
        return vec![];
    }
    let count = ((limit - 3) / 2 + 1) as usize;
    let words = count.div_ceil(64);
    let mut sieve = vec![0u64; words];
    let mut p = 3u64;
    while p * p <= limit {
        let pi = ((p - 3) / 2) as usize;
        if (sieve[pi / 64] >> (pi % 64)) & 1 == 0 {
            let mut m = p * p;
            while m <= limit {
                let mi = ((m - 3) / 2) as usize;
                sieve[mi / 64] |= 1u64 << (mi % 64);
                m += 2 * p;
            }
        }
        p += 2;
    }
    sieve
}

/// Return true if n is prime, using the sieve built for the same limit.
/// Panics if n > limit (caller's responsibility to stay in range).
pub fn is_prime(n: u64, sieve: &[u64]) -> bool {
    match n {
        0 | 1 => false,
        2 => true,
        _ if n.is_multiple_of(2) => false,
        _ => {
            let idx = ((n - 3) / 2) as usize;
            (sieve[idx / 64] >> (idx % 64)) & 1 == 0
        }
    }
}

// ---------------------------------------------------------------------------
// Core algorithm
// ---------------------------------------------------------------------------

/// Write all Goldbach pairs for even n in 4..=limit to `out`.
/// Each line: `n p q\n` with p ≤ q and p + q = n, ordered by n then p.
/// Returns the total number of pairs written.
pub fn goldbach_pairs<W: Write>(limit: u64, sieve: &[u64], out: &mut W) -> io::Result<u64> {
    let mut count = 0u64;
    let mut n = 4u64;
    while n <= limit {
        if is_prime(n - 2, sieve) {
            writeln!(out, "{n} 2 {}", n - 2)?;
            count += 1;
        }
        let mut p = 3u64;
        while p <= n / 2 {
            if is_prime(p, sieve) && is_prime(n - p, sieve) {
                writeln!(out, "{n} {p} {}", n - p)?;
                count += 1;
            }
            p += 2;
        }
        n += 2;
    }
    Ok(count)
}
