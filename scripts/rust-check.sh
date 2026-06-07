#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf "Usage: %s <lint|test>\n" "$(basename "$0")" >&2
}

if [[ $# -ne 1 ]]; then
    usage
    exit 2
fi

MODE="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -z "${CARGO_HOME:-}" ]]; then
    CARGO_HOME="${REPO_ROOT}/.cache/cargo-home"
    export CARGO_HOME
fi

mkdir -p "${CARGO_HOME}"

CARGO_BIN="${RUST_CHECK_CARGO_BIN:-cargo}"
OFFLINE_ARGS=()
if [[ "${RUST_CHECK_OFFLINE:-0}" == "1" ]]; then
    OFFLINE_ARGS+=(--offline)
fi

TMP_OUTPUT="$(mktemp)"
trap 'rm -f "${TMP_OUTPUT}"' EXIT

run_cargo() {
    case "${MODE}" in
    lint)
        "${CARGO_BIN}" fmt --all -- --check \
            && "${CARGO_BIN}" clippy --all-targets "${OFFLINE_ARGS[@]}" -- -D warnings \
            && "${CARGO_BIN}" machete
        ;;
    test)
        if ! "${CARGO_BIN}" nextest --version >/dev/null 2>&1; then
            printf "cargo-nextest not found. Install with: cargo install cargo-nextest --locked\n" >&2
            return 1
        fi
        "${CARGO_BIN}" nextest run "${OFFLINE_ARGS[@]}"
        ;;
    *)
        usage
        return 2
        ;;
    esac
}

if run_cargo >"${TMP_OUTPUT}" 2>&1; then
    cat "${TMP_OUTPUT}"
    exit 0
else
    EXIT_CODE=$?
fi
OUTPUT_CONTENT="$(<"${TMP_OUTPUT}")"
printf "%s\n" "${OUTPUT_CONTENT}" >&2

if [[ "${OUTPUT_CONTENT}" =~ (Operation\ not\ permitted|Permission\ denied|Read-only\ file\ system|failed\ to\ create\ directory|failed\ to\ open|os\ error\ 13|os\ error\ 30|os\ error\ 1|SC_SEM_NSEMS_MAX|could\ not\ create\ home\ directory) ]]; then
    printf "Environment/setup failure: cargo could not access required local cache or filesystem paths.\n" >&2
    printf "Action: ensure CARGO_HOME points to a writable directory (current: %s).\n" "${CARGO_HOME}" >&2
    printf "Hint: export CARGO_HOME=\"%s/.cache/cargo-home\" before rerunning.\n" "${REPO_ROOT}" >&2
elif [[ "${OUTPUT_CONTENT}" =~ (failed\ to\ get|download\ of|failed\ to\ download|Could\ not\ resolve\ host|network\ failure|timed\ out|index.crates.io) ]]; then
    printf "Environment/setup failure: cargo dependency index or network access is unavailable.\n" >&2
    printf "Action: retry with cached dependencies and offline mode.\n" >&2
    printf "Hint: RUST_CHECK_OFFLINE=1 make %s\n" "${MODE}" >&2
else
    printf "Code failure: cargo %s reported lint/test errors.\n" "${MODE}" >&2
fi

exit "${EXIT_CODE}"
