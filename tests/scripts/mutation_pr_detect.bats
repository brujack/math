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
    ALL10="amicable collatz descartes e factorial fib perfect-numbers pi sq triangle"
}

@test "template path selects all ten" {
    export MOCK_GIT_DIFF_NAMES="scripts/crate_templates/python/Makefile"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=${ALL10}" ]
    [ "${lines[1]}" = "has_py=true" ]
}

@test "a py workflow selects all ten" {
    export MOCK_GIT_DIFF_NAMES=".github/workflows/fib-py.yml"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=${ALL10}" ]
    [ "${lines[1]}" = "has_py=true" ]
}

@test "a python install_deps.sh selects all ten" {
    export MOCK_GIT_DIFF_NAMES="pi/install_deps.sh"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=${ALL10}" ]
    [ "${lines[1]}" = "has_py=true" ]
}

@test "mutation-pr.yml selects all ten" {
    export MOCK_GIT_DIFF_NAMES=".github/workflows/mutation-pr.yml"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[0]}" = "py_dirs=${ALL10}" ]
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
    grep -q 'diff --name-only --no-renames origin/main...HEAD' "${MOCK_CALLS_FILE}"
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
    [ "${#lines[@]}" -eq 8 ]
    [ "${lines[7]}" = "py_test_dirs=" ]
}

@test "rust nested source selects its crate" {
    rs_setup
    export MOCK_GIT_DIFF_NAMES="pi/pi-rs/src/a/b.rs"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[2]}" = "rs_dirs=pi/pi-rs" ]
    [ "${lines[3]}" = "has_rs=true" ]
}

@test "rust paths outside src, tests, .cargo, build.rs and Cargo.toml select nothing" {
    rs_setup
    local p
    for p in fib/fib-rs/README.md fib/fib-rs/benches/b.rs fib/fib-rs/src.rs fib/fib-rs/Cargo.lock; do
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

@test "mutation-rs-plan.sh sets rs_canary true" {
    rs_setup
    export MOCK_GIT_DIFF_NAMES="scripts/mutation-rs-plan.sh"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[4]}" = "rs_canary=true" ]
}

@test "mutation-exit-code.sh sets rs_canary true" {
    rs_setup
    export MOCK_GIT_DIFF_NAMES="scripts/mutation-exit-code.sh"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[4]}" = "rs_canary=true" ]
}

