"""Read local settings as data. Only validated values cross the launcher boundary."""
import ipaddress
import json
import os
import re
import sys
from pathlib import Path

REGION = Path(__file__).resolve().parent
if sys.platform == "darwin":
    PROFILE = Path.home() / "Library/Application Support/Claude Paperclip Workspace/region.json"
else:
    PROFILE = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "claude-paperclip-workspace/region.json"
COUNTRIES = frozenset((REGION / "countries.txt").read_text().split()) - {"RU"}
LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
BLOCKED = {"ru", "su", "xn--p1ai", "xn--p1acf", "xn--80aswg", "xn--80adxhks", "moscow", "tatar"}


def hostname(value):
    if not isinstance(value, str) or len(value) > 253:
        raise ValueError()
    parts = value.split(".")
    if len(parts) < 2 or not all(LABEL.fullmatch(p) for p in parts):
        raise ValueError()
    if parts[-1] in BLOCKED or not re.search("[a-z]", parts[-1]):
        raise ValueError()
    return value


def public_ip(value):
    addr = ipaddress.IPv4Address(value)
    if not addr.is_global or addr.is_multicast or str(addr) != value:
        raise ValueError()
    return value


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def settings(path=PROFILE):
    try:
        data = json.loads(path.read_text(), object_pairs_hook=unique)
    except FileNotFoundError:
        if path.is_symlink():
            raise ValueError()
        return None
    if set(data) != {"country", "timezone", "exit_ipv4", "proxy_host", "proxy_ipv4", "proxy_port", "allow_hosts"}:
        raise ValueError()
    if data["country"] not in COUNTRIES:
        raise ValueError()
    zones = [line.split()[:3] for line in Path("/usr/share/zoneinfo/zone.tab").read_text().splitlines() if line and not line.startswith("#")]
    if not any(cc == data["country"] and zone == data["timezone"] for cc, _, zone in zones):
        raise ValueError()
    public_ip(data["exit_ipv4"])
    public_ip(data["proxy_ipv4"])
    hostname(data["proxy_host"])
    if type(data["proxy_port"]) is not int or not 1 <= data["proxy_port"] <= 65535:
        raise ValueError()
    hosts = data["allow_hosts"]
    if not isinstance(hosts, list) or not 1 <= len(hosts) <= 256:
        raise ValueError()
    for host in hosts:
        hostname(host[2:] if host.startswith("*.") else host)
    return data


if __name__ == "__main__":
    try:
        profile = settings()
        if profile:
            print(json.dumps(profile, separators=(",", ":")))
            print(profile["country"])
            print(profile["timezone"])
            print(profile["exit_ipv4"])
        else:
            print("default")
    except (ValueError, TypeError, AttributeError, KeyError, OSError):
        sys.exit(43)
