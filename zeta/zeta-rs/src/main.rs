use std::fs::{self, File, OpenOptions};
use std::io::{self, BufRead, BufWriter, Write};
use std::path::PathBuf;
use std::time::Instant;

use clap::Parser;
use rug::Float;
use rug::float::Round;
use zeta::config::VerifyConfig;
use zeta::spacing::{midpoint, refine_intervals, width_text, write_report};
use zeta::verify::{GramSpan, PoolPolicy, RunStats, Verdict, verify};
use zeta::zfun::{RealZ, SELF_CHECK_PREC, ZError, ZEvaluator, ZSource, self_check};

/// Smallest and largest accepted N (the height is 10^N).
const MIN_N: u32 = 2;
const MAX_N: u32 = 7;

#[derive(Parser, Debug)]
#[command(
    name = "zeta",
    about = "Verify the Riemann Hypothesis up to height 10^N with certified interval arithmetic"
)]
struct Cli {
    /// N: target height 10^N (2-7); prompted for when omitted
    ///
    /// Kept as text, with negative numbers accepted as values, so that every invalid
    /// N exits 1 (R1), not clap's usage code 2.
    #[arg(allow_negative_numbers = true, value_name = "N")]
    exponent: Option<String>,

    /// Narrow each zero's bracket by certified bisection and print the spacing histogram
    #[arg(long)]
    refine: bool,
}

/// Parses N and checks the 2-7 range.
fn parse_n(text: &str) -> Option<u32> {
    text.trim().parse::<u32>().ok().filter(|n| (MIN_N..=MAX_N).contains(n))
}

/// Prompts for N until valid. `Ok(Err(code))` means end the run with exit `code`
/// (end of input, reported on `err`; unreadable input, reported on `err` best effort).
/// `Err` is a failed write to `out` or `err`.
fn prompt_n<R: BufRead, W: Write, E: Write>(
    reader: &mut R,
    out: &mut W,
    err: &mut E,
) -> io::Result<Result<u32, i32>> {
    loop {
        write!(out, "Enter N (verifies RH up to height 10^N, {MIN_N}-{MAX_N}): ")?;
        out.flush()?;
        let mut line = String::new();
        let read = match reader.read_line(&mut line) {
            Ok(read) => read,
            Err(e) => {
                // Best effort: the input error is the exit-1 cause even if stderr is also broken.
                let _ = writeln!(err, "Error: cannot read input: {e}");
                return Ok(Err(1));
            }
        };
        if read == 0 {
            writeln!(out)?;
            writeln!(err, "Error: no input; pass SIZE as an argument (e.g. zeta 3).")?;
            return Ok(Err(1));
        }
        match parse_n(&line) {
            Some(n) => return Ok(Ok(n)),
            None => writeln!(out, "N must be between {MIN_N} and {MAX_N}.")?,
        }
    }
}

/// Where the output table goes. A trait so tests can fail each step; production
/// uses `DirStore`. Names are bare file names, resolved by the store.
trait OutputStore {
    type File: SyncFile;
    /// Removes a stale temporary file; a missing file is success.
    fn remove_stale(&self, name: &str) -> io::Result<()>;
    fn create(&self, name: &str) -> io::Result<Self::File>;
    fn rename(&self, from: &str, to: &str) -> io::Result<()>;
    fn remove(&self, name: &str) -> io::Result<()>;
}

/// A writable file that can be forced to stable storage before it is renamed
/// into place, so a crash cannot leave a complete-looking but truncated table.
trait SyncFile: Write {
    fn sync(&mut self) -> io::Result<()>;
}

impl SyncFile for File {
    fn sync(&mut self) -> io::Result<()> {
        self.sync_all()
    }
}

/// The real store: files in one directory (the current directory in production).
#[derive(Debug)]
struct DirStore(PathBuf);

impl OutputStore for DirStore {
    type File = File;

    fn remove_stale(&self, name: &str) -> io::Result<()> {
        match fs::remove_file(self.0.join(name)) {
            Err(e) if e.kind() != io::ErrorKind::NotFound => Err(e),
            _ => Ok(()),
        }
    }

    /// `create_new`: an existing file is another run's (or a stale one the start of
    /// this run failed to remove), never ours to truncate.
    fn create(&self, name: &str) -> io::Result<File> {
        OpenOptions::new().write(true).create_new(true).open(self.0.join(name))
    }

    fn rename(&self, from: &str, to: &str) -> io::Result<()> {
        fs::rename(self.0.join(from), self.0.join(to))
    }

    fn remove(&self, name: &str) -> io::Result<()> {
        fs::remove_file(self.0.join(name))
    }
}

/// Everything `run_core` needs besides the streams, so production and tests differ
/// only in what they put here (R24: `run` fixes the production values).
struct Env<'a, Z, S> {
    cfg: &'a VerifyConfig,
    /// The Z source, or why it could not be built (reported as a failed self-check).
    z: Result<Z, ZError>,
    store: &'a S,
    policy: PoolPolicy,
    /// Test-only (R24): production always runs the self-check.
    #[cfg(test)]
    skip_self_check: bool,
}

/// Runs the CLI against injectable streams with the real Z, self-check and pool,
/// writing the table into the current directory.
fn run<R: BufRead, W: Write, E: Write>(
    cli: &Cli,
    reader: &mut R,
    out: &mut W,
    err: &mut E,
) -> io::Result<i32> {
    let cfg = VerifyConfig::default();
    let env = Env {
        z: RealZ::new(&cfg),
        cfg: &cfg,
        store: &DirStore(PathBuf::from(".")),
        policy: PoolPolicy::Parallel,
        #[cfg(test)]
        skip_self_check: false,
    };
    run_core(cli, reader, out, err, env)
}

/// `run` with injected configuration, Z source, store, pool and self-check skip.
#[cfg(test)]
fn run_with<R, W, E, Z, S>(
    cli: &Cli,
    reader: &mut R,
    out: &mut W,
    err: &mut E,
    env: Env<'_, Z, S>,
) -> io::Result<i32>
where
    R: BufRead,
    W: Write,
    E: Write,
    Z: ZSource + Sync,
    S: OutputStore,
{
    run_core(cli, reader, out, err, env)
}

/// Shared body of `run` and `run_with`.
fn run_core<R, W, E, Z, S>(
    cli: &Cli,
    reader: &mut R,
    out: &mut W,
    err: &mut E,
    env: Env<'_, Z, S>,
) -> io::Result<i32>
where
    R: BufRead,
    W: Write,
    E: Write,
    Z: ZSource + Sync,
    S: OutputStore,
{
    let n = match &cli.exponent {
        Some(text) => match parse_n(text) {
            Some(n) => n,
            None => {
                writeln!(err, "Error: N must be between {MIN_N} and {MAX_N}.")?;
                return Ok(1);
            }
        },
        None => match prompt_n(reader, out, err)? {
            Ok(n) => n,
            Err(code) => return Ok(code),
        },
    };
    if n == MAX_N {
        writeln!(
            err,
            "Warning: N=7 writes about 1.5 GB (about 2.2 GB with --refine) and may take many hours."
        )?;
    }
    // A stale temporary file from an interrupted run goes first (R9), before any
    // work that could end the run.
    let tmp = tmp_name(n);
    if let Err(e) = env.store.remove_stale(&tmp) {
        writeln!(err, "Error: cannot remove stale {tmp}: {e}")?;
        return Ok(4);
    }
    // Test-only skip (R24): in a production build the self-check always runs.
    #[cfg(test)]
    let skip_self_check = env.skip_self_check;
    #[cfg(not(test))]
    let skip_self_check = false;
    let z = match env.z {
        Ok(z) => z,
        Err(e) => {
            writeln!(err, "self-check failed: {e}")?;
            return Ok(5);
        }
    };
    let self_checked = !skip_self_check;
    if self_checked && let Err(reason) = self_check_with(env.cfg) {
        writeln!(err, "self-check failed: {reason}")?;
        return Ok(5);
    }
    let started = Instant::now();
    let height = 10u64.pow(n);
    // Exact: 10^7 < 2^53.
    let verdict = verify(height as f64, &z, env.cfg, env.policy, err);
    // Refinement runs only on a verified table, before anything is saved: a Z fault
    // here is an internal error (exit 6) and leaves no table behind.
    let refined = match (&verdict, cli.refine) {
        (Verdict::Verified { intervals, .. }, true) => {
            match refine_intervals(&z, env.cfg, intervals) {
                Ok(refined) => Some(refined),
                Err(e) => {
                    writeln!(err, "internal error: {e}")?;
                    return Ok(6);
                }
            }
        }
        _ => None,
    };
    let summary = Summary { n, self_checked, elapsed: started.elapsed().as_secs_f64() };
    report(verdict, &summary, refined.as_deref(), env.store, out, err)
}

