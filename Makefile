.PHONY: install-hooks test-hooks changelog validate-plan validate-memory

install-hooks:
	ln -sf "../../scripts/pre-commit" "$$(git rev-parse --git-path hooks)/pre-commit"
	ln -sf "../../scripts/pre-push" "$$(git rev-parse --git-path hooks)/pre-push"
	ln -sf "../../scripts/commit-msg" "$$(git rev-parse --git-path hooks)/commit-msg"
	@printf "Pre-commit, pre-push, and commit-msg hooks installed\n"

test-hooks:
	bats --recursive tests/

changelog:
	git-cliff -o CHANGELOG.md

# 10-80-10 cycle (ADR-0009/0010 in ai-config) — validate a plan file
validate-plan:
ifndef PLAN
	@printf "error: PLAN is required, e.g. make validate-plan PLAN=docs/superpowers/plans/foo.md\n" >&2
	@exit 2
endif
	@python3 ~/.claude/scripts/validate-plan.py "$(PLAN)"

# Validate canonical memory + retrospective frontmatter (ADR-0014)
validate-memory:
	@if [ -f .claude/scripts/validate_memory.py ]; then \
		python3 .claude/scripts/validate_memory.py --all; \
	elif [ -f "$$HOME/.claude/scripts/validate_memory.py" ]; then \
		python3 "$$HOME/.claude/scripts/validate_memory.py" --all; \
	else \
		printf "validate-memory: validator not found (ai-config not installed); skipping. Local pre-commit gate still enforced.\n" >&2; \
	fi
