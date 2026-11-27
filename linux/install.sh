#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
root=$PWD
[[ $(uname -s) == Linux && $EUID != 0 ]] || { echo "Run as your desktop user on Linux or in WSL 2." >&2; exit 1; }
/usr/bin/python3 -c 'from PyQt6.QtWebEngineWidgets import QWebEngineView' ||
    { echo "Install python3-pyqt6.qtwebengine first (see README)." >&2; exit 1; }
claude="$root/Claude Workspace.source/Contents/Resources"
paper="$root/Paperclip Workspace.source/Contents/Resources"
browser="$root/Paperclip Browser.source/Contents/Resources"
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
. "$claude/network-check.sh"
load_region
check_host
select_engine
start_engine
. "$root/build-images.sh"
/usr/bin/python3 "$root/linux/shortcuts.py"
echo "Ready. Open Claude Workspace or Paperclip Workspace from the applications menu."
