# Shared by native macOS launchers, Linux and WSL 2.
is_wsl() {
    [[ -n "${WSL_INTEROP:-}" || -n "${WSL_DISTRO_NAME:-}" ]] ||
        { [[ -r /proc/sys/kernel/osrelease ]] && grep -qi microsoft /proc/sys/kernel/osrelease; }
}

select_engine() {
    WORKSPACE_DOCKER_CONTEXT=desktop-linux
    if [[ "$(uname -s)" == Linux ]]; then
        if is_wsl && ! docker info --format '{{.OSType}}' >/dev/null 2>&1; then
            docker.exe desktop start >/dev/null 2>&1 || return 51
        fi
        WORKSPACE_DOCKER_CONTEXT=$(docker context show) || return 51
        local endpoint
        endpoint=$(docker context inspect "$WORKSPACE_DOCKER_CONTEXT" --format '{{.Endpoints.docker.Host}}') || return 51
        [[ "$endpoint" == unix:///* ]] || { echo "Select a local Docker context." >&2; return 51; }
    fi
    export WORKSPACE_DOCKER_CONTEXT
    engine=(docker --context "$WORKSPACE_DOCKER_CONTEXT")
}

start_engine() {
    if [[ "$(uname -s)" == Darwin || "$WORKSPACE_DOCKER_CONTEXT" == desktop-linux ]]; then
        "${engine[@]}" desktop start >/dev/null || return 51
    fi
    "${engine[@]}" info --format '{{.OSType}}' 2>/dev/null | grep -qx linux ||
        { echo "Start your local Linux Docker engine and retry." >&2; return 51; }
}

lock_region() {
    if [[ "${WORKSPACE_PROFILE_LOCKED:-}" != 1 ]]; then
        exec /usr/bin/python3 -B "$REGION_DIR/locked.py" "$@"
    fi
}
region_error() {
    echo "Region policy blocked startup. Check the settings, VPN and gateway." >&2
    exit 43
}

check_exit_country() {
    local trace country ip
    trace=$("$@" --disable --fail --silent --max-time 10 https://www.cloudflare.com/cdn-cgi/trace 2>/dev/null) || return 1
    country=$(printf '%s\n' "$trace" | LC_ALL=C awk '/^loc=/{n++; sub(/\r$/, ""); value=substr($0,5)} END{if(n!=1 || value !~ /^[A-Z][A-Z]$/) exit 1; print value}') || return 1
    if [[ -n "${region_expected_exit:-}" ]]; then
        ip=$(printf '%s\n' "$trace" | LC_ALL=C awk '/^ip=/{n++; sub(/\r$/, ""); value=substr($0,4)} END{if(n!=1) exit 1; print value}') || return 1
        [[ "$ip" == "$region_expected_exit" ]] || return 1
    fi
    [[ "$country" != RU ]] && grep -Fxq "$country" "$REGION_DIR/countries.txt" &&
        [[ -z "${WORKSPACE_COUNTRY:-}" || "$country" == "$WORKSPACE_COUNTRY" ]]
}

require_exit_country() {
    check_exit_country "$@" || region_error
}

require_workload_exit() {
    local region_expected_exit="${WORKSPACE_EXIT_IPV4:-}"
    require_exit_country "$@"
}

load_region() {
    local result
    result=$(/usr/bin/python3 -B "$REGION_DIR/profile.py") || region_error
    REGION_PROFILE= WORKSPACE_COUNTRY= WORKSPACE_TZ= WORKSPACE_EXIT_IPV4= REGION_DIGEST=
    if [[ "$result" != default ]]; then
        REGION_PROFILE=$(sed -n '1p' <<< "$result")
        WORKSPACE_COUNTRY=$(sed -n '2p' <<< "$result")
        WORKSPACE_TZ=$(sed -n '3p' <<< "$result")
        WORKSPACE_EXIT_IPV4=$(sed -n '4p' <<< "$result")
        REGION_DIGEST=$(printf %s "$REGION_PROFILE" | shasum -a 256 | cut -d' ' -f1)
    fi
    export REGION_DIR REGION_PROFILE WORKSPACE_COUNTRY WORKSPACE_TZ REGION_DIGEST
}

check_host() {
    if [[ -n "$REGION_PROFILE" ]]; then
        require_exit_country /usr/bin/curl --disable --noproxy '*' -4
    else
        require_exit_country /usr/bin/curl
    fi
    if is_wsl; then
        require_exit_country curl.exe --disable --noproxy '*' -4
    fi
}

configure_region_compose() {
    [[ -n "$REGION_PROFILE" ]] || return 0
    REGION_SERVICE=desktop REGION_PORT=6080 REGION_HOST_PORT=
    compose+=(-f "$PWD/compose.yaml" -f "$REGION_DIR/gateway.yaml")
    case "$1" in
        claude) compose+=(-f "$REGION_DIR/desktop.yaml" -f "$REGION_DIR/shell.yaml")
                export REGION_DESKTOP_BASE=local/claude-workspace-desktop:2 REGION_DESKTOP_IMAGE=local/workspace-strict-claude:1 ;;
        browser) compose+=(-f "$REGION_DIR/desktop.yaml")
                 export REGION_DESKTOP_BASE=local/paperclip-linux-browser:1 REGION_DESKTOP_IMAGE=local/workspace-strict-browser:1 ;;
        paperclip) REGION_SERVICE=paperclip REGION_PORT=43107 REGION_HOST_PORT=43107
                   compose+=(-f "$REGION_DIR/paperclip.yaml") ;;
        *) region_error ;;
    esac
    export REGION_SERVICE REGION_PORT REGION_HOST_PORT
}

prepare_region() {
    local name id active digest
    if [[ -z "$REGION_PROFILE" ]]; then
        # A removed or unavailable profile must not downgrade a live strict installation.
        active=$("${engine[@]}" ps -q --filter label=workspace.region.profile) || region_error
        [[ -z "$active" ]] || region_error
        return 0
    fi
    # Switching policy is explicit. Never silently replace a live, unprotected workspace.
    for name in claude-english paperclip-workspace paperclip-browser; do
        active=$("${engine[@]}" ps -q --filter "label=com.docker.compose.project=$name") || region_error
        for id in $active; do
            digest=$("${engine[@]}" inspect --format '{{index .Config.Labels "workspace.region.profile"}}' "$id") || region_error
            [[ "$digest" == "$REGION_DIGEST" ]] || region_error
        done
    done
    if [[ "$REGION_SERVICE" == desktop ]]; then
        "${compose[@]}" build desktop >/dev/null 2>&1 || region_error
    fi
    "${compose[@]}" up --build -d --no-deps region-gateway >/dev/null 2>&1 || region_error
    id=$("${compose[@]}" ps -q region-gateway) || region_error
    [[ -n "$id" ]] || region_error
    # Disconnected from the GUI process so its short lease survives closing the window.
    nohup /usr/bin/python3 -B "$REGION_DIR/monitor.py" "$id" "$REGION_DIGEST" </dev/null >/dev/null 2>&1 &
    local i
    for ((i=0; i<160; i++)); do
        if "${engine[@]}" exec "$id" python3 -B /opt/region/gateway.py --ready >/dev/null 2>&1; then return 0; fi
        sleep 1
    done
    region_error
}
