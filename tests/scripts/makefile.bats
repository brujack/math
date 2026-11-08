#!/usr/bin/env bats

load '../helpers/common'

# HAVE_PARALLEL is forced on the command line in each case below: the default is
# detected from the host, and a test that passes only where GNU parallel happens to
# be installed says nothing about the branch it is not on.
@test "make test-hooks without GNU parallel runs bats --recursive tests/ serially" {
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS -u JOBS -u HAVE_PARALLEL make -C "${REPO_ROOT}" -n test-hooks HAVE_PARALLEL= --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"bats --recursive tests/"* ]]
    [[ "${output}" != *"--jobs"* ]]
}

@test "make test-hooks without GNU parallel prints a notice naming the remedy" {
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS -u JOBS -u HAVE_PARALLEL make -C "${REPO_ROOT}" -n test-hooks HAVE_PARALLEL= --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"GNU parallel not found"* ]]
    [[ "${output}" == *"apt-get install parallel"* ]]
    [[ "${output}" == *"brew install parallel"* ]]
}

@test "make test-hooks with GNU parallel runs bats --jobs 8 --recursive tests/" {
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS -u JOBS -u HAVE_PARALLEL make -C "${REPO_ROOT}" -n test-hooks HAVE_PARALLEL=yes --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"bats --jobs 8 --recursive tests/"* ]]
    [[ "${output}" != *"GNU parallel not found"* ]]
}

@test "make test-hooks honours a JOBS override" {
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS -u JOBS -u HAVE_PARALLEL make -C "${REPO_ROOT}" -n test-hooks HAVE_PARALLEL=yes JOBS=3 --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"bats --jobs 3 --recursive tests/"* ]]
}

@test "make test-hooks treats a non-GNU parallel as absent" {
    # moreutils ships a different `parallel` that rejects bats' flags.
    mkdir -p "${BATS_TEST_TMPDIR}/bin"
    printf '#!/bin/sh\necho "parallel from moreutils"\n' > "${BATS_TEST_TMPDIR}/bin/parallel"
    chmod +x "${BATS_TEST_TMPDIR}/bin/parallel"
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS -u JOBS -u HAVE_PARALLEL PATH="${BATS_TEST_TMPDIR}/bin:${PATH}" make -C "${REPO_ROOT}" -n test-hooks --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"GNU parallel not found"* ]]
}

@test "make install-hooks recipe links pre-commit hook" {
    run make -C "${REPO_ROOT}" -n install-hooks --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"scripts/pre-commit"* ]]
}

@test "make install-hooks recipe links pre-push hook" {
    run make -C "${REPO_ROOT}" -n install-hooks --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"scripts/pre-push"* ]]
}

@test "install-hooks and test-hooks are declared .PHONY" {
    run grep -E "^\.PHONY" "${REPO_ROOT}/Makefile"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"install-hooks"* ]]
    [[ "${output}" == *"test-hooks"* ]]
}

# Both lists are derived from `git ls-files`, never hardcoded: an omitted crate
# would be absent from the loop rather than failing it, so a hand-list turns a
# real gap into a silent pass (tdd.md "Coverage Denominators"). The non-empty
# assertion before each loop guards the same class from the other direction --
# an empty derived list makes every `for` body vacuously true.

@test "every Rust crate Makefile's test target depends on lint" {
    local makefiles missing=""
    makefiles="$(cd "${REPO_ROOT}" && git ls-files '*-rs/Makefile')"
    [ -n "${makefiles}" ]

    while IFS= read -r mf; do
        [[ -z "${mf}" ]] && continue
        local prereqs
        prereqs="$(grep -m1 -E '^test:' "${REPO_ROOT}/${mf}" | sed 's/^test:[[:space:]]*//')"
        case " ${prereqs} " in
        *" lint "*) ;;
        *) missing="${missing}${mf} " ;;
        esac
    done <<< "${makefiles}"

    if [[ -n "${missing}" ]]; then
        printf 'test: target does not depend on lint in: %s\n' "${missing}" >&2
        return 1
    fi
}

# scripts/rust-check.sh lint mode runs `cargo machete` unguarded, so a workflow
# reaching lint -- directly or through `test: lint` -- fails without it
# installed. This invariant is coupled to the one above: satisfying that test
# without this one turns the crate's CI red instead of green.
@test "every Rust crate CI workflow installs cargo-machete" {
    local workflows missing=""
    workflows="$(cd "${REPO_ROOT}" && git ls-files '.github/workflows/*-rs.yml' | grep -v '/release-')"
    [ -n "${workflows}" ]

    while IFS= read -r wf; do
        [[ -z "${wf}" ]] && continue
        grep -qE '^[[:space:]]*(run:[[:space:]]*cargo install cargo-machete|tool:[[:space:]]*.*cargo-machete@[0-9])' \
            "${REPO_ROOT}/${wf}" || missing="${missing}${wf} "
    done <<< "${workflows}"

    if [[ -n "${missing}" ]]; then
        printf 'cargo-machete not installed in: %s\n' "${missing}" >&2
        return 1
    fi
}

# The push path is what this pins, not the Makefile's aesthetics: pre-push
# invokes a root target when scripts/, tests/ or the Makefile change, and until
# this prerequisite existed that target ran bats without ever linting the shell.
# `make lint-hooks` had exactly one call site in the repo and it was CI. See
# code-standards.md: the requirement is that every changed component's lint
# runs on the push path.
#
# (A comment line must not START with the word shellcheck -- that is parsed as
# a directive, SC1072/SC1073. Caught by this very prerequisite on its first run.)
@test "root make test reaches shell lint" {
    run make -C "${REPO_ROOT}" -n test --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"shellcheck"* ]]
}

# Companion to the shell-lint assertion above. ruff.toml at the repo root
# already reaches every .py in the repo by ancestor discovery -- the config was
# never the gap, the invocation was. scripts/ and tests/ sat outside every
# gated scope and were linted by nothing, which ai-config/docs/knowledge/math-quick-reference.md § Ruff config recorded
# as a known gap. `ruff check .` from the root needs no derived file list and
# so has no denominator to drift.
@test "root make lint reaches ruff" {
    run make -C "${REPO_ROOT}" -n lint RUFF=/usr/bin/true --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"ruff check"* ]]
}

@test "root make test reaches ruff" {
    run make -C "${REPO_ROOT}" -n test RUFF=/usr/bin/true --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"ruff check"* ]]
}

@test "lint-python runs both ruff check and ruff format" {
    run make -C "${REPO_ROOT}" -n lint-python RUFF=/usr/bin/true --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"ruff check"* ]]
    [[ "${output}" == *"ruff format --check"* ]]
}

# The guard is tested rather than incidental, and it is why the three above
# force RUFF. `ifndef RUFF` is evaluated at parse time, so on a machine without
# ruff -- the bash-coverage CI job, for one -- `make -n` prints the skip notice
# instead of the recipe. That notice contains the word "ruff", so an assertion
# matching the bare substring passes while reporting the gate was SKIPPED.
# Caught by CI on this branch, not by review.
@test "lint-python skips with a remedy when ruff is absent" {
    run make -C "${REPO_ROOT}" -n lint-python RUFF= --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"ruff not found"* ]]
    [[ "${output}" == *"pip install ruff=="* ]]
    [[ "${output}" != *"ruff check"* ]]
}

@test "lint-python skips when ruff is on PATH but not runnable" {
    local stub="${BATS_TEST_TMPDIR}/bin"
    mkdir -p "${stub}"
    printf '#!/usr/bin/env bash\nexit 127\n' >"${stub}/ruff"
    chmod +x "${stub}/ruff"
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS PATH="${stub}:${PATH}" make -C "${REPO_ROOT}" lint-python --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"ruff not found, skipping"* ]]
    [[ "${output}" != *"Error 127"* ]]
}

@test "lint-python runs ruff when ruff answers --version" {
    local stub="${BATS_TEST_TMPDIR}/bin"
    mkdir -p "${stub}"
    printf '#!/usr/bin/env bash\nexit 0\n' >"${stub}/ruff"
    chmod +x "${stub}/ruff"
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS PATH="${stub}:${PATH}" make -C "${REPO_ROOT}" -n lint-python --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"ruff check"* ]]
    [[ "${output}" != *"ruff not found"* ]]
}

@test "python sub-project lint skips when ruff is on PATH but not runnable" {
    local stub="${BATS_TEST_TMPDIR}/bin"
    mkdir -p "${stub}"
    printf '#!/usr/bin/env bash\nexit 127\n' >"${stub}/ruff"
    chmod +x "${stub}/ruff"
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS PATH="${stub}:${PATH}" make -C "${REPO_ROOT}/fib" lint --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"ruff not found, skipping (install: pip install ruff==0.16.4)"* ]]
    [[ "${output}" != *"Error 127"* ]]
}

@test "python sub-project lint runs ruff when ruff answers --version" {
    local stub="${BATS_TEST_TMPDIR}/bin"
    mkdir -p "${stub}"
    printf '#!/usr/bin/env bash\nexit 0\n' >"${stub}/ruff"
    chmod +x "${stub}/ruff"
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS PATH="${stub}:${PATH}" make -C "${REPO_ROOT}/fib" -n lint --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"ruff check"* ]]
    [[ "${output}" != *"ruff not found"* ]]
}

@test "the workflow running root lint installs ruff" {
    run grep -E '^[[:space:]]*run: pip install .*ruff==' \
        "${REPO_ROOT}/.github/workflows/scripts.yml"
    [ "${status}" -eq 0 ]
}

# ADR-0006: pin GitHub Actions to immutable SHA digests. A *branch* ref is the
# worst case -- it moves with no upstream release at all, so a compromised or
# simply changed action reaches CI with nothing to notice. This asserts the
# whole class rather than one action, because the next branch ref will not be
# dtolnay's. Local `./.github/workflows/*.yml` reusable-workflow calls carry no
# `@` and cannot be digest-pinned, so they never match.
@test "no workflow pins a third-party action to a mutable branch ref" {
    local refs bad=""
    refs="$(cd "${REPO_ROOT}" && git grep -hoE 'uses: [^ ]+@[A-Za-z0-9._/-]+' -- '.github/workflows/*.yml' \
        | sed 's/uses: //' | sort -u)"
    [ -n "${refs}" ]

    while IFS= read -r r; do
        [[ -z "${r}" ]] && continue
        case "${r##*@}" in
        stable | main | master | nightly | dev) bad="${bad}${r} " ;;
        esac
    done <<< "${refs}"

    if [[ -n "${bad}" ]]; then
        printf 'action(s) pinned to a mutable branch ref: %s\n' "${bad}" >&2
        return 1
    fi
}

# renovate.json must not extend a preset hosted in another repo. Renovate
# resolves `extends` at initRepo, BEFORE any dependency extraction, so a preset
# it cannot fetch throws config-validation and abandons the entire repository --
# silently, from the repo's point of view: no PRs, no dashboard, no error
# anywhere a maintainer looks. math is public and the shared preset lives in a
# private repo, so this repo extracted 0 of its 291 dependencies from
# 2026-05-18 until the preset was inlined. Reproduced: result config-validation
# in 207ms, versus a full extraction in 6578ms once inlined.
@test "renovate.json extends no cross-repo preset" {
    local bad
    bad="$(python3 -c "
import json
for e in json.load(open('${REPO_ROOT}/renovate.json')).get('extends', []):
    if not e.startswith('config:'):
        print(e)
")"
    if [[ -n "${bad}" ]]; then
        printf 'renovate.json extends a non-official preset, which is fetched at initRepo and aborts the repo if unreachable: %s\n' "${bad}" >&2
        return 1
    fi
}

# `cargo mutants --timeout` bounds every cargo command it runs, including the
# unmutated baseline -- not just the per-mutant budget the flag name suggests.
# A crate whose baseline test phase exceeds a fixed --timeout (pi-rs, e-rs at
# 54s+ against 30s) times out before evaluating a single mutant. The fix is a
# multiplier derived from the measured baseline, floored so the nine
# already-working crates don't fall below their current 30s budget.
#
# The mocks directory is stripped from PATH before the `git ls-files` call:
# tests/mocks/git answers ls-files with MOCK_GIT_LS_FILES (empty by default),
# so an inherited mock silently returns an empty list and every assertion below would pass vacuously
# (math#95 -- see shell.md's PATH-mock-shadowing pitfall).
#
# --timeout-multiplier and --minimum-test-timeout both contain the substring
# "timeout", and --timeout-multiplier even starts with "--timeout" -- a bare
# `grep -q -- '--timeout'` cannot tell the fixed form from the fix. Matching
# "--timeout" followed by whitespace then a digit is what discriminates them.
@test "no crate Makefile caps the mutants baseline with a fixed --timeout" {
    local _clean_path
    _clean_path="$(printf '%s' "${PATH}" | tr ':' '\n' | grep -v 'tests/mocks' | tr '\n' ':' | sed 's/:$//')"

    local makefiles count=0 bad=""
    makefiles="$(cd "${REPO_ROOT}" && PATH="${_clean_path}" command git ls-files '*/*-rs/Makefile')"
    [ -n "${makefiles}" ]

    while IFS= read -r mf; do
        [[ -z "${mf}" ]] && continue
        grep -q '^mutants:' "${REPO_ROOT}/${mf}" || continue
        count=$((count + 1))

        if grep -qE -- '--timeout[[:space:]]+[0-9]' "${REPO_ROOT}/${mf}"; then
            bad="${bad}${mf}(fixed --timeout caps the baseline) "
        fi
        grep -qE -- '--minimum-test-timeout' "${REPO_ROOT}/${mf}" \
            || bad="${bad}${mf}(missing --minimum-test-timeout) "
    done <<< "${makefiles}"

    [ "${count}" -eq 11 ]

    if [[ -n "${bad}" ]]; then
        printf 'mutants recipe does not scale the baseline timeout: %s\n' "${bad}" >&2
        return 1
    fi
}

