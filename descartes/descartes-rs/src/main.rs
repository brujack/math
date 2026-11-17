use clap::error::ErrorKind;
use clap::{ArgAction, CommandFactory, Parser};
use std::env;
use std::ffi::OsString;
use std::fmt::Display;
use std::fs::File;
use std::io::{self, BufRead, BufWriter, IsTerminal, Write};
use std::path::Path;
use std::process::{self, Command, Stdio};
use std::time::Instant;

use descartes::{
    Circle, DescartesError, distinct, pack, render, root_centres, solve, validate_root, visible,
};

/// Largest K: curvature limit 10^8 is the core's `N_MAX` (spec R14, R22).
const K_MAX: i64 = 8;
/// `--smoke` runs the packing at this K (ADR-0030).
const SMOKE_SIZE: i64 = 2;
/// 17 significant digits round-trip any double; `--precision` caps decimal places at 17
/// to bound output size, since more only lets a flag write gigabytes (R27).
const PRECISION_MAX: i64 = 17;
const DEFAULT_ROOT: [i64; 4] = [-1, 2, 2, 3];
/// Piped output uses this fixed canvas, in braille cells (R11).
const PIPE_WIDTH: usize = 60;
const PIPE_HEIGHT: usize = 24;
/// A hostile terminal size must not make the drawing, and so the memory, unbounded (R27).
const CANVAS_MAX_WIDTH: usize = 1000;
const CANVAS_MAX_HEIGHT: usize = 500;
/// The packing drawing shows curvature at most twice the canvas width in dots,
/// and a braille cell is two dots wide: 4 per cell of width.
const DRAW_LIMIT_PER_COLUMN: i64 = 4;
/// Terminal size when neither the environment nor `stty` knows it, as Python's.
const FALLBACK_COLUMNS: usize = 80;
const FALLBACK_LINES: usize = 24;

const EPILOG: &str = "The packing drawing shows circles with curvature at most \
min(10^K, 2 x canvas width in braille dots), so its circle set depends on terminal width. \
--solve prints full-precision values that paste back into --solve; that stops passing the \
1e-9 tangency tolerance near curvature 2.6e7, and nearly collinear inputs are \
ill-conditioned. Run with no arguments at a terminal for interactive prompts.";

#[derive(Parser, Debug)]
#[command(
    about = "Enumerate an integral Apollonian packing up to curvature 10^K, or solve for the \
             circles tangent to three given circles",
    after_help = EPILOG,
    allow_negative_numbers = true,
    args_override_self = true
)]
struct Args {
    /// Exponent (curvature limit = 10^K, 1 to 8)
    #[arg(value_name = "K")]
    size: Option<i64>,
    /// Root quadruple, one negative value (default -1 2 2 3)
    #[arg(long, num_args = 4, action = ArgAction::Set, value_names = ["A", "B", "C", "D"])]
    root: Option<Vec<i64>>,
    /// Also print each result line to stdout
    #[arg(long)]
    show: bool,
    /// Confirm a large run (ignored when this program has none)
    #[arg(long)]
    yes: bool,
    /// Quick check at K = 2
    #[arg(long)]
    smoke: bool,
    /// Three mutually tangent circles (curvature, centre x, centre y); prints the circles
    /// tangent to all three. Excludes K
    #[arg(
        long,
        num_args = 3,
        action = ArgAction::Set,
        value_name = "K,X,Y",
        allow_hyphen_values = true,
        value_parser = parse_circle
    )]
    solve: Option<Vec<Circle>>,
    /// --solve only: round the displayed table to P decimal places (default: full precision)
    #[arg(long, value_name = "P")]
    precision: Option<i64>,
    /// Do not draw the circles in braille
    #[arg(long)]
    no_draw: bool,
}

/// What the process knows about its terminals; injected so tests drive both branches.
#[derive(Debug)]
struct Terminal {
    stdin_is_tty: bool,
    /// `Some((columns, lines))` when stdout is a terminal.
    stdout_size: Option<(usize, usize)>,
}

/// Why a run stopped early: an exit code (the message is already written) or an I/O failure.
#[derive(Debug)]
enum Stop {
    Code(i32),
    Io(io::Error),
}

impl From<io::Error> for Stop {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}

/// Write `text` and a newline to stderr; stop with `code`.
fn say<E: Write>(stderr: &mut E, text: impl Display, code: i32) -> Stop {
    match writeln!(stderr, "{text}") {
        Ok(()) => Stop::Code(code),
        Err(error) => Stop::Io(error),
    }
}

/// `Error: <message>` on stderr, as Python's `_fail`.
fn fail<E: Write>(stderr: &mut E, message: impl Display, code: i32) -> Stop {
    say(stderr, format!("Error: {message}"), code)
}

/// Report a library error at its own exit code (2 bad input, 1 no answer).
fn fail_descartes<E: Write>(stderr: &mut E, error: &DescartesError) -> Stop {
    fail(stderr, error, error.exit_code())
}

/// One `--solve` value, `K,X,Y`.
fn parse_circle(text: &str) -> Result<Circle, String> {
    let parts: Vec<&str> = text.split(',').collect();
    let [k, x, y] = parts[..] else {
        return Err(format!("'{text}' is not K,X,Y (three values)"));
    };
    let number = |part: &str| part.trim().parse::<f64>();
    match (number(k), number(x), number(y)) {
        (Ok(k), Ok(x), Ok(y)) => Ok((k, x, y)),
        _ => Err(format!("'{text}' is not K,X,Y (values must be numbers)")),
    }
}

/// A clap error for a rule clap cannot express, in clap's own format (usage block included).
fn usage_error(message: &str) -> String {
    Args::command().error(ErrorKind::ValueValidation, message).to_string()
}

/// Cross-flag rules of the Python `parse_args`: range of `--precision`, mode clashes, `--smoke`.
fn check_modes(args: &mut Args, stdin_is_tty: bool) -> Result<(), String> {
    if args.precision.is_some_and(|p| !(0..=PRECISION_MAX).contains(&p)) {
        return Err(format!("--precision must be between 0 and {PRECISION_MAX}"));
    }
    if args.solve.is_some() {
        let used = [
            ("K", args.size.is_some()),
            ("--root", args.root.is_some()),
            ("--smoke", args.smoke),
            ("--show", args.show),
            ("--yes", args.yes),
        ];
        let extras: Vec<&str> = used.iter().filter(|(_, on)| *on).map(|(name, _)| *name).collect();
        if !extras.is_empty() {
            return Err(format!("--solve takes no {}", extras.join(", ")));
        }
    } else if args.precision.is_some() {
        return Err("--precision needs --solve".to_string());
    } else if args.smoke {
        if args.size.is_some() {
            return Err("--smoke takes no K".to_string());
        }
        args.size = Some(SMOKE_SIZE);
        args.show = false;
    } else if args.size.is_none() && !stdin_is_tty {
        return Err("K is required when stdin is not a terminal".to_string());
    }
    Ok(())
}

