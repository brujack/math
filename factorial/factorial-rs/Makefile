.PHONY: factorial lint test bench clean mutants

factorial:
	cargo build --release
	cp target/release/factorial ~/Downloads/factorial

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

bench:
	cargo bench

mutants:
	cargo mutants --timeout 120 --no-shuffle

clean:
	cargo clean
	rm -f ~/Downloads/factorial