# Every crate Makefile carries the PR-scoped mutants-diff target next to mutants, under the
# same memory cap. The mocks directory is stripped from PATH before git ls-files for the
# reason given above (math#95).
@test "every crate Makefile has a capped mutants-diff target using --in-diff" {
    local _clean_path
    _clean_path="$(printf '%s' "${PATH}" | tr ':' '\n' | grep -v 'tests/mocks' | tr '\n' ':' | sed 's/:$//')"

    local makefiles count=0 bad="" body
    makefiles="$(cd "${REPO_ROOT}" && PATH="${_clean_path}" command git ls-files '*/*-rs/Makefile')"
    [ -n "${makefiles}" ]

    while IFS= read -r mf; do
        [[ -z "${mf}" ]] && continue
        count=$((count + 1))
        grep -qE '^\.PHONY:.* mutants-diff( |$)' "${REPO_ROOT}/${mf}" || bad="${bad}${mf}(not PHONY) "
        grep -q '^mutants-diff:' "${REPO_ROOT}/${mf}" || { bad="${bad}${mf}(no target) "; continue; }
        body="$(sed -n '/^mutants-diff:/,/^[a-z]/p' "${REPO_ROOT}/${mf}")"
        [[ "${body}" == *"--in-diff"* ]] || bad="${bad}${mf}(no --in-diff) "
        [[ "${body}" == *"--timeout-multiplier 5"* ]] || bad="${bad}${mf}(no --timeout-multiplier 5 in mutants-diff) "
        [[ "${body}" == *"--minimum-test-timeout 30"* ]] || bad="${bad}${mf}(no --minimum-test-timeout 30 in mutants-diff) "
        # The cap lives once in the MUTANTS_SETUP macro; mutants-diff must use it and the macro must hold the cap.
        [[ "${body}" == *'$(MUTANTS_SETUP)'* ]] || bad="${bad}${mf}(mutants-diff does not use MUTANTS_SETUP) "
        [[ "$(sed -n '/^MUTANTS_SETUP =/,/^$/p' "${REPO_ROOT}/${mf}")" == *"ulimit -v 8388608"* ]] || bad="${bad}${mf}(no ulimit in MUTANTS_SETUP) "
        if grep -qE -- '--timeout[[:space:]]+[0-9]' "${REPO_ROOT}/${mf}"; then
            bad="${bad}${mf}(fixed --timeout) "
        fi
    done <<< "${makefiles}"

    [ "${count}" -eq 11 ]
    [ -z "${bad}" ] || { printf 'mutants-diff problems: %s\n' "${bad}" >&2; return 1; }
}

# rm that stalls ~1 s on a TMPDIR removal once the hang stub is ready (STUB_RM_SLOW set), so a
# second SIGTERM lands while the cleanup rm is running. It logs the path it was asked to remove
# to ${BATS_TEST_TMPDIR}/rm-log only when that path (the last argument) is an existing directory at
# call time, so a test can tell "dir removed" from "dir never there".
_stub_slow_rm() {
    cat > "$1/rm" <<'STUB'
#!/bin/bash
case "$*" in
    *mutants-tmp*)
        if [ -n "${STUB_RM_SLOW}" ] && [ -e "${BATS_TEST_TMPDIR}/hang-ready" ]; then
            if [ -d "${@: -1}" ]; then
                printf '%s\n' "$*" >> "${BATS_TEST_TMPDIR}/rm-log"
            fi
            : > "${BATS_TEST_TMPDIR}/rm-started"
            sleep 1
        fi ;;
esac
exec /bin/rm "$@"
STUB
    chmod +x "$1/rm"
}

# On a timed-out wait, prints every process still in session $1 (the setsid'd make) with its
# signal dispositions, so a failure in CI shows which process held up and whether TERM was
# ignored, blocked or caught there. Diagnostic only; always returns 0.
_dump_group_state() {
    local p
    printf 'process state in session %s:\n' "$1" >&2
    for p in $(ps -e -o pid= -o sid= 2>/dev/null | awk -v s="$1" '$2 == s { print $1 }'); do
        printf '  %s\n' "$(ps -o pid=,ppid=,stat=,args= -p "${p}" 2>/dev/null)" >&2
        grep -E '^Sig(Blk|Ign|Cgt):' "/proc/${p}/status" 2>/dev/null | sed 's/^/    /' >&2
    done
    return 0
}

# The Python SIGTERM tests time out under CI's bash-coverage tracer only (math#212, run
# 42126186260; not reproduced locally, including `make bash-coverage` on 2 CPUs). Makefile
# recipes are outside the coverage denominator, so skipping them there loses no coverage;
# they still run as real tests in the scripts job, and tests/test_mutants_cleanup_traps.py
# pins the traps deterministically.
_skip_under_coverage_tracer() {
    if [ -n "${_COV_TRACE_FILE:-}" ]; then
        skip "SIGTERM timing test is not run under the bash-coverage tracer"
    fi
}

# Waits up to $2 tenths of a second for $1 to exist; fails naming the wait on timeout.
_wait_for_file() {
    local i
    for i in $(seq 1 "$2"); do
        [ -e "$1" ] && return 0
        sleep 0.1
    done
    printf 'timed out waiting for %s\n' "$1" >&2
    return 1
}

# Runs `make <args>` in $1 as its own process group with the hang stubs, sends the group SIGTERM
# once the stub hangs, and again once the cleanup rm has started. Fails with a named message on
# any timed-out wait. Env (STUB_*, TMPDIR) is inherited from the caller.
_term_group_twice() {
    local dir="$1" pid
    shift
    rm -f "${BATS_TEST_TMPDIR}/hang-ready" "${BATS_TEST_TMPDIR}/rm-started" "${BATS_TEST_TMPDIR}/rm-log"
    setsid env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS make -C "${dir}" "$@" >/dev/null 2>&1 </dev/null &
    pid=$!
    if ! _wait_for_file "${BATS_TEST_TMPDIR}/hang-ready" 100; then
        _dump_group_state "${pid}"
        kill -KILL -- "-${pid}" 2>/dev/null
        wait "${pid}" 2>/dev/null || true
        printf 'wait failed: stub never reached hang-ready\n' >&2
        return 1
    fi
    kill -TERM -- "-${pid}"
    if ! _wait_for_file "${BATS_TEST_TMPDIR}/rm-started" 100; then
        _dump_group_state "${pid}"
        kill -KILL -- "-${pid}" 2>/dev/null
        wait "${pid}" 2>/dev/null || true
        printf 'wait failed: cleanup rm never started after first TERM\n' >&2
        return 1
    fi
    kill -TERM -- "-${pid}" 2>/dev/null
    local i
    for i in $(seq 1 100); do
        kill -0 "${pid}" 2>/dev/null || break
        sleep 0.1
    done
    if kill -0 "${pid}" 2>/dev/null; then
        _dump_group_state "${pid}"
        kill -KILL -- "-${pid}" 2>/dev/null
        wait "${pid}" 2>/dev/null || true
        printf 'wait failed: make did not exit after second TERM\n' >&2
        return 1
    fi
    wait "${pid}" 2>/dev/null || true
}

# Behavioural harness: a copy of fib-rs's rendered Makefile and a stub cargo that logs its argv
# and the address-space limit it runs under, and exits STUB_CARGO_RC. An optional
# STUB_CARGO_WRITE makes it write mutants.out/outcomes.json as cargo-mutants would.
_rs_stub_setup() {
    CALLS="${BATS_TEST_TMPDIR}/calls"
    : > "${CALLS}"
    export CALLS
    CRATE="${BATS_TEST_TMPDIR}/fib-rs"
    local bin="${BATS_TEST_TMPDIR}/bin"
    mkdir -p "${CRATE}" "${bin}"
    cp "${REPO_ROOT}/fib/fib-rs/Makefile" "${CRATE}/Makefile"
    cat > "${bin}/cargo" <<'STUB'
#!/bin/bash
printf 'cargo %s ulimit=%s\n' "$*" "$(ulimit -v)" >> "${CALLS}"
# One argument per line, so a test can tell one quoted argument from several.
for arg in "$@"; do printf 'arg %s\n' "${arg}" >> "${CALLS}.args"; done
# Simulate a killed timeout test: its TempDir is never dropped, so it leaves a dir in TMPDIR.
printf 'tmpdir %s\n' "${TMPDIR}" >> "${CALLS}"
printf 'fsize=%s\n' "$(ulimit -f)" >> "${CALLS}"
printf 'core=%s\n' "$(ulimit -c)" >> "${CALLS}"
# The recipe must create TMPDIR itself and wipe a stale one before cargo runs.
if [ -n "${TMPDIR}" ] && [ ! -d "${TMPDIR}" ]; then printf 'tmpdir-missing\n' >> "${CALLS}"; fi
if [ -n "${TMPDIR}" ] && [ -e "${TMPDIR}/old" ]; then printf 'stale\n' >> "${CALLS}"; fi
if [ -n "${TMPDIR}" ]; then
    mkdir "${TMPDIR}/.tmpLEAK" && printf x > "${TMPDIR}/.tmpLEAK/primes_1e7.txt"
fi
if [ -n "${STUB_CARGO_WRITE}" ]; then
    mkdir -p mutants.out
    printf 'NEW\n' > mutants.out/outcomes.json
fi
# Hang after the TMPDIR is populated, as a cancelled CI job would find cargo-mutants.
if [ -n "${STUB_CARGO_HANG}" ]; then
    : > "${BATS_TEST_TMPDIR}/hang-ready"
    sleep 30
fi
exit "${STUB_CARGO_RC:-0}"
STUB
    _stub_slow_rm "${bin}"
    chmod +x "${bin}/cargo"
    export PATH="${bin}:${PATH}"
}

# Dev boxes commonly run with a soft core limit of 0 (`claude` and `workstation`, measured), so a test inheriting it would see 0
# without the fix. Raise the soft limit to the hard one first; a zero hard limit cannot
# test anything, which is a failure in CI and a skip elsewhere.
_raise_core_limit() {
    local hard
    hard="$(ulimit -Hc)"
    if [ "${hard}" = "0" ]; then
        [ "${CI:-}" = "true" ] && { printf 'hard core limit is 0 in CI\n' >&2; return 1; }
        skip "hard core limit is 0; the parent limit cannot be raised"
    fi
    ulimit -Sc "${hard}"
}

# Fails unless the file holds at least one core= line (bare, or after a command name) and every one is core=0.
_assert_cores_disabled() {
    local lines
    lines="$(grep -E '(^| )core=' "$1")" || { printf 'no core= line recorded\n' >&2; return 1; }
    if printf '%s\n' "${lines}" | grep -vqE '(^| )core=0$'; then
        printf 'core limit not 0:\n%s\n' "${lines}" >&2
        return 1
    fi
}

_rs_make() {
    env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS -u MUTANTS_UNCAPPED make -C "${CRATE}" "$@"
}

# cargo-mutants kills a timed-out test, so its TempDir never drops; /tmp is tmpfs (RAM).
# Both recipes must point TMPDIR at the crate's own target dir and remove it on exit.
_tmpdir_run() {
    local recipe="$1"
    _rs_stub_setup
    OUTER="${BATS_TEST_TMPDIR}/outer"
    mkdir -p "${OUTER}"
    printf 'diff\n' > "${BATS_TEST_TMPDIR}/pr.diff"
    local args=("${recipe}")
    [ "${recipe}" = "mutants-diff" ] && args+=("DIFF=${BATS_TEST_TMPDIR}/pr.diff")
    TMPDIR="${OUTER}" run _rs_make "${args[@]}"
}

# A CI cancel signals the whole group more than once; the second TERM must not kill the cleanup rm.
@test "make mutants removes target/mutants-tmp when the whole process group gets SIGTERM twice" {
    _rs_stub_setup
    STUB_CARGO_HANG=1 STUB_RM_SLOW=1 _term_group_twice "${CRATE}" mutants
    [ -s "${BATS_TEST_TMPDIR}/rm-log" ]
    [ ! -e "${CRATE}/target/mutants-tmp" ]
}

@test "make mutants-diff removes target/mutants-tmp when the whole process group gets SIGTERM twice" {
    _rs_stub_setup
    printf 'diff\n' > "${BATS_TEST_TMPDIR}/pr.diff"
    STUB_CARGO_HANG=1 STUB_RM_SLOW=1 _term_group_twice "${CRATE}" mutants-diff "DIFF=${BATS_TEST_TMPDIR}/pr.diff"
    [ -s "${BATS_TEST_TMPDIR}/rm-log" ]
    [ ! -e "${CRATE}/target/mutants-tmp" ]
}

@test "make mutants runs cargo with TMPDIR under the crate's target dir" {
    _tmpdir_run mutants
    [ "${status}" -eq 0 ]
    grep -qxF "tmpdir ${CRATE}/target/mutants-tmp" "${CALLS}"
    _assert_no_call "^tmpdir-missing$"
}

@test "make mutants caps any single file at 256 MiB" {
    _tmpdir_run mutants
    [ "${status}" -eq 0 ]
    grep -qxF "fsize=262144" "${CALLS}"
}

@test "make mutants caps file size even with MUTANTS_UNCAPPED set" {
    _rs_stub_setup
    printf 'diff\n' > "${BATS_TEST_TMPDIR}/pr.diff"
    MUTANTS_UNCAPPED=1 run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS make -C "${CRATE}" mutants
    [ "${status}" -eq 0 ]
    grep -qxF "fsize=262144" "${CALLS}"
}

# MUTANTS_UNCAPPED=1 skips only the memory cap: cargo must inherit this shell's own `ulimit -v`
# (not 8 GiB), the operator must be warned, and the file-size cap must stay.
@test "make mutants with MUTANTS_UNCAPPED leaves the memory cap off, warns, and keeps the file cap" {
    _rs_stub_setup
    local parent_v
    parent_v="$(ulimit -v)"
    MUTANTS_UNCAPPED=1 run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS make -C "${CRATE}" mutants
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"warning: MUTANTS_UNCAPPED set"* ]]
    grep -qE "^cargo mutants .* ulimit=${parent_v}$" "${CALLS}"
    _assert_no_call "ulimit=8388608"
    grep -qxF "fsize=262144" "${CALLS}"
}

