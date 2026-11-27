.PHONY: run lint test coverage mutants mutants-baseline mutants-diff-plan mutants-diff mutants-weakening mutants-report mutants-clean clean

# Set only when ruff answers --version, so a ruff that is on PATH but not runnable is skipped, not an Error 127.
RUFF := $(shell ruff --version >/dev/null 2>&1 && command -v ruff)

run:
	python3 descartes.py

ifdef RUFF
lint:
	ruff check .
	ruff format --check .
else
lint:
	@printf "ruff not found, skipping (install: pip install ruff==0.17.4)\n"
endif

test: lint
	pytest test_descartes.py -v
	python3 ../scripts/cli_contract.py descartes.py

coverage:
	pytest --cov=descartes --cov-report=term-missing --cov-fail-under=90 test_descartes.py

CELL_LABEL ?= descartes
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
	  cosmic-ray baseline cosmic-ray.toml || { python3 -m unittest test_descartes; exit 1; }'

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
	  out="$${OUT_DIR:-$$proj}"; sp="$$SESSION"; rp="$$REPORT"; \
	  if [ -n "$${OUT_DIR}" ]; then sp="$$OUT_DIR/$$SESSION"; rp="$$OUT_DIR/$$REPORT"; fi; \
	  if [ "$$MODE" != plan ]; then rm -f "$$sp" "$$sp-journal" "$$rp" || exit 1; fi; \
	  mkdir -p "$$proj/.mutants-tmp" || exit 1; \
	  work="$$(mktemp -d "$$proj/.mutants-tmp/$$WORK-descartes.XXXXXX")" || exit 1; \
	  cleanup() { \
	    trap "" TERM HUP INT; \
	    ok=1; \
	    if [ "$$MODE" != plan ]; then \
	      if [ -f "$$work/descartes/$$SESSION" ]; then \
	        cp -- "$$work/descartes/$$SESSION"* "$$out/" || ok=; \
	      fi; \
	      if [ -f "$$work/descartes/$$REPORT" ]; then \
	        cp -- "$$work/descartes/$$REPORT" "$$out/" || ok=; \
	      fi; \
	    fi; \
	    if [ -n "$$ok" ]; then rm -rf -- "$$work"; \
	    else printf "%s: kept %s (copy-back failed)\n" "$$WORK" "$$work" >&2; fi; \
	  }; \
	  trap cleanup EXIT; trap "exit 143" TERM; trap "exit 129" HUP; \
	  mkdir "$$work/descartes" "$$work/tmp" || exit 1; \
	  export TMPDIR="$$work/tmp"; \
	  cp -- descartes.py test_descartes.py cosmic-ray.toml mutants-equivalent.toml "$$work/descartes/" || exit 1; \
	  ln -s "$$(cd .. && pwd)/scripts" "$$work/scripts" || exit 1; \
	  cd "$$work/descartes" || exit 1; \
	  cosmic-ray init cosmic-ray.toml "$$SESSION" || exit 1; \
	  if [ "$$MODE" = full ]; then \
	    python3 ../scripts/cosmic_ray_prune.py equivalents "$$SESSION" mutants-equivalent.toml --full-run || exit 1; \
	  else \
	    python3 ../scripts/cosmic_ray_prune.py equivalents "$$SESSION" mutants-equivalent.toml --diff "$$DIFF_ABS" --toml-path mutants-equivalent.toml || exit 1; \
	    python3 ../scripts/cosmic_ray_prune.py diff "$$SESSION" "$$DIFF_ABS" descartes.py || exit 1; \
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
	  if [ -n "$${MUTANT_JOB}" ]; then \
	    python3 -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); o,n=sys.argv[2].rsplit(\"@\",1); ids=[r[0] for r in c.execute(\"SELECT job_id FROM mutation_specs WHERE operator_name=? AND occurrence=?\",(o,int(n)))]; len(ids)==1 or sys.exit(\"error: JOB \"+sys.argv[2]+\" is not a mutant of this session\"); c.execute(\"DELETE FROM mutation_specs WHERE job_id != ?\",(ids[0],)); c.execute(\"DELETE FROM work_items WHERE job_id != ?\",(ids[0],)); c.commit()" "$$SESSION" "$${MUTANT_JOB}" || exit 64; \
	  fi; \
	  cosmic-ray exec cosmic-ray.toml "$$SESSION" || exit 1; \
	  cr-report "$$SESSION" --show-output --show-diff > "$$REPORT" || exit 1; \
	  cr-report "$$SESSION" | tail -5; \
	  cp -- "$$SESSION" "$$REPORT" "$$out/" || exit 1; \
	  cd "$$proj" || exit 1; \
	  set -- "$$sp" "$${CELL_LABEL}"; \
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

# The PR weakening check (R7, R31): the head session is the mutants-diff exec path fed the whole-module
# diff (its job set equals the planner's), then judge and replay run on a per-run copy. Everything
# lives under .mutants-tmp/weakening-<pid>.*, removed on exit, so nothing in the tracked tree is
# written (N5). The head session writes into the copy through OUT_DIR, and MUTANT_JOB (from JOB)
# trims it to one job before exec (exit 64 when the job is absent, which stops the run). A red head session does not stop the judge and replay, whose
# summary is still wanted; the target exits non-zero when any step is red.
#   BASE (hex sha) and exactly one of MUTANT_SHARD=<k>/<n> or JOB=<job id> are required;
#   PLANNED (default: the head session's job count, or 1 for JOB), PR and HEAD_SHA are optional.
WEAKENING_GUARD = if [ -z "$$BASE" ]; then printf "error: BASE is required: BASE=<merge-base sha>\n" >&2; exit 1; fi; \
	  case "$$BASE" in *[!0-9a-f]*) printf "error: BASE must be a lowercase hex sha, got %s\n" "$$BASE" >&2; exit 1 ;; esac; \
	  case "$$HEAD_SHA" in *[!0-9a-f]*) printf "error: HEAD_SHA must be a lowercase hex sha, got %s\n" "$$HEAD_SHA" >&2; exit 1 ;; esac; \
	  case "$$PR$$PLANNED" in *[!0-9]*) printf "error: PR and PLANNED must be decimal numbers\n" >&2; exit 1 ;; esac; \
	  case "$$JOB" in "") ;; *@*@* | @* | *@ | *@*[!0-9]* | *[!A-Za-z0-9_./:@-]*) printf "error: JOB must be <operator>@<occurrence>, e.g. core/NumberReplacer@3, got %s\n" "$$JOB" >&2; exit 1 ;; *@*) ;; *) printf "error: JOB must be <operator>@<occurrence>, got %s\n" "$$JOB" >&2; exit 1 ;; esac; \
	  if [ -z "$$MUTANT_SHARD" ] && [ -z "$$JOB" ]; then printf "error: MUTANT_SHARD=<k>/<n> or JOB=<job id> is required\n" >&2; exit 1; fi; \
	  if [ -n "$$MUTANT_SHARD" ] && [ -n "$$JOB" ]; then printf "error: MUTANT_SHARD and JOB are mutually exclusive\n" >&2; exit 1; fi

