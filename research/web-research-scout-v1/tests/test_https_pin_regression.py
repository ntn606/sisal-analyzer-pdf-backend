"""Synthetic approved source, DNS and wire response; no external connections."""

import io
import socket
import ssl
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import Mock, call, create_autospec, patch

from support import NOW

from web_research_scout.collect import Collector, DomainBudget, HTTPSReader

HOST = "club.scout.example"
URL = "https://" + HOST + "/news"
PINS = {"1.1.1.1", "8.8.8.8"}
BODY = (
    b"<title>Synthetic club update</title>"
    b'<meta property="article:published_time" content="2026-10-11T21:00:00Z">'
)


def answers(addresses):
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
        for address in sorted(addresses)
    ]


class MemoryTLSSocket:
    """Only an in-memory HTTP response, never a socket or TLS connection."""

    def __init__(self):
        self.sent = []
        self.response = io.BytesIO(
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/html; charset=utf-8\r\n"
            b"Content-Length: " + str(len(BODY)).encode() + b"\r\n"
            b"Connection: close\r\n\r\n" + BODY
        )

    def sendall(self, data):
        self.sent.append(data)

    def makefile(self, mode):
        if mode != "rb":
            raise AssertionError("unexpected_http_stream_mode")
        return self.response

    def close(self):
        # HTTPResponse owns its separate stream even after connection close.
        pass


