#!/bin/bash
set -euo pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"
cd "$(dirname "$0")"
if [[ "$(uname -s)" == Darwin ]]; then
    state="$HOME/Library/Application Support/Paperclip Workspace"
else
    state="${XDG_STATE_HOME:-$HOME/.local/state}/claude-paperclip-workspace/paperclip"
fi
umask 077
mkdir -p "$state"
if [[ ! -f "$state/server.env" ]]; then
    temp=$(mktemp "$state/server.env.XXXXXX")
    for key in BETTER_AUTH_SECRET PAPERCLIP_TOOL_ACTION_SIGNING_SECRET; do
        printf '%s=%s\n' "$key" "$(openssl rand -hex 32)"
    done > "$temp"
    ln "$temp" "$state/server.env" || test -s "$state/server.env"
    unlink "$temp"
fi
. ./network-check.sh
lock_region "$PWD/$(basename "$0")" "$@"
load_region
check_host
select_engine
start_engine
compose=("${engine[@]}" compose --env-file "$state/server.env")
configure_region_compose paperclip
prepare_region
require_workload_exit "${compose[@]}" run --rm --no-deps -T --entrypoint curl paperclip
[[ "${1:-}" != --region-check ]] || exit 0
"${compose[@]}" up -d
healthy() {
    curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:43107/api/health 2>/dev/null |
        python3 -c 'import json,sys; sys.exit(json.load(sys.stdin).get("status") != "ok")' 2>/dev/null
}
for ((i=0; i<120; i++)); do
    if healthy; then break; fi
    sleep 1
done
healthy || { echo "Paperclip did not become ready."; exit 1; }
