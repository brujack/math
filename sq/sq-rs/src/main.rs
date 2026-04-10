use std::io::{self, BufRead, Write};

use clap::Parser;

#[derive(Parser)]
#[command(
    name = "sq",
    about = "Generate all perfect squares with up to 10^N digits",
    long_about = "Generate all perfect squares whose decimal digit count is at most 10^N.\n\n\
                  Run without arguments for interactive prompts."
)]
struct Cli {
    /// N: generates perfect squares with up to 10^N digits (max 1)
    exponent: Option<u32>,
}

fn generate_squares<W: Write>(_max_digits: u32, _out: &mut W) -> io::Result<u64> {
    Ok(0)
}

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

fn read_line() -> String {
    let stdin = io::stdin();
    let mut line = String::new();
    stdin.lock().read_line(&mut line).unwrap();
    line.trim().to_string()
}

fn prompt_exponent() -> u32 {
    1
}

fn main() {}

#[cfg(test)]
mod tests {
    use super::*;

    // --- fmt_int ---

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
    }

    #[test]
    fn test_fmt_int_millions() {
        assert_eq!(fmt_int(1_234_567), "1,234,567");
    }
}