@test "make mutants-diff with MUTANTS_UNCAPPED leaves the memory cap off, warns, and keeps the file cap" {
    _rs_stub_setup
    local parent_v
    parent_v="$(ulimit -v)"
    printf 'diff\n' > "${BATS_TEST_TMPDIR}/pr.diff"
    MUTANTS_UNCAPPED=1 run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS make -C "${CRATE}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"warning: MUTANTS_UNCAPPED set"* ]]
    grep -qE "^cargo mutants .* ulimit=${parent_v}$" "${CALLS}"
    _assert_no_call "ulimit=8388608"
    grep -qxF "fsize=262144" "${CALLS}"
}

@test "make mutants-diff runs cargo with TMPDIR under the crate's target dir" {
    _tmpdir_run mutants-diff
    [ "${status}" -eq 0 ]
    grep -qxF "tmpdir ${CRATE}/target/mutants-tmp" "${CALLS}"
    _assert_no_call "^tmpdir-missing$"
}

@test "make mutants-diff caps any single file at 256 MiB" {
    _tmpdir_run mutants-diff
    [ "${status}" -eq 0 ]
    grep -qxF "fsize=262144" "${CALLS}"
}

@test "make mutants-diff caps file size even with MUTANTS_UNCAPPED set" {
    _rs_stub_setup
    printf 'diff\n' > "${BATS_TEST_TMPDIR}/pr.diff"
    MUTANTS_UNCAPPED=1 run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS make -C "${CRATE}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -eq 0 ]
    grep -qxF "fsize=262144" "${CALLS}"
}

@test "make mutants removes target/mutants-tmp and leaves the caller's TMPDIR empty" {
    _tmpdir_run mutants
    [ "${status}" -eq 0 ]
    [ ! -e "${CRATE}/target/mutants-tmp" ]
    [ -z "$(ls -A "${OUTER}")" ]
}

@test "make mutants-diff removes target/mutants-tmp and leaves the caller's TMPDIR empty" {
    _tmpdir_run mutants-diff
    [ "${status}" -eq 0 ]
    [ ! -e "${CRATE}/target/mutants-tmp" ]
    [ -z "$(ls -A "${OUTER}")" ]
}

@test "make mutants cleans target/mutants-tmp and still propagates cargo's exit code 3" {
    _rs_stub_setup
    STUB_CARGO_RC=3 run _rs_make mutants
    [ "${status}" -ne 0 ]
    [ "$(cat "${CRATE}/mutants.out/exit-code")" = "3" ]
    [ ! -e "${CRATE}/target/mutants-tmp" ]
}

@test "make mutants-diff cleans target/mutants-tmp and still propagates cargo's exit code 3" {
    _rs_stub_setup
    printf 'diff\n' > "${BATS_TEST_TMPDIR}/pr.diff"
    STUB_CARGO_RC=3 run _rs_make mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -ne 0 ]
    [ "$(cat "${CRATE}/mutants.out/exit-code")" = "3" ]
    [ ! -e "${CRATE}/target/mutants-tmp" ]
}

@test "make mutants runs cargo with no core dumps" {
    _rs_stub_setup
    _raise_core_limit
    run _rs_make mutants
    [ "${status}" -eq 0 ]
    _assert_cores_disabled "${CALLS}"
}

@test "make mutants runs cargo with no core dumps even with MUTANTS_UNCAPPED set" {
    _rs_stub_setup
    _raise_core_limit
    MUTANTS_UNCAPPED=1 run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS make -C "${CRATE}" mutants
    [ "${status}" -eq 0 ]
    _assert_cores_disabled "${CALLS}"
}

@test "make mutants-diff runs cargo with no core dumps" {
    _rs_stub_setup
    _raise_core_limit
    printf 'diff\n' > "${BATS_TEST_TMPDIR}/pr.diff"
    run _rs_make mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -eq 0 ]
    _assert_cores_disabled "${CALLS}"
}

@test "make mutants-diff runs cargo with no core dumps even with MUTANTS_UNCAPPED set" {
    _rs_stub_setup
    _raise_core_limit
    printf 'diff\n' > "${BATS_TEST_TMPDIR}/pr.diff"
    MUTANTS_UNCAPPED=1 run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS make -C "${CRATE}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -eq 0 ]
    _assert_cores_disabled "${CALLS}"
}

@test "make mutants clears a stale target/mutants-tmp left by a killed run" {
    _rs_stub_setup
    mkdir -p "${CRATE}/target/mutants-tmp/old"
    run _rs_make mutants
    [ "${status}" -eq 0 ]
    [ ! -e "${CRATE}/target/mutants-tmp" ]
    _assert_no_call "^stale$"
}

@test "make mutants-diff clears a stale target/mutants-tmp left by a killed run" {
    _rs_stub_setup
    printf 'diff\n' > "${BATS_TEST_TMPDIR}/pr.diff"
    mkdir -p "${CRATE}/target/mutants-tmp/old"
    run _rs_make mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -eq 0 ]
    [ ! -e "${CRATE}/target/mutants-tmp" ]
    _assert_no_call "^stale$"
}

@test "make mutants records cargo's exit code in mutants.out/exit-code and propagates it" {
    _rs_stub_setup
    STUB_CARGO_RC=4 run _rs_make mutants
    [ "${status}" -ne 0 ]
    [ "$(cat "${CRATE}/mutants.out/exit-code")" = "4" ]
}

@test "make mutants with cargo exit 0 writes 0 and succeeds" {
    _rs_stub_setup
    STUB_CARGO_RC=0 run _rs_make mutants
    [ "${status}" -eq 0 ]
    [ "$(cat "${CRATE}/mutants.out/exit-code")" = "0" ]
}

@test "make mutants runs cargo mutants with the scaled timeout under the 8 GiB cap" {
    _rs_stub_setup
    run _rs_make mutants
    [ "${status}" -eq 0 ]
    grep -qF 'cargo mutants --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle ulimit=8388608' "${CALLS}"
    ! command grep -q -- '--in-diff' "${CALLS}"
}

@test "make mutants-diff passes --in-diff and records the exit code" {
    _rs_stub_setup
    printf 'diff\n' > "${BATS_TEST_TMPDIR}/pr.diff"
    STUB_CARGO_RC=4 run _rs_make mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -ne 0 ]
    [ "$(cat "${CRATE}/mutants.out/exit-code")" = "4" ]
    grep -qF "cargo mutants --in-diff ${BATS_TEST_TMPDIR}/pr.diff --timeout-multiplier 5 --minimum-test-timeout 30 --no-shuffle ulimit=8388608" "${CALLS}"
}

@test "make mutants-diff with cargo exit 0 writes 0 and succeeds" {
    _rs_stub_setup
    printf 'diff\n' > "${BATS_TEST_TMPDIR}/pr.diff"
    STUB_CARGO_RC=0 run _rs_make mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -eq 0 ]
    [ "$(cat "${CRATE}/mutants.out/exit-code")" = "0" ]
}

@test "stale mutants.out is removed before the run" {
    _rs_stub_setup
    mkdir -p "${CRATE}/mutants.out"
    printf 'STALE\n' > "${CRATE}/mutants.out/outcomes.json"
    run _rs_make mutants
    [ "${status}" -eq 0 ]
    [ ! -e "${CRATE}/mutants.out/outcomes.json" ]
}

@test "stale mutants.out is removed before a mutants-diff run" {
    _rs_stub_setup
    printf 'diff\n' > "${BATS_TEST_TMPDIR}/pr.diff"
    mkdir -p "${CRATE}/mutants.out"
    printf 'STALE\n' > "${CRATE}/mutants.out/outcomes.json"
    run _rs_make mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -eq 0 ]
    [ ! -e "${CRATE}/mutants.out/outcomes.json" ]
}

@test "a fresh outcomes.json written by cargo survives the exit-code write" {
    _rs_stub_setup
    STUB_CARGO_WRITE=1 run _rs_make mutants
    [ "${status}" -eq 0 ]
    [ "$(cat "${CRATE}/mutants.out/outcomes.json")" = "NEW" ]
}

@test "make mutants-diff without DIFF exits non-zero naming DIFF and never calls cargo" {
    _rs_stub_setup
    run _rs_make mutants-diff
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"DIFF"* ]]
    [[ "${output}" == *"Error 2"* ]]
    [ ! -s "${CALLS}" ]
    [ ! -e "${CRATE}/mutants.out" ]
}

@test "make mutants-diff with a nonexistent DIFF exits non-zero naming DIFF and never calls cargo" {
    _rs_stub_setup
    run _rs_make mutants-diff DIFF=/nonexistent/pr.diff
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"DIFF"* ]]
    [[ "${output}" == *"Error 2"* ]]
    [ ! -s "${CALLS}" ]
}

@test "make mutants-diff with a directory as DIFF is refused without calling cargo" {
    _rs_stub_setup
    run _rs_make mutants-diff DIFF="${BATS_TEST_TMPDIR}"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"DIFF"* ]]
    [[ "${output}" == *"Error 2"* ]]
    [ ! -s "${CALLS}" ]
}

@test "make mutants-diff passes a DIFF path with a space and a quote to cargo as one argument" {
    _rs_stub_setup
    local odd="${BATS_TEST_TMPDIR}/it's a.diff"
    printf 'diff\n' > "${odd}"
    run _rs_make mutants-diff DIFF="${odd}"
    [ "${status}" -eq 0 ]
    # The argument right after --in-diff must be the whole odd path.
    run command grep -xF -A1 -- 'arg --in-diff' "${CALLS}.args"
    [ "${status}" -eq 0 ]
    [ "${lines[1]}" = "arg ${odd}" ]
}

@test "make mutants fails closed when the memory cap cannot be enforced" {
    _rs_stub_setup
    # A limit below the 8 GiB cap makes `ulimit -v 8388608` fail, as on macOS.
    run bash -c 'ulimit -v 1000000 && env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS -u MUTANTS_UNCAPPED make -C "$1" mutants' _ "${CRATE}"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"cannot enforce a memory cap"* ]]
    [ ! -s "${CALLS}" ]
    [ ! -e "${CRATE}/mutants.out/exit-code" ]
}

@test "make mutants-diff fails closed when the memory cap cannot be enforced" {
    _rs_stub_setup
    printf 'diff\n' > "${BATS_TEST_TMPDIR}/pr.diff"
    run bash -c 'ulimit -v 1000000 && env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS -u MUTANTS_UNCAPPED make -C "$1" mutants-diff DIFF="$2"' _ "${CRATE}" "${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"cannot enforce a memory cap"* ]]
    [ ! -s "${CALLS}" ]
    [ ! -e "${CRATE}/mutants.out/exit-code" ]
}

# install-deps must invoke pip through `python3 -m pip`, never a bare `pip` --
# measured, bare `pip` resolves to an unrelated pyenv environment on the Mac
# Studio, so a bare `pip install` can exit 0 while `make test-python` still
# raises ModuleNotFoundError (ci.md/shell.md PATH-resolution class).
@test "install-deps recipe uses python3 -m pip install" {
    run make -C "${REPO_ROOT}" -n install-deps --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"python3 -m pip install -r requirements-dev.txt"* ]]
}

# A plain substring check for "pip install" would also match inside
# "python3 -m pip install", so it can't discriminate a bare invocation from a
# correct one. Strip every correct occurrence first, then apply the idiom
# from the "lint-python skips" test above to the remainder.
@test "install-deps recipe contains no bare pip install" {
    run make -C "${REPO_ROOT}" -n install-deps --no-print-directory
    [ "${status}" -eq 0 ]
    local stripped="${output//python3 -m pip install/}"
    [[ "${stripped}" != *"pip install"* ]]
}

# pip's own check_externally_managed() returns early -- skipping the marker
# check entirely -- when sys.prefix != sys.base_prefix (i.e. running under a
# virtualenv). A predicate that checks only the marker refuses identically
# inside and outside a venv, which is a dead end: the guard's own remedy
# ("create a venv") does not change its verdict. A byte pin here (grep -F
# over the predicate text) asserts spelling, not behaviour: reordering the
# conjuncts or reflowing whitespace turns it red with identical semantics,
# and reverting to a marker-only predicate (dropping the venv term -- the
# exact bug this fixes) leaves it green, because the two stub tests below
# only vary python3's exit code and cannot distinguish the two predicates.
#
# So this extracts the `-c` argument VERBATIM from the Makefile (anchored to
# a tab-indented, `@`-led recipe line -- not merely to the "python3 -c"
# substring anywhere in the file, which a comment line (tab + `#`, never
# tab + `@`) cannot satisfy) and
# executes it with sys.prefix/sys.base_prefix and the EXTERNALLY-MANAGED
# marker monkeypatched, reproducing all four (in_venv, marker) combinations.
# Measured on this machine (Python 3.14, Mac Studio) by extracting the same
# `-c` body and monkeypatching the same two inputs:
#   in_venv=no  marker=yes -> rc=1 (refuse, matches pip)
#   in_venv=no  marker=no  -> rc=0
#   in_venv=yes marker=yes -> rc=0 (the case the venv term exists for)
#   in_venv=yes marker=no  -> rc=0
@test "install-deps predicate matches pip's four (venv, marker) outcomes" {
    local code
    if ! code="$(python3 - "${REPO_ROOT}/Makefile" <<'PYEOF'
import re
import sys

text = open(sys.argv[1]).read()
m = re.search(r"^\t@.*?python3 -c '([^']*)'", text, re.MULTILINE)
if not m:
    sys.exit(1)
print(m.group(1))
PYEOF
    )"; then
        printf 'no anchored tab-indented @python3 -c recipe line found in Makefile\n' >&2
        return 1
    fi
    [ -n "${code}" ]

    local driver="${BATS_TEST_TMPDIR}/predicate_driver.py"
    cat > "${driver}" <<'DRIVER'
import os
import sys
import sysconfig
import tempfile

in_venv = sys.argv[1] == "1"
marker = sys.argv[2] == "1"
code = sys.argv[3]

stdlib_dir = tempfile.mkdtemp()
sysconfig.get_path = lambda *_a, **_kw: stdlib_dir
sys.base_prefix = "/base-prefix"
sys.prefix = "/venv-prefix" if in_venv else "/base-prefix"
if marker:
    open(os.path.join(stdlib_dir, "EXTERNALLY-MANAGED"), "w").close()

