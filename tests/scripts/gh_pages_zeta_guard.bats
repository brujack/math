#!/usr/bin/env bats

setup() {
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    export HOME="${BATS_TEST_TMPDIR}/home"
    mkdir -p "${HOME}"
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    SCRIPT="${REPO_ROOT}/scripts/gh-pages-zeta-guard.sh"
    PAGES="${BATS_TEST_TMPDIR}/gh-pages"
    mkdir -p "${PAGES}/zeta" "${PAGES}/dev/bench"
    printf 'old\n' >"${PAGES}/zeta/index.html"
    printf 'bench\n' >"${PAGES}/dev/bench/x"
    git -C "${PAGES}" init -q
    git -C "${PAGES}" add -A
    git -C "${PAGES}" -c user.name=t -c user.email=t@example.com commit -q -m init
}

@test "a change under zeta/ exits 0" {
    printf 'new\n' >"${PAGES}/zeta/index.html"
    printf 'sha\n' >"${PAGES}/zeta/deployed-from.txt"
    run "${SCRIPT}" "${PAGES}"
    [ "${status}" -eq 0 ]
}

@test "a clean tree exits 0" {
    run "${SCRIPT}" "${PAGES}"
    [ "${status}" -eq 0 ]
}

@test "a change to dev/bench/x exits 1 and names the path" {
    printf 'changed\n' >"${PAGES}/dev/bench/x"
    run "${SCRIPT}" "${PAGES}"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"dev/bench/x"* ]]
}

@test "a deletion outside zeta/ exits 1" {
    rm "${PAGES}/dev/bench/x"
    run "${SCRIPT}" "${PAGES}"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"dev/bench/x"* ]]
}

@test "a new untracked file outside zeta/ exits 1" {
    printf 'x\n' >"${PAGES}/stray.txt"
    run "${SCRIPT}" "${PAGES}"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"stray.txt"* ]]
}

@test "a rename from zeta/ to outside exits 1" {
    git -C "${PAGES}" mv zeta/index.html moved.html
    run "${SCRIPT}" "${PAGES}"
    [ "${status}" -eq 1 ]
    [[ "${output}" == *"moved.html"* ]]
}

@test "a sibling directory sharing the zeta prefix exits 1" {
    mkdir -p "${PAGES}/zeta-other"
    printf 'x\n' >"${PAGES}/zeta-other/a"
    run "${SCRIPT}" "${PAGES}"
    [ "${status}" -eq 1 ]
}

@test "missing argument exits 2" {
    run "${SCRIPT}"
    [ "${status}" -eq 2 ]
}

@test "a directory that is not a repository exits 2" {
    mkdir -p "${BATS_TEST_TMPDIR}/plain"
    run "${SCRIPT}" "${BATS_TEST_TMPDIR}/plain"
    [ "${status}" -eq 2 ]
}
