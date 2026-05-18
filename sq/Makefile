.PHONY: run lint test coverage mutants

run:
	python3 sq.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_sq -v

coverage:
	coverage run -m unittest test_sq -v
	coverage report -m --fail-under=90
benchmark:
	printf "999999999\n" | timeout 30 python3 sq.py
mutants:
	mutmut run || true
	mutmut results
