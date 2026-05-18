.PHONY: run lint test coverage clean

run:
	python3 pi.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_pi -v

coverage:
	python3 -m coverage run -m unittest test_pi
	python3 -m coverage report --fail-under=90

clean:
	rm -rf __pycache__ .coverage
