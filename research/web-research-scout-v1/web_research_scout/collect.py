"""Explicit manual opt-in only. Fixed reviewed URLs, no discovery crawl."""

import fcntl
import http.client
import ipaddress
import json
import socket
import ssl
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .extract import metadata
from .security import (
    SafeError,
    digest,
    instant,
    public_addresses,
    validated_url,
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    """Direct connections only when no proxy is configured, with validated IP."""

    def __init__(self, addresses, context):
        super().__init__(context=context)
        self.addresses = tuple(sorted(addresses))

    def https_open(self, request):
        addresses = self.addresses

        class Connection(http.client.HTTPSConnection):
            def connect(self):
                if self._tunnel_host:
                    raise SafeError("unexpected_proxy_tunnel")
                # Literal IP connection preserves TLS certificate/SNI for the
                # official hostname. No second hostname resolution occurs.
                address = addresses[0]
                if not ipaddress.ip_address(address).is_global:
                    raise SafeError("private_destination_blocked")
                raw = socket.create_connection(
                    (address, self.port), self.timeout, self.source_address
                )
                try:
                    self.sock = self._context.wrap_socket(
                        raw, server_hostname=self.host
                    )
                except Exception:
                    raw.close()
                    raise

        return self.do_open(Connection, request, context=self._context)


class HTTPSReader:
    """Pinned public IP/TLS; configured proxies fail closed, never bypassed."""

    def read(self, url, timeout, max_bytes, *, destination_addresses=None):
        if any(urllib.request.getproxies().get(k) for k in ("https", "http", "all")):
            raise SafeError("proxy_target_integrity_unverified")
        if not destination_addresses:
            raise SafeError("destination_pin_missing")
        for value in destination_addresses:
            address = ipaddress.ip_address(value)
            if (
                not address.is_global
                or getattr(address, "ipv4_mapped", None) is not None
            ):
                raise SafeError("private_destination_blocked")
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "text/html,text/plain",
                "User-Agent": "SisalWebResearchScout/0.1 (manual public metadata review)",
                "Accept-Encoding": "identity",
            },
        )
        opener = urllib.request.build_opener(
            NoRedirect(),
            PinnedHTTPSHandler(destination_addresses, ssl.create_default_context()),
        )
        try:
            with opener.open(request, timeout=timeout) as response:
                status = response.status
                ctype = response.headers.get_content_type()
                if response.headers.get("Content-Encoding", "identity") != "identity":
                    raise SafeError("compressed_response_rejected")
                raw = response.read(max_bytes + 1)
                if len(raw) > max_bytes:
                    raise SafeError("response_too_large")
                return status, ctype, raw, None
        except urllib.error.HTTPError as error:
            if error.code in (301, 302, 303, 307, 308):
                raise SafeError("redirect_blocked") from None
            if error.code == 429:
                retry = error.headers.get("Retry-After", "60")
                try:
                    seconds = int(retry)
                    seconds = max(60, min(seconds, 86400))
                except ValueError:
                    try:
                        seconds = max(
                            60,
                            min(
                                int(
                                    (
                                        __import__(
                                            "email.utils",
                                            fromlist=["parsedate_to_datetime"],
                                        ).parsedate_to_datetime(retry)
                                        - datetime.now(timezone.utc)
                                    ).total_seconds()
                                ),
                                86400,
                            ),
                        )
                    except Exception:
                        seconds = 60
                return 429, None, b"", seconds
            return error.code, None, b"", None
        except urllib.error.URLError as error:
            # Do not print/store the raw proxy or provider error.
            reason = str(getattr(error, "reason", ""))
            raise SafeError(
                "proxy_tunnel_denied_403" if "403" in reason else "https_unavailable"
            ) from None


