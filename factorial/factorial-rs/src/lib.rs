use rug::ops::Pow;
use rug::Integer;

fn sieve(n: u64) -> Vec<u32> {
    if n < 2 {
        return vec![];
    }
    let n = n as usize;
    let mut is_composite = vec![false; n + 1];
    is_composite[0] = true;
    is_composite[1] = true;
    let mut p = 2usize;
    // mutants::skip — p*p→p+p is equivalent (loops more but marks same composites); <=→< killed by test_sieve_count_to_49
    while p * p <= n {
        if !is_composite[p] {
            // mutants::skip — p*p→p+p is equivalent (2p starts earlier but marks same composites as p²)
            let mut m = p * p;
            while m <= n {
                is_composite[m] = true;
                m += p;
            }
        }
        p += 1;
    }
    (2..=n).filter(|&i| !is_composite[i]).map(|i| i as u32).collect()
}

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
        // mutants::skip — exp>=0 is equivalent: p^0=1 multiplies by 1 (no-op)
        if exp > 0 {
            result *= Integer::from(p).pow(exp);
        }
    }
    result
}

fn compute_swing(m: u64, primes: &[u32]) -> Integer {
    use rayon::prelude::*;

    let relevant: Vec<u32> = primes.iter().copied().take_while(|&p| p as u64 <= m).collect();
    if relevant.is_empty() {
        return Integer::from(1u64);
    }

    let num_threads = rayon::current_num_threads().max(1);
    let chunk_size = relevant.len().div_ceil(num_threads).max(1);

    relevant.par_chunks(chunk_size).map(|chunk| compute_swing_chunk(m, chunk)).reduce(
        || Integer::from(1u64),
        |a, b| {
            let mut r = a;
            r *= b;
            r
        },
    )
}

fn factorial_rec(n: u64, primes: &[u32]) -> Integer {
    if n <= 1 {
        return Integer::from(1u64);
    }
    let half = factorial_rec(n / 2, primes);
    let swing = compute_swing(n, primes);
    Integer::from(&half * &half) * swing
}

pub fn calculate_factorial(n: u64) -> Integer {
    if n <= 1 {
        return Integer::from(1u64);
    }
    let primes = sieve(n);
    factorial_rec(n, &primes)
}

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;

    // --- sieve ---

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
            assert!(p < 2 || (2..p).all(|d| p % d != 0), "{} is composite", p);
        }
    }

    #[test]
    fn test_sieve_count_to_100() {
        // π(100) = 25
        assert_eq!(sieve(100).len(), 25);
    }

    #[test]
    fn test_sieve_count_to_49() {
        // π(49) = 15; 49 = 7² must be marked composite (tests the p*p <= n bound)
        assert_eq!(sieve(49).len(), 15);
        assert!(!sieve(49).contains(&49));
    }

    #[test]
    fn test_sieve_count_to_1000() {
        // π(1000) = 168
        assert_eq!(sieve(1000).len(), 168);
    }

    // --- compute_swing_chunk ---

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
        assert_eq!(compute_swing_chunk(2, &[2u32]), Integer::from(2u64));
    }

    #[test]
    fn test_swing_chunk_p2_contribution_for_m6() {
        assert_eq!(compute_swing_chunk(6, &[2u32]), Integer::from(4u64));
    }

    #[test]
    fn test_swing_chunk_p3_contribution_for_m6() {
        assert_eq!(compute_swing_chunk(6, &[3u32]), Integer::from(1u64));
    }

    #[test]
    fn test_swing_chunk_p5_contribution_for_m6() {
        assert_eq!(compute_swing_chunk(6, &[5u32]), Integer::from(5u64));
    }

    #[test]
    fn test_swing_chunk_exp_zero_returns_one() {
        // p=7, m=14: floor(14/7)=2 (even), so exp=0; p^0=1 contributes nothing
        assert_eq!(compute_swing_chunk(14, &[7u32]), Integer::from(1u64));
    }

    // --- compute_swing ---

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
        let primes = sieve(10);
        assert_eq!(compute_swing(6, &primes), Integer::from(20u64));
    }

    #[test]
    fn test_swing_4() {
        let primes = sieve(10);
        assert_eq!(compute_swing(4, &primes), Integer::from(6u64));
    }

    #[test]
    fn test_swing_empty_primes() {
        assert_eq!(compute_swing(100, &[]), Integer::from(1u64));
    }

    #[test]
    fn test_swing_satisfies_factorial_identity() {
        let primes = sieve(10);
        let sw6 = compute_swing(6, &primes);
        let three_factorial_sq = Integer::from(36u64);
        assert_eq!(sw6 * three_factorial_sq, Integer::from(720u64));
    }

    // --- factorial_rec ---

    #[test]
    fn test_factorial_rec_base_0() {
        let primes = sieve(10);
        assert_eq!(factorial_rec(0, &primes), Integer::from(1u64));
    }

    #[test]
    fn test_factorial_rec_base_1() {
        let primes = sieve(10);
        assert_eq!(factorial_rec(1, &primes), Integer::from(1u64));
    }

    #[test]
    fn test_factorial_rec_2() {
        let primes = sieve(10);
        assert_eq!(factorial_rec(2, &primes), Integer::from(2u64));
    }

    #[test]
    fn test_factorial_rec_5() {
        let primes = sieve(10);
        assert_eq!(factorial_rec(5, &primes), Integer::from(120u64));
    }

    // --- calculate_factorial ---

    #[test]
    fn test_calculate_factorial_0() {
        assert_eq!(calculate_factorial(0), Integer::from(1u64));
    }

    #[test]
    fn test_calculate_factorial_1() {
        assert_eq!(calculate_factorial(1), Integer::from(1u64));
    }

    #[test]
    fn test_calculate_factorial_5() {
        assert_eq!(calculate_factorial(5), Integer::from(120u64));
    }

    #[test]
    fn test_calculate_factorial_10() {
        assert_eq!(calculate_factorial(10), Integer::from(3628800u64));
    }

    #[test]
    fn test_calculate_factorial_20() {
        assert_eq!(calculate_factorial(20), Integer::from(2432902008176640000u64));
    }

    proptest! {
        #[test]
        fn prop_generate_succeeds(n in 1u64..=20u64) {
            let result = calculate_factorial(n);
            prop_assert!(result > 0u64);
        }
    }
}
