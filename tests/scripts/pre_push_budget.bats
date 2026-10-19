#!/usr/bin/env bats

# Real-git tests for the CLAUDE.md byte-ceiling check in scripts/pre-push.
# Unlike pre_push.bats these must NOT put tests/mocks on PATH: its git mock
# answers every `git diff` with exit 0, which would make "CLAUDE.md unchanged"
# true for every push and the check untestable. The stub dir holds only `make`.

ZEROS="0000000000000000000000000000000000000000"

setup() {
    unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE
    export GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null
    export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com
    export GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
    unset CLAUDE_CODE_SESSION_ID

    REPO_ROOT="$(cd "${BATS_TEST_DIRNAME}/../.." && pwd)"
    REAL_GIT="$(command -v git)"
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/make_calls"
    : > "${MOCK_CALLS_FILE}"

    STUBS="${BATS_TEST_TMPDIR}/stubs"
    mkdir -p "${STUBS}"
    printf '#!/usr/bin/env bash\nprintf "make %%s\\n" "$*" >> "${MOCK_CALLS_FILE}"\n' > "${STUBS}/make"
    chmod +x "${STUBS}/make"

    FIX="${BATS_TEST_TMPDIR}/fixture"
    mkdir -p "${FIX}/scripts"
    "${REAL_GIT}" -C "${FIX}" init -q -b master
    printf 'small\n' > "${FIX}/CLAUDE.md"
    cp "${REPO_ROOT}/scripts/claude_md_budget.py" "${FIX}/scripts/claude_md_budget.py"
    commit_all "base"
    "${REAL_GIT}" -C "${FIX}" update-ref refs/remotes/origin/master HEAD
}

commit_all() {
    "${REAL_GIT}" -C "${FIX}" add -A
    "${REAL_GIT}" -C "${FIX}" commit -q -m "$1"
}

big_claude_md() { head -c "$1" /dev/zero | tr '\0' 'x' > "${FIX}/CLAUDE.md"; }

head_sha() { "${REAL_GIT}" -C "${FIX}" rev-parse HEAD; }

# Runs the hook in the fixture with a one-ref (or multi-line) push on stdin.
run_hook() {
    cd "${FIX}" || return 1
    PATH="${STUBS}:${PATH}" run bash "${REPO_ROOT}/scripts/pre-push" <<< "$1"
}

@test "CLAUDE.md-only push over 30000 bytes is refused" {
    big_claude_md 30001
    commit_all "grow"
    sha="$(head_sha)"
    run_hook "refs/heads/feat ${sha} refs/heads/feat ${ZEROS}"
    [ "$status" -eq 1 ]
    [[ "${output}" == *"refusing ${sha}"* ]]
    [[ "${output}" == *"30001 bytes"* ]]
}

@test "refusal precedes test dispatch" {
    big_claude_md 30001
    mkdir -p "${FIX}/scripts" && printf 'x\n' > "${FIX}/scripts/other.sh"
    commit_all "grow and touch scripts"
    sha="$(head_sha)"
    run_hook "refs/heads/feat ${sha} refs/heads/feat ${ZEROS}"
    [ "$status" -eq 1 ]
    [ ! -s "${MOCK_CALLS_FILE}" ]
}

@test "compliant CLAUDE.md change is allowed with checker evidence" {
    big_claude_md 29999
    commit_all "grow within ceiling"
    sha="$(head_sha)"
    run_hook "refs/heads/feat ${sha} refs/heads/feat ${ZEROS}"
    [ "$status" -eq 0 ]
    [[ "${output}" == *"CLAUDE.md byte ceiling OK for ${sha}"* ]]
}

@test "push not changing CLAUDE.md onto an over-ceiling base is allowed and checker not run" {
    big_claude_md 30001
    commit_all "over-ceiling master"
    "${REAL_GIT}" -C "${FIX}" update-ref refs/remotes/origin/master HEAD
    printf 'y\n' > "${FIX}/other.txt"
    commit_all "unrelated"
    sha="$(head_sha)"
    run_hook "refs/heads/feat ${sha} refs/heads/feat ${ZEROS}"
    [ "$status" -eq 0 ]
    [[ "${output}" != *"byte ceiling"* ]]
}

@test "branch rebased onto over-ceiling master with no own CLAUDE.md change is allowed" {
    "${REAL_GIT}" -C "${FIX}" checkout -q -b feat
    printf 'y\n' > "${FIX}/other.txt"
    commit_all "own change"
    "${REAL_GIT}" -C "${FIX}" checkout -q master
    big_claude_md 30001
    commit_all "master grows"
    "${REAL_GIT}" -C "${FIX}" update-ref refs/remotes/origin/master HEAD
    "${REAL_GIT}" -C "${FIX}" checkout -q feat
    "${REAL_GIT}" -C "${FIX}" rebase -q master
    sha="$(head_sha)"
    # Existing-branch push: remote sha is the pre-rebase tip, not zeros.
    old="$("${REAL_GIT}" -C "${FIX}" rev-parse master~1)"
    run_hook "refs/heads/feat ${sha} refs/heads/feat ${old}"
    [ "$status" -eq 0 ]
    [[ "${output}" != *"byte ceiling"* ]]
    [[ "${output}" != *"refusing"* ]]
}

