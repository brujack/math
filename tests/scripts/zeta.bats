#!/usr/bin/env bats

# Input-error failure modes of the zeta Rust CLI (spec R1, R13). scripts.yml builds
# no crate, so CI's gate for the CLI is zeta/zeta-rs/tests/cli.rs (as descartes.bats
# explains); these tests run only where `make test` in zeta-rs has built the debug
# binary, and skip when it is missing or older than any source file.

bats_require_minimum_version 1.5.0

setup() {
    load "../helpers/common.bash"
    RUST_BIN="${REPO_ROOT}/zeta/zeta-rs/target/debug/zeta"
    [[ -x "${RUST_BIN}" ]] || skip "zeta binary not built (run make test in zeta/zeta-rs)"
    local src
    for src in "${REPO_ROOT}"/zeta/zeta-rs/src/*.rs; do
        [[ "${RUST_BIN}" -nt "${src}" ]] || skip "zeta binary is older than ${src##*/}; rebuild"
    done
    WORK_DIR="${BATS_TEST_TMPDIR}/work"
    mkdir -p "${WORK_DIR}"
}

@test "missing N with closed stdin exits 1 naming the problem" {
    run --separate-stderr bash -c "cd '${WORK_DIR}' && '${RUST_BIN}' </dev/null"
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *"Error: no input; pass SIZE as an argument (e.g. zeta 3)."* ]]
    [ -z "$(ls -A "${WORK_DIR}")" ]
}

@test "N out of range exits 1 naming the range" {
    for n in 1 8 -1 -5; do
        run --separate-stderr bash -c "cd '${WORK_DIR}' && '${RUST_BIN}' ${n} </dev/null"
        [ "${status}" -eq 1 ]
        [[ "${stderr}" == *"Error: N must be between 2 and 7."* ]]
    done
    [ -z "$(ls -A "${WORK_DIR}")" ]
}

@test "non-integer N exits 1 naming the range" {
    run --separate-stderr bash -c "cd '${WORK_DIR}' && '${RUST_BIN}' abc </dev/null"
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *"Error: N must be between 2 and 7."* ]]
    [ -z "$(ls -A "${WORK_DIR}")" ]
}

@test "N = 2 verifies 29 zeros, saves the table and leaves no temporary file" {
    run --separate-stderr bash -c "cd '${WORK_DIR}' && '${RUST_BIN}' 2 </dev/null"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"RH verified: all 29 nontrivial zeros with 0 < Im s <= 100 lie on Re s = 1/2 and are simple"* ]]
    [[ "${output}${stderr}" != *"RH holds"* ]]
    [[ "${output}" != *"progress:"* ]]
    # The production throttle (2 s, 1%) lets a quick run print only each stage's final line.
    [ "$(printf '%s\n' "${stderr}" | grep -c '^progress:')" -eq 2 ]
    local re='^progress: ([0-9]+)/([0-9]+) Gram (points|blocks), t = [0-9.]+$'
    local kind line
    for kind in points blocks; do
        line="$(printf '%s\n' "${stderr}" | grep "^progress: .* Gram ${kind}, ")"
        [ "$(printf '%s\n' "${line}" | wc -l)" -eq 1 ]
        [[ "${line}" =~ ${re} ]]
        [ "${BASH_REMATCH[1]}" = "${BASH_REMATCH[2]}" ]
    done
    [ "$(ls -A "${WORK_DIR}")" = "zeta_1e2.txt" ]
    [ "$(head -n 1 "${WORK_DIR}/zeta_1e2.txt")" = "# n a b" ]
    [ "$(grep -vc '^#' "${WORK_DIR}/zeta_1e2.txt")" -eq 29 ]
}

@test "a stale temporary file that cannot be removed exits 4 without a verified claim" {
    mkdir "${WORK_DIR}/zeta_1e2.tmp.txt"
    run --separate-stderr bash -c "cd '${WORK_DIR}' && '${RUST_BIN}' 2 </dev/null"
    [ "${status}" -eq 4 ]
    [[ "${output}${stderr}" != *"RH verified"* ]]
    [ ! -e "${WORK_DIR}/zeta_1e2.txt" ]
}

@test "N = 2 --refine writes the refined table and prints the spacing report" {
    run --separate-stderr bash -c "cd '${WORK_DIR}' && '${RUST_BIN}' 2 --refine </dev/null"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"KS distance to the Wigner surmise CDF:"* ]]
    [ "$(head -n 1 "${WORK_DIR}/zeta_1e2.txt")" = "# n a b t_n w_n" ]
    [ "$(ls -A "${WORK_DIR}")" = "zeta_1e2.txt" ]
}