/// Name of the temporary file the table is written to before it is renamed.
fn tmp_name(n: u32) -> String {
    format!("zeta_1e{n}.tmp.txt")
}

/// Name of the finished table.
fn table_name(n: u32) -> String {
    format!("zeta_1e{n}.txt")
}

/// The self-check's spec line, printed only when the self-check ran.
const SELF_CHECK_LINE: &str =
    "Self-check: Riemann\u{2013}Siegel and Euler\u{2013}Maclaurin agree on [200, 300] (8 points)";

/// Why a Gram block is listed as uncertified: only blocks still short of Rosser's
/// count after the neighbour search are listed.
const BLOCK_REASON: &str = "Rosser's count not reached after the neighbour search";

/// What a run knows about itself besides the verdict.
struct Summary {
    n: u32,
    self_checked: bool,
    elapsed: f64,
}

/// Turns a verdict into the report, the table (only when verified) and the exit code.
/// The verified block is printed only after the table is saved, so a failed save
/// never follows a claim. `refined` holds the refined brackets under `--refine`: they
/// replace the unrefined ones in the table and feed the spacing report.
fn report<W: Write, E: Write, S: OutputStore>(
    verdict: Verdict,
    summary: &Summary,
    refined: Option<&[(f64, f64)]>,
    store: &S,
    out: &mut W,
    err: &mut E,
) -> io::Result<i32> {
    let Summary { n, self_checked, elapsed } = *summary;
    let height = 10u64.pow(n);
    match verdict {
        Verdict::Verified { count, intervals, stats } => {
            let (brackets, columns) = match refined {
                Some(r) => (r, true),
                None => (intervals.as_slice(), false),
            };
            if let Err(e) = save_table(store, n, brackets, columns) {
                writeln!(err, "Error: cannot write {}: {e}", table_name(n))?;
                return Ok(4);
            }
            if self_checked {
                writeln!(out, "{SELF_CHECK_LINE}")?;
            }
            write_verified(out, n, count, &stats, elapsed)?;
            if let Some(r) = refined {
                write_report(out, r)?;
            }
            Ok(0)
        }
        Verdict::NotVerified { reason, blocks } => {
            writeln!(out, "RH NOT verified up to {height}: {reason}")?;
            if !blocks.is_empty() {
                writeln!(
                    out,
                    "Uncertified Gram blocks: {}  ({BLOCK_REASON})",
                    spans_text(&blocks)
                )?;
            }
            writeln!(out, "No claim is made for this range.")?;
            Ok(3)
        }
        Verdict::Fault { reason } => {
            writeln!(err, "internal error: {reason}")?;
            Ok(6)
        }
        Verdict::WriteFailed { error } => {
            writeln!(err, "Error: cannot write to stderr: {error}")?;
            Ok(4)
        }
    }
}

/// `[g_a, g_b], [g_c, g_d]`
fn spans_text(blocks: &[GramSpan]) -> String {
    let spans: Vec<String> =
        blocks.iter().map(|b| format!("[g_{}, g_{}]", b.first, b.last)).collect();
    spans.join(", ")
}

/// g_M's bracket to 6 decimals: one value when both ends print alike, else `[lo, hi]`.
fn g_m_text((lo, hi): (f64, f64)) -> String {
    let (lo, hi) = (format!("{lo:.6}"), format!("{hi:.6}"));
    if lo == hi { lo } else { format!("[{lo}, {hi}]") }
}

/// The verified block after the self-check line, in the spec's order.
fn write_verified<W: Write>(
    out: &mut W,
    n: u32,
    count: usize,
    stats: &RunStats,
    elapsed: f64,
) -> io::Result<()> {
    let height = 10u64.pow(n);
    writeln!(out, "Turing bound: N(g_M) <= M+1 established at g_M = {}", g_m_text(stats.g_m))?;
    writeln!(out, "Isolating zeros in 0 < t <= {height} ({} threads)...", stats.threads)?;
    writeln!(out)?;
    writeln!(
        out,
        "RH verified: all {count} nontrivial zeros with 0 < Im s <= {height} lie on Re s = 1/2 and are simple"
    )?;
    writeln!(
        out,
        "Gram blocks: {}   Rosser exceptions: {}   max precision: {} bits",
        stats.gram_blocks, stats.rosser_exceptions, stats.max_precision
    )?;
    writeln!(out, "Saved {}", table_name(n))?;
    writeln!(out, "Elapsed: {elapsed:.1} s")
}

/// Writes the table to the temporary file, syncs it and renames it into place; a
/// failure after the file was created removes the temporary file, so no partial table
/// is left under either name. A failed create removes nothing: the file in the way
/// is not ours (`AlreadyExists` is another run's temporary file).
fn save_table<S: OutputStore>(
    store: &S,
    n: u32,
    intervals: &[(f64, f64)],
    columns: bool,
) -> io::Result<()> {
    let (tmp, table) = (tmp_name(n), table_name(n));
    let mut file = store.create(&tmp)?;
    let written = write_table(&mut file, intervals, columns).and_then(|()| file.sync());
    drop(file);
    let result = written.and_then(|()| store.rename(&tmp, &table));
    if result.is_err() {
        // Cleanup only: the write error is the one to report.
        let _ = store.remove(&tmp);
    }
    result
}

/// Header `# n a b`, then one `n a b` line per zero; with `columns` (`--refine`) the
/// header is `# n a b t_n w_n` and each line adds the bracket's midpoint to 15
/// significant digits and its width b - a to 3.
fn write_table<F: Write>(file: F, intervals: &[(f64, f64)], columns: bool) -> io::Result<()> {
    let mut w = BufWriter::new(file);
    writeln!(w, "{}", if columns { "# n a b t_n w_n" } else { "# n a b" })?;
    for (i, &(a, b)) in intervals.iter().enumerate() {
        write!(w, "{} {} {}", i + 1, digits30(a, Round::Down), digits30(b, Round::Up))?;
        if columns {
            write!(w, " {} {}", digits(midpoint(a, b), 15, Round::Nearest), width_text(b - a))?;
        }
        writeln!(w)?;
    }
    w.flush()
}

/// `x` (finite, at least 1: every zero height is above 14, and rug switches to
/// exponent notation below 1) to 30 significant digits, rounded in the given
/// direction. The `f64` is exact in 120 bits, so the only rounding is the decimal one.
fn digits30(x: f64, round: Round) -> String {
    digits(x, 30, round)
}

/// `x` (finite, at least 1) to `sig` significant digits, rounded in the given direction.
fn digits(x: f64, sig: usize, round: Round) -> String {
    Float::with_val(120, x).to_string_radix_round(10, Some(sig), round)
}

/// The self-check of both Z paths at `SELF_CHECK_PREC`; production passes default
/// settings (a Gabcke multiplier noticeably above 1 fails it; the 1e-10 slack
/// admits up to about 1 + 2e-8).
fn self_check_with(cfg: &VerifyConfig) -> Result<(), String> {
    let z = ZEvaluator::new(SELF_CHECK_PREC, cfg).map_err(|e| e.to_string())?;
    self_check(&z).map_err(|e| e.to_string())
}

