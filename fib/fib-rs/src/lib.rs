use std::io::{self, Write};

use rug::ops::PowAssign;
use rug::Integer;

/// Generate all Fibonacci numbers with at most max_digits decimal digits,
/// writing one number per line to `out`. Returns the total count.
pub fn generate_fibonacci<W: Write>(max_digits: usize, out: &mut W) -> io::Result<u64> {
    let mut limit = Integer::from(10u32);
    limit.pow_assign(max_digits as u32);

    let mut a = Integer::from(0u32);
    let mut b = Integer::from(1u32);
    let mut count = 0u64;

    while b < limit {
        writeln!(out, "{}", b)?;
        count += 1;
        let next = Integer::from(&a + &b);
        a = b;
        b = next;
    }

    Ok(count)
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
