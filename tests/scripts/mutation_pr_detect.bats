#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/calls"
    SCRIPT="${REPO_ROOT}/scripts/mutation-pr-detect.sh"
    ALL9="amicable collatz e factorial fib perfect-numbers pi sq triangle"
}

@test "template path selects all nine" {
    export MOCK_GIT_DIFF_NAMES="scripts/crate_templates/python/Makefile"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=${ALL9}" ]
    [ "${lines[1]}" = "has_py=true" ]
}

@test "a py workflow selects all nine" {
    export MOCK_GIT_DIFF_NAMES=".github/workflows/fib-py.yml"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=${ALL9}" ]
    [ "${lines[1]}" = "has_py=true" ]
}

@test "a python install_deps.sh selects all nine" {
    export MOCK_GIT_DIFF_NAMES="pi/install_deps.sh"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=${ALL9}" ]
    [ "${lines[1]}" = "has_py=true" ]
}

@test "mutation-pr.yml selects all nine" {
    export MOCK_GIT_DIFF_NAMES=".github/workflows/mutation-pr.yml"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=${ALL9}" ]
    [ "${lines[1]}" = "has_py=true" ]
}

@test "a single python source selects its directory" {
    export MOCK_GIT_DIFF_NAMES="fib/fib.py"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=fib" ]
    [ "${lines[1]}" = "has_py=true" ]
}

@test "multiple sources are sorted and unique" {
    export MOCK_GIT_DIFF_NAMES=$'sq/sq.py\nfib/test_fib.py\nfib/fib.py'
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=fib sq" ]
    [ "${lines[1]}" = "has_py=true" ]
}

@test "rust-only change is not python" {
    export MOCK_GIT_DIFF_NAMES="fib/fib-rs/src/main.rs"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=" ]
    [ "${lines[1]}" = "has_py=false" ]
}

@test "nested rust install_deps.sh is not python" {
    export MOCK_GIT_DIFF_NAMES="fib/fib-rs/install_deps.sh"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=" ]
    [ "${lines[1]}" = "has_py=false" ]
}

@test "docs-only change is not python" {
    export MOCK_GIT_DIFF_NAMES="README.md"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=" ]
    [ "${lines[1]}" = "has_py=false" ]
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

rs_setup() {
    export MOCK_GIT_LS_FILES=$'fib/fib-rs/Cargo.toml\npi/pi-rs/Cargo.toml\namicable/amicable-rs/Cargo.toml'
}

@test "rust lib.rs selects its crate" {
    rs_setup
    export MOCK_GIT_DIFF_NAMES="fib/fib-rs/src/lib.rs"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[2]}" = "rs_dirs=fib/fib-rs" ]
    [ "${lines[3]}" = "has_rs=true" ]
    [ "${lines[4]}" = "rs_canary=false" ]
    [ "${#lines[@]}" -eq 5 ]
}

@test "rust nested source selects its crate" {
    rs_setup
    export MOCK_GIT_DIFF_NAMES="pi/pi-rs/src/a/b.rs"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[2]}" = "rs_dirs=pi/pi-rs" ]
    [ "${lines[3]}" = "has_rs=true" ]
}

@test "non-source rust paths select nothing" {
    rs_setup
    local p
    for p in fib/fib-rs/Cargo.toml fib/fib-rs/.cargo/mutants.toml fib/fib-rs/tests/cli.rs fib/fib-rs/src/notes.txt; do
        export MOCK_GIT_DIFF_NAMES="${p}"
        run -0 bash "${SCRIPT}" origin/master
        [ "${lines[2]}" = "rs_dirs=" ]
        [ "${lines[3]}" = "has_rs=false" ]
    done
}

@test "two crates are sorted and space-joined" {
    rs_setup
    export MOCK_GIT_DIFF_NAMES=$'pi/pi-rs/src/main.rs\nfib/fib-rs/src/lib.rs\npi/pi-rs/src/x.rs'
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[2]}" = "rs_dirs=fib/fib-rs pi/pi-rs" ]
    [ "${lines[3]}" = "has_rs=true" ]
}

@test "no rust change gives empty rs_dirs and has_rs false" {
    rs_setup
    export MOCK_GIT_DIFF_NAMES="README.md"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[2]}" = "rs_dirs=" ]
    [ "${lines[3]}" = "has_rs=false" ]
}

@test "has_rs true never pairs with empty rs_dirs" {
    rs_setup
    local p
    for p in README.md fib/fib-rs/src/lib.rs fib/fib-rs/Cargo.toml fib/fib.py scripts/crate_templates/python/Makefile; do
        export MOCK_GIT_DIFF_NAMES="${p}"
        run -0 bash "${SCRIPT}" origin/master
        if [ "${lines[3]}" = "has_rs=true" ]; then
            [ "${lines[2]}" != "rs_dirs=" ]
        fi
    done
}

@test "select-all python branch still prints the rust lines" {
    rs_setup
    export MOCK_GIT_DIFF_NAMES=$'.github/workflows/fib-py.yml\npi/pi-rs/src/lib.rs'
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[1]}" = "has_py=true" ]
    [ "${lines[2]}" = "rs_dirs=pi/pi-rs" ]
    [ "${lines[3]}" = "has_rs=true" ]
}

@test "each canary path sets rs_canary true" {
    rs_setup
    local p
    for p in .github/workflows/mutation-pr.yml scripts/mutation-pr-detect.sh scripts/mutation-pr-diff.sh scripts/mutation-pr-run.sh scripts/mutation-classify.sh scripts/crate_templates/Makefile amicable/amicable-rs/src/lib.rs; do
        export MOCK_GIT_DIFF_NAMES="${p}"
        run -0 bash "${SCRIPT}" origin/master
        [ "${lines[4]}" = "rs_canary=true" ]
    done
}

@test "non-canary path sets rs_canary false" {
    rs_setup
    export MOCK_GIT_DIFF_NAMES="README.md"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[4]}" = "rs_canary=false" ]
}

@test "ls-files failure exits non-zero" {
    export MOCK_GIT_DIFF_NAMES="README.md"
    export MOCK_GIT_LS_FILES_EXIT=1
    run ! bash "${SCRIPT}" origin/master
}

@test "ls-files uses the crate manifest pattern" {
    rs_setup
    export MOCK_GIT_DIFF_NAMES="README.md"
    run -0 bash "${SCRIPT}" origin/master
    grep -qF "ls-files */*-rs/Cargo.toml" "${MOCK_CALLS_FILE}"
}

@test "only listed crates under src/ are selected" {
    export MOCK_GIT_LS_FILES=$'pi/pi-rs/Cargo.toml\nfib/fib-rs/Cargo.toml'
    export MOCK_GIT_DIFF_NAMES=$'pi/pi-rs/src.rs\npi/pi-rs/srcx/a.rs\nx/x-rs/src/a.rs'
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[2]}" = "rs_dirs=" ]
    [ "${lines[3]}" = "has_rs=false" ]
}
