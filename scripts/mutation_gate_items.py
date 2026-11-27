#!/usr/bin/env python3
"""Items for the `mutation-gate-items` check (spec R21, R22, R25, R26; N4).

An item is a change that could weaken the mutation gate without showing up as a
survivor: an equivalents entry, a `cosmic-ray.toml` key, or gate-shaping content. Each
item carries a key derived from its content, so a later edit is a new item.

N4 is the core constraint: nothing from the PR head is ever built, imported or run.
PR files are written only with `git show <sha>:<path>` into a scratch tree outside the
repo; every tool subprocess (`run_tool`) runs in a fresh empty directory with a scrubbed
environment, and `git` calls read objects from the repo with GIT_* stripped;
`cosmic-ray init` runs through its console script on a config this script generates.
Besides the standard library it imports only the pinned PyYAML and the base checkout's
own `cosmic_ray_prune.py` (this file's directory).

Usage: mutation_gate_items.py <base-sha> <head-sha> [--repo <dir>]
Exit codes: 0 no items, 1 red (items listed; only the operator's admin merge clears
them), 2 usage, 3 infrastructure error (still red in CI).
"""

import argparse
import bisect
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
from dataclasses import dataclass, replace
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

GIT_ENV_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")
OPERATOR_LINE = (
    "mutation-gate-items: these need the operator's review; "
    "only the operator merges this PR (admin override)."
)
GATE_FILES = (
    ".github/workflows/mutation-pr.yml",
    ".github/workflows/mutation-gate-items.yml",
    # The mirror names the contexts ci-gate.sh waits for even before they register;
    # editing either file changes what auto-merge waits for.
    ".github/required-status-checks",
    "scripts/ci-gate.sh",
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
    r"(?P<comment>\s+#.*)?\s*$"
)
ASSIGN_RE = re.compile(
    r"^\s*(?:(?:export|override)\s+)*([A-Za-z_][\w.-]*)\s*(?:::=|:=|\?=|\+=|=)"
)
RULE_RE = re.compile(r"^([^\s#=:\t][^:=#]*):(?!=)")
DIRECTIVE_RE = re.compile(
    r"^\s*(?:ifeq|ifneq|ifdef|ifndef|else|endif|-?include|sinclude|export|unexport|vpath)\b"
)
DEFINE_RE = re.compile(r"^\s*define\b")
ENDEF_RE = re.compile(r"^\s*endef\b")
SUBMAKE_RE = re.compile(r"\$\(MAKE\)\s+(?:-\S+\s+)*([\w.-]+)")
CONFIG_REMOVED = "<removed>"
DELETED = "deleted"
REGULAR_MODES = frozenset({"100644", "100755"})


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
    """Run a tool with cwd = a fresh empty directory and a scrubbed environment (N4).

    The environment is built from scratch (never inherited): a PATH of absolute entries
    only, HOME in the empty directory, and the fixed Python hardening variables. A caller
    needing more passes `extra_env`, for example `RUSTUP_HOME`, `RUSTUP_TOOLCHAIN` and
    `CARGO_HOME` for `cargo mutants --list`; nothing else reaches the tool.
    """
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


class NotRegularError(RuntimeError):
    """A blob that is not a regular file (symlink, gitlink, tree) where one is needed."""

    def __init__(self, path: str, mode: str, blob: str) -> None:
        super().__init__(f"{path} is not a regular file (mode {mode})")
        self.path = path
        self.mode = mode
        self.blob = blob


def _git_bytes(repo: Path, args: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        env=_clean_env(),
        stdin=subprocess.DEVNULL,
        check=False,
    )


