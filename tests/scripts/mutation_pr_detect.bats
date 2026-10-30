#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/calls"
    SCRIPT="${REPO_ROOT}/scripts/mutation-pr-detect.sh"
    ALL8="amicable collatz e factorial fib perfect-numbers pi sq"
}

@test "template path selects all eight" {
    export MOCK_GIT_DIFF_NAMES="scripts/crate_templates/python/Makefile"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=${ALL8}" ]
    [ "${lines[1]}" = "has_py=true" ]
}

@test "a py workflow selects all eight" {
    export MOCK_GIT_DIFF_NAMES=".github/workflows/fib-py.yml"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=${ALL8}" ]
    [ "${lines[1]}" = "has_py=true" ]
}

@test "a python install_deps.sh selects all eight" {
    export MOCK_GIT_DIFF_NAMES="pi/install_deps.sh"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=${ALL8}" ]
    [ "${lines[1]}" = "has_py=true" ]
}

@test "mutation-pr.yml selects all eight" {
    export MOCK_GIT_DIFF_NAMES=".github/workflows/mutation-pr.yml"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=${ALL8}" ]
    [ "${lines[1]}" = "has_py=true" ]
}

@test "a single python source selects its directory" {
    export MOCK_GIT_DIFF_NAMES="fib/fib.py"
    run -0 bash "${SCRIPT}" origin/master
    [ "${output}" = $'py_dirs=fib\nhas_py=true' ]
}

@test "multiple sources are sorted and unique" {
    export MOCK_GIT_DIFF_NAMES=$'sq/sq.py\nfib/test_fib.py\nfib/fib.py'
    run -0 bash "${SCRIPT}" origin/master
    [ "${output}" = $'py_dirs=fib sq\nhas_py=true' ]
}

@test "rust-only change is not python" {
    export MOCK_GIT_DIFF_NAMES="fib/fib-rs/src/main.rs"
    run -0 bash "${SCRIPT}" origin/master
    [ "${output}" = $'py_dirs=\nhas_py=false' ]
}

@test "nested rust install_deps.sh is not python" {
    export MOCK_GIT_DIFF_NAMES="fib/fib-rs/install_deps.sh"
    run -0 bash "${SCRIPT}" origin/master
    [ "${output}" = $'py_dirs=\nhas_py=false' ]
}

@test "docs-only change is not python" {
    export MOCK_GIT_DIFF_NAMES="README.md"
    run -0 bash "${SCRIPT}" origin/master
    [ "${output}" = $'py_dirs=\nhas_py=false' ]
}

@test "git failure exits non-zero" {
    export MOCK_GIT_EXIT=1
    run ! bash "${SCRIPT}" origin/master
}

@test "diff uses the three-dot range" {
    export MOCK_GIT_DIFF_NAMES="README.md"
    run -0 bash "${SCRIPT}" origin/main
    grep -q 'diff --name-only origin/main...HEAD' "${MOCK_CALLS_FILE}"
}

@test "missing base ref exits 2" {
    run -2 bash "${SCRIPT}"
}
