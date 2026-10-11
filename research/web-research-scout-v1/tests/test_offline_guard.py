"""Synthetic egress attempts MUST fail in CI, including child processes."""

import os
import socket
import subprocess
import sys
import unittest


class OfflineGuardTests(unittest.TestCase):
    data_origin = "synthetic_denied_network_attempts_no_packets"

    @unittest.skipUnless(
        os.environ.get("WEB_SCOUT_OFFLINE_TESTS") == "1", "requires guarded runner"
    )
    def test_dns_and_connections_for_all_provider_hosts_blocked(self):
        for host in (
            "www.newcastleunited.com",
            "landing.sisal.it",
            "v3.football.api-sports.io",
            "api.football-data.org",
        ):
            with (
                self.subTest(host=host),
                self.assertRaisesRegex(RuntimeError, "offline_dns_disabled"),
            ):
                socket.getaddrinfo(host, 443)
        with self.assertRaises(PermissionError):
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    @unittest.skipUnless(
        os.environ.get("WEB_SCOUT_OFFLINE_TESTS") == "1", "requires guarded runner"
    )
    def test_guard_inherited_by_cli_and_mcp_children(self):
        script = "import socket;socket.getaddrinfo('api.football-data.org',443)"
        child = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True, timeout=5
        )
        self.assertNotEqual(child.returncode, 0)
        self.assertIn("offline_dns_disabled", child.stderr)

    @unittest.skipUnless(
        os.environ.get("WEB_SCOUT_OFFLINE_TESTS") == "1", "requires guarded runner"
    )
    def test_native_socket_cannot_bypass_python_guard(self):
        import ctypes
        import errno

        libc = ctypes.CDLL(None, use_errno=True)
        result = libc.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        self.assertEqual(result, -1)
        self.assertEqual(ctypes.get_errno(), errno.EPERM)
        import platform

        if platform.machine() == "x86_64":
            self.assertEqual(
                libc.syscall(0x40000029, socket.AF_INET, socket.SOCK_STREAM, 0), -1
            )
            self.assertEqual(ctypes.get_errno(), errno.EPERM)
        self.assertEqual(libc.syscall(425, 1, 0), -1)
        self.assertEqual(ctypes.get_errno(), errno.EPERM)
