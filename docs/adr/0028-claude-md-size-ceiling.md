# ADR-0028: CLAUDE.md Has a Hard Size Ceiling, One Line Per Rule

**Date:** 2026-10-19
**Status:** Accepted

## Context

The root `CLAUDE.md` loads into every session in this repo before any file is read. Measured
2026-10-19 with `claude -p "/context"` in the main checkout on `claude` at `4fe381a`: session
start 65.7k tokens, of which `CLAUDE.md` (60,297 bytes) was 21.9k. Most of it was reference
material a session needs only when it touches that area: the CI section alone was 14,718 bytes,
bash coverage 7,132, Rust mutation testing 4,797.

Nothing stopped it growing. 16 commits touched `CLAUDE.md` in the 60 days before this ADR, and
5 of them went straight to master as docs-only commits, which CI never sees. The rest went
through PRs that `auto-merge.yml` merges on green: it has no `paths:` filter, and math#142,
which changed only `CLAUDE.md`, was merged by `app/github-actions` with no human review.

terraform_ansible (its ADR-0028) and dotfiles (its ADR-0047) adopted the same method on
2026-10-18 and 2026-10-19.

## Decision

**One line per rule.** Each rule in `CLAUDE.md` is one line. When detail is dropped, the line
ends with `→ ai-config/docs/knowledge/math-<topic>.md § <heading>`, and the original text sits
byte-identical under that heading. Rules a session must hold before reading any file (release
signing order, mutation-testing traps, generated-output and `.cache/` rules, pre-push trigger
rules, the DoD) stay as full lines, never pointer-only. Lines for commands that touch live state
keep their variable, override or command.

**A 30,000-byte ceiling**, measured by `scripts/claude_md_budget.py <rev>`:

- It reads `CLAUDE.md` only from git (`git show <rev>:CLAUDE.md`), never the working tree, and
  decides absence with `git ls-tree --full-tree`.
- Exit 1 when the file is over the ceiling, naming the size, the ceiling and the remedy. Exit 0
  when within, or when `<rev>` has no `CLAUDE.md`. Exit 2 when git cannot resolve `<rev>` or
  read its tree.
- `CLAUDE.md` must be a regular file. A symlink makes `git show` return the link's target path
  rather than the file, so a symlink to an oversized file would pass; any mode other than
  `100644` or `100755` is refused.
- No flag, environment variable or commit trailer changes the ceiling or skips the check.

The ceiling sat about 30% above the projected size (about 22.7 KB) when set; the result was
24,945 bytes.

**Enforced where `CLAUDE.md` changes, on every path that can change it:**

- `scripts/pre-push`, for each pushed ref, diffs `CLAUDE.md` against
  `merge-base(local_sha, origin/master)` with `git diff --quiet`, falling back to the hook's
  existing root-commit base for orphan pushes. When the push changes `CLAUDE.md`, it runs the
  checker from the pushed commit and refuses the push on exit 1 or 2. A failed diff refuses. A
  pushed commit with no checker is skipped with a message. Pushes that leave `CLAUDE.md`
  unchanged are never blocked, even when master is over.
- A `claude-md-budget` job in `auto-merge.yml`, in the auto-merge job's `needs:`, runs on every
  PR. It fails a PR that changes `CLAUDE.md` and is over, warns (`::warning::`) when the PR
  leaves an over-ceiling `CLAUDE.md` unchanged, and fails when the checker or the diff errors.

**Raising the ceiling needs an amendment to this ADR**, in the same change that raises
`CEILING`.

## Consequences

- **The ceiling is held by review, not by mechanism.** Both the hook and CI run the checker from
  the commit under test, so a commit can weaken the checker and pass its own check. The defence
  is that a change to `scripts/claude_md_budget.py` is visible in review; the same writer could
  already change `scripts/pre-push` or the Makefile.
- **The hooks are symlinks** (`make install-hooks` runs `ln -sf ../../scripts/pre-push`), so the
  running hook is the main checkout's working tree. The check takes effect on a machine when its
  main checkout pulls the merge commit; there is no install step to run, and comparing the
  installed hook with `cmp` proves nothing.
- Detail now lives in another repo. A session that needs it follows the pointer into ai-config,
  which is private. `AGENTS.md` no longer calls `CLAUDE.md` exhaustive.
- Direct-to-master `CLAUDE.md` commits are gated only by pre-push. A push from a checkout without
  hooks (the GitHub web editor, a cloud session) is caught only if it goes through a PR.

## Related

- `docs/superpowers/specs/2026-10-19-claude-md-budget-design.md`: the design and its review.
- terraform_ansible ADR-0028 and dotfiles ADR-0047: the same mechanism in those repos.
- ai-config ADR-0020: `docs/knowledge/` as the home for reference material.
- ai-config ADR-0077 rule 5: live-state lines keep their command.
