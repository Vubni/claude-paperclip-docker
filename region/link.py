import sys
from urllib.parse import urlsplit
from profile import BLOCKED, hostname, settings

try:
    url = urlsplit(sys.stdin.readline().rstrip("\n"))
    if url.scheme != "https" or url.username is not None or url.password is not None:
        raise ValueError()
    name = (url.hostname or "").rstrip(".").encode("idna").decode("ascii")
    if not name or name.split(".")[-1] in BLOCKED:
        raise ValueError()
    policy = settings()
    if policy:
        from gateway import allowed_host
        if url.port not in (443, None) or not allowed_host(hostname(name), policy["allow_hosts"]):
            raise ValueError()
except (ValueError, OSError, TypeError, UnicodeError):
    sys.exit(43)
