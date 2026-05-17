.PHONY: run lint test coverage clean

run:
	python3 amicable.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_amicable -v

coverage:
	python3 -m coverage run -m unittest test_amicable
	python3 -m coverage report

clean:
	rm -rf __pycache__ .coverage amicable_1e*.txt
