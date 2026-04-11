/// Number range covered by one sieve segment. 2^19 = 524,288 numbers.
/// Packed bitset (odd numbers only) = 32,768 bytes — fits in L2 cache.
const SEG_SIZE: u64 = 1 << 19;

#[allow(dead_code)]
fn small_sieve(limit: u64) -> Vec<u64> {
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

#[allow(dead_code)]
fn fmt_int(n: u64) -> String {
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

/// Sieve odd numbers in [lo, lo + SEG_SIZE) ∩ [lo, limit] using `small_primes`.
///
/// Packed bitset: bit index i ↔ number lo + 2*i. 1 = composite, 0 = prime.
/// `lo` must be odd.
#[allow(dead_code)]
fn sieve_segment(lo: u64, limit: u64, small_primes: &[u64]) -> Vec<u64> {
    let hi = (lo + SEG_SIZE).min(limit + 1); // exclusive
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

fn main() {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fmt_int_zero() {
        assert_eq!(fmt_int(0), "0");
    }

    #[test]
    fn test_fmt_int_below_thousand() {
        assert_eq!(fmt_int(999), "999");
    }

    #[test]
    fn test_fmt_int_thousands() {
        assert_eq!(fmt_int(1_000), "1,000");
        assert_eq!(fmt_int(10_000), "10,000");
    }

    #[test]
    fn test_fmt_int_millions() {
        assert_eq!(fmt_int(1_234_567), "1,234,567");
    }

    // --- small_sieve ---

    #[test]
    fn test_small_sieve_empty() {
        assert!(small_sieve(0).is_empty());
        assert!(small_sieve(1).is_empty());
    }

    #[test]
    fn test_small_sieve_two() {
        assert_eq!(small_sieve(2), vec![2u64]);
    }

    #[test]
    fn test_small_sieve_ten() {
        assert_eq!(small_sieve(10), vec![2u64, 3, 5, 7]);
    }

    #[test]
    fn test_small_sieve_thirty() {
        assert_eq!(
            small_sieve(30),
            vec![2u64, 3, 5, 7, 11, 13, 17, 19, 23, 29]
        );
    }

    #[test]
    fn test_small_sieve_count_100() {
        // π(100) = 25
        assert_eq!(small_sieve(100).len(), 25);
    }

    #[test]
    fn test_small_sieve_count_1000() {
        // π(1000) = 168
        assert_eq!(small_sieve(1000).len(), 168);
    }

    // --- sieve_segment ---

    #[test]
    fn test_sieve_segment_small() {
        // Primes in [11, 30] given small primes [2,3,5,7].
        let sp = vec![2u64, 3, 5, 7];
        let result = sieve_segment(11, 30, &sp);
        assert_eq!(result, vec![11u64, 13, 17, 19, 23, 29]);
    }

    #[test]
    fn test_sieve_segment_known_range() {
        // Primes in [101, 200]; sqrt(200) < 15 so sieve with primes up to 14.
        let sp = small_sieve(14);
        let result = sieve_segment(101, 200, &sp);
        let expected = vec![
            101u64, 103, 107, 109, 113, 127, 131, 137, 139, 149,
            151, 157, 163, 167, 173, 179, 181, 191, 193, 197, 199,
        ];
        assert_eq!(result, expected);
    }

    #[test]
    fn test_sieve_segment_all_odd() {
        // All returned values must be odd (segment starts at odd lo).
        let sp = small_sieve(32);
        let result = sieve_segment(101, 200, &sp);
        assert!(result.iter().all(|&p| p % 2 == 1));
    }

    #[test]
    fn test_sieve_segment_lo_exceeds_limit() {
        // lo > limit → empty.
        let sp = vec![2u64, 3, 5];
        assert!(sieve_segment(101, 100, &sp).is_empty());
    }

    #[test]
    fn test_sieve_segment_single_prime() {
        // lo == limit == 31 (a prime): returns exactly [31].
        let sp = small_sieve(5);
        assert_eq!(sieve_segment(31, 31, &sp), vec![31u64]);
    }
}
