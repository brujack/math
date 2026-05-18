.PHONY: run lint test coverage mutants clean

run:
	python3 collatz.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_collatz -v

coverage:
	python3 -m coverage run -m unittest test_collatz
	python3 -m coverage report --fail-under=90


benchmark:
	timeout 30 python3 collatz.py 5
mutants:
	mutmut run || true
	mutmut results
clean:
	rm -rf __pycache__ .coverage
