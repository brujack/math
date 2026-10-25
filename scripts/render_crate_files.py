#!/usr/bin/env python3
"""Render every per-crate file from one template, so all 11 crates stay identical.

Usage: render_crate_files.py (--check | --write) [--root DIR] [--kind NAME ...]

Each template in scripts/crate_templates/ is the single source for one file kind;
@CRATE@ is replaced with the crate's directory name and nothing else varies.
Operator rule (2026-10-24): all 11 crates are treated the same, all of the time,
so a per-crate difference is a template change applied to every crate.

--check  exit 1 and list every crate file that differs from its rendered text
--write  rewrite the files that differ; print each one written
"""

import argparse
import pathlib
import re
import sys

CRATES = [
    "amicable",
    "collatz",
    "e",
    "factorial",
    "fib",
    "goldbach",
    "perfect-numbers",
    "pi",
    "prime",
    "sq",
    "twin-primes",
]

# Template file name in scripts/crate_templates/ -> per-crate output path.
KINDS = {
    "Makefile": "{crate}/{crate}-rs/Makefile",
    "rustfmt.toml": "{crate}/{crate}-rs/rustfmt.toml",
    "release.yml": ".github/workflows/release-{crate}-rs.yml",
    "ci.yml": ".github/workflows/{crate}-rs.yml",
    "nextest.toml": "{crate}/{crate}-rs/.config/nextest.toml",
}

PLACEHOLDER = "@CRATE@"
_ANY_PLACEHOLDER = re.compile(r"@[A-Z_]+@")
TEMPLATE_DIR = pathlib.Path("scripts") / "crate_templates"


def render(template, crate):
    """Return template with every @CRATE@ replaced; any other @NAME@ is an error."""
    unknown = sorted(set(_ANY_PLACEHOLDER.findall(template)) - {PLACEHOLDER})
    if unknown:
        raise ValueError(f"unknown placeholder(s) {unknown}; only {PLACEHOLDER} exists")
    return template.replace(PLACEHOLDER, crate)


def _expected(root, kinds):
    """Yield (relative path, rendered text) for every crate file of every kind."""
    for kind, pattern in kinds.items():
        template = (root / TEMPLATE_DIR / kind).read_text()
        for crate in CRATES:
            yield pattern.format(crate=crate), render(template, crate)


def check(root, kinds):
    """Return the relative paths whose content differs from the rendered text."""
    drift = []
    for rel, text in _expected(root, kinds):
        path = root / rel
        if not path.is_file() or path.read_text() != text:
            drift.append(rel)
    return drift


def write(root, kinds):
    """Rewrite every drifted file; return the relative paths written."""
    written = []
    for rel, text in _expected(root, kinds):
        path = root / rel
        if not path.is_file() or path.read_text() != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            written.append(rel)
    return written


def main():
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--kind", action="append", choices=sorted(KINDS))
    args = parser.parse_args()
    kinds = {k: KINDS[k] for k in args.kind} if args.kind else KINDS
    if args.write:
        for rel in write(args.root, kinds):
            print(f"wrote {rel}")
        return 0
    drift = check(args.root, kinds)
    for rel in drift:
        print(f"differs from its template: {rel}")
    if drift:
        print("run: python3 scripts/render_crate_files.py --write")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
