#!/usr/bin/env bats

# A bare `! grep -q ...` only fails a bats test while it is the last command in
# the body (shellcheck SC2314); anywhere else the negation is silently ignored
# and the assertion cannot fail. Every negative assertion in this file goes
# through here instead, which also names what it found on failure.
assert_no_match() {
    if grep -q "$1" "${MOCK_CALLS_FILE}" 2>/dev/null; then
        printf 'expected no match for %s, but calls were:\n%s\n' \
            "$1" "$(cat "${MOCK_CALLS_FILE}")" >&2
        return 1
    fi
}

ZEROS="0000000000000000000000000000000000000000"

setup() {
    # Isolate git and HOME from the caller's environment (core.md tdd-007/009).
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    mkdir -p "${BATS_TEST_TMPDIR}/home"
    export HOME="${BATS_TEST_TMPDIR}/home"
    export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    source "${REPO_ROOT}/tests/helpers/common.bash"
    load_mocks
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/mock_calls"
    export MOCK_GIT_SHOW_TOPLEVEL="${BATS_TEST_TMPDIR}/fake-worktree"
    export MOCK_GIT_DIFF_NAMES=""
    export MOCK_GIT_MERGE_BASE="base123"
}

teardown() {
    rm -f "${MOCK_CALLS_FILE:-}"
}

@test "branch deletion push skips make" {
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat ${ZEROS} refs/heads/feat abc123"
    [ "$status" -eq 0 ]
    assert_no_match "^make"
}

@test "no changed files in push range skips make" {
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    assert_no_match "^make"
}

@test "changed file in pi/ uses worktree root in make path" {
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree/pi test" "${MOCK_CALLS_FILE}"
}

@test "changed file in factorial/factorial-rs/ uses worktree root in make path" {
    export MOCK_GIT_DIFF_NAMES="factorial/factorial-rs/src/main.rs"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree/factorial/factorial-rs test" "${MOCK_CALLS_FILE}"
}

@test "changed files in two sub-projects calls make twice" {
    export MOCK_GIT_DIFF_NAMES=$'pi/pi.py\ne/e.py'
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    [ "$(grep -c "^make" "${MOCK_CALLS_FILE}")" -eq 2 ]
}

@test "hook/script change runs the root test target" {
    # Regression guard: the sub-project loop only matches <dir>/*.py and
    # <dir>/**/*.rs, so a change to the hooks themselves matched nothing and
    # pushed with no local test at all.
    export MOCK_GIT_DIFF_NAMES="scripts/pre-push"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$" "${MOCK_CALLS_FILE}"
}

@test "deny.toml-only push runs the root test target" {
    export MOCK_GIT_DIFF_NAMES="deny.toml"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$" "${MOCK_CALLS_FILE}"
}

@test "crate Cargo.toml-only push runs no make" {
    # Guard against widening the root-scope regex to every *.toml.
    export MOCK_GIT_DIFF_NAMES="pi/pi-rs/Cargo.toml"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    assert_no_match "^make"
}

@test "bats-only change runs the root test target and no sub-project suite" {
    export MOCK_GIT_DIFF_NAMES="tests/scripts/pre_push.bats"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -qE "^make -C [^ ]+ test$" "${MOCK_CALLS_FILE}"
    [ "$(grep -c "^make" "${MOCK_CALLS_FILE}")" -eq 1 ]
}

@test "a passing suite prints an ok line" {
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    [[ "${output}" == *"ok pi"* ]]
}

@test "one failing suite among several prints FAIL and its log and exits 1" {
    export MOCK_GIT_DIFF_NAMES=$'pi/pi.py\nfib/fib.py\ne/e.py'
    export MOCK_MAKE_FAIL_DIR="fib"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 1 ]
    [[ "${output}" == *"FAIL fib"* ]]
    [[ "${output}" == *"ok pi"* ]]
    [[ "${output}" == *"ok e"* ]]
    [[ "${output}" == *"simulated failure in ${BATS_TEST_TMPDIR}/fake-worktree/fib"* ]]
    [ "$(grep -c "^make" "${MOCK_CALLS_FILE}")" -eq 3 ]
}

