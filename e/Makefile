.PHONY: run lint test coverage mutants mutants-baseline mutants-report mutants-clean clean

run:
	python3 e.py

lint:
	ruff check .
	ruff format --check .

test: lint
	pytest test_e.py -v
	python3 ../scripts/cli_contract.py e.py

coverage:
	pytest --cov=e --cov-report=term-missing --cov-fail-under=90 test_e.py

CELL_LABEL ?= e

mutants-baseline:
	@command -v cosmic-ray >/dev/null || { printf "cosmic-ray not installed: pip install cosmic-ray\n" >&2; exit 1; }
	cosmic-ray baseline cosmic-ray.toml || { python3 -m unittest test_e; exit 1; }

mutants: mutants-baseline
	@bash -c 'if [ -n "$${MUTANTS_UNCAPPED}" ]; then \
	    printf "warning: MUTANTS_UNCAPPED set — running without a memory cap.\n" >&2; \
	  else \
	    ulimit -v 8388608 2>/dev/null || { \
	      printf "error: this platform cannot enforce a memory cap (ulimit -v unsupported).\n" >&2; \
	      printf "  An allocation-unbounded mutant will consume system memory until the OS intervenes.\n" >&2; \
	      printf "  Re-run with MUTANTS_UNCAPPED=1 to proceed anyway, or use the Linux path.\n" >&2; \
	      exit 1; }; \
	  fi; \
	  rm -f cosmic-ray-session.sqlite || exit 1; \
	  cosmic-ray init cosmic-ray.toml cosmic-ray-session.sqlite || exit 1; \
	  if [ -n "$${MUTANT_SHARD}" ]; then \
	    case "$${MUTANT_SHARD}" in \
	      *[!0-9/]* | */*/* | /* | */) \
	        printf "error: MUTANT_SHARD must be k/n, got %s\n" "$${MUTANT_SHARD}" >&2; exit 1 ;; \
	    esac; \
	    python3 ../scripts/cosmic_ray_shard.py cosmic-ray-session.sqlite "$$(printf %s "$${MUTANT_SHARD}" | cut -d/ -f1)" "$$(printf %s "$${MUTANT_SHARD}" | cut -d/ -f2)" || exit 1; \
	  fi; \
	  cosmic-ray exec cosmic-ray.toml cosmic-ray-session.sqlite || exit 1; \
	  $(MAKE) -s mutants-report || exit 1; \
	  exec python3 ../scripts/cosmic_ray_cell_status.py cosmic-ray-session.sqlite "$(CELL_LABEL)"$(if $(STATUS_OUT), --out "$(STATUS_OUT)")$(if $(SURVIVORS_OUT), --survivors "$(SURVIVORS_OUT)")'

mutants-report:
	@cr-report cosmic-ray-session.sqlite --show-output --show-diff > mutants-report.txt
	@cr-report cosmic-ray-session.sqlite | tail -5

mutants-clean:
	rm -f cosmic-ray-session.sqlite mutants-report.txt

clean: mutants-clean
	rm -rf __pycache__ .coverage e_*.txt
