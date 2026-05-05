.PHONY: install-hooks test-hooks

install-hooks:
	ln -sf "../../scripts/pre-commit" "$$(git rev-parse --git-path hooks)/pre-commit"
	ln -sf "../../scripts/pre-push" "$$(git rev-parse --git-path hooks)/pre-push"
	@printf "Pre-commit and pre-push hooks installed\n"

test-hooks:
	bats --recursive tests/