WEAKENING_BODY = $(MUTANTS_CAP); \
	  proj="$$(pwd)"; \
	  repo="$$(cd .. && pwd)" || exit 1; \
	  mkdir -p "$$proj/.mutants-tmp" || exit 1; \
	  w="$$(mktemp -d "$$proj/.mutants-tmp/weakening-$$$$.XXXXXX")" || exit 1; \
	  cleanup() { trap "" TERM HUP INT; rm -rf -- "$$w"; }; \
	  trap cleanup EXIT; trap "exit 143" TERM; trap "exit 129" HUP; \
	  copy="$$w/descartes"; \
	  mkdir "$$copy" "$$w/tmp" "$$w/profile" "$$w/out" "$$w/work" || exit 1; \
	  cp -- descartes.py test_descartes.py cosmic-ray.toml "$$copy/" || exit 1; \
	  if [ -f mutants-equivalent.toml ]; then cp -- mutants-equivalent.toml "$$copy/" || exit 1; fi; \
	  export TMPDIR="$$w/tmp" PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$$w/profile"; \
	  python3 ../scripts/mutation_hypothesis_profile.py write "$$w/profile" || exit 1; \
	  python3 ../scripts/mutation_hypothesis_profile.py preflight "$$w/profile" || exit 1; \
	  bash ../scripts/mutation-whole-module-diff.sh "$$proj" "$$w/whole.diff" || exit 1; \
	  red=0; \
	  env MODE=exec WORK=weakening SESSION=head.sqlite REPORT=head-report.txt OUT_DIR="$$w/out" DIFF_ABS="$$w/whole.diff" bash -c "$$HEAD_BODY"; hrc=$$?; \
	  if [ "$$hrc" -eq 64 ]; then exit 1; fi; \
	  if [ "$$hrc" -ne 0 ]; then red=1; fi; \
	  if [ ! -f "$$w/out/head.sqlite" ]; then printf "error: the head session left no session file\n" >&2; exit 1; fi; \
	  python3 ../scripts/mutation_weakening.py judge --dir "$$copy" --base "$$BASE" --work "$$w/work" --after-head --repo "$$repo"; rc=$$?; \
	  case "$$rc" in 0) ;; 3) exit "$$red" ;; *) exit 1 ;; esac; \
	  if [ -n "$${PLANNED}" ]; then planned="$$PLANNED"; \
	  elif [ -n "$${MUTANT_JOB}" ]; then planned=1; \
	  else planned="$$(python3 -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute(\"SELECT count(*) FROM work_items\").fetchone()[0])" "$$w/out/head.sqlite")" || exit 1; fi; \
	  set -- --dir "$$copy" --session "$$w/out/head.sqlite" --shard "$${MUTANT_SHARD:-0/1}" --planned "$$planned" --base "$$BASE" --work "$$w/work" --repo "$$repo"; \
	  if [ -n "$${PR}" ]; then set -- "$$@" --pr "$$PR"; fi; \
	  if [ -n "$${HEAD_SHA}" ]; then set -- "$$@" --head "$$HEAD_SHA"; fi; \
	  python3 ../scripts/mutation_weakening.py replay "$$@" || exit 1; \
	  exit "$$red"

mutants-weakening:
	@$(WEAKENING_GUARD)
	@$(MAKE) --no-print-directory mutants-baseline
	@env MUTANT_JOB="$$JOB" HEAD_BODY='$(MUTANTS_BODY)' bash -c '$(WEAKENING_BODY)'

mutants-report:
	@cr-report cosmic-ray-session.sqlite --show-output --show-diff > mutants-report.txt
	@cr-report cosmic-ray-session.sqlite | tail -5

mutants-clean:
	rm -f cosmic-ray-session.sqlite cosmic-ray-session.sqlite-journal mutants-report.txt
	rm -f cosmic-ray-diff-session.sqlite cosmic-ray-diff-session.sqlite-journal mutants-diff-report.txt
	rm -rf .mutants-tmp

clean: mutants-clean
	rm -rf __pycache__ .coverage descartes_*.txt
