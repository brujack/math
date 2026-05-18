.PHONY: run lint test coverage mutants clean

run:
	python3 pi.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_pi -v

coverage:
	python3 -m coverage run -m unittest test_pi
	python3 -m coverage report --fail-under=90


benchmark:
	printf "10000\n" | timeout 30 python3 pi.py
mutants:
	mutmut run || true
	mutmut results
clean:
	rm -rf __pycache__ .coverage
