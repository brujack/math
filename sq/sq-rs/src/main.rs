use std::io::{self, BufRead, Write};
use std::path::{Path, PathBuf};

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
fn generate_squares<W: Write>(max_digits: u32, out: &mut W) -> io::Result<u64> {
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
        write!(out, "Enter N (finds all perfect squares with up to 10^N digits, max 1): ")?;
        out.flush()?;
        match read_line_from(reader)?.parse::<u32>() {
            Ok(1) => return Ok(1),
            Ok(_) => writeln!(err, "N must be 1.")?,
            _ => writeln!(err, "Please enter a positive integer.")?,
        }
    }
}

fn write_squares_file(dir: &Path, exponent: u32, buf: &[u8]) -> io::Result<PathBuf> {
    let path = dir.join(format!("sq_1e{}.txt", exponent));
    std::fs::write(&path, buf)?;
    Ok(path)
}

fn run<R: BufRead, W: Write, E: Write>(
    cli: Cli,
    reader: &mut R,
    out: &mut W,
    err: &mut E,
    dir: &Path,
) -> io::Result<i32> {
    let exponent = match cli.exponent {
        Some(n) => {
            if n != 1 {
                writeln!(err, "Error: N must be 1.")?;
                return Ok(1);
            }
            n
        }
        None => prompt_exponent_with(reader, out, err)?,
    };

    let max_digits: u32 = 10u32.pow(exponent);

    writeln!(out, "Perfect Square Generator (Rust)")?;
    writeln!(out, "{}", "=".repeat(40))?;
    writeln!(
        out,
        "Generating all perfect squares with up to 10^{} = {} digits",
        exponent,
        fmt_int(u64::from(max_digits))
    )?;

    let mut buf: Vec<u8> = Vec::new();
    let count = generate_squares(max_digits, &mut buf)?;

    let path = write_squares_file(dir, exponent, &buf)?;

    writeln!(out, "\nFound {} perfect squares with up to 10^{} digits", fmt_int(count), exponent)?;
    writeln!(out, "Saved to {}", path.display())?;
    write!(out, "Also display all {} perfect squares? (y/n): ", fmt_int(count))?;
    out.flush()?;
    if matches!(read_line_from(reader)?.as_str(), "y" | "yes") {
        out.write_all(&buf)?;
    }
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
    use proptest::prelude::*;
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

    // --- generate_squares ---

    #[test]
    fn test_zero_max_digits_empty() {
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_squares(0, &mut buf).unwrap();
        assert_eq!(count, 0);
        assert!(buf.is_empty());
    }

    #[test]
    fn test_one_digit_squares() {
        let mut buf: Vec<u8> = Vec::new();
        let count = generate_squares(1, &mut buf).unwrap();
        assert_eq!(count, 3);
        assert_eq!(String::from_utf8(buf).unwrap(), "1 | 1\n4 | 2\n9 | 3\n");
    }

    #[test]
    fn test_two_digit_count() {
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
        let nums: Vec<u64> =
            output.lines().map(|l| l.split(" | ").next().unwrap().parse().unwrap()).collect();
        for i in 1..nums.len() {
            assert!(nums[i] > nums[i - 1]);
        }
    }

    #[test]
    fn test_ten_digit_count() {
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

    // --- read_line_from ---

    #[test]
    fn test_read_line_from_trims_newline() {
        let mut input = Cursor::new(b"hello\n");
        let line = read_line_from(&mut input).unwrap();
        assert_eq!(line, "hello");
    }

    #[test]
    fn test_read_line_from_trims_whitespace() {
        let mut input = Cursor::new(b"  spaced  \n");
        let line = read_line_from(&mut input).unwrap();
        assert_eq!(line, "spaced");
    }

    #[test]
    fn test_read_line_from_empty_eof() {
        let mut input = Cursor::new(b"");
        let line = read_line_from(&mut input).unwrap();
        assert_eq!(line, "");
    }

    #[test]
    fn test_read_line_from_only_first_line() {
        let mut input = Cursor::new(b"first\nsecond\n");
        let line = read_line_from(&mut input).unwrap();
        assert_eq!(line, "first");
    }

    // --- prompt_exponent_with ---

    #[test]
    fn test_prompt_exponent_accepts_one() {
        let mut input = Cursor::new(b"1\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        let n = prompt_exponent_with(&mut input, &mut out, &mut err).unwrap();
        assert_eq!(n, 1);
        assert!(err.is_empty());
        assert!(String::from_utf8(out).unwrap().contains("Enter N"));
    }

    #[test]
    fn test_prompt_exponent_retries_on_zero() {
        let mut input = Cursor::new(b"0\n1\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        let n = prompt_exponent_with(&mut input, &mut out, &mut err).unwrap();
        assert_eq!(n, 1);
        assert!(String::from_utf8(err).unwrap().contains("N must be 1."));
    }

    #[test]
    fn test_prompt_exponent_retries_on_too_high() {
        let mut input = Cursor::new(b"5\n1\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        let n = prompt_exponent_with(&mut input, &mut out, &mut err).unwrap();
        assert_eq!(n, 1);
        assert!(String::from_utf8(err).unwrap().contains("N must be 1."));
    }

    #[test]
    fn test_prompt_exponent_retries_on_non_integer() {
        let mut input = Cursor::new(b"abc\n1\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        let n = prompt_exponent_with(&mut input, &mut out, &mut err).unwrap();
        assert_eq!(n, 1);
        assert!(String::from_utf8(err).unwrap().contains("Please enter a positive integer."));
    }

    #[test]
    fn test_prompt_exponent_retries_on_negative() {
        let mut input = Cursor::new(b"-1\n1\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        let n = prompt_exponent_with(&mut input, &mut out, &mut err).unwrap();
        assert_eq!(n, 1);
        assert!(String::from_utf8(err).unwrap().contains("Please enter a positive integer."));
    }

    // --- write_squares_file ---

    #[test]
    fn test_write_squares_file_creates_file() {
        let dir = tempdir().unwrap();
        let path = write_squares_file(dir.path(), 1, b"hello").unwrap();
        assert!(path.exists());
        assert_eq!(path.file_name().unwrap(), "sq_1e1.txt");
        assert_eq!(std::fs::read(&path).unwrap(), b"hello");
    }

    #[test]
    fn test_write_squares_file_overwrites() {
        let dir = tempdir().unwrap();
        write_squares_file(dir.path(), 1, b"first").unwrap();
        let path = write_squares_file(dir.path(), 1, b"second").unwrap();
        assert_eq!(std::fs::read(&path).unwrap(), b"second");
    }

    #[test]
    fn test_write_squares_file_uses_exponent_in_name() {
        let dir = tempdir().unwrap();
        let path = write_squares_file(dir.path(), 2, b"x").unwrap();
        assert_eq!(path.file_name().unwrap(), "sq_1e2.txt");
    }

    #[test]
    fn test_write_squares_file_returns_err_on_bad_dir() {
        let dir = tempdir().unwrap();
        let bad = dir.path().join("does/not/exist");
        let result = write_squares_file(&bad, 1, b"x");
        assert!(result.is_err());
    }

    // --- run ---

    #[test]
    fn test_run_with_arg_one_succeeds_and_writes_file() {
        let dir = tempdir().unwrap();
        let cli = Cli { exponent: Some(1) };
        let mut input = Cursor::new(b"n\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        let code = run(cli, &mut input, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 0);
        let path = dir.path().join("sq_1e1.txt");
        assert!(path.exists());
        let contents = std::fs::read_to_string(&path).unwrap();
        assert!(contents.contains("9999800001 | 99999"));
        assert!(err.is_empty());
    }

    #[test]
    fn test_run_with_arg_zero_returns_one() {
        let dir = tempdir().unwrap();
        let cli = Cli { exponent: Some(0) };
        let mut input = Cursor::new(b"");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        let code = run(cli, &mut input, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 1);
        assert!(String::from_utf8(err).unwrap().contains("Error: N must be 1."));
        assert!(!dir.path().join("sq_1e0.txt").exists());
    }

    #[test]
    fn test_run_with_arg_two_returns_one() {
        let dir = tempdir().unwrap();
        let cli = Cli { exponent: Some(2) };
        let mut input = Cursor::new(b"");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        let code = run(cli, &mut input, &mut out, &mut err, dir.path()).unwrap();
        assert_eq!(code, 1);
        assert!(String::from_utf8(err).unwrap().contains("Error: N must be 1."));
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
        let path = dir.path().join("sq_1e1.txt");
        assert!(path.exists());
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("Enter N"));
        assert!(stdout.contains("Saved to"));
    }

    #[test]
    fn test_run_yes_displays_buffer() {
        let dir = tempdir().unwrap();
        let cli = Cli { exponent: Some(1) };
        let mut input = Cursor::new(b"y\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        run(cli, &mut input, &mut out, &mut err, dir.path()).unwrap();
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("9999800001 | 99999"));
    }

    #[test]
    fn test_run_yes_alias() {
        let dir = tempdir().unwrap();
        let cli = Cli { exponent: Some(1) };
        let mut input = Cursor::new(b"yes\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        run(cli, &mut input, &mut out, &mut err, dir.path()).unwrap();
        let stdout = String::from_utf8(out).unwrap();
        assert!(stdout.contains("9999800001 | 99999"));
    }

    #[test]
    fn test_run_no_does_not_display_buffer() {
        let dir = tempdir().unwrap();
        let cli = Cli { exponent: Some(1) };
        let mut input = Cursor::new(b"n\n");
        let mut out: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        run(cli, &mut input, &mut out, &mut err, dir.path()).unwrap();
        let stdout = String::from_utf8(out).unwrap();
        assert!(!stdout.contains("9999800001 | 99999"));
        assert!(stdout.contains("Saved to"));
    }

    #[test]
    fn test_run_idempotent() {
        let dir = tempdir().unwrap();
        let cli1 = Cli { exponent: Some(1) };
        let cli2 = Cli { exponent: Some(1) };
        let mut input1 = Cursor::new(b"n\n");
        let mut input2 = Cursor::new(b"n\n");
        let mut out1: Vec<u8> = Vec::new();
        let mut out2: Vec<u8> = Vec::new();
        let mut err: Vec<u8> = Vec::new();
        run(cli1, &mut input1, &mut out1, &mut err, dir.path()).unwrap();
        let first = std::fs::read(dir.path().join("sq_1e1.txt")).unwrap();
        run(cli2, &mut input2, &mut out2, &mut err, dir.path()).unwrap();
        let second = std::fs::read(dir.path().join("sq_1e1.txt")).unwrap();
        assert_eq!(first, second);
    }

    #[test]
    fn run_returns_err_on_stdout_failure() {
        let dir = tempdir().unwrap();
        let mut err = Vec::new();
        let mut reader = std::io::Cursor::new("n\n");
        let cli = Cli { exponent: Some(1) };
        let result = run(cli, &mut reader, &mut FailWriter, &mut err, dir.path());
        assert!(result.is_err());
    }

    #[test]
    fn run_returns_err_on_stderr_failure() {
        // exponent=2 is invalid for sq (only 1 is valid)
        let dir = tempdir().unwrap();
        let mut out = Vec::new();
        let mut reader = std::io::Cursor::new("");
        let cli = Cli { exponent: Some(2) };
        let result = run(cli, &mut reader, &mut out, &mut FailWriter, dir.path());
        assert!(result.is_err());
    }

    proptest! {
        #[test]
        fn prop_generate_succeeds(max_digits in 1u32..=5u32) {
            let mut out = Vec::new();
            let result = generate_squares(max_digits, &mut out);
            prop_assert!(result.is_ok());
            prop_assert!(!out.is_empty());
        }
    }
}
