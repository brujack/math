.PHONY: install-hooks test-hooks lint-hooks changelog validate-plan

# Every shell file at the repo root that nothing else lints: the six scripts in
# scripts/ (three of them extensionless hooks, so an extension-keyed sweep skips
# them) and the bats suites that cover them. None of these was shellchecked by
# any target or workflow before.
SHELL_SOURCES := scripts/ci-gate.sh scripts/mutation-classify.sh scripts/rust-check.sh \
                 scripts/pre-commit scripts/pre-push scripts/commit-msg
BATS_SOURCES := $(shell find tests -name '*.bats' | sort)

install-hooks:
	ln -sf "../../scripts/pre-commit" "$$(git rev-parse --git-path hooks)/pre-commit"
	ln -sf "../../scripts/pre-push" "$$(git rev-parse --git-path hooks)/pre-push"
	ln -sf "../../scripts/commit-msg" "$$(git rev-parse --git-path hooks)/commit-msg"
	@printf "Pre-commit, pre-push, and commit-msg hooks installed\n"

test-hooks:
	bats --recursive tests/

# --severity=warning, not shellcheck's default: bats' run/@test model emits
# SC2030/SC2031 subshell notices structurally, which say nothing about
# correctness. Everything at warning+ is fixed and this target is clean.
lint-hooks:
	shellcheck --severity=warning $(SHELL_SOURCES)
	@if [ -n "$(BATS_SOURCES)" ]; then shellcheck --severity=warning $(BATS_SOURCES); fi

changelog:
	git-cliff -o CHANGELOG.md

# 10-80-10 cycle (ADR-0009/0010 in ai-config) — validate a plan file
validate-plan:
ifndef PLAN
	@printf "error: PLAN is required, e.g. make validate-plan PLAN=docs/superpowers/plans/foo.md\n" >&2
	@exit 2
endif
	@python3 ~/.claude/scripts/validate-plan.py "$(PLAN)"
