.PHONY: amicable lint test bench mutants clean

amicable:
	cargo build --release

lint:
	../../scripts/rust-check.sh lint

test:
	../../scripts/rust-check.sh test

bench:
	cargo bench

mutants:
	cargo mutants --timeout 120 --no-shuffle

clean:
	cargo clean
	rm -f amicable_1e*.txt
