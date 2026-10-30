#!/usr/bin/env bash
# Regenerate the committed cosmic-ray sessions: fib init pair (tests/test_cosmic_ray_shard.py)
# and the executed crfix session (tests/test_cosmic_ray_cell_status.py).
# Usage: regen.sh <cosmic-ray-venv-bin-dir>
# Runs inside a temp copy of fib/; never inside the worktree's sub-project dirs,
# because cosmic-ray can mutate source in place.

FIXTURE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 1
REPO_ROOT="$(cd "${FIXTURE_DIR}/../../.." && pwd)" || exit 1
readonly FIXTURE_DIR REPO_ROOT

regen_init_sessions() {
    local venv_bin="${1:-}"
    if [[ -z "${venv_bin}" || ! -x "${venv_bin}/cosmic-ray" ]]; then
        printf 'usage: regen.sh <cosmic-ray-venv-bin-dir>\n' >&2
        return 1
    fi
    venv_bin="$(cd "${venv_bin}" && pwd)" || return 1
    (
        work="$(mktemp -d)" || exit 1
        trap 'rm -rf "${work}"' EXIT
        cp "${REPO_ROOT}/fib/fib.py" "${REPO_ROOT}/fib/test_fib.py" \
            "${REPO_ROOT}/fib/cosmic-ray.toml" "${work}/" || exit 1
        cd "${work}" || exit 1
        for name in a b; do
            "${venv_bin}/cosmic-ray" init cosmic-ray.toml "fib-init-${name}.sqlite" || exit 1
        done
        mkdir crfix || exit 1
        cp "${FIXTURE_DIR}/crfix.py" "${FIXTURE_DIR}/test_crfix.py" \
            "${FIXTURE_DIR}/cosmic-ray.toml" crfix/ || exit 1
        (
            cd crfix || exit 1
            "${venv_bin}/cosmic-ray" init cosmic-ray.toml ../crfix-exec.sqlite || exit 1
            # The exec session runs mutants; cap memory like the real recipe does.
            ulimit -v 4194304 || exit 1
            PATH="${venv_bin}:${PATH}" "${venv_bin}/cosmic-ray" exec cosmic-ray.toml \
                ../crfix-exec.sqlite || exit 1
        ) || exit 1
        # Copy only after every step succeeds so a failure never leaves a mismatched set.
        for name in a b; do
            cp "fib-init-${name}.sqlite" "${FIXTURE_DIR}/fib-init-${name}.sqlite" || exit 1
        done
        cp crfix-exec.sqlite "${FIXTURE_DIR}/crfix-exec.sqlite" || exit 1
    ) || return 1
}

main() {
    regen_init_sessions "$@" || return 1
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@" || exit 1
fi