exec(code)
DRIVER

    local combos=("0 1 1" "0 0 0" "1 1 0" "1 0 0")
    local combo in_venv marker expected
    for combo in "${combos[@]}"; do
        read -r in_venv marker expected <<< "${combo}"
        run python3 "${driver}" "${in_venv}" "${marker}" "${code}"
        if [ "${status}" -ne "${expected}" ]; then
            printf 'in_venv=%s marker=%s: expected rc=%s, got rc=%s\n' \
                "${in_venv}" "${marker}" "${expected}" "${status}" >&2
            return 1
        fi
    done
}

# `make -n` PRINTS the recipe without ever EXECUTING it, so a test built on
# it cannot tell a working guard from a deleted or inverted one. These two
# tests stub `python3` and actually run the recipe, asserting on the branch
# actually taken. The stub lives in its own BATS_TEST_TMPDIR directory and is
# prepended to PATH only for the duration of this one test -- adding it to
# tests/mocks/ would shadow python3 for the whole suite (see shell.md, "A
# PATH mock shadows the binary your production code needs").
#
# This is the structural guard against the actual regression shell.md names
# (an absolute path such as `/usr/bin/python3` hardcoded into the recipe): a
# runtime `command -v python3` check cannot catch it, because PATH
# resolution is unaffected by what the recipe's own command words are -- a
# hardcoded absolute path bypasses PATH lookup entirely, stub or no stub. A
# static check on the recipe body, run once, closes it for every test below
# rather than depending on each one to notice at runtime.
@test "install-deps recipe invokes python3 via PATH, never a hardcoded path" {
    local recipe
    recipe="$(awk '/^install-deps:/{f=1; next} /^[A-Za-z_.-]+:/{if(f){exit}} f' "${REPO_ROOT}/Makefile")"
    [ -n "${recipe}" ]
    [[ "${recipe}" != *"/python3"* ]]
}

# The positive control right after the PATH override is load-bearing, not
# defensive noise (tdd.md E2, "a test's failure mode must be inert"): without
# it, a regression that makes the STUB unreachable via PATH -- a typo in
# stub_dir, a PATH restore that runs too early, another python3 earlier on
# PATH winning the lookup -- does not merely fail the assertions below, it
# runs a REAL `pip install` into whatever python3 actually resolves, outside
# this repo, before the test ever gets to fail. This happened during review
# of the prior round: a probe wrote defusedxml and PyYAML into a live pyenv
# environment's site-packages. It does NOT, on its own, catch a hardcoded
# absolute path inside the Makefile recipe -- that class is what the test
# above guards, structurally, before either stub test ever runs.
# PIP_NO_INDEX/PIP_REQUIRE_VIRTUALENV are the belt-and-braces layer under
# BOTH: even if a bypass reaches a real interpreter, PIP_NO_INDEX=1 makes a
# real network install unreachable (verified: even `pip install
# --force-reinstall` under PIP_NO_INDEX=1 fails cleanly with "Could not find
# a version ... from versions: none" and touches nothing on disk).
# PIP_REQUIRE_VIRTUALENV=1 is NOT reliable on every machine -- verified: it
# is a no-op whenever VIRTUAL_ENV is already set in the invoking shell (this
# machine's session shell has one active), since pip's own check considers
# that "already in a virtualenv". PIP_NO_INDEX is the layer both stub tests
# actually depend on.
@test "install-deps refuses and never reaches pip when the marker check fails" {
    local stub_dir="${BATS_TEST_TMPDIR}/stub-marker-present"
    mkdir -p "${stub_dir}"
    cat > "${stub_dir}/python3" <<'STUB'
#!/usr/bin/env bash
[[ "$1" == "-c" ]] && exit 1
exit 0
STUB
    chmod +x "${stub_dir}/python3"

    local old_path="${PATH}"
    PATH="${stub_dir}:${PATH}"
    [ "$(command -v python3)" = "${stub_dir}/python3" ]
    PIP_NO_INDEX=1 PIP_REQUIRE_VIRTUALENV=1 run make -C "${REPO_ROOT}" install-deps
    PATH="${old_path}"

    [ "${status}" -ne 0 ]
    [[ "${output}" == *"externally managed"* ]]
    [[ "${output}" != *"pip install"* ]]
}

@test "install-deps proceeds to pip install when the marker check passes" {
    local stub_dir="${BATS_TEST_TMPDIR}/stub-marker-absent"
    local call_log="${BATS_TEST_TMPDIR}/pip-calls.log"
    mkdir -p "${stub_dir}"
    cat > "${stub_dir}/python3" <<STUB
#!/usr/bin/env bash
if [[ "\$1" == "-c" ]]; then
    exit 0
fi
if [[ "\$1" == "-m" && "\$2" == "pip" ]]; then
    printf '%s\n' "\$*" >> "${call_log}"
    exit 0
fi
exit 0
STUB
    chmod +x "${stub_dir}/python3"

    # The recipe's last step installs actionlint. A fixture XDG_BIN_HOME already
    # holding a 1.7.12 binary makes that a no-op: no network, no real ~/.local/bin.
    local fixture_bin="${BATS_TEST_TMPDIR}/xdg-bin"
    mkdir -p "${fixture_bin}"
    printf '#!/bin/sh\nprintf "1.7.12\\n"\n' > "${fixture_bin}/actionlint"
    chmod +x "${fixture_bin}/actionlint"

    local old_path="${PATH}"
    PATH="${stub_dir}:${PATH}"
    [ "$(command -v python3)" = "${stub_dir}/python3" ]
    HOME="${BATS_TEST_TMPDIR}" XDG_BIN_HOME="${fixture_bin}" \
        PIP_NO_INDEX=1 PIP_REQUIRE_VIRTUALENV=1 run make -C "${REPO_ROOT}" install-deps
    PATH="${old_path}"

    [ "${status}" -eq 0 ]
    [ -f "${call_log}" ]
    grep -q 'requirements-dev.txt' "${call_log}"
    [[ "${output}" == *"actionlint 1.7.12 already installed in ${fixture_bin}"* ]]
}

# Installer-failure fixture: pip stub succeeds, curl always fails, empty bin dir.
install_deps_with_failing_installer() {
    local stub_dir="${BATS_TEST_TMPDIR}/stub-failing-installer"
    mkdir -p "${stub_dir}" "${BATS_TEST_TMPDIR}/empty-bin"
    printf '#!/usr/bin/env bash\nexit 0\n' > "${stub_dir}/python3"
    printf '#!/usr/bin/env bash\nexit 22\n' > "${stub_dir}/curl"
    chmod +x "${stub_dir}/python3" "${stub_dir}/curl"

    local old_path="${PATH}"
    PATH="${stub_dir}:${PATH}"
    HOME="${BATS_TEST_TMPDIR}" XDG_BIN_HOME="${BATS_TEST_TMPDIR}/empty-bin" \
        PIP_NO_INDEX=1 PIP_REQUIRE_VIRTUALENV=1 run make -C "${REPO_ROOT}" install-deps
    PATH="${old_path}"
}

@test "install-deps: actionlint installer failure only warns outside CI" {
    unset CI
    install_deps_with_failing_installer
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"warning: actionlint not installed"* ]]
    [ ! -e "${BATS_TEST_TMPDIR}/empty-bin/actionlint" ]
}

@test "install-deps: actionlint installer failure is fatal when CI=true" {
    export CI=true
    install_deps_with_failing_installer
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"download failed"* ]]
}

@test "install-deps installs actionlint after the pip install" {
    run make -C "${REPO_ROOT}" -n install-deps --no-print-directory
    [ "${status}" -eq 0 ]
    local before="${output%%scripts/install-actionlint.sh*}"
    [[ "${output}" == *"scripts/install-actionlint.sh"* ]]
    [[ "${before}" == *"pip install -r requirements-dev.txt"* ]]
}

# The discriminator the Makefile comment above install-deps documents:
# python3's exit code is 1 both for the predicate's deliberate
# `raise SystemExit(1)` AND for any uncaught exception (verified: ImportError,
# ValueError and a syntax error all exit 1), so this stub's `-c` branch
# writes a traceback to stderr before exiting 1 -- the actual signal that
# distinguishes "the marker check refused" from "the probe itself is
# broken". Without the stderr split, this would misreport an unrelated
# breakage as "python3 is externally managed", sending the reader after a
# venv for a fault that has nothing to do with PEP 668.
@test "install-deps names the probe itself as the failure when it dies for an unrelated reason" {
    local stub_dir="${BATS_TEST_TMPDIR}/stub-marker-broken"
    mkdir -p "${stub_dir}"
    cat > "${stub_dir}/python3" <<'STUB'
#!/usr/bin/env bash
if [[ "$1" == "-c" ]]; then
    echo "Traceback (most recent call last):" >&2
    echo "ModuleNotFoundError: No module named 'sysconfig'" >&2
    exit 1
fi
exit 0
STUB
    chmod +x "${stub_dir}/python3"

    local old_path="${PATH}"
    PATH="${stub_dir}:${PATH}"
    [ "$(command -v python3)" = "${stub_dir}/python3" ]
    PIP_NO_INDEX=1 PIP_REQUIRE_VIRTUALENV=1 run make -C "${REPO_ROOT}" install-deps
    PATH="${old_path}"

    [ "${status}" -ne 0 ]
    [[ "${output}" == *"the PEP 668 probe itself failed"* ]]
    [[ "${output}" != *"externally managed"* ]]
    [[ "${output}" != *"pip install"* ]]
}

# The failing branch here has no E2 exposure at all: with no python3
# reachable, the pip line is structurally unreachable, so there is nothing
# for a regressed guard to install for real. PATH is not replaced wholesale
# PATH is neither replaced wholesale nor scrubbed by dropping python3-bearing
# entries. Both fail, for opposite reasons:
#
#   empty PATH        -> `make` itself is unresolvable, exit 127, recipe never runs
#   drop python3 dirs -> works on macOS, FAILS on Linux. Measured: this box has
#                        python3 at ~/.pyenv/shims and make at Homebrew's gnubin,
#                        different directories; ubuntu-latest has BOTH at
#                        /usr/bin, so dropping python3's directory drops make too
#                        and the recipe again never runs (exit 127).
#
# The scrub form shipped first and passed locally on exactly that difference --
# tdd.md pitfall G, caught by CI on this branch, not by review. Instead: a shim
# directory holding only a `make` symlink. `make` resolves, `python3` does not,
# and the answer is identical on both platforms because it depends on nothing
# about where either binary lives.
@test "install-deps names python3 absence separately from the marker message" {
    local shim
    shim="${BATS_TEST_TMPDIR}/nopy"
    mkdir -p "${shim}"
    ln -s "$(command -v make)" "${shim}/make"

    PATH="${shim}" run make -C "${REPO_ROOT}" install-deps

    [ "${status}" -ne 0 ]
    [[ "${output}" == *"python3 not found on PATH"* ]]
    [[ "${output}" != *"externally managed"* ]]
}

# A two-count comparison (pinned-lines vs total-lines) has false passes AND
# false fails an added entry cannot be relied on to trip: an indented
# unpinned line (`  pyright`) is invisible to BOTH the total-lines regex
# (which requires a non-whitespace first character) and the pinned-lines
# regex, so the ratio cannot move -- the exact Coverage Denominators failure
# from tdd.md, reintroduced by the fix for a different denominator bug. And
# `pyright[nodejs]==1.1.0` (extras), `-r other.txt` / `--index-url ...` (pip
# directives), and `pyright ==1.1.0` (PEP 508 permits whitespace around ==)
# are all legitimate, non-broken lines that a naive "starts with a name,
# then ==, then a digit" regex would misclassify.
#
# A one-sided predicate -- name what's wrong, rather than compare two counts
# that must independently agree -- doesn't have this shape. Comments and
# blank lines are stripped first; directive lines (leading `-`) are exempt
# from the == requirement; PEP 508 whitespace and extras are tolerated by
# not anchoring the == check to the start of the line.
@test "requirements-dev.txt has no entry that fails the == pin check" {
    [ -s "${REPO_ROOT}/requirements-dev.txt" ]

    # The trailing `|| true` is not swallowing a real failure: grep -v
    # exits 1 when NOTHING matches, which here is the expected passing case
    # (no bad lines) -- without it, that exit code would abort the bats body
    # (errexit-like) at this assignment, reporting a grep failure instead of
    # the actual (passing) result. Verified against all documented cases plus
    # the real file.
    local bad
    bad="$(sed -E 's/[[:space:]]*#.*$//; s/^[[:space:]]+//; s/[[:space:]]+$//' "${REPO_ROOT}/requirements-dev.txt" \
          | grep -vE '^$' | grep -vE '^-' | grep -vE '==[[:space:]]*[0-9]' || true)"
    [ -z "${bad}" ]
}

# Every Python program writes its output as <dir>_*.txt (perfect-numbers uses
# the directory name, not the module), so the rendered clean target removes
# that glob and nothing else.
@test "Python make clean removes the program's output files and keeps others" {
    local p d f projects=()
    # Derive the Python sub-projects: dirs tracking <dir>/<dir with - as _>.py and a Makefile.
    while IFS= read -r f; do
        p="${f%%/*}"
        [[ "${f}" == "${p}/${p//-/_}.py" ]] || continue
        env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git -C "${REPO_ROOT}" ls-files --error-unmatch "${p}/Makefile" > /dev/null 2>&1 || continue
        projects+=("${p}")
    done < <(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git -C "${REPO_ROOT}" ls-files '*/*.py')
    [ "${#projects[@]}" -eq 9 ]
    for p in "${projects[@]}"; do
        d="${BATS_TEST_TMPDIR}/${p}"
        mkdir -p "${d}"
        cp "${REPO_ROOT}/${p}/Makefile" "${d}/Makefile"
        touch "${d}/${p}_1e3.txt" "${d}/${p}_1000_digits.txt" "${d}/notes.txt"
        run make -C "${d}" clean --no-print-directory
        [ "${status}" -eq 0 ]
        [ ! -e "${d}/${p}_1e3.txt" ]
        [ ! -e "${d}/${p}_1000_digits.txt" ]
        [ -e "${d}/notes.txt" ]
    done
}

