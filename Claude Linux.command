#!/bin/bash
set -eu
cd "$(dirname "$0")"
. "./Claude Workspace.source/Contents/Resources/network-check.sh"
lock_region "$PWD/$(basename "$0")" "$@"
load_region
check_host
select_engine
start_engine
cd "Claude Workspace.source/Contents/Resources"
compose=("${engine[@]}" compose)
configure_region_compose claude
prepare_region
require_workload_exit "${compose[@]}" run --rm --no-deps -T --entrypoint curl shell
exec "${compose[@]}" run --rm shell "$@"
