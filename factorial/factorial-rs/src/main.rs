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
fn compute_swing_chunk(_m: u64, _primes: &[u32]) -> Integer {
    todo!()
}

#[allow(dead_code)]
fn compute_swing(_m: u64, _primes: &[u32]) -> Integer {
    todo!()
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