# test-rust: the real make runs the root target; PATH is then shadowed by the make
# mock alone (not load_mocks, whose git mock would empty the derived crate list) so
# the sub-makes parallel-make-test.sh starts are recorded, not executed.
setup_test_rust() {
    REAL_MAKE="$(command -v make)"
    mkdir -p "${BATS_TEST_TMPDIR}/bin"
    ln -s "${REPO_ROOT}/tests/mocks/make" "${BATS_TEST_TMPDIR}/bin/make"
    export PATH="${BATS_TEST_TMPDIR}/bin:${PATH}"
    export MOCK_CALLS_FILE="${BATS_TEST_TMPDIR}/calls"
    : > "${MOCK_CALLS_FILE}"
    EXPECTED_DIRS="$(env -u GIT_DIR -u GIT_WORK_TREE -u GIT_COMMON_DIR -u GIT_INDEX_FILE git -C "${REPO_ROOT}" ls-files '*/*-rs/Makefile' | sed 's|/Makefile$||')"
}

@test "make test-rust runs make test once in each of the 11 Rust crates" {
    setup_test_rust
    [ "$(printf '%s\n' "${EXPECTED_DIRS}" | wc -l)" -eq 11 ]
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS -u JOBS "${REAL_MAKE}" -C "${REPO_ROOT}" test-rust JOBS=3 --no-print-directory
    [ "${status}" -eq 0 ]
    # GNU make's $(CURDIR) is the physical path (macOS /var -> /private/var), while
    # REPO_ROOT is the logical one, so the expected calls use the physical root.
    local dir root
    root="$(cd "${REPO_ROOT}" && pwd -P)"
    for dir in ${EXPECTED_DIRS}; do
        [ "$(grep -cxF "make -C ${root}/${dir} test" "${MOCK_CALLS_FILE}")" -eq 1 ]
        [[ "${output}" == *"ok ${dir}"* ]]
    done
    [ "$(grep -c '^make -C ' "${MOCK_CALLS_FILE}")" -eq 11 ]
}

@test "make test-rust fails and names the crate when one crate's tests fail" {
    setup_test_rust
    export MOCK_MAKE_FAIL_DIR=fib/fib-rs
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS -u JOBS "${REAL_MAKE}" -C "${REPO_ROOT}" test-rust JOBS=3 --no-print-directory
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"FAIL fib/fib-rs"* ]]
}

@test "make test-rust refuses an empty crate list with a message" {
    setup_test_rust
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS -u JOBS "${REAL_MAKE}" -C "${REPO_ROOT}" test-rust RUST_CRATE_DIRS= --no-print-directory
    # make reports a failed recipe as its own exit 2; the guard's exit 1 is the cause.
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"no Rust crates found"* ]]
    [ ! -s "${MOCK_CALLS_FILE}" ]
}

@test "make test-rust derives the crate list even with a decoy GIT_DIR exported" {
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS -u JOBS GIT_DIR=/nonexistent make -C "${REPO_ROOT}" -n test-rust --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"twin-primes/twin-primes-rs"* ]]
    [ "$(printf '%s\n' "${output}" | grep -o '[a-z-]*/[a-z-]*-rs' | sort -u | wc -l)" -eq 11 ]
}

# The concurrency probe in the make mock records, per call, how many calls were live
# at once. JOBS=1 must never overlap; JOBS=3 over 11 crates must overlap at least once.
# Together they pin that `make test-rust JOBS=N` reaches the runner in both directions.
run_test_rust_with_probe() {
    local jobs="$1"
    setup_test_rust
    PROBE_DIR="${BATS_TEST_TMPDIR}/probe"
    mkdir -p "${PROBE_DIR}"
    export MOCK_MAKE_CONCURRENCY_DIR="${PROBE_DIR}"
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS -u JOBS "${REAL_MAKE}" -C "${REPO_ROOT}" test-rust JOBS="${jobs}" --no-print-directory
    [ "${status}" -eq 0 ]
    local seen=("${PROBE_DIR}"/seen.*)
    [ "${#seen[@]}" -eq 11 ]
    PROBE_MAX=0
    local f v
    for f in "${seen[@]}"; do
        v="$(cat "${f}")"
        if [ "${v}" -gt "${PROBE_MAX}" ]; then PROBE_MAX="${v}"; fi
    done
}

@test "make test-rust JOBS=1 never runs two crate suites at once" {
    run_test_rust_with_probe 1
    [ "${PROBE_MAX}" -eq 1 ]
}

@test "make test-rust JOBS=3 runs crate suites concurrently" {
    run_test_rust_with_probe 3
    [ "${PROBE_MAX}" -gt 1 ]
}

# The Python mutants recipe: baseline first, memory cap, optional shard, cell status last.
# PATH is stripped of tests/mocks for `git ls-files` for the same reason as the Rust test above.
_py_mutants_makefiles() {
    local _clean_path mf
    _clean_path="$(printf '%s' "${PATH}" | tr ':' '\n' | grep -v 'tests/mocks' | tr '\n' ':' | sed 's/:$//')"
    while IFS= read -r mf; do
        [[ -z "${mf}" ]] && continue
        # Rendered copies are one level deep; the template sits under scripts/.
        [[ "${mf}" == */*/* ]] && continue
        [[ -f "${REPO_ROOT}/$(dirname "${mf}")/cosmic-ray.toml" ]] && printf '%s\n' "${mf}"
    done < <(cd "${REPO_ROOT}" && PATH="${_clean_path}" command git ls-files '*/Makefile')
}

# Prints the mutants recipe (target line plus its tab-indented continuation) of a Makefile.
_py_mutants_recipe() {
    awk '/^mutants:/ {on=1; print; next} on && /^\t/ {print; next} on {exit}' "$1"
}

# Line number of the first recipe line matching an ERE, or empty.
_py_recipe_line() {
    printf '%s\n' "$1" | grep -nE -- "$2" | head -1 | cut -d: -f1
}

@test "exactly 9 Python Makefiles carry a cosmic-ray.toml" {
    local count
    count="$(_py_mutants_makefiles | wc -l)"
    [ "${count}" -eq 9 ]
}

@test "every Python mutants-baseline falls back to the module's unittest on failure" {
    local mf mod bad="" n=0
    while IFS= read -r mf; do
        n=$((n + 1))
        mod="$(sed -n 's/^\tpython3 \([a-z_]*\)\.py$/\1/p' "${REPO_ROOT}/${mf}" | head -1)"
        [ -n "${mod}" ] || { bad="${bad}${mf}(no module) "; continue; }
        grep -qE '^mutants-baseline:' "${REPO_ROOT}/${mf}" || bad="${bad}${mf}(no mutants-baseline) "
        grep -qF "cosmic-ray baseline cosmic-ray.toml || { python3 -m unittest test_${mod}; exit 1; }" "${REPO_ROOT}/${mf}" \
            || bad="${bad}${mf}(no unittest fallback) "
        grep -qE '^\.PHONY:.* mutants-baseline( |$)' "${REPO_ROOT}/${mf}" || bad="${bad}${mf}(not PHONY) "
        grep -qE '^CELL_LABEL \?= ' "${REPO_ROOT}/${mf}" || bad="${bad}${mf}(no CELL_LABEL) "
    done < <(_py_mutants_makefiles)
    [ "${n}" -eq 9 ]
    [ -z "${bad}" ] || { printf 'baseline problems: %s\n' "${bad}" >&2; return 1; }
}

# Behavioural harness: a real copy of fib's rendered Makefile plus stubs on PATH that log
# their argv to ${CALLS}. python3 stands in for both ../scripts/ helpers; exit codes come from
# STUB_EXEC_RC, STUB_STATUS_RC and STUB_SHARD_RC. cosmic-ray records the address-space limit it
# runs under so the memory cap is observed, not read from the text.
_py_stub_setup() {
    CALLS="${BATS_TEST_TMPDIR}/calls"
    : > "${CALLS}"
    STUBDIR="${BATS_TEST_TMPDIR}/fib"
    local bin="${BATS_TEST_TMPDIR}/bin"
    mkdir -p "${STUBDIR}" "${bin}"
    cp "${REPO_ROOT}/fib/Makefile" "${STUBDIR}/Makefile"
    mkdir -p "${BATS_TEST_TMPDIR}/scripts"
    : > "${BATS_TEST_TMPDIR}/scripts/cosmic_ray_shard.py"
    : > "${BATS_TEST_TMPDIR}/scripts/cosmic_ray_cell_status.py"
    printf 'ORIGINAL\n' > "${STUBDIR}/fib.py"
    printf 'TEST\n' > "${STUBDIR}/test_fib.py"
    printf 'CONFIG\n' > "${STUBDIR}/cosmic-ray.toml"
    : > "${STUBDIR}/mutants-equivalent.toml"
    # Working directories each stub ran in, kept apart from ${CALLS} so its line shapes stay put.
    PWDS="${BATS_TEST_TMPDIR}/pwds"
    : > "${PWDS}"
    cat > "${bin}/cosmic-ray" <<'STUB'
#!/bin/bash
printf 'cosmic-ray %s ulimit=%s\n' "$*" "$(ulimit -v)" >> "${CALLS}"
printf '%s %s\n' "$1" "${PWD}" >> "${PWDS}"
printf '%s fsize=%s\n' "$1" "$(ulimit -f)" >> "${CALLS}.env"
printf '%s core=%s\n' "$1" "$(ulimit -c)" >> "${CALLS}.env"
printf '%s tmpdir=%s\n' "$1" "${TMPDIR}" >> "${CALLS}.env"
case "$1" in
    baseline)
        # The baseline runs the tests too; whatever it leaks must land under its TMPDIR, not /tmp.
        printf x > "${TMPDIR}/baseline-leak"
        if [ -n "${STUB_BASELINE_HANG}" ]; then
            : > "${BATS_TEST_TMPDIR}/hang-ready"
            sleep 30
        fi
        exit "${STUB_BASELINE_RC:-0}" ;;
    init)
        # The real init creates the session; later steps and the copy-back depend on it.
        printf 'I' > cosmic-ray-session.sqlite
        exit "${STUB_INIT_RC:-0}" ;;
    exec)
        # A killed test never drops its tempfile dir; it must land under TMPDIR, not /tmp.
        if [ -n "${STUB_EXEC_LEAK}" ]; then mkdir "${TMPDIR}/tmpLEAK" && printf x > "${TMPDIR}/tmpLEAK/fib_1e5.txt"; fi
        [ -n "${STUB_EXEC_MUTATE}" ] && printf 'MUTATED\n' >> fib.py
        [ -n "${STUB_EXEC_SESSION}" ] && printf 'S' > cosmic-ray-session.sqlite
        [ -n "${STUB_EXEC_LS}" ] && ls -A | grep -v '^cosmic-ray-session' | tr '\n' ' ' > "${BATS_TEST_TMPDIR}/ls"
        # A report in scratch whose project-side destination is a dangling symlink: copy-back must fail.
        if [ -n "${STUB_EXEC_DANGLE}" ]; then
            printf 'R' > mutants-report.txt
            ln -s /nonexistent/x "${STUBDIR}/mutants-report.txt"
        fi
        # A session in scratch whose project-side destination is a dangling symlink: copy-back must fail.
        if [ -n "${STUB_EXEC_DANGLE_SESSION}" ]; then
            printf 'S' > cosmic-ray-session.sqlite
            ln -s /nonexistent/x "${STUBDIR}/cosmic-ray-session.sqlite"
        fi
        # Hang after writing the session, as a cancelled CI job would find exec.
        if [ -n "${STUB_EXEC_HANG}" ]; then
            printf 'S' > cosmic-ray-session.sqlite
            : > "${BATS_TEST_TMPDIR}/exec-ready"
            sleep 30
        fi
        exit "${STUB_EXEC_RC:-0}" ;;
esac
exit 0
STUB
    cat > "${bin}/python3" <<'STUB'
#!/bin/bash
printf 'python3 %s ulimit=%s\n' "$*" "$(ulimit -v)" >> "${CALLS}"
case "$*" in
    *cosmic_ray_cell_status*)
        {
            printf 'pwd=%s\n' "${PWD}"
            if [ -f cosmic-ray-session.sqlite ]; then
                printf 'session=present content=%s\n' "$(cat cosmic-ray-session.sqlite)"
            else
                printf 'session=absent\n'
            fi
        } >> "${BATS_TEST_TMPDIR}/status-seen"
        exit "${STUB_STATUS_RC:-0}" ;;
    *cosmic_ray_shard*)
        # The helper must be reachable from the scratch copy, as the real recipe needs it.
        [ -f "$1" ] || exit 2
        exit "${STUB_SHARD_RC:-0}" ;;
esac
exit 0
STUB
    cat > "${bin}/cr-report" <<'STUB'
#!/bin/bash
printf 'cr-report %s\n' "$*" >> "${CALLS}"
[ -t 1 ] || printf 'REPORT\n'
STUB
    # cp that stalls on the session file when STUB_CP_SLOW is set, so a signal sent once the
    # copy-back has begun lands inside the cleanup trap every time.
    cat > "${bin}/cp" <<'STUB'
#!/bin/bash
case "$*" in
    *cosmic-ray-session*)
        if [ -n "${STUB_CP_SLOW}" ]; then
            : > "${BATS_TEST_TMPDIR}/cp-started"
            sleep 1
        fi ;;
esac
exec /bin/cp "$@"
STUB
    _stub_slow_rm "${bin}"
    chmod +x "${bin}/cosmic-ray" "${bin}/python3" "${bin}/cr-report" "${bin}/cp"
    export CALLS PWDS STUBDIR
    export PATH="${bin}:${PATH}"
    unset MUTANTS_UNCAPPED MUTANT_SHARD STATUS_OUT SURVIVORS_OUT CELL_LABEL
}

_py_make() {
    env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS make -C "${STUBDIR}" "$@"
}

# Fails when any calls-file line matches the pattern. A bare `! grep` never fails a bats test.
_assert_no_call() {
    if grep -q -- "$1" "${CALLS}"; then
        printf 'unexpected call matching %s:\n' "$1" >&2
        cat "${CALLS}" >&2
        return 1
    fi
}

