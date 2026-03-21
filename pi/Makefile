.PHONY: run test coverage clean

run:
	python3 pi.py

test:
	python3 -m unittest test_pi -v

coverage:
	python3 -m coverage run -m unittest test_pi
	python3 -m coverage report

clean:
	rm -rf __pycache__ .coverage