/// Canvas in cells: a fixed size when piped, else the terminal clamped, one row spared (R27).
fn canvas_size(term: &Terminal) -> (usize, usize) {
    match term.stdout_size {
        None => (PIPE_WIDTH, PIPE_HEIGHT),
        Some((columns, lines)) => (
            columns.clamp(1, CANVAS_MAX_WIDTH),
            lines.saturating_sub(1).clamp(1, CANVAS_MAX_HEIGHT),
        ),
    }
}

/// `stty size` output, `<rows> <columns>`, as `(columns, lines)`.
fn parse_stty_size(text: &str) -> Option<(usize, usize)> {
    let mut fields = text.split_whitespace();
    let rows = fields.next()?.parse().ok()?;
    let columns = fields.next()?.parse().ok()?;
    Some((columns, rows))
}

/// Run `stty` (`command`, given the `size` argument) on `stdin`; `None` if it cannot say.
/// Taking a `Command` lets tests pass `sh -c` instead of writing an executable file, which
/// races with concurrent forks (ETXTBSY).
fn stty_size(mut command: Command, stdin: Stdio) -> Option<(usize, usize)> {
    let output = command.arg("size").stdin(stdin).stderr(Stdio::null()).output().ok()?;
    if !output.status.success() {
        return None;
    }
    parse_stty_size(&String::from_utf8_lossy(&output.stdout))
}

/// Per dimension, like Python's `shutil.get_terminal_size`: a positive environment value,
/// else a positive `stty` value, else the fallback.
fn pick_size(
    env_columns: Option<&str>,
    env_lines: Option<&str>,
    stty: Option<(usize, usize)>,
) -> (usize, usize) {
    let positive = |n: Option<usize>| n.filter(|&n| n > 0);
    let from_env = |text: Option<&str>| positive(text.and_then(|t| t.trim().parse().ok()));
    let columns = from_env(env_columns)
        .or(positive(stty.map(|(columns, _)| columns)))
        .unwrap_or(FALLBACK_COLUMNS);
    let lines =
        from_env(env_lines).or(positive(stty.map(|(_, lines)| lines))).unwrap_or(FALLBACK_LINES);
    (columns, lines)
}

/// Full-precision shortest form by default, else `precision` decimals; never `-0`.
fn format_value(value: f64, precision: Option<usize>) -> String {
    let Some(places) = precision else {
        return format!("{}", value + 0.0);
    };
    let text = format!("{value:.places$}");
    match text.strip_prefix('-') {
        Some(unsigned) if text.parse::<f64>().is_ok_and(|v| v == 0.0) => unsigned.to_string(),
        _ => text,
    }
}

/// The given and solution circles as table lines, columns padded to align, no trailing space.
fn table_lines(given: &[Circle], solutions: &[Circle], precision: Option<usize>) -> Vec<String> {
    let mut rows: Vec<Vec<String>> =
        vec![["kind", "#", "curvature", "radius", "x", "y"].map(String::from).to_vec()];
    for (kind, circles) in [("given", given), ("solution", solutions)] {
        for (number, &(k, x, y)) in circles.iter().enumerate() {
            let mut row = vec![kind.to_string(), (number + 1).to_string()];
            row.extend([k, 1.0 / k, x, y].map(|value| format_value(value, precision)));
            rows.push(row);
        }
    }
    let widths: Vec<usize> =
        (0..6).map(|c| rows.iter().map(|row| row[c].len()).max().unwrap_or(0)).collect();
    rows.iter()
        .map(|row| {
            let cells: Vec<String> =
                row.iter().zip(&widths).map(|(cell, width)| format!("{cell:<width$}")).collect();
            cells.join("  ").trim_end().to_string()
        })
        .collect()
}

/// Draw the circles on the canvas the terminal allows.
fn draw<W: Write, E: Write>(
    circles: &[Circle],
    term: &Terminal,
    stdout: &mut W,
    stderr: &mut E,
) -> Result<(), Stop> {
    let (width, height) = canvas_size(term);
    let lines = render(circles, width, height).map_err(|e| fail_descartes(stderr, &e))?;
    writeln!(stdout, "{}", lines.join("\n"))?;
    Ok(())
}

fn run_solve<W: Write, E: Write>(
    args: &Args,
    given: &[Circle],
    term: &Terminal,
    stdout: &mut W,
    stderr: &mut E,
) -> Result<(), Stop> {
    let solutions = solve(given[0], given[1], given[2]).map_err(|e| fail_descartes(stderr, &e))?;
    let precision = args.precision.map(|p| p as usize);
    for line in table_lines(given, &solutions, precision) {
        writeln!(stdout, "{line}")?;
    }
    if !args.no_draw {
        let all: Vec<Circle> = given.iter().chain(&solutions).copied().collect();
        draw(&all, term, stdout, stderr)?;
    }
    Ok(())
}

/// Prompt for K on stdout until stdin gives an integer in 1..=`K_MAX` (a terminal run with
/// no K argument); each bad answer is reported on stderr and asked again.
fn prompt_exponent<R: BufRead, W: Write, E: Write>(
    stdin: &mut R,
    stdout: &mut W,
    stderr: &mut E,
) -> Result<i64, Stop> {
    loop {
        write!(stdout, "Enter exponent K (limit = 10^K, max {K_MAX}): ")?;
        stdout.flush()?;
        let mut line = String::new();
        if stdin.read_line(&mut line)? == 0 {
            writeln!(stdout)?;
            let hint = format!("no input; pass K as an argument (e.g. descartes {SMOKE_SIZE}).");
            return Err(fail(stderr, hint, 1));
        }
        let text = line.trim_end_matches(['\n', '\r']);
        match text.trim().parse::<i64>() {
            Err(_) => writeln!(stderr, "Invalid input: '{text}' is not an integer K.")?,
            Ok(k) if !(1..=K_MAX).contains(&k) => {
                writeln!(stderr, "K must be between 1 and {K_MAX}, got {k}.")?;
            }
            Ok(k) => return Ok(k),
        }
    }
}

/// K from the argument or the prompt, checked against 1..=`K_MAX`.
fn exponent<R: BufRead, W: Write, E: Write>(
    size: Option<i64>,
    stdin: &mut R,
    stdout: &mut W,
    stderr: &mut E,
) -> Result<u32, Stop> {
    let k = match size {
        Some(k) => k,
        None => prompt_exponent(stdin, stdout, stderr)?,
    };
    if !(1..=K_MAX).contains(&k) {
        return Err(say(stderr, format!("K must be between 1 and {K_MAX}, got {k}."), 2));
    }
    Ok(k as u32)
}

/// The output file name: the root joins the name unless it is the default.
fn packing_filename(k: u32, root: [i64; 4]) -> String {
    if root == DEFAULT_ROOT {
        return format!("descartes_1e{k}.txt");
    }
    format!("descartes_1e{k}_root_{}_{}_{}_{}.txt", root[0], root[1], root[2], root[3])
}

