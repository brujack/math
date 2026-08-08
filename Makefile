.PHONY: install-hooks test-hooks test-python test lint-hooks changelog validate-plan

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
SHELL_SOURCES := $(shell env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
                   git ls-files '*.sh' '*.bash') scripts/pre-commit scripts/pre-push scripts/commit-msg
BATS_SOURCES := $(shell env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE \
                   git ls-files '*.bats')

install-hooks:
	ln -sf "../../scripts/pre-commit" "$$(git rev-parse --git-path hooks)/pre-commit"
	ln -sf "../../scripts/pre-push" "$$(git rev-parse --git-path hooks)/pre-push"
	ln -sf "../../scripts/commit-msg" "$$(git rev-parse --git-path hooks)/commit-msg"
	@printf "Pre-commit, pre-push, and commit-msg hooks installed\n"

test-hooks:
	bats --recursive tests/

# tests/*.py were type-checked by pyright and never executed by anything —
# test_time_tests.py sat green-by-assumption for its whole life. This target is
# what actually runs them.
test-python:
	python3 -m unittest discover -s tests -p 'test_*.py'

test: test-hooks test-python

# BATS_SOURCES run at --severity=warning, unlike SHELL_SOURCES which run at
# shellcheck's default: bats' run/@test model emits SC2030/SC2031 subshell
# notices structurally, which say nothing about correctness.
lint-hooks:
	@if [ -n "$(SHELLCHECK)" ]; then \
	  shellcheck $(SHELL_SOURCES) && printf "shellcheck OK\n" || exit 1; \
	  if [ -n "$(BATS_SOURCES)" ]; then shellcheck --severity=warning $(BATS_SOURCES) && printf "shellcheck bats OK\n" || exit 1; fi; \
	else \
	  printf "shellcheck not found, skipping (install: brew install shellcheck)\n"; \
	fi

changelog:
	git-cliff -o CHANGELOG.md

# 10-80-10 cycle (ADR-0009/0010 in ai-config) — validate a plan file
validate-plan:
ifndef PLAN
	@printf "error: PLAN is required, e.g. make validate-plan PLAN=docs/superpowers/plans/foo.md\n" >&2
	@exit 2
endif
	@python3 ~/.claude/scripts/validate-plan.py "$(PLAN)"
