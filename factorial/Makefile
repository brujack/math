.PHONY: run lint test coverage mutants mutants-baseline mutants-report mutants-clean clean

# Set only when ruff answers --version, so a ruff that is on PATH but not runnable is skipped, not an Error 127.
RUFF := $(shell ruff --version >/dev/null 2>&1 && command -v ruff)

run:
	python3 factorial.py

ifdef RUFF
lint:
	ruff check .
	ruff format --check .
else
lint:
	@printf "ruff not found, skipping (install: pip install ruff==0.16.4)\n"
endif

test: lint
	pytest test_factorial.py -v
	python3 ../scripts/cli_contract.py factorial.py

coverage:
	pytest --cov=factorial --cov-report=term-missing --cov-fail-under=90 test_factorial.py

CELL_LABEL ?= factorial
export CELL_LABEL STATUS_OUT SURVIVORS_OUT MUTANT_SHARD

# The memory cap, shared by every recipe that runs cosmic-ray (same text as the Rust template).
MUTANTS_CAP = if [ -n "$${MUTANTS_UNCAPPED}" ]; then \
	    printf "warning: MUTANTS_UNCAPPED set — running without a memory cap.\n" >&2; \
	  else \
	    ulimit -v 8388608 2>/dev/null || { \
	      printf "error: this platform cannot enforce a memory cap (ulimit -v unsupported).\n" >&2; \
	      printf "  An allocation-unbounded mutant will consume system memory until the OS intervenes.\n" >&2; \
	      printf "  Re-run with MUTANTS_UNCAPPED=1 to proceed anyway, or use the Linux path.\n" >&2; \
	      exit 1; }; \
	  fi

mutants-baseline:
	@command -v cosmic-ray >/dev/null || { printf "cosmic-ray not installed: pip install cosmic-ray\n" >&2; exit 1; }
	@bash -c '$(MUTANTS_CAP); \
	  cosmic-ray baseline cosmic-ray.toml || { python3 -m unittest test_factorial; exit 1; }'

mutants: mutants-baseline
	@bash -c '$(MUTANTS_CAP); \
	  proj="$$(pwd)"; \
	  rm -f cosmic-ray-session.sqlite mutants-report.txt || exit 1; \
	  work="$$(mktemp -d "$${TMPDIR:-/tmp}/mutants-factorial.XXXXXX")" || exit 1; \
	  work="$$(CDPATH="" cd -- "$$work" >/dev/null && pwd)" || exit 1; \
	  cleanup() { \
	    trap "" TERM HUP INT; \
	    ok=1; \
	    if [ -f "$$work/factorial/cosmic-ray-session.sqlite" ]; then \
	      cp -- "$$work/factorial"/cosmic-ray-session.sqlite* "$$proj/" || ok=; \
	    fi; \
	    if [ -f "$$work/factorial/mutants-report.txt" ]; then \
	      cp -- "$$work/factorial/mutants-report.txt" "$$proj/" || ok=; \
	    fi; \
	    if [ -n "$$ok" ]; then rm -rf -- "$$work"; \
	    else printf "mutants: kept %s (copy-back failed)\n" "$$work" >&2; fi; \
	  }; \
	  trap cleanup EXIT; trap "exit 143" TERM; trap "exit 129" HUP; \
	  mkdir "$$work/factorial" || exit 1; \
	  cp -- factorial.py test_factorial.py cosmic-ray.toml "$$work/factorial/" || exit 1; \
	  ln -s "$$(cd .. && pwd)/scripts" "$$work/scripts" || exit 1; \
	  cd "$$work/factorial" || exit 1; \
	  cosmic-ray init cosmic-ray.toml cosmic-ray-session.sqlite || exit 1; \
	  if [ -n "$${MUTANT_SHARD}" ]; then \
	    case "$${MUTANT_SHARD}" in \
	      *[!0-9/]* | */*/* | /* | */) bad=1 ;; \
	      */*) bad= ;; \
	      *) bad=1 ;; \
	    esac; \
	    if [ -n "$${bad}" ]; then printf "error: MUTANT_SHARD must be k/n, got %s\n" "$${MUTANT_SHARD}" >&2; exit 1; fi; \
	    python3 ../scripts/cosmic_ray_shard.py cosmic-ray-session.sqlite "$$(printf %s "$${MUTANT_SHARD}" | cut -d/ -f1)" "$$(printf %s "$${MUTANT_SHARD}" | cut -d/ -f2)" || exit 1; \
	  fi; \
	  cosmic-ray exec cosmic-ray.toml cosmic-ray-session.sqlite || exit 1; \
	  cr-report cosmic-ray-session.sqlite --show-output --show-diff > mutants-report.txt || exit 1; \
	  cr-report cosmic-ray-session.sqlite | tail -5; \
	  cp -- cosmic-ray-session.sqlite mutants-report.txt "$$proj/" || exit 1; \
	  cd "$$proj" || exit 1; \
	  set -- cosmic-ray-session.sqlite "$${CELL_LABEL}"; \
	  if [ -n "$${STATUS_OUT}" ]; then set -- "$$@" --out "$${STATUS_OUT}"; fi; \
	  if [ -n "$${SURVIVORS_OUT}" ]; then set -- "$$@" --survivors "$${SURVIVORS_OUT}"; fi; \
	  python3 ../scripts/cosmic_ray_cell_status.py "$$@"'

mutants-report:
	@cr-report cosmic-ray-session.sqlite --show-output --show-diff > mutants-report.txt
	@cr-report cosmic-ray-session.sqlite | tail -5

mutants-clean:
	rm -f cosmic-ray-session.sqlite mutants-report.txt

clean: mutants-clean
	rm -rf __pycache__ .coverage factorial_*.txt
