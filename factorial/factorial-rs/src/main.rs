use rug::ops::Pow;
use rug::Integer;

#[allow(dead_code)]
fn sieve(n: u64) -> Vec<u32> {
    if n < 2 {
        return vec![];
    }
    let n = n as usize;
    let mut is_composite = vec![false; n + 1];
    is_composite[0] = true;
    is_composite[1] = true;
    let mut p = 2usize;
    while p * p <= n {
        if !is_composite[p] {
            let mut m = p * p;
            while m <= n {
                is_composite[m] = true;
                m += p;
            }
        }
        p += 1;
    }
    (2..=n)
        .filter(|&i| !is_composite[i])
        .map(|i| i as u32)
        .collect()
}

#[allow(dead_code)]
fn compute_swing_chunk(m: u64, primes: &[u32]) -> Integer {
    let mut result = Integer::from(1u64);
    for &p in primes {
        let p = p as u64;
        if p > m {
            break; // primes is sorted ascending
        }
        let mut exp = 0u32;
        let mut q = m;
        while q >= p {
            q /= p;
            if q & 1 == 1 {
                exp += 1;
            }
        }
        if exp > 0 {
            result *= Integer::from(p).pow(exp);
        }
    }
    result
}

#[allow(dead_code)]
fn compute_swing(m: u64, primes: &[u32]) -> Integer {
    use rayon::prelude::*;

    let relevant: Vec<u32> = primes
        .iter()
        .copied()
        .take_while(|&p| p as u64 <= m)
        .collect();
    if relevant.is_empty() {
        return Integer::from(1u64);
    }

    let num_threads = rayon::current_num_threads().max(1);
    let chunk_size = relevant.len().div_ceil(num_threads).max(1);

    relevant
        .par_chunks(chunk_size)
        .map(|chunk| compute_swing_chunk(m, chunk))
        .reduce(
            || Integer::from(1u64),
            |a, b| {
                let mut r = a;
                r *= b;
                r
            },
        )
}

#[allow(dead_code)]
fn factorial_rec(_n: u64, _primes: &[u32]) -> Integer {
    todo!()
}

#[allow(dead_code)]
fn calculate_factorial(_n: u64) -> Integer {
    todo!()
}

#[allow(dead_code)]
fn fmt_int(_n: u64) -> String {
    todo!()
}

fn main() {
    todo!()
}

#[cfg(test)]
mod tests {
    use super::*;

    // compute_swing_chunk tests
    #[test]
    fn test_swing_chunk_empty() {
        assert_eq!(compute_swing_chunk(10, &[]), Integer::from(1u64));
    }

    #[test]
    fn test_swing_chunk_prime_exceeds_m() {
        assert_eq!(compute_swing_chunk(2, &[3u32, 5, 7]), Integer::from(1u64));
    }

    #[test]
    fn test_swing_chunk_m_equals_2() {
        // p=2: q=2->1(odd,+1) -> exp=1, 2^1=2
        assert_eq!(compute_swing_chunk(2, &[2u32]), Integer::from(2u64));
    }

    #[test]
    fn test_swing_chunk_p2_contribution_for_m6() {
        // p=2 for m=6: q=6->3(odd,+1)->1(odd,+1) -> exp=2, contrib=4
        assert_eq!(compute_swing_chunk(6, &[2u32]), Integer::from(4u64));
    }

    #[test]
    fn test_swing_chunk_p3_contribution_for_m6() {
        // p=3 for m=6: q=6->2(even) -> exp=0, contrib=1
        assert_eq!(compute_swing_chunk(6, &[3u32]), Integer::from(1u64));
    }

    #[test]
    fn test_swing_chunk_p5_contribution_for_m6() {
        // p=5 for m=6: q=6->1(odd,+1) -> exp=1, contrib=5
        assert_eq!(compute_swing_chunk(6, &[5u32]), Integer::from(5u64));
    }

    // compute_swing tests
    #[test]
    fn test_swing_0() {
        let primes = sieve(10);
        assert_eq!(compute_swing(0, &primes), Integer::from(1u64));
    }

    #[test]
    fn test_swing_1() {
        let primes = sieve(10);
        assert_eq!(compute_swing(1, &primes), Integer::from(1u64));
    }

    #[test]
    fn test_swing_2() {
        let primes = sieve(10);
        assert_eq!(compute_swing(2, &primes), Integer::from(2u64));
    }

    #[test]
    fn test_swing_6() {
        // swing(6) = 4 * 1 * 5 = 20
        let primes = sieve(10);
        assert_eq!(compute_swing(6, &primes), Integer::from(20u64));
    }

    #[test]
    fn test_swing_4() {
        // swing(4): p=2 exp=1->2, p=3 exp=1->3. swing(4) = 6
        let primes = sieve(10);
        assert_eq!(compute_swing(4, &primes), Integer::from(6u64));
    }

    #[test]
    fn test_swing_empty_primes() {
        assert_eq!(compute_swing(100, &[]), Integer::from(1u64));
    }

    #[test]
    fn test_swing_satisfies_factorial_identity() {
        // swing(6) * 3!^2 = 20 * 36 = 720 = 6!
        let primes = sieve(10);
        let sw6 = compute_swing(6, &primes);
        let three_factorial_sq = Integer::from(36u64);
        assert_eq!(sw6 * three_factorial_sq, Integer::from(720u64));
    }

    // Sieve tests
    #[test]
    fn test_sieve_below_2_empty() {
        assert!(sieve(0).is_empty());
        assert!(sieve(1).is_empty());
    }

    #[test]
    fn test_sieve_n_equals_2() {
        assert_eq!(sieve(2), vec![2u32]);
    }

    #[test]
    fn test_sieve_small_known() {
        assert_eq!(sieve(10), vec![2u32, 3, 5, 7]);
    }

    #[test]
    fn test_sieve_no_composites() {
        let primes = sieve(20);
        for &p in &primes {
            assert!(p < 2 || (2..p).all(|d| p % d != 0),
                "{} is composite", p);
        }
    }

    #[test]
    fn test_sieve_count_to_100() {
        // π(100) = 25
        assert_eq!(sieve(100).len(), 25);
    }

    #[test]
    fn test_sieve_count_to_1000() {
        // π(1000) = 168
        assert_eq!(sieve(1000).len(), 168);
    }
}
