pub fn proper_divisor_sum_sieve(limit: usize) -> Vec<u32> {
    let mut s = vec![0u32; limit + 1];
    for d in 1..=(limit / 2) {
        let mut m = 2 * d;
        while m <= limit {
            s[m] += d as u32;
            m += d;
        }
    }
    s
}