# 1-based line of the first calls-file line matching an ERE, or empty.
_calls_line() {
    grep -nE -- "$1" "${CALLS}" | head -1 | cut -d: -f1
}

@test "python mutants-baseline runs cosmic-ray with no core dumps" {
    _py_stub_setup
    _raise_core_limit
    run _py_make mutants-baseline
    [ "${status}" -eq 0 ]
    _assert_cores_disabled "${CALLS}.env"
}

@test "python mutants-baseline runs cosmic-ray with no core dumps even with MUTANTS_UNCAPPED set" {
    _py_stub_setup
    _raise_core_limit
    MUTANTS_UNCAPPED=1 run _py_make mutants-baseline
    [ "${status}" -eq 0 ]
    _assert_cores_disabled "${CALLS}.env"
}

@test "python mutants runs cosmic-ray with no core dumps" {
    _py_stub_setup
    _raise_core_limit
    run _py_make mutants
    [ "${status}" -eq 0 ]
    _assert_cores_disabled "${CALLS}.env"
}

@test "python mutants runs cosmic-ray with no core dumps even with MUTANTS_UNCAPPED set" {
    _py_stub_setup
    _raise_core_limit
    MUTANTS_UNCAPPED=1 run _py_make mutants
    [ "${status}" -eq 0 ]
    _assert_cores_disabled "${CALLS}.env"
}

@test "python make -n mutants executes nothing" {
    _py_stub_setup
    run _py_make -n mutants
    [ "${status}" -eq 0 ]
    [ ! -s "${CALLS}" ]
}

@test "python mutants-baseline runs cosmic-ray baseline under the 8 GiB cap" {
    _py_stub_setup
    run _py_make mutants-baseline
    [ "${status}" -eq 0 ]
    grep -q '^cosmic-ray baseline cosmic-ray.toml ulimit=8388608$' "${CALLS}"
}

@test "python mutants-baseline caps any single file at 256 MiB" {
    _py_stub_setup
    run _py_make mutants-baseline
    [ "${status}" -eq 0 ]
    grep -qxF 'baseline fsize=262144' "${CALLS}.env"
}

@test "python mutants-baseline runs with a project-local TMPDIR removed on exit" {
    _py_stub_setup
    local outer="${BATS_TEST_TMPDIR}/outer"
    mkdir -p "${outer}"
    run env TMPDIR="${outer}" env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants-baseline
    [ "${status}" -eq 0 ]
    grep -q "^baseline tmpdir=${STUBDIR}/.mutants-tmp/baseline\\." "${CALLS}.env"
    [ -z "$(ls -A "${STUBDIR}/.mutants-tmp")" ]
    [ -z "$(ls -A "${outer}")" ]
}

@test "python mutants-baseline removes its TMPDIR when the baseline fails" {
    _py_stub_setup
    run env STUB_BASELINE_RC=1 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants-baseline
    [ "${status}" -ne 0 ]
    [ -z "$(ls -A "${STUBDIR}/.mutants-tmp")" ]
}

@test "python mutants-clean removes the kept .mutants-tmp scratch dir" {
    _py_stub_setup
    mkdir -p "${STUBDIR}/.mutants-tmp/kept"
    printf x > "${STUBDIR}/.mutants-tmp/kept/x"
    run _py_make mutants-clean
    [ "${status}" -eq 0 ]
    [ ! -e "${STUBDIR}/.mutants-tmp" ]
}

@test "python mutants caps any single file at 256 MiB, also with MUTANTS_UNCAPPED" {
    _py_stub_setup
    run _py_make mutants
    [ "${status}" -eq 0 ]
    grep -qxF 'baseline fsize=262144' "${CALLS}.env"
    grep -qxF 'exec fsize=262144' "${CALLS}.env"
    : > "${CALLS}.env"
    MUTANTS_UNCAPPED=1 run _py_make mutants
    [ "${status}" -eq 0 ]
    grep -qxF 'exec fsize=262144' "${CALLS}.env"
}

@test "python mutants runs cosmic-ray exec with TMPDIR inside the project-local work dir" {
    _py_stub_setup
    run _py_make mutants
    [ "${status}" -eq 0 ]
    grep -qE "^exec tmpdir=${STUBDIR}/\.mutants-tmp/mutants-fib\.[^/]+/tmp\$" "${CALLS}.env"
}

@test "python mutants leaves .mutants-tmp empty after a successful run" {
    _py_stub_setup
    run _py_make mutants
    [ "${status}" -eq 0 ]
    [ -d "${STUBDIR}/.mutants-tmp" ]
    [ -z "$(ls -A "${STUBDIR}/.mutants-tmp")" ]
}

@test "python mutants removes tempfile dirs a killed test left in TMPDIR" {
    _py_stub_setup
    mkdir -p "${BATS_TEST_TMPDIR}/outer"
    run env TMPDIR="${BATS_TEST_TMPDIR}/outer" STUB_EXEC_LEAK=1 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants
    [ "${status}" -eq 0 ]
    [ -d "${STUBDIR}/.mutants-tmp" ]
    [ -z "$(ls -A "${STUBDIR}/.mutants-tmp")" ]
    [ -z "$(ls -A "${BATS_TEST_TMPDIR}/outer")" ]
}

@test "python mutants-baseline with MUTANTS_UNCAPPED runs uncapped and warns" {
    _py_stub_setup
    run env MUTANTS_UNCAPPED=1 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants-baseline
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"MUTANTS_UNCAPPED set"* ]]
    grep -q 'ulimit=unlimited' "${CALLS}"
}

@test "python mutants-baseline fails closed when the cap cannot be applied" {
    _py_stub_setup
    # A limit below 8 GiB (soft and hard) makes `ulimit -v 8388608` fail, as on macOS.
    run bash -c 'ulimit -v 1000000 && env -u MAKEFLAGS -u MAKELEVEL make -C "$1" mutants-baseline' _ "${STUBDIR}"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"cannot enforce a memory cap"* ]]
    _assert_no_call '^cosmic-ray baseline'
}

@test "python mutants fails closed on an unenforceable cap before init" {
    _py_stub_setup
    run bash -c 'ulimit -v 1000000 && env -u MAKEFLAGS -u MAKELEVEL make -C "$1" mutants' _ "${STUBDIR}"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"cannot enforce a memory cap"* ]]
    _assert_no_call '^cosmic-ray init'
}

@test "python mutants failed baseline runs the unittest fallback capped and stops" {
    _py_stub_setup
    run env STUB_BASELINE_RC=1 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants
    [ "${status}" -ne 0 ]
    grep -q '^python3 -m unittest test_fib ulimit=8388608$' "${CALLS}"
    _assert_no_call '^cosmic-ray init'
}

@test "python mutants without MUTANT_SHARD runs baseline, init, exec, report, status in order and never shards" {
    _py_stub_setup
    run _py_make mutants
    [ "${status}" -eq 0 ]
    _assert_no_call cosmic_ray_shard
    local b i e r s
    b="$(_calls_line '^cosmic-ray baseline')"
    i="$(_calls_line '^cosmic-ray init cosmic-ray.toml cosmic-ray-session.sqlite')"
    e="$(_calls_line '^cosmic-ray exec cosmic-ray.toml cosmic-ray-session.sqlite')"
    r="$(_calls_line '^cr-report')"
    s="$(_calls_line 'cosmic_ray_cell_status')"
    [ "${b}" -lt "${i}" ] && [ "${i}" -lt "${e}" ] && [ "${e}" -lt "${r}" ] && [ "${r}" -lt "${s}" ]
    [ "$(wc -l < "${CALLS}")" -eq "${s}" ]
    grep -q '^cosmic-ray init .* ulimit=8388608$' "${CALLS}"
}

@test "python mutants with MUTANT_SHARD=2/4 shards between init and exec" {
    _py_stub_setup
    run env MUTANT_SHARD=2/4 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants
    [ "${status}" -eq 0 ]
    local i sh e
    i="$(_calls_line '^cosmic-ray init')"
    sh="$(_calls_line '^python3 ../scripts/cosmic_ray_shard.py cosmic-ray-session.sqlite 2 4 ')"
    e="$(_calls_line '^cosmic-ray exec')"
    [ -n "${sh}" ]
    [ "${i}" -lt "${sh}" ] && [ "${sh}" -lt "${e}" ]
}

@test "python mutants rejects a malformed MUTANT_SHARD without sharding or executing" {
    local bad
    for bad in bogus 3 /4 3/ 1/2/3 a/b 1/b; do
        _py_stub_setup
        run env MUTANT_SHARD="${bad}" env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants
        [ "${status}" -ne 0 ] || { printf 'accepted %s\n' "${bad}" >&2; return 1; }
        [[ "${output}" == *"MUTANT_SHARD must be k/n"* ]] || { printf 'no error for %s\n' "${bad}" >&2; return 1; }
        _assert_no_call cosmic_ray_shard
        _assert_no_call '^cosmic-ray exec'
    done
}

@test "python mutants stops when the shard script fails" {
    _py_stub_setup
    run env MUTANT_SHARD=1/2 STUB_SHARD_RC=1 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants
    [ "${status}" -ne 0 ]
    grep -q '^cosmic-ray init' "${CALLS}"
    _assert_no_call '^cosmic-ray exec'
}

@test "python mutants exits non-zero and skips status when cosmic-ray exec fails" {
    _py_stub_setup
    run env STUB_EXEC_RC=1 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants
    [ "${status}" -ne 0 ]
    grep -q '^cosmic-ray init' "${CALLS}"
    _assert_no_call cosmic_ray_cell_status
}

@test "python mutants exits with the cell-status script's failure" {
    _py_stub_setup
    run env STUB_STATUS_RC=1 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants
    [ "${status}" -ne 0 ]
    grep -q cosmic_ray_cell_status "${CALLS}"
}

@test "python mutants labels the cell with the directory name by default" {
    _py_stub_setup
    run _py_make mutants
    [ "${status}" -eq 0 ]
    grep -qE '^python3 \.\./scripts/cosmic_ray_cell_status\.py cosmic-ray-session\.sqlite fib ulimit=' "${CALLS}"
}

@test "python mutants forwards CELL_LABEL, STATUS_OUT and SURVIVORS_OUT intact" {
    _py_stub_setup
    run env CELL_LABEL="fib 'x\$y\"z" env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants STATUS_OUT=out/s.txt SURVIVORS_OUT=out/v.txt
    [ "${status}" -eq 0 ]
    grep -qF "cosmic_ray_cell_status.py cosmic-ray-session.sqlite fib 'x\$y\"z --out out/s.txt --survivors out/v.txt " "${CALLS}"
}

# Scratch-copy cases. The recipe's work dir is project-local (.mutants-tmp), whatever the caller's
# TMPDIR says, so "scratch removed" is observed there.
_scratch_tmp() {
    SCRATCH_T="${STUBDIR}/.mutants-tmp"
    mkdir -p "${SCRATCH_T}"
}

@test "python mutants leaves the source untouched when exec mutates it and fails" {
    _py_stub_setup
    _scratch_tmp
    cp "${STUBDIR}/fib.py" "${BATS_TEST_TMPDIR}/fib.py.before"
    run env TMPDIR="${SCRATCH_T}" STUB_EXEC_MUTATE=1 STUB_EXEC_RC=1 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants
    [ "${status}" -ne 0 ]
    grep -q "^exec ${SCRATCH_T}/" "${PWDS}"
    grep -q "^init ${SCRATCH_T}/" "${PWDS}"
    cmp "${STUBDIR}/fib.py" "${BATS_TEST_TMPDIR}/fib.py.before"
}

@test "python mutants copies outputs back before the status call and removes scratch" {
    _py_stub_setup
    _scratch_tmp
    run env TMPDIR="${SCRATCH_T}" STUB_EXEC_SESSION=1 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants
    [ "${status}" -eq 0 ]
    grep -q "^pwd=${STUBDIR}$" "${BATS_TEST_TMPDIR}/status-seen"
    grep -q '^session=present content=S$' "${BATS_TEST_TMPDIR}/status-seen"
    [ "$(cat "${STUBDIR}/cosmic-ray-session.sqlite")" = "S" ]
    [ "$(cat "${STUBDIR}/mutants-report.txt")" = "REPORT" ]
    [ -z "$(ls -A "${SCRATCH_T}")" ]
    grep -q "^exec ${SCRATCH_T}/" "${PWDS}"
}

@test "python mutants keeps a partial session in the project when exec fails" {
    _py_stub_setup
    _scratch_tmp
    run env TMPDIR="${SCRATCH_T}" STUB_EXEC_SESSION=1 STUB_EXEC_RC=1 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants
    [ "${status}" -ne 0 ]
    grep -q "^exec ${SCRATCH_T}/" "${PWDS}"
    [ "$(cat "${STUBDIR}/cosmic-ray-session.sqlite")" = "S" ]
    [ -z "$(ls -A "${SCRATCH_T}")" ]
}

@test "python mutants keeps the scratch copy when a copy-back fails" {
    _py_stub_setup
    _scratch_tmp
    run env TMPDIR="${SCRATCH_T}" STUB_EXEC_SESSION=1 STUB_EXEC_DANGLE=1 STUB_EXEC_RC=1 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"mutants: kept"* ]]
    [ -n "$(ls -A "${SCRATCH_T}")" ]
}

@test "python mutants removes stale outputs from the project first" {
    _py_stub_setup
    _scratch_tmp
    printf 'OLD\n' > "${STUBDIR}/mutants-report.txt"
    run env TMPDIR="${SCRATCH_T}" STUB_INIT_RC=1 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants
    [ "${status}" -ne 0 ]
    [ ! -e "${STUBDIR}/mutants-report.txt" ]
}

# A hot journal left by an interrupted run would be rolled back into the next
# run's fresh session by SQLite, so it goes with the stale session.
@test "python mutants removes a stale session journal from the project first" {
    _py_stub_setup
    _scratch_tmp
    printf 'J\n' > "${STUBDIR}/cosmic-ray-session.sqlite-journal"
    run env TMPDIR="${SCRATCH_T}" STUB_INIT_RC=1 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants
    [ "${status}" -ne 0 ]
    [ ! -e "${STUBDIR}/cosmic-ray-session.sqlite-journal" ]
}

