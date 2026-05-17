use clap::Parser;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use std::path::Path;
use std::process;

#[derive(Parser)]
#[command(about = "Find all amicable pairs (a,b) with b <= 10^N")]
struct Args {
    /// Exponent N: find pairs up to 10^N (1-8)
    #[arg(value_parser = clap::value_parser!(u32).range(1..=8))]
    n: u32,
}

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

fn run<W: Write, E: Write>(
    stdout: &mut W,
    _stderr: &mut E,
    out_path: &Path,
    limit: usize,
) -> io::Result<()> {
    let s = proper_divisor_sum_sieve(limit);
    let file = File::create(out_path)?;
    let mut writer = BufWriter::new(file);
    for a in 2..=limit {
        let b = s[a] as usize;
        if b > a && b <= limit && s[b] as usize == a {
            writeln!(stdout, "{a} {b}")?;
            writeln!(writer, "{a} {b}")?;
        }
    }
    Ok(())
}

#[cfg(not(tarpaulin_include))]
fn main() {
    let args = Args::parse();
    let n = args.n;
    let limit = 10usize.pow(n);
    let filename = format!("amicable_1e{n}.txt");
    if let Err(e) =
        run(&mut io::stdout().lock(), &mut io::stderr().lock(), Path::new(&filename), limit)
    {
        eprintln!("error: {e}");
        process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use crate::proper_divisor_sum_sieve;
    use crate::run;

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

    #[test]
    fn run_no_pairs_small_limit() {
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("out.txt");
        run(&mut out, &mut err, &path, 100).unwrap();
        assert!(out.is_empty());
    }

    #[test]
    fn run_first_pair_220_284() {
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("out.txt");
        run(&mut out, &mut err, &path, 284).unwrap();
        assert_eq!(String::from_utf8(out).unwrap(), "220 284\n");
    }

    #[test]
    fn run_b_exceeds_limit_no_pair() {
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("out.txt");
        run(&mut out, &mut err, &path, 219).unwrap();
        assert!(out.is_empty());
    }

    #[test]
    fn run_five_pairs_up_to_10000() {
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("out.txt");
        run(&mut out, &mut err, &path, 10_000).unwrap();
        let output = String::from_utf8(out).unwrap();
        let lines: Vec<&str> = output.lines().collect();
        assert_eq!(lines.len(), 5);
        assert_eq!(lines[0], "220 284");
        assert_eq!(lines[4], "6232 6368");
    }

    #[test]
    fn run_perfect_number_excluded() {
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("out.txt");
        run(&mut out, &mut err, &path, 10).unwrap();
        let output = String::from_utf8(out).unwrap();
        assert!(output.is_empty());
    }

    #[test]
    fn run_output_file_written() {
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("amicable_1e0.txt");
        run(&mut out, &mut err, &path, 284).unwrap();
        let content = std::fs::read_to_string(&path).unwrap();
        assert_eq!(content, "220 284\n");
    }
}