def _write_under(root: Path, rel: str, data: bytes) -> Path:
    dest = (root / rel).resolve()
    if root.resolve() not in dest.parents:
        raise RuntimeError(f"refusing to write outside the scratch tree: {rel}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return dest


@dataclass
class Context:
    """What a collector sees: the repo, both shas, changed paths and its own scratch dir.

    PR files reach disk only through `materialise` and `materialise_tree`.
    """

    repo: Path
    base: str
    head: str
    changed: list[str]
    scratch: Path

    def entry(self, sha: str, path: str) -> tuple[str, str] | None:
        """(mode, blob id) of `<sha>:<path>` from `git ls-tree`, or None when absent."""
        out = _git_bytes(self.repo, ["ls-tree", "-z", sha, "--", path])
        if out.returncode != 0 or not out.stdout:
            return None
        mode, _, blob = out.stdout.split(b"\t", 1)[0].decode().split()[:3]
        return mode, blob

    def mode(self, sha: str, path: str) -> str | None:
        found = self.entry(sha, path)
        return found[0] if found else None

    def show(self, sha: str, path: str) -> str | None:
        """`git show <sha>:<path>` as text (undecodable bytes kept), or None if absent."""
        out = _git_bytes(self.repo, ["show", f"{sha}:{path}"])
        if out.returncode != 0:
            return None
        return out.stdout.decode("utf-8", errors="surrogateescape")

    def blob_id(self, sha: str, path: str) -> str:
        found = self.entry(sha, path)
        return found[1] if found else DELETED

    def _blob(self, blob: str) -> bytes:
        out = _git_bytes(self.repo, ["cat-file", "blob", blob])
        if out.returncode != 0:
            raise RuntimeError(f"git cat-file blob {blob} failed")
        return out.stdout

    def materialise(self, sha: str, path: str, root: Path) -> Path | None:
        """Write `<sha>:<path>` to `<root>/<path>` from its blob (never archive or checkout).

        None when the path is absent; NotRegularError when it is not a regular file.
        """
        found = self.entry(sha, path)
        if found is None:
            return None
        if found[0] not in REGULAR_MODES:
            raise NotRegularError(path, found[0], found[1])
        return _write_under(root, path, self._blob(found[1]))

    def materialise_tree(
        self,
        sha: str,
        subdir: str,
        root: Path,
        skip: Callable[[str], bool] | None = None,
    ) -> Path:
        """Write every file under `<sha>:<subdir>` to `<root>/<subdir>` as bytes.

        `skip(path)` leaves a path unwritten (N4). NotRegularError on any entry that is
        not a regular file (symlink, gitlink), skipped paths included: they are judged
        before they are dropped.
        """
        out = _git_bytes(self.repo, ["ls-tree", "-r", "-z", sha, "--", subdir])
        if out.returncode != 0:
            raise RuntimeError(f"git ls-tree {sha} {subdir} failed")
        (root / subdir).mkdir(parents=True, exist_ok=True)
        for record in filter(None, out.stdout.split(b"\0")):
            meta, _, raw_path = record.partition(b"\t")
            mode, _, blob = meta.decode().split()
            path = raw_path.decode("utf-8", errors="surrogateescape")
            if mode not in REGULAR_MODES:
                raise NotRegularError(path, mode, blob)
            if skip is None or not skip(path):
                _write_under(root, path, self._blob(blob))
        return root / subdir


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
    """Every item of the change base..head, sorted and de-duplicated.

    Each collector runs with its own scratch subdirectory.
    """
    with tempfile.TemporaryDirectory(prefix="mgi-scratch-") as tmp:
        ctx = Context(repo, base, head, _changed_paths(repo, base, head), Path(tmp))
        found: set[Item] = set()
        for kind in sorted(_COLLECTORS):
            scratch = Path(tmp) / kind
            scratch.mkdir()
            found.update(_COLLECTORS[kind](replace(ctx, scratch=scratch)))
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
    except ValueError:
        return None


def _config_dirs(ctx: Context) -> list[str]:
    pattern = re.compile(r"^([^/]+)/cosmic-ray\.toml$")
    return sorted({m.group(1) for p in ctx.changed if (m := pattern.match(p))})


def _config_items_for(ctx: Context, directory: str) -> list[Item]:
    path = f"{directory}/cosmic-ray.toml"
    mode = ctx.mode(ctx.head, path)
    if mode is not None and mode not in REGULAR_MODES:
        key = (directory, "config-not-regular", ctx.blob_id(ctx.head, path))
        return [Item(directory, "python-config", key)]
    new = _parse_config(ctx.show(ctx.head, path))
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


@dataclass
class _Resolved:
    operator: str
    spec: Any
    count: int
    ordinal: int


def _equivalent_dirs(ctx: Context) -> list[str]:
    pattern = re.compile(r"^([^/]+)/mutants-equivalent\.toml$")
    return sorted({m.group(1) for p in ctx.changed if (m := pattern.match(p))})


def _equivalent_marker(directory: str, what: str, blob: str) -> Item:
    return Item(directory, "python-equivalent", (directory, what, blob))


def _init_session(ctx: Context, directory: str) -> Path | Item:
    """`cosmic-ray init` on the head module with a generated config.

    An Item (module-not-regular) when the head module is missing or not a regular file:
    a symlinked module would otherwise yield no jobs and hide every new entry.
    """
    module = f"{directory}/{directory.replace('-', '_')}.py"
    try:
        materialised = ctx.materialise(ctx.head, module, ctx.scratch / "head")
    except NotRegularError as exc:
        return _equivalent_marker(directory, "module-not-regular", exc.blob)
    if materialised is None:
        return _equivalent_marker(directory, "module-not-regular", DELETED)
    binary = shutil.which("cosmic-ray", path=_safe_path_entries())
    if binary is None:
        raise RuntimeError("cosmic-ray console script not found on PATH")
    config = ctx.scratch / f"{directory}-generated.toml"
    module_literal = json.dumps(str(materialised), ensure_ascii=False)
    config.write_text(GENERATED_CONFIG.format(module=module_literal), encoding="utf-8")
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


def _ordinal(specs: list[Any], spec: Any) -> int:
    """Position of `spec` among specs of one operator sharing function, line and above."""
    peers = [
        s
        for s in specs
        if (s.function, s.line, s.above) == (spec.function, spec.line, spec.above)
    ]
    return peers.index(spec)


def _resolve_tolerant(
    conn: sqlite3.Connection, entries: list[Any]
) -> dict[str, _Resolved]:
    """job id -> resolution for every entry that resolves; others are skipped."""
    sources = prune.SourceCache()
    resolved: dict[str, _Resolved] = {}
    for entry in entries:
        try:
            job_id = prune.resolve_entry(conn, entry, sources)[0]
        except prune.PruneError:
            continue
        if job_id in resolved:
            resolved[job_id].count += 1
            continue
        specs = sources.specs[entry.operator]
        spec = next(s for s in specs if s.job_id == job_id)
        resolved[job_id] = _Resolved(entry.operator, spec, 1, _ordinal(specs, spec))
    return resolved


def _equivalent_item(directory: str, found: _Resolved, duplicate: bool) -> Item:
    spec = found.spec
    key = (
        directory,
        found.operator,
        spec.function or "",
        spec.line,
        spec.above,
        str(found.ordinal),
    )
    suffix = ("duplicate-entry",) if duplicate else ()
    return Item(directory, "python-equivalent", key + suffix)


def _head_only_items(
    directory: str, head_jobs: dict[str, _Resolved], base_jobs: dict[str, _Resolved]
) -> list[Item]:
    """Jobs pruned only by the head file, and entries the head file repeats (R22)."""
    items = []
    for job_id, found in head_jobs.items():
        base_count = base_jobs[job_id].count if job_id in base_jobs else 0
        if found.count > max(base_count, 1):
            items.append(_equivalent_item(directory, found, True))
        if base_count == 0:
            items.append(_equivalent_item(directory, found, False))
    return items


def _equivalents_for(ctx: Context, directory: str) -> list[Item]:
    path = f"{directory}/mutants-equivalent.toml"
    try:
        head_toml = ctx.materialise(ctx.head, path, ctx.scratch / "head")
    except NotRegularError as exc:
        return [_equivalent_marker(directory, "toml-not-regular", exc.blob)]
    try:
        base_toml = ctx.materialise(ctx.base, path, ctx.scratch / "base")
    except NotRegularError:
        base_toml = None
    head_entries = _load_entries(head_toml)
    if head_entries is None:
        return [
            _equivalent_marker(directory, "unparseable", ctx.blob_id(ctx.head, path))
        ]
    if not head_entries:
        return []
    session = _init_session(ctx, directory)
    if isinstance(session, Item):
        return [session]
    conn = prune.open_session(session)
    try:
        head_jobs = _resolve_tolerant(conn, head_entries)
        base_jobs = _resolve_tolerant(conn, _load_entries(base_toml) or [])
    finally:
        conn.close()
    return _head_only_items(directory, head_jobs, base_jobs)


def collect_python_equivalents(ctx: Context) -> list[Item]:
    items: list[Item] = []
    for directory in _equivalent_dirs(ctx):
        items += _equivalents_for(ctx, directory)
    return items


# --- Rust exclusion items (R21, R23) -------------------------------------------------

RUST_CRATE_RE = re.compile(
    r"^([^/]+/[^/]+-rs)/(?:src/|\.cargo/|tests/|Cargo\.toml$|build\.rs$)"
)
RUST_CONFIG_NAME = ".cargo/mutants.toml"
RUST_TOOLCHAIN = "stable"
MUTANT_POSITION_RE = re.compile(r"^.*?:\d+:\d+: ")
RUST_KIND = "rust-exclusion"
Mutant = dict[str, Any]


def normalise_line(line: str) -> str:
    return " ".join(line.split())


def mutant_description(name: str) -> str:
    """A mutant's `name` without its `<file>:<line>:<col>: ` prefix (R23)."""
    return MUTANT_POSITION_RE.sub("", name, count=1)


def cargo_tool(name: str, cargo_home: Path) -> Path:
    """`<cargo_home>/bin/<name>`, resolved from the caller's install, never from the PR."""
    path = cargo_home / "bin" / name
    if not path.exists():
        raise RuntimeError(f"{name} not found at {path}")
    return path


def _real_cargo_home() -> Path:
    return Path(os.environ.get("CARGO_HOME") or Path.home() / ".cargo")


def _rust_env(cargo_home: Path, fresh_cargo_home: Path) -> dict[str, str]:
    """The R21 environment: pinned toolchain, empty CARGO_HOME, tools by absolute path."""
    rustup_home = os.environ.get("RUSTUP_HOME") or str(Path.home() / ".rustup")
    return {
        "PATH": os.pathsep.join([str(cargo_home / "bin"), _safe_path_entries()]),
        "RUSTUP_HOME": rustup_home,
        "RUSTUP_TOOLCHAIN": RUST_TOOLCHAIN,
        "CARGO_HOME": str(fresh_cargo_home),
        "CARGO_NET_OFFLINE": "true",
    }


def _list_mutants(tree: Path, no_config: bool) -> list[Mutant] | None:
    """`cargo mutants --list --json -d <tree>`; None when the tool fails or prints junk.

    Only a listing: nothing is built, and `cargo metadata` is never run without
    `--no-deps` (cargo-mutants itself passes it).
    """
    cargo_home = _real_cargo_home()
    cargo = cargo_tool("cargo", cargo_home)
    cargo_tool("cargo-mutants", cargo_home)
    args = [str(cargo), "mutants", "--list", "--json", "-d", str(tree)]
    if no_config:
        args.insert(-2, "--no-config")
    with tempfile.TemporaryDirectory(prefix="mgi-cargo-home-") as fresh:
        result = run_tool(args, _rust_env(cargo_home, Path(fresh)))
    if result.returncode != 0:
        return None
    try:
        listing = json.loads(result.stdout)
    except ValueError:
        return None
    return listing if isinstance(listing, list) else None


def _source_lines(tree: Path, cache: dict[str, list[str]], file: str) -> list[str]:
    """The lines of `<tree>/<file>`, [] when it escapes the tree or cannot be read."""
    if file not in cache:
        path = (tree / file).resolve()
        lines: list[str] = []
        if tree.resolve() in path.parents and path.is_file():
            lines = path.read_text(encoding="utf-8", errors="surrogateescape").split(
                "\n"
            )
        cache[file] = lines
    return cache[file]


def _line_at(lines: list[str], number: int) -> str:
    return normalise_line(lines[number - 1]) if 0 < number <= len(lines) else ""


def _mutant_base_key(
    crate: str, tree: Path, cache: dict[str, list[str]], mutant: Mutant
) -> tuple[str, ...]:
    """R23 key of a mutant without its ordinal."""
    file = str(mutant.get("file", ""))
    function = (mutant.get("function") or {}).get("function_name") or ""
    start = (mutant.get("span") or {}).get("start", {}).get("line", 0)
    lines = _source_lines(tree, cache, file)
    return (
        crate,
        file,
        function,
        str(mutant.get("genre", "")),
        mutant_description(str(mutant.get("name", ""))),
        _line_at(lines, start),
        _line_at(lines, start - 1),
    )


def _excluded_keys(
    crate: str, tree: Path, plain: list[Mutant], configured: list[Mutant]
) -> set[tuple[str, ...]]:
    """Keys, with ordinals, of the mutants the config excludes (R23)."""
    kept = {m.get("name") for m in configured}
    cache: dict[str, list[str]] = {}
    seen: dict[tuple[str, ...], int] = {}
    excluded: set[tuple[str, ...]] = set()
    for mutant in plain:
        base_key = _mutant_base_key(crate, tree, cache, mutant)
        ordinal = seen.get(base_key, 0)
        seen[base_key] = ordinal + 1
        if mutant.get("name") not in kept:
            excluded.add((*base_key, str(ordinal)))
    return excluded


def is_cargo_control_file(path: str) -> bool:
    """`.cargo/config*` and `rust-toolchain*`: files cargo or rustup read to run code (N4).

    `.cargo/mutants.toml` is data the listing needs, so it is kept.
    """
    parts = path.split("/")
    name = parts[-1]
    in_cargo_dir = len(parts) > 1 and parts[-2] == ".cargo"
    return (in_cargo_dir and name.startswith("config")) or name.startswith(
        "rust-toolchain"
    )


def _rust_marker(crate: str, what: str, blob: str) -> Item:
    return Item(crate, RUST_KIND, (crate, what, blob))


def _keys_at(
    ctx: Context, sha: str, crate: str, label: str
) -> set[tuple[str, ...]] | Item:
    """Excluded-mutant keys of `crate` at `sha`; an Item when it cannot be listed."""
    manifest = f"{crate}/Cargo.toml"
    if ctx.entry(sha, manifest) is None:
        return set()
    root = ctx.scratch / f"{crate.replace('/', '_')}-{label}"
    try:
        tree = ctx.materialise_tree(sha, crate, root, is_cargo_control_file)
    except NotRegularError as exc:
        return _rust_marker(crate, "tree-not-regular", exc.blob)
    plain = _list_mutants(tree, True)
    configured = _list_mutants(tree, False)
    if plain is None or configured is None:
        return _rust_marker(crate, "list-failed", ctx.blob_id(sha, crate))
    return _excluded_keys(crate, tree, plain, configured)


def _rust_config_items(ctx: Context, crate: str) -> list[Item]:
    """Changed `.cargo/mutants.toml` keys other than `exclude_re` (R23)."""
    path = f"{crate}/{RUST_CONFIG_NAME}"
    if path not in ctx.changed:
        return []
    new = _parse_config(ctx.show(ctx.head, path))
    old = _parse_config(ctx.show(ctx.base, path))
    if new is None or old is None:
        return [_rust_marker(crate, "unparseable", ctx.blob_id(ctx.head, path))]
    changed = {k: v for k, v in new.items() if old.get(k) != v}
    changed.update({k: CONFIG_REMOVED for k in old if k not in new})
    return [
        Item(crate, RUST_KIND, (crate, k, v))
        for k, v in changed.items()
        if k != "exclude_re"
    ]


def _rust_exclusion_items(ctx: Context, crate: str) -> list[Item]:
    head = _keys_at(ctx, ctx.head, crate, "head")
    if isinstance(head, Item):
        return [head, *_rust_config_items(ctx, crate)]
    base = _keys_at(ctx, ctx.base, crate, "base")
    base_keys = set() if isinstance(base, Item) else base
    items = [Item(crate, RUST_KIND, key) for key in sorted(head - base_keys)]
    return items + _rust_config_items(ctx, crate)


def collect_rust_exclusions(ctx: Context) -> list[Item]:
    crates = sorted({m.group(1) for p in ctx.changed if (m := RUST_CRATE_RE.match(p))})
    items: list[Item] = []
    for crate in crates:
        items += _rust_exclusion_items(ctx, crate)
    return items


# --- Rust hidden-code items (R24, R34) -----------------------------------------------

HIDDEN_KIND = "rust-hidden"
# Every crate `.rs` file except the crate's own tests/, benches/ and examples/ trees:
# cargo-mutants never mutates those, and a `#[path]` into them is already an item.
RUST_FILE_RE = re.compile(r"^([^/]+/[^/]+-rs)/(?!(?:tests|benches|examples)/)(.+\.rs)$")
RAW_STR_RE = re.compile(r'(?:br|cr|r)(#*)"')
PLAIN_STR_RE = re.compile(r'[bc]?"')
NUM_RE = re.compile(r"\d\w*(?:\.\d\w*)?")
IDENT_RE = re.compile(r"[^\W\d]\w*")
SKIP_RE = re.compile(r"(?<!\w)mutants::skip(?!\w)")
OPENERS = {"(": ")", "[": "]", "{": "}"}
CLOSERS = frozenset(OPENERS.values())
# Keywords that make a macro argument an expression with behaviour, not data.
EXPRESSION_KEYWORDS = frozenset(
    {"as", "match", "if", "else", "loop", "while", "for", "in", "let", "return"}
    | {"break", "continue", "move", "unsafe", "async", "await", "yield", "fn", "impl"}
)
CONTAINER_KEYWORDS = frozenset({"mod", "impl", "trait"})
CONTAINER_PREV = frozenset(
    {"}", "{", ";", "]", ")", "pub", "unsafe", "default", "auto"}
)
ARG_LITERALS = frozenset({"str", "num", "char"})
CALLABLE_PREV = frozenset({"ident", "num", "str", "char"})


@dataclass(frozen=True)
class RustTok:
    """`kind` is ident, num, str, char, life or punct (`::` is one punct)."""

    kind: str
    text: str


def _skip_block_comment(text: str, i: int) -> int:
    """Index after the (nested) block comment opening at `i`; end of text if unclosed."""
    depth = 0
    while i < len(text):
        if text.startswith("/*", i):
            depth, i = depth + 1, i + 2
        elif text.startswith("*/", i):
            depth, i = depth - 1, i + 2
            if depth == 0:
                return i
        else:
            i += 1
    return i


def _skip_quoted(text: str, i: int, quote: str) -> int:
    """Index after the quoted literal whose opening quote sits at `i`."""
    i += 1
    while i < len(text) and text[i] != quote:
        i += 2 if text[i] == "\\" else 1
    return min(i + 1, len(text))


def _lex_string(text: str, i: int) -> tuple[RustTok, int] | None:
    raw = RAW_STR_RE.match(text, i)
    if raw:
        closing = '"' + raw.group(1)
        end = text.find(closing, raw.end())
        stop = len(text) if end < 0 else end + len(closing)
        return RustTok("str", text[i:stop]), stop
    plain = PLAIN_STR_RE.match(text, i)
    if plain:
        stop = _skip_quoted(text, plain.end() - 1, '"')
        return RustTok("str", text[i:stop]), stop
    if text.startswith("b'", i):
        stop = _skip_quoted(text, i + 1, "'")
        return RustTok("char", text[i:stop]), stop
    return None


def _lex_quote(text: str, i: int) -> tuple[RustTok, int]:
    """A char literal (`'a'`, `'\\n'`) or a lifetime (`'a`) starting at the `'` at `i`."""
    if text.startswith("\\", i + 1) or text.startswith("'", i + 2):
        stop = _skip_quoted(text, i, "'")
        return RustTok("char", text[i:stop]), stop
    word = IDENT_RE.match(text, i + 1)
    stop = word.end() if word else i + 1
    return RustTok("life", text[i:stop]), stop


def _lex_word(text: str, i: int) -> tuple[RustTok, int] | None:
    for kind, pattern in (("num", NUM_RE), ("ident", IDENT_RE)):
        found = pattern.match(text, i)
        if found:
            return RustTok(kind, found.group()), found.end()
    return None


def _lex_one(text: str, i: int) -> tuple[RustTok | None, int]:
    """The token starting at `i` (None for a comment or whitespace) and the next index."""
    if text.startswith("//", i):
        end = text.find("\n", i)
        return None, len(text) if end < 0 else end
    if text.startswith("/*", i):
        return None, _skip_block_comment(text, i)
    if text[i].isspace():
        return None, i + 1
    for lexer in (_lex_string, _lex_word):
        lexed = lexer(text, i)
        if lexed:
            return lexed
    if text[i] == "'":
        return _lex_quote(text, i)
    width = 2 if text.startswith("::", i) else 1
    return RustTok("punct", text[i : i + width]), i + width


def rust_tokens(text: str) -> list[RustTok]:
    """Rust tokens of `text` without comments or whitespace; strings stay one token."""
    toks: list[RustTok] = []
    i = 0
    while i < len(text):
        tok, i = _lex_one(text, i)
        if tok is not None:
            toks.append(tok)
    return toks


def _match(toks: list[RustTok], i: int) -> int:
    """Index of the delimiter closing the one at `i` (last token when unbalanced)."""
    depth = 0
    for j in range(i, len(toks)):
        if toks[j].kind != "punct":
            continue
        if toks[j].text in OPENERS:
            depth += 1
        elif toks[j].text in CLOSERS:
            depth -= 1
            if depth == 0:
                return j
    return len(toks) - 1


def _texts(toks: list[RustTok], start: int, end: int) -> list[str]:
    return [t.text for t in toks[start:end]]


def _attr_end(toks: list[RustTok], i: int) -> int:
    """Index after the attribute whose `#` sits at `i`; `i` when it is not one."""
    j = i + 1
    if j < len(toks) and toks[j].text == "!":
        j += 1
    if j < len(toks) and toks[j].text == "[":
        return _match(toks, j) + 1
    return i


ITEM_KEYWORDS = frozenset(
    {"fn", "mod", "impl", "struct", "enum", "trait", "union", "use", "type", "static"}
    | {"extern", "unsafe", "async", "const", "macro_rules", "default"}
)


def _starts_item(toks: list[RustTok], i: int) -> bool:
    """Whether the tokens at `i` open an item (after `pub`, `pub(crate)`), not an element."""
    if i < len(toks) and toks[i].text == "pub":
        i += 1
        if i < len(toks) and toks[i].text == "(":
            i = _match(toks, i) + 1
    return i < len(toks) and toks[i].text in ITEM_KEYWORDS


def _item_end(toks: list[RustTok], i: int, element: bool = False) -> int:
    """Index after the item starting at `i`: its `;`, or its braces' close.

    Stops, without consuming, at a closer that belongs to the enclosing scope, so a
    gated struct field, variant, match arm or parameter never reaches past its own end.
    With `element` set, a depth-0 `,` also ends an element that is not an item.
    """
    while i < len(toks) and toks[i].text == "#" and _attr_end(toks, i) > i:
        i = _attr_end(toks, i)
    until_comma = element and not _starts_item(toks, i)
    while i < len(toks):
        text = toks[i].text if toks[i].kind == "punct" else ""
        if text in CLOSERS or (until_comma and text == ","):
            return i
        if text == ";":
            return i + 1
        if text == "{":
            return _match(toks, i) + 1
        i = _match(toks, i) + 1 if text in ("(", "[") else i + 1
    return len(toks)


def _block_end(toks: list[RustTok], i: int) -> int:
    """Index of the closer ending the block that holds token `i` (end of text if none)."""
    depth = 0
    for j in range(i, len(toks)):
        text = toks[j].text if toks[j].kind == "punct" else ""
        if text in OPENERS:
            depth += 1
        elif text in CLOSERS:
            if depth == 0:
                return j
            depth -= 1
    return len(toks)


CFG_TEST = ["cfg", "(", "test", ")"]


def _cfg_test_attr(toks: list[RustTok], i: int) -> tuple[bool, int]:
    """(is it `#[cfg(test)]` or `#![cfg(test)]`, index after the attribute)."""
    end = _attr_end(toks, i)
    inner = toks[i + 1].text == "!" if i + 1 < len(toks) else False
    body = _texts(toks, i + (3 if inner else 2), end - 1)
    return end > i and body == CFG_TEST, end


def _gated_end(toks: list[RustTok], after: int, inner: bool, leading: bool) -> int:
    """End of what a `cfg(test)` attribute gates, given where the attribute sits.

    An inner attribute gates its enclosing block, and the whole file only when it comes
    before any item at the top level (later it gates nothing, as it is invalid Rust there); an outer one gates the one item or element after it.
    """
    if inner and leading:
        return len(toks)
    if inner:
        # Outside any block an inner attribute after an item is invalid Rust: gate nothing.
        end = _block_end(toks, after)
        return after if end == len(toks) else end
    return _item_end(toks, after, element=True)


def test_mask(toks: list[RustTok]) -> list[bool]:
    """True for every token inside what a `#[cfg(test)]` attribute gates (R24 exempts it).

    Only the exact `cfg(test)` form counts: `cfg_attr(test, ...)` and `cfg(not(test))`
    keep their code examined. A gate never reaches past its own element or block.
    """
    mask = [False] * len(toks)
    leading = True
    i = 0
    while i < len(toks):
        if toks[i].text != "#" or _attr_end(toks, i) == i:
            leading = False
            i += 1
            continue
        gated, after = _cfg_test_attr(toks, i)
        inner = toks[i + 1].text == "!"
        if not gated:
            leading = leading and inner
            i = after
            continue
        stop = _gated_end(toks, after, inner, leading)
        mask[i:stop] = [True] * (stop - i)
        leading = False
        i = stop
    return mask


def _is_macro_call(toks: list[RustTok], i: int) -> bool:
    return (
        toks[i].kind == "ident"
        and toks[i].text not in EXPRESSION_KEYWORDS
        and i + 2 < len(toks)
        and toks[i + 1].text == "!"
        and toks[i + 2].text in OPENERS
        and toks[i + 2].kind == "punct"
    )


def _is_macro_rules(toks: list[RustTok], i: int) -> bool:
    return (
        toks[i].text == "macro_rules" and i + 1 < len(toks) and toks[i + 1].text == "!"
    )


def _always(prev: RustTok | None, nxt: RustTok | None) -> bool:
    return True


def _dot_ok(prev: RustTok | None, nxt: RustTok | None) -> bool:
    """Access only: a value before, an ident or number after (so `..` never is)."""
    value = prev is not None and (prev.kind in CALLABLE_PREV or prev.text == ")")
    return value and nxt is not None and nxt.kind in ("ident", "num")


def _call_paren_ok(prev: RustTok | None, nxt: RustTok | None) -> bool:
    return prev is not None and prev.kind == "ident"


def _prefix_amp_ok(prev: RustTok | None, nxt: RustTok | None) -> bool:
    return prev is None or prev.text in (",", "(", "&")


ARG_PUNCT_RULES: dict[str, Callable[[RustTok | None, RustTok | None], bool]] = {
    ",": _always,
    "::": _always,
    ")": _always,
    ".": _dot_ok,
    "(": _call_paren_ok,
    "&": _prefix_amp_ok,
}


def _arg_ok(prev: RustTok | None, tok: RustTok, nxt: RustTok | None) -> bool:
    """One macro-argument token against the allow-set (R24).

    Allowed: literals (a format string is one), identifiers other than expression
    keywords, `::` paths, `,`, `.` as field or method access (a dot is access only
    between a value and an ident or number, so `..` never is), `(`/`)` only as the call
    parens after an identifier, and `&` only as a prefix: first in the arguments or right
    after `,`, `(` or another prefix `&`. After a value `&` is the binary operator.
    Everything else is behaviour that cargo-mutants may not see (operators, `match`,
    braces, `=>`, `?`, `;`, `[`, `-1`) and fails closed.
    """
    if tok.kind in ARG_LITERALS:
        return True
    if tok.kind == "ident":
        return tok.text not in EXPRESSION_KEYWORDS
    rule = ARG_PUNCT_RULES.get(tok.text) if tok.kind == "punct" else None
    return rule is not None and rule(prev, nxt)


def _args_ok(toks: list[RustTok], start: int, end: int) -> bool:
    """Whether every token of `toks[start:end]` is allowed; nested calls judge themselves."""
    prev: RustTok | None = None
    j = start
    while j < end:
        if _is_macro_call(toks, j):
            j = _match(toks, j + 2) + 1
            prev = toks[j - 1]
            continue
        nxt = toks[j + 1] if j + 1 < end else None
        if not _arg_ok(prev, toks[j], nxt):
            return False
        prev = toks[j]
        j += 1
    return True


def _joined(toks: list[RustTok], start: int, end: int) -> str:
    """Tokens joined by single spaces: spelling, comments and layout do not change it."""
    return " ".join(_texts(toks, start, end))


def _enclosing_attr(toks: list[RustTok], i: int) -> tuple[int, int]:
    """Token range of the `#[...]` holding token `i`, or just `(i, i + 1)`.

    Walks outwards past unmatched openers such as the `(` of `cfg_attr(`.
    """
    depth = 0
    for j in range(i, -1, -1):
        text = toks[j].text if toks[j].kind == "punct" else ""
        if text in CLOSERS:
            depth += 1
        elif text in OPENERS and depth:
            depth -= 1
        elif text == "[" and j > 0 and toks[j - 1].text in ("#", "!"):
            return j - 1, _match(toks, j) + 1
    return i, i + 1


def _flatten_tokens(toks: list[RustTok]) -> tuple[str, list[int]]:
    """Tokens as one string (whitespace and comments gone) and each token's offset.

    String and char literals become `S`, so a mention in a literal never matches;
    adjacent word tokens keep one space so `xmutants` cannot pose as `mutants`.
    """
    flat = ""
    starts: list[int] = []
    for tok in toks:
        piece = "S" if tok.kind in ("str", "char") else tok.text
        if (
            flat
            and tok.kind in ("ident", "num")
            and (flat[-1].isalnum() or flat[-1] == "_")
        ):
            flat += " "
        starts.append(len(flat))
        flat += piece
    return flat, starts


def _skip_texts(toks: list[RustTok], mask: list[bool]) -> list[str]:
    """Attributes naming `mutants::skip` in any spelling (whitespace/comments removed)."""
    flat, starts = _flatten_tokens(toks)
    found = []
    for m in SKIP_RE.finditer(flat):
        k = bisect.bisect_right(starts, m.start()) - 1
        if not mask[k]:
            first, last = _enclosing_attr(toks, k)
            found.append(_joined(toks, first, last))
    return found


def _macro_texts(toks: list[RustTok], mask: list[bool]) -> list[str]:
    found = []
    for i in range(len(toks)):
        if mask[i]:
            continue
        if _is_macro_rules(toks, i):
            found.append(_joined(toks, i, min(i + 3, len(toks))))
        if not _is_macro_call(toks, i):
            continue
        close = _match(toks, i + 2)
        if toks[i].text == "include" or not _args_ok(toks, i + 3, close):
            found.append(_joined(toks, i, close + 1))
    return found


def _is_path_assign(toks: list[RustTok], k: int) -> bool:
    return (
        toks[k].kind == "ident"
        and toks[k].text == "path"
        and k + 1 < len(toks)
        and toks[k + 1].text == "="
        and toks[k - 1].text in ("[", "(", ",")
    )


def _path_attr_texts(toks: list[RustTok], mask: list[bool]) -> list[str]:
    """Attributes assigning `path = ...` (also inside `cfg_attr`): a module from anywhere."""
    found = []
    for i, tok in enumerate(toks):
        if mask[i] or tok.text != "#":
            continue
        end = _attr_end(toks, i)
        if any(_is_path_assign(toks, k) for k in range(i + 1, end)):
            found.append(_joined(toks, i, end))
    return found


def hidden_texts(text: str) -> list[str]:
    """Normalised texts of the hidden-code occurrences in `text`, outside test modules."""
    toks = rust_tokens(text)
    mask = test_mask(toks)
    found = _skip_texts(toks, mask) + _macro_texts(toks, mask)
    return sorted(found + _path_attr_texts(toks, mask))


def _container_label(toks: list[RustTok], i: int, body: int) -> str:
    return toks[i + 1].text if toks[i].text == "mod" else _joined(toks, i, body)


def _containers(toks: list[RustTok]) -> list[tuple[int, int, str]]:
    """(open, close, label) of every `mod`, `impl` and `trait` body."""
    found = []
    for i, tok in enumerate(toks):
        before = toks[i - 1].text if i else ";"
        if tok.kind != "ident" or tok.text not in CONTAINER_KEYWORDS:
            continue
        if before not in CONTAINER_PREV:
            continue
        end = _item_end(toks, i)
        body = next((j for j in range(i, end) if toks[j].text == "{"), None)
        if body is not None and toks[end - 1].text == "}":
            found.append((body, end - 1, _container_label(toks, i, body)))
    return found


def _is_test_fn(toks: list[RustTok], i: int) -> bool:
    """Whether the `fn` at `i` carries a `#[test]` or `#[cfg(test)]` attribute."""
    j = i - 1
    while j >= 0 and toks[j].text in ("pub", "const", "async", "unsafe", ")", "extern"):
        j -= 1
    while j >= 0 and toks[j].text == "]":
        first, _ = _enclosing_attr(toks, j - 1)
        if _texts(toks, first, j + 1)[2:-1] in (["test"], CFG_TEST):
            return True
        j = first - 1
    return False


def _has_body(toks: list[RustTok], i: int) -> bool:
    end = _item_end(toks, i)
    return toks[end - 1].text == "}"


def function_ids(text: str) -> set[tuple[str, ...]]:
    """(container labels..., name) of each non-test function with a body in `text`."""
    toks = rust_tokens(text)
    mask = test_mask(toks)
    containers = _containers(toks)
    found = set()
    for i, tok in enumerate(toks[:-1]):
        if mask[i] or tok.text != "fn" or toks[i + 1].kind != "ident":
            continue
        if _is_test_fn(toks, i) or not _has_body(toks, i):
            continue
        path = tuple(lbl for lo, hi, lbl in containers if lo < i < hi)
        found.add((*path, toks[i + 1].text))
    return found


def _function_item(crate: str, file: str, ident: tuple[str, ...]) -> Item:
    return Item(crate, HIDDEN_KIND, (crate, file, "fn " + "::".join(ident)))


def _unqualified(mutant: Mutant) -> str:
    """The function name of a listed mutant without its `Type::` or `module::` prefix."""
    name = (mutant.get("function") or {}).get("function_name") or ""
    return name.rsplit("::", 1)[-1]


def _head_listed_functions(
    ctx: Context, crate: str
) -> tuple[set[tuple[str, str]], Item | None]:
    """(file, function) pairs with a mutant in the head `--no-config` listing."""
    root = ctx.scratch / f"{crate.replace('/', '_')}-head"
    try:
        tree = ctx.materialise_tree(ctx.head, crate, root, is_cargo_control_file)
    except NotRegularError as exc:
        return set(), _rust_marker(crate, "tree-not-regular", exc.blob)
    listing = _list_mutants(tree, True)
    if listing is None:
        return set(), _rust_marker(crate, "list-failed", ctx.blob_id(ctx.head, crate))
    return {(str(m.get("file", "")), _unqualified(m)) for m in listing}, None


def _text_at(ctx: Context, sha: str, path: str) -> str:
    return ctx.show(sha, path) or ""


def _hidden_for_file(
    ctx: Context, crate: str, file: str
) -> tuple[list[Item], set[tuple[str, ...]]]:
    """Added hidden-code items of one file, and its functions new in the head."""
    path = f"{crate}/{file}"
    head = _text_at(ctx, ctx.head, path)
    base = _text_at(ctx, ctx.base, path)
    remaining = hidden_texts(base)
    items = []
    for text in hidden_texts(head):
        if text in remaining:
            remaining.remove(text)
        else:
            items.append(Item(crate, HIDDEN_KIND, (crate, file, text)))
    if not file.startswith("src/"):
        return items, set()
    return items, function_ids(head) - function_ids(base)


def _hidden_for_crate(ctx: Context, crate: str) -> list[Item]:
    files = sorted(
        m.group(2)
        for p in ctx.changed
        if (m := RUST_FILE_RE.match(p)) and m.group(1) == crate
    )
    items: list[Item] = []
    new_functions: dict[str, set[tuple[str, ...]]] = {}
    for file in files:
        added, fresh = _hidden_for_file(ctx, crate, file)
        items += added
        if fresh:
            new_functions[file] = fresh
    if not new_functions:
        return items
    listed, marker = _head_listed_functions(ctx, crate)
    if marker is not None:
        return [*items, marker]
    for file, fresh in new_functions.items():
        items += [
            _function_item(crate, file, ident)
            for ident in sorted(fresh)
            if (file, ident[-1]) not in listed
        ]
    return items


def _declares_proc_macro(text: str | None, unparseable: bool) -> bool:
    """True when the manifest `text` declares a proc-macro library.

    `unparseable` is the answer for text that is not valid TOML (fail closed for the head).
    """
    if text is None:
        return False
    try:
        lib = tomllib.loads(text).get("lib")
    except tomllib.TOMLDecodeError:
        return unparseable
    if not isinstance(lib, dict):
        return False
    if lib.get("proc-macro") is True or lib.get("proc_macro") is True:
        return True
    return any(
        isinstance(kinds, list) and "proc-macro" in kinds
        for kinds in (lib.get("crate-type"), lib.get("crate_type"))
    )


def _proc_macro_items(ctx: Context) -> list[Item]:
    """New or changed proc-macro declarations: their generated code is invisible (R24)."""
    items = []
    for path in ctx.changed:
        if path.rsplit("/", 1)[-1] != "Cargo.toml":
            continue
        crate = path.rsplit("/", 1)[0] if "/" in path else "."
        blob = ctx.blob_id(ctx.head, path)
        mode = ctx.mode(ctx.head, path)
        if mode is not None and mode not in REGULAR_MODES:
            # git show of a link is its target text, not a manifest: fail closed.
            items.append(
                Item(crate, HIDDEN_KIND, (crate, "Cargo.toml", f"not-regular {blob}"))
            )
            continue
        if not _declares_proc_macro(ctx.show(ctx.head, path), True):
            continue
        if _declares_proc_macro(ctx.show(ctx.base, path), False):
            continue
        items.append(
            Item(crate, HIDDEN_KIND, (crate, "Cargo.toml", f"proc-macro {blob}"))
        )
    return items


def collect_rust_hidden(ctx: Context) -> list[Item]:
    crates = sorted({m.group(1) for p in ctx.changed if (m := RUST_FILE_RE.match(p))})
    items: list[Item] = _proc_macro_items(ctx)
    for crate in crates:
        items += _hidden_for_crate(ctx, crate)
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


def _is_gate_name(name: object) -> bool:
    return isinstance(name, str) and (name in GATE_NAMES or "${{" in name)


def _declares_gate_name(text: str) -> bool:
    """True when a workflow has a job id or `name:` of a gate check (or cannot be read).

    A `name:` holding a `${{` expression counts: it can evaluate to a gate name.
    """
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
    return any(_is_gate_name(n) for n in names)


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
    base_text = ctx.show(ctx.base, path)
    texts = [t for t in (head_text, base_text) if t is not None]
    if not _is_listed_gate_path(path) and not any(
        _declares_gate_name(t) for t in texts
    ):
        return None
    if (
        head_text is not None
        and base_text is not None
        and only_uses_bumps(base_text, head_text)
    ):
        return None
    return Item("gate", "gate", (path, ctx.blob_id(ctx.head, path)))


@dataclass
class _Make:
    """What the gate needs from a Makefile: everything outside recipes, and the recipes."""

    other: list[str]
    recipes: dict[str, list[str]]
    prereqs: dict[str, set[str]]
    special: set[str]


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


def _add_rule(make: _Make, names: list[str], line: str) -> None:
    after = line.split(":", 1)[1].split(";", 1)[0].replace("|", " ")
    for name in names:
        make.recipes.setdefault(name, [])
        make.prereqs.setdefault(name, set()).update(after.split())
        if name.startswith(".") or "%" in name:
            make.special.add(name)


def _parse_make(text: str) -> _Make:
    """Just enough make: rules, recipes, defines and directives; the rest is `other`."""
    make = _Make([], {}, {}, set())
    current: list[str] = []
    in_define = False
    for line in _logical_lines(text):
        if in_define:
            make.other.append(line)
            in_define = not ENDEF_RE.match(line)
        elif line.startswith("\t") and current:
            for name in current:
                make.recipes[name].append(line)
        elif not line.strip() or line.lstrip().startswith("#"):
            continue
        else:
            make.other.append(line)
            in_define = bool(DEFINE_RE.match(line))
            if DIRECTIVE_RE.match(line) or in_define:
                continue
            rule = None if ASSIGN_RE.match(line) else RULE_RE.match(line)
            current = rule.group(1).split() if rule else []
            if rule:
                _add_rule(make, current, line)
    return make


def _reachable(make: _Make) -> set[str]:
    """Targets `mutants*` can reach through prerequisites and `$(MAKE) <target>` calls."""
    seen: set[str] = set()
    queue = [n for n in make.recipes if fnmatch.fnmatchcase(n, "mutants*")]
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        queue += make.prereqs.get(name, set())
        for line in make.recipes.get(name, []):
            queue += SUBMAKE_RE.findall(line)
    return seen


def make_scope_text(text: str) -> str:
    """The text the gate hashes: every non-recipe line, plus the recipes `mutants*` reaches.

    Recipes of pattern and special (`.PHONY`-style) targets are always included. Only recipe
    lines of targets `mutants*` cannot reach are exempt, so a variable, export, conditional,
    `define`, `include` or `SHELL` change always changes the text.
    """
    make = _parse_make(text)
    reached = _reachable(make)
    parts = [*make.other, "--recipes--"]
    for name in sorted(make.recipes):
        if name in reached or name in make.special:
            parts += [name, *make.recipes[name]]
    return "\n".join(parts)


def _makefile_item(ctx: Context, path: str) -> Item | None:
    mode = ctx.mode(ctx.head, path)
    if mode is not None and mode not in REGULAR_MODES:
        return Item("gate", "gate", (path, ctx.blob_id(ctx.head, path)))
    old = make_scope_text(ctx.show(ctx.base, path) or "")
    new = make_scope_text(ctx.show(ctx.head, path) or "")
    if old == new:
        return None
    digest = hashlib.sha256(new.encode("utf-8", errors="surrogateescape")).hexdigest()
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
register(RUST_KIND, collect_rust_exclusions)
register(HIDDEN_KIND, collect_rust_hidden)


# --- CLI (R26) -----------------------------------------------------------------------


def merge_base(repo: Path, base: str, head: str) -> str:
    """The merge base of the two commits; RuntimeError when git cannot find one."""
    out = _git(repo, ["merge-base", "--end-of-options", base, head])
    sha = out.stdout.strip()
    if out.returncode != 0 or not sha:
        raise RuntimeError(f"git merge-base {base} {head} failed: {out.stderr.strip()}")
    return sha


def run(repo: Path, base: str, head: str) -> tuple[int, str]:
    """The CLI body: (exit code, text to print).

    Items are computed against the merge base of `base` and `head`, so a base branch that
    moved after the PR branched produces none. Any item is red: nothing clears it in
    band, only the operator's admin merge does.
    """
    items = collect(repo, merge_base(repo, base, head), head)
    if not items:
        return 0, "mutation-gate-items: no uncleared items"
    lines = [f"uncleared item: {i.target} {i.kind} {' | '.join(i.key)}" for i in items]
    return 1, "\n".join([*lines, OPERATOR_LINE])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mutation-gate-items.sh")
    parser.add_argument("base")
    parser.add_argument("head")
    parser.add_argument("--repo", default=".")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        code, text = run(Path(args.repo).resolve(), args.base, args.head)
    # Top-level handler: every fault is reported and exits 3, which stays red in CI.
    except Exception as exc:  # noqa: BLE001
        print(
            f"mutation-gate-items: infra error: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 3
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
