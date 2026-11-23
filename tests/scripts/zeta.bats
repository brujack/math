#!/usr/bin/env bats

# Input-error failure modes of the zeta Rust CLI (spec R1, R13). The crate is not
# built by scripts.yml, so each test skips when no binary is present.

bats_require_minimum_version 1.5.0

setup() {
    load "../helpers/common.bash"
    RUST_BIN="${REPO_ROOT}/zeta/zeta-rs/target/release/zeta"
    if [[ ! -x "${RUST_BIN}" ]]; then
        RUST_BIN="${REPO_ROOT}/zeta/zeta-rs/target/debug/zeta"
    fi
    [[ -x "${RUST_BIN}" ]] || skip "zeta binary not built"
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
    for n in 1 8; do
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
}

@test "a valid N is never reported as verified" {
    run --separate-stderr bash -c "cd '${WORK_DIR}' && '${RUST_BIN}' 2 </dev/null"
    [ "${status}" -eq 3 ]
    [[ "${output}" == "RH NOT verified up to 100: zero isolation is not implemented yet" ]]
    [[ "${output}${stderr}" != *"RH verified"* ]]
    [[ "${output}${stderr}" != *"RH holds"* ]]
}
