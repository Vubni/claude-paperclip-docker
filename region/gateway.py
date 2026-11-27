"""Restricted HTTP CONNECT proxy and loopback viewer relay for an isolated Docker network."""
import asyncio
import bisect
import contextlib
import csv
import datetime as dt
import gzip
import io
import ipaddress
import json
import os
import re
import sys
import ssl
import time
from pathlib import Path
from urllib.parse import urlencode

from profile import COUNTRIES, hostname, public_ip


class CountryDB:
    def __init__(self, compressed):
        self.starts, self.ends, self.codes = [], [], []
        with gzip.open(io.BytesIO(compressed), "rt") as source:
            for start, end, code in csv.reader(source):
                if ":" in start:
                    continue
                left, right = int(ipaddress.IPv4Address(start)), int(ipaddress.IPv4Address(end))
                if left > right or (self.ends and left <= self.ends[-1]):
                    raise ValueError()
                self.starts.append(left)
                self.ends.append(right)
                self.codes.append(code)

    def country_for(self, address):
        number = int(ipaddress.IPv4Address(address))
        index = bisect.bisect_right(self.starts, number) - 1
        return self.codes[index] if index >= 0 and number <= self.ends[index] else None


def allowed_host(name, rules):
    hostname(name)
    return any(name == rule or (rule.startswith("*.") and name.endswith(rule[1:])) for rule in rules)


async def close(writer):
    writer.close()
    with contextlib.suppress(Exception):
        await asyncio.wait_for(writer.wait_closed(), 1)


async def pump(reader, writer):
    while chunk := await reader.read(65536):
        writer.write(chunk)
        await writer.drain()


