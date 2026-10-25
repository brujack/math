.PHONY: sq lint test bench clean mutants install

sq:
	cargo build --release

# Installs to the XDG user bin dir on Linux and macOS alike; make sq alone
# writes nothing outside the crate.
install: sq
	@dest="$${XDG_BIN_HOME:-$$HOME/.local/bin}"; \
	mkdir -p "$$dest" && cp target/release/sq "$$dest/sq" && \
	printf 'installed %s\n' "$$dest/sq"

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

bench:
	cargo bench

mutants:
	@bash -c 'if [ -n "$${MUTANTS_UNCAPPED}" ]; then \
	    printf "warning: MUTANTS_UNCAPPED set — running without a memory cap.\n" >&2; \
	  else \
	    ulimit -v 8388608 2>/dev/null || { \
	      printf "error: this platform cannot enforce a memory cap (ulimit -v unsupported).\n" >&2; \
	      printf "  An allocation-unbounded mutant will consume system memory until the OS intervenes.\n" >&2; \
	      printf "  Re-run with MUTANTS_UNCAPPED=1 to proceed anyway, or use the Linux path.\n" >&2; \
	      exit 1; }; \
	  fi; exec cargo mutants --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle'

clean:
	cargo clean