/// Maps a `run` outcome to a process exit code. `run` returns `Err` only when a
/// write to stdout or stderr fails (a closed pipe, a full disk), which is exit 4.
/// Bad input is exit 1, except that a failure to write its error report is exit 4;
/// an unreadable prompt answer stays exit 1 because that report is best effort.
fn exit_code(result: std::io::Result<i32>) -> i32 {
    result.unwrap_or(4)
}

#[cfg(not(tarpaulin_include))]
fn main() {
    let cli = Cli::parse();
    let (stdin, stdout, stderr) = (io::stdin(), io::stdout(), io::stderr());
    let result = run(&cli, &mut stdin.lock(), &mut stdout.lock(), &mut stderr.lock());
    std::process::exit(exit_code(result));
}

#[cfg(test)]
mod tests {
    use super::*;
    use clap::CommandFactory;
    use std::cell::RefCell;
    use std::collections::BTreeMap;
    use std::rc::Rc;
    use zeta::interval::Interval;
    use zeta::verify::{Fault, GramSpan, NotVerifiedReason};
    use zeta::zfun::ZFault;

    #[test]
    fn help_parses() {
        let err = Cli::try_parse_from(["zeta", "--help"]).unwrap_err();
        assert_eq!(err.kind(), clap::error::ErrorKind::DisplayHelp);
    }

    #[test]
    fn command_definition_is_valid() {
        Cli::command().debug_assert();
    }

    #[test]
    fn exponent_is_optional_and_parsed() {
        assert_eq!(Cli::try_parse_from(["zeta"]).unwrap().exponent, None);
        assert_eq!(Cli::try_parse_from(["zeta", "3"]).unwrap().exponent.as_deref(), Some("3"));
    }

    struct FailingWriter;

    impl Write for FailingWriter {
        fn write(&mut self, _buf: &[u8]) -> io::Result<usize> {
            Err(io::Error::other("stderr closed"))
        }

        fn flush(&mut self) -> io::Result<()> {
            Err(io::Error::other("stderr closed"))
        }
    }

    /// Accepts writes, fails every flush.
    struct FlushFailingWriter;

    impl Write for FlushFailingWriter {
        fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
            Ok(buf.len())
        }

