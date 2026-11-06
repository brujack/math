.PHONY: factorial lint test bench clean mutants mutants-diff install

factorial:
	cargo build --release

# Installs to the XDG user bin dir on Linux and macOS alike; make factorial alone
# writes nothing outside the crate.
install: factorial
	@dest="$${XDG_BIN_HOME:-$$HOME/.local/bin}"; \
	mkdir -p "$$dest" && cp target/release/factorial "$$dest/factorial" && \
	printf 'installed %s\n' "$$dest/factorial"

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

bench:
	cargo bench

# Killed timeout tests never drop their TempDir and /tmp is tmpfs (RAM), so TMPDIR is a dir under target, removed on exit.
# ulimit -f (1 KiB units in bash -c) kills a mutant that writes unbounded output at 256 MiB.
# cleanup ignores TERM/HUP/INT so a repeated signal (a group-wide TERM plus the one make forwards to this shell) cannot stop the rm;
# the TERM/HUP traps route a first TERM/HUP through EXIT.
# MUTANTS_SETUP is the whole shared preamble (caps, TMPDIR, traps) of the mutants and mutants-diff targets, so a cap changes here once.
MUTANTS_SETUP = rm -rf mutants.out; \
	  t="$$(pwd)/target/mutants-tmp"; rm -rf -- "$$t"; mkdir -p "$$t"; export TMPDIR="$$t"; ulimit -f 262144 2>/dev/null || { printf "error: cannot set the 256 MiB file-size cap (ulimit -f).\n" >&2; exit 1; }; cleanup() { trap "" TERM HUP INT; rm -rf -- "$$t"; }; trap cleanup EXIT; trap "exit 143" TERM; trap "exit 129" HUP; \
	  if [ -n "$${MUTANTS_UNCAPPED}" ]; then \
	    printf "warning: MUTANTS_UNCAPPED set — running without a memory cap.\n" >&2; \
	  else \
	    ulimit -v 8388608 2>/dev/null || { \
	      printf "error: this platform cannot enforce a memory cap (ulimit -v unsupported).\n" >&2; \
	      printf "  An allocation-unbounded mutant will consume system memory until the OS intervenes.\n" >&2; \
	      printf "  Re-run with MUTANTS_UNCAPPED=1 to proceed anyway, or use the Linux path.\n" >&2; \
	      exit 1; }; \
	  fi

# MUTANTS_TAIL records cargo's exit code in mutants.out/exit-code and exits with it; it must directly follow the cargo command.
MUTANTS_TAIL = rc=$$?; \
	  mkdir -p mutants.out && printf "%s\n" "$${rc}" > mutants.out/exit-code; exit "$${rc}"

mutants:
	@bash -c '$(MUTANTS_SETUP); \
	  cargo mutants --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle; $(MUTANTS_TAIL)'

# PR-scoped run: only mutants inside DIFF, same memory cap, file cap, TMPDIR handling, signal-safe cleanup and timeout scaling as mutants.
mutants-diff:
	@bash -c 'd="$${DIFF}"; \
	  if [ -z "$${d}" ] || [ ! -f "$${d}" ] || [ ! -r "$${d}" ]; then \
	    printf "usage: make mutants-diff DIFF=<readable diff file> (DIFF unset or unreadable)\n" >&2; exit 2; \
	  fi; \
	  $(MUTANTS_SETUP); \
	  cargo mutants --in-diff "$${d}" --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle; $(MUTANTS_TAIL)'

clean:
	cargo clean
