#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/calls"
    SCRIPT="${REPO_ROOT}/scripts/mutation-pr-detect.sh"
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    export HOME="${BATS_TEST_TMPDIR}"
    export XDG_CONFIG_HOME="${BATS_TEST_TMPDIR}/xdg"
    export GIT_CONFIG_GLOBAL=/dev/null
    export GIT_CONFIG_NOSYSTEM=1
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
    [ "${#lines[@]}" -eq 7 ]
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

# Real-git fixture: numstat needs genuine diffs, which the git mock cannot produce.
# setup() isolates the environment; the mock dir is dropped from PATH here so `git`
# is the real binary.
fixture_repo() {
    PATH="${PATH#"${REPO_ROOT}/tests/mocks:"}"
    FIX="${BATS_TEST_TMPDIR}/fixture"
    mkdir -p "${FIX}"
    git -C "${FIX}" init -q -b main
    local d m
    for d in amicable collatz e factorial fib perfect-numbers pi sq triangle; do
        m="${d//-/_}"
        mkdir -p "${FIX}/${d}"
        printf 'a = 1\nb = 2\nc = 3\n' > "${FIX}/${d}/${m}.py"
        printf 'def test_x():\n    pass\n' > "${FIX}/${d}/test_${m}.py"
    done
    fix_commit "base"
    git -C "${FIX}" checkout -q -b feature
}

fix_commit() {
    git -C "${FIX}" add -A
    git -C "${FIX}" -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -q -m "$1"
}

fix_run() {
    cd "${FIX}" || return 1
    run -0 bash "${SCRIPT}" main
}

@test "added lines in a module select py_src_dirs" {
    fixture_repo
    printf 'd = 4\n' >> "${FIX}/fib/fib.py"
    fix_commit "add"
    fix_run
    [ "${lines[0]}" = "py_dirs=fib" ]
    [ "${lines[1]}" = "has_py=true" ]
    [ "${lines[5]}" = "py_src_dirs=fib" ]
    [ "${lines[6]}" = "py_canary=false" ]
}

@test "py_src_dirs is sorted and unique across modules" {
    fixture_repo
    printf 'd = 4\n' >> "${FIX}/sq/sq.py"
    printf 'd = 4\ne = 5\n' >> "${FIX}/fib/fib.py"
    printf 'd = 4\n' >> "${FIX}/e/e.py"
    fix_commit "add"
    fix_run
    [ "${lines[5]}" = "py_src_dirs=e fib sq" ]
}

@test "perfect-numbers selects through perfect_numbers.py" {
    fixture_repo
    printf 'd = 4\n' >> "${FIX}/perfect-numbers/perfect_numbers.py"
    fix_commit "add"
    fix_run
    [ "${lines[5]}" = "py_src_dirs=perfect-numbers" ]
}

@test "a deletion-only module diff selects nothing but keeps py_dirs" {
    fixture_repo
    printf 'a = 1\nb = 2\n' > "${FIX}/fib/fib.py"
    fix_commit "delete a line"
    fix_run
    [ "${lines[0]}" = "py_dirs=fib" ]
    [ "${lines[1]}" = "has_py=true" ]
    [ "${lines[5]}" = "py_src_dirs=" ]
}

@test "a mode-only module change selects nothing" {
    fixture_repo
    chmod +x "${FIX}/pi/pi.py"
    fix_commit "mode"
    fix_run
    [ "${lines[5]}" = "py_src_dirs=" ]
}

@test "a rename onto a module with an added line selects its dir" {
    fixture_repo
    git -C "${FIX}" mv sq/sq.py sq/old.py
    fix_commit "move away"
    git -C "${FIX}" checkout -q -b feature2
    git -C "${FIX}" mv sq/old.py sq/sq.py
    printf 'd = 4\n' >> "${FIX}/sq/sq.py"
    fix_commit "rename back with an added line"
    cd "${FIX}"
    run -0 bash "${SCRIPT}" feature
    [ "${lines[5]}" = "py_src_dirs=sq" ]
}

@test "a test-file change keeps py_dirs and leaves py_src_dirs empty" {
    fixture_repo
    printf 'def test_y():\n    pass\n' >> "${FIX}/fib/test_fib.py"
    fix_commit "test only"
    fix_run
    [ "${lines[0]}" = "py_dirs=fib" ]
    [ "${lines[1]}" = "has_py=true" ]
    [ "${lines[5]}" = "py_src_dirs=" ]
}

@test "a binary file named like a module is not selected" {
    fixture_repo
    printf '\000\001\002' > "${FIX}/triangle/triangle.py"
    fix_commit "binary"
    git -C "${FIX}" show --numstat --format= HEAD | grep -q '^-'
    fix_run
    [ "${lines[5]}" = "py_src_dirs=" ]
}

@test "a diff failure exits non-zero" {
    export MOCK_GIT_DIFF_NAMES="README.md"
    export MOCK_GIT_EXIT_DIFF=1
    run ! bash "${SCRIPT}" origin/master
}

@test "each python canary path sets py_canary true" {
    local p
    for p in .github/workflows/mutation-pr.yml scripts/mutation-pr-detect.sh scripts/mutation-pr-diff.sh scripts/mutation-pr-plan-python.sh scripts/mutation-pr-verdict-python.sh scripts/cosmic_ray_prune.py scripts/cosmic_ray_cell_status.py scripts/crate_templates/python/Makefile sq/sq.py sq/mutants-equivalent.toml; do
        export MOCK_GIT_DIFF_NAMES="${p}"
        run -0 bash "${SCRIPT}" origin/master
        [ "${lines[6]}" = "py_canary=true" ]
    done
}

@test "an unrelated path leaves py_canary false" {
    export MOCK_GIT_DIFF_NAMES="README.md"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[6]}" = "py_canary=false" ]
}

@test "a non-canary module does not set py_canary" {
    export MOCK_GIT_DIFF_NAMES="fib/fib.py"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[6]}" = "py_canary=false" ]
}

@test "a numstat-only failure exits non-zero" {
    local shim="${BATS_TEST_TMPDIR}/shim"
    mkdir -p "${shim}"
    printf '#!/usr/bin/env bash\ncase "$*" in *--numstat*) exit 1 ;; esac\nexec "%s/tests/mocks/git" "$@"\n' "${REPO_ROOT}" > "${shim}/git"
    chmod +x "${shim}/git"
    export PATH="${shim}:${PATH}"
    export MOCK_GIT_DIFF_NAMES="fib/fib.py"
    run ! bash "${SCRIPT}" origin/master
}

@test "an exported GIT_DIR does not redirect the diff scope" {
    fixture_repo
    printf 'd = 4\n' >> "${FIX}/fib/fib.py"
    fix_commit "add"
    local other="${BATS_TEST_TMPDIR}/other"
    mkdir -p "${other}/sq"
    git -C "${other}" init -q -b main
    printf 'a = 1\n' > "${other}/sq/sq.py"
    git -C "${other}" add -A
    git -C "${other}" -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -q -m base
    git -C "${other}" checkout -q -b feature
    printf 'b = 2\n' >> "${other}/sq/sq.py"
    git -C "${other}" add -A
    git -C "${other}" -c user.name=t -c user.email=t@t -c commit.gpgsign=false commit -q -m add
    export GIT_DIR="${other}/.git"
    fix_run
    [ "${lines[5]}" = "py_src_dirs=fib" ]
}
