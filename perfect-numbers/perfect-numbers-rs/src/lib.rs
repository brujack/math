use rug::Integer;

pub fn is_prime(n: u64) -> bool {
    if n < 2 {
        return false;
    }
    if n == 2 {
        return true;
    }
    if n.is_multiple_of(2) {
        return false;
    }
    let mut i = 3u64;
    while i * i <= n {
        if n.is_multiple_of(i) {
            return false;
        }
        i += 2;
    }
    true
}

pub fn lucas_lehmer(p: u64) -> bool {
    if p == 2 {
        return true;
    }
    let mut mp = Integer::from(1u32);
    mp <<= p as u32;
    mp -= 1u32;

    let mut s = Integer::from(4u32);
    for _ in 0..(p - 2) {
        s.square_mut();
        s -= 2i32;
        s %= &mp;
        if s < 0i32 {
            s += &mp;
        }
    }
    s == 0u32
}

pub fn verify_perfect(p: u64) -> bool {
    let mut mp = Integer::from(1u32);
    mp <<= p as u32;
    mp -= 1u32;

    let mut n = Integer::from(1u32);
    n <<= (p - 1) as u32;
    n *= &mp;

    // sigma(n) = mp * (mp + 1) = (2^p - 1) * 2^p
    let sigma = &mp * Integer::from(&mp + 1u32);
    sigma == n << 1u32
}

pub fn generate_perfect_numbers(limit: &Integer) -> Vec<(u64, Integer)> {
    let mut results = Vec::new();
    if limit < &Integer::from(6u32) {
        return results;
    }
    let max_p = (limit.significant_bits() as u64 / 2) + 3;
    for p in 2..=max_p {
        if !is_prime(p) {
            continue;
        }
        if !lucas_lehmer(p) {
            continue;
        }
        let mut mp = Integer::from(1u32);
        mp <<= p as u32;
        mp -= 1u32;
        let mut pn = Integer::from(1u32);
        pn <<= (p - 1) as u32;
        pn *= &mp;
        if &pn > limit {
            break;
        }
        results.push((p, pn));
    }
    results
}
