.PHONY: run lint test coverage mutants mutants-report mutants-clean clean

run:
	python3 pi.py

lint:
	ruff check .
	ruff format --check .

test: lint
	pytest test_pi.py -v

coverage:
	pytest --cov=pi --cov-report=term-missing --cov-fail-under=90 test_pi.py


benchmark:
	printf "10000\n" | timeout 30 python3 pi.py
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
	rm -rf __pycache__ .coverage
