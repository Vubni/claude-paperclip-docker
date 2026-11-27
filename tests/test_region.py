import asyncio
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from region import profile

# The standalone gateway imports the sibling module as "profile" in its image.
with patch.dict(sys.modules, {"profile": profile}):
    from region import gateway


ROOT = Path(__file__).resolve().parents[1]
NETWORK_CHECK = ROOT / "Claude Workspace.source/Contents/Resources/network-check.sh"


class ProfileTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "region.json"
        # These are fixture values. The validator never connects to either address.
        self.data = {
            "country": "PL",
            "timezone": "Europe/Warsaw",
            "exit_ipv4": "192.0.0.9",
            "proxy_host": "proxy.example.com",
            "proxy_ipv4": "192.0.0.10",
            "proxy_port": 443,
            "allow_hosts": ["claude.ai", "*.anthropic.com"],
        }

    def write_profile(self, **overrides):
        self.path.write_text(json.dumps({**self.data, **overrides}), encoding="utf-8")

    def test_absent_profile_keeps_default(self):
        self.assertIsNone(profile.settings(self.path))

    def test_dangling_profile_symlink_is_invalid(self):
        self.path.symlink_to(self.path.with_name("missing.json"))
        with self.assertRaises(ValueError):
            profile.settings(self.path)

    def test_profile_accepts_country_timezone_exact_hosts_and_subdomains(self):
        self.write_profile()
        self.assertTrue(profile.settings(self.path) == self.data, "valid profile changed")

    def test_rejects_duplicate_keys(self):
        encoded = json.dumps(self.data)
        self.path.write_text(encoded[:-1] + ', "country": "PL"}', encoding="utf-8")
        with self.assertRaises(ValueError):
            profile.settings(self.path)

    def test_rejects_unexpected_fields(self):
        self.write_profile(extra="unexpected")
        with self.assertRaises(ValueError):
            profile.settings(self.path)

    def test_rejects_country_and_timezone_mismatch(self):
        self.write_profile(timezone="Europe/Berlin")
        with self.assertRaises(ValueError):
            profile.settings(self.path)

    def test_rejects_blocked_unknown_and_lowercase_countries(self):
        for country, timezone in (
            ("RU", "Europe/Moscow"),
            ("AA", "Europe/Warsaw"),
            ("XX", "Europe/Warsaw"),
            ("ZZ", "Europe/Warsaw"),
            ("pl", "Europe/Warsaw"),
        ):
            with self.subTest(country=country):
                self.write_profile(country=country, timezone=timezone)
                with self.assertRaises(ValueError):
                    profile.settings(self.path)

    def test_rejects_non_host_proxy_strings(self):
        for label, value in {
            "scheme": "https://proxy.example.com",
            "path": "proxy.example.com/path",
            "authentication": "user@proxy.example.com",
            "command": "proxy.example.com; command",
            "wildcard": "*.example.com",
            "blocked country domain": "proxy.example.ru",
        }.items():
            with self.subTest(case=label):
                self.write_profile(proxy_host=value)
                with self.assertRaises(ValueError):
                    profile.settings(self.path)

    def test_rejects_invalid_allowed_hosts(self):
        for label, value in {
            "empty": [],
            "oversized": ["example.com"] * 257,
            "scalar": "example.com",
            "wildcard suffix": ["example.*"],
            "wildcard only": ["*"],
            "embedded wildcard": ["api.*.example.com"],
            "newline": ["example.com\nproxy.example.com"],
            "blocked country domain": ["*.example.xn--p1ai"],
        }.items():
            with self.subTest(case=label):
                self.write_profile(allow_hosts=value)
                with self.assertRaises(ValueError):
                    profile.settings(self.path)

    def test_rejects_invalid_ports(self):
        for port in (0, 65536, True, "443"):
            with self.subTest(port=port):
                self.write_profile(proxy_port=port)
                with self.assertRaises(ValueError):
                    profile.settings(self.path)

    def test_both_addresses_require_canonical_public_ipv4(self):
        for field in ("exit_ipv4", "proxy_ipv4"):
            for label, value in {
                "loopback": "127.0.0.1",
                "private": "10.0.0.1",
                "carrier NAT": "100.64.0.1",
                "documentation": "192.0.2.1",
                "multicast": "224.0.0.1",
                "ipv6": "::1",
                "noncanonical": "192.000.000.009",
                "command": "192.0.0.9; command",
            }.items():
                with self.subTest(field=field, case=label):
                    self.write_profile(**{field: value})
                    with self.assertRaises(ValueError):
                        profile.settings(self.path)