class DomainBudget:
    def __init__(self, directory):
        self.directory = Path(directory)

    def reserve(self, host, now, delay=5):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / (digest(host.encode()) + ".json")
        with (self.directory / "budget.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                previous = json.loads(path.read_text())["next_at"]
            except FileNotFoundError:
                previous = None
            except (OSError, ValueError, KeyError):
                raise SafeError("domain_budget_invalid") from None
            if previous and instant(previous) > now:
                raise SafeError("domain_rate_limited")
            path.write_text(
                json.dumps(
                    {"next_at": (now + timedelta(seconds=max(5, delay))).isoformat()}
                )
            )

    def backoff(self, host, now, delay):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / (digest(host.encode()) + ".json")
        with (self.directory / "budget.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                previous = instant(json.loads(path.read_text())["next_at"])
            except FileNotFoundError:
                previous = now
            except (OSError, ValueError, KeyError, SafeError):
                raise SafeError("domain_budget_invalid") from None
            path.write_text(
                json.dumps(
                    {
                        "next_at": max(
                            previous, now + timedelta(seconds=max(60, delay))
                        ).isoformat()
                    }
                )
            )


class Collector:
    def __init__(
        self, sources, budget, *, live=False, reader=None, resolver=None, clock=None
    ):
        self.sources = sources
        self.budget = budget
        self.live = live
        self.reader = reader or HTTPSReader()
        self.resolver = resolver
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def collect(self, source_id, resource):
        now = self.clock()
        output = {
            "schema_version": "web-scout-proof.1",
            "source_id": None,
            "url": None,
            "origin": "real_access_attempt",
            "status": "source_blocked",
            "collected_at": now.isoformat(),
            "published_at": None,
            "publication_date": None,
            "content_retrieved": False,
            "content_sha256": None,
            "title": None,
            "reason": None,
            "http_status": None,
            "automatic_claim_verification": False,
        }
        try:
            if not self.live:
                raise SafeError("live_disabled")
            source = self.sources[source_id]
            url = source["resources"][resource]
            host = validated_url(url, source)
            output.update(source_id=source_id, url=url)
            governance = resource == "robots"
            if not governance:
                if source.get("review_state") != "approved" or not source.get(
                    "metadata_retention_allowed"
                ):
                    raise SafeError("terms_or_retention_unverified")
                robots = source.get("robots_review", {})
                if (
                    robots.get("allowed_resources", []).count(resource) != 1
                    or not robots.get("reviewed_at")
                    or not robots.get("valid_until")
                    or instant(robots["reviewed_at"]) > now
                    or instant(robots["valid_until"]) <= now
                ):
                    raise SafeError("robots_permission_unverified")
            addresses = public_addresses(
                host, **({"resolver": self.resolver} if self.resolver else {})
            )
            self.budget.reserve(
                host,
                now,
                max(
                    source.get("minimum_interval_seconds", 5),
                    source.get("robots_review", {}).get("crawl_delay_seconds", 0),
                ),
            )
            # Recheck DNS, then pin a public IP with TLS hostname verification.
            # A configured proxy is never bypassed: the reader fails closed.
            if addresses != public_addresses(
                host, **({"resolver": self.resolver} if self.resolver else {})
            ):
                raise SafeError("dns_changed_before_request")
            code, ctype, raw, retry = self.reader.read(
                url, timeout=15, max_bytes=256_000
            )
            output["http_status"] = code
            if code == 429:
                self.budget.backoff(host, now, retry or 60)
                raise SafeError("http_rate_limited")
            if code != 200:
                raise SafeError("http_access_denied_or_unavailable")
            if len(raw) > 256_000:
                raise SafeError("response_too_large")
            output.update(
                origin="real_saved", content_retrieved=True, content_sha256=digest(raw)
            )
            if governance:
                if ctype not in ("text/plain", "text/robots"):
                    raise SafeError("unexpected_robots_content_type")
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(raw.decode("utf-8", "strict").splitlines())
                output.update(
                    status="reported_unconfirmed",
                    reason="robots_not_a_license",
                    robots_paths={
                        k: parser.can_fetch("SisalWebResearchScout", v)
                        for k, v in source["resources"].items()
                        if k != "robots"
                    },
                    crawl_delay=parser.crawl_delay("SisalWebResearchScout"),
                )
            else:
                item = metadata(raw, ctype)
                output.update(
                    item,
                    status="reported_unconfirmed",
                    reason=item["reason"] or "metadata_requires_manual_claim_review",
                )
            return output
        except SafeError as error:
            output.update(status="source_blocked", reason=error.code)
        except Exception:
            output.update(status="source_blocked", reason="technical_or_parsing_error")
        # On failures no body, exception, headers or unexpected metadata survive.
        output.update(
            content_retrieved=False,
            content_sha256=None,
            title=None,
            published_at=None,
            publication_date=None,
        )
        return output
