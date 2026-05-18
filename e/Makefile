.PHONY: run lint test coverage mutants clean

run:
	python3 e.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_e -v

coverage:
	python3 -m coverage run -m unittest test_e
	python3 -m coverage report --fail-under=90


benchmark:
	printf "10000\n" | timeout 30 python3 e.py
mutants:
	mutmut run || true
	mutmut results
clean:
	rm -rf __pycache__ .coverage
