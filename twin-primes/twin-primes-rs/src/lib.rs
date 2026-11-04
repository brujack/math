use std::io::{self, Write};

/// Number range covered by one sieve segment. 2^19 = 524,288 numbers.
/// Packed bitset (odd numbers only) = 32,768 bytes — fits in L2 cache.
pub const SEG_SIZE: u64 = 1 << 19;

pub fn small_sieve(limit: u64) -> Vec<u64> {
    let n = limit as usize;
    if n < 2 {
        return vec![];
    }
    let mut composite = vec![false; n + 1];
    composite[0] = true;
    composite[1] = true;
    let mut i = 2usize;
    while i * i <= n {
        if !composite[i] {
            let mut j = i * i;
            while j <= n {
                composite[j] = true;
                j += i;
            }
        }
        i += 1;
    }
    (2..=n).filter(|&i| !composite[i]).map(|i| i as u64).collect()
}

pub fn fmt_int(n: u64) -> String {
    let s = n.to_string();
    let mut out = String::with_capacity(s.len() + s.len() / 3);
    for (i, ch) in s.chars().rev().enumerate() {
        if i > 0 && i % 3 == 0 {
            out.push(',');
        }
        out.push(ch);
    }
    out.chars().rev().collect()
}

/// Sieve odd numbers in [lo, lo + seg) ∩ [lo, limit] using `small_primes`.
///
/// Packed bitset: bit index i ↔ number lo + 2*i. 1 = composite, 0 = prime.
/// `lo` must be odd and `seg` even.
pub fn sieve_segment(lo: u64, limit: u64, small_primes: &[u64], seg: u64) -> Vec<u64> {
    debug_assert!(seg.is_multiple_of(2), "seg must be even to keep lo odd");
    let hi = (lo + seg).min(limit + 1); // exclusive
    if lo >= hi {
        return vec![];
    }

    let n = (hi - lo).div_ceil(2) as usize;
    let n_bytes = n.div_ceil(8);
    let mut composite = vec![0u8; n_bytes];

    for &p in small_primes {
        if p == 2 {
            continue;
        }
        let rem = lo % p;
        let mut s = if rem == 0 { lo } else { lo + (p - rem) };
        if s % 2 == 0 {
            s += p;
        }
        if s >= hi {
            continue;
        }
        let mut idx = ((s - lo) / 2) as usize;
        let step = p as usize;
        while idx < n {
            composite[idx >> 3] |= 1u8 << (idx & 7);
            idx += step;
        }
    }

    (0..n)
        .filter(|&i| composite[i >> 3] & (1u8 << (i & 7)) == 0)
        .map(|i| lo + (i as u64) * 2)
        .collect()
}

/// First odd number above `sqrt_limit`: where the segmented phase begins.
pub fn segment_start(sqrt_limit: u64) -> u64 {
    sqrt_limit + 1 + (sqrt_limit & 1)
}

/// Find all twin prime pairs (p, p+2) where both p and p+2 < limit.
/// Writes "p | p+2\n" per pair to `out`. Returns pair count.
pub fn find_twin_primes<W: Write>(limit: u64, out: &mut W) -> io::Result<u64> {
    find_twin_primes_sized(limit, out, SEG_SIZE)
}

/// As `find_twin_primes`, with the segment size `seg` (even) chosen by the caller.
pub fn find_twin_primes_sized<W: Write>(limit: u64, out: &mut W, seg: u64) -> io::Result<u64> {
    debug_assert!(seg.is_multiple_of(2), "seg must be even to keep lo odd");
    if limit < 5 {
        return Ok(0);
    }

    let sqrt_limit = (limit as f64).sqrt() as u64 + 1;
    let small_primes = small_sieve(sqrt_limit);

    let mut count = 0u64;

    // Twin pairs within the small_primes range (both must be < limit).
    for w in small_primes.windows(2) {
        if w[1] - w[0] == 2 && w[1] < limit {
            writeln!(out, "{} | {}", w[0], w[1])?;
            count += 1;
        }
    }

    // Segmented sieve for (sqrt_limit, limit].
    // lo is always odd; seg is even so lo + seg stays odd.
    let mut last_prime: Option<u64> = small_primes.last().copied();
    let mut lo = segment_start(sqrt_limit);

    while lo <= limit {
        let segment = sieve_segment(lo, limit, &small_primes, seg);

        // Boundary: check if last prime from the previous segment + 2 equals
        // the first prime of this segment.
        if let (Some(lp), Some(&fp)) = (last_prime, segment.first())
            && fp == lp + 2
            && fp < limit
        {
            writeln!(out, "{} | {}", lp, fp)?;
            count += 1;
        }

        // Twin pairs within this segment.
        for w in segment.windows(2) {
            if w[1] - w[0] == 2 && w[1] < limit {
                writeln!(out, "{} | {}", w[0], w[1])?;
                count += 1;
            }
        }

        last_prime = segment.last().copied().or(last_prime);
        lo += seg;
    }

    Ok(count)
}