class Gateway:
    def __init__(self, profile, service, port):
        self.p, self.service, self.port = profile, service, port
        self.db = None
        self.month = None
        self.until = 0
        self.writers = set()
        self.tls = ssl.create_default_context()

    def ready(self):
        try:
            # The launcher renews this in tmpfs after a fresh check on macOS.
            host_lease = float(Path("/tmp/mac-lease").read_text())
        except (ValueError, OSError):
            return False
        return time.monotonic() < min(host_lease, self.until)

    async def fetch(self, url, limit, timeout=8, headers=()):
        p = self.p
        proxy = f'{p["proxy_host"]}:{p["proxy_port"]}'
        cmd = ["curl", "--disable", "--silent", "--fail", "--noproxy", "", "--proxy",
               "https://" + proxy, "--resolve", proxy + ":" + p["proxy_ipv4"],
               "--max-time", str(timeout), "--max-filesize", str(limit), "--proto", "=https"]
        for header in headers:
            cmd.extend(["--header", header])
        proc = await asyncio.create_subprocess_exec(*cmd, url, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL, env={"PATH": "/usr/bin:/bin"})
        try:
            data, _ = await proc.communicate()
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
        if proc.returncode or len(data) > limit:
            raise ValueError()
        return data

    async def verify(self):
        trace = (await self.fetch("https://www.cloudflare.com/cdn-cgi/trace", 8192)).decode("ascii")
        if ([v[4:] for v in trace.splitlines() if v.startswith("loc=")] != [self.p["country"]]
                or [v[3:] for v in trace.splitlines() if v.startswith("ip=")] != [self.p["exit_ipv4"]]):
            raise ValueError()
        month = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m")
        if self.month != month:
            self.until = 0
            data = await self.fetch(f"https://download.db-ip.com/free/dbip-country-lite-{month}.csv.gz",
                                    48 * 1024 * 1024, 90)
            db = await asyncio.to_thread(CountryDB, data)
            if any(db.country_for(self.p[k]) != self.p["country"] for k in ("proxy_ipv4","exit_ipv4")):
                raise ValueError()
            self.db, self.month = db, month
            return  # Require a new exit check after the potentially long database download.
        self.until = time.monotonic() + 18
        Path("/tmp/exit-lease").write_text(str(self.until))

    async def monitor(self):
        while True:
            try:
                await self.verify()
            except (OSError, ValueError, EOFError, csv.Error, UnicodeError):
                self.until = 0
                Path("/tmp/exit-lease").unlink(missing_ok=True)
            await asyncio.sleep(5)

    async def enforce(self):
        while True:
            if not self.ready():
                for writer in tuple(self.writers):
                    writer.close()
            await asyncio.sleep(0.25)

    async def resolve(self, host):
        query = urlencode({"name":host, "type":"A"})
        data = json.loads(await self.fetch("https://cloudflare-dns.com/dns-query?" + query, 65536,
                                           headers=("Accept: application/dns-json",)))
        if data.get("Status") != 0 or data.get("TC") or not self.db:
            raise ValueError()
        for rr in data.get("Answer", []):
            if rr.get("type") == 1:
                addr = public_ip(rr["data"])
                if self.db.country_for(addr) in COUNTRIES:
                    return addr
        raise ValueError()

    async def connect(self, reader):
        request = await reader.readuntil(b"\r\n\r\n")
        line = request.split(b"\r\n", 1)[0].decode("ascii")
        match = re.fullmatch(r"CONNECT ([a-zA-Z0-9.-]+):443 HTTP/1\.[01]", line)
        if not match or not allowed_host(match[1].lower(), [*self.p["allow_hosts"], "www.cloudflare.com"]):
            raise ValueError()
        addr = await self.resolve(match[1].lower())
        if not self.ready():
            raise ValueError()
        upstream, writer = await asyncio.open_connection(self.p["proxy_ipv4"], self.p["proxy_port"],
                                ssl=self.tls, server_hostname=self.p["proxy_host"], limit=16384)
        try:
            writer.write(f"CONNECT {addr}:443 HTTP/1.1\r\nHost: {addr}:443\r\n\r\n".encode("ascii"))
            await writer.drain()
            response = await upstream.readuntil(b"\r\n\r\n")
            if not re.fullmatch(rb"HTTP/1\.[01] 200(?: [^\r\n]*)?", response.split(b"\r\n", 1)[0]):
                raise ValueError()
        except BaseException:
            writer.close()
            raise
        return upstream, writer

    async def handle(self, reader, writer, proxy):
        remote = None
        tasks = []
        self.writers.add(writer)
        try:
            if not self.ready():
                raise ValueError()
            async with asyncio.timeout(12):
                if proxy:
                    upstream, remote = await self.connect(reader)
                    if not self.ready():
                        raise ValueError()
                    writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                    await writer.drain()
                else:
                    upstream, remote = await asyncio.open_connection(self.service, self.port)
            self.writers.add(remote)
            if not self.ready():
                raise ValueError()
            tasks = [asyncio.create_task(pump(reader, remote)), asyncio.create_task(pump(upstream, writer))]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except (Exception, asyncio.CancelledError):
            pass  # Request URLs, peers and TLS diagnostics must stay out of the logs.
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            for stream in (writer, remote):
                if stream:
                    self.writers.discard(stream)
                    await close(stream)

    async def serve(self):
        # This alias exists only on the application's isolated network.
        await asyncio.start_server(lambda r,w: self.handle(r,w,True), "region-private", 3128, limit=16384)
        await asyncio.start_server(lambda r,w: self.handle(r,w,False), "0.0.0.0", self.port)
        await asyncio.gather(self.monitor(), self.enforce())


if __name__ == "__main__":
    if sys.argv[1:] == ["--ready"]:
        try:
            live = min(float(Path("/tmp/" + key).read_text()) for key in ("exit-lease", "mac-lease"))
        except (ValueError, OSError):
            sys.exit(1)
        sys.exit(0 if live > time.monotonic() else 1)
    gateway = Gateway(json.loads(os.environ["REGION_PROFILE"]), os.environ["REGION_SERVICE"],
                      int(os.environ["REGION_PORT"]))
    asyncio.run(gateway.serve())