class CountryCheckTests(unittest.TestCase):
    def check(self, response, expected_country="", curl_status=0, expected_ip=""):
        env = {
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "REGION_DIR": str(ROOT / "region"),
            "WORKSPACE_COUNTRY": expected_country,
            "TEST_TRACE": response,
            "WORKSPACE_EXIT_IPV4": expected_ip,
            "TEST_CURL_STATUS": str(curl_status),
        }
        return subprocess.run(
            [
                "/bin/bash", "-euo", "pipefail", "-c",
                """
                source "$1"
                fake_curl() {
                    printf '%s' "$TEST_TRACE"
                    return "$TEST_CURL_STATUS"
                }
                require_workload_exit fake_curl
                """,
                "country-check-test", str(NETWORK_CHECK),
            ],
            cwd=NETWORK_CHECK.parent,
            env=env,
            capture_output=True,
            timeout=5,
        )

    def assert_blocked(self, response, expected_country="", curl_status=0):
        result = self.check(response, expected_country, curl_status)
        self.assertEqual(result.returncode, 43)
        self.assertFalse(result.stdout, "country check emitted a response body")

    def test_accepts_valid_country_without_profile(self):
        self.assertEqual(self.check("loc=PL\n").returncode, 0)
        self.assertEqual(self.check("loc=DE\r\n").returncode, 0)

    def test_requires_configured_country(self):
        self.assertEqual(self.check("loc=PL\n", "PL").returncode, 0)
        self.assert_blocked("loc=DE\n", "PL")
        self.assert_blocked("loc=RU\n", "RU")

    def test_rejects_unknown_malformed_and_repeated_country_records(self):
        for label, response in {
            "blocked": "loc=RU\n",
            "unknown": "loc=XX\n",
            "unassigned": "loc=AA\n",
            "user assigned": "loc=ZZ\n",
            "missing": "other=PL\n",
            "empty": "loc=\n",
            "lowercase": "loc=pl\n",
            "padding": "loc=PL \n",
            "identical duplicate": "loc=PL\nloc=PL\n",
            "conflicting duplicate": "loc=PL\nloc=RU\n",
            "trailing empty duplicate": "loc=PL\nloc=\n",
        }.items():
            with self.subTest(case=label):
                self.assert_blocked(response)
                self.assert_blocked(response, "PL")

    def test_workload_requires_one_matching_exit_address_when_pinned(self):
        address = "192.0.2.5"
        self.assertEqual(self.check(f"loc=PL\nip={address}\n", "PL", expected_ip=address).returncode, 0)
        for address_fields in ("", "ip=192.0.2.6", f"ip={address}\nip="):
            with self.subTest(address_fields=bool(address_fields)):
                result = self.check("loc=PL\n" + address_fields, "PL", expected_ip=address)
                self.assertEqual(result.returncode, 43)
                self.assertFalse(result.stdout)

    def test_rejects_transport_failure_even_with_valid_record(self):
        for status in (6, 22, 28):
            with self.subTest(curl_status=status):
                self.assert_blocked("loc=PL\n", "PL", status)


