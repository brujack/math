.PHONY: run lint test coverage clean

run:
	python3 perfect_numbers.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_perfect_numbers -v

coverage:
	python3 -m coverage run -m unittest test_perfect_numbers
	python3 -m coverage report

clean:
	rm -rf __pycache__ .coverage
