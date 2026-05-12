#!/usr/bin/env bash
set -e

if ! command -v rustup &>/dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "${HOME}/.cargo/env"
fi
rustup update stable
cargo install cargo-tarpaulin --locked