@test "a suite killed before writing its status prints FAIL and exits 1" {
    export MOCK_GIT_DIFF_NAMES=$'pi/pi.py\nfib/fib.py\ne/e.py'
    export MOCK_MAKE_KILL_DIR="e"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 1 ]
    [[ "${output}" == *"FAIL e"* ]]
    [[ "${output}" == *"ok pi"* ]]
    [[ "${output}" == *"ok fib"* ]]
}

@test "seven changed Python sub-projects run all seven suites" {
    export MOCK_GIT_DIFF_NAMES=$'pi/pi.py\nfib/fib.py\nsq/sq.py\ne/e.py\nfactorial/factorial.py\ncollatz/collatz.py\namicable/amicable.py'
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    [[ "${output}" != *"skipping"* ]]
    [ "$(grep -c "^make" "${MOCK_CALLS_FILE}")" -eq 7 ]
}

@test "the hook locates the runner through a symlink" {
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    ln -s "${REPO_ROOT}/scripts/pre-push" "${BATS_TEST_TMPDIR}/pre-push-link"
    run bash "${BATS_TEST_TMPDIR}/pre-push-link" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    [[ "${output}" == *"ok pi"* ]]
}

@test "a relative symlink to the hook resolves too" {
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    mkdir -p "${BATS_TEST_TMPDIR}/hooks"
    ln -s "../real/pre-push" "${BATS_TEST_TMPDIR}/hooks/pre-push"
    mkdir -p "${BATS_TEST_TMPDIR}/real"
    cp "${REPO_ROOT}/scripts/pre-push" "${REPO_ROOT}/scripts/parallel-make-test.sh" "${BATS_TEST_TMPDIR}/real/"
    run bash "${BATS_TEST_TMPDIR}/hooks/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    [[ "${output}" == *"ok pi"* ]]
}

@test "PRE_PUSH_JOBS=1 runs the changed suites one at a time" {
    export MOCK_GIT_DIFF_NAMES=$'pi/pi.py\nfib/fib.py\ne/e.py'
    export PRE_PUSH_JOBS=1
    export MOCK_MAKE_CONCURRENCY_DIR="${BATS_TEST_TMPDIR}/probe"
    mkdir -p "${MOCK_MAKE_CONCURRENCY_DIR}"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    local f max=0 n
    for f in "${MOCK_MAKE_CONCURRENCY_DIR}"/seen.*; do
        read -r n < "${f}"
        [[ "${n}" -gt "${max}" ]] && max="${n}"
    done
    [ "${max}" -eq 1 ]
}

@test "the default job count runs the changed suites concurrently" {
    export MOCK_GIT_DIFF_NAMES=$'pi/pi.py\nfib/fib.py\ne/e.py'
    unset PRE_PUSH_JOBS
    export MOCK_MAKE_CONCURRENCY_DIR="${BATS_TEST_TMPDIR}/probe"
    mkdir -p "${MOCK_MAKE_CONCURRENCY_DIR}"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    local f max=0 n
    for f in "${MOCK_MAKE_CONCURRENCY_DIR}"/seen.*; do
        read -r n < "${f}"
        [[ "${n}" -gt "${max}" ]] && max="${n}"
    done
    [ "${max}" -eq 3 ]
}

@test "make test failure exits non-zero" {
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    export MOCK_MAKE_EXIT=1
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -ne 0 ]
}

@test "new branch push uses merge-base and calls make for changed files" {
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat ${ZEROS}"
    [ "$status" -eq 0 ]
    grep -q "merge-base" "${MOCK_CALLS_FILE}"
    # The sub-project selection must diff the merge-base..local range. Matching
    # only "merge-base" passes even when the range is built from something else,
    # because the CLAUDE.md budget check also calls merge-base.
    grep -qxF "git diff --name-only ${MOCK_GIT_MERGE_BASE}..abc123" "${MOCK_CALLS_FILE}"
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree/pi test" "${MOCK_CALLS_FILE}"
}

@test "rust-only change does not drag in the python sibling suite" {
    # CI scopes pi.py with the single-level glob `pi/*.py`, which cannot match
    # a file under pi/pi-rs/. The hook must not be broader than the gate it
    # approximates.
    export MOCK_GIT_DIFF_NAMES="pi/pi-rs/src/lib.rs"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree/pi/pi-rs test" "${MOCK_CALLS_FILE}"
    assert_no_match "make -C ${BATS_TEST_TMPDIR}/fake-worktree/pi test"
}