class CountryDBTests(unittest.TestCase):
    def test_returns_country_only_within_inclusive_ranges(self):
        db = gateway.CountryDB(gzip.compress(
            b"192.0.0.9,192.0.0.10,PL\n192.0.0.13,192.0.0.14,RU\n"
        ))
        self.assertIsNone(db.country_for("192.0.0.8"))
        self.assertEqual(db.country_for("192.0.0.9"), "PL")
        self.assertEqual(db.country_for("192.0.0.10"), "PL")
        self.assertIsNone(db.country_for("192.0.0.11"))
        self.assertEqual(db.country_for("192.0.0.14"), "RU")
        self.assertIsNone(db.country_for("192.0.0.15"))

    def test_rejects_overlapping_or_reversed_ranges(self):
        for label, rows in {
            "overlap": b"192.0.0.9,192.0.0.10,PL\n192.0.0.10,192.0.0.11,DE\n",
            "reversed": b"192.0.0.10,192.0.0.9,PL\n",
        }.items():
            with self.subTest(case=label), self.assertRaises(ValueError):
                gateway.CountryDB(gzip.compress(rows))

    def test_wildcard_matches_labels_below_suffix(self):
        rules = ["claude.ai", "*.anthropic.com"]
        self.assertTrue(gateway.allowed_host("claude.ai", rules))
        self.assertTrue(gateway.allowed_host("api.anthropic.com", rules))
        self.assertFalse(gateway.allowed_host("anthropic.com", rules))
        self.assertFalse(gateway.allowed_host("fakeanthropic.com", rules))
        self.assertFalse(gateway.allowed_host("api.anthropic.com.example", rules))


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.exit = "192.0.0.9"
        self.proxy = "192.0.0.10"
        self.destination = "192.88.99.2"
        self.gateway = gateway.Gateway(
            {
                "country": "PL",
                "exit_ipv4": self.exit,
                "proxy_ipv4": self.proxy,
                "proxy_host": "proxy.example.com",
                "proxy_port": 443,
                "allow_hosts": ["*.anthropic.com"],
            },
            "service",
            6080,
        )
        self.gateway.db = Mock()

    def trace(self, country="PL", address=None):
        return f"loc={country}\nip={address or self.exit}\n".encode()

    def test_ready_requires_both_current_leases(self):
        for host_until, docker_until, expected in (
            ("120", 120, True),
            ("100", 120, False),
            ("120", 100, False),
            ("invalid", 120, False),
        ):
            with self.subTest(host_until=host_until, docker_until=docker_until):
                self.gateway.until = docker_until
                with (
                    patch.object(gateway, "Path", return_value=Mock(read_text=Mock(return_value=host_until))),
                    patch.object(gateway.time, "monotonic", return_value=100),
                ):
                    self.assertIs(self.gateway.ready(), expected)

    async def test_verify_rejects_wrong_country_wrong_address_and_duplicates(self):
        for label, response in {
            "wrong country": self.trace(country="DE"),
            "blocked country": self.trace(country="RU"),
            "unknown country": self.trace(country="XX"),
            "wrong address": self.trace(address=self.proxy),
            "duplicate country": self.trace() + b"loc=\n",
            "duplicate address": self.trace() + b"ip=\n",
        }.items():
            with self.subTest(case=label), patch.object(self.gateway, "fetch", AsyncMock(return_value=response)):
                with self.assertRaises(ValueError):
                    await self.gateway.verify()
                self.assertEqual(self.gateway.until, 0)

    async def test_verify_checks_exit_and_proxy_in_country_database(self):
        for exit_country, proxy_country in (("RU", "PL"), ("PL", "DE"), ("PL", "XX")):
            with self.subTest(exit_country=exit_country, proxy_country=proxy_country):
                rows = f"{self.exit},{self.exit},{exit_country}\n{self.proxy},{self.proxy},{proxy_country}\n"
                fetch = AsyncMock(side_effect=[self.trace(), gzip.compress(rows.encode())])
                with patch.object(self.gateway, "fetch", fetch), self.assertRaises(ValueError):
                    await self.gateway.verify()
                self.assertEqual(self.gateway.until, 0)

    async def test_fresh_database_requires_second_exit_check_before_renewal(self):
        rows = f"{self.exit},{self.proxy},PL\n"
        fetch = AsyncMock(side_effect=[self.trace(), gzip.compress(rows.encode()), self.trace()])
        with patch.object(self.gateway, "fetch", fetch):
            await self.gateway.verify()
            self.assertEqual(self.gateway.until, 0)
            await self.gateway.verify()
        self.assertGreater(self.gateway.until, time.monotonic())

    async def test_monitor_retracts_unexpired_lease_after_failed_verification(self):
        self.gateway.until = time.monotonic() + 18
        verify = AsyncMock(side_effect=ValueError)
        stop_after_first_check = AsyncMock(side_effect=asyncio.CancelledError)
        with (
            patch.object(self.gateway, "verify", verify),
            patch.object(gateway.asyncio, "sleep", stop_after_first_check),
            self.assertRaises(asyncio.CancelledError),
        ):
            await self.gateway.monitor()
        verify.assert_awaited_once()
        self.assertEqual(self.gateway.until, 0)

    async def test_resolve_rejects_private_blocked_and_unknown_destinations(self):
        for label, address, country in (
            ("private", "10.0.0.1", "PL"),
            ("blocked", self.destination, "RU"),
            ("unknown", self.destination, "AA"),
            ("no match", self.destination, None),
        ):
            with self.subTest(case=label):
                self.gateway.db.country_for.return_value = country
                response = json.dumps({"Status": 0, "Answer": [{"type": 1, "data": address}]}).encode()
                with patch.object(self.gateway, "fetch", AsyncMock(return_value=response)):
                    with self.assertRaises(ValueError):
                        await self.gateway.resolve("api.anthropic.com")

    async def test_resolve_accepts_public_destination_with_assigned_country(self):
        self.gateway.db.country_for.return_value = "DE"
        fetch = AsyncMock(return_value=json.dumps({
            "Status": 0,
            "Answer": [{"type": 1, "data": self.destination}],
        }).encode())
        with patch.object(self.gateway, "fetch", fetch):
            address = await self.gateway.resolve("api.anthropic.com")
        self.assertTrue(address == self.destination, "unexpected validated destination")

    async def test_resolve_rejects_dns_errors_and_truncation(self):
        self.gateway.db.country_for.return_value = "DE"
        answers = [{"type": 1, "data": self.destination}]
        for status, truncated in ((3, False), (0, True)):
            with self.subTest(status=status, truncated=truncated):
                data = json.dumps({"Status": status, "TC": truncated, "Answer": answers}).encode()
                with patch.object(self.gateway, "fetch", AsyncMock(return_value=data)):
                    with self.assertRaises(ValueError):
                        await self.gateway.resolve("api.anthropic.com")
        self.gateway.db.country_for.assert_not_called()

    def request(self, authority):
        reader = asyncio.StreamReader()
        reader.feed_data(f"CONNECT {authority} HTTP/1.1\r\n\r\n".encode())
        reader.feed_eof()
        return reader

    async def test_connect_rejects_outside_allowlist_before_dns(self):
        for authority in ("other.example.com:443", "anthropic.com:443", "api.anthropic.com:80"):
            with self.subTest(authority=authority):
                resolve = AsyncMock()
                with patch.object(self.gateway, "resolve", resolve):
                    with self.assertRaises(ValueError):
                        await self.gateway.connect(self.request(authority))
                resolve.assert_not_awaited()

    async def test_connect_pins_both_proxy_and_destination_addresses(self):
        response = asyncio.StreamReader()
        response.feed_data(b"HTTP/1.1 200 Connection established\r\n\r\n")
        writer = Mock(drain=AsyncMock())
        resolve = AsyncMock(return_value=self.destination)
        open_connection = AsyncMock(return_value=(response, writer))
        with (
            patch.object(self.gateway, "ready", return_value=True),
            patch.object(self.gateway, "resolve", resolve),
            patch.object(gateway.asyncio, "open_connection", open_connection),
        ):
            self.assertEqual(
                await self.gateway.connect(self.request("API.ANTHROPIC.COM:443")),
                (response, writer),
            )
        resolve.assert_awaited_once_with("api.anthropic.com")
        args, kwargs = open_connection.await_args
        self.assertTrue(args == (self.proxy, 443), "proxy socket was not pinned")
        self.assertEqual(kwargs["server_hostname"], "proxy.example.com")
        self.assertIs(kwargs["ssl"], self.gateway.tls)
        expected = f"CONNECT {self.destination}:443 HTTP/1.1\r\nHost: {self.destination}:443\r\n\r\n".encode()
        self.assertTrue(writer.write.call_args.args == (expected,), "CONNECT was not pinned")

    async def test_expired_lease_revokes_active_tunnel(self):
        ready = True
        client = asyncio.StreamReader()
        upstream = asyncio.StreamReader()
        started = asyncio.Event()
        finished = asyncio.Event()
        client_writer = Mock(drain=AsyncMock(side_effect=started.set), wait_closed=AsyncMock())
        upstream_writer = Mock(wait_closed=AsyncMock())
        client_writer.close.side_effect = client.feed_eof
        upstream_writer.close.side_effect = upstream.feed_eof

        async def handle():
            await self.gateway.handle(client, client_writer, True)
            finished.set()

        with (
            patch.object(self.gateway, "ready", side_effect=lambda: ready),
            patch.object(self.gateway, "connect", AsyncMock(return_value=(upstream, upstream_writer))),
        ):
            handler = asyncio.create_task(handle())
            enforcer = asyncio.create_task(self.gateway.enforce())
            try:
                await asyncio.wait_for(started.wait(), 2)
                self.assertIn(upstream_writer, self.gateway.writers)
                ready = False
                await asyncio.wait_for(finished.wait(), 2)
            finally:
                handler.cancel()
                enforcer.cancel()
                await asyncio.gather(handler, enforcer, return_exceptions=True)
        self.assertTrue(client_writer.close.called)
        self.assertTrue(upstream_writer.close.called)
        self.assertFalse(self.gateway.writers)


if __name__ == "__main__":
    unittest.main()