@test "mutation-shard-count.sh sets rs_canary true" {
    rs_setup
    export MOCK_GIT_DIFF_NAMES="scripts/mutation-shard-count.sh"
    run -0 bash "${SCRIPT}" origin/master
    [ "${lines[4]}" = "rs_canary=true" ]
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
    for d in amicable collatz descartes e factorial fib perfect-numbers pi sq triangle; do
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

@test "a binary file named like the descartes module is not selected" {
    fixture_repo
    printf '\000\001\002' > "${FIX}/descartes/descartes.py"
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

@test "each weakening path sets py_canary true" {
    local p
    for p in scripts/mutation_weakening.py scripts/mutation_base_runner.py scripts/mutation_hypothesis_profile.py scripts/mutation-whole-module-diff.sh tests/test_mutation_weakening_canary.py; do
        export MOCK_GIT_DIFF_NAMES="${p}"
        run -0 bash "${SCRIPT}" origin/master
        [ "${lines[6]}" = "py_canary=true" ]
    done
}
@test "any file under the weakening fixtures sets py_canary true" {
    local p
    for p in tests/fixtures/mutation_weakening/a/sq.py tests/fixtures/mutation_weakening/pair1/test_sq.py; do
        export MOCK_GIT_DIFF_NAMES="${p}"
        run -0 bash "${SCRIPT}" origin/master
        [ "${lines[6]}" = "py_canary=true" ]
    done
}
@test "a path that only resembles a weakening path leaves py_canary false" {
    local p
    for p in tests/fixtures/mutation_weakening_other/x.py scripts/mutation_weakening.pyc; do
        export MOCK_GIT_DIFF_NAMES="${p}"
        run -0 bash "${SCRIPT}" origin/master
        [ "${lines[6]}" = "py_canary=false" ]
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

# DETECT_SCRIPT lets a mutation probe point these two tests at an altered copy of the script.
_detect_readonly() {
    sed -n "s/^readonly $1=\"\\(.*\\)\"\$/\\1/p" "${DETECT_SCRIPT:-${SCRIPT}}"
}

@test "every PY_CANARY_PATHS entry is a tracked file and there are ten" {
    PATH="${PATH#"${REPO_ROOT}/tests/mocks:"}"
    local paths p n=0
    paths="$(_detect_readonly PY_CANARY_PATHS)"
    [ -n "${paths}" ]
    for p in ${paths}; do
        n=$((n + 1))
        run git -C "${REPO_ROOT}" ls-files --error-unmatch -- "${p}"
        [ "${status}" -eq 0 ] || { printf 'untracked canary path: %s\n' "${p}" >&2; return 1; }
    done
    [ "${n}" -eq 10 ]
}

@test "PYTHON_DIRS is exactly the ten dirs with a tracked cosmic-ray.toml and module" {
    PATH="${PATH#"${REPO_ROOT}/tests/mocks:"}"
    local want got d
    want="$(git -C "${REPO_ROOT}" ls-files '*/cosmic-ray.toml' | grep -v '.*/.*/' | sed 's|/cosmic-ray.toml$||' | sort | paste -sd' ' -)"
    got="$(_detect_readonly PYTHON_DIRS)"
    [ "$(printf '%s\n' ${got} | wc -l)" -eq 10 ]
    [ -n "${want}" ]
    [ "${got}" = "${want}" ]
    for d in ${got}; do
        run git -C "${REPO_ROOT}" ls-files --error-unmatch -- "${d}/${d//-/_}.py"
        [ "${status}" -eq 0 ] || { printf 'no module for dir: %s\n' "${d}" >&2; return 1; }
    done
}

# R1: whole-crate trigger. Each helper builds a real-git fixture holding the fib crate.
rs_cargo_toml() {
    printf '[package]\nname = "fib"\nversion = "%s"\nedition = "2024"\n\n[dependencies]\nrug = "%s"\n\n[dev-dependencies]\nproptest = "1.0"\n%s' "$1" "$2" "${3:-}"
}

rs_fixture_repo() {
    FIX="${BATS_TEST_TMPDIR}/fixture"
    mkdir -p "${FIX}/fib/fib-rs/src"
    mkdir -p "${FIX}/fib/fib-rs/tests"
    if [[ -n "${RS_BASE_TOML:-}" ]]; then
        printf '%s\n' "${RS_BASE_TOML}" > "${FIX}/fib/fib-rs/Cargo.toml"
    else
        rs_cargo_toml 0.1.0 1.0 > "${FIX}/fib/fib-rs/Cargo.toml"
    fi
    printf 'fn main() {}\n' > "${FIX}/fib/fib-rs/src/main.rs"
    printf 'fn t() {}\n' > "${FIX}/fib/fib-rs/tests/cli.rs"
    fixture_repo
}

# Args: path (relative to the fixture) and its new content.
rs_change() {
    rs_fixture_repo
    mkdir -p "$(dirname "${FIX}/$1")"
    printf '%s\n' "$2" > "${FIX}/$1"
    fix_commit "change"
    fix_run
}

@test "a crate tests/ fixture of any extension selects the crate" {
    rs_change fib/fib-rs/tests/data/input.txt $'1 2 3\n'
    [ "${lines[2]}" = "rs_dirs=fib/fib-rs" ]
    [ "${lines[3]}" = "has_rs=true" ]
}

@test "a non-rs src file selects the crate" {
    rs_change fib/fib-rs/src/table.txt $'x\n'
    [ "${lines[2]}" = "rs_dirs=fib/fib-rs" ]
}

@test "a .cargo/mutants.toml change selects the crate" {
    rs_change fib/fib-rs/.cargo/mutants.toml $'exclude_re = []\n'
    [ "${lines[2]}" = "rs_dirs=fib/fib-rs" ]
}

@test "build.rs selects the crate" {
    rs_change fib/fib-rs/build.rs $'fn main() {}\n'
    [ "${lines[2]}" = "rs_dirs=fib/fib-rs" ]
}

@test "a build.rs in another directory of the crate does not select it" {
    rs_change fib/fib-rs/other/build.rs $'fn main() {}\n'
    [ "${lines[2]}" = "rs_dirs=" ]
}

@test "a Cargo.toml [[test]] addition selects the crate" {
    rs_change fib/fib-rs/Cargo.toml "$(rs_cargo_toml 0.1.0 1.0 $'\n[[test]]\nname = "x"\n')"
    [ "${lines[2]}" = "rs_dirs=fib/fib-rs" ]
}

@test "a Cargo.toml [package] edition change selects the crate" {
    rs_change fib/fib-rs/Cargo.toml "$(rs_cargo_toml 0.1.0 1.0 | sed 's/2024/2021/')"
    [ "${lines[2]}" = "rs_dirs=fib/fib-rs" ]
}

@test "a Cargo.toml [dependencies] version change alone does not select the crate" {
    rs_change fib/fib-rs/Cargo.toml "$(rs_cargo_toml 0.1.0 1.1)"
    [ "${lines[2]}" = "rs_dirs=" ]
    [ "${lines[3]}" = "has_rs=false" ]
}

@test "a Cargo.toml [dev-dependencies] change alone does not select the crate" {
    rs_change fib/fib-rs/Cargo.toml "$(rs_cargo_toml 0.1.0 1.0 | sed 's/proptest = "1.0"/proptest = "1.1"/')"
    [ "${lines[2]}" = "rs_dirs=" ]
}

@test "a Cargo.toml [package] version change alone does not select the crate" {
    rs_change fib/fib-rs/Cargo.toml "$(rs_cargo_toml 0.2.0 1.0)"
    [ "${lines[2]}" = "rs_dirs=" ]
}

@test "a Cargo.toml dependency removal alone does not select the crate" {
    rs_change fib/fib-rs/Cargo.toml $'[package]\nname = "fib"\nversion = "0.1.0"\nedition = "2024"\n\n[dependencies]\n\n[dev-dependencies]\nproptest = "1.0"\n'
    [ "${lines[2]}" = "rs_dirs=" ]
}

@test "a Cargo.toml version bump plus a [[test]] addition selects the crate" {
    rs_change fib/fib-rs/Cargo.toml "$(rs_cargo_toml 0.2.0 1.0 $'\n[[test]]\nname = "x"\n')"
    [ "${lines[2]}" = "rs_dirs=fib/fib-rs" ]
}

@test "a Cargo.toml diff failure exits non-zero" {
    rs_fixture_repo
    printf '%s' "$(rs_cargo_toml 0.1.0 1.1)" > "${FIX}/fib/fib-rs/Cargo.toml"
    fix_commit "dep"
    local shim="${BATS_TEST_TMPDIR}/shim"
    mkdir -p "${shim}"
    local real
    real="$(command -v git)"
    printf '#!/usr/bin/env bash\ncase "$*" in *-U1000000*) exit 1 ;; esac\nexec "%s" "$@"\n' "${real}" > "${shim}/git"
    chmod +x "${shim}/git"
    export PATH="${shim}:${PATH}"
    cd "${FIX}" || return 1
    run ! bash "${SCRIPT}" main
    [ -z "${output}" ]
}

@test "a table header removed in the same hunk does not mis-attribute an added line" {
    RS_BASE_TOML=$'[lib]\npath = "src/lib.rs"\n[dev-dependencies]\nproptest = "1"'
    rs_change fib/fib-rs/Cargo.toml $'[lib]\npath = "src/lib.rs"\ntest = false'
    [ "${lines[2]}" = "rs_dirs=fib/fib-rs" ]
}

@test "a renamed-away tests/ file selects the crate" {
    rs_fixture_repo
    mkdir -p "${FIX}/attic"
    git -C "${FIX}" mv fib/fib-rs/tests/cli.rs attic/cli.rs
    fix_commit "rename"
    fix_run
    [ "${lines[2]}" = "rs_dirs=fib/fib-rs" ]
}

@test "an indented table header is recognised" {
    rs_change fib/fib-rs/Cargo.toml "$(rs_cargo_toml 0.1.0 1.0 $'  [lints.rust]\n  unsafe_code = "forbid"')"
    [ "${lines[2]}" = "rs_dirs=fib/fib-rs" ]
}

@test "a target-specific dependencies bump selects the crate" {
    RS_BASE_TOML="$(rs_cargo_toml 0.1.0 1.0 $'\n[target.\'cfg(unix)\'.dependencies]\nlibc = "0.1"')"
    rs_change fib/fib-rs/Cargo.toml "$(rs_cargo_toml 0.1.0 1.0 $'\n[target.\'cfg(unix)\'.dependencies]\nlibc = "0.2"')"
    [ "${lines[2]}" = "rs_dirs=fib/fib-rs" ]
}

@test "a [dependencies.name] version bump alone does not select the crate" {
    RS_BASE_TOML=$'[package]\nname = "fib"\nversion = "0.1.0"\n\n[dependencies.rug]\nversion = "1.0"'
    rs_change fib/fib-rs/Cargo.toml $'[package]\nname = "fib"\nversion = "0.1.0"\n\n[dependencies.rug]\nversion = "1.1"'
    [ "${lines[2]}" = "rs_dirs=" ]
}

@test "a commented [lints.rust] header with a change under it selects the crate" {
    rs_change fib/fib-rs/Cargo.toml "$(rs_cargo_toml 0.1.0 1.0 $'\n[lints.rust] # c\nunsafe_code = "forbid"')"
    [ "${lines[2]}" = "rs_dirs=fib/fib-rs" ]
}

# R5: py_test_dirs, line 7 of the output.
@test "an added test line selects py_test_dirs" {
    fixture_repo
    printf 'def test_y():\n    pass\n' >> "${FIX}/fib/test_fib.py"
    fix_commit "add"
    fix_run
    [ "${lines[7]}" = "py_test_dirs=fib" ]
}

@test "a deleted-only test line selects py_test_dirs" {
    fixture_repo
    printf 'def test_x():\n' > "${FIX}/fib/test_fib.py"
    fix_commit "del"
    git -C "${FIX}" show --numstat --format= HEAD | grep -q '^0'
    fix_run
    [ "${lines[7]}" = "py_test_dirs=fib" ]
}

@test "a deleted test file selects py_test_dirs" {
    fixture_repo
    git -C "${FIX}" rm -q fib/test_fib.py
    fix_commit "rm"
    fix_run
    [ "${lines[7]}" = "py_test_dirs=fib" ]
}

@test "a cosmic-ray.toml change selects py_test_dirs" {
    fixture_repo
    printf 'k = 1\n' > "${FIX}/sq/cosmic-ray.toml"
    fix_commit "cr"
    fix_run
    [ "${lines[7]}" = "py_test_dirs=sq" ]
}

@test "a mutants-equivalent.toml change selects py_test_dirs" {
    fixture_repo
    printf 'k = 1\n' > "${FIX}/pi/mutants-equivalent.toml"
    fix_commit "eq"
    fix_run
    [ "${lines[7]}" = "py_test_dirs=pi" ]
}

@test "a module change alone does not select py_test_dirs" {
    fixture_repo
    printf 'd = 4\n' >> "${FIX}/fib/fib.py"
    fix_commit "mod"
    fix_run
    [ "${lines[5]}" = "py_src_dirs=fib" ]
    [ "${lines[7]}" = "py_test_dirs=" ]
}

@test "a mode-only test file change does not select py_test_dirs" {
    fixture_repo
    chmod +x "${FIX}/fib/test_fib.py"
    fix_commit "mode"
    fix_run
    [ "${lines[7]}" = "py_test_dirs=" ]
}

@test "py_test_dirs is sorted and unique across dirs" {
    fixture_repo
    printf 'x = 1\n' >> "${FIX}/sq/test_sq.py"
    printf 'x = 1\n' >> "${FIX}/fib/test_fib.py"
    printf 'k = 1\n' > "${FIX}/fib/cosmic-ray.toml"
    fix_commit "many"
    fix_run
    [ "${lines[7]}" = "py_test_dirs=fib sq" ]
}

@test "a test file of another directory does not select a dir" {
    fixture_repo
    mkdir -p "${FIX}/fib/fib-rs"
    printf 'x = 1\n' > "${FIX}/fib/fib-rs/test_fib.py"
    fix_commit "nested"
    fix_run
    [ "${lines[7]}" = "py_test_dirs=" ]
}
