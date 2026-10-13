"""Test-only: block all AF_INET/AF_INET6 sockets and DNS, including children."""

import os
import socket

if os.environ.get("SISAL_MATCHES_OFFLINE_TESTS") == "1":
    try:
        from os_guard import install

        install()
    except Exception:
        # Python ignores ordinary sitecustomize exceptions; terminate instead.
        os._exit(78)
    _original = socket.socket

    class OfflineSocket(_original):
        def connect(self, address):
            if self.family in (socket.AF_INET, socket.AF_INET6):
                raise RuntimeError("offline_external_network_disabled")
            return super().connect(address)

        def connect_ex(self, address):
            if self.family in (socket.AF_INET, socket.AF_INET6):
                raise RuntimeError("offline_external_network_disabled")
            return super().connect_ex(address)

        def sendto(self, *args, **kwargs):
            if self.family in (socket.AF_INET, socket.AF_INET6):
                raise RuntimeError("offline_external_network_disabled")
            return super().sendto(*args, **kwargs)

        def bind(self, address):
            if self.family in (socket.AF_INET, socket.AF_INET6):
                raise RuntimeError("offline_external_network_disabled")
            return super().bind(address)

    def denied(*args, **kwargs):
        raise RuntimeError("offline_dns_disabled")

    socket.socket = OfflineSocket
    socket.getaddrinfo = denied
    socket.gethostbyname = denied
    socket.gethostbyname_ex = denied
    socket.gethostbyaddr = denied
