use std::io::{self, Write};

/// Generate all perfect squares with at most max_digits decimal digits,
/// writing one square per line to `out`. Returns the total count.
pub fn generate_squares<W: Write>(max_digits: u32, out: &mut W) -> io::Result<u64> {
    let limit: u64 = 10u64.pow(max_digits);
    let mut k: u64 = 1;
    let mut count: u64 = 0;
    while let Some(sq) = k.checked_mul(k).filter(|&sq| sq < limit) {
        writeln!(out, "{} | {}", sq, k)?;
        count += 1;
        k += 1;
    }
    Ok(count)
}
