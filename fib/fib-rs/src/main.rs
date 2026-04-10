use std::io::{self, BufRead, BufWriter, Write};
use std::fs::File;
use std::time::Instant;

use clap::Parser;
use rug::ops::PowAssign;
use rug::Integer;

#[derive(Parser)]
#[command(
    name = "fib",
    about = "Generate all Fibonacci numbers with up to 10^X digits",
    long_about = "Generate all Fibonacci numbers whose decimal digit count is at most 10^X.\n\n\
                  Run without arguments for interactive prompts."
)]
struct Cli {
    /// X: generates Fibonacci numbers with up to 10^X digits (e.g. 3 → up to 1,000 digits)
    exponent: Option<u32>,
}

/// Generate all Fibonacci numbers with at most max_digits decimal digits,
/// writing one number per line to `out`. Returns the total count.
///
/// Uses b < 10^max_digits as the stopping criterion. The limit is computed
/// once with GMP — cheaper than converting b to a decimal string each iteration.
fn generate_fibonacci<W: Write>(max_digits: usize, out: &mut W) -> io::Result<u64> {
    // limit = 10^max_digits; stop when b >= limit (b would have > max_digits digits)
    let mut limit = Integer::from(10u32);
    limit.pow_assign(max_digits as u32);

    let mut a = Integer::from(0u32);
    let mut b = Integer::from(1u32);
    let mut count = 0u64;

    while b < limit {
        writeln!(out, "{}", b)?;
        count += 1;
        // rug lazy arithmetic: wrap Integer::from() around incomplete expressions
        let next = Integer::from(&a + &b);
        a = b;
        b = next;
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
        print!("Enter X (finds all Fibonacci numbers with up to 10^X digits, max 5): ");
        io::stdout().flush().unwrap();
        match read_line().parse::<u32>() {
            Ok(x) if (1..=5).contains(&x) => return x,
            Ok(_) => eprintln!("X must be between 1 and 5."),
            _ => eprintln!("Please enter a positive integer."),
        }
    }
}

fn main() {
    let cli = Cli::parse();

    println!("Fibonacci Number Generator (Rust/GMP)");
    println!("{}", "=".repeat(40));

    let exponent = match cli.exponent {
        Some(x) => {
            if !(1..=5).contains(&x) {
                eprintln!("Error: X must be between 1 and 5.");
                std::process::exit(1);
            }
            x
        }
        None => prompt_exponent(),
    };

    let max_digits = 10usize.pow(exponent);

    if exponent >= 4 {
        eprintln!(
            "Warning: X={} means Fibonacci numbers with up to {} digits — this may take a long time",
            exponent,
            fmt_int(max_digits as u64)
        );
        eprintln!("         and produce a very large output file.");
        print!("Continue? (y/n): ");
        io::stdout().flush().unwrap();
        if !matches!(read_line().as_str(), "y" | "yes") {
            return;
        }
    }

    println!(
        "Generating all Fibonacci numbers with up to 10^{} = {} digits",
        exponent,
        fmt_int(max_digits as u64)
    );

    let t_total = Instant::now();

    if exponent <= 2 {
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_fibonacci(max_digits, &mut buf).expect("generation error");

        println!(
            "\nFound {} Fibonacci numbers with up to 10^{} digits",
            fmt_int(count),
            exponent
        );
        print!("Display all {} Fibonacci numbers? (y/n): ", fmt_int(count));
        io::stdout().flush().unwrap();
        if matches!(read_line().as_str(), "y" | "yes") {
            io::stdout().write_all(&buf).unwrap();
        } else {
            let filename = format!("fib_1e{}.txt", exponent);
            std::fs::write(&filename, &buf).expect("file write failed");
            println!("Saved to {}", filename);
        }
    } else {
        let filename = format!("fib_1e{}.txt", exponent);
        println!("\nSaving to {}...", filename);
        let file = File::create(&filename).expect("cannot create output file");
        let mut writer = BufWriter::with_capacity(8 * 1024 * 1024, file);
        let count = generate_fibonacci(max_digits, &mut writer).expect("generation error");
        writer.flush().expect("flush error");

        println!(
            "Found {} Fibonacci numbers with up to 10^{} digits",
            fmt_int(count),
            exponent
        );
        println!("Saved to {}", filename);
    }

    println!("Total time: {:.2}s", t_total.elapsed().as_secs_f64());
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

    // --- generate_fibonacci ---

    #[test]
    fn test_single_digit_sequence() {
        // max_digits=1, limit=10: yields 1,1,2,3,5,8 then 13 >= 10 stops
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_fibonacci(1, &mut buf).unwrap();
        assert_eq!(count, 6);
        assert_eq!(String::from_utf8(buf).unwrap(), "1\n1\n2\n3\n5\n8\n");
    }

    #[test]
    fn test_two_digit_count() {
        // max_digits=2, limit=100: 11 numbers ending at 89, then 144 >= 100 stops
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_fibonacci(2, &mut buf).unwrap();
        assert_eq!(count, 11);
    }

    #[test]
    fn test_two_digit_last_value() {
        let mut buf: Vec<u8> = Vec::new();
        generate_fibonacci(2, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        assert_eq!(output.lines().last().unwrap(), "89");
    }

    #[test]
    fn test_known_first_ten_values() {
        // F: 1,1,2,3,5,8,13,21,34,55,...
        let mut buf: Vec<u8> = Vec::new();
        generate_fibonacci(2, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        let nums: Vec<u64> = output.lines().take(10).map(|l| l.parse().unwrap()).collect();
        assert_eq!(nums, vec![1, 1, 2, 3, 5, 8, 13, 21, 34, 55]);
    }

    #[test]
    fn test_each_is_sum_of_previous_two() {
        let mut buf: Vec<u8> = Vec::new();
        generate_fibonacci(3, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        // 3-digit numbers are small enough to parse as u64
        let nums: Vec<u64> = output.lines().map(|l| l.parse().unwrap()).collect();
        for i in 2..nums.len() {
            assert_eq!(nums[i], nums[i - 1] + nums[i - 2]);
        }
    }

    #[test]
    fn test_all_positive() {
        let mut buf: Vec<u8> = Vec::new();
        generate_fibonacci(2, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        for line in output.lines() {
            let n: u64 = line.parse().unwrap();
            assert!(n > 0);
        }
    }

    #[test]
    fn test_zero_max_digits_empty() {
        // max_digits=0: limit=10^0=1, b=1, 1<1 is false → yields nothing
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_fibonacci(0, &mut buf).unwrap();
        assert_eq!(count, 0);
        assert!(buf.is_empty());
    }

    #[test]
    fn test_write_error_propagates() {
        // A writer that always fails; generate_fibonacci must surface the error.
        let result = generate_fibonacci(1, &mut FailWriter);
        assert!(result.is_err());
    }
}
