.PHONY: run lint test coverage mutants mutants-report mutants-clean

run:
	python3 sq.py

lint:
	ruff check .

test: lint
	python3 -m unittest test_sq -v

coverage:
	coverage run -m unittest test_sq -v
	coverage report -m --fail-under=90
benchmark:
	printf "999999999\n" | timeout 30 python3 sq.py
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
