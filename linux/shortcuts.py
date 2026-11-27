"""Install per-user desktop entries, including the WSLg Start menu entries."""
import os
from pathlib import Path

here = Path(__file__).resolve().parent
apps = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "applications"
apps.mkdir(parents=True, exist_ok=True)
path = str(here / "viewer.py")
if any(ord(c) < 32 for c in path):
    raise SystemExit("Unsupported control character in checkout path")
# The desktop-entry value and the Exec argument each interpret backslashes.
path = "".join(("\\" + c) if c in '\\"$' + chr(96) else c for c in path)
path = path.replace("\\", "\\\\").replace("%", "%%")
for mode, name in (("claude", "Claude Workspace"), ("paperclip", "Paperclip Workspace"), ("browser", "Paperclip Browser")):
    (apps / ("claude-paperclip-" + mode + ".desktop")).write_text(
        f'[Desktop Entry]\nType=Application\nName={name}\nExec=/usr/bin/python3 "{path}" {mode}\n'
        'Terminal=false\nCategories=Development;\nIcon=applications-development\n', encoding="utf-8")