        fn flush(&mut self) -> io::Result<()> {
            Err(io::Error::other("flush failed"))
        }
    }

    /// Fails every write, accepts every flush.
    struct WriteFailingWriter;

    impl Write for WriteFailingWriter {
        fn write(&mut self, _buf: &[u8]) -> io::Result<usize> {
            Err(io::Error::other("write failed"))
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    /// Z that refuses every height: certifies nothing, so every run is "not verified".
    struct RefusingZ;

    impl ZSource for RefusingZ {
        fn z(&self, _t: f64, _prec: u32) -> Result<Option<Interval>, ZFault> {
            Ok(None)
        }

        fn z_over(&self, _lo: f64, _hi: f64, _prec: u32) -> Result<Option<Interval>, ZFault> {
            Ok(None)
        }
    }

    /// Z that faults on every call, so a run ends in exit 6.
    struct FaultZ;

    impl ZSource for FaultZ {
        fn z(&self, _t: f64, _prec: u32) -> Result<Option<Interval>, ZFault> {
            Err(ZFault::NanHeight)
        }

        fn z_over(&self, _lo: f64, _hi: f64, _prec: u32) -> Result<Option<Interval>, ZFault> {
            Err(ZFault::NanHeight)
        }
    }

    /// Which store step fails.
    #[derive(Clone, Copy, PartialEq)]
    enum Break {
        Nothing,
        Stale,
        Create,
        Write,
        Sync,
        Rename,
    }

    type Files = Rc<RefCell<BTreeMap<String, Vec<u8>>>>;

    /// In-memory store: `files` is the directory, `removed` logs every `remove`.
    struct MemStore {
        files: Files,
        removed: RefCell<Vec<String>>,
        /// Names of files whose `sync` ran.
        synced: Rc<RefCell<Vec<String>>>,
        brk: Break,
    }

    impl MemStore {
        fn new(brk: Break) -> MemStore {
            MemStore {
                files: Rc::default(),
                removed: RefCell::default(),
                synced: Rc::default(),
                brk,
            }
        }

        fn names(&self) -> Vec<String> {
            self.files.borrow().keys().cloned().collect()
        }
    }

    struct MemFile {
        files: Files,
        synced: Rc<RefCell<Vec<String>>>,
        name: String,
        fail: bool,
        fail_sync: bool,
    }

    impl SyncFile for MemFile {
        fn sync(&mut self) -> io::Result<()> {
            if self.fail_sync {
                return Err(io::Error::other("sync failed"));
            }
            self.synced.borrow_mut().push(self.name.clone());
            Ok(())
        }
    }

    impl Write for MemFile {
        fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
            if self.fail {
                return Err(io::Error::other("disk full"));
            }
            self.files.borrow_mut().get_mut(&self.name).unwrap().extend_from_slice(buf);
            Ok(buf.len())
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    impl OutputStore for MemStore {
        type File = MemFile;

        fn remove_stale(&self, name: &str) -> io::Result<()> {
            if self.brk == Break::Stale {
                return Err(io::Error::other("stale stuck"));
            }
            self.files.borrow_mut().remove(name);
            Ok(())
        }

        fn create(&self, name: &str) -> io::Result<MemFile> {
            if self.brk == Break::Create {
                return Err(io::Error::other("no space"));
            }
            if self.files.borrow().contains_key(name) {
                return Err(io::Error::from(io::ErrorKind::AlreadyExists));
            }
            self.files.borrow_mut().insert(name.to_string(), Vec::new());
            Ok(MemFile {
                files: Rc::clone(&self.files),
                synced: Rc::clone(&self.synced),
                name: name.to_string(),
                fail: self.brk == Break::Write,
                fail_sync: self.brk == Break::Sync,
            })
        }

        fn rename(&self, from: &str, to: &str) -> io::Result<()> {
            if self.brk == Break::Rename {
                return Err(io::Error::other("rename refused"));
            }
            let data = self.files.borrow_mut().remove(from).unwrap();
            self.files.borrow_mut().insert(to.to_string(), data);
            Ok(())
        }

        fn remove(&self, name: &str) -> io::Result<()> {
            self.removed.borrow_mut().push(name.to_string());
            self.files.borrow_mut().remove(name);
            Ok(())
        }
    }

    fn cli(args: &[&str]) -> Cli {
        let mut argv = vec!["zeta"];
        argv.extend_from_slice(args);
        Cli::try_parse_from(argv).unwrap()
    }

    fn env<'a, Z, S>(cfg: &'a VerifyConfig, z: Z, store: &'a S) -> Env<'a, Z, S> {
        Env { cfg, z: Ok(z), store, policy: PoolPolicy::Serial, skip_self_check: true }
    }

    /// Runs with the refusing Z, the default configuration and no self-check.
    fn drive(args: &[&str], input: &str) -> (i32, String, String) {
        let cfg = VerifyConfig::default();
        let store = MemStore::new(Break::Nothing);
        drive_with(args, input, env(&cfg, RefusingZ, &store))
    }

    fn drive_with<Z: ZSource + Sync, S: OutputStore>(
        args: &[&str],
        input: &str,
        env: Env<'_, Z, S>,
    ) -> (i32, String, String) {
        let (mut out, mut err) = (Vec::new(), Vec::new());
        let code = run_with(&cli(args), &mut input.as_bytes(), &mut out, &mut err, env).unwrap();
        (code, String::from_utf8(out).unwrap(), String::from_utf8(err).unwrap())
    }

    /// A widened Gabcke multiplier: the real self-check fails under it.
    fn widened() -> VerifyConfig {
        VerifyConfig::new(2.0, 512, 40, true).unwrap()
    }

    #[test]
    fn out_of_range_or_non_numeric_n_exits_1_with_message() {
        for arg in ["0", "1", "8", "99", "abc", "3x", "3.5", "", "-1", "-5"] {
            let (code, out, err) = drive(&[arg], "");
            assert_eq!(code, 1, "{arg:?}");
            assert_eq!(err, "Error: N must be between 2 and 7.\n", "{arg:?}");
            assert!(out.is_empty(), "{arg:?}: {out:?}");
        }
    }

    const PROMPT: &str = "Enter N (verifies RH up to height 10^N, 2-7): ";

    #[test]
    fn end_of_input_at_prompt_prints_newline_and_exits_1() {
        let (code, out, err) = drive(&[], "");
        assert_eq!(code, 1);
        assert_eq!(out, format!("{PROMPT}\n"));
        assert_eq!(err, "Error: no input; pass SIZE as an argument (e.g. zeta 3).\n");
    }

    #[test]
    fn prompt_reprompts_on_invalid_input_then_accepts() {
        let (code, out, err) = drive(&[], "abc\n8\n1\n 3 \n");
        assert_eq!(code, 3);
        let expected_prefix = format!(
            "{PROMPT}N must be between 2 and 7.\n{PROMPT}N must be between 2 and 7.\n\
             {PROMPT}N must be between 2 and 7.\n{PROMPT}"
        );
        assert!(out.starts_with(&expected_prefix), "{out:?}");
        assert!(!err.contains("no input"), "{err:?}");
    }

    #[test]
    fn prompt_accepts_both_range_ends() {
        for n in ["2", "7"] {
            let (code, out, _) = drive(&[], &format!("{n}\n"));
            assert_eq!(code, 3, "{n}");
            assert!(out.starts_with(PROMPT), "{n}");
        }
    }

    #[test]
    fn prompt_is_not_shown_when_n_is_an_argument() {
        let (_, out, _) = drive(&["3"], "");
        assert!(!out.contains("Enter N"), "{out:?}");
    }

    const WARNING: &str =
        "Warning: N=7 writes about 1.5 GB (about 2.2 GB with --refine) and may take many hours.\n";

    #[test]
    fn n_7_warns_on_stderr_and_other_n_do_not() {
        let (_, _, err) = drive(&["7"], "");
        assert_eq!(err, WARNING);
        let (_, _, err) = drive(&[], "7\n");
        assert_eq!(err, WARNING, "prompted N=7 also warns");
        for n in ["2", "3", "4", "5", "6"] {
            let (_, _, err) = drive(&[n], "");
            assert!(err.is_empty(), "{n}: {err:?}");
        }
    }

    #[test]
    fn no_certified_z_ends_not_verified_with_exit_3_and_no_file() {
        for (n, t) in [("2", "100"), ("3", "1000"), ("6", "1000000"), ("7", "10000000")] {
            let cfg = VerifyConfig::default();
            let store = MemStore::new(Break::Nothing);
            let (code, out, _) = drive_with(&[n], "", env(&cfg, RefusingZ, &store));
            assert_eq!(code, 3, "{n}");
            assert!(
                out.starts_with(&format!(
                    "RH NOT verified up to {t}: Turing bound not established\n"
                )),
                "{n}: {out:?}"
            );
            assert!(out.ends_with("No claim is made for this range.\n"), "{n}: {out:?}");
            assert!(store.names().is_empty(), "{n}: wrote {:?}", store.names());
        }
    }

    #[test]
    fn z_fault_ends_with_exit_6_internal_error_and_no_file() {
        let cfg = VerifyConfig::default();
        let store = MemStore::new(Break::Nothing);
        let (code, out, err) = drive_with(&["3"], "", env(&cfg, FaultZ, &store));
        assert_eq!(code, 6);
        assert!(err.starts_with("internal error: "), "{err:?}");
        assert!(out.is_empty(), "{out:?}");
        assert!(store.names().is_empty());
    }

    #[test]
    fn failing_self_check_exits_5_before_verifying_and_reports_on_stderr() {
        let cfg = widened();
        let store = MemStore::new(Break::Nothing);
        let mut e = env(&cfg, FaultZ, &store);
        e.skip_self_check = false;
        let (code, out, err) = drive_with(&["3"], "", e);
        assert_eq!(code, 5, "a Z fault would be exit 6, so the self-check ran first");
        assert!(err.starts_with("self-check failed: "), "{err:?}");
        assert!(err.contains("Riemann-Siegel enclosure wider"), "{err:?}");
        assert!(out.is_empty(), "{out:?}");
    }

    #[test]
    fn skip_self_check_lets_the_widened_config_reach_verification() {
        let cfg = widened();
        let store = MemStore::new(Break::Nothing);
        let (code, ..) = drive_with(&["3"], "", env(&cfg, RefusingZ, &store));
        assert_eq!(code, 3);
    }

    #[test]
    fn default_config_passes_the_self_check_in_a_run() {
        let cfg = VerifyConfig::default();
        let store = MemStore::new(Break::Nothing);
        let mut e = env(&cfg, RefusingZ, &store);
        e.skip_self_check = false;
        let (code, _, err) = drive_with(&["2"], "", e);
        assert_eq!(code, 3);
        assert!(err.is_empty(), "{err:?}");
    }

    #[test]
    fn self_check_does_not_run_for_an_invalid_n() {
        let cfg = widened();
        for bad in [vec!["1"], vec!["8"], vec!["x"], vec![]] {
            let store = MemStore::new(Break::Nothing);
            let mut e = env(&cfg, RefusingZ, &store);
            e.skip_self_check = false;
            let (code, ..) = drive_with(&bad, "", e);
            assert_eq!(code, 1, "{bad:?}: self-check ran without a valid N");
        }
    }

    #[test]
    fn unbuildable_z_exits_5() {
        let cfg = VerifyConfig::default();
        let store = MemStore::new(Break::Nothing);
        let e = Env::<RefusingZ, _> {
            cfg: &cfg,
            z: Err(ZError::HeightOutOfRange),
            store: &store,
            policy: PoolPolicy::Serial,
            skip_self_check: true,
        };
        let (code, _, err) = drive_with(&["3"], "", e);
        assert_eq!(code, 5);
        assert!(err.starts_with("self-check failed: "), "{err:?}");
    }

    #[test]
    fn stale_temporary_file_is_removed_at_start_and_never_replaced_by_a_table() {
        let cfg = VerifyConfig::default();
        let store = MemStore::new(Break::Nothing);
        store.files.borrow_mut().insert("zeta_1e3.tmp.txt".into(), b"stale".to_vec());
        store.files.borrow_mut().insert("zeta_1e2.tmp.txt".into(), b"other n".to_vec());
        let (code, ..) = drive_with(&["3"], "", env(&cfg, RefusingZ, &store));
        assert_eq!(code, 3);
        assert_eq!(store.names(), vec!["zeta_1e2.tmp.txt".to_string()]);
    }

    #[test]
    fn stale_removal_failure_exits_4_before_verifying() {
        let cfg = VerifyConfig::default();
        let store = MemStore::new(Break::Stale);
        let (code, out, err) = drive_with(&["3"], "", env(&cfg, FaultZ, &store));
        assert_eq!(code, 4, "a Z fault would be exit 6");
        assert_eq!(err, "Error: cannot remove stale zeta_1e3.tmp.txt: stale stuck\n");
        assert!(out.is_empty(), "{out:?}");
    }

    #[test]
    fn stale_removal_failure_exits_4_before_the_self_check() {
        let cfg = widened();
        let store = MemStore::new(Break::Stale);
        let mut e = env(&cfg, RefusingZ, &store);
        e.skip_self_check = false;
        let (code, ..) = drive_with(&["3"], "", e);
        assert_eq!(code, 4, "the widened config would fail the self-check with exit 5");
    }

    #[test]
    fn unbuildable_pool_falls_back_to_serial_on_stderr() {
        let cfg = VerifyConfig::default();
        let store = MemStore::new(Break::Nothing);
        let mut e = env(&cfg, RefusingZ, &store);
        e.policy = PoolPolicy::FailBuild;
        let (code, _, err) = drive_with(&["2"], "", e);
        assert_eq!(code, 3);
        assert!(err.starts_with("Parallel mode unavailable ("), "{err:?}");
        assert!(err.ends_with("falling back to serial.\n"), "{err:?}");
    }

    #[test]
    fn stderr_failure_while_reporting_the_pool_fallback_exits_4() {
        let cfg = VerifyConfig::default();
        let store = MemStore::new(Break::Nothing);
        let mut e = env(&cfg, RefusingZ, &store);
        e.policy = PoolPolicy::FailBuild;
        let result =
            run_with(&cli(&["2"]), &mut "".as_bytes(), &mut Vec::new(), &mut FailingWriter, e);
        assert_eq!(exit_code(result), 4);
    }

    fn exit_with<W: Write, E: Write>(args: &[&str], out: &mut W, err: &mut E) -> i32 {
        let cfg = widened();
        let store = MemStore::new(Break::Nothing);
        let mut e = env(&cfg, RefusingZ, &store);
        e.skip_self_check = false;
        exit_code(run_with(&cli(args), &mut "".as_bytes(), out, err, e))
    }

    // The widened config makes a run that reaches the self-check exit 5, so exit 4
    // here proves the write failed before it.
    #[test]
    fn prompt_write_failure_exits_4_before_the_self_check() {
        let cfg = widened();
        let store = MemStore::new(Break::Nothing);
        let mut e = env(&cfg, RefusingZ, &store);
        e.skip_self_check = false;
        let result =
            run_with(&cli(&[]), &mut "3\n".as_bytes(), &mut WriteFailingWriter, &mut Vec::new(), e);
        assert_eq!(exit_code(result), 4);
    }

    #[test]
    fn prompt_flush_failure_exits_4_before_the_self_check() {
        assert_eq!(exit_with(&[], &mut FlushFailingWriter, &mut Vec::new()), 4);
    }

    #[test]
    fn stderr_failure_on_the_n_7_warning_exits_4_before_the_self_check() {
        assert_eq!(exit_with(&["7"], &mut Vec::new(), &mut FailingWriter), 4);
    }

    #[test]
    fn stderr_failure_on_the_range_error_exits_4() {
        assert_eq!(exit_with(&["9"], &mut Vec::new(), &mut FailingWriter), 4);
    }

    #[test]
    fn stderr_failure_on_a_self_check_failure_exits_4() {
        assert_eq!(exit_with(&["3"], &mut Vec::new(), &mut FailingWriter), 4);
    }

    #[test]
    fn stdout_failure_on_the_not_verified_report_exits_4() {
        let cfg = VerifyConfig::default();
        let store = MemStore::new(Break::Nothing);
        let result = run_with(
            &cli(&["3"]),
            &mut "".as_bytes(),
            &mut FailingWriter,
            &mut Vec::new(),
            env(&cfg, RefusingZ, &store),
        );
        assert_eq!(exit_code(result), 4);
    }

    #[test]
    fn unreadable_input_exits_1_and_names_the_problem() {
        let invalid_utf8: &[u8] = &[0xff, 0xfe, b'\n'];
        let cfg = VerifyConfig::default();
        let store = MemStore::new(Break::Nothing);
        let (mut out, mut err) = (Vec::new(), Vec::new());
        let result = run_with(
            &cli(&[]),
            &mut &invalid_utf8[..],
            &mut out,
            &mut err,
            env(&cfg, RefusingZ, &store),
        );
        assert_eq!(exit_code(result), 1);
        let err = String::from_utf8(err).unwrap();
        assert!(err.starts_with("Error: cannot read input:"), "{err:?}");
        assert!(!String::from_utf8(out).unwrap().contains("RH NOT verified"));
    }

    #[test]
    fn unreadable_input_still_exits_1_when_stderr_is_also_broken() {
        let invalid_utf8: &[u8] = &[0xff, b'\n'];
        let cfg = VerifyConfig::default();
        let store = MemStore::new(Break::Nothing);
        let result = run_with(
            &cli(&[]),
            &mut &invalid_utf8[..],
            &mut Vec::new(),
            &mut FailingWriter,
            env(&cfg, RefusingZ, &store),
        );
        assert_eq!(exit_code(result), 1);
    }

    #[test]
    fn negative_n_is_a_range_error_not_a_usage_error() {
        assert_eq!(cli(&["-1"]).exponent.as_deref(), Some("-1"));
    }

    #[test]
    fn real_self_check_passes_by_default_and_fails_with_a_widened_bound() {
        assert_eq!(self_check_with(&VerifyConfig::default()), Ok(()));
        let err = self_check_with(&widened()).unwrap_err();
        assert!(err.contains("Riemann-Siegel enclosure wider"), "{err}");
    }

    #[test]
    fn exit_code_passes_through_success_codes() {
        assert_eq!(exit_code(Ok(3)), 3);
        assert_eq!(exit_code(Ok(0)), 0);
    }

    #[test]
    fn exit_code_maps_a_write_error_to_4() {
        assert_eq!(exit_code(Err(io::Error::other("closed"))), 4);
    }

    // ---- the table ----

    #[test]
    fn digits30_rounds_in_the_requested_direction() {
        // 1.1 as an f64 is 1.100000000000000088817841970012523...
        assert_eq!(digits30(1.1, Round::Down), "1.10000000000000008881784197001");
        assert_eq!(digits30(1.1, Round::Up), "1.10000000000000008881784197002");
    }

    #[test]
    fn digits30_keeps_30_significant_digits_for_a_large_height() {
        let down = digits30(1234.5, Round::Down);
        assert_eq!(down.chars().filter(char::is_ascii_digit).count(), 30, "{down}");
        assert!(down.starts_with("1234.5"), "{down}");
    }

    #[test]
    fn digits30_of_an_exact_value_is_the_same_both_ways() {
        assert_eq!(digits30(14.0, Round::Down), digits30(14.0, Round::Up));
    }

    #[test]
    fn write_table_has_the_header_then_numbered_lines() {
        let mut buf = Vec::new();
        write_table(&mut buf, &[(14.0, 14.5), (21.0, 21.5)], false).unwrap();
        let text = String::from_utf8(buf).unwrap();
        let lines: Vec<&str> = text.lines().collect();
        assert_eq!(lines.len(), 3);
        assert_eq!(lines[0], "# n a b");
        let first: Vec<&str> = lines[1].split(' ').collect();
        assert_eq!((first[0], first.len()), ("1", 3));
        assert!(first[1].starts_with("14.0") && first[2].starts_with("14.5"), "{}", lines[1]);
        assert!(lines[2].starts_with("2 21.0"), "{}", lines[2]);
    }

    #[test]
    fn write_table_rounds_a_down_and_b_up_for_a_non_exact_interval() {
        // 1.1 and 1.2 are not exact in binary: the interval must only ever widen.
        let mut buf = Vec::new();
        write_table(&mut buf, &[(1.1, 1.2)], false).unwrap();
        let text = String::from_utf8(buf).unwrap();
        assert_eq!(
            text,
            "# n a b\n1 1.10000000000000008881784197001 1.19999999999999995559107901500\n"
        );
    }

    #[test]
    fn write_table_of_no_zeros_is_just_the_header() {
        let mut buf = Vec::new();
        write_table(&mut buf, &[], false).unwrap();
        assert_eq!(String::from_utf8(buf).unwrap(), "# n a b\n");
    }

    #[test]
    fn write_table_reports_a_failing_writer() {
        assert!(write_table(WriteFailingWriter, &[(1.0, 2.0)], false).is_err());
        assert!(write_table(FlushFailingWriter, &[], false).is_err());
    }

    #[test]
    fn dir_store_create_refuses_an_existing_file() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("zeta_1e2.tmp.txt");
        fs::write(&path, b"another run's data").unwrap();
        let store = DirStore(dir.path().to_path_buf());
        let err = store.create("zeta_1e2.tmp.txt").unwrap_err();
        assert_eq!(err.kind(), io::ErrorKind::AlreadyExists);
        assert_eq!(fs::read(&path).unwrap(), b"another run's data");
    }

    #[test]
    fn save_table_leaves_only_the_final_file() {
        let store = MemStore::new(Break::Nothing);
        save_table(&store, 2, &[(14.0, 15.0)], false).unwrap();
        assert_eq!(store.names(), vec!["zeta_1e2.txt".to_string()]);
        let data = String::from_utf8(store.files.borrow()["zeta_1e2.txt"].clone()).unwrap();
        assert!(data.starts_with("# n a b\n1 14.0"), "{data:?}");
        assert!(store.removed.borrow().is_empty());
    }

    #[test]
    fn save_table_failure_at_any_step_leaves_no_file_and_removes_the_temporary() {
        for brk in [Break::Write, Break::Sync, Break::Rename] {
            let store = MemStore::new(brk);
            assert!(save_table(&store, 3, &[(14.0, 15.0)], false).is_err());
            assert!(store.names().is_empty(), "{:?}", store.names());
            assert_eq!(*store.removed.borrow(), vec!["zeta_1e3.tmp.txt".to_string()]);
        }
    }

    #[test]
    fn save_table_syncs_the_temporary_file_before_the_rename() {
        let store = MemStore::new(Break::Nothing);
        save_table(&store, 3, &[(14.0, 15.0)], false).unwrap();
        assert_eq!(*store.synced.borrow(), vec!["zeta_1e3.tmp.txt".to_string()]);
    }

    #[test]
    fn a_failed_create_removes_nothing() {
        let store = MemStore::new(Break::Create);
        assert!(save_table(&store, 3, &[(14.0, 15.0)], false).is_err());
        assert!(store.removed.borrow().is_empty());
    }

    #[test]
    fn a_temporary_file_that_already_exists_is_left_untouched_and_fails_the_save() {
        let store = MemStore::new(Break::Nothing);
        store.files.borrow_mut().insert("zeta_1e3.tmp.txt".into(), b"other run".to_vec());
        let error = save_table(&store, 3, &[(14.0, 15.0)], false).unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::AlreadyExists);
        assert_eq!(store.files.borrow()["zeta_1e3.tmp.txt"], b"other run");
        assert!(store.removed.borrow().is_empty());
        assert!(store.synced.borrow().is_empty());
    }

    fn stats() -> RunStats {
        RunStats {
            m: 5,
            g_m: (535.25, 535.75),
            gram_blocks: 7,
            rosser_exceptions: 2,
            max_precision: 128,
            threads: 4,
        }
    }

    fn verified() -> Verdict {
        Verdict::Verified { count: 2, intervals: vec![(14.0, 15.0), (21.0, 22.0)], stats: stats() }
    }

    /// `report` as a run that did the self-check and took 1.25 s.
    fn report_for<W: Write, E: Write, S: OutputStore>(
        verdict: Verdict,
        n: u32,
        store: &S,
        out: &mut W,
        err: &mut E,
    ) -> io::Result<i32> {
        report(verdict, &Summary { n, self_checked: true, elapsed: 1.25 }, None, store, out, err)
    }

    #[test]
    fn verified_verdict_prints_the_line_saves_the_table_and_exits_0() {
        let store = MemStore::new(Break::Nothing);
        let (mut out, mut err) = (Vec::new(), Vec::new());
        let code = report_for(verified(), 2, &store, &mut out, &mut err).unwrap();
        assert_eq!(code, 0);
        assert_eq!(
            String::from_utf8(out).unwrap(),
            "Self-check: Riemann\u{2013}Siegel and Euler\u{2013}Maclaurin agree on [200, 300] (8 points)\n\
             Turing bound: N(g_M) <= M+1 established at g_M = [535.250000, 535.750000]\n\
             Isolating zeros in 0 < t <= 100 (4 threads)...\n\
             \n\
             RH verified: all 2 nontrivial zeros with 0 < Im s <= 100 lie on Re s = 1/2 and are simple\n\
             Gram blocks: 7   Rosser exceptions: 2   max precision: 128 bits\n\
             Saved zeta_1e2.txt\n\
             Elapsed: 1.2 s\n"
        );
        assert!(err.is_empty());
        assert_eq!(store.names(), vec!["zeta_1e2.txt".to_string()]);
    }

    #[test]
    fn verified_verdict_with_a_failed_write_exits_4_and_claims_nothing() {
        for brk in [Break::Create, Break::Write, Break::Sync, Break::Rename] {
            let store = MemStore::new(brk);
            let (mut out, mut err) = (Vec::new(), Vec::new());
            let code = report_for(verified(), 2, &store, &mut out, &mut err).unwrap();
            assert_eq!(code, 4);
            assert!(out.is_empty(), "{:?}", String::from_utf8_lossy(&out));
            let err = String::from_utf8(err).unwrap();
            assert!(err.starts_with("Error: cannot write zeta_1e2.txt: "), "{err:?}");
            assert!(store.names().is_empty());
        }
    }

    #[test]
    fn a_failing_stdout_after_the_save_exits_4_and_the_table_stays() {
        let store = MemStore::new(Break::Nothing);
        let result = report_for(verified(), 2, &store, &mut FailingWriter, &mut Vec::new());
        assert_eq!(exit_code(result), 4);
        assert_eq!(store.names(), vec!["zeta_1e2.txt".to_string()]);
    }

    #[test]
    fn g_m_prints_one_value_when_the_ends_agree_to_six_decimals() {
        assert_eq!(g_m_text((1000.4755762, 1000.4755764)), "1000.475576");
        assert_eq!(g_m_text((535.25, 535.75)), "[535.250000, 535.750000]");
        assert_eq!(g_m_text((535.0, 535.000_002)), "[535.000000, 535.000002]");
    }

    #[test]
    fn the_verified_block_prints_a_single_g_m_when_the_bracket_is_that_narrow() {
        let store = MemStore::new(Break::Nothing);
        let mut verdict = verified();
        if let Verdict::Verified { stats, .. } = &mut verdict {
            stats.g_m = (1000.4755762, 1000.4755764);
        }
        let mut out = Vec::new();
        report(
            verdict,
            &Summary { n: 2, self_checked: true, elapsed: 0.0 },
            None,
            &store,
            &mut out,
            &mut Vec::new(),
        )
        .unwrap();
        let out = String::from_utf8(out).unwrap();
        assert!(out.contains("established at g_M = 1000.475576\n"), "{out:?}");
    }

    #[test]
    fn the_real_file_sync_reports_a_failing_fsync() {
        // fsync on a pipe is EINVAL on Linux, so the real impl must pass the error on.
        let (_read, write) = io::pipe().unwrap();
        let mut file = File::from(std::os::fd::OwnedFd::from(write));
        assert!(SyncFile::sync(&mut file).is_err());
    }

    #[test]
    fn the_real_file_sync_succeeds_on_a_regular_file() {
        let dir = tempfile::tempdir().unwrap();
        let mut file = File::create(dir.path().join("f")).unwrap();
        file.write_all(b"x").unwrap();
        SyncFile::sync(&mut file).unwrap();
    }

    #[test]
    fn the_self_check_line_is_printed_only_when_it_ran() {
        let store = MemStore::new(Break::Nothing);
        let mut out = Vec::new();
        report(
            verified(),
            &Summary { n: 2, self_checked: false, elapsed: 0.04 },
            None,
            &store,
            &mut out,
            &mut Vec::new(),
        )
        .unwrap();
        let out = String::from_utf8(out).unwrap();
        assert!(out.starts_with("Turing bound: "), "{out:?}");
        assert!(!out.contains("Self-check"), "{out:?}");
        assert!(out.ends_with("Elapsed: 0.0 s\n"), "{out:?}");
    }

    #[test]
    fn not_verified_verdict_names_reason_and_blocks_and_exits_3() {
        let store = MemStore::new(Break::Nothing);
        let (mut out, mut err) = (Vec::new(), Vec::new());
        let verdict = Verdict::NotVerified {
            reason: NotVerifiedReason::UnresolvedBlocks,
            blocks: vec![GramSpan { first: 412, last: 414 }, GramSpan { first: 7, last: 8 }],
        };
        assert_eq!(report_for(verdict, 3, &store, &mut out, &mut err).unwrap(), 3);
        assert_eq!(
            String::from_utf8(out).unwrap(),
            "RH NOT verified up to 1000: every zero isolated, but some Gram blocks stayed short of Rosser's count\n\
             Uncertified Gram blocks: [g_412, g_414], [g_7, g_8]  (Rosser's count not reached after the neighbour search)\n\
             No claim is made for this range.\n"
        );
        assert!(err.is_empty());
        assert!(store.names().is_empty());
    }

    #[test]
    fn not_verified_without_blocks_omits_the_block_line() {
        let store = MemStore::new(Break::Nothing);
        let (mut out, mut err) = (Vec::new(), Vec::new());
        let verdict =
            Verdict::NotVerified { reason: NotVerifiedReason::NoBlocks, blocks: Vec::new() };
        assert_eq!(report_for(verdict, 2, &store, &mut out, &mut err).unwrap(), 3);
        let out = String::from_utf8(out).unwrap();
        assert!(!out.contains("Gram blocks"), "{out:?}");
    }

    #[test]
    fn fault_verdict_exits_6_on_stderr_only() {
        let store = MemStore::new(Break::Nothing);
        let (mut out, mut err) = (Vec::new(), Vec::new());
        let verdict = Verdict::Fault { reason: Fault::WorkerPanicked };
        assert_eq!(report_for(verdict, 3, &store, &mut out, &mut err).unwrap(), 6);
        assert_eq!(String::from_utf8(err).unwrap(), "internal error: worker panicked\n");
        assert!(out.is_empty());
    }

    #[test]
    fn write_failed_verdict_exits_4() {
        let store = MemStore::new(Break::Nothing);
        let (mut out, mut err) = (Vec::new(), Vec::new());
        let verdict = Verdict::WriteFailed { error: "pipe".into() };
        assert_eq!(report_for(verdict, 3, &store, &mut out, &mut err).unwrap(), 4);
        assert_eq!(String::from_utf8(err).unwrap(), "Error: cannot write to stderr: pipe\n");
    }

    #[test]
    fn no_failing_path_claims_verification() {
        let store = MemStore::new(Break::Nothing);
        for verdict in [
            Verdict::NotVerified { reason: NotVerifiedReason::NoBlocks, blocks: Vec::new() },
            Verdict::Fault { reason: Fault::WorkerPanicked },
            Verdict::WriteFailed { error: "x".into() },
        ] {
            let (mut out, mut err) = (Vec::new(), Vec::new());
            report_for(verdict, 3, &store, &mut out, &mut err).unwrap();
            for text in [out, err] {
                let text = String::from_utf8(text).unwrap();
                assert!(!text.contains("RH verified") && !text.contains("RH holds"), "{text:?}");
            }
        }
    }

    // ---- DirStore ----

    #[test]
    fn dir_store_creates_renames_and_removes_files() {
        let dir = tempfile::tempdir().unwrap();
        let store = DirStore(dir.path().to_path_buf());
        let mut f = store.create("a.tmp").unwrap();
        f.write_all(b"x").unwrap();
        drop(f);
        store.rename("a.tmp", "a").unwrap();
        assert_eq!(fs::read(dir.path().join("a")).unwrap(), b"x");
        assert!(!dir.path().join("a.tmp").exists());
        store.remove("a").unwrap();
        assert!(!dir.path().join("a").exists());
        assert!(store.remove("a").is_err());
    }

    #[test]
    fn dir_store_remove_stale_tolerates_missing_and_removes_present() {
        let dir = tempfile::tempdir().unwrap();
        let store = DirStore(dir.path().to_path_buf());
        store.remove_stale("none.tmp").unwrap();
        fs::write(dir.path().join("s.tmp"), "old").unwrap();
        store.remove_stale("s.tmp").unwrap();
        assert!(!dir.path().join("s.tmp").exists());
    }

    #[test]
    fn dir_store_remove_stale_reports_other_errors() {
        let dir = tempfile::tempdir().unwrap();
        fs::create_dir(dir.path().join("d")).unwrap();
        let store = DirStore(dir.path().to_path_buf());
        assert!(store.remove_stale("d").is_err(), "a directory cannot be unlinked as a file");
    }

    #[test]
    fn dir_store_create_in_a_missing_directory_fails() {
        let dir = tempfile::tempdir().unwrap();
        let store = DirStore(dir.path().join("missing"));
        assert!(store.create("x").is_err());
    }

    // ---- end to end with the real Z (skipped by cargo-mutants, spec V8) ----

    fn real_run(n: &str, cfg: &VerifyConfig, skip: bool) -> (i32, String, String, MemStore) {
        let store = MemStore::new(Break::Nothing);
        let e = Env {
            cfg,
            z: RealZ::new(cfg),
            store: &store,
            policy: PoolPolicy::Parallel,
            skip_self_check: skip,
        };
        let (code, out, err) = drive_with(&[n], "", e);
        (code, out, err, store)
    }

    #[test]
    fn e2e_real_z_verifies_n_2_through_run_with() {
        let (code, out, _, store) = real_run("2", &VerifyConfig::default(), false);
        assert_eq!(code, 0, "{out}");
        assert!(out.starts_with(SELF_CHECK_LINE), "{out}");
        assert!(out.contains("Isolating zeros in 0 < t <= 100 ("), "{out}");
        assert!(out.contains("all 29 nontrivial zeros"), "{out}");
        assert!(out.contains("   max precision: "), "{out}");
        let seconds = out.lines().last().unwrap().strip_prefix("Elapsed: ").unwrap();
        assert!(seconds.strip_suffix(" s").unwrap().parse::<f64>().unwrap() >= 0.0, "{out}");
        assert_eq!(store.names(), vec!["zeta_1e2.txt".to_string()]);
    }

    #[test]
    fn e2e_control_depth_cap_1_with_points_fixed_is_not_verified_at_n_3() {
        let cfg = VerifyConfig::new(1.0, 512, 1, false).unwrap();
        let (code, out, _, store) = real_run("3", &cfg, false);
        assert_eq!(code, 3, "{out}");
        assert!(store.names().is_empty());
        assert!(
            out.starts_with(
                "RH NOT verified up to 1000: 605 of 649 zeros isolated\n\
                 Uncertified Gram blocks: [g_125, g_127], [g_133, g_135]"
            ),
            "{out}"
        );
    }

    #[test]
    fn e2e_control_gabcke_times_1e6_is_not_verified_at_n_2() {
        let cfg = VerifyConfig::new(1e6, 512, 40, true).unwrap();
        let (code, out, _, store) = real_run("2", &cfg, true);
        assert_eq!(code, 3, "{out}");
        assert!(store.names().is_empty());
        assert_eq!(
            out,
            "RH NOT verified up to 100: Turing bound not established\n\
             No claim is made for this range.\n"
        );
    }

    // ---- --refine ----

    #[test]
    fn cli_parses_refine_as_a_flag_defaulting_to_off() {
        assert!(!Cli::try_parse_from(["zeta", "3"]).unwrap().refine);
        let c = Cli::try_parse_from(["zeta", "3", "--refine"]).unwrap();
        assert!(c.refine);
        assert_eq!(c.exponent.as_deref(), Some("3"));
        assert!(Cli::try_parse_from(["zeta", "--refine", "3"]).unwrap().refine);
    }

    #[test]
    fn write_table_with_columns_adds_t_n_and_w_n() {
        let mut buf = Vec::new();
        write_table(&mut buf, &[(14.0, 14.5), (21.0, 21.001)], true).unwrap();
        let text = String::from_utf8(buf).unwrap();
        let lines: Vec<&str> = text.lines().collect();
        assert_eq!(lines[0], "# n a b t_n w_n");
        assert_eq!(
            lines[1],
            format!(
                "1 {} {} 14.2500000000000 5.00e-1",
                digits30(14.0, Round::Down),
                digits30(14.5, Round::Up)
            )
        );
        let f: Vec<&str> = lines[2].split(' ').collect();
        assert_eq!(f.len(), 5);
        assert_eq!(f[3], "21.0005000000000");
        assert_eq!(f[4], "1.00e-3");
        assert_eq!(lines.len(), 3);
    }

    #[test]
    fn write_table_without_columns_is_the_plain_three_column_table() {
        let mut buf = Vec::new();
        write_table(&mut buf, &[(14.0, 14.5)], false).unwrap();
        let text = String::from_utf8(buf).unwrap();
        assert!(text.starts_with("# n a b\n1 "), "{text}");
        assert_eq!(text.lines().nth(1).unwrap().split(' ').count(), 3);
    }

    #[test]
    fn report_with_refined_brackets_saves_them_and_prints_the_spacing_block_last() {
        let store = MemStore::new(Break::Nothing);
        let (mut out, mut err) = (Vec::new(), Vec::new());
        let refined = [(14.1, 14.2), (21.0, 21.001)];
        let summary = Summary { n: 2, self_checked: false, elapsed: 0.5 };
        let code =
            report(verified(), &summary, Some(&refined), &store, &mut out, &mut err).unwrap();
        assert_eq!(code, 0);
        let out = String::from_utf8(out).unwrap();
        let elapsed = out.find("Elapsed: 0.5 s\n").unwrap();
        let block = out.find("\nSpacing histogram: ").unwrap();
        assert!(elapsed < block, "{out}");
        assert!(out.contains("Largest w_n: 1.00e-1\n"), "{out}");
        let table = String::from_utf8(store.files.borrow()["zeta_1e2.txt"].clone()).unwrap();
        assert!(table.starts_with("# n a b t_n w_n\n1 14.09"), "{table}");
    }

    #[test]
    fn report_without_refined_brackets_prints_no_spacing_block() {
        let store = MemStore::new(Break::Nothing);
        let (mut out, mut err) = (Vec::new(), Vec::new());
        report_for(verified(), 2, &store, &mut out, &mut err).unwrap();
        let out = String::from_utf8(out).unwrap();
        assert!(!out.contains("Spacing histogram") && out.ends_with("Elapsed: 1.2 s\n"), "{out}");
        let table = String::from_utf8(store.files.borrow()["zeta_1e2.txt"].clone()).unwrap();
        assert!(table.starts_with("# n a b\n"), "{table}");
    }

    #[test]
    fn a_non_verified_run_with_refine_skips_refinement() {
        let (code, out, _) = drive(&["3", "--refine"], "");
        assert_eq!(code, 3, "{out}");
        assert!(!out.contains("Spacing histogram"), "{out}");
    }

    const ODLYZKO: &str = include_str!("../tests/fixtures/odlyzko_1e3.txt");

    fn fixture_zeros() -> Vec<f64> {
        ODLYZKO.lines().filter(|l| !l.starts_with('#')).map(|l| l.trim().parse().unwrap()).collect()
    }

    fn table_rows(store: &MemStore, name: &str) -> Vec<Vec<String>> {
        let text = String::from_utf8(store.files.borrow()[name].clone()).unwrap();
        text.lines().skip(1).map(|l| l.split(' ').map(str::to_string).collect()).collect()
    }

    #[test]
    fn e2e_refine_at_n_3_brackets_every_odlyzko_zero_more_tightly() {
        let cfg = VerifyConfig::default();
        let (code, out, _, plain) = real_run("3", &cfg, true);
        assert_eq!(code, 0, "{out}");
        let store = MemStore::new(Break::Nothing);
        let env = Env {
            cfg: &cfg,
            z: RealZ::new(&cfg),
            store: &store,
            policy: PoolPolicy::Parallel,
            skip_self_check: true,
        };
        let (code, out, _) = drive_with(&["3", "--refine"], "", env);
        assert_eq!(code, 0, "{out}");
        let text = String::from_utf8(store.files.borrow()["zeta_1e3.txt"].clone()).unwrap();
        assert_eq!(text.lines().next(), Some("# n a b t_n w_n"));
        let (rows, plain_rows) =
            (table_rows(&store, "zeta_1e3.txt"), table_rows(&plain, "zeta_1e3.txt"));
        let zeros = fixture_zeros();
        assert_eq!((rows.len(), zeros.len()), (649, 649));
        // The fixture has 9 decimals, so a zero may sit up to half a unit beyond the bracket.
        let slack = 5.1e-10;
        for ((row, plain), z) in rows.iter().zip(&plain_rows).zip(&zeros) {
            let num = |s: &String| s.parse::<f64>().unwrap();
            let (a, b, w) = (num(&row[1]), num(&row[2]), num(&row[4]));
            assert!(a - slack <= *z && *z <= b + slack, "{row:?} vs {z}");
            assert_eq!(row[4], width_text(b - a), "{row:?}");
            assert!(w < 1e-2, "{row:?}");
            assert!(b - a < num(&plain[2]) - num(&plain[1]), "{row:?} vs {plain:?}");
            assert_eq!(row[3], digits(midpoint(a, b), 15, Round::Nearest), "{row:?}");
        }
        assert!(out.contains("Spacing histogram: "), "{out}");
        let ks: f64 = out
            .lines()
            .find_map(|l| l.strip_prefix("KS distance to the Wigner surmise CDF: "))
            .unwrap()
            .parse()
            .unwrap();
        assert!(ks < 0.1, "{ks}");
    }

    #[test]
    fn e2e_refine_without_the_flag_leaves_the_table_and_output_unchanged() {
        let (code, out, _, store) = real_run("2", &VerifyConfig::default(), true);
        assert_eq!(code, 0);
        assert!(!out.contains("Spacing histogram") && !out.contains("Largest w_n"), "{out}");
        let text = String::from_utf8(store.files.borrow()["zeta_1e2.txt"].clone()).unwrap();
        assert_eq!(text.lines().next(), Some("# n a b"));
        assert!(text.lines().skip(1).all(|l| l.split(' ').count() == 3));
    }

    /// Real Z that faults once `limit` calls have been made.
    struct FaultAfter {
        inner: RealZ,
        calls: std::sync::Arc<std::sync::atomic::AtomicUsize>,
        limit: usize,
    }

    impl ZSource for FaultAfter {
        fn z(&self, t: f64, prec: u32) -> Result<Option<Interval>, ZFault> {
            let n = self.calls.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
            if n >= self.limit { Err(ZFault::NanHeight) } else { self.inner.z(t, prec) }
        }

        fn z_over(&self, lo: f64, hi: f64, prec: u32) -> Result<Option<Interval>, ZFault> {
            self.inner.z_over(lo, hi, prec)
        }
    }

    #[test]
    fn e2e_a_z_fault_during_refinement_exits_6_and_saves_no_table() {
        let cfg = VerifyConfig::default();
        let run = |args: &[&str], limit: usize| {
            let store = MemStore::new(Break::Nothing);
            let calls = std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0));
            let z = FaultAfter { inner: RealZ::new(&cfg).unwrap(), calls: calls.clone(), limit };
            let e = Env {
                cfg: &cfg,
                z: Ok(z),
                store: &store,
                policy: PoolPolicy::Serial,
                skip_self_check: true,
            };
            let result = drive_with(args, "", e);
            (result, store.names(), calls.load(std::sync::atomic::Ordering::SeqCst))
        };
        let ((code, _, _), _, verify_calls) = run(&["2"], usize::MAX);
        assert_eq!(code, 0);
        let ((code, out, err), names, _) = run(&["2", "--refine"], verify_calls);
        assert_eq!(code, 6, "{out}{err}");
        assert!(err.starts_with("internal error: "), "{err}");
        assert!(names.is_empty() && !out.contains("RH verified"), "{out}");
    }
}
