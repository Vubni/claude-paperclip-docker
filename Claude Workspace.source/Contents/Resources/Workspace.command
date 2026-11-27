#!/bin/bash
set -euo pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"
cd "$(dirname "$0")"
. ./network-check.sh
lock_region "$PWD/$(basename "$0")" "$@"
load_region
check_host
select_engine
start_engine
compose=("${engine[@]}" compose)
configure_region_compose claude
prepare_region
require_workload_exit "${compose[@]}" run --rm --no-deps -T --entrypoint curl shell
[[ "${1:-}" != --region-check ]] || exit 0
"${compose[@]}" up -d --no-deps desktop >&2 || exit 52
id=$("${compose[@]}" ps -aq desktop) || exit 52
[[ -n "$id" ]] || exit 52
for ((i=0; i<90; i++)); do
    state=$("${engine[@]}" inspect --format '{{.State.Status}} {{.State.ExitCode}} {{.State.Health.Status}}' "$id") || exit 52
    read -r status code health <<< "$state"
    if [[ "$status" == exited || "$status" == dead ]]; then
        case "$code" in
            61|62|63|64|65) exit "$code" ;;
            *) exit 66 ;;
        esac
    fi
    if [[ "$status" == running && "$health" == healthy ]]; then
        if [[ "${1:-}" == --viewer && ! -t 1 ]]; then
            port_service=desktop
            if [[ -n "$REGION_PROFILE" ]]; then port_service=region-gateway; fi
            address=$("${compose[@]}" port "$port_service" 6080)
            [[ "$address" =~ ^127\.0\.0\.1:([0-9]+)$ ]] || exit 1
            printf '%s\n' "${BASH_REMATCH[1]}"
            "${compose[@]}" exec -T desktop cat /tmp/claude-runtime/viewer-token
        fi
        exit 0
    fi
    sleep 1
done
echo "Linux desktop did not become ready." >&2
exit 67
