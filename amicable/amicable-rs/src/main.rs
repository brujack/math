use std::io::{self, Write};
use std::path::Path;
use std::process;

#[allow(dead_code)]
fn proper_divisor_sum_sieve(limit: usize) -> Vec<u32> {
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

#[allow(dead_code)]
fn run<W: Write, E: Write>(
    _stdout: &mut W,
    _stderr: &mut E,
    _out_path: &Path,
    _limit: usize,
) -> io::Result<()> {
    Ok(())
}

#[cfg(not(tarpaulin_include))]
fn main() {
    if let Err(e) =
        run(&mut io::stdout().lock(), &mut io::stderr().lock(), Path::new("amicable_1e0.txt"), 0)
    {
        eprintln!("error: {e}");
        process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use crate::proper_divisor_sum_sieve;

    #[test]
    fn sieve_zero_and_one() {
        let s = proper_divisor_sum_sieve(6);
        assert_eq!(s[0], 0);
        assert_eq!(s[1], 0);
    }

    #[test]
    fn sieve_small_values() {
        let s = proper_divisor_sum_sieve(10);
        assert_eq!(s[2], 1);
        assert_eq!(s[4], 3);
        assert_eq!(s[6], 6);
        assert_eq!(s[10], 8);
    }

    #[test]
    fn sieve_amicable_values() {
        let s = proper_divisor_sum_sieve(285);
        assert_eq!(s[220], 284);
        assert_eq!(s[284], 220);
    }

    #[test]
    fn sieve_length() {
        let s = proper_divisor_sum_sieve(10);
        assert_eq!(s.len(), 11);
    }
}
