.PHONY: run lint test coverage mutants mutants-baseline mutants-diff-plan mutants-diff mutants-report mutants-clean clean

# Set only when ruff answers --version, so a ruff that is on PATH but not runnable is skipped, not an Error 127.
RUFF := $(shell ruff --version >/dev/null 2>&1 && command -v ruff)

run:
	python3 pi.py

ifdef RUFF
lint:
	ruff check .
	ruff format --check .
else
lint:
	@printf "ruff not found, skipping (install: pip install ruff==0.17.4)\n"
endif

test: lint
	pytest test_pi.py -v
	python3 ../scripts/cli_contract.py pi.py

coverage:
	pytest --cov=pi --cov-report=term-missing --cov-fail-under=90 test_pi.py

CELL_LABEL ?= pi
export CELL_LABEL STATUS_OUT SURVIVORS_OUT MUTANT_SHARD

# The memory and file-size caps, shared by every recipe that runs cosmic-ray (same caps as the Rust
# template). ulimit -f (1 KiB units in bash -c) ends a mutant writing unbounded output at 256 MiB.
# ulimit -c 0 disables core dumps: hosted runners pipe them to systemd-coredump with an unlimited limit, and capped-out mutants streamed multi-GB dumps that killed the runner (ADR-0043).
MUTANTS_CAP = ulimit -f 262144 2>/dev/null || { printf "error: cannot set the 256 MiB file-size cap (ulimit -f).\n" >&2; exit 1; }; ulimit -c 0 2>/dev/null || { printf "error: cannot disable core dumps (ulimit -c 0).\n" >&2; exit 1; }; if [ -n "$${MUTANTS_UNCAPPED}" ]; then \
	    printf "warning: MUTANTS_UNCAPPED set — running without a memory cap.\n" >&2; \
	  else \
	    ulimit -v 8388608 2>/dev/null || { \
	      printf "error: this platform cannot enforce a memory cap (ulimit -v unsupported).\n" >&2; \
	      printf "  An allocation-unbounded mutant will consume system memory until the OS intervenes.\n" >&2; \
	      printf "  Re-run with MUTANTS_UNCAPPED=1 to proceed anyway, or use the Linux path.\n" >&2; \
	      exit 1; }; \
	  fi

# cleanup ignores TERM/HUP/INT so a repeated signal (a group-wide TERM plus the one make forwards to this shell) cannot stop the rm;
# here and in mutants below, the TERM/HUP traps route a first TERM/HUP through EXIT.
mutants-baseline:
	@command -v cosmic-ray >/dev/null || { printf "cosmic-ray not installed: pip install cosmic-ray\n" >&2; exit 1; }
	@bash -c '$(MUTANTS_CAP); \
	  mkdir -p "$$(pwd)/.mutants-tmp" || exit 1; \
	  b="$$(mktemp -d "$$(pwd)/.mutants-tmp/baseline.XXXXXX")" || exit 1; \
	  cleanup() { trap "" TERM HUP INT; rm -rf -- "$$b"; }; \
	  trap cleanup EXIT; trap "exit 143" TERM; trap "exit 129" HUP; \
	  export TMPDIR="$$b"; \
	  cosmic-ray baseline cosmic-ray.toml || { python3 -m unittest test_pi; exit 1; }'

# The directory make was started from: make -C changes CURDIR but not the PWD it inherited from the
# invoking shell. Relative DIFF, STATUS_OUT and SURVIVORS_OUT of the mutants-diff targets are resolved
# against it; with no usable PWD, against CURDIR. PWD must be the shell-accurate invoking directory: a
# parent that changes cwd without updating PWD resolves against the stale directory. CI passes absolute paths.
INVOKE_DIR := $(if $(filter /%,$(PWD)),$(PWD),$(CURDIR))
ABS_OF = $(if $(1),$(if $(filter /%,$(1)),$(1),$(INVOKE_DIR)/$(1)))
DIFF_ABS = $(call ABS_OF,$(DIFF))
STATUS_OUT_ABS = $(call ABS_OF,$(STATUS_OUT))
SURVIVORS_OUT_ABS = $(call ABS_OF,$(SURVIVORS_OUT))
export DIFF_ABS STATUS_OUT_ABS SURVIVORS_OUT_ABS

