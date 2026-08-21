#!/usr/bin/env bats

# A sub-project's Makefile and its install_deps.sh are two independent
# statements about the same dependency set, and nothing forces them equal.
# CI hides the drift because each workflow pip-installs on its own path, so a
# fresh checkout following the documented installer is the only place the gap
# shows -- and only as a command-not-found nobody is watching for.
#
# The sub-project list is derived from `git ls-files`, never hardcoded: an
# omitted sub-project would be absent from the loop rather than failing it.

load '../helpers/common'

# Tools whose presence in a Makefile recipe implies a pip requirement.
# pytest --cov is the pytest-cov plugin, which is a separate distribution
# from pytest and is what `make coverage` actually needs.
@test "every sub-project install_deps.sh installs what its Makefile invokes" {
    local makefiles missing=""
    makefiles="$(cd "${REPO_ROOT}" && git ls-files '*/Makefile' '*/*/Makefile')"
    [ -n "${makefiles}" ]

    local checked=0
    while IFS= read -r mf; do
        [[ -z "${mf}" ]] && continue
        local dir installer body
        dir="$(dirname "${mf}")"
        installer="${REPO_ROOT}/${dir}/install_deps.sh"
        [[ -f "${installer}" ]] || continue
        body="$(cat "${REPO_ROOT}/${mf}")"
        checked=$((checked + 1))

        if grep -qE '^[[:space:]]+pytest ' <<< "${body}"; then
            grep -qE '(^|[[:space:]])pytest([[:space:]]|$|==)' "${installer}" \
                || missing="${missing}${dir}:pytest "
        fi
        if grep -qE '^[[:space:]]+pytest .*--cov' <<< "${body}"; then
            grep -qE '(^|[[:space:]])pytest-cov([[:space:]]|$|==)' "${installer}" \
                || missing="${missing}${dir}:pytest-cov "
        fi
        if grep -qE '^[[:space:]]+ruff ' <<< "${body}"; then
            grep -qE '(^|[[:space:]])ruff([[:space:]]|$|==)' "${installer}" \
                || missing="${missing}${dir}:ruff "
        fi
    done <<< "${makefiles}"

    # Guards the vacuous case: if no Makefile had a sibling installer the loop
    # would leave missing empty and the test would pass having checked nothing.
    [ "${checked}" -gt 0 ]

    if [[ -n "${missing}" ]]; then
        printf 'install_deps.sh does not install what the Makefile invokes: %s\n' \
            "${missing}" >&2
        return 1
    fi
}
