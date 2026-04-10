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

/// Generate all perfect squares with at most max_digits decimal digits,
/// writing one square per line to `out`. Returns the total count.
///
/// Uses k*k < 10^max_digits as the stopping criterion. All values fit
/// in u64 for max_digits ≤ 10 (the maximum supported input).
fn generate_squares<W: Write>(max_digits: u32, out: &mut W) -> io::Result<u64> {
    let limit: u64 = 10u64.pow(max_digits);
    let mut k: u64 = 1;
    let mut count: u64 = 0;
    while let Some(sq) = k.checked_mul(k) {
        if sq >= limit {
            break;
        }
        writeln!(out, "{} | {}", sq, k)?;
        count += 1;
        k += 1;
    }
    Ok(count)
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
    loop {
        print!("Enter N (finds all perfect squares with up to 10^N digits, max 1): ");
        io::stdout().flush().unwrap();
        match read_line().parse::<u32>() {
            Ok(1) => return 1,
            Ok(_) => eprintln!("N must be 1."),
            _ => eprintln!("Please enter a positive integer."),
        }
    }
}

fn main() {
    let cli = Cli::parse();

    let exponent = match cli.exponent {
        Some(n) => {
            if n != 1 {
                eprintln!("Error: N must be 1.");
                std::process::exit(1);
            }
            n
        }
        None => prompt_exponent(),
    };

    let max_digits: u32 = 10u32.pow(exponent); // 10^1 = 10

    println!("Perfect Square Generator (Rust)");
    println!("{}", "=".repeat(40));
    println!(
        "Generating all perfect squares with up to 10^{} = {} digits",
        exponent,
        fmt_int(u64::from(max_digits))
    );

    let mut buf: Vec<u8> = Vec::new();
    let count = generate_squares(max_digits, &mut buf).expect("generation error");

    let filename = format!("sq_1e{}.txt", exponent);
    std::fs::write(&filename, &buf).expect("file write failed");

    println!("\nFound {} perfect squares with up to 10^{} digits", fmt_int(count), exponent);
    println!("Saved to {}", filename);
    print!("Also display all {} perfect squares? (y/n): ", fmt_int(count));
    io::stdout().flush().unwrap();
    if matches!(read_line().as_str(), "y" | "yes") {
        io::stdout().write_all(&buf).unwrap();
    }
}

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

    // --- FailWriter helper ---

    struct FailWriter;
    impl Write for FailWriter {
        fn write(&mut self, _buf: &[u8]) -> io::Result<usize> {
            Err(io::Error::new(io::ErrorKind::Other, "write failed"))
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    // --- generate_squares ---

    #[test]
    fn test_zero_max_digits_empty() {
        // max_digits=0: limit=1, k=1, k*k=1 >= 1 → yields nothing
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_squares(0, &mut buf).unwrap();
        assert_eq!(count, 0);
        assert!(buf.is_empty());
    }

    #[test]
    fn test_one_digit_squares() {
        // max_digits=1: limit=10, yields "1 | 1", "4 | 2", "9 | 3"
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_squares(1, &mut buf).unwrap();
        assert_eq!(count, 3);
        assert_eq!(String::from_utf8(buf).unwrap(), "1 | 1\n4 | 2\n9 | 3\n");
    }

    #[test]
    fn test_two_digit_count() {
        // max_digits=2: limit=100, k=1..9 → 9 squares
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_squares(2, &mut buf).unwrap();
        assert_eq!(count, 9);
    }

    #[test]
    fn test_two_digit_last_value() {
        let mut buf: Vec<u8> = Vec::new();
        generate_squares(2, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        assert_eq!(output.lines().last().unwrap(), "81 | 9");
    }

    #[test]
    fn test_two_digit_excludes_100() {
        let mut buf: Vec<u8> = Vec::new();
        generate_squares(2, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        assert!(!output.lines().any(|l| l.starts_with("100 |")));
    }

    #[test]
    fn test_each_is_perfect_square() {
        let mut buf: Vec<u8> = Vec::new();
        generate_squares(3, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        for line in output.lines() {
            let mut parts = line.split(" | ");
            let sq: u64 = parts.next().unwrap().parse().unwrap();
            let root: u64 = parts.next().unwrap().parse().unwrap();
            assert_eq!(root * root, sq, "{sq} is not a perfect square");
        }
    }

    #[test]
    fn test_strictly_increasing() {
        let mut buf: Vec<u8> = Vec::new();
        generate_squares(3, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        let nums: Vec<u64> = output
            .lines()
            .map(|l| l.split(" | ").next().unwrap().parse().unwrap())
            .collect();
        for i in 1..nums.len() {
            assert!(nums[i] > nums[i - 1]);
        }
    }

    #[test]
    fn test_ten_digit_count() {
        // max_digits=10: k=1..99999 → exactly 99,999 squares
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_squares(10, &mut buf).unwrap();
        assert_eq!(count, 99_999);
    }

    #[test]
    fn test_ten_digit_last_value() {
        let mut buf: Vec<u8> = Vec::new();
        generate_squares(10, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        assert_eq!(output.lines().last().unwrap(), "9999800001 | 99999");
    }

    #[test]
    fn test_ten_digit_excludes_100000_squared() {
        let mut buf: Vec<u8> = Vec::new();
        generate_squares(10, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        assert!(!output.lines().any(|l| l.starts_with("10000000000 |")));
    }

    #[test]
    fn test_write_error_propagates() {
        let result = generate_squares(1, &mut FailWriter);
        assert!(result.is_err());
    }

    #[test]
    fn test_idempotent_same_input() {
        let mut buf1: Vec<u8> = Vec::new();
        generate_squares(2, &mut buf1).unwrap();
        let mut buf2: Vec<u8> = Vec::new();
        generate_squares(2, &mut buf2).unwrap();
        assert_eq!(buf1, buf2);
    }
}
