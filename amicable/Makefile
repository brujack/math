.PHONY: run lint test coverage mutants mutants-report mutants-clean clean

run:
	python3 amicable.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_amicable -v

coverage:
	python3 -m coverage run -m unittest test_amicable
	python3 -m coverage report --fail-under=90


benchmark:
	printf "100000\n" | timeout 60 python3 amicable.py
mutants:
	@command -v cosmic-ray >/dev/null || { printf "cosmic-ray not installed: pip install cosmic-ray\n" >&2; exit 1; }
	rm -f cosmic-ray-session.sqlite
	cosmic-ray init cosmic-ray.toml cosmic-ray-session.sqlite
	cosmic-ray exec cosmic-ray.toml cosmic-ray-session.sqlite
	@$(MAKE) -s mutants-report

mutants-report:
	@cr-report cosmic-ray-session.sqlite --show-output --show-diff > mutants-report.txt
	@cr-report cosmic-ray-session.sqlite | tail -5

mutants-clean:
	rm -f cosmic-ray-session.sqlite mutants-report.txt

clean: mutants-clean
	rm -rf __pycache__ .coverage amicable_1e*.txt