@test "python-only change does not drag in the rust sibling suite" {
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree/pi test" "${MOCK_CALLS_FILE}"
    assert_no_match "make -C ${BATS_TEST_TMPDIR}/fake-worktree/pi/pi-rs test"
}

@test "scripts-only change reaches the root test target" {
    export MOCK_GIT_DIFF_NAMES="scripts/run-bash-coverage.sh"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -qE "^make -C [^ ]+ test$" "${MOCK_CALLS_FILE}" || {
        printf 'expected the root test target, got:\n%s\n' \
            "$(cat "${MOCK_CALLS_FILE}")" >&2
        return 1
    }
}

@test "repo-level python test change triggers the root suite" {
    export MOCK_GIT_DIFF_NAMES="tests/test_triage_log.py"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -qE "^make" "${MOCK_CALLS_FILE}" || {
        printf 'expected a make call for a tests/*.py change, got:\n%s\n' \
            "$(cat "${MOCK_CALLS_FILE}")" >&2
        return 1
    }
}

@test "release workflow change reaches the root test target" {
    # Regression guard: a change to .github/workflows/release-*.yml matches
    # neither the sub-project loop nor the root-test pattern, so
    # tests/test_release_workflows.py — the contract test pinning all eleven
    # release workflows — never runs on the change class it guards.
    export MOCK_GIT_DIFF_NAMES=".github/workflows/release-sq-rs.yml"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -qE "^make -C [^ ]+ test$" "${MOCK_CALLS_FILE}" || {
        printf 'expected the root test target, got:\n%s\n' \
            "$(cat "${MOCK_CALLS_FILE}")" >&2
        return 1
    }
}

@test "pyrightconfig.json change reaches the root test target" {
    # Regression guard: pyrightconfig.json changes what the root suite can
    # type-check, but the trigger pattern did not name it.
    export MOCK_GIT_DIFF_NAMES="pyrightconfig.json"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$" "${MOCK_CALLS_FILE}"
}

@test "requirements-dev.txt change reaches the root test target" {
    # Regression guard: requirements-dev.txt changes what the root suite can
    # import, but the trigger pattern did not name it.
    export MOCK_GIT_DIFF_NAMES="requirements-dev.txt"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$" "${MOCK_CALLS_FILE}"
}

@test "typings/ change reaches the root test target" {
    # Regression guard: tests/test_gmpy2_stub.py is the only guard on the stub
    # and pyright accepts Any there, so a stub-only push must run it.
    export MOCK_GIT_DIFF_NAMES="typings/gmpy2/__init__.pyi"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$" "${MOCK_CALLS_FILE}"
}

@test ".claude/scripts/ change reaches the root test target" {
    # Regression guard: .claude/scripts/triage_log.py enters the type-check
    # denominator, but the trigger pattern did not name the directory.
    export MOCK_GIT_DIFF_NAMES=".claude/scripts/triage_log.py"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$" "${MOCK_CALLS_FILE}"
}

@test ".github/workflows/scripts.yml change reaches the root test target" {
    # Regression guard: tests/scripts/makefile.bats:133 greps this workflow
    # file, so editing it can turn the root suite red while the hook stays
    # silent unless it is named in the trigger pattern.
    export MOCK_GIT_DIFF_NAMES=".github/workflows/scripts.yml"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$" "${MOCK_CALLS_FILE}"
}

@test ".github/workflows/auto-merge.yml change reaches the root test target" {
    # tests/test_automerge_bot_hold.py runs the hold step extracted from this
    # workflow, so a hold-step edit must run the root suite (ai-config ADR-0085).
    export MOCK_GIT_DIFF_NAMES=".github/workflows/auto-merge.yml"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$" "${MOCK_CALLS_FILE}"
}

@test "renovate.json change reaches the root test target" {
    # tests/test_renovate_automerge_policy.py asserts this file's auto-merge
    # policy, so editing it must run the root suite.
    export MOCK_GIT_DIFF_NAMES="renovate.json"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -q "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$" "${MOCK_CALLS_FILE}"
}

