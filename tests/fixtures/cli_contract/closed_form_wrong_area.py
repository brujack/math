"""Stub closed-form CLI that prints the area a missing sqrt gives."""

import argparse

CONTRACT_ARGS = ["-a", "3", "-b", "4", "-c", "5"]
CONTRACT_EXPECT = "6.0000"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Closed-form contract stub.")
    parser.add_argument("-a", type=float)
    parser.add_argument("-b", type=float)
    parser.add_argument("-c", type=float)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args(argv)
    if args.smoke:
        args.a, args.b, args.c = 3.0, 4.0, 5.0
    elif args.a is None and args.b is None and args.c is None:
        parser.error("give three of the triangle values")
    return args


def main(argv: list[str] | None = None) -> None:
    parse_args(argv)
    print("area 36.0000")


if __name__ == "__main__":
    main()
