#!/bin/bash
# macOS on Apple Silicon, Docker Desktop and the Xcode command-line tools.
set -euo pipefail
cd "$(dirname "$0")"
root=$PWD
export PATH="/usr/local/bin:/opt/homebrew/bin:/Applications/Docker.app/Contents/Resources/bin:$PATH"
[[ "$(uname -sm)" == "Darwin arm64" ]] || { echo "Нужен Mac с Apple Silicon."; exit 1; }
xcrun --find swiftc >/dev/null
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
claude="$root/Claude Workspace.source/Contents/Resources"
paper="$root/Paperclip Workspace.source/Contents/Resources"
browser="$root/Paperclip Browser.source/Contents/Resources"
engine=(docker --context desktop-linux)
. "$claude/network-check.sh"
case "${1:-}" in
    ""|--launchers-only) ;;
    *) echo "Usage: Install.command [--launchers-only]" >&2; exit 2 ;;
esac
if [[ "${1:-}" != --launchers-only ]]; then
    load_region
    check_host
    "${engine[@]}" desktop start >/dev/null
    . "$root/build-images.sh"
fi

for name in 'Claude Workspace' 'Paperclip Workspace' 'Paperclip Browser'; do
    src="$root/$name.source/Contents"
    app="$stage/$name.app"
    mkdir -p "$app/Contents/MacOS"
    cp "$src/Info.plist" "$app/Contents/"
    rsync -a "$src/Resources/" "$app/Contents/Resources/"
    rsync -a --exclude=__pycache__ "$root/region/" "$app/Contents/Resources/region/"
    id=$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$src/Info.plist")
    ui=ClaudeLinuxUI
    if [[ "$name" == 'Paperclip Workspace' ]]; then ui=PaperclipUI; fi
    if [[ "$name" == 'Paperclip Browser' ]]; then
        cp "$claude"/{launcher.swift,network-check.sh,linux-edit.py} "$paper/Workspace.icns" "$app/Contents/Resources/"
        cp "$claude/../MacOS/launcher" "$app/Contents/MacOS/"
    else
        cp "$src/MacOS/launcher" "$app/Contents/MacOS/"
    fi
    swiftc -O -module-cache-path "$stage/modules" -target arm64-apple-macos14.0 "$app/Contents/Resources/launcher.swift" -o "$app/Contents/MacOS/$ui"
    codesign --force --sign - --identifier "$id.ui" "$app/Contents/MacOS/$ui"
    codesign --force --sign - --identifier "$id" "$app"
    codesign --verify --strict "$app"
done
# Check all destinations before installing. Preserve Finder's custom icons and the existing identifiers.
for name in 'Claude Workspace' 'Paperclip Workspace' 'Paperclip Browser'; do
    target="/Applications/$name.app"
    if [[ -e "$target" ]]; then
        installed_id=$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$target/Contents/Info.plist")
        expected_id=$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$stage/$name.app/Contents/Info.plist")
        [[ "$installed_id" == "$expected_id" ]] || { echo "Другое приложение занимает $target"; exit 1; }
    fi
done
for name in 'Claude Workspace' 'Paperclip Workspace' 'Paperclip Browser'; do
    target="/Applications/$name.app"
    mkdir -p "$target/Contents/Resources/region"
    # This directory holds only shipped code. User settings live in Application Support.
    rsync -a --checksum --delete "$stage/$name.app/Contents/Resources/region/" "$target/Contents/Resources/region/"
    rsync -a --checksum "$stage/$name.app/Contents/" "$target/Contents/"
    codesign --verify "$target"
done
echo "Готово. Откройте Paperclip Workspace или Claude Workspace из «Программ»."