# One body for the three scratch-copy runs, parameterised by the environment the recipes set:
#   MODE     full (mutants: whole session, equivalents --full-run), plan (mutants-diff-plan: prune only,
#            nothing written in the project) or exec (mutants-diff: prune to the diff, run, max-survivors 0)
#   WORK     scratch dir prefix and the name in the copy-back warning
#   SESSION, REPORT   the project-side file names; the diff pair differs from the full pair so a local
#            diff run never overwrites the full run's cosmic-ray-session.sqlite or mutants-report.txt
# Runs in a scratch copy of the module, its test, the config and the equivalents file only: the project
# directory also holds <crate>-rs/target (up to ~1.8 GB). The scratch dir and TMPDIR live in the
# project's gitignored .mutants-tmp, not /tmp (tmpfs, RAM): cosmic-ray kills tests mid-write and
# their tempfile dirs would otherwise leak; here cleanup removes them with the scratch copy.
MUTANTS_BODY = $(MUTANTS_CAP); \
	  proj="$$(pwd)"; \
	  if [ "$$MODE" != plan ]; then rm -f "$$SESSION" "$$SESSION-journal" "$$REPORT" || exit 1; fi; \
	  mkdir -p "$$proj/.mutants-tmp" || exit 1; \
	  work="$$(mktemp -d "$$proj/.mutants-tmp/$$WORK-pi.XXXXXX")" || exit 1; \
	  cleanup() { \
	    trap "" TERM HUP INT; \
	    ok=1; \
	    if [ "$$MODE" != plan ]; then \
	      if [ -f "$$work/pi/$$SESSION" ]; then \
	        cp -- "$$work/pi/$$SESSION"* "$$proj/" || ok=; \
	      fi; \
	      if [ -f "$$work/pi/$$REPORT" ]; then \
	        cp -- "$$work/pi/$$REPORT" "$$proj/" || ok=; \
	      fi; \
	    fi; \
	    if [ -n "$$ok" ]; then rm -rf -- "$$work"; \
	    else printf "%s: kept %s (copy-back failed)\n" "$$WORK" "$$work" >&2; fi; \
	  }; \
	  trap cleanup EXIT; trap "exit 143" TERM; trap "exit 129" HUP; \
	  mkdir "$$work/pi" "$$work/tmp" || exit 1; \
	  export TMPDIR="$$work/tmp"; \
	  cp -- pi.py test_pi.py cosmic-ray.toml mutants-equivalent.toml "$$work/pi/" || exit 1; \
	  ln -s "$$(cd .. && pwd)/scripts" "$$work/scripts" || exit 1; \
	  cd "$$work/pi" || exit 1; \
	  cosmic-ray init cosmic-ray.toml "$$SESSION" || exit 1; \
	  if [ "$$MODE" = full ]; then \
	    python3 ../scripts/cosmic_ray_prune.py equivalents "$$SESSION" mutants-equivalent.toml --full-run || exit 1; \
	  else \
	    python3 ../scripts/cosmic_ray_prune.py equivalents "$$SESSION" mutants-equivalent.toml --diff "$$DIFF_ABS" --toml-path mutants-equivalent.toml || exit 1; \
	    python3 ../scripts/cosmic_ray_prune.py diff "$$SESSION" "$$DIFF_ABS" pi.py || exit 1; \
	  fi; \
	  if [ "$$MODE" = plan ]; then exit 0; fi; \
	  if [ -n "$${MUTANT_SHARD}" ]; then \
	    case "$${MUTANT_SHARD}" in \
	      *[!0-9/]* | */*/* | /* | */) bad=1 ;; \
	      */*) bad= ;; \
	      *) bad=1 ;; \
	    esac; \
	    if [ -n "$${bad}" ]; then printf "error: MUTANT_SHARD must be k/n, got %s\n" "$${MUTANT_SHARD}" >&2; exit 1; fi; \
	    python3 ../scripts/cosmic_ray_shard.py "$$SESSION" "$$(printf %s "$${MUTANT_SHARD}" | cut -d/ -f1)" "$$(printf %s "$${MUTANT_SHARD}" | cut -d/ -f2)" || exit 1; \
	  fi; \
	  cosmic-ray exec cosmic-ray.toml "$$SESSION" || exit 1; \
	  cr-report "$$SESSION" --show-output --show-diff > "$$REPORT" || exit 1; \
	  cr-report "$$SESSION" | tail -5; \
	  cp -- "$$SESSION" "$$REPORT" "$$proj/" || exit 1; \
	  cd "$$proj" || exit 1; \
	  set -- "$$SESSION" "$${CELL_LABEL}"; \
	  if [ "$$MODE" = full ]; then \
	    if [ -n "$${STATUS_OUT}" ]; then set -- "$$@" --out "$${STATUS_OUT}"; fi; \
	    if [ -n "$${SURVIVORS_OUT}" ]; then set -- "$$@" --survivors "$${SURVIVORS_OUT}"; fi; \
	    python3 ../scripts/cosmic_ray_cell_status.py "$$@"; exit $$?; \
	  fi; \
	  set -- "$$@" --max-survivors 0; \
	  if [ -n "$${SURVIVORS_OUT_ABS}" ]; then set -- "$$@" --survivors "$${SURVIVORS_OUT_ABS}"; fi; \
	  python3 ../scripts/cosmic_ray_cell_status.py "$$@" > "$$work/status.out"; rc=$$?; \
	  cat "$$work/status.out"; \
	  if [ -n "$${STATUS_OUT_ABS}" ]; then cp -- "$$work/status.out" "$${STATUS_OUT_ABS}" || exit 1; fi; \
	  exit "$$rc"

# `env` rather than a VAR=... prefix: dash does not exec a command that carries assignments, which would
# leave an extra sh between make and bash that dies on the group TERM and lets make exit mid-cleanup.
mutants: mutants-baseline
	@env MODE=full WORK=mutants SESSION=cosmic-ray-session.sqlite REPORT=mutants-report.txt bash -c '$(MUTANTS_BODY)'

# The DIFF check is the first line of each recipe, not a prerequisite: make -k and -j start sibling
# prerequisites regardless, and the baseline calls cosmic-ray, which a missing DIFF must never reach.
# Make exits 2 on a failed recipe line.
DIFF_GUARD = if [ -z "$(DIFF)" ]; then printf "error: DIFF is required: DIFF=<unified diff file>\n" >&2; exit 1; fi; if [ ! -f "$(DIFF_ABS)" ] || [ ! -r "$(DIFF_ABS)" ]; then printf "error: DIFF %s is not a readable file\n" "$(DIFF)" >&2; exit 1; fi

# Prints the prune summary lines (excluded E of T ..., kept K of T (lines L)) and runs no mutant.
mutants-diff-plan:
	@$(DIFF_GUARD)
	@$(MAKE) --no-print-directory mutants-baseline
	@env MODE=plan WORK=mutants-diff SESSION=cosmic-ray-diff-session.sqlite REPORT=mutants-diff-report.txt bash -c '$(MUTANTS_BODY)'

# STATUS_OUT receives cell_status's whole stdout (verdict, survivor keys, diffs), not just its first line.
mutants-diff:
	@$(DIFF_GUARD)
	@$(MAKE) --no-print-directory mutants-baseline
	@env MODE=exec WORK=mutants-diff SESSION=cosmic-ray-diff-session.sqlite REPORT=mutants-diff-report.txt bash -c '$(MUTANTS_BODY)'

mutants-report:
	@cr-report cosmic-ray-session.sqlite --show-output --show-diff > mutants-report.txt
	@cr-report cosmic-ray-session.sqlite | tail -5

mutants-clean:
	rm -f cosmic-ray-session.sqlite cosmic-ray-session.sqlite-journal mutants-report.txt
	rm -f cosmic-ray-diff-session.sqlite cosmic-ray-diff-session.sqlite-journal mutants-diff-report.txt
	rm -rf .mutants-tmp

clean: mutants-clean
	rm -rf __pycache__ .coverage pi_*.txt
