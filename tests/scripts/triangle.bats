#!/usr/bin/env bats

# Failure modes of the triangle Python CLI's --svg PATH option (2026-11-17
# spec R14-R16), plus one success path per solution count as controls.

bats_require_minimum_version 1.5.0

setup() {
    load "../helpers/common.bash"
    PYTHON_CLI="${REPO_ROOT}/triangle/triangle.py"
    TMP_DIR=$(mktemp -d)
}

teardown() {
    rm -rf "${TMP_DIR}"
}

@test "python: --svg into a missing directory exits 1 before any prompt or file" {
    run --separate-stderr bash -c \
        "cd '${TMP_DIR}' && python3 '${PYTHON_CLI}' -a 3 -b 4 -c 5 --no-draw --svg nope/t.svg </dev/null"
    [ "${status}" -eq 1 ]
    [ "${output}" = "" ]
    [ "${stderr}" = "Error: cannot write SVG 'nope/t.svg': directory 'nope' does not exist" ]
    [ -z "$(ls -A "${TMP_DIR}")" ]
}

@test "python: --svg naming a directory exits 1 and writes nothing" {
    mkdir "${TMP_DIR}/d"
    run --separate-stderr bash -c \
        "cd '${TMP_DIR}' && python3 '${PYTHON_CLI}' -a 3 -b 4 -c 5 --no-draw --svg d </dev/null"
    [ "${status}" -eq 1 ]
    [ "${stderr}" = "Error: cannot write SVG 'd': it is a directory" ]
    [ "$(ls -A "${TMP_DIR}")" = "d" ]
}

@test "python: a suffixed SSA name that is a directory exits 1 before any output" {
    mkdir "${TMP_DIR}/t-2.svg"
    run --separate-stderr bash -c \
        "cd '${TMP_DIR}' && python3 '${PYTHON_CLI}' -a 6 -b 8 -A 30 --no-draw --svg t.svg </dev/null"
    [ "${status}" -eq 1 ]
    [ "${output}" = "" ]
    [ "${stderr}" = "Error: cannot write SVG 't-2.svg': it is a directory" ]
    [ ! -e "${TMP_DIR}/t-1.svg" ]
}

@test "python: one solution writes PATH itself" {
    run --separate-stderr bash -c \
        "cd '${TMP_DIR}' && python3 '${PYTHON_CLI}' -a 3 -b 4 -c 5 --no-draw --svg t.svg </dev/null"
    [ "${status}" -eq 0 ]
    [ "${lines[-1]}" = "Saved SVG to t.svg" ]
    [ "$(grep -c '<polygon ' "${TMP_DIR}/t.svg")" -eq 1 ]
}

@test "python: two SSA solutions write t-1.svg and t-2.svg" {
    run --separate-stderr bash -c \
        "cd '${TMP_DIR}' && python3 '${PYTHON_CLI}' -a 6 -b 8 -A 30 --no-draw --svg t.svg </dev/null"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"Saved SVG to t-1.svg"* ]]
    [ "${lines[-1]}" = "Saved SVG to t-2.svg" ]
    [ -s "${TMP_DIR}/t-1.svg" ]
    [ -s "${TMP_DIR}/t-2.svg" ]
    [ ! -e "${TMP_DIR}/t.svg" ]
}
