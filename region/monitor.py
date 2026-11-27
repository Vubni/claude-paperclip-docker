"""Renew a short-lived grant in one exact container while the Mac matches its profile."""
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from profile import PROFILE, settings

DOCKER = ["docker", "--context", os.environ.get("WORKSPACE_DOCKER_CONTEXT", "desktop-linux")]
LEASE = """import os,time;from pathlib import Path;p=Path('/tmp/mac-lease.new');p.write_text(str(time.monotonic()+20));os.replace(p,'/tmp/mac-lease')"""


def run(args):
    return subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=12)


def monitor(container, digest):
    lock = PROFILE.parent / ("monitor-" + container + ".lock")
    with lock.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        while True:
            profile = settings()
            if hashlib.sha256(json.dumps(profile, separators=(",", ":")).encode()).hexdigest() != digest:
                break
            if run(DOCKER + ["inspect", "--format", "{{.State.Running}}", container]).stdout.strip() != b"true":
                return
            clients = ["/usr/bin/curl"]
            kernel = Path("/proc/sys/kernel/osrelease")
            if (os.environ.get("WSL_INTEROP") or os.environ.get("WSL_DISTRO_NAME")
                    or (kernel.is_file() and "microsoft" in kernel.read_text().lower())):
                clients.append("curl.exe")
            allowed = True
            for client in clients:
                check = run([client, "--disable", "--noproxy", "*", "-4", "--fail", "--silent",
                             "--max-time", "7", "https://www.cloudflare.com/cdn-cgi/trace"])
                codes = [line[4:] for line in check.stdout.splitlines() if line.startswith(b"loc=")]
                if check.returncode or codes != [profile["country"].encode()]:
                    allowed = False
                    break
            if not allowed:
                run(DOCKER + ["exec", container, "unlink", "/tmp/mac-lease"])
            elif run(DOCKER + ["exec", container, "python3", "-c", LEASE]).returncode:
                return
            time.sleep(5)
        run(DOCKER + ["exec", container, "unlink", "/tmp/mac-lease"])


if __name__ == "__main__":
    try:
        monitor(sys.argv[1], sys.argv[2])
    except (OSError, ValueError, subprocess.SubprocessError, TypeError):
        sys.exit(1)
