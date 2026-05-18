.PHONY: run lint test coverage clean

run:
	python3 e.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_e -v

coverage:
	python3 -m coverage run -m unittest test_e
	python3 -m coverage report --fail-under=90

clean:
	rm -rf __pycache__ .coverage
