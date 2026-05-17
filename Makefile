.PHONY: install-hooks test-hooks

install-hooks:
	ln -sf "../../scripts/pre-commit" "$$(git rev-parse --git-path hooks)/pre-commit"
	ln -sf "../../scripts/pre-push" "$$(git rev-parse --git-path hooks)/pre-push"
	ln -sf "../../scripts/commit-msg" "$$(git rev-parse --git-path hooks)/commit-msg"
	@printf "Pre-commit, pre-push, and commit-msg hooks installed\n"

test-hooks:
	bats --recursive tests/
