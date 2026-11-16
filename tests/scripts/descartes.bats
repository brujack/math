#!/usr/bin/env bats

# Failure modes of the descartes Python CLI (spec R17). The Rust half lives in
# descartes-rs/tests/cli.rs (PR2), because scripts.yml runs BATS without
# building any crate.

bats_require_minimum_version 1.5.0

setup() {
    load "../helpers/common.bash"
    PYTHON_CLI="${REPO_ROOT}/descartes/descartes.py"
    TMP_DIR=$(mktemp -d)
}

teardown() {
    rm -rf "${TMP_DIR}"
}

@test "python: missing K with stdin not a terminal exits 2 naming the problem" {
    run --separate-stderr bash -c "cd '${TMP_DIR}' && python3 '${PYTHON_CLI}' </dev/null"
    [ "${status}" -eq 2 ]
    [[ "${stderr}" == *"error: K is required when stdin is not a terminal"* ]]
}

@test "python: K out of range exits 2 naming the range" {
    for k in 0 7; do
        run --separate-stderr bash -c "cd '${TMP_DIR}' && python3 '${PYTHON_CLI}' ${k} </dev/null"
        [ "${status}" -eq 2 ]
        [[ "${stderr}" == *"K must be between 1 and 6, got ${k}."* ]]
    done
}

@test "python: non-integer K exits 2" {
    run --separate-stderr bash -c "cd '${TMP_DIR}' && python3 '${PYTHON_CLI}' abc </dev/null"
    [ "${status}" -eq 2 ]
    [[ "${stderr}" == *"invalid int value: 'abc'"* ]]
}

@test "python: a root that is not a Descartes quadruple exits 1 naming it" {
    run --separate-stderr bash -c \
        "cd '${TMP_DIR}' && python3 '${PYTHON_CLI}' 2 --root -1 2 2 4 </dev/null"
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *"root (-1, 2, 2, 4) is not a Descartes quadruple"* ]]
    [ -z "$(ls -A "${TMP_DIR}")" ]
}

@test "python: non-tangent --solve exits 1 naming circles 1 and 3" {
    run --separate-stderr bash -c \
        "cd '${TMP_DIR}' && python3 '${PYTHON_CLI}' --solve -1,0,0 2,0.5,0 3,0,0.6667 </dev/null"
    [ "${status}" -eq 1 ]
    [[ "${stderr}" == *"circles 1 and 3 are not tangent"* ]]
    [[ "${stderr}" == *"full-precision"* ]]
}

@test "python: K=1 writes the three distinct curvatures" {
    run --separate-stderr bash -c \
        "cd '${TMP_DIR}' && python3 '${PYTHON_CLI}' 1 --no-draw </dev/null"
    [ "${status}" -eq 0 ]
    [ "${lines[0]}" = "root -1 2 2 3" ]
    [ "${lines[1]}" = "circles 8" ]
    [ "$(cat "${TMP_DIR}/descartes_1e1.txt")" = "$(printf '2\n3\n6')" ]
}