@test "python mutants copies only the module, its test and the config into scratch" {
    _py_stub_setup
    _scratch_tmp
    mkdir -p "${STUBDIR}/fib-rs/target"
    printf 'x' > "${STUBDIR}/fib-rs/target/big"
    run env TMPDIR="${SCRATCH_T}" STUB_EXEC_LS=1 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants
    [ "${status}" -eq 0 ]
    [ "$(cat "${BATS_TEST_TMPDIR}/ls")" = "cosmic-ray.toml fib.py mutants-equivalent.toml test_fib.py " ]
}

@test "python mutants copies the session back when the whole process group gets SIGTERM" {
    _skip_under_coverage_tracer
    _py_stub_setup
    _scratch_tmp
    rm -f "${BATS_TEST_TMPDIR}/exec-ready" "${BATS_TEST_TMPDIR}/cp-started"
    TMPDIR="${SCRATCH_T}" STUB_EXEC_HANG=1 STUB_CP_SLOW=1 setsid env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants >/dev/null 2>&1 </dev/null &
    local pid=$! i
    for i in $(seq 1 100); do
        [ -e "${BATS_TEST_TMPDIR}/exec-ready" ] && break
        sleep 0.1
    done
    if [ ! -e "${BATS_TEST_TMPDIR}/exec-ready" ]; then
        _dump_group_state "${pid}"
        kill -KILL -- "-${pid}" 2>/dev/null
        wait "${pid}" 2>/dev/null || true
        printf 'wait failed: exec stub never reached exec-ready\n' >&2
        return 1
    fi
    kill -TERM -- "-${pid}"
    # Once cleanup is inside its (stalled) copy-back, a second TERM must not abort it.
    if ! _wait_for_file "${BATS_TEST_TMPDIR}/cp-started" 50; then
        _dump_group_state "${pid}"
        kill -KILL -- "-${pid}" 2>/dev/null
        wait "${pid}" 2>/dev/null || true
        printf 'wait failed: copy-back never started (cp-started) after first TERM\n' >&2
        return 1
    fi
    # GNU make ignores a repeated TERM, so also signal its recipe shell, which is what make's
    # own forwarded TERM reaches.
    local child
    kill -TERM "${pid}" 2>/dev/null
    for child in $(pgrep -P "${pid}"); do
        kill -TERM "${child}" 2>/dev/null
    done
    for i in $(seq 1 100); do
        kill -0 "${pid}" 2>/dev/null || break
        sleep 0.1
    done
    if kill -0 "${pid}" 2>/dev/null; then
        _dump_group_state "${pid}"
        kill -KILL -- "-${pid}" 2>/dev/null
        wait "${pid}" 2>/dev/null || true
        printf 'wait failed: make did not exit after the second TERM\n' >&2
        return 1
    fi
    wait "${pid}" 2>/dev/null || true
    [ "$(cat "${STUBDIR}/cosmic-ray-session.sqlite")" = "S" ]
    [ -z "$(ls -A "${SCRATCH_T}")" ]
}

@test "python mutants-baseline removes its scratch dir when the whole process group gets SIGTERM twice" {
    _skip_under_coverage_tracer
    _py_stub_setup
    _scratch_tmp
    STUB_BASELINE_HANG=1 STUB_RM_SLOW=1 _term_group_twice "${STUBDIR}" mutants-baseline
    # The rm was asked to remove a baseline dir, and nothing is left of it.
    grep -q 'baseline\.' "${BATS_TEST_TMPDIR}/rm-log"
    [ -z "$(ls -A "${SCRATCH_T}")" ]
}

@test "python mutants keeps the scratch copy when the session copy-back fails" {
    _py_stub_setup
    _scratch_tmp
    run env TMPDIR="${SCRATCH_T}" STUB_EXEC_DANGLE_SESSION=1 STUB_EXEC_RC=1 env -u MAKEFLAGS -u MAKELEVEL make -C "${STUBDIR}" mutants
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"mutants: kept"* ]]
    [ -n "$(ls -A "${SCRATCH_T}")" ]
}

@test "every cosmic-ray project has both helper scripts at ../scripts" {
    local n=0 cfg dir
    while IFS= read -r cfg; do
        dir="${REPO_ROOT}/$(dirname "${cfg}")"
        [ -f "${dir}/../scripts/cosmic_ray_shard.py" ]
        [ -f "${dir}/../scripts/cosmic_ray_cell_status.py" ]
        n=$((n + 1))
    done < <(git -C "${REPO_ROOT}" ls-files ':(glob)*/cosmic-ray.toml')
    [ "${n}" -eq 9 ]
}

# lint-workflows (actionlint). The fixture is a positive control: actionlint
# only reports SC2086 for the `run:` body when it both ran and found shellcheck,
# so a green run on the real workflows is not a vacuous pass.
@test "actionlint flags SC2086 in the positive-control fixture" {
    if ! command -v actionlint > /dev/null 2>&1 || ! command -v shellcheck > /dev/null 2>&1; then
        if [[ "${CI:-}" == "true" ]]; then
            fail_msg="actionlint or shellcheck missing under CI=true"
            printf '%s\n' "${fail_msg}" >&2
            return 1
        fi
        skip "actionlint or shellcheck not installed"
    fi
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS make -C "${REPO_ROOT}" lint-workflows WORKFLOWS=tests/fixtures/actionlint/sc2086.yml
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"SC2086"* ]]
}

@test "lint-workflows without actionlint under CI=true fails naming actionlint" {
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS CI=true make -C "${REPO_ROOT}" lint-workflows ACTIONLINT=
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"actionlint not found"* ]]
}

@test "lint-workflows without actionlint and CI unset skips with the remedy" {
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS -u CI make -C "${REPO_ROOT}" lint-workflows ACTIONLINT=
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"actionlint not found, skipping"* ]]
    [[ "${output}" == *"v1.7.12"* ]]
}

@test "make lint lists lint-workflows as a prerequisite (actionlint wiring)" {
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS make -C "${REPO_ROOT}" -n lint --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"actionlint"* ]] || [[ "${output}" == *"lint-workflows"* ]]
}

@test "lint-workflows with an empty workflow list fails closed (actionlint present)" {
    command -v actionlint > /dev/null 2>&1 || skip "actionlint not installed"
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS make -C "${REPO_ROOT}" lint-workflows WORKFLOWS=
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"WORKFLOWS"* ]]
}

@test "lint-workflows with a whitespace-only workflow list fails closed (actionlint present)" {
    command -v actionlint > /dev/null 2>&1 || skip "actionlint not installed"
    run env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS make -C "${REPO_ROOT}" lint-workflows 'WORKFLOWS=$(subst x, ,x)'
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"WORKFLOWS list is EMPTY"* ]]
}

# --- Python mutants / mutants-diff / mutants-diff-plan ---------------------------------
# The recipes run against a fixture copy of sq/ whose ../scripts holds stubs that log their
# argv one argument per line, so call order and arguments are asserted without cosmic-ray.
# HOME and XDG_CONFIG_HOME go to the fixture so nothing here can touch the real config.
_pd_setup() {
    export HOME="${BATS_TEST_TMPDIR}/home" XDG_CONFIG_HOME="${BATS_TEST_TMPDIR}/home/.config"
    mkdir -p "${HOME}" "${XDG_CONFIG_HOME}"
    FX="${BATS_TEST_TMPDIR}/repo"
    PROJ="${FX}/sq"
    CALLS="${BATS_TEST_TMPDIR}/calls"
    : > "${CALLS}"
    mkdir -p "${PROJ}" "${FX}/scripts" "${BATS_TEST_TMPDIR}/bin"
    # PD_MAKEFILE lets a mutation probe run this suite against an altered copy of the Makefile.
    cp "${PD_MAKEFILE:-${REPO_ROOT}/sq/Makefile}" "${PROJ}/Makefile"
    cp "${REPO_ROOT}/sq/cosmic-ray.toml" "${PROJ}/"
    : > "${PROJ}/sq.py"
    : > "${PROJ}/test_sq.py"
    : > "${PROJ}/mutants-equivalent.toml"
    printf 'diff --git a/sq.py b/sq.py\n' > "${BATS_TEST_TMPDIR}/pr.diff"
    local s
    for s in cosmic_ray_prune cosmic_ray_shard cosmic_ray_cell_status; do
        cat > "${FX}/scripts/${s}.py" <<PYEOF
import os, sys
with open(os.environ["CALLS"], "a") as f:
    f.write("${s}\n")
    for a in sys.argv[1:]:
        f.write("  " + a + "\n")
if "${s}" == "cosmic_ray_prune":
    if os.environ.get("STUB_PRUNE_RC", "0") != "0" and sys.argv[1] == os.environ.get("STUB_PRUNE_FAIL_ON", "equivalents"):
        sys.stderr.write("cosmic_ray_prune: stub failure\n")
        sys.exit(1)
    print("excluded 0 of 5 equivalents" if sys.argv[1] == "equivalents" else "kept 2 of 5 (lines 1)")
if "${s}" == "cosmic_ray_cell_status":
    if os.environ.get("STUB_STATUS_ECHO_SESSION"):
        print("session=" + open(sys.argv[1]).read().splitlines()[0])
        sys.exit(int(os.environ.get("STUB_STATUS_RC", "1")))
    print("red: sq - 1 surviving exceeds --max-survivors 0")
    sys.exit(int(os.environ.get("STUB_STATUS_RC", "1")))
PYEOF
    done
    cat > "${BATS_TEST_TMPDIR}/bin/cosmic-ray" <<'SHEOF'
#!/usr/bin/env bash
printf 'cosmic-ray %s\n' "$1" >> "${CALLS}"
case "$1" in
    baseline) exit "${STUB_BASELINE_RC:-0}" ;;
    init) printf 'fresh\n' > "$3"; exit 0 ;;
    exec) exit "${STUB_EXEC_RC:-0}" ;;
esac
SHEOF
    cat > "${BATS_TEST_TMPDIR}/bin/cr-report" <<'SHEOF'
#!/usr/bin/env bash
# STUB_CR_FAIL: the report is written (the shell creates it first), then cr-report dies.
if [ -n "${STUB_CR_FAIL}" ] && [ "$*" != "${1}" ]; then printf 'partial\n'; exit 1; fi
printf 'report\n'
SHEOF
    chmod +x "${BATS_TEST_TMPDIR}/bin/cosmic-ray" "${BATS_TEST_TMPDIR}/bin/cr-report"
    export CALLS
    export PATH="${BATS_TEST_TMPDIR}/bin:${PATH}"
}

_pd_make() {
    env -u MAKEFLAGS -u MAKELEVEL -u MFLAGS -u DIFF -u MUTANT_SHARD -u STATUS_OUT -u SURVIVORS_OUT \
        MUTANTS_UNCAPPED=1 make --no-print-directory "$@"
}

# The first line of each logged call, in order.
_pd_order() {
    grep -v '^  ' "${CALLS}" | sed -e 's/^cosmic-ray //' -e 's/^cosmic_ray_prune$/prune/' \
        -e 's/^cosmic_ray_shard$/shard/' -e 's/^cosmic_ray_cell_status$/status/' | tr '\n' ' '
}

@test "python mutants-diff exits 2 naming DIFF when DIFF is unset, with no cosmic-ray call" {
    _pd_setup
    run _pd_make -C "${PROJ}" mutants-diff
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"DIFF"* ]]
    [ ! -s "${CALLS}" ]
}

@test "python mutants-diff-plan exits 2 naming DIFF when DIFF is missing, with no cosmic-ray call" {
    _pd_setup
    run _pd_make -C "${PROJ}" mutants-diff-plan DIFF="${BATS_TEST_TMPDIR}/missing.diff"
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"DIFF"* ]]
    [ ! -s "${CALLS}" ]
}

# An existing but unreadable file isolates the -r half of DIFF_GUARD from its -f half.
@test "python mutants-diff-plan exits 2 naming DIFF when DIFF exists but is unreadable, with no cosmic-ray call" {
    [ "$(id -u)" -ne 0 ] || skip "root can read mode-000 files"
    _pd_setup
    chmod 000 "${BATS_TEST_TMPDIR}/pr.diff"
    run _pd_make -C "${PROJ}" mutants-diff-plan DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    chmod 644 "${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"is not a readable file"* ]]
    [ ! -s "${CALLS}" ]
}

@test "python mutants-diff exits 2 when DIFF is a directory" {
    _pd_setup
    run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}"
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"DIFF"* ]]
    [ ! -s "${CALLS}" ]
}

@test "python mutants-diff-plan stops when the baseline fails" {
    _pd_setup
    STUB_BASELINE_RC=1 run _pd_make -C "${PROJ}" mutants-diff-plan DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -ne 0 ]
    [ "$(_pd_order)" = "baseline " ]
    ! command grep -q 'cosmic_ray_prune' "${CALLS}"
}

@test "python mutants-diff stops when the baseline fails" {
    _pd_setup
    STUB_BASELINE_RC=1 run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -ne 0 ]
    ! command grep -q 'cosmic-ray exec\|cosmic_ray_prune' "${CALLS}"
}

@test "python mutants-diff runs baseline, init, equivalents, diff, exec, cell_status in order" {
    _pd_setup
    run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -ne 0 ] # the status stub reports red, and the recipe propagates it
    [ "$(_pd_order)" = "baseline init prune prune exec status " ]
    run command grep -A1 '^cosmic_ray_prune$' "${CALLS}"
    [[ "${output}" == *"  equivalents"* ]]
    [[ "${output}" == *"  diff"* ]]
}

@test "python mutants-diff runs the equivalents prune before the diff prune" {
    _pd_setup
    run _pd_make -C "${PROJ}" mutants-diff-plan DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -eq 0 ]
    eq="$(command grep -n '^  equivalents$' "${CALLS}" | cut -d: -f1)"
    df="$(command grep -n '^  diff$' "${CALLS}" | cut -d: -f1)"
    [ -n "${eq}" ] && [ -n "${df}" ]
    [ "${eq}" -lt "${df}" ]
}

