#!/bin/bash
set -euo pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"
script=$(cd "$(dirname "$0")" && pwd)/open-linux-link.sh
if [[ "$(uname -s)" == Darwin ]]; then
    browser="/Applications/Paperclip Browser.app"
    cd "$browser/Contents/Resources"
    . ./network-check.sh
else
    root=$(cd "$(dirname "$script")/../../.." && pwd)
    cd "$root/Paperclip Browser.source/Contents/Resources"
    REGION_DIR="$root/region"
    . "$REGION_DIR/check.sh"
fi
lock_region "$script" "$@"
IFS= read -r url
[[ "$url" == https://* ]] || exit 1
/usr/bin/python3 -B "$REGION_DIR/link.py" <<< "$url" || exit 43
./Workspace.command </dev/null >/dev/null
select_engine
compose=("${engine[@]}" compose)
load_region
configure_region_compose browser
require_workload_exit "${compose[@]}" exec -T desktop curl
printf '%s\n' "$url" | "${compose[@]}" exec -T desktop sh -ec '
    IFS= read -r url
    export DBUS_SESSION_BUS_ADDRESS="$(cat "$XDG_RUNTIME_DIR/browser-bus")"
    exec firefox-esr --private-window "$url"
' >/dev/null 2>&1
if [[ "$(uname -s)" == Darwin ]]; then /usr/bin/open -a "$browser"; fi
