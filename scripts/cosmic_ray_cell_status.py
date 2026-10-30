#!/usr/bin/env python3
"""Summarise a finished cosmic-ray session as one verdict line.

Usage: cosmic_ray_cell_status.py <session.sqlite> <label> [--out FILE] [--survivors FILE]

Prints `green: <label> — S surviving, T timed out, K jobs` and exits 0, or
`red: <label> — <reason>` and exits 1. A session is red when it has no work
items, the result count differs from the work-item count, or any result is not
worker_outcome NORMAL with test_outcome KILLED or SURVIVED. Survivors and
timeouts (test_outcome KILLED with output 'timeout') are never red.
cosmic-ray stores enum names uppercase; a differently-cased value is red.
--out also writes the line to FILE; --survivors writes one
`<module_path>:<start_pos_row> <operator_name>` line per survivor, sorted.
"""

import argparse
import pathlib
import sqlite3
import sys

DASH = "—"
GOOD_OUTCOMES = "worker_outcome = 'NORMAL' AND test_outcome IN ('KILLED', 'SURVIVED')"


def count(conn: sqlite3.Connection, sql: str) -> int:
    return int(conn.execute(sql).fetchone()[0])


def assess(conn: sqlite3.Connection, label: str) -> tuple[bool, str]:
    """Return (is_green, verdict line) for an open session."""
    jobs = count(conn, "SELECT count(*) FROM work_items")
    if jobs == 0:
        return False, f"red: {label} {DASH} no work items"
    results = count(conn, "SELECT count(*) FROM work_results")
    if results != jobs:
        return False, f"red: {label} {DASH} {results} results for {jobs} work items"
    bad = conn.execute(
        "SELECT DISTINCT worker_outcome, test_outcome FROM work_results "
        f"WHERE NOT ({GOOD_OUTCOMES}) ORDER BY 1, 2"
    ).fetchall()
    if bad:
        pairs = ", ".join(f"{w}/{t}" for w, t in bad)
        return False, f"red: {label} {DASH} unusable outcomes (worker/test): {pairs}"
    survivors = count(
        conn, "SELECT count(*) FROM work_results WHERE test_outcome = 'SURVIVED'"
    )
    timeouts = count(
        conn,
        "SELECT count(*) FROM work_results "
        "WHERE test_outcome = 'KILLED' AND output = 'timeout'",
    )
    return (
        True,
        f"green: {label} {DASH} {survivors} surviving, {timeouts} timed out, {jobs} jobs",
    )


def survivor_lines(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT m.module_path, m.start_pos_row, m.operator_name "
        "FROM work_results r JOIN mutation_specs m USING (job_id) "
        "WHERE r.test_outcome = 'SURVIVED'"
    ).fetchall()
    return sorted(f"{path}:{row} {op}" for path, row, op in rows)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Summarise a finished cosmic-ray session as one verdict line."
    )
    parser.add_argument("session", type=pathlib.Path)
    parser.add_argument("label")
    parser.add_argument("--out", type=pathlib.Path)
    parser.add_argument("--survivors", type=pathlib.Path)
    args = parser.parse_args(argv)

    survivors: list[str] = []
    if not args.session.is_file():
        green, line = (
            False,
            f"red: {args.label} {DASH} no such session file: {args.session}",
        )
    else:
        try:
            # Read-only: a status check must never alter the session it judges.
            conn = sqlite3.connect(f"file:{args.session}?mode=ro", uri=True)
            try:
                green, line = assess(conn, args.label)
                if green:
                    survivors = survivor_lines(conn)
            finally:
                conn.close()
        except sqlite3.Error as err:
            green, line = False, f"red: {args.label} {DASH} unreadable session: {err}"

    print(line)
    if args.out is not None:
        args.out.write_text(line + "\n", encoding="utf-8")
    if args.survivors is not None and green:
        args.survivors.write_text(
            "".join(f"{s}\n" for s in survivors), encoding="utf-8"
        )
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