fn run_packing<R: BufRead, W: Write, E: Write>(
    args: &Args,
    stdin: &mut R,
    term: &Terminal,
    out_dir: &Path,
    stdout: &mut W,
    stderr: &mut E,
) -> Result<(), Stop> {
    let k = exponent(args.size, stdin, stdout, stderr)?;
    // `num_args = 4` with `ArgAction::Set` leaves exactly four values (the last `--root` wins).
    let requested = args
        .root
        .as_deref()
        .map_or(DEFAULT_ROOT, |r| <[i64; 4]>::try_from(r).expect("clap yields four root values"));
    let root = validate_root(requested).map_err(|e| fail_descartes(stderr, &e))?;
    let n = 10_i64.pow(k);
    let filename = packing_filename(k, root);
    // Open first: a path or permission error must not cost a computation.
    let file = File::create(out_dir.join(&filename))
        .map_err(|e| fail(stderr, format!("cannot write {filename}: {e}"), 1))?;
    let start = Instant::now();
    let (count, bitmap) = pack(root, n).map_err(|e| fail_descartes(stderr, &e))?;
    let curvatures = distinct(&bitmap);
    let mut writer = BufWriter::new(file);
    for curvature in &curvatures {
        writeln!(writer, "{curvature}")?;
    }
    writer.flush()?;
    let elapsed = start.elapsed().as_secs_f64();
    if args.show {
        for curvature in &curvatures {
            writeln!(stdout, "{curvature}")?;
        }
    }
    writeln!(stdout, "root {} {} {} {}", root[0], root[1], root[2], root[3])?;
    writeln!(stdout, "circles {count}")?;
    writeln!(stdout, "distinct {}", curvatures.len())?;
    writeln!(stdout, "Saved to {filename}")?;
    writeln!(stderr, "Elapsed: {elapsed:.2}s")?;
    if count > 0 && !args.no_draw {
        let (width, _) = canvas_size(term);
        let limit = n.min(DRAW_LIMIT_PER_COLUMN * width as i64);
        let bounding = root_centres(root).map_err(|e| fail_descartes(stderr, &e))?[0];
        let mut circles = vec![bounding];
        circles.extend(visible(root, limit).map_err(|e| fail_descartes(stderr, &e))?);
        draw(&circles, term, stdout, stderr)?;
    }
    Ok(())
}

/// Parse, validate and dispatch; every early stop carries its exit code.
fn dispatch<R: BufRead, W: Write, E: Write>(
    argv: impl IntoIterator<Item = OsString>,
    stdin: &mut R,
    term: &Terminal,
    out_dir: &Path,
    stdout: &mut W,
    stderr: &mut E,
) -> Result<(), Stop> {
    let mut args = match Args::try_parse_from(argv) {
        Ok(args) => args,
        Err(error) => return Err(show_clap_error(&error, stdout, stderr)),
    };
    if let Err(message) = check_modes(&mut args, term.stdin_is_tty) {
        return Err(say(stderr, usage_error(&message).trim_end(), 2));
    }
    match args.solve.take() {
        Some(given) => run_solve(&args, &given, term, stdout, stderr),
        None => run_packing(&args, stdin, term, out_dir, stdout, stderr),
    }
}

/// Print a clap error (help and version go to stdout) and stop with clap's exit code.
fn show_clap_error<W: Write, E: Write>(
    error: &clap::Error,
    stdout: &mut W,
    stderr: &mut E,
) -> Stop {
    let sink: &mut dyn Write = if error.use_stderr() { stderr } else { stdout };
    match write!(sink, "{error}") {
        Ok(()) => Stop::Code(error.exit_code()),
        Err(io_error) => Stop::Io(io_error),
    }
}

/// Run the CLI: all logic, with I/O, the terminal and the output directory injected.
/// Returns the exit code (0 done, 1 no answer, 2 bad input).
fn run<R: BufRead, W: Write, E: Write>(
    argv: impl IntoIterator<Item = OsString>,
    stdin: &mut R,
    term: &Terminal,
    out_dir: &Path,
    stdout: &mut W,
    stderr: &mut E,
) -> io::Result<i32> {
    let outcome = dispatch(argv, stdin, term, out_dir, stdout, stderr);
    stdout.flush()?;
    match outcome {
        Ok(()) => Ok(0),
        Err(Stop::Code(code)) => Ok(code),
        Err(Stop::Io(error)) => Err(error),
    }
}

