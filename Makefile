.PHONY: install-hooks

install-hooks:
	ln -sf ../../scripts/pre-commit .git/hooks/pre-commit
	@printf "pre-commit hook installed\n"
