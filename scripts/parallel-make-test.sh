#!/usr/bin/env bash
# Runs `make -C <root>/<dir> test` for each <dir> concurrently and reports one
# ok/FAIL line per dir, in input order, followed by the full log of each failure.
#
# Usage: parallel-make-test.sh <jobs> <root> <dir>...
# Exit:  0 every dir passed, 1 any dir failed, 2 usage error.
#
# Each job writes its own exit status to a file rather than relying on xargs's
# exit code: xargs folds child failures into 123-125 and stops starting jobs on
# 255. A dir with no status file (the job was killed before writing it) is FAIL.
# Only flags that BSD xargs also supports are used (-0, -P, -I).

print_usage() {
    printf "usage: parallel-make-test.sh <jobs> <root> <dir>...\n" >&2
}

# Runs the jobs and prints the report. Called inside a subshell that owns the
# temp directory, so the EXIT trap fires once, when that subshell ends.
run_suites() {
    local jobs="$1" root="$2" tmp="$3"
    shift 3
    local dir name status failed=0

    # stdin is /dev/null for every suite: Python multiprocessing's
    # resource_tracker must not inherit git's push pipe and deadlock.
    printf '%s\0' "$@" | xargs -0 -P "${jobs}" -I{} bash -c \
        'name="${2//\//_}"; make -C "$1/$2" test </dev/null >"$3/${name}.log" 2>&1; printf "%s\n" "$?" >"$3/${name}.status"' \
        _ "${root}" {} "${tmp}"
    # xargs's own exit code is deliberately ignored; the status files decide.

    for dir in "$@"; do
        name="${dir//\//_}"
        status=""
        if [[ -f "${tmp}/${name}.status" ]]; then
            read -r status < "${tmp}/${name}.status"
        fi
        if [[ "${status}" == "0" ]]; then
            printf "ok %s\n" "${dir}"
        else
            printf "FAIL %s\n" "${dir}"
            failed=1
        fi
    done

    if [[ "${failed}" -eq 1 ]]; then
        for dir in "$@"; do
            name="${dir//\//_}"
            status=""
            [[ -f "${tmp}/${name}.status" ]] && read -r status < "${tmp}/${name}.status"
            [[ "${status}" == "0" ]] && continue
            printf "\n==== log: %s ====\n" "${dir}"
            if [[ -f "${tmp}/${name}.log" ]]; then
                cat "${tmp}/${name}.log"
            else
                printf "(no log written)\n"
            fi
        done
        return 1
    fi
    return 0
}

main() {
    local jobs root
    if [[ "$#" -lt 3 ]]; then
        print_usage
        return 2
    fi
    jobs="$1"
    root="$2"
    shift 2
    if [[ ! "${jobs}" =~ ^[1-9][0-9]*$ ]]; then
        printf "parallel-make-test.sh: jobs must be a positive integer, got '%s'\n" "${jobs}" >&2
        print_usage
        return 2
    fi

    (
        tmp="$(mktemp -d)" || exit 1
        trap 'rm -rf -- "${tmp}"' EXIT
        run_suites "${jobs}" "${root}" "${tmp}" "$@"
    )
}

[[ "${BASH_SOURCE[0]}" != "${0}" ]] && return 0
main "$@"
exit "$?"
