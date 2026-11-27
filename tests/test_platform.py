"""Check host selection and WSL fail-closed behavior without starting an engine."""
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PlatformTests(unittest.TestCase):
    def shell(self, script):
        return subprocess.run(
            ["bash", "-euo", "pipefail", "-c", '. "$1"; ' + script, "_", str(ROOT / "region/check.sh")],
            capture_output=True, text=True, env={"PATH": os.defpath}, timeout=5)

    def test_wsl_checks_windows_even_after_success_in_linux(self):
        result = self.shell("""
            WSL_DISTRO_NAME=Ubuntu REGION_PROFILE=""
            require_exit_country() { echo "$1"; [[ "$1" != curl.exe ]] || exit 43; }
            check_host
        """)
        self.assertEqual(result.stdout.splitlines(), ["/usr/bin/curl", "curl.exe"])
        self.assertEqual(result.returncode, 43)

    def test_linux_rejects_remote_docker_context(self):
        result = self.shell("""
            uname() { echo Linux; }
            is_wsl() { return 1; }
            docker() {
                case "$2" in show) echo remote;; inspect) echo ssh://remote.example;; esac
            }
            select_engine
        """)
        self.assertEqual(result.returncode, 51)

    def test_local_linux_engine_does_not_start_docker_desktop(self):
        result = self.shell("""
            uname() { echo Linux; }
            is_wsl() { return 1; }
            docker() {
                case "$1 $2" in
                    'context show') echo default;;
                    'context inspect') echo unix:///var/run/docker.sock;;
                    '--context default') [[ "$3" == info ]] && echo linux;;
                    *) return 1;;
                esac
            }
            select_engine
            start_engine
        """)
        self.assertEqual(result.returncode, 0)
