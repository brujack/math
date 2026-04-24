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

fn factorial_rec(n: u64, primes: &[u32]) -> Integer {
    if n <= 1 {
        return Integer::from(1u64);
    }
    let half = factorial_rec(n / 2, primes);
    let swing = compute_swing(n, primes);
    Integer::from(&half * &half) * swing
}

fn calculate_factorial(n: u64) -> Integer {
    if n <= 1 {
        return Integer::from(1u64);
    }
    let primes = sieve(n);
    factorial_rec(n, &primes)
}

fn fmt_int(n: u64) -> String {
    let s = n.to_string();
    let mut result = String::new();
    let chars: Vec<char> = s.chars().collect();
    let len = chars.len();
    for (i, &c) in chars.iter().enumerate() {
        if i > 0 && (len - i).is_multiple_of(3) {
            result.push(',');
        }
        result.push(c);
    }
    result
}

fn prompt_n() -> u64 {
    use std::io::{self, BufRead, Write};
    loop {
        print!("Enter N to compute N! : ");
        io::stdout().flush().unwrap();
        let stdin = io::stdin();
        let line = stdin.lock().lines().next().unwrap().unwrap();
        match line.trim().parse::<u64>() {
            Ok(n) => return n,
            Err(_) => eprintln!("Invalid input '{}'. Please enter a non-negative integer.", line.trim()),
        }
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let n: u64 = if args.len() > 1 {
        match args[1].parse::<u64>() {
            Ok(v) => v,
            Err(_) => {
                eprintln!("Error: '{}' is not a valid non-negative integer", args[1]);
                std::process::exit(1);
            }
        }
    } else {
        prompt_n()
    };

    eprintln!("Computing {}! ...", fmt_int(n));
    let start = std::time::Instant::now();
    let result = calculate_factorial(n);
    let elapsed = start.elapsed();
    eprintln!("Computed in {:.2}s", elapsed.as_secs_f64());

    let digits_str = result.to_string_radix(10);
    let digit_count = digits_str.len();
    let filename = format!("factorial_{}.txt", n);

    eprintln!("Writing {} digits to {} ...", fmt_int(digit_count as u64), filename);
    let write_start = std::time::Instant::now();
    std::fs::write(&filename, &digits_str).expect("Failed to write output file");
    let write_elapsed = write_start.elapsed();
    eprintln!(
        "{} digits written to {} in {:.2}s",
        fmt_int(digit_count as u64),
        filename,
        write_elapsed.as_secs_f64()
    );
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

    // factorial_rec tests
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

    // fmt_int tests
    #[test]
    fn test_fmt_int_zero() {
        assert_eq!(fmt_int(0), "0");
    }

    #[test]
    fn test_fmt_int_sub_thousand() {
        assert_eq!(fmt_int(999), "999");
    }

    #[test]
    fn test_fmt_int_thousands() {
        assert_eq!(fmt_int(1000), "1,000");
    }

    #[test]
    fn test_fmt_int_millions() {
        assert_eq!(fmt_int(1_234_567), "1,234,567");
    }

    #[test]
    fn test_fmt_int_large() {
        assert_eq!(fmt_int(1_000_000_000), "1,000,000,000");
    }

    // calculate_factorial tests
    #[test]
    fn test_calculate_factorial_0() {
        assert_eq!(calculate_factorial(0), Integer::from(1u64));
    }

    #[test]
    fn test_calculate_factorial_1() {
        assert_eq!(calculate_factorial(1), Integer::from(1u64));
    }

    #[test]
    fn test_calculate_factorial_2() {
        assert_eq!(calculate_factorial(2), Integer::from(2u64));
    }

    #[test]
    fn test_calculate_factorial_3() {
        assert_eq!(calculate_factorial(3), Integer::from(6u64));
    }

    #[test]
    fn test_calculate_factorial_4() {
        assert_eq!(calculate_factorial(4), Integer::from(24u64));
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
}
