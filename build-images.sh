# Sourced by the platform installers after the host network check.
"${engine[@]}" compose -f "$claude/compose.yaml" build shell
shell_image=$("${engine[@]}" compose -f "$claude/compose.yaml" config --images shell)
require_exit_country "${engine[@]}" run --rm --entrypoint curl "$shell_image"
# Let Compose create and label its volume. Initialisation needs no network.
"${engine[@]}" compose -f "$claude/compose.yaml" -f - run --no-deps --rm -T shell mkdir -p /home/developer/projects <<'YAML'
services:
  shell:
    network_mode: none
YAML
if ! "${engine[@]}" image inspect local/claude-workspace-desktop:2 >/dev/null 2>&1; then
    "${engine[@]}" compose -f "$claude/compose.yaml" build desktop
fi
mkdir "$stage/browser-image"
cp "$browser"/{Dockerfile,start-browser,ready-browser} "$claude/desktop/viewer.html" "$stage/browser-image/"
"${engine[@]}" build -t local/paperclip-linux-browser:1 "$stage/browser-image"
paper_image=$(awk '$1=="image:" {print $2; exit}' "$paper/compose.yaml")
"${engine[@]}" build -t "$paper_image" "$paper/localization"