@test "pi-only change does not reach the root test target" {
    # The point of this file: every existing negative case here either uses
    # an EMPTY diff (which an over-broad root-trigger regex also passes) or
    # names a specific sub-project target rather than the root one. Neither
    # would fail if line 52's regex were widened to match everything. This
    # one names an ordinary sub-project-only change and asserts the root
    # target is never reached.
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    assert_no_match "make -C ${BATS_TEST_TMPDIR}/fake-worktree test\$"
}

# ai-config#229: a gate pattern named `docs/postmortems/**`, a directory that has
# never existed in that repo, and its whole firing matrix passed because each case
# did `mkdir -p` first. The fixture supplied the precondition production must
# already have, so the suite could not tell a live pattern from a dead one.
#
# Every case above sets MOCK_GIT_DIFF_NAMES itself, so it has the same blind spot:
# a pattern and a fixture sharing the same wrong path agree with each other. This
# asserts the alternatives against the tracked set instead, and counts rather than
# checks membership -- a membership check passes on a partial parse.
@test "every root-scope trigger alternative matches at least one tracked path" {
    local line alts alt probe matched=0 total=0 dead="" clean_path
    # `load_mocks` puts tests/mocks on PATH, and it contains a `git` stub -- so a
    # bare `git ls-files` here queries the mock and reports every alternative dead.
    # shell.md: "a PATH mock shadows the binary your production code needs".
    clean_path="$(printf '%s' "${PATH}" | tr ':' '\n' | grep -v 'tests/mocks' | tr '\n' ':' | sed 's/:$//')"
    # Anchor on the root-scope alternation specifically: the sub-project loop
    # above it also pipes `git diff --name-only` into `grep -qE`, but with a
    # built `${_pattern}` rather than a literal, and matching that line first is
    # how the initial version of this test extracted nothing.
    line="$(grep -n "grep -qE '\^scripts/" "${REPO_ROOT}/scripts/pre-push" | head -1)"
    [ -n "${line}" ]

    # Pull the alternation out of the single-quoted grep -E argument.
    alts="$(printf '%s' "${line}" | sed -E "s/.*grep -qE '([^']+)'.*/\1/")"
    [ -n "${alts}" ]
    [ "${alts}" != "${line}" ]

    while IFS= read -r alt; do
        [ -n "${alt}" ] || continue
        total=$((total + 1))
        # Strip anchors and regex escapes to recover the literal path or prefix.
        probe="${alt#^}"; probe="${probe%$}"; probe="${probe//\\./.}"
        # A prefix alternative (no trailing $) matches a directory; a `.*` form is
        # a glob. Reduce both to something git ls-files can answer.
        probe="${probe%%.\**}"
        if [ -n "$(cd "${REPO_ROOT}" && PATH="${clean_path}" git ls-files -- "${probe}" "${probe}*" 2>/dev/null | head -1)" ]; then
            matched=$((matched + 1))
        else
            dead="${dead}${alt} "
        fi
    done < <(printf '%s\n' "${alts}" | tr '|' '\n')

    if [ -n "${dead}" ]; then
        printf 'trigger alternatives matching no tracked path: %s\n' "${dead}" >&2
        return 1
    fi
    # Every parsed alternative matched, and the parse yielded something. Derived
    # rather than a literal: the alternation legitimately grows, and a hardcoded
    # count turns red on a correct addition (writing-plans, magic-number gates).
    [ "${matched}" -eq "${total}" ]
    [ "${total}" -ge 4 ]
}

# The sub-project loop matches only `.py` and `.rs`, and the root trigger has no
# sub-project prefix, so a push touching only an `install_deps.sh` used to lint
# nothing: 19 of 26 tracked `.sh` files never reached shellcheck on the push
# path. Such a push now runs the root `lint-hooks` target, which shellchecks
# every tracked shell file and spawns no Python suite.
@test "python install_deps.sh-only change runs root lint-hooks and nothing else" {
    export MOCK_GIT_DIFF_NAMES="amicable/install_deps.sh"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -qxF "make -C ${BATS_TEST_TMPDIR}/fake-worktree lint-hooks" "${MOCK_CALLS_FILE}"
    [ "$(grep -c "^make" "${MOCK_CALLS_FILE}")" -eq 1 ]
}

