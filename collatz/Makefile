.PHONY: run lint test coverage clean

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
clean:
	rm -rf __pycache__ .coverage
