.PHONY: install-hooks install-deps test-hooks test-python test lint lint-hooks lint-python changelog validate-plan bash-coverage

# Derived from the tracked set (git ls-files), not a hand-maintained list --
# an omitted file leaves a hand-list's coverage unchanged rather than lowering
# it (tdd.md "Coverage Denominators"), which is exactly how the previous
# 6-file literal list covered only scripts/{ci-gate,mutation-classify,
# rust-check}.sh and the three extensionless hooks, missing all 19
# install_deps.sh scripts under the sub-projects and tests/helpers/common.bash.
# The three hooks (pre-commit/pre-push/commit-msg) have no extension for a
# `git ls-files` glob to match, so they stay listed explicitly. The env -u
# prefix strips a GIT_DIR that git exports into a worktree pre-push hook's
# environment (ci.md/shell.md); without it this parse-time assignment can
# silently resolve against the wrong repository.
SHELLCHECK := $(shell command -v shellcheck 2>/dev/null)
RUFF := $(shell command -v ruff 2>/dev/null)
BATS := $(shell command -v bats 2>/dev/null)
# Split so the derived half can be checked on its own: appending the three
# literal hook paths would otherwise mask an empty git ls-files, and lint would
# report a pass having examined 3 files instead of the full tracked set.
SHELL_TRACKED := $(shell env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
                   git ls-files '*.sh' '*.bash')
SHELL_SOURCES := $(SHELL_TRACKED) scripts/pre-commit scripts/pre-push scripts/commit-msg $(wildcard tests/mocks/*)
BATS_SOURCES := $(shell env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
                   git ls-files '*.bats')

install-hooks:
	ln -sf "../../scripts/pre-commit" "$$(git rev-parse --git-path hooks)/pre-commit"
	ln -sf "../../scripts/pre-push" "$$(git rev-parse --git-path hooks)/pre-push"
	ln -sf "../../scripts/commit-msg" "$$(git rev-parse --git-path hooks)/commit-msg"
	@printf "Pre-commit, pre-push, and commit-msg hooks installed\n"

# Guards against PEP 668 (externally-managed environments): measured, the
# Linux 7950X ships Python 3.12.3 with EXTERNALLY-MANAGED present, and a bare
# `python3 -m pip install` there fails with "error: externally-managed-
# environment". pip's own check_externally_managed() skips the marker check
# entirely when sys.prefix != sys.base_prefix (i.e. inside a virtualenv) --
# checking only the marker, without the venv term, refuses identically
# inside and outside a venv, so the guard's own "create a venv" remedy would
# not change its verdict. Measured on the Linux workstation, Python 3.12.3:
#   outside venv, marker present -> guard refuses (correct)
#   inside venv, marker present  -> marker-only guard refuses (WRONG: pip
#     itself permits the install there, rc=0); the venv-aware guard permits
#     it too, matching pip.
# Bare `pip` is deliberately never used here -- measured, `pip` resolves to an
# unrelated pyenv environment on the Mac Studio, so a bare `pip install` can
# exit 0 while `make test-python` still raises ModuleNotFoundError.
install-deps:
	@command -v python3 >/dev/null 2>&1 \
	  || { printf 'python3 not found on PATH.\n' >&2; exit 1; }
	@python3 -c 'import os, sys, sysconfig; raise SystemExit(1 if sys.prefix == sys.base_prefix and os.path.exists(os.path.join(sysconfig.get_path("stdlib"), "EXTERNALLY-MANAGED")) else 0)' \
	  || { printf 'python3 is externally managed (PEP 668). Create a venv first:\n  python3 -m venv .venv && . .venv/bin/activate\nthen re-run: make install-deps\n' >&2; exit 1; }
	python3 -m pip install -r requirements-dev.txt

test-hooks:
	bats --recursive tests/

# tests/*.py were type-checked by pyright and never executed by anything —
# test_time_tests.py sat green-by-assumption for its whole life. This target is
# what actually runs them.
test-python:
	python3 -m unittest discover -s tests -p 'test_*.py'

test: lint test-hooks test-python

# Not wired into `test` or `lint-hooks` — it re-runs the entire bats suite
# under a PS4 xtrace tracer, which takes minutes, so it stays an explicit,
# separately-invoked target (CI runs it in its own job; see
# .github/workflows/auto-merge.yml). Guarded the same way as SHELLCHECK
# above: a missing bats would otherwise hard-lock a machine out of this one
# target, but since it's not part of the pre-commit/pre-push gate, a hard
# $(error) here (matching dotfiles' bash-coverage target) is fine — nothing
# else depends on this succeeding locally.
bash-coverage:
ifndef BATS
	$(error bats not found. Install: brew install bats-core (macOS) or sudo apt-get install bats (Linux))
endif
	@bash scripts/run-bash-coverage.sh

# BATS_SOURCES run at --severity=warning, unlike SHELL_SOURCES which run at
# shellcheck's default: bats' run/@test model emits SC2030/SC2031 subshell
# notices structurally, which say nothing about correctness.
lint-hooks:
	@if [ -z "$(SHELL_TRACKED)" ]; then \
	  printf 'lint-hooks: derived shell file list is EMPTY — refusing to report a pass having linted only the literal hook paths.\n' >&2; \
	  exit 1; \
	fi
	@if [ -n "$(SHELLCHECK)" ]; then \
	  shellcheck $(SHELL_SOURCES) && printf "shellcheck OK\n" || exit 1; \
	  if [ -n "$(BATS_SOURCES)" ]; then shellcheck --severity=warning $(BATS_SOURCES) && printf "shellcheck bats OK\n" || exit 1; fi; \
	else \
	  printf "shellcheck not found, skipping (install: brew install shellcheck)\n"; \
	fi

# `ruff check .` from the repo root, not a derived file list. ruff.toml here
# reaches every .py in the repo by ancestor discovery, so the whole tracked set
# is covered with no denominator that can silently drift -- an omitted file
# would leave a hand-list's result unchanged rather than lowering it (tdd.md
# "Coverage Denominators"). It duplicates each sub-project's own `make lint`,
# which is cheap and is the point: nothing can sit outside it.
#
# Guarded like SHELLCHECK above. `test` depends on this and the pre-push hook
# runs `test`, so a hard failure on a missing ruff would lock a machine out of
# committing the very change that installs it (ci.md).
lint-python:
ifndef RUFF
	@printf "ruff not found, skipping (install: pip install ruff==0.16.4)\n"
else
	ruff check .
	@env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
	  git ls-files -z '*.py' | xargs -0 ruff format --check
endif

lint: lint-hooks lint-python

changelog:
	git-cliff -o CHANGELOG.md

# 10-80-10 cycle (ADR-0009/0010 in ai-config) — validate a plan file
validate-plan:
ifndef PLAN
	@printf "error: PLAN is required, e.g. make validate-plan PLAN=docs/superpowers/plans/foo.md\n" >&2
	@exit 2
endif
	@python3 ~/.claude/scripts/validate-plan.py "$(PLAN)"