@test "rust install_deps.sh-only change runs root lint-hooks, not the crate suite" {
    export MOCK_GIT_DIFF_NAMES="pi/pi-rs/install_deps.sh"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -qxF "make -C ${BATS_TEST_TMPDIR}/fake-worktree lint-hooks" "${MOCK_CALLS_FILE}"
    assert_no_match "make -C ${BATS_TEST_TMPDIR}/fake-worktree/pi/pi-rs test"
}

@test "lint-hooks failure on a shell-only push exits non-zero" {
    export MOCK_GIT_DIFF_NAMES="amicable/install_deps.sh"
    export MOCK_MAKE_EXIT=1
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -ne 0 ]
    grep -qxF "make -C ${BATS_TEST_TMPDIR}/fake-worktree lint-hooks" "${MOCK_CALLS_FILE}"
}

@test "scripts/*.sh change runs root test once and no separate lint-hooks" {
    # Root `make test` already runs `lint`, which runs `lint-hooks`.
    export MOCK_GIT_DIFF_NAMES="scripts/rust-check.sh"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -qxF "make -C ${BATS_TEST_TMPDIR}/fake-worktree test" "${MOCK_CALLS_FILE}"
    assert_no_match "lint-hooks"
}

@test "install_deps.sh plus a python source change runs lint-hooks and the suite" {
    export MOCK_GIT_DIFF_NAMES=$'pi/install_deps.sh\npi/pi.py'
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    grep -qxF "make -C ${BATS_TEST_TMPDIR}/fake-worktree lint-hooks" "${MOCK_CALLS_FILE}"
    grep -qxF "make -C ${BATS_TEST_TMPDIR}/fake-worktree/pi test" "${MOCK_CALLS_FILE}"
    [ "$(grep -c "^make" "${MOCK_CALLS_FILE}")" -eq 2 ]
}

@test "shell lint still runs alongside seven concurrent sub-project suites" {
    export MOCK_GIT_DIFF_NAMES=$'pi/pi.py\nfib/fib.py\nsq/sq.py\ne/e.py\nfactorial/factorial.py\ncollatz/collatz.py\namicable/amicable.py\namicable/install_deps.sh'
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    [[ "${output}" != *"skipping local tests"* ]]
    grep -qxF "make -C ${BATS_TEST_TMPDIR}/fake-worktree lint-hooks" "${MOCK_CALLS_FILE}"
    [ "$(grep -c "^make" "${MOCK_CALLS_FILE}")" -eq 8 ]
}

@test "a non-.sh file in a sub-project does not trigger lint-hooks" {
    export MOCK_GIT_DIFF_NAMES=$'amicable/README.md\namicable/install_deps.sh.bak'
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    assert_no_match "^make"
}

# --- CLI contract harness (spec R16) ---------------------------------------
# The harness runs real CLIs, so these cases put a recording python3 stub first
# on PATH; MOCK_PYTHON_EXIT makes one invocation fail. The stub is created in
# the per-test tmpdir, so nothing real is executed and nothing outside it is
# touched.
HARNESS_PROJECTS="amicable collatz e factorial fib perfect-numbers pi sq"

setup_harness_stub() {
    local d
    mkdir -p "${BATS_TEST_TMPDIR}/stub-bin"
    for d in ${HARNESS_PROJECTS}; do
        mkdir -p "${MOCK_GIT_SHOW_TOPLEVEL}/${d}"
    done
    cat > "${BATS_TEST_TMPDIR}/stub-bin/python3" <<'STUB'
#!/usr/bin/env bash
printf "python3 cwd=%s args=%s\n" "$(basename "${PWD}")" "$*" >> "${MOCK_CALLS_FILE}"
if [[ -n "${MOCK_PYTHON_FAIL_DIR:-}" && "$(basename "${PWD}")" = "${MOCK_PYTHON_FAIL_DIR}" ]]; then
    exit 1
fi
exit 0
STUB
    chmod +x "${BATS_TEST_TMPDIR}/stub-bin/python3"
    export PATH="${BATS_TEST_TMPDIR}/stub-bin:${PATH}"
}