class HTTPSPinRegressionTests(unittest.TestCase):
    data_origin = "synthetic_approved_source_dns_http_and_tls_transport"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.budget = DomainBudget(temporary.name)
        self.sources = {
            "synthetic-club": {
                "hosts": [HOST],
                "resources": {"news": URL},
                "review_state": "approved",
                "metadata_retention_allowed": True,
                "minimum_interval_seconds": 5,
                "robots_review": {
                    "allowed_resources": ["news"],
                    "reviewed_at": (NOW - timedelta(hours=1)).isoformat(),
                    "valid_until": (NOW + timedelta(hours=1)).isoformat(),
                },
            }
        }
        self.resolver = Mock(side_effect=[answers(PINS), answers(PINS)])

    def collect(self, *, reader=None, live=True, resolver=None):
        return Collector(
            self.sources,
            self.budget,
            live=live,
            reader=reader,
            resolver=resolver if resolver is not None else self.resolver,
            clock=lambda: NOW,
        ).collect("synthetic-club", "news")

    def assert_two_approved_resolutions(self):
        self.assertEqual(
            self.resolver.call_args_list,
            [call(HOST, 443, type=socket.SOCK_STREAM)] * 2,
        )

    def test_collector_passes_exact_approved_addresses_to_reader(self):
        reader = create_autospec(HTTPSReader, instance=True)
        reader.read.return_value = (200, "text/html", BODY, None)

        result = self.collect(reader=reader)

        self.assertEqual(result["status"], "reported_unconfirmed")
        self.assertTrue(result["content_retrieved"])
        self.assert_two_approved_resolutions()
        reader.read.assert_called_once_with(
            URL, timeout=15, max_bytes=256_000, destination_addresses=PINS
        )

    def test_collector_real_reader_and_http_stack_use_public_pin_and_tls_hostname(self):
        # Use the real reader, urllib opener, HTTPS handler, HTTP connection and
        # socket.create_connection. Only the OS socket and TLS wire are mocked.
        # Literal-IP getaddrinfo is a local conversion, never hostname DNS.
        chosen = sorted(PINS)[0]
        raw_socket = Mock()
        tls_socket = MemoryTLSSocket()
        context = ssl.create_default_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

        def literal_ip_only(host, port, family=0, socktype=0):
            self.assertEqual(host, chosen)
            self.assertEqual(port, 443)
            self.assertEqual(socktype, socket.SOCK_STREAM)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (host, port))]

        with (
            patch("urllib.request.getproxies", return_value={}),
            patch("socket.getaddrinfo", side_effect=literal_ip_only) as conversion,
            patch("socket.socket", return_value=raw_socket) as socket_factory,
            patch("ssl.create_default_context", return_value=context) as ca_context,
            patch.object(context, "wrap_socket", return_value=tls_socket) as tls_wrap,
        ):
            result = self.collect(reader=HTTPSReader())

        self.assertEqual(result["status"], "reported_unconfirmed", result["reason"])
        self.assertTrue(result["content_retrieved"])
        self.assertEqual(result["title"], "Synthetic club update")
        self.assertEqual(result["http_status"], 200)
        self.assertFalse(result["automatic_claim_verification"])
        self.assert_two_approved_resolutions()
        # No third hostname lookup; the only additional getaddrinfo uses the IP.
        conversion.assert_called_once_with(chosen, 443, 0, socket.SOCK_STREAM)
        socket_factory.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM, 6)
        raw_socket.connect.assert_called_once_with((chosen, 443))
        raw_socket.settimeout.assert_called_once_with(15)
        tls_wrap.assert_called_once_with(raw_socket, server_hostname=HOST)
        ca_context.assert_called_once_with()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        request = b"".join(tls_socket.sent).lower()
        self.assertIn(("host: " + HOST).encode(), request)
        self.assertNotIn(b"authorization:", request)
        self.assertNotIn(b"cookie:", request)

    def test_private_mixed_mapped_or_changed_dns_blocks_real_reader(self):
        cases = [
            ([answers({"127.0.0.1"})], "private_destination_blocked"),
            ([answers({"169.254.169.254"})], "private_destination_blocked"),
            ([answers({"::ffff:8.8.8.8"})], "private_destination_blocked"),
            ([answers({"8.8.8.8", "10.0.0.1"})], "private_destination_blocked"),
            (
                [answers(PINS), answers({"9.9.9.9"})],
                "dns_changed_before_request",
            ),
            (
                [answers(PINS), answers({"169.254.169.254"})],
                "private_destination_blocked",
            ),
        ]
        for responses, reason in cases:
            with (
                self.subTest(reason=reason, responses=len(responses)),
                tempfile.TemporaryDirectory() as temporary,
                patch("urllib.request.build_opener") as opener,
                patch("socket.getaddrinfo", side_effect=AssertionError("no_extra_dns")),
                patch("socket.create_connection") as connection,
            ):
                self.budget = DomainBudget(temporary)
                resolver = Mock(side_effect=responses)
                reader = HTTPSReader()
                with patch.object(reader, "read", wraps=reader.read) as read:
                    result = self.collect(reader=reader, resolver=resolver)
                self.assertEqual(result["reason"], reason)
                self.assertFalse(result["content_retrieved"])
                self.assertEqual(resolver.call_count, len(responses))
                read.assert_not_called()
                opener.assert_not_called()
                connection.assert_not_called()

    def test_configured_proxy_still_blocks_real_reader_without_fallback(self):
        for scheme in ("https", "http", "all"):
            with (
                self.subTest(scheme=scheme),
                tempfile.TemporaryDirectory() as temporary,
                patch(
                    "urllib.request.getproxies",
                    return_value={scheme: "http://proxy.scout.example:8080"},
                ),
                patch("urllib.request.build_opener") as opener,
                patch("socket.getaddrinfo", side_effect=AssertionError("no_extra_dns")),
                patch("socket.create_connection") as connection,
            ):
                self.budget = DomainBudget(temporary)
                resolver = Mock(side_effect=[answers(PINS), answers(PINS)])
                result = self.collect(reader=HTTPSReader(), resolver=resolver)
                self.assertEqual(result["reason"], "proxy_target_integrity_unverified")
                self.assertFalse(result["content_retrieved"])
                self.assertEqual(resolver.call_count, 2)
                opener.assert_not_called()
                connection.assert_not_called()

    def test_default_live_disabled_before_dns_or_real_reader(self):
        reader = HTTPSReader()
        with (
            patch.object(reader, "read", wraps=reader.read) as read,
            patch("socket.getaddrinfo", side_effect=AssertionError("no_extra_dns")),
            patch("socket.create_connection") as connection,
        ):
            # Deliberately omit live: Collector's default must remain False.
            result = Collector(
                self.sources,
                self.budget,
                reader=reader,
                resolver=self.resolver,
                clock=lambda: NOW,
            ).collect("synthetic-club", "news")

        self.assertEqual(result["reason"], "live_disabled")
        self.assertFalse(result["content_retrieved"])
        self.resolver.assert_not_called()
        read.assert_not_called()
        connection.assert_not_called()
