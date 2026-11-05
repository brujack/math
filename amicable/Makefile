.PHONY: run lint test coverage mutants mutants-baseline mutants-report mutants-clean clean

# Set only when ruff answers --version, so a ruff that is on PATH but not runnable is skipped, not an Error 127.
RUFF := $(shell ruff --version >/dev/null 2>&1 && command -v ruff)

run:
	python3 amicable.py

ifdef RUFF
lint:
	ruff check .
	ruff format --check .
else
lint:
	@printf "ruff not found, skipping (install: pip install ruff==0.16.4)\n"
endif

test: lint
	pytest test_amicable.py -v
	python3 ../scripts/cli_contract.py amicable.py

coverage:
	pytest --cov=amicable --cov-report=term-missing --cov-fail-under=90 test_amicable.py

CELL_LABEL ?= amicable
export CELL_LABEL STATUS_OUT SURVIVORS_OUT MUTANT_SHARD

# The memory and file-size caps, shared by every recipe that runs cosmic-ray (same caps as the Rust
# template). ulimit -f (1 KiB units in bash -c) ends a mutant writing unbounded output at 256 MiB.
MUTANTS_CAP = ulimit -f 262144 2>/dev/null || { printf "error: cannot set the 256 MiB file-size cap (ulimit -f).\n" >&2; exit 1; }; if [ -n "$${MUTANTS_UNCAPPED}" ]; then \
	    printf "warning: MUTANTS_UNCAPPED set — running without a memory cap.\n" >&2; \
	  else \
	    ulimit -v 8388608 2>/dev/null || { \
	      printf "error: this platform cannot enforce a memory cap (ulimit -v unsupported).\n" >&2; \
	      printf "  An allocation-unbounded mutant will consume system memory until the OS intervenes.\n" >&2; \
	      printf "  Re-run with MUTANTS_UNCAPPED=1 to proceed anyway, or use the Linux path.\n" >&2; \
	      exit 1; }; \
	  fi

# cleanup ignores TERM/HUP/INT so a repeated signal (make forwards one) cannot stop the rm; the TERM/HUP traps route a first signal through EXIT.
mutants-baseline:
	@command -v cosmic-ray >/dev/null || { printf "cosmic-ray not installed: pip install cosmic-ray\n" >&2; exit 1; }
	@bash -c '$(MUTANTS_CAP); \
	  mkdir -p "$$(pwd)/.mutants-tmp" || exit 1; \
	  b="$$(mktemp -d "$$(pwd)/.mutants-tmp/baseline.XXXXXX")" || exit 1; \
	  cleanup() { trap "" TERM HUP INT; rm -rf -- "$$b"; }; \
	  trap cleanup EXIT; trap "exit 143" TERM; trap "exit 129" HUP; \
	  export TMPDIR="$$b"; \
	  cosmic-ray baseline cosmic-ray.toml || { python3 -m unittest test_amicable; exit 1; }'

# Runs in a scratch copy of the module, its test and the config only: the project
# directory also holds <crate>-rs/target (up to ~1.8 GB). The scratch dir and TMPDIR live in the
# project's gitignored .mutants-tmp, not /tmp (tmpfs, RAM): cosmic-ray kills tests mid-write and
# their tempfile dirs would otherwise leak; here cleanup removes them with the scratch copy.
mutants: mutants-baseline
	@bash -c '$(MUTANTS_CAP); \
	  proj="$$(pwd)"; \
	  rm -f cosmic-ray-session.sqlite cosmic-ray-session.sqlite-journal mutants-report.txt || exit 1; \
	  mkdir -p "$$proj/.mutants-tmp" || exit 1; \
	  work="$$(mktemp -d "$$proj/.mutants-tmp/mutants-amicable.XXXXXX")" || exit 1; \
	  cleanup() { \
	    trap "" TERM HUP INT; \
	    ok=1; \
	    if [ -f "$$work/amicable/cosmic-ray-session.sqlite" ]; then \
	      cp -- "$$work/amicable"/cosmic-ray-session.sqlite* "$$proj/" || ok=; \
	    fi; \
	    if [ -f "$$work/amicable/mutants-report.txt" ]; then \
	      cp -- "$$work/amicable/mutants-report.txt" "$$proj/" || ok=; \
	    fi; \
	    if [ -n "$$ok" ]; then rm -rf -- "$$work"; \
	    else printf "mutants: kept %s (copy-back failed)\n" "$$work" >&2; fi; \
	  }; \
	  trap cleanup EXIT; trap "exit 143" TERM; trap "exit 129" HUP; \
	  mkdir "$$work/amicable" "$$work/tmp" || exit 1; \
	  export TMPDIR="$$work/tmp"; \
	  cp -- amicable.py test_amicable.py cosmic-ray.toml "$$work/amicable/" || exit 1; \
	  ln -s "$$(cd .. && pwd)/scripts" "$$work/scripts" || exit 1; \
	  cd "$$work/amicable" || exit 1; \
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
	rm -f cosmic-ray-session.sqlite cosmic-ray-session.sqlite-journal mutants-report.txt
	rm -rf .mutants-tmp

clean: mutants-clean
	rm -rf __pycache__ .coverage amicable_*.txt