# The python3 stub accepts any module name, so a typo in the entry table
# (collatz:collatzz) passes every stubbed case. Check the table against the
# tracked set instead, with a clean PATH so the git mock is not consulted.
@test "every harness entry names a tracked <dir>/<module>.py and there are 8" {
    local line entries entry dir module count=0 clean_path
    clean_path="$(printf '%s' "${PATH}" | tr ':' '\n' | grep -v 'tests/mocks' | tr '\n' ':' | sed 's/:$//')"
    line="$(command grep -m1 'for _entry in ' "${REPO_ROOT}/scripts/pre-push")"
    entries="$(printf '%s' "${line}" | sed -E 's/.*for _entry in (.*); do.*/\1/')"
    [ -n "${entries}" ]
    [ "${entries}" != "${line}" ]
    for entry in ${entries}; do
        dir="${entry%%:*}"
        module="${entry##*:}"
        PATH="${clean_path}" git -C "${REPO_ROOT}" ls-files --error-unmatch -- "${dir}/${module}.py" >/dev/null
        count=$((count + 1))
    done
    [ "${count}" -eq 8 ]
}

@test "harness-only push runs the harness over all 8 CLIs and no project suite" {
    setup_harness_stub
    export MOCK_GIT_DIFF_NAMES="scripts/cli_contract.py"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    [ "$(grep -c '^python3 ' "${MOCK_CALLS_FILE}")" -eq 8 ]
    grep -qxF "python3 cwd=amicable args=../scripts/cli_contract.py amicable.py" "${MOCK_CALLS_FILE}"
    grep -qxF "python3 cwd=perfect-numbers args=../scripts/cli_contract.py perfect_numbers.py" "${MOCK_CALLS_FILE}"
    grep -qxF "python3 cwd=pi args=../scripts/cli_contract.py pi.py" "${MOCK_CALLS_FILE}"
    assert_no_match "^make -C .*/\(pi\|e\|fib\) test"
}

@test "harness still runs alongside seven concurrent sub-project suites" {
    setup_harness_stub
    export MOCK_GIT_DIFF_NAMES=$'pi/pi.py\nfib/fib.py\nsq/sq.py\ne/e.py\nfactorial/factorial.py\ncollatz/collatz.py\namicable/amicable.py\nscripts/cli_contract.py'
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    [[ "${output}" != *"skipping local tests"* ]]
    [ "$(grep -c '^python3 ' "${MOCK_CALLS_FILE}")" -eq 8 ]
    # 7 sub-project suites plus the root target that scripts/cli_contract.py triggers.
    [ "$(grep -c '^make' "${MOCK_CALLS_FILE}")" -eq 8 ]
}

@test "a push not touching the harness runs no harness" {
    setup_harness_stub
    export MOCK_GIT_DIFF_NAMES="pi/pi.py"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    assert_no_match "^python3 "
}

@test "a failing harness run fails the push and names the project" {
    setup_harness_stub
    export MOCK_GIT_DIFF_NAMES="scripts/cli_contract.py"
    export MOCK_PYTHON_FAIL_DIR="fib"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -ne 0 ]
    [[ "${output}" == *"CLI contract harness failed for fib"* ]]
    assert_no_match "cwd=perfect-numbers"
}

@test "a renamed harness still triggers the harness" {
    setup_harness_stub
    # Real git reports only the new name for a rename unless --no-renames is
    # passed; this wrapper reproduces that and otherwise defers to the mock.
    cat > "${BATS_TEST_TMPDIR}/stub-bin/git" <<STUB
#!/usr/bin/env bash
if [[ "\$*" == *"diff"* && "\$*" != *"--no-renames"* ]]; then
    printf '%s\n' "scripts/cli_contract_renamed.py"
    exit 0
fi
if [[ "\$*" == *"diff"* ]]; then
    printf '%s\n' "scripts/cli_contract.py" "scripts/cli_contract_renamed.py"
    exit 0
fi
exec "${REPO_ROOT}/tests/mocks/git" "\$@"
STUB
    chmod +x "${BATS_TEST_TMPDIR}/stub-bin/git"
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    [ "$(grep -c '^python3 ' "${MOCK_CALLS_FILE}")" -eq 8 ]
}

