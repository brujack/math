.PHONY: prime lint test clean mutants

prime:
	cargo build --release
	cp target/release/prime ~/Downloads/prime

lint:
	../../scripts/rust-check.sh lint

test: lint
	../../scripts/rust-check.sh test

mutants:
	cargo mutants --timeout 120 --no-shuffle

clean:
	cargo clean
	rm -f ~/Downloads/prime
