#!/usr/bin/env bash
# Regenerate the committed cosmic-ray init sessions used by tests/test_cosmic_ray_shard.py.
# Usage: regen.sh <cosmic-ray-venv-bin-dir>
# Runs inside a temp copy of fib/; never inside the worktree's sub-project dirs,
# because cosmic-ray can mutate source in place.

readonly FIXTURE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${FIXTURE_DIR}/../../.." && pwd)"

regen_init_sessions() {
    local venv_bin="${1:-}"
    if [[ -z "${venv_bin}" || ! -x "${venv_bin}/cosmic-ray" ]]; then
        printf 'usage: regen.sh <cosmic-ray-venv-bin-dir>\n' >&2
        return 1
    fi
    (
        work="$(mktemp -d)" || exit 1
        trap 'rm -rf "${work}"' EXIT
        cp "${REPO_ROOT}/fib/fib.py" "${REPO_ROOT}/fib/test_fib.py" \
            "${REPO_ROOT}/fib/cosmic-ray.toml" "${work}/" || exit 1
        cd "${work}" || exit 1
        for local_name in a b; do
            "${venv_bin}/cosmic-ray" init cosmic-ray.toml "fib-init-${local_name}.sqlite" || exit 1
            cp "fib-init-${local_name}.sqlite" "${FIXTURE_DIR}/fib-init-${local_name}.sqlite" || exit 1
        done
    ) || return 1
}

main() {
    regen_init_sessions "$@" || return 1
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@" || exit 1
fi