@test "paths merely resembling the harness do not trigger it" {
    setup_harness_stub
    export MOCK_GIT_DIFF_NAMES=$'scripts/cli_contract.pyc\ntests/scripts/cli_contract.py'
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat abc123 refs/heads/feat abc456"
    [ "$status" -eq 0 ]
    assert_no_match "^python3 "
}

# --- Shared push-content gate wiring (spec 2026-10-30, R13) -----------------
# A push to master or main must load ai-config's gate over the network. These
# tests force the load to fail (`gh auth token` exits 1) so no test makes a
# network call: the hook has to refuse before reaching curl or make.

# A ref line needs an existing remote sha; an all-zeros one exits 128 under
# the git mock.
WIRING_LOCAL="abc123"
WIRING_REMOTE="abc456"

# Every wiring test fails the token lookup explicitly, rather than relying on
# the gh mock's default empty output being rejected by accident.
wiring_setup() {
    export MOCK_GH_EXIT_AUTH_TOKEN=1
}

# gh calls other than `auth token`; the gate must reach for nothing else.
wiring_other_gh_calls() {
    local n
    n="$(grep -c '^gh ' "${MOCK_CALLS_FILE}" 2>/dev/null)" || n=0
    local tokens
    tokens="$(grep -c '^gh auth token$' "${MOCK_CALLS_FILE}" 2>/dev/null)" || tokens=0
    printf '%s\n' "$((n - tokens))"
}

# Runs a bash body in its own process group under a 30s watchdog that kills the
# whole group (`set -m`, then `kill -- -PGID`), so a regression that blocks on
# stdin fails the test instead of hanging the suite or orphaning a child.
# `timeout` is not on the macOS runners.
run_in_pgroup() {
    run bash -c '
        set -m
        bash -c "$1" &
        job=$!
        ( sleep 30; kill -- -"${job}" 2>/dev/null ) &
        dog=$!
        wait "${job}"; rc=$?
        kill -- -"${dog}" 2>/dev/null
        exit "${rc}"
    ' _ "$1"
}

@test "wiring: a feature-only push makes no gh call" {
    wiring_setup
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat ${WIRING_LOCAL} refs/heads/feat ${WIRING_REMOTE}"
    [ "$status" -eq 0 ]
    assert_no_match "^gh "
}

@test "wiring: a master push whose gate cannot load is refused before make" {
    wiring_setup
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/master ${WIRING_LOCAL} refs/heads/master ${WIRING_REMOTE}"
    [ "$status" -eq 1 ]
    [[ "${output}" == *"cannot load the push-content gate"* ]]
    grep -q '^gh auth token$' "${MOCK_CALLS_FILE}"
    [ "$(wiring_other_gh_calls)" -eq 0 ]
    assert_no_match "^make"
}

@test "wiring: a main push whose gate cannot load is refused before make" {
    wiring_setup
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/main ${WIRING_LOCAL} refs/heads/main ${WIRING_REMOTE}"
    [ "$status" -eq 1 ]
    [[ "${output}" == *"cannot load the push-content gate"* ]]
    grep -q '^gh auth token$' "${MOCK_CALLS_FILE}"
    [ "$(wiring_other_gh_calls)" -eq 0 ]
    assert_no_match "^make"
}

# `git push origin feat:master` hands the hook a feature local ref and a master
# remote ref; the wiring must key on the remote ref (field 3).
@test "wiring: a feature branch pushed onto master is judged by the gate" {
    wiring_setup
    run bash "${REPO_ROOT}/scripts/pre-push" \
        <<< "refs/heads/feat ${WIRING_LOCAL} refs/heads/master ${WIRING_REMOTE}"
    [ "$status" -eq 1 ]
    [[ "${output}" == *"cannot load the push-content gate"* ]]
    assert_no_match "^make"
}