/// `main` is excluded from coverage by `#[cfg(not(tarpaulin_include))]`. The terminal-size
/// query is a closure inside it, so it adds no function for cargo-mutants to mutate;
/// `stty_size` and `pick_size` hold the tested logic.
#[cfg(not(tarpaulin_include))]
fn main() {
    let term = Terminal {
        stdin_is_tty: io::stdin().is_terminal(),
        stdout_size: io::stdout().is_terminal().then(|| {
            let tty = File::open("/dev/tty").ok();
            let stty = tty.and_then(|tty| stty_size(Command::new("stty"), Stdio::from(tty)));
            let columns = env::var("COLUMNS").ok();
            pick_size(columns.as_deref(), env::var("LINES").ok().as_deref(), stty)
        }),
    };
    let mut stdout = BufWriter::new(io::stdout().lock());
    let outcome = run(
        env::args_os(),
        &mut io::stdin().lock(),
        &term,
        Path::new("."),
        &mut stdout,
        &mut io::stderr().lock(),
    );
    let code = outcome.unwrap_or_else(|error| {
        eprintln!("Error: {error}");
        1
    });
    drop(stdout);
    process::exit(code);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    const PIPED: Terminal = Terminal { stdin_is_tty: false, stdout_size: None };

    struct Outcome {
        code: i32,
        stdout: String,
        stderr: String,
    }

    fn argv(args: &[&str]) -> Vec<OsString> {
        std::iter::once("descartes").chain(args.iter().copied()).map(OsString::from).collect()
    }

    fn run_in(args: &[&str], stdin: &str, term: &Terminal, dir: &Path) -> Outcome {
        let mut out = Vec::<u8>::new();
        let mut err = Vec::<u8>::new();
        let code = run(argv(args), &mut stdin.as_bytes(), term, dir, &mut out, &mut err).unwrap();
        Outcome {
            code,
            stdout: String::from_utf8(out).unwrap(),
            stderr: String::from_utf8(err).unwrap(),
        }
    }

    /// Run piped in a fresh directory; returns the outcome and the directory.
    fn piped(args: &[&str]) -> (Outcome, tempfile::TempDir) {
        let dir = tempfile::tempdir().unwrap();
        (run_in(args, "", &PIPED, dir.path()), dir)
    }

    fn has_line(text: &str, line: &str) -> bool {
        text.lines().any(|l| l == line)
    }

    fn braille_lines(text: &str) -> Vec<&str> {
        text.lines().filter(|l| l.chars().any(|c| ('\u{2800}'..='\u{28ff}').contains(&c))).collect()
    }

    fn is_blank(line: &str) -> bool {
        line.chars().all(|c| c == '\u{2800}')
    }

    fn read(dir: &tempfile::TempDir, name: &str) -> String {
        std::fs::read_to_string(dir.path().join(name)).unwrap()
    }

    fn no_files(dir: &tempfile::TempDir) -> bool {
        std::fs::read_dir(dir.path()).unwrap().next().is_none()
    }

    // ---- packing ----

    #[test]
    fn packing_prints_root_counts_and_saved_line_in_order() {
        let (o, dir) = piped(&["3", "--no-draw"]);
        assert_eq!(o.code, 0);
        assert_eq!(
            o.stdout,
            "root -1 2 2 3\ncircles 3328\ndistinct 324\nSaved to descartes_1e3.txt\n"
        );
        let file = read(&dir, "descartes_1e3.txt");
        assert_eq!(file.lines().count(), 324);
        assert!(file.starts_with("2\n3\n6\n11\n14\n15\n18\n23\n26\n27\n30\n"));
        assert!(file.ends_with('\n'));
    }

    #[test]
    fn elapsed_goes_to_stderr_only_with_two_decimals() {
        let (o, _dir) = piped(&["1", "--no-draw"]);
        assert!(!o.stdout.contains("Elapsed"), "{}", o.stdout);
        let line = o.stderr.strip_suffix("s\n").and_then(|s| s.strip_prefix("Elapsed: ")).unwrap();
        let (whole, fraction) = line.split_once('.').unwrap();
        assert!(whole.parse::<u32>().is_ok(), "{line}");
        assert_eq!(fraction.len(), 2, "{line}");
    }

    #[test]
    fn other_root_names_the_file_with_the_root() {
        let (o, dir) = piped(&["3", "--root", "-2", "3", "6", "7", "--no-draw"]);
        assert_eq!(o.code, 0);
        assert_eq!(
            o.stdout,
            "root -2 3 6 7\ncircles 1300\ndistinct 297\nSaved to descartes_1e3_root_-2_3_6_7.txt\n"
        );
        assert_eq!(read(&dir, "descartes_1e3_root_-2_3_6_7.txt").lines().count(), 297);
    }

    #[test]
    fn unreduced_root_gives_the_default_packing_and_file_name() {
        let (a, dir_a) = piped(&["3", "--root", "-1", "2", "3", "6", "--no-draw"]);
        let (b, dir_b) = piped(&["3", "--no-draw"]);
        assert_eq!(a.code, 0);
        assert_eq!(a.stdout, b.stdout);
        assert_eq!(read(&dir_a, "descartes_1e3.txt"), read(&dir_b, "descartes_1e3.txt"));
        let (c, _dir) = piped(&["3", "--root", "-1", "3", "6", "14", "--no-draw"]);
        assert_eq!(c.stdout, b.stdout);
    }

    #[test]
    fn empty_packing_writes_an_empty_file_and_draws_nothing() {
        let (o, dir) = piped(&["1", "--root", "-11", "21", "24", "28"]);
        assert_eq!(o.code, 0);
        assert_eq!(
            o.stdout,
            "root -11 21 24 28\ncircles 0\ndistinct 0\nSaved to descartes_1e1_root_-11_21_24_28.txt\n"
        );
        assert_eq!(read(&dir, "descartes_1e1_root_-11_21_24_28.txt"), "");
    }

    #[test]
    fn show_echoes_the_file_before_the_summary() {
        let (o, dir) = piped(&["1", "--show", "--no-draw"]);
        let file = read(&dir, "descartes_1e1.txt");
        assert!(file.lines().count() > 1);
        assert!(o.stdout.starts_with(&file), "{}", o.stdout);
        assert!(o.stdout[file.len()..].starts_with("root -1 2 2 3\n"));
    }

    #[test]
    fn smoke_runs_k_2_and_never_echoes() {
        let (o, dir) = piped(&["--smoke", "--show", "--no-draw"]);
        assert_eq!(o.code, 0);
        assert_eq!(
            o.stdout,
            "root -1 2 2 3\ncircles 168\ndistinct 33\nSaved to descartes_1e2.txt\n"
        );
        assert_eq!(read(&dir, "descartes_1e2.txt").lines().count(), 33);
    }

    #[test]
    fn yes_is_accepted_and_ignored() {
        let (o, _dir) = piped(&["1", "--yes", "--no-draw"]);
        assert_eq!(o.code, 0);
        assert!(o.stdout.starts_with("root -1 2 2 3\n"));
    }

    #[test]
    fn piped_drawing_is_24_lines_of_60_cells_and_not_blank() {
        let (o, _dir) = piped(&["2"]);
        assert_eq!(o.code, 0);
        let drawing = braille_lines(&o.stdout);
        assert_eq!(drawing.len(), 24);
        assert!(drawing.iter().all(|l| l.chars().count() == 60));
        assert!(drawing.iter().any(|l| !is_blank(l)));
        assert!(o.stdout.lines().take(4).all(|l| braille_lines(l).is_empty()));
    }

    #[test]
    fn no_draw_prints_no_braille() {
        let (o, _dir) = piped(&["2", "--no-draw"]);
        assert!(braille_lines(&o.stdout).is_empty());
    }

    /// The drawing of the packing for a canvas, built from the library with a literal limit.
    fn expected_drawing(width: usize, height: usize, limit: i64) -> String {
        let root = DEFAULT_ROOT;
        let mut circles = vec![root_centres(root).unwrap()[0]];
        circles.extend(visible(root, limit).unwrap());
        render(&circles, width, height).unwrap().join("\n") + "\n"
    }

    fn drawing_of(o: &Outcome) -> String {
        braille_lines(&o.stdout).iter().map(|l| format!("{l}\n")).collect()
    }

    fn on_terminal(args: &[&str], columns: usize, lines: usize) -> Outcome {
        let dir = tempfile::tempdir().unwrap();
        let term = Terminal { stdin_is_tty: true, stdout_size: Some((columns, lines)) };
        run_in(args, "", &term, dir.path())
    }

    #[test]
    fn terminal_canvas_is_its_size_one_row_short() {
        let o = on_terminal(&["2"], 100, 31);
        let drawing = braille_lines(&o.stdout);
        assert_eq!(drawing.len(), 30);
        assert!(drawing.iter().all(|l| l.chars().count() == 100));
    }

    #[test]
    fn drawing_limit_is_four_times_the_width_and_capped_by_n() {
        // width 10: limit 40 < n = 1000
        let a = on_terminal(&["3"], 10, 13);
        assert_eq!(drawing_of(&a), expected_drawing(10, 12, 40));
        assert_ne!(expected_drawing(10, 12, 40), expected_drawing(10, 12, 20));
        assert_ne!(expected_drawing(10, 12, 40), expected_drawing(10, 12, 80));
        // width 60: limit 240 > n = 10, so n caps it
        let b = on_terminal(&["1"], 60, 25);
        assert_eq!(drawing_of(&b), expected_drawing(60, 24, 10));
        assert_ne!(expected_drawing(60, 24, 10), expected_drawing(60, 24, 240));
    }

    #[test]
    fn canvas_clamps_at_both_ends() {
        let t =
            |columns, lines| Terminal { stdin_is_tty: true, stdout_size: Some((columns, lines)) };
        assert_eq!(canvas_size(&PIPED), (60, 24));
        assert_eq!(canvas_size(&t(0, 0)), (1, 1));
        assert_eq!(canvas_size(&t(1, 1)), (1, 1));
        assert_eq!(canvas_size(&t(1, 2)), (1, 1));
        assert_eq!(canvas_size(&t(1, 3)), (1, 2));
        assert_eq!(canvas_size(&t(1000, 500)), (1000, 499));
        assert_eq!(canvas_size(&t(1001, 501)), (1000, 500));
        assert_eq!(canvas_size(&t(100_000, 100_000)), (1000, 500));
        assert_eq!(canvas_size(&t(80, 24)), (80, 23));
    }

    #[test]
    fn a_one_by_one_terminal_still_draws() {
        let o = on_terminal(&["1"], 0, 0);
        assert_eq!(o.code, 0);
        assert_eq!(braille_lines(&o.stdout).len(), 1);
    }

    // ---- K and the prompt ----

    #[test]
    fn k_out_of_range_exits_2_naming_the_range_and_writes_nothing() {
        for (k, got) in [("0", "0"), ("9", "9"), ("-1", "-1"), ("100", "100")] {
            let (o, dir) = piped(&[k]);
            assert_eq!(o.code, 2, "{k}");
            assert_eq!(o.stderr, format!("K must be between 1 and 8, got {got}.\n"));
            assert_eq!(o.stdout, "");
            assert!(no_files(&dir));
        }
    }

    #[test]
    fn k_boundaries_one_and_eight_are_accepted() {
        let (o, _dir) = piped(&["1", "--no-draw"]);
        assert_eq!(o.code, 0);
        // K = 8 would run about 1.1e10 circles: an unwritable directory stops it at the
        // open, before pack, so this also proves the file is opened first.
        let missing: PathBuf = tempfile::tempdir().unwrap().path().join("gone");
        let o = run_in(&["8", "--no-draw"], "", &PIPED, &missing);
        assert_eq!(o.code, 1);
        assert_eq!(o.stdout, "");
        assert!(o.stderr.starts_with("Error: cannot write descartes_1e8.txt: "), "{}", o.stderr);
        assert_eq!(o.stderr.lines().count(), 1);
    }

    #[test]
    fn non_integer_k_is_a_usage_error() {
        let (o, _dir) = piped(&["abc"]);
        assert_eq!(o.code, 2);
        let line = "error: invalid value 'abc' for '[K]': invalid digit found in string";
        assert!(has_line(&o.stderr, line), "{}", o.stderr);
        assert_eq!(o.stdout, "");
    }

    #[test]
    fn missing_k_without_a_terminal_is_a_usage_error() {
        let (o, dir) = piped(&[]);
        assert_eq!(o.code, 2);
        assert!(has_line(&o.stderr, "error: K is required when stdin is not a terminal"));
        assert!(o.stderr.contains("Usage:"));
        assert!(no_files(&dir));
    }

    fn at_terminal(args: &[&str], stdin: &str) -> (Outcome, tempfile::TempDir) {
        let dir = tempfile::tempdir().unwrap();
        let term = Terminal { stdin_is_tty: true, stdout_size: None };
        (run_in(args, stdin, &term, dir.path()), dir)
    }

    #[test]
    fn prompt_reads_k_from_stdin() {
        let (o, dir) = at_terminal(&["--no-draw"], "1\n");
        assert_eq!(o.code, 0);
        let prompt = "Enter exponent K (limit = 10^K, max 8): ";
        assert!(o.stdout.starts_with(&format!("{prompt}root -1 2 2 3\n")), "{}", o.stdout);
        assert!(dir.path().join("descartes_1e1.txt").exists());
    }

    #[test]
    fn prompt_tolerates_whitespace_and_crlf() {
        let (o, _dir) = at_terminal(&["--no-draw"], "  2 \r\n");
        assert_eq!(o.code, 0);
        assert!(o.stdout.contains("circles 168\n"), "{}", o.stdout);
    }

    #[test]
    fn prompt_end_of_input_exits_1_naming_the_remedy() {
        let (o, dir) = at_terminal(&[], "");
        assert_eq!(o.code, 1);
        assert_eq!(o.stdout, "Enter exponent K (limit = 10^K, max 8): \n");
        assert_eq!(o.stderr, "Error: no input; pass K as an argument (e.g. descartes 2).\n");
        assert!(no_files(&dir));
    }

    const PROMPT: &str = "Enter exponent K (limit = 10^K, max 8): ";

    #[test]
    fn reprompt_after_non_integer() {
        let (o, _dir) = at_terminal(&["--no-draw"], "abc\n3\n");
        assert_eq!(o.code, 0);
        assert_eq!(o.stderr.matches("Invalid input: 'abc' is not an integer K.\n").count(), 1);
        assert!(
            o.stderr.starts_with("Invalid input: 'abc' is not an integer K.\n"),
            "{}",
            o.stderr
        );
        assert_eq!(o.stdout.matches(PROMPT).count(), 2, "{}", o.stdout);
    }

    #[test]
    fn reprompt_after_out_of_range() {
        let (o, _dir) = at_terminal(&["--no-draw"], "9\n3\n");
        assert_eq!(o.code, 0);
        assert_eq!(o.stderr.matches("K must be between 1 and 8, got 9.\n").count(), 1);
        assert!(o.stderr.starts_with("K must be between 1 and 8, got 9.\n"), "{}", o.stderr);
        assert_eq!(o.stdout.matches(PROMPT).count(), 2, "{}", o.stdout);
    }

    #[test]
    fn reprompt_then_end_of_input_exits_1() {
        let (o, dir) = at_terminal(&[], "abc\n");
        assert_eq!(o.code, 1);
        let want = "Invalid input: 'abc' is not an integer K.\n\
                    Error: no input; pass K as an argument (e.g. descartes 2).\n";
        assert_eq!(o.stderr, want);
        assert_eq!(o.stdout.matches(PROMPT).count(), 2, "{}", o.stdout);
        assert!(no_files(&dir));
    }

    #[test]
    fn reprompt_tolerates_crlf_between_answers() {
        let (o, _dir) = at_terminal(&["--no-draw"], "x\r\n3\r\n");
        assert_eq!(o.code, 0);
        assert_eq!(o.stderr.matches("Invalid input: 'x' is not an integer K.\n").count(), 1);
        assert!(o.stdout.contains("Saved to descartes_1e3.txt"), "{}", o.stdout);
    }

    #[test]
    fn k_argument_out_of_range_exits_2_without_prompting() {
        let (o, _dir) = at_terminal(&["9"], "3\n");
        assert_eq!(o.code, 2);
        assert_eq!(o.stderr, "K must be between 1 and 8, got 9.\n");
        assert!(!o.stdout.contains("Enter exponent"));
    }

    #[test]
    fn a_given_k_never_prompts() {
        let (o, _dir) = at_terminal(&["1", "--no-draw"], "");
        assert_eq!(o.code, 0);
        assert!(!o.stdout.contains("Enter exponent"));
    }

    // ---- --root ----

    #[test]
    fn root_failing_the_descartes_relation_exits_1_naming_it() {
        let (o, dir) = piped(&["1", "--root", "-1", "2", "2", "4"]);
        assert_eq!(o.code, 1);
        assert!(o.stderr.starts_with("Error: "), "{}", o.stderr);
        assert!(o.stderr.contains("(-1, 2, 2, 4)"), "{}", o.stderr);
        assert_eq!(o.stdout, "");
        assert!(no_files(&dir));
    }

    #[test]
    fn root_without_exactly_one_negative_exits_1() {
        let (o, _dir) = piped(&["1", "--root", "0", "0", "1", "1"]);
        assert_eq!(o.code, 1);
        assert!(o.stderr.starts_with("Error: "), "{}", o.stderr);
        assert!(o.stderr.contains("(0, 0, 1, 1)"), "{}", o.stderr);
    }

    #[test]
    fn non_integer_root_value_is_a_usage_error() {
        let (o, _dir) = piped(&["1", "--root", "-1", "2", "2", "x"]);
        assert_eq!(o.code, 2);
        let line =
            "error: invalid value 'x' for '--root <A> <B> <C> <D>': invalid digit found in string";
        assert!(has_line(&o.stderr, line), "{}", o.stderr);
    }

    #[test]
    fn root_with_too_few_values_is_a_usage_error() {
        let (o, _dir) = piped(&["1", "--root", "-1", "2", "2"]);
        assert_eq!(o.code, 2);
        assert!(o.stderr.starts_with("error: "), "{}", o.stderr);
    }

    #[test]
    fn root_above_the_cap_exits_2_and_the_cap_itself_is_not_refused_as_too_big() {
        let (o, dir) = piped(&["1", "--root", "-1", "2", "2", "100000001"]);
        assert_eq!(o.code, 2);
        assert!(o.stderr.starts_with("Error: "), "{}", o.stderr);
        assert!(no_files(&dir));
    }

    #[test]
    fn root_at_the_cap_is_not_refused_as_too_big() {
        let (o, _dir) = piped(&["1", "--root", "-1", "2", "2", "100000000"]);
        assert_eq!(o.code, 1);
        assert!(!o.stderr.contains("at most 10^8"), "{}", o.stderr);
    }

    #[test]
    fn the_default_root_given_explicitly_exits_0() {
        let (o, _dir) = piped(&["1", "--root", "-1", "2", "2", "3", "--no-draw"]);
        assert_eq!(o.code, 0);
    }

    #[test]
    fn repeated_root_keeps_the_last_one_as_python_does() {
        let (o, dir) = piped(&[
            "1",
            "--root",
            "-11",
            "21",
            "24",
            "28",
            "--root",
            "-11",
            "21",
            "24",
            "28",
            "--no-draw",
        ]);
        assert_eq!(o.code, 0, "{}", o.stderr);
        assert!(o.stdout.starts_with("root -11 21 24 28\n"), "{}", o.stdout);
        assert!(!no_files(&dir));
        let (o, _dir) = piped(&["1", "--root", "-1", "2", "2", "3", "--root", "-2", "3", "6", "7"]);
        assert_eq!(o.code, 0, "{}", o.stderr);
        assert!(o.stdout.starts_with("root -2 3 6 7\n"), "{}", o.stdout);
    }

    #[test]
    fn repeated_solve_keeps_the_last_one_as_python_does() {
        let (o, _dir) = piped(&[
            "--solve",
            "-1,0,0",
            "2,0.5,0",
            "3,0,0.6666666666666666",
            "--solve",
            "9,9,9",
            "1,1,1",
            "2,2,2",
        ]);
        assert_eq!(o.code, 1, "{}", o.stderr);
        assert!(o.stderr.contains("circles 1 and 2 are not tangent"), "{}", o.stderr);
        assert_eq!(o.stdout, "");
    }

    #[test]
    fn unwritable_directory_exits_1_before_any_output() {
        let missing = tempfile::tempdir().unwrap().path().join("gone");
        let o = run_in(&["1"], "", &PIPED, &missing);
        assert_eq!(o.code, 1);
        assert_eq!(o.stdout, "");
    }

    // ---- --solve ----

    const R9: [&str; 4] = ["--solve", "-1,0,0", "2,0.5,0", "3,0,0.6666666666666666"];

    fn solve_args<'a>(extra: &[&'a str]) -> Vec<&'a str> {
        R9.iter().copied().chain(extra.iter().copied()).collect()
    }

    #[test]
    fn solve_prints_the_table_at_full_precision() {
        let (o, _dir) = piped(&solve_args(&["--no-draw"]));
        assert_eq!(o.code, 0, "{}", o.stderr);
        let expected = "\
kind      #  curvature  radius               x     y
given     1  -1         -1                   0     0
given     2  2          0.5                  0.5   0
given     3  3          0.3333333333333333   0     0.6666666666666666
solution  1  2          0.5                  -0.5  0
solution  2  6          0.16666666666666666  0.5   0.6666666666666666
";
        assert_eq!(o.stdout, expected);
        assert_eq!(o.stderr, "");
    }

    #[test]
    fn solve_precision_rounds_the_display_only() {
        let (o, _dir) = piped(&solve_args(&["--precision", "4", "--no-draw"]));
        assert_eq!(o.code, 0);
        assert!(o.stdout.contains("0.6667"), "{}", o.stdout);
        let rows: Vec<Vec<&str>> =
            o.stdout.lines().skip(1).map(|l| l.split_whitespace().collect()).collect();
        let curvatures: Vec<&str> = rows.iter().map(|r| r[2]).collect();
        assert_eq!(curvatures, ["-1.0000", "2.0000", "3.0000", "2.0000", "6.0000"]);
    }

    #[test]
    fn solve_precision_bounds() {
        for p in ["0", "17"] {
            let (o, _dir) = piped(&solve_args(&["--precision", p, "--no-draw"]));
            assert_eq!(o.code, 0, "{p}");
        }
        for p in ["18", "-1"] {
            let (o, _dir) = piped(&solve_args(&["--precision", p, "--no-draw"]));
            assert_eq!(o.code, 2, "{p}");
            assert!(
                has_line(&o.stderr, "error: --precision must be between 0 and 17"),
                "{}",
                o.stderr
            );
            assert_eq!(o.stdout, "");
        }
        let (o, _dir) = piped(&solve_args(&["--precision", "0", "--no-draw"]));
        assert!(o.stdout.lines().nth(1).unwrap().starts_with("given     1  -1 "), "{}", o.stdout);
    }

    #[test]
    fn solve_accepts_a_leading_negative_curvature() {
        let (o, _dir) = piped(&["--solve", "-1,0,0", "2,0.5,0", "3,0,0.6666666666666666"]);
        assert_eq!(o.code, 0, "{}", o.stderr);
    }

    #[test]
    fn solve_draws_24_by_60_unless_no_draw() {
        let (o, _dir) = piped(&R9);
        assert_eq!(o.code, 0);
        let drawing = braille_lines(&o.stdout);
        assert_eq!(drawing.len(), 24);
        assert!(drawing.iter().all(|l| l.chars().count() == 60));
        assert!(drawing.iter().any(|l| !is_blank(l)));
        assert_eq!(o.stdout.lines().count(), 6 + 24);
    }

    #[test]
    fn solve_draws_the_three_given_and_the_solutions() {
        let o = on_terminal(&R9, 40, 21);
        let all: Vec<Circle> = vec![
            (-1.0, 0.0, 0.0),
            (2.0, 0.5, 0.0),
            (3.0, 0.0, 0.6666666666666666),
            (2.0, -0.5, 0.0),
            (6.0, 0.5, 0.6666666666666666),
        ];
        let expected: String =
            render(&all, 40, 20).unwrap().iter().map(|l| format!("{l}\n")).collect();
        assert_eq!(drawing_of(&o), expected);
    }

    #[test]
    fn solve_non_tangent_exits_1_naming_the_circles_and_the_remedy() {
        let (o, _dir) = piped(&["--solve", "-1,0,0", "2,0.5,0", "3,0,0.6667"]);
        assert_eq!(o.code, 1);
        assert!(o.stderr.starts_with("Error: "), "{}", o.stderr);
        assert!(o.stderr.contains("circles 1 and 3 are not tangent"), "{}", o.stderr);
        assert!(o.stderr.contains("full-precision"), "{}", o.stderr);
        assert_eq!(o.stdout, "");
    }

    #[test]
    fn solve_zero_curvature_exits_2() {
        let (o, _dir) = piped(&["--solve", "0,0,0", "2,0.5,0", "3,0,0.6666666666666666"]);
        assert_eq!(o.code, 2);
        assert!(o.stderr.starts_with("Error: "), "{}", o.stderr);
    }

    #[test]
    fn solve_nan_exits_2() {
        let (o, _dir) = piped(&["--solve", "nan,0,0", "2,0.5,0", "3,0,0.6666666666666666"]);
        assert_eq!(o.code, 2);
        assert!(o.stderr.starts_with("Error: "), "{}", o.stderr);
    }

    #[test]
    fn solve_unparsable_triples_are_usage_errors() {
        let (o, _dir) = piped(&["--solve", "1,2", "2,0.5,0", "3,0,0.6"]);
        assert_eq!(o.code, 2);
        assert!(
            o.stderr.lines().any(|l| l.ends_with("'1,2' is not K,X,Y (three values)")),
            "{}",
            o.stderr
        );
        let (o, _dir) = piped(&["--solve", "1,2,x", "2,0.5,0", "3,0,0.6"]);
        assert_eq!(o.code, 2);
        assert!(
            o.stderr.lines().any(|l| l.ends_with("'1,2,x' is not K,X,Y (values must be numbers)")),
            "{}",
            o.stderr
        );
    }

    #[test]
    fn solve_with_too_few_triples_is_a_usage_error() {
        let (o, _dir) = piped(&["--solve", "-1,0,0", "2,0.5,0"]);
        assert_eq!(o.code, 2);
        assert!(o.stderr.starts_with("error: "), "{}", o.stderr);
    }

    // ---- mode flags ----

    #[test]
    fn solve_rejects_every_packing_flag_in_order() {
        let (o, _dir) =
            piped(&solve_args(&["3", "--root", "-1", "2", "2", "3", "--smoke", "--show", "--yes"]));
        assert_eq!(o.code, 2);
        assert!(
            has_line(&o.stderr, "error: --solve takes no K, --root, --smoke, --show, --yes"),
            "{}",
            o.stderr
        );
        for (flag, name) in [("--smoke", "--smoke"), ("--show", "--show"), ("--yes", "--yes")] {
            let (o, _dir) = piped(&solve_args(&[flag]));
            assert_eq!(o.code, 2, "{flag}");
            assert!(
                has_line(&o.stderr, &format!("error: --solve takes no {name}")),
                "{}",
                o.stderr
            );
        }
        let (o, _dir) = piped(&solve_args(&["--root", "-1", "2", "2", "3"]));
        assert!(has_line(&o.stderr, "error: --solve takes no --root"), "{}", o.stderr);
        let (o, _dir) = piped(&["5", "--solve", "-1,0,0", "2,0.5,0", "3,0,0.6666666666666666"]);
        assert!(has_line(&o.stderr, "error: --solve takes no K"), "{}", o.stderr);
    }

    #[test]
    fn precision_needs_solve() {
        let (o, dir) = piped(&["2", "--precision", "3"]);
        assert_eq!(o.code, 2);
        assert!(has_line(&o.stderr, "error: --precision needs --solve"), "{}", o.stderr);
        assert!(no_files(&dir));
    }

    #[test]
    fn precision_range_is_checked_before_the_missing_solve() {
        let (o, _dir) = piped(&["2", "--precision", "99"]);
        assert!(has_line(&o.stderr, "error: --precision must be between 0 and 17"), "{}", o.stderr);
    }

    #[test]
    fn smoke_takes_no_k() {
        let (o, dir) = piped(&["--smoke", "3"]);
        assert_eq!(o.code, 2);
        assert!(has_line(&o.stderr, "error: --smoke takes no K"), "{}", o.stderr);
        assert!(no_files(&dir));
    }

    #[test]
    fn help_goes_to_stdout_and_exits_0() {
        let (o, _dir) = piped(&["--help"]);
        assert_eq!(o.code, 0);
        assert!(o.stdout.contains("Usage:"));
        assert!(o.stdout.contains("depends on terminal width"));
        assert!(o.stdout.contains("2.6e7"));
        assert_eq!(o.stderr, "");
    }

    #[test]
    fn unknown_flag_is_a_usage_error() {
        let (o, _dir) = piped(&["--bogus"]);
        assert_eq!(o.code, 2);
        assert!(has_line(&o.stderr, "error: unexpected argument '--bogus' found"), "{}", o.stderr);
    }

    // ---- I/O failures ----

    struct Full;

    impl Write for Full {
        fn write(&mut self, _: &[u8]) -> io::Result<usize> {
            Err(io::Error::other("full"))
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    #[test]
    fn a_failing_stdout_is_an_io_error() {
        let dir = tempfile::tempdir().unwrap();
        let result = run(
            argv(&["1", "--no-draw"]),
            &mut "".as_bytes(),
            &PIPED,
            dir.path(),
            &mut Full,
            &mut Vec::new(),
        );
        assert!(result.is_err());
    }

    #[test]
    fn a_failing_stderr_is_an_io_error() {
        let dir = tempfile::tempdir().unwrap();
        let result =
            run(argv(&["0"]), &mut "".as_bytes(), &PIPED, dir.path(), &mut Vec::new(), &mut Full);
        assert!(result.is_err());
        let result = run(
            argv(&["1", "--root", "-1", "2", "2", "4"]),
            &mut "".as_bytes(),
            &PIPED,
            dir.path(),
            &mut Vec::new(),
            &mut Full,
        );
        assert!(result.is_err());
    }

    #[test]
    fn a_failing_stdout_cannot_hide_a_help_or_usage_error() {
        let dir = tempfile::tempdir().unwrap();
        let help = run(
            argv(&["--help"]),
            &mut "".as_bytes(),
            &PIPED,
            dir.path(),
            &mut Full,
            &mut Vec::new(),
        );
        assert!(help.is_err());
        let usage = run(
            argv(&["--bogus"]),
            &mut "".as_bytes(),
            &PIPED,
            dir.path(),
            &mut Vec::new(),
            &mut Full,
        );
        assert!(usage.is_err());
    }

    // ---- helpers ----

    #[test]
    fn format_value_full_precision_is_the_shortest_round_trip() {
        assert_eq!(format_value(0.5, None), "0.5");
        assert_eq!(format_value(2.0, None), "2");
        assert_eq!(format_value(-1.0, None), "-1");
        assert_eq!(format_value(1.0 / 3.0, None), "0.3333333333333333");
    }

    #[test]
    fn format_value_never_prints_negative_zero() {
        assert_eq!(format_value(-0.0, None), "0");
        assert_eq!(format_value(0.0, None), "0");
        assert_eq!(format_value(-0.0, Some(2)), "0.00");
        assert_eq!(format_value(-0.001, Some(2)), "0.00");
        assert_eq!(format_value(-0.004, Some(0)), "0");
    }

    #[test]
    fn format_value_keeps_real_negatives() {
        assert_eq!(format_value(-1.5, Some(2)), "-1.50");
        assert_eq!(format_value(-0.006, Some(2)), "-0.01");
        assert_eq!(format_value(0.006, Some(2)), "0.01");
    }

    #[test]
    fn table_columns_align_with_no_trailing_space() {
        let lines = table_lines(&[(2.0, 0.5, 0.0)], &[(-1.0, 0.0, 10.0)], Some(1));
        assert_eq!(
            lines,
            [
                "kind      #  curvature  radius  x    y",
                "given     1  2.0        0.5     0.5  0.0",
                "solution  1  -1.0       -1.0    0.0  10.0",
            ]
        );
    }

    #[test]
    fn table_with_no_solution_rows_has_the_header_and_given_only() {
        let lines = table_lines(&[(2.0, 0.0, 0.0)], &[], None);
        assert_eq!(lines.len(), 2);
        assert!(lines.iter().all(|l| l == l.trim_end()));
    }

    #[test]
    fn parse_circle_accepts_signed_and_spaced_numbers() {
        assert_eq!(parse_circle("-1,0,0"), Ok((-1.0, 0.0, 0.0)));
        assert_eq!(parse_circle(" 2 , 0.5 ,1e-1"), Ok((2.0, 0.5, 0.1)));
        assert!(parse_circle("1,2,3,4").is_err());
        assert!(parse_circle("").is_err());
        assert!(parse_circle("1,2,").is_err());
    }

    #[test]
    fn packing_filename_includes_a_non_default_root() {
        assert_eq!(packing_filename(4, DEFAULT_ROOT), "descartes_1e4.txt");
        assert_eq!(packing_filename(1, [-2, 3, 6, 7]), "descartes_1e1_root_-2_3_6_7.txt");
        assert_eq!(packing_filename(3, [-3, 4, 12, 13]), "descartes_1e3_root_-3_4_12_13.txt");
    }

    #[test]
    fn stty_output_is_rows_then_columns() {
        assert_eq!(parse_stty_size("30 100\n"), Some((100, 30)));
        assert_eq!(parse_stty_size("0 0"), Some((0, 0)));
        assert_eq!(parse_stty_size(""), None);
        assert_eq!(parse_stty_size("30"), None);
        assert_eq!(parse_stty_size("a b"), None);
        assert_eq!(parse_stty_size("30 b"), None);
    }

    #[test]
    fn pick_size_prefers_environment_then_stty_then_fallback() {
        assert_eq!(pick_size(Some("120"), Some("40"), Some((100, 30))), (120, 40));
        assert_eq!(pick_size(None, None, Some((100, 30))), (100, 30));
        assert_eq!(pick_size(None, None, None), (80, 24));
        // each dimension on its own
        assert_eq!(pick_size(Some("120"), None, Some((100, 30))), (120, 30));
        assert_eq!(pick_size(None, Some("40"), Some((100, 30))), (100, 40));
        // zero, negative and junk are not sizes
        assert_eq!(pick_size(Some("0"), Some("0"), Some((100, 30))), (100, 30));
        assert_eq!(pick_size(Some("x"), Some("-5"), Some((0, 0))), (80, 24));
        assert_eq!(pick_size(Some(" 7 "), Some(" 9 "), None), (7, 9));
    }

    /// `sh -c <body> sh`: the later `size` argument becomes `$1`.
    #[cfg(unix)]
    fn fake_stty(body: &str) -> Command {
        let mut command = Command::new("/bin/sh");
        command.args(["-c", body, "sh"]);
        command
    }

    #[cfg(unix)]
    #[test]
    fn stty_size_runs_the_program_with_size_and_parses_it() {
        let ok = fake_stty("[ \"$1\" = size ] && echo '30 100'");
        assert_eq!(stty_size(ok, Stdio::null()), Some((100, 30)));
    }

    #[cfg(unix)]
    #[test]
    fn stty_size_is_none_when_the_program_fails_or_is_missing() {
        assert_eq!(stty_size(fake_stty("echo '30 100'; exit 1"), Stdio::null()), None);
        assert_eq!(stty_size(fake_stty("echo hello"), Stdio::null()), None);
        assert_eq!(stty_size(Command::new("/nonexistent/stty"), Stdio::null()), None);
    }
}
