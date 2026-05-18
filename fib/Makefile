.PHONY: run lint test coverage clean

run:
	python3 fib.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_fib -v

coverage:
	python3 -m coverage run -m unittest test_fib
	python3 -m coverage report --fail-under=90


benchmark:
	timeout 30 python3 fib.py 5000
clean:
	rm -rf __pycache__ .coverage
