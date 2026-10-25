#!/usr/bin/env python3
"""Stub CLI that exits 0 but writes no output file."""

import argparse

SMOKE_SIZE = 2
LARGE_RUN_THRESHOLD: int | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Contract stub without a threshold.")
    parser.add_argument("size", nargs="?", type=int)
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--yes", action="store_true", help="accepted and ignored")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)
    if args.smoke:
        args.size, args.show = SMOKE_SIZE, False
    elif args.size is None:
        parser.error("SIZE is required when stdin is not a terminal")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    lines = [f"result {i}" for i in range(1, args.size + 1)]
    if args.show:
        print("\n".join(lines))
    print(f"Wrote {len(lines)} results to out.txt")


if __name__ == "__main__":
    main()
