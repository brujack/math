#!/usr/bin/env bats

load '../helpers/common'

@test "make test-hooks recipe calls bats --recursive tests/" {
    run make -C "${REPO_ROOT}" -n test-hooks --no-print-directory
    [ "${status}" -eq 0 ]
    [[ "${output}" == *"bats --recursive tests/"* ]]
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
        grep -qE '^[[:space:]]*run:[[:space:]]*cargo install cargo-machete' \
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
# gated scope and were linted by nothing, which math's own CLAUDE.md recorded
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
# tests/mocks/git has no ls-files branch, so an inherited mock silently
# returns an empty list and every assertion below would pass vacuously
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
    makefiles="$(cd "${REPO_ROOT}" && PATH="${_clean_path}" command git ls-files '*/*/Makefile')"
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

    local old_path="${PATH}"
    PATH="${stub_dir}:${PATH}"
    [ "$(command -v python3)" = "${stub_dir}/python3" ]
    PIP_NO_INDEX=1 PIP_REQUIRE_VIRTUALENV=1 run make -C "${REPO_ROOT}" install-deps
    PATH="${old_path}"

    [ "${status}" -eq 0 ]
    [ -f "${call_log}" ]
    grep -q 'requirements-dev.txt' "${call_log}"
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
