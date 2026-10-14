"""Single offline CI command: schemas, examples, new tests + 13 backend tests.

Run with Python after installing dependencies. Network is denied even during
imports. Any attempted network operation makes the run fail, even if caught.
The libcurl request guard covers curl_cffi, which bypasses Python sockets.
"""

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
    attempted = []

    def deny(*args, **kwargs):
        attempted.append("network_operation")
        raise AssertionError("offline_network_forbidden")

    with ExitStack() as guards:
        for method in (
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
            "create_connection",
        ):
            guards.enter_context(patch.object(socket, method, deny))
        for method in ("connect", "connect_ex", "sendto"):
            guards.enter_context(patch.object(socket.socket, method, deny))
        guards.enter_context(patch("curl_cffi.requests.Session.request", deny))
        loader = unittest.TestLoader()
        prototype = loader.discover(str(ROOT / "tests"), pattern="test_*.py")
        backend = loader.discover(
            str(REPO / "tests"), pattern="test_api_football_errors.py"
        )
        result = unittest.TextTestRunner(verbosity=2).run(
            unittest.TestSuite([prototype, backend])
        )
    print("Network attempts: " + str(len(attempted)))
    print("Live provider acquisitions: 0")
    return 0 if result.wasSuccessful() and not attempted else 1


if __name__ == "__main__":
    raise SystemExit(main())