@test "commit without the checker is skipped with a message" {
    "${REAL_GIT}" -C "${FIX}" rm -q scripts/claude_md_budget.py
    big_claude_md 30001
    commit_all "no checker, big file"
    sha="$(head_sha)"
    run_hook "refs/heads/feat ${sha} refs/heads/feat ${ZEROS}"
    [ "$status" -eq 0 ]
    [[ "${output}" == *"skipping CLAUDE.md byte ceiling for ${sha}"* ]]
}

@test "checker read failure is refused with its own message" {
    big_claude_md 100
    commit_all "change"
    sha="$(head_sha)"
    # Fails only the checker's `git show`; the checker's own `show sha:CLAUDE.md`
    # still works, so only a read of the checker from the commit can trip it.
    printf '#!/usr/bin/env bash\n[[ "$1" == show && "${!#}" == *:scripts/claude_md_budget.py ]] && exit 128\nexec "%s" "$@"\n' "${REAL_GIT}" > "${STUBS}/git"
    chmod +x "${STUBS}/git"
    run_hook "refs/heads/feat ${sha} refs/heads/feat ${ZEROS}"
    [ "$status" -eq 1 ]
    [[ "${output}" == *"refusing ${sha}: cannot read scripts/claude_md_budget.py from ${sha}"* ]]
    [[ "${output}" != *"skipping CLAUDE.md byte ceiling"* ]]
}

@test "tree listing failure is refused, not treated as a missing checker" {
    big_claude_md 100
    commit_all "change"
    sha="$(head_sha)"
    printf '#!/usr/bin/env bash\n[[ "$1" == ls-tree && "$*" == *scripts/claude_md_budget.py* ]] && exit 128\nexec "%s" "$@"\n' "${REAL_GIT}" > "${STUBS}/git"
    chmod +x "${STUBS}/git"
    run_hook "refs/heads/feat ${sha} refs/heads/feat ${ZEROS}"
    [ "$status" -eq 1 ]
    [[ "${output}" == *"refusing ${sha}: cannot read tree of ${sha}"* ]]
    [[ "${output}" != *"skipping CLAUDE.md byte ceiling"* ]]
}

@test "checker runs isolated: a planted subprocess.py in TMPDIR does not run" {
    big_claude_md 30001
    commit_all "grow"
    sha="$(head_sha)"
    plant="${BATS_TEST_TMPDIR}/plant"
    marker="${BATS_TEST_TMPDIR}/marker"
    mkdir -p "${plant}"
    # Without `python3 -I` the script's directory heads sys.path, so this file
    # shadows the stdlib module, records that it ran, and makes the checker exit 0.
    printf 'import os\nopen("%s", "w").close()\nos._exit(0)\n' "${marker}" > "${plant}/subprocess.py"
    TMPDIR="${plant}" run_hook "refs/heads/feat ${sha} refs/heads/feat ${ZEROS}"
    [ "$status" -eq 1 ]
    [[ "${output}" == *"refusing ${sha}"* ]]
    [ ! -e "${marker}" ]
}

@test "failed diff is refused" {
    big_claude_md 100
    commit_all "change"
    sha="$(head_sha)"
    printf '#!/usr/bin/env bash\n[[ "$1" == diff ]] && exit 128\nexec "%s" "$@"\n' "${REAL_GIT}" > "${STUBS}/git"
    chmod +x "${STUBS}/git"
    run_hook "refs/heads/feat ${sha} refs/heads/feat ${ZEROS}"
    [ "$status" -eq 1 ]
    [[ "${output}" == *"cannot determine whether it changes CLAUDE.md"* ]]
}

@test "orphan-branch push is not refused by this check" {
    "${REAL_GIT}" -C "${FIX}" checkout -q --orphan lone
    "${REAL_GIT}" -C "${FIX}" rm -rq --cached .
    big_claude_md 30001
    "${REAL_GIT}" -C "${FIX}" add CLAUDE.md
    "${REAL_GIT}" -C "${FIX}" commit -q -m "orphan root"
    sha="$(head_sha)"
    # Unrelated history: merge-base with origin/master fails, root fallback applies.
    run_hook "refs/heads/lone ${sha} refs/heads/lone ${ZEROS}"
    [ "$status" -eq 0 ]
    [[ "${output}" != *"refusing"* ]]
}

@test "two-ref push: checker runs per ref and a non-HEAD second ref over ceiling is refused" {
    "${REAL_GIT}" -C "${FIX}" checkout -q -b one
    printf 'medium\n' > "${FIX}/CLAUDE.md"
    commit_all "one: within ceiling"
    one="$(head_sha)"
    "${REAL_GIT}" -C "${FIX}" checkout -q master
    "${REAL_GIT}" -C "${FIX}" checkout -q -b two
    big_claude_md 30001
    commit_all "two: over ceiling"
    two="$(head_sha)"
    # HEAD returns to master (small CLAUDE.md): a checker run on HEAD instead of
    # the pushed sha would pass ref two.
    "${REAL_GIT}" -C "${FIX}" checkout -q master
    run_hook "$(printf 'refs/heads/one %s refs/heads/one %s\nrefs/heads/two %s refs/heads/two %s' "${one}" "${ZEROS}" "${two}" "${ZEROS}")"
    [ "$status" -eq 1 ]
    [[ "${output}" == *"CLAUDE.md byte ceiling OK for ${one}"* ]]
    [[ "${output}" == *"refusing ${two}"* ]]
    [[ "${output}" != *"refusing ${one}"* ]]
}
