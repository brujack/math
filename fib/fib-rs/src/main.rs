use std::fs::File;
use std::io::{self, BufRead, BufWriter, Write};
use std::path::{Path, PathBuf};
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
fn generate_fibonacci<W: Write>(max_digits: usize, out: &mut W) -> io::Result<u64> {
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

fn read_line_from<R: BufRead>(reader: &mut R) -> io::Result<String> {
    let mut line = String::new();
    reader.read_line(&mut line)?;
    Ok(line.trim().to_string())
}

fn prompt_exponent_with<R: BufRead, W: Write, E: Write>(
    reader: &mut R,
    out: &mut W,
    err: &mut E,
) -> io::Result<u32> {
    loop {
        write!(out, "Enter X (finds all Fibonacci numbers with up to 10^X digits, max 5): ")?;
        out.flush()?;
        match read_line_from(reader)?.parse::<u32>() {
            Ok(x) if (1..=5).contains(&x) => return Ok(x),
            Ok(_) => writeln!(err, "X must be between 1 and 5.")?,
            _ => writeln!(err, "Please enter a positive integer.")?,
        }
    }
}

fn confirm_large_n_with<R: BufRead, W: Write, E: Write>(
    reader: &mut R,
    out: &mut W,
    err: &mut E,
    exponent: u32,
    max_digits: usize,
) -> io::Result<bool> {
    writeln!(err, "Warning: X={} means Fibonacci numbers with up to {} digits — this may take a long time", exponent, fmt_int(max_digits as u64))?;
    writeln!(err, "         and produce a very large output file.")?;
    write!(out, "Continue? (y/n): ")?;
    out.flush()?;
    Ok(matches!(read_line_from(reader)?.as_str(), "y" | "yes"))
}

fn write_fib_file(dir: &Path, exponent: u32, buf: &[u8]) -> io::Result<PathBuf> {
    let path = dir.join(format!("fib_1e{}.txt", exponent));
    std::fs::write(&path, buf)?;
    Ok(path)
}

fn stream_fib_to_file(dir: &Path, exponent: u32, max_digits: usize) -> io::Result<(PathBuf, u64)> {
    let path = dir.join(format!("fib_1e{}.txt", exponent));
    let file = File::create(&path)?;
    let mut writer = BufWriter::with_capacity(8 * 1024 * 1024, file);
    let count = generate_fibonacci(max_digits, &mut writer)?;
    writer.flush()?;
    Ok((path, count))
}

fn run<R: BufRead, W: Write, E: Write>(
    cli: Cli,
    reader: &mut R,
    out: &mut W,
    err: &mut E,
    dir: &Path,
) -> io::Result<i32> {
    writeln!(out, "Fibonacci Number Generator (Rust/GMP)")?;
    writeln!(out, "{}", "=".repeat(40))?;

    let exponent = match cli.exponent {
        Some(x) => {
            if !(1..=5).contains(&x) {
                writeln!(err, "Error: X must be between 1 and 5.")?;
                return Ok(1);
            }
            x
        }
        None => prompt_exponent_with(reader, out, err)?,
    };

    let max_digits = 10usize.pow(exponent);

    if exponent >= 4 && !confirm_large_n_with(reader, out, err, exponent, max_digits)? {
        return Ok(0);
    }

    writeln!(out, "Generating all Fibonacci numbers with up to 10^{} = {} digits", exponent, fmt_int(max_digits as u64))?;

    let t_total = Instant::now();

    if exponent <= 2 {
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_fibonacci(max_digits, &mut buf)?;

        writeln!(out, "\nFound {} Fibonacci numbers with up to 10^{} digits", fmt_int(count), exponent)?;
        write!(out, "Display all {} Fibonacci numbers? (y/n): ", fmt_int(count))?;
        out.flush()?;
        if matches!(read_line_from(reader)?.as_str(), "y" | "yes") {
            out.write_all(&buf)?;
        } else {
            let path = write_fib_file(dir, exponent, &buf)?;
            writeln!(out, "Saved to {}", path.display())?;
        }
    } else {
        let preview_path = dir.join(format!("fib_1e{}.txt", exponent));
        writeln!(out, "\nSaving to {}...", preview_path.display())?;
        let (path, count) = stream_fib_to_file(dir, exponent, max_digits)?;

        writeln!(out, "Found {} Fibonacci numbers with up to 10^{} digits", fmt_int(count), exponent)?;
        writeln!(out, "Saved to {}", path.display())?;
    }

    writeln!(out, "Total time: {:.2}s", t_total.elapsed().as_secs_f64())?;
    Ok(0)
}

#[cfg(not(tarpaulin_include))]
fn main() {
    let cli = Cli::parse();
    let stdin = io::stdin();
    let stdout = io::stdout();
    let stderr = io::stderr();
    let mut reader = stdin.lock();
    let mut out = stdout.lock();
    let mut err = stderr.lock();
    let cwd = std::env::current_dir().expect("cwd unavailable");
    let code = run(cli, &mut reader, &mut out, &mut err, &cwd).expect("io error");
    std::process::exit(code);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;
    use tempfile::tempdir;

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
            Err(io::Error::other("write failed"))
        }
        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    // --- generate_fibonacci ---

    #[test]
    fn test_single_digit_sequence() {
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_fibonacci(1, &mut buf).unwrap();
        assert_eq!(count, 6);
        assert_eq!(String::from_utf8(buf).unwrap(), "1\n1\n2\n3\n5\n8\n");
    }

    #[test]
    fn test_two_digit_count() {
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
        let mut buf: Vec<u8> = Vec::new();
        generate_fibonacci(2, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
        let nums: Vec<u64> = output
            .lines()
            .take(10)
            .map(|l| l.parse().unwrap())
            .collect();
        assert_eq!(nums, vec![1, 1, 2, 3, 5, 8, 13, 21, 34, 55]);
    }

    #[test]
    fn test_each_is_sum_of_previous_two() {
        let mut buf: Vec<u8> = Vec::new();
        generate_fibonacci(3, &mut buf).unwrap();
        let output = String::from_utf8(buf).unwrap();
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
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_fibonacci(0, &mut buf).unwrap();
        assert_eq!(count, 0);
        assert!(buf.is_empty());
    }

    #[test]
    fn test_write_error_propagates() {
        let result = generate_fibonacci(1, &mut FailWriter);
        assert!(result.is_err());
    }

    #[test]
    fn test_idempotent_same_input() {
        let mut buf1: Vec<u8> = Vec::new();
        generate_fibonacci(2, &mut buf1).unwrap();
        let mut buf2: Vec<u8> = Vec::new();
        generate_fibonacci(2, &mut buf2).unwrap();
        assert_eq!(buf1, buf2);
    }

    // --- read_line_from ---

    #[test]
    fn test_read_line_from_trims_newline() {
        let mut input = Cursor::new(b"hello\n");
        assert_eq!(read_line_from(&mut input).unwrap(), "hello");
    }

    #[test]
    fn test_read_line_from_trims_whitespace() {
        let mut input = Cursor::new(b"  spaced  \n");
        assert_eq!(read_line_from(&mut input).unwrap(), "spaced");
    }

    #[test]
    fn test_read_line_from_empty_eof() {
        let mut input = Cursor::new(b"");
        assert_eq!(read_line_from(&mut input).unwrap(), "");
    }

    #[test]
    fn test_read_line_from_only_first_line() {
        let mut input = Cursor::new(b"first\nsecond\n");
        assert_eq!(read_line_from(&mut input).unwrap(), "first");
    }

    // --- prompt_exponent_with ---

    #[test]
    fn test_prompt_exponent_accepts_low_boundary() {
        let mut input = Cursor::new(b"1\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        assert_eq!(
            prompt_exponent_with(&mut input, &mut out, &mut err).unwrap(),
            1
        );
        assert!(err.is_empty());
    }

    #[test]
    fn test_prompt_exponent_accepts_high_boundary() {
        let mut input = Cursor::new(b"5\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        assert_eq!(
            prompt_exponent_with(&mut input, &mut out, &mut err).unwrap(),
            5
        );
    }

    #[test]
    fn test_prompt_exponent_retries_on_zero() {
        let mut input = Cursor::new(b"0\n3\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        assert_eq!(
            prompt_exponent_with(&mut input, &mut out, &mut err).unwrap(),
            3
        );
        assert!(String::from_utf8(err).unwrap().contains("between 1 and 5"));
    }

    #[test]
    fn test_prompt_exponent_retries_on_too_high() {
        let mut input = Cursor::new(b"6\n2\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        assert_eq!(
            prompt_exponent_with(&mut input, &mut out, &mut err).unwrap(),
            2
        );
        assert!(String::from_utf8(err).unwrap().contains("between 1 and 5"));
    }

    #[test]
    fn test_prompt_exponent_retries_on_non_integer() {
        let mut input = Cursor::new(b"abc\n1\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        assert_eq!(
            prompt_exponent_with(&mut input, &mut out, &mut err).unwrap(),
            1
        );
        assert!(String::from_utf8(err).unwrap().contains("positive integer"));
    }

    #[test]
    fn test_prompt_exponent_retries_on_negative() {
        let mut input = Cursor::new(b"-1\n2\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        assert_eq!(
            prompt_exponent_with(&mut input, &mut out, &mut err).unwrap(),
            2
        );
        assert!(String::from_utf8(err).unwrap().contains("positive integer"));
    }

    // --- confirm_large_n_with ---

    #[test]
    fn test_confirm_large_n_yes() {
        let mut input = Cursor::new(b"y\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        assert!(confirm_large_n_with(&mut input, &mut out, &mut err, 4, 10_000).unwrap());
        assert!(String::from_utf8(err).unwrap().contains("Warning"));
    }

    #[test]
    fn test_confirm_large_n_yes_alias() {
        let mut input = Cursor::new(b"yes\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        assert!(confirm_large_n_with(&mut input, &mut out, &mut err, 4, 10_000).unwrap());
    }

    #[test]
    fn test_confirm_large_n_no() {
        let mut input = Cursor::new(b"n\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        assert!(!confirm_large_n_with(&mut input, &mut out, &mut err, 4, 10_000).unwrap());
    }

    #[test]
    fn test_confirm_large_n_blank_treated_as_no() {
        let mut input = Cursor::new(b"\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        assert!(!confirm_large_n_with(&mut input, &mut out, &mut err, 4, 10_000).unwrap());
    }

    // --- write_fib_file ---

    #[test]
    fn test_write_fib_file_creates_file() {
        let dir = tempdir().unwrap();
        let path = write_fib_file(dir.path(), 1, b"hello").unwrap();
        assert!(path.exists());
        assert_eq!(path.file_name().unwrap(), "fib_1e1.txt");
        assert_eq!(std::fs::read(&path).unwrap(), b"hello");
    }

    #[test]
    fn test_write_fib_file_overwrites() {
        let dir = tempdir().unwrap();
        write_fib_file(dir.path(), 1, b"first").unwrap();
        let path = write_fib_file(dir.path(), 1, b"second").unwrap();
        assert_eq!(std::fs::read(&path).unwrap(), b"second");
    }

    #[test]
    fn test_write_fib_file_uses_exponent_in_name() {
        let dir = tempdir().unwrap();
        let path = write_fib_file(dir.path(), 2, b"x").unwrap();
        assert_eq!(path.file_name().unwrap(), "fib_1e2.txt");
    }

    #[test]
    fn test_write_fib_file_returns_err_on_bad_dir() {
        let dir = tempdir().unwrap();
        let bad = dir.path().join("does/not/exist");
        assert!(write_fib_file(&bad, 1, b"x").is_err());
    }

    // --- stream_fib_to_file ---

    #[test]
    fn test_stream_fib_to_file_writes_all_values() {
        let dir = tempdir().unwrap();
        let (path, count) = stream_fib_to_file(dir.path(), 3, 1).unwrap();
        assert!(path.exists());
        assert_eq!(path.file_name().unwrap(), "fib_1e3.txt");
        assert_eq!(count, 6);
        let contents = std::fs::read_to_string(&path).unwrap();
        assert_eq!(contents, "1\n1\n2\n3\n5\n8\n");
    }

    #[test]
    fn test_stream_fib_to_file_returns_err_on_bad_dir() {
        let dir = tempdir().unwrap();
        let bad = dir.path().join("missing/sub");
        assert!(stream_fib_to_file(&bad, 3, 1).is_err());
    }

    // --- run ---

    #[test]
    fn test_run_arg_out_of_range_zero_returns_one() {
        let dir = tempdir().unwrap();
        let cli = Cli { exponent: Some(0) };
        let mut input = Cursor::new(b"");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        let code = run(cli, &mut input, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 1);
        assert!(String::from_utf8(err)
            .unwrap()
            .contains("X must be between 1 and 5"));
    }

    #[test]
    fn test_run_arg_out_of_range_six_returns_one() {
        let dir = tempdir().unwrap();
        let cli = Cli { exponent: Some(6) };
        let mut input = Cursor::new(b"");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        let code = run(cli, &mut input, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 1);
    }

    #[test]
    fn test_run_x_one_save_branch() {
        let dir = tempdir().unwrap();
        let cli = Cli { exponent: Some(1) };
        let mut input = Cursor::new(b"n\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        let code = run(cli, &mut input, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        let path = dir.path().join("fib_1e1.txt");
        assert!(path.exists());
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("Saved to"));
        assert!(!stdout.contains("\n8\n"));
    }

    #[test]
    fn test_run_x_one_display_branch() {
        let dir = tempdir().unwrap();
        let cli = Cli { exponent: Some(1) };
        let mut input = Cursor::new(b"y\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        run(cli, &mut input, &mut out, &mut err, dir.path()).unwrap();
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("\n8\n"));
        assert!(!dir.path().join("fib_1e1.txt").exists());
    }

    #[test]
    fn test_run_x_two_yes_alias_displays() {
        let dir = tempdir().unwrap();
        let cli = Cli { exponent: Some(2) };
        let mut input = Cursor::new(b"yes\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        run(cli, &mut input, &mut out, &mut err, dir.path()).unwrap();
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("\n89\n"));
    }

    #[test]
    fn test_run_x_three_streams() {
        let dir = tempdir().unwrap();
        let cli = Cli { exponent: Some(3) };
        let mut input = Cursor::new(b"");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        let code = run(cli, &mut input, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        let path = dir.path().join("fib_1e3.txt");
        assert!(path.exists());
        let contents = std::fs::read_to_string(&path).unwrap();
        let lines: Vec<&str> = contents.lines().collect();
        assert!(lines.len() > 100);
        for line in lines.iter().take(5) {
            assert!(!line.is_empty());
        }
    }

    #[test]
    fn test_run_x_four_warning_aborts_on_n() {
        let dir = tempdir().unwrap();
        let cli = Cli { exponent: Some(4) };
        let mut input = Cursor::new(b"n\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        let code = run(cli, &mut input, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        assert!(!dir.path().join("fib_1e4.txt").exists());
        assert!(String::from_utf8(err).unwrap().contains("Warning"));
    }

    #[test]
    fn test_run_x_four_warning_aborts_on_blank() {
        let dir = tempdir().unwrap();
        let cli = Cli { exponent: Some(4) };
        let mut input = Cursor::new(b"\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        run(cli, &mut input, &mut out, &mut err, dir.path()).unwrap();
        assert!(!dir.path().join("fib_1e4.txt").exists());
    }

    #[test]
    fn test_run_no_arg_prompts_then_succeeds() {
        let dir = tempdir().unwrap();
        let cli = Cli { exponent: None };
        let mut input = Cursor::new(b"1\nn\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        let code = run(cli, &mut input, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        assert!(dir.path().join("fib_1e1.txt").exists());
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("Enter X"));
    }

    #[test]
    fn test_run_idempotent_save_branch() {
        let dir = tempdir().unwrap();
        let mut out1: Vec<u8> = Vec::new();
        let mut out2: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        let mut input1 = Cursor::new(b"n\n");
        let mut input2 = Cursor::new(b"n\n");
        run(
            Cli { exponent: Some(1) },
            &mut input1,
            &mut out1,
            &mut err,
            dir.path(),
        )
        .unwrap();
        let first = std::fs::read(dir.path().join("fib_1e1.txt")).unwrap();
        run(
            Cli { exponent: Some(1) },
            &mut input2,
            &mut out2,
            &mut err,
            dir.path(),
        )
        .unwrap();
        let second = std::fs::read(dir.path().join("fib_1e1.txt")).unwrap();
        assert_eq!(first, second);
    }
}