@test "python mutants-diff passes the prune calls their documented arguments" {
    _pd_setup
    run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    # equivalents <session> <toml> --diff <abs> --toml-path <toml>
    [[ "$(cat "${CALLS}"; printf .)" == *$'cosmic_ray_prune\n  equivalents\n  cosmic-ray-diff-session.sqlite\n  mutants-equivalent.toml\n  --diff\n  '"${BATS_TEST_TMPDIR}"$'/pr.diff\n  --toml-path\n'* ]]
    [[ "$(cat "${CALLS}"; printf .)" == *$'  --toml-path\n  mutants-equivalent.toml\n'* ]]
    # diff <session> <abs diff> <module>
    [[ "$(cat "${CALLS}"; printf .)" == *$'  diff\n  cosmic-ray-diff-session.sqlite\n  '"${BATS_TEST_TMPDIR}"$'/pr.diff\n  sq.py\n'* ]]
    # cell_status gets --max-survivors 0
    [[ "$(cat "${CALLS}"; printf .)" == *$'  --max-survivors\n  0\n'* ]]
}

@test "python mutants-diff resolves a relative DIFF against the invoking directory" {
    _pd_setup
    mkdir -p "${BATS_TEST_TMPDIR}/inv"
    cp "${BATS_TEST_TMPDIR}/pr.diff" "${BATS_TEST_TMPDIR}/inv/rel.diff"
    cd "${BATS_TEST_TMPDIR}/inv"
    PWD="${BATS_TEST_TMPDIR}/inv" run _pd_make -C "${PROJ}" mutants-diff-plan DIFF=rel.diff
    [ "${status}" -eq 0 ]
    [[ "$(cat "${CALLS}"; printf .)" == *$'  --diff\n  '"${BATS_TEST_TMPDIR}"$'/inv/rel.diff\n'* ]]
}

@test "python mutants-diff applies MUTANT_SHARD between diff and exec, and only when set" {
    _pd_setup
    run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff" MUTANT_SHARD=1/3
    [ "$(_pd_order)" = "baseline init prune prune shard exec status " ]
    [[ "$(cat "${CALLS}"; printf .)" == *$'cosmic_ray_shard\n  cosmic-ray-diff-session.sqlite\n  1\n  3\n'* ]]
}

@test "python mutants-diff rejects a malformed MUTANT_SHARD before exec" {
    _pd_setup
    run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff" MUTANT_SHARD=oops
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"MUTANT_SHARD"* ]]
    ! command grep -q 'cosmic-ray exec' "${CALLS}"
}

@test "python mutants-diff-plan stops after both prune calls and prints their stdout" {
    _pd_setup
    run _pd_make -C "${PROJ}" mutants-diff-plan DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -eq 0 ]
    [ "$(_pd_order)" = "baseline init prune prune " ]
    [[ "${output}" == *"excluded 0 of 5 equivalents"* ]]
    [[ "${output}" == *"kept 2 of 5 (lines 1)"* ]]
    [ ! -e "${PROJ}/cosmic-ray-diff-session.sqlite" ]
    [ ! -e "${PROJ}/mutants-diff-report.txt" ]
}

@test "python mutants-diff-plan fails with prune's stderr when equivalents fails, skipping diff" {
    _pd_setup
    STUB_PRUNE_RC=1 run _pd_make -C "${PROJ}" mutants-diff-plan DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"cosmic_ray_prune: stub failure"* ]]
    [ "$(command grep -c '^cosmic_ray_prune$' "${CALLS}")" -eq 1 ]
}

@test "python mutants-diff-plan fails when the diff prune fails" {
    _pd_setup
    STUB_PRUNE_RC=1 STUB_PRUNE_FAIL_ON=diff run _pd_make -C "${PROJ}" mutants-diff-plan DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"cosmic_ray_prune: stub failure"* ]]
}

@test "python mutants-diff writes only the diff session and report, leaving the full session byte-identical" {
    _pd_setup
    printf 'full-run-session-bytes\n' > "${PROJ}/cosmic-ray-session.sqlite"
    printf 'full-run-report\n' > "${PROJ}/mutants-report.txt"
    before="$(cksum "${PROJ}/cosmic-ray-session.sqlite" "${PROJ}/mutants-report.txt")"
    STUB_STATUS_RC=0 run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -eq 0 ]
    [ "$(cksum "${PROJ}/cosmic-ray-session.sqlite" "${PROJ}/mutants-report.txt")" = "${before}" ]
    [ -f "${PROJ}/cosmic-ray-diff-session.sqlite" ]
    [ -f "${PROJ}/mutants-diff-report.txt" ]
    # Everything else in the project is what the fixture put there, plus the transient dir.
    [ "$(find "${PROJ}" -mindepth 1 -maxdepth 1 ! -name .mutants-tmp -printf "%f\n" | LC_ALL=C sort | tr '\n' ' ')" = "Makefile cosmic-ray-diff-session.sqlite cosmic-ray-session.sqlite cosmic-ray.toml mutants-diff-report.txt mutants-equivalent.toml mutants-report.txt sq.py test_sq.py " ]
}

@test "python mutants-diff copies the diff session back even when cell_status is red" {
    _pd_setup
    run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -ne 0 ]
    [ -f "${PROJ}/cosmic-ray-diff-session.sqlite" ]
}

@test "python mutants-diff STATUS_OUT receives the full cell_status stdout and SURVIVORS_OUT is passed on" {
    _pd_setup
    run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff" STATUS_OUT="${BATS_TEST_TMPDIR}/status.txt" SURVIVORS_OUT="${BATS_TEST_TMPDIR}/surv.txt"
    [ "${status}" -ne 0 ]
    [ "$(cat "${BATS_TEST_TMPDIR}/status.txt")" = "red: sq - 1 surviving exceeds --max-survivors 0" ]
    [[ "${output}" == *"red: sq - 1 surviving"* ]]
    [[ "$(cat "${CALLS}"; printf .)" == *$'  --survivors\n  '"${BATS_TEST_TMPDIR}"$'/surv.txt\n'* ]]
    ! command grep -q -- '--out' "${CALLS}"
}

@test "python mutants-diff fails when exec fails and does not run cell_status" {
    _pd_setup
    STUB_EXEC_RC=1 run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -ne 0 ]
    ! command grep -q 'cosmic_ray_cell_status' "${CALLS}"
}

@test "python mutants runs equivalents --full-run after init and before the shard" {
    _pd_setup
    STUB_STATUS_RC=0 run _pd_make -C "${PROJ}" mutants MUTANT_SHARD=0/2
    [ "${status}" -eq 0 ]
    [ "$(_pd_order)" = "baseline init prune shard exec status " ]
    [[ "$(cat "${CALLS}"; printf .)" == *$'  equivalents\n  cosmic-ray-session.sqlite\n  mutants-equivalent.toml\n  --full-run\n'* ]]
}

@test "python mutants fails when equivalents fails and runs no exec" {
    _pd_setup
    STUB_PRUNE_RC=1 run _pd_make -C "${PROJ}" mutants
    [ "${status}" -ne 0 ]
    ! command grep -q 'cosmic-ray exec' "${CALLS}"
}

@test "python mutants does not write the diff session or report" {
    _pd_setup
    STUB_STATUS_RC=0 run _pd_make -C "${PROJ}" mutants
    [ "${status}" -eq 0 ]
    [ ! -e "${PROJ}/cosmic-ray-diff-session.sqlite" ]
    [ ! -e "${PROJ}/mutants-diff-report.txt" ]
}

@test "python mutants-clean removes both session pairs, journals and the work dir" {
    _pd_setup
    local f
    for f in cosmic-ray-session.sqlite cosmic-ray-session.sqlite-journal mutants-report.txt \
        cosmic-ray-diff-session.sqlite cosmic-ray-diff-session.sqlite-journal mutants-diff-report.txt; do
        : > "${PROJ}/${f}"
    done
    mkdir -p "${PROJ}/.mutants-tmp"
    run _pd_make -C "${PROJ}" mutants-clean
    [ "${status}" -eq 0 ]
    for f in cosmic-ray-session.sqlite cosmic-ray-session.sqlite-journal mutants-report.txt \
        cosmic-ray-diff-session.sqlite cosmic-ray-diff-session.sqlite-journal mutants-diff-report.txt .mutants-tmp; do
        [ ! -e "${PROJ}/${f}" ]
    done
}

@test "python mutants-equivalent.toml is an empty file in all nine projects except where filled" {
    local d
    for d in amicable collatz e factorial fib perfect-numbers pi sq triangle; do
        [ -f "${REPO_ROOT}/${d}/mutants-equivalent.toml" ]
    done
    for d in amicable collatz factorial fib perfect-numbers sq triangle; do
        [ ! -s "${REPO_ROOT}/${d}/mutants-equivalent.toml" ]
    done
}

@test "gitignore covers the diff session, its journal and the diff report" {
    local f
    for f in cosmic-ray-diff-session.sqlite cosmic-ray-diff-session.sqlite-journal mutants-diff-report.txt; do
        command grep -qxF "${f}" "${REPO_ROOT}/.gitignore"
    done
}

@test "python mutants-diff grades the fresh session, not a stale one left in the project" {
    _pd_setup
    printf 'stale\n' > "${PROJ}/cosmic-ray-diff-session.sqlite"
    printf 'stale\n' > "${PROJ}/mutants-diff-report.txt"
    STUB_STATUS_ECHO_SESSION=1 STUB_STATUS_RC=0 run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"session=fresh"* ]]
    [[ "${output}" != *"stale"* ]]
    [ "$(cat "${PROJ}/mutants-diff-report.txt")" = "report" ]
}

@test "python mutants-diff leaves no stale diff report when exec fails" {
    _pd_setup
    printf 'stale\n' > "${PROJ}/cosmic-ray-diff-session.sqlite"
    printf 'stale\n' > "${PROJ}/mutants-diff-report.txt"
    STUB_EXEC_RC=1 run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -ne 0 ]
    [ ! -e "${PROJ}/mutants-diff-report.txt" ]
    [ "$(head -1 "${PROJ}/cosmic-ray-diff-session.sqlite")" = "fresh" ]
}

@test "python mutants-diff copies the partial diff session back when exec fails" {
    _pd_setup
    STUB_EXEC_RC=1 run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -ne 0 ]
    [ "$(head -1 "${PROJ}/cosmic-ray-diff-session.sqlite")" = "fresh" ]
}

@test "python mutants-diff and mutants-diff-plan leave .mutants-tmp empty on success" {
    _pd_setup
    STUB_STATUS_RC=0 run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -eq 0 ]
    [ -z "$(ls -A "${PROJ}/.mutants-tmp")" ]
    run _pd_make -C "${PROJ}" mutants-diff-plan DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -eq 0 ]
    [ -z "$(ls -A "${PROJ}/.mutants-tmp")" ]
}

@test "python mutants-diff resolves a relative STATUS_OUT and SURVIVORS_OUT against the invoking directory" {
    _pd_setup
    mkdir -p "${BATS_TEST_TMPDIR}/inv"
    cp "${BATS_TEST_TMPDIR}/pr.diff" "${BATS_TEST_TMPDIR}/inv/rel.diff"
    cd "${BATS_TEST_TMPDIR}/inv"
    PWD="${BATS_TEST_TMPDIR}/inv" run _pd_make -C "${PROJ}" mutants-diff DIFF=rel.diff STATUS_OUT=status.txt SURVIVORS_OUT=surv.txt
    [ -f "${BATS_TEST_TMPDIR}/inv/status.txt" ]
    [ ! -e "${PROJ}/status.txt" ]
    [[ "$(cat "${CALLS}"; printf .)" == *$'  --survivors\n  '"${BATS_TEST_TMPDIR}"$'/inv/surv.txt\n'* ]]
}

@test "python mutants-diff with DIFF unset never reaches cosmic-ray under make -k" {
    _pd_setup
    run _pd_make -k -C "${PROJ}" mutants-diff
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"DIFF"* ]]
    [ ! -s "${CALLS}" ]
}

@test "python mutants-diff-plan with DIFF unset never reaches cosmic-ray under make -j2" {
    _pd_setup
    run _pd_make -j2 -C "${PROJ}" mutants-diff-plan
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"DIFF"* ]]
    [ ! -s "${CALLS}" ]
}

@test "python mutants-diff with a missing DIFF never reaches cosmic-ray under make -k -j2" {
    _pd_setup
    run _pd_make -k -j2 -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/missing.diff"
    [ "${status}" -ne 0 ]
    [ ! -s "${CALLS}" ]
}

@test "python mutants-diff with an unreadable DIFF never reaches cosmic-ray under make -k -j2" {
    [ "$(id -u)" -ne 0 ] || skip "root can read mode-000 files"
    _pd_setup
    chmod 000 "${BATS_TEST_TMPDIR}/pr.diff"
    run _pd_make -k -j2 -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    chmod 644 "${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -ne 0 ]
    [[ "${output}" == *"is not a readable file"* ]]
    [ ! -s "${CALLS}" ]
}

@test "python mutants-diff exits 2 when the STATUS_OUT copy fails after cell_status exits 0" {
    _pd_setup
    STUB_STATUS_RC=0 run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff" \
        STATUS_OUT="${BATS_TEST_TMPDIR}/no-such-dir/status.txt"
    [ "${status}" -eq 2 ]
    [[ "${output}" == *"cp:"* ]]
    [ ! -e "${BATS_TEST_TMPDIR}/no-such-dir" ]
}

@test "python mutants-diff keeps the partial report in the project when cr-report fails" {
    _pd_setup
    STUB_CR_FAIL=1 run _pd_make -C "${PROJ}" mutants-diff DIFF="${BATS_TEST_TMPDIR}/pr.diff"
    [ "${status}" -eq 2 ]
    [ "$(cat "${PROJ}/mutants-diff-report.txt")" = "partial" ]
}

@test "python mutants keeps the partial report in the project when cr-report fails" {
    _pd_setup
    STUB_CR_FAIL=1 run _pd_make -C "${PROJ}" mutants
    [ "${status}" -eq 2 ]
    [ "$(cat "${PROJ}/mutants-report.txt")" = "partial" ]
}