@test "wiring: master on a later ref line is still judged" {
    wiring_setup
    run bash "${REPO_ROOT}/scripts/pre-push" <<< \
        "refs/heads/feat ${WIRING_LOCAL} refs/heads/feat ${WIRING_REMOTE}"$'\n'"refs/heads/master ${WIRING_LOCAL} refs/heads/master ${WIRING_REMOTE}"
    [ "$status" -eq 1 ]
    [[ "${output}" == *"cannot load the push-content gate"* ]]
    assert_no_match "^make"
}

# The wiring decides master/main in bash and reads stdin with a builtin, so
# neither a PATH awk that says "no match" nor a PATH cat that prints nothing can
# make a master push look like a feature push.
@test "wiring: a PATH awk or cat cannot hide a master push from the gate" {
    wiring_setup
    local stub name shim="${BATS_TEST_TMPDIR}/shim-bin"
    mkdir -p "${shim}"
    for stub in 'awk:exit 1' 'cat:exit 0'; do
        name="${stub%%:*}"
        printf '#!/usr/bin/env bash\n%s\n' "${stub#*:}" > "${shim}/${name}"
        chmod +x "${shim}/${name}"
        rm -f "${MOCK_CALLS_FILE}"
        PATH="${shim}:${PATH}" run bash "${REPO_ROOT}/scripts/pre-push" \
            <<< "refs/heads/master ${WIRING_LOCAL} refs/heads/master ${WIRING_REMOTE}"
        rm -f "${shim}/${name}"
        [ "$status" -eq 1 ]
        [[ "${output}" == *"cannot load the push-content gate"* ]]
        grep -q '^gh auth token$' "${MOCK_CALLS_FILE}"
    done
}

# git always hands pre-push a pipe, but with fd 0 closed the read fails and the
# hook must refuse rather than read "no refs". A `$(cat)` read blocks on a
# closed fd 0 instead of failing, so a regression to it is caught by the
# watchdog rather than by hanging the suite.
@test "wiring: an unreadable stdin refuses before any gh call" {
    wiring_setup
    run_in_pgroup "bash -p '${REPO_ROOT}/scripts/pre-push' <&- 2>&1"
    [ "$status" -eq 1 ]
    [[ "${output}" == *"cannot read the pushed refs"* ]]
    assert_no_match "^gh "
    assert_no_match "^make"
}

# `bash -p` makes bash ignore BASH_ENV. Exec the script directly so the shebang
# is what runs, with BASH_ENV pointing at a file that writes a marker: no marker
# means the shebang's -p took effect. `env` sets BASH_ENV for the script alone:
# a wrapping `bash -c` would source it itself and write the marker. The control
# run as `bash script` (no -p) must write the marker, proving the mechanism can
# fire; the shebang run that follows must not.
@test "wiring: the shebang's -p stops BASH_ENV from being sourced" {
    wiring_setup
    local marker="${BATS_TEST_TMPDIR}/bash_env.marker" env_file="${BATS_TEST_TMPDIR}/bash_env.sh"
    # BASH_ENV is inherited by the bash mocks the hook spawns (git, make), which
    # have no -p; only the hook itself may write the marker, so key on $0.
    printf 'case "$0" in */scripts/pre-push) printf x > "%s" ;; esac\n' "${marker}" > "${env_file}"

    rm -f "${marker}"
    run env BASH_ENV="${env_file}" bash "${REPO_ROOT}/scripts/pre-push" < /dev/null
    [ "$status" -eq 0 ]
    [ -e "${marker}" ]

    rm -f "${marker}"
    run env BASH_ENV="${env_file}" "${REPO_ROOT}/scripts/pre-push" < /dev/null
    [ "$status" -eq 0 ]
    [ ! -e "${marker}" ]
}

@test "wiring: the script's first line is the bash -p shebang" {
    [ "$(head -n 1 "${REPO_ROOT}/scripts/pre-push")" = '#!/usr/bin/env -S bash -p' ]
}

@test "wiring: the block matches the sha256 pinned to ai-config 34cf3bee" {
    local hash
    hash="$(sed -n '/^# >>> push-content-gate wiring$/,/^# <<< push-content-gate wiring$/p' "${REPO_ROOT}/scripts/pre-push" | sha256sum | cut -d' ' -f1)"
    [ "${hash}" = "d556979bd64b72ca237e4bd3a8d4cf709e0db164ae155c18ab0eea86e39e221f" ]
}
