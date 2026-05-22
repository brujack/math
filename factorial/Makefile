.PHONY: run lint test coverage mutants clean

run:
	python3 factorial.py

lint:
	ruff check .
	pyright .

test: lint
	python3 -m unittest test_factorial -v

coverage:
	python3 -m coverage run -m unittest test_factorial
	python3 -m coverage report --fail-under=90


benchmark:
	timeout 30 python3 factorial.py 1000
mutants:
	mutmut run || true
	mutmut results
clean:
	rm -rf __pycache__ .coverage
