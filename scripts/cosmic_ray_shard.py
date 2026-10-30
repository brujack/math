#!/usr/bin/env python3
"""Partition a cosmic-ray session into one shard, in place.

Usage: cosmic_ray_shard.py <session.sqlite> <k> <n>

Sorts mutation_specs by spec key (not job_id, which differs between inits),
keeps the rows whose sorted index i satisfies i % n == k, and deletes the rest
from mutation_specs and work_items in one transaction. Prints `kept K of T`.
Exits 1 with a message on stderr for any invalid input, leaving the file as is.
Defined on a fresh `cosmic-ray init` session only: a session holding results,
or two specs sharing a sort key, is refused.
"""

import pathlib
import re
import sqlite3
import sys

SORT_COLUMNS = (
    "module_path, operator_name, operator_args, occurrence, "
    "start_pos_row, start_pos_col, end_pos_row, end_pos_col"
)


PLAIN_DECIMAL = re.compile(r"0|[1-9][0-9]*")


def fail(message: str) -> int:
    print(f"cosmic_ray_shard: {message}", file=sys.stderr)
    return 1


def shard(path: pathlib.Path, k: int, n: int) -> tuple[int, int]:
    """Trim the session to shard k of n; return (kept, total)."""
    conn = sqlite3.connect(path)
    try:
        with conn:
            if conn.execute("SELECT count(*) FROM work_items").fetchone()[0] == 0:
                raise ValueError("work_items is empty: nothing to shard")
            if conn.execute("SELECT count(*) FROM work_results").fetchone()[0] != 0:
                raise ValueError(
                    "work_results is not empty: session was already executed, "
                    "shard a fresh init only"
                )
            duplicates = conn.execute(
                f"SELECT count(*) FROM (SELECT 1 FROM mutation_specs "
                f"GROUP BY {SORT_COLUMNS} HAVING count(*) > 1)"
            ).fetchone()[0]
            if duplicates:
                raise ValueError(
                    f"duplicate spec key: {duplicates} keys shared by several rows"
                )
            job_ids = [
                row[0]
                for row in conn.execute(
                    f"SELECT job_id FROM mutation_specs ORDER BY {SORT_COLUMNS}"
                )
            ]
            if not job_ids:
                raise ValueError("mutation_specs is empty: nothing to shard")
            doomed = [(j,) for i, j in enumerate(job_ids) if i % n != k]
            conn.executemany("DELETE FROM mutation_specs WHERE job_id = ?", doomed)
            conn.executemany("DELETE FROM work_items WHERE job_id = ?", doomed)
    finally:
        conn.close()
    return len(job_ids) - len(doomed), len(job_ids)


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        return fail("usage: cosmic_ray_shard.py <session.sqlite> <k> <n>")
    path = pathlib.Path(argv[1])
    if not (PLAIN_DECIMAL.fullmatch(argv[2]) and PLAIN_DECIMAL.fullmatch(argv[3])):
        return fail(
            f"k and n must be plain decimal integers, got {argv[2]!r} and {argv[3]!r}"
        )
    k = int(argv[2])
    n = int(argv[3])
    if n < 1:
        return fail(f"n must be >= 1, got {n}")
    if not 0 <= k < n:
        return fail(f"k must be in [0, {n}), got {k}")
    if not path.is_file():
        return fail(f"no such session file: {path}")
    try:
        kept, total = shard(path, k, n)
    except (sqlite3.Error, ValueError) as exc:
        return fail(str(exc))
    print(f"kept {kept} of {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
