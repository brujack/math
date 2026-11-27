#!/usr/bin/env python3
"""Items for the `mutation-gate-items` check (spec R21, R22, R25, R26; N4).

An item is a change that could weaken the mutation gate without showing up as a
survivor: an equivalents entry, a `cosmic-ray.toml` key, or gate-shaping content. Each
item carries a key made of the content it approves, so a later edit produces a new key.

N4 is the core constraint: nothing from the PR head is ever built, imported or run.
PR files are written only with `git show <sha>:<path>` into a scratch tree outside the
repo; every subprocess runs in a fresh empty directory with a scrubbed environment;
`cosmic-ray init` runs through its console script on a config this script generates.
The only code imported besides the standard library is the base checkout's own
`cosmic_ray_prune.py` and `mutation_gate_clearance.py` (this file's directory).

Usage: mutation_gate_items.py <base-sha> <head-sha> [--pr <n>] [--repo <dir>]
Exit codes: 0 no uncleared items, 1 red, 2 usage.
"""

import argparse
import difflib
import fnmatch
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib
import yaml


def _load_sibling(name: str) -> Any:
    """Import `<name>.py` from this file's directory: the base checkout's own code."""
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / f"{name}.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


prune: Any = _load_sibling("cosmic_ray_prune")
clearance: Any = _load_sibling("mutation_gate_clearance")

GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
SIGNERS_PATH = ".github/mutation-gate-allowed-signers"
SIGNERS_ENV = "MUTATION_GATE_SIGNERS"
GATE_FILES = (
    ".github/workflows/mutation-pr.yml",
    ".github/workflows/mutation-gate-items.yml",
    SIGNERS_PATH,
    "tests/test_mutation_gate_allowed_signers.py",
)
GATE_SCRIPT_GLOBS = (
    "scripts/mutation-*.sh",
    "scripts/mutation_*.py",
    "scripts/cosmic_ray_*.py",
)
GATE_DIR_PREFIX = "tests/fixtures/mutation_weakening/"
WORKFLOW_GLOB = ".github/workflows/*"
GATE_NAMES = frozenset({"mutation-pr", "mutation-gate-items", "secret-scan"})
GENERATED_CONFIG = """[cosmic-ray]
module-path = {module}
timeout = 60.0
excluded-modules = []
test-command = "true"

[cosmic-ray.distributor]
name = "local"
"""
USES_RE = re.compile(
    r"^(?P<lead>\s*(?:-\s+)?uses:\s*)"
    r"(?P<action>[\w.-]+/[\w.-]+(?:/[\w./-]+)?)@(?P<sha>[0-9a-f]{40})"
    r"(?P<comment>\s*#.*)?\s*$"
)
ASSIGN_RE = re.compile(
    r"^\s*(?:(?:export|override)\s+)*([A-Za-z_][\w.-]*)\s*(?:::=|:=|\?=|\+=|=)"
)
RULE_RE = re.compile(r"^([^\s#=:\t][^:=#]*):(?!=)")
REF_RE = re.compile(r"\$[({]([A-Za-z_][\w.-]*)[)}]")
CONFIG_REMOVED = "<removed>"
DELETED = "deleted"


@dataclass(frozen=True)
class Item:
    """One thing needing review: `target` is a dir, a crate dir or `gate`."""

    target: str
    kind: str
    key: tuple[str, ...]


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in GIT_ENV_VARS}


def _git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=_clean_env(),
        stdin=subprocess.DEVNULL,
        check=False,
    )


def _safe_path_entries() -> str:
    """PATH without relative entries, so no tool is found through a cwd or PR dir."""
    entries = os.environ.get("PATH", "").split(os.pathsep)
    return os.pathsep.join(e for e in entries if e and os.path.isabs(e))


def run_tool(
    args: list[str], extra_env: dict[str, str] | None = None, timeout: int = 900
) -> subprocess.CompletedProcess[str]:
    """Run a tool with cwd = a fresh empty directory and a scrubbed environment (N4)."""
    with tempfile.TemporaryDirectory(prefix="mgi-cwd-") as cwd:
        env = {
            "PATH": _safe_path_entries(),
            "HOME": cwd,
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONSAFEPATH": "1",
            "PYTHONNOUSERSITE": "1",
            **(extra_env or {}),
        }
        return subprocess.run(
            args,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )


