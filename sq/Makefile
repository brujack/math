.PHONY: run lint test coverage clean

run:
	python3 sq.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_sq -v

coverage:
	coverage run -m unittest test_sq -v
	coverage report -m --fail-under=90
