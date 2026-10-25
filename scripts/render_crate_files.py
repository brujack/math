#!/usr/bin/env python3
"""Render every per-crate and per-Python-project file from one template each.

Usage: render_crate_files.py (--check | --write) [--root DIR] [--kind NAME ...]

Each template in scripts/crate_templates/ is the single source for one file kind;
@CRATE@ is replaced with the project's directory name and nothing else varies,
except that templates under python/ may also use @MODULE@ (the directory name with
"-" replaced by "_", the Python module and test file stem).
Operator rule (2026-10-24): all 11 crates and all 8 Python projects are treated the
same, all of the time, so a per-project difference is a template change applied to
every project.

--check  exit 1 and list every rendered file that differs from its template
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

# The 8 Python sub-projects; each directory holds <module>.py.
PYTHON_PROJECTS = [
    "amicable",
    "collatz",
    "e",
    "factorial",
    "fib",
    "perfect-numbers",
    "pi",
    "sq",
]

# Template path under scripts/crate_templates/ (python/<name>) -> per-project output
# path. Rust KINDS never take @MODULE@.
PYTHON_KINDS = {
    "python/Makefile": "{project}/Makefile",
    "python/install_deps.sh": "{project}/install_deps.sh",
    "python/py.yml": ".github/workflows/{project}-py.yml",
    "python/pyrightconfig.json": "{project}/pyrightconfig.json",
    "python/cosmic-ray.toml": "{project}/cosmic-ray.toml",
}

# Template file name in scripts/crate_templates/ -> per-crate output path.
KINDS = {
    "Makefile": "{crate}/{crate}-rs/Makefile",
    "rustfmt.toml": "{crate}/{crate}-rs/rustfmt.toml",
    "release.yml": ".github/workflows/release-{crate}-rs.yml",
    "ci.yml": ".github/workflows/{crate}-rs.yml",
    "nextest.toml": "{crate}/{crate}-rs/.config/nextest.toml",
    "install_deps.sh": "{crate}/{crate}-rs/install_deps.sh",
}

PLACEHOLDER = "@CRATE@"
MODULE_PLACEHOLDER = "@MODULE@"
_ANY_PLACEHOLDER = re.compile(r"@[A-Z_]+@")
TEMPLATE_DIR = pathlib.Path("scripts") / "crate_templates"


def module_name(project):
    """Return the Python module stem for a project directory (perfect-numbers -> perfect_numbers)."""
    return project.replace("-", "_")


def render(template, project, module=None):
    """Return template with @CRATE@ (and @MODULE@ when module is given) replaced.

    @MODULE@ without a module, or any other @NAME@, is an error.
    """
    allowed = {PLACEHOLDER}
    if module is not None:
        allowed.add(MODULE_PLACEHOLDER)
    unknown = sorted(set(_ANY_PLACEHOLDER.findall(template)) - allowed)
    if unknown:
        raise ValueError(
            f"unknown placeholder(s) {unknown}; only {sorted(allowed)} allowed here"
        )
    text = template.replace(PLACEHOLDER, project)
    if module is not None:
        text = text.replace(MODULE_PLACEHOLDER, module)
    return text


def _expected(root, kinds, python_kinds):
    """Yield (relative path, rendered text) for every file of every kind."""
    for kind, pattern in kinds.items():
        template = (root / TEMPLATE_DIR / kind).read_text()
        for crate in CRATES:
            yield pattern.format(crate=crate), render(template, crate)
    for kind, pattern in python_kinds.items():
        template = (root / TEMPLATE_DIR / kind).read_text()
        for project in PYTHON_PROJECTS:
            yield (
                pattern.format(project=project),
                render(template, project, module_name(project)),
            )


def check(root, kinds, python_kinds=None):
    """Return the relative paths whose content differs from the rendered text."""
    drift = []
    for rel, text in _expected(root, kinds, python_kinds or {}):
        path = root / rel
        if not path.is_file() or path.read_text() != text:
            drift.append(rel)
    return drift


def write(root, kinds, python_kinds=None):
    """Rewrite every drifted file; return the relative paths written."""
    written = []
    for rel, text in _expected(root, kinds, python_kinds or {}):
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
    parser.add_argument(
        "--kind", action="append", choices=sorted([*KINDS, *PYTHON_KINDS])
    )
    args = parser.parse_args()
    if args.kind:
        kinds = {k: KINDS[k] for k in args.kind if k in KINDS}
        python_kinds = {k: PYTHON_KINDS[k] for k in args.kind if k in PYTHON_KINDS}
    else:
        kinds, python_kinds = KINDS, PYTHON_KINDS
    if args.write:
        for rel in write(args.root, kinds, python_kinds):
            print(f"wrote {rel}")
        return 0
    drift = check(args.root, kinds, python_kinds)
    for rel in drift:
        print(f"differs from its template: {rel}")
    if drift:
        print("run: python3 scripts/render_crate_files.py --write")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