@dataclass
class Context:
    """What a collector sees: the repo, both shas, changed paths and a scratch tree."""

    repo: Path
    base: str
    head: str
    changed: list[str]
    scratch: Path

    def show(self, sha: str, path: str) -> str | None:
        """`git show <sha>:<path>` as text, or None when the path is absent there."""
        out = _git(self.repo, ["show", f"{sha}:{path}"])
        return out.stdout if out.returncode == 0 else None

    def blob_id(self, sha: str, path: str) -> str:
        out = _git(self.repo, ["rev-parse", "--verify", "-q", f"{sha}:{path}"])
        return out.stdout.strip() if out.returncode == 0 else DELETED

    def materialise(self, sha: str, path: str, root: Path) -> Path | None:
        """Write `<sha>:<path>` to `<root>/<path>` with `git show` only (never archive)."""
        text = self.show(sha, path)
        if text is None:
            return None
        dest = (root / path).resolve()
        if root.resolve() not in dest.parents:
            raise RuntimeError(f"refusing to write outside the scratch tree: {path}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        return dest


Collector = Callable[[Context], list[Item]]
_COLLECTORS: dict[str, Collector] = {}


def register(kind: str, fn: Collector) -> None:
    """Register (or replace) the collector for an item kind."""
    _COLLECTORS[kind] = fn


def _changed_paths(repo: Path, base: str, head: str) -> list[str]:
    out = _git(repo, ["diff", "--name-only", "-z", "--no-renames", base, head])
    if out.returncode != 0:
        raise RuntimeError(f"git diff {base} {head} failed: {out.stderr.strip()}")
    return [p for p in out.stdout.split("\0") if p]


def collect(repo: Path, base: str, head: str) -> list[Item]:
    """Every item of the change base..head, sorted and de-duplicated."""
    with tempfile.TemporaryDirectory(prefix="mgi-scratch-") as tmp:
        ctx = Context(repo, base, head, _changed_paths(repo, base, head), Path(tmp))
        found: set[Item] = set()
        for kind in sorted(_COLLECTORS):
            found.update(_COLLECTORS[kind](ctx))
    return sorted(found, key=lambda i: (i.target, i.kind, i.key))


# --- Python config items (R22) -------------------------------------------------------


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{name}."))
        else:
            flat[name] = json.dumps(value, sort_keys=True, default=str)
    return flat


def _parse_config(text: str | None) -> dict[str, str] | None:
    if text is None:
        return {}
    try:
        return _flatten(tomllib.loads(text))
    except tomllib.TOMLDecodeError:
        return None


def _config_dirs(ctx: Context) -> list[str]:
    pattern = re.compile(r"^([^/]+)/cosmic-ray\.toml$")
    return sorted({m.group(1) for p in ctx.changed if (m := pattern.match(p))})


def _config_items_for(ctx: Context, directory: str) -> list[Item]:
    path = f"{directory}/cosmic-ray.toml"
    new_text = ctx.show(ctx.head, path)
    new = _parse_config(new_text)
    old = _parse_config(ctx.show(ctx.base, path))
    if new is None or old is None:
        key = (directory, "unparseable", ctx.blob_id(ctx.head, path))
        return [Item(directory, "python-config", key)]
    changed = {k: v for k, v in new.items() if old.get(k) != v}
    changed.update({k: CONFIG_REMOVED for k in old if k not in new})
    return [
        Item(directory, "python-config", (directory, k, v)) for k, v in changed.items()
    ]


def collect_python_config(ctx: Context) -> list[Item]:
    items: list[Item] = []
    for directory in _config_dirs(ctx):
        items += _config_items_for(ctx, directory)
    return items


# --- Python equivalents items (R22) --------------------------------------------------


def _equivalent_dirs(ctx: Context) -> list[str]:
    pattern = re.compile(r"^([^/]+)/mutants-equivalent\.toml$")
    return sorted({m.group(1) for p in ctx.changed if (m := pattern.match(p))})


def _init_session(ctx: Context, directory: str) -> Path | None:
    """`cosmic-ray init` on the head module with a generated config; None if no module."""
    module = f"{directory}/{directory.replace('-', '_')}.py"
    materialised = ctx.materialise(ctx.head, module, ctx.scratch / "head")
    if materialised is None:
        return None
    binary = shutil.which("cosmic-ray", path=_safe_path_entries())
    if binary is None:
        raise RuntimeError("cosmic-ray console script not found on PATH")
    config = ctx.scratch / f"{directory}-generated.toml"
    config.write_text(GENERATED_CONFIG.format(module=json.dumps(str(materialised))))
    session = ctx.scratch / f"{directory}-session.sqlite"
    result = run_tool([binary, "init", str(config), str(session)])
    if result.returncode != 0:
        raise RuntimeError(f"cosmic-ray init failed for {directory}: {result.stderr}")
    return session


def _load_entries(path: Path | None) -> list[Any] | None:
    """Entries of a materialised toml, [] when absent, None when it cannot be parsed."""
    if path is None:
        return []
    try:
        return prune.load_entries(path)[0]
    except prune.PruneError:
        return None


def _resolve_tolerant(
    conn: sqlite3.Connection, entries: list[Any]
) -> dict[str, tuple[str, Any, int]]:
    """job id -> (operator, spec, entry count); an entry matching no job is skipped."""
    sources = prune.SourceCache()
    resolved: dict[str, tuple[str, Any, int]] = {}
    for entry in entries:
        try:
            job_id = prune.resolve_entry(conn, entry, sources)[0]
        except prune.PruneError:
            continue
        spec = next(s for s in sources.specs[entry.operator] if s.job_id == job_id)
        count = resolved[job_id][2] if job_id in resolved else 0
        resolved[job_id] = (entry.operator, spec, count + 1)
    return resolved


def _equivalent_item(directory: str, operator: str, spec: Any, duplicate: bool) -> Item:
    key = (
        directory,
        operator,
        spec.function or "",
        spec.line,
        spec.above,
        str(spec.occurrence),
    )
    return Item(
        directory,
        "python-equivalent",
        key + (("duplicate-entry",) if duplicate else ()),
    )


def _head_only_items(
    directory: str, head_jobs: dict[str, Any], base_jobs: dict[str, Any]
) -> list[Item]:
    """Jobs pruned only by the head file, and entries the head file repeats (R22)."""
    items = []
    for job_id, (operator, spec, count) in head_jobs.items():
        base_count = base_jobs[job_id][2] if job_id in base_jobs else 0
        if count > max(base_count, 1) or (base_count == 0 and count > 1):
            items.append(_equivalent_item(directory, operator, spec, True))
        if base_count == 0:
            items.append(_equivalent_item(directory, operator, spec, False))
    return items


def _equivalents_for(ctx: Context, directory: str) -> list[Item]:
    path = f"{directory}/mutants-equivalent.toml"
    head_toml = ctx.materialise(ctx.head, path, ctx.scratch / "head")
    base_toml = ctx.materialise(ctx.base, path, ctx.scratch / "base")
    head_entries = _load_entries(head_toml)
    if head_entries is None:
        key = (directory, "unparseable", ctx.blob_id(ctx.head, path))
        return [Item(directory, "python-equivalent", key)]
    base_entries = _load_entries(base_toml) or []
    session = _init_session(ctx, directory) if head_entries else None
    if session is None:
        return []
    conn = prune.open_session(session)
    try:
        head_jobs = _resolve_tolerant(conn, head_entries)
        base_jobs = _resolve_tolerant(conn, base_entries)
    finally:
        conn.close()
    return _head_only_items(directory, head_jobs, base_jobs)


def collect_python_equivalents(ctx: Context) -> list[Item]:
    items: list[Item] = []
    for directory in _equivalent_dirs(ctx):
        items += _equivalents_for(ctx, directory)
    return items


# --- Gate items (R25) ----------------------------------------------------------------


def _is_listed_gate_path(path: str) -> bool:
    if path in GATE_FILES or path.startswith(GATE_DIR_PREFIX):
        return True
    return path.count("/") == 1 and any(
        fnmatch.fnmatchcase(path, g) for g in GATE_SCRIPT_GLOBS
    )


def _is_workflow(path: str) -> bool:
    return (
        path.count("/") == 2
        and fnmatch.fnmatchcase(path, WORKFLOW_GLOB)
        and path.endswith((".yml", ".yaml"))
    )


def _declares_gate_name(text: str) -> bool:
    """True when a workflow has a job id or `name:` of a gate check (or cannot be read)."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return True
    if not isinstance(data, dict):
        return False
    names: list[object] = [data.get("name")]
    jobs = data.get("jobs")
    if isinstance(jobs, dict):
        for job_id, job in jobs.items():
            names.append(job_id)
            names.append(job.get("name") if isinstance(job, dict) else None)
    return any(isinstance(n, str) and n in GATE_NAMES for n in names)


def _uses_bump(old: str, new: str) -> bool:
    a, b = USES_RE.match(old), USES_RE.match(new)
    return bool(a and b and a["lead"] == b["lead"] and a["action"] == b["action"])


def only_uses_bumps(old_text: str, new_text: str) -> bool:
    """True when every changed line is a `uses: <action>@<sha>` pin bump (R25)."""
    old, new = old_text.splitlines(), new_text.splitlines()
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag != "replace" or i2 - i1 != j2 - j1:
            return False
        if not all(
            _uses_bump(x, y) for x, y in zip(old[i1:i2], new[j1:j2], strict=True)
        ):
            return False
    return True


def _workflow_item(ctx: Context, path: str) -> Item | None:
    head_text = ctx.show(ctx.head, path)
    listed = _is_listed_gate_path(path)
    if not listed and (head_text is None or not _declares_gate_name(head_text)):
        return None
    base_text = ctx.show(ctx.base, path)
    if (
        head_text is not None
        and base_text is not None
        and only_uses_bumps(base_text, head_text)
    ):
        return None
    return Item("gate", "gate", (path, ctx.blob_id(ctx.head, path)))


def _logical_lines(text: str) -> list[str]:
    out: list[str] = []
    current: list[str] = []
    for raw in text.splitlines():
        current.append(raw)
        if not raw.endswith("\\"):
            out.append("\n".join(current))
            current = []
    if current:
        out.append("\n".join(current))
    return out


def _parse_make(text: str) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Targets -> rule and recipe lines, variables -> assignment lines (just enough make)."""
    targets: dict[str, list[str]] = {}
    variables: dict[str, list[str]] = {}
    current: list[str] = []
    for line in _logical_lines(text):
        if line.startswith("\t"):
            for name in current:
                targets[name].append(line)
        elif not line.strip() or line.lstrip().startswith("#"):
            continue
        elif assign := ASSIGN_RE.match(line):
            variables.setdefault(assign.group(1), []).append(line)
            current = []
        elif rule := RULE_RE.match(line):
            current = rule.group(1).split()
            for name in current:
                targets.setdefault(name, []).append(line)
        else:
            current = []
    return targets, variables


def _refs(text: str) -> list[str]:
    return REF_RE.findall(text.replace("$$", ""))


def mutants_text(text: str) -> str:
    """The `mutants*` target text plus every variable it references, transitively."""
    targets, variables = _parse_make(text)
    body = "\n".join(
        "\n".join(lines)
        for name, lines in targets.items()
        if fnmatch.fnmatchcase(name, "mutants*")
    )
    seen: dict[str, str] = {}
    queue = _refs(body)
    while queue:
        name = queue.pop()
        if name in seen or name not in variables:
            continue
        seen[name] = "\n".join(variables[name])
        queue += _refs(seen[name])
    return body + "\n" + "\n".join(f"{n}:\n{seen[n]}" for n in sorted(seen))


def _makefile_item(ctx: Context, path: str) -> Item | None:
    old = mutants_text(ctx.show(ctx.base, path) or "")
    new = mutants_text(ctx.show(ctx.head, path) or "")
    if old == new:
        return None
    digest = hashlib.sha256(new.encode("utf-8")).hexdigest()
    return Item("gate", "gate", (path, digest))


def _gate_item(ctx: Context, path: str) -> Item | None:
    if _is_workflow(path):
        return _workflow_item(ctx, path)
    if _is_listed_gate_path(path):
        return Item("gate", "gate", (path, ctx.blob_id(ctx.head, path)))
    if path.rsplit("/", 1)[-1] == "Makefile":
        return _makefile_item(ctx, path)
    return None


def collect_gate(ctx: Context) -> list[Item]:
    found = (_gate_item(ctx, p) for p in ctx.changed)
    return [item for item in found if item is not None]


register("python-config", collect_python_config)
register("python-equivalent", collect_python_equivalents)
register("gate", collect_gate)


# --- Clearance and CLI (R26) ---------------------------------------------------------


def _signers_file(repo: Path, base: str, scratch: Path, override: str | None) -> Path:
    """The allowed-signers file: the override seam, else the base branch's own copy."""
    if override:
        return Path(override)
    dest = scratch / "allowed-signers"
    out = _git(repo, ["show", f"{base}:{SIGNERS_PATH}"])
    dest.write_text(out.stdout if out.returncode == 0 else "", encoding="utf-8")
    return dest


def _signing_key(signers: Path) -> str:
    """`<type> <blob>` of the first key in the signers file, for the R26 command."""
    for raw in signers.read_text(encoding="utf-8").splitlines():
        tokens = raw.split()
        blobs = [i for i, t in enumerate(tokens) if i > 0 and t.startswith("AAAA")]
        if tokens and not tokens[0].startswith("#") and blobs and blobs[0] >= 2:
            return f"{tokens[blobs[0] - 1]} {tokens[blobs[0]]}"
    return "<key>"


def _cleared_keys(
    repo: Path, base: str, found: list[Any]
) -> set[tuple[str, str, tuple[str, ...]]]:
    """Keys present in the tree of a verified clearing commit for their own target."""
    cleared: set[tuple[str, str, tuple[str, ...]]] = set()
    by_sha: dict[str, list[Item]] = {}
    for entry in found:
        if entry.sha not in by_sha:
            by_sha[entry.sha] = collect(repo, base, entry.sha)
        cleared.update(
            (i.target, i.kind, i.key)
            for i in by_sha[entry.sha]
            if i.target == entry.target
        )
    return cleared


def _uncleared(
    items: list[Item], found: list[Any], repo: Path, base: str
) -> list[Item]:
    keys = _cleared_keys(repo, base, found)
    return [i for i in items if (i.target, i.kind, i.key) not in keys]


def _render(items: list[Item], ignored: list[str], pr: int | None, key: str) -> str:
    lines = [f"uncleared item: {i.target} {i.kind} {' | '.join(i.key)}" for i in items]
    lines += ignored
    targets = list(dict.fromkeys(i.target for i in items))
    remedy = clearance.remedy_command(pr or 0, targets, key)
    lines.append(remedy if pr is not None else remedy.replace("#0 ", "#<pr> "))
    return "\n".join(lines)


def run(
    repo: Path, base: str, head: str, pr: int | None, signers_override: str | None
) -> tuple[int, str]:
    """The CLI body: (exit code, text to print)."""
    items = collect(repo, base, head)
    ignored: list[str] = []
    found: list[Any] = []
    with tempfile.TemporaryDirectory(prefix="mgi-signers-") as tmp:
        signers = _signers_file(repo, base, Path(tmp), signers_override)
        key = _signing_key(signers)
        if pr is not None:
            found, ignored = clearance.trailers(repo, base, head, pr, signers)
    open_items = _uncleared(items, found, repo, base) if found else items
    if not open_items:
        return 0, "mutation-gate-items: no uncleared items"
    return 1, _render(open_items, ignored, pr, key)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mutation-gate-items.sh")
    parser.add_argument("base")
    parser.add_argument("head")
    parser.add_argument("--pr", type=int)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--signers", default=os.environ.get(SIGNERS_ENV))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        code, text = run(
            Path(args.repo).resolve(), args.base, args.head, args.pr, args.signers
        )
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"mutation-gate-items: error: {exc}", file=sys.stderr)
        return 1
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
