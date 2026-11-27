"""Keep a shared lock through launcher startup while the settings editor uses an exclusive lock."""
import fcntl
import os
from pathlib import Path
import subprocess
import sys
from profile import PROFILE


def profile_lock():
    PROFILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    return (PROFILE.parent / "profile.lock").open("a")


if __name__ == "__main__":
    with profile_lock() as handle:
        fcntl.flock(handle, fcntl.LOCK_SH)
        # The parent owns the lock. Daemonized lease monitors never inherit its descriptor.
        env = dict(os.environ, WORKSPACE_PROFILE_LOCKED="1")
        sys.exit(subprocess.call(["/bin/bash", *sys.argv[1:]], env=env))
