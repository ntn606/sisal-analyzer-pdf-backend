"""Offline CI entry: deny DNS/socket/libcurl traffic before loading any tests."""

import socket
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests"), str(REPO)]


def main():
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append("network_operation")
        raise AssertionError("offline_network_forbidden")

    with ExitStack() as stack:
        for method in (
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
            "create_connection",
        ):
            stack.enter_context(patch.object(socket, method, forbidden))
        for method in ("connect", "connect_ex", "sendto"):
            stack.enter_context(patch.object(socket.socket, method, forbidden))
        stack.enter_context(patch("curl_cffi.requests.Session.request", forbidden))
        suites = [
            unittest.TestLoader().discover(str(ROOT / "tests"), pattern="test_*.py"),
            unittest.TestLoader().discover(
                str(REPO / "tests"), pattern="test_api_football_errors.py"
            ),
        ]
        result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(suites))
    print("Network attempts: " + str(len(attempts)))
    print("Live acquisitions during tests: 0")
    return 0 if result.wasSuccessful() and not attempts else 1


if __name__ == "__main__":
    raise SystemExit(main())
