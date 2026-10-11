"""Untrusted content boundaries: strict URLs, public DNS, no redirects/execution."""

import hashlib
import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit


class SafeError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def instant(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError
        return result.astimezone(timezone.utc)
    except (ValueError, AttributeError, TypeError):
        raise SafeError("timezone_or_timestamp_invalid") from None


def json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SafeError("duplicate_json_key")
        result[key] = value
    return result


def load_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=json_object)
    except (ValueError, UnicodeError):
        raise SafeError("invalid_json") from None


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def relative_file(root, name):
    if (
        not isinstance(name, str)
        or not name
        or "\\" in name
        or "\x00" in name
        or Path(name).is_absolute()
    ):
        raise SafeError("invalid_evidence_path")
    original = Path(root) / name
    path = original.resolve()
    root = Path(root).resolve()
    if ".." in Path(name).parts or not path.is_relative_to(root) or path == root:
        raise SafeError("evidence_path_outside_cache")
    if any(
        p.is_symlink()
        for p in [original, *original.parents]
        if p == root or p.is_relative_to(root)
    ):
        raise SafeError("symlink_not_allowed")
    return path


def validated_url(url, source):
    if (
        not isinstance(url, str)
        or len(url) > 2048
        or any(ord(c) < 33 or ord(c) > 126 for c in url)
        or "\\" in url
    ):
        raise SafeError("unsafe_url")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise SafeError("unsafe_url") from None
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or port is not None
        or parsed.fragment
        or parsed.query
        or not host
        or host != parsed.netloc
    ):
        raise SafeError("unsafe_url")
    if (
        len(host) > 253
        or not all(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in host.split(".")
        )
        or "." not in host
    ):
        raise SafeError("unsafe_url")
    if (
        host not in source.get("hosts", [])
        or host in ("localhost", "metadata.google.internal")
        or host.endswith((".localhost", ".local", ".internal"))
    ):
        raise SafeError("unsafe_url")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise SafeError("unsafe_url")
    if re.fullmatch(r"[0-9.]+", host):
        raise SafeError("unsafe_url")
    path = parsed.path or "/"
    decoded = unquote(path)
    if (
        "%" in decoded
        or any(ord(c) < 32 for c in decoded)
        or "\\" in decoded
        or ".." in decoded.split("/")
        or "//" in decoded
    ):
        raise SafeError("unsafe_url")
    if url not in source.get("resources", {}).values():
        raise SafeError("url_not_reviewed")
    return host


def public_addresses(host, resolver=socket.getaddrinfo):
    try:
        addresses = {r[4][0] for r in resolver(host, 443, type=socket.SOCK_STREAM)}
    except Exception:
        raise SafeError("dns_unavailable") from None
    if not addresses:
        raise SafeError("dns_unavailable")
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            raise SafeError("invalid_dns_address") from None
        # Also reject IPv4-mapped IPv6, even when the outer form appears global.
        if not address.is_global or getattr(address, "ipv4_mapped", None) is not None:
            raise SafeError("private_destination_blocked")
    return addresses


SECRET_PATTERNS = [
    r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----",
    r"\b(?:gh[pousr]_[a-zA-Z0-9]{20,}|AKIA[A-Z0-9]{16})",
    r"\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}",
    r"(?i)(?:bearer\s+|[?&](?:token|key|sig|code|secret)=)[A-Za-z0-9_./+=%-]{12,}",
    r'(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|authorization)["\']?\s*[:=]\s*["\']?[A-Za-z0-9_./+=%-]{16,}',
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{40,256}AZFu[A-Za-z0-9_-]{0,32}",
]
INJECTION = re.compile(
    r"(?i)(ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions|system\s*(?:prompt|message)|developer\s*(?:message|instructions)|reveal\s+(?:the\s+)?(?:secret|token|password)|<\s*(?:script|iframe)|javascript:|\[INST\]|ignora\s+(?:le\s+)?istruzioni|esegui\s+(?:questo\s+)?comando)"
)
BETTING = re.compile(
    r"(?i)\b(value\s*bet|betting|prediction|pronostic\w*|probabil\w*|odds|scommess\w*|quote\s+teoriche)\b"
)


def unsafe_content(value):
    text = (
        json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    )
    if any(re.search(pattern, text) for pattern in SECRET_PATTERNS):
        return "sensitive_content"
    if INJECTION.search(text):
        return "prompt_injection_suspected"
    if BETTING.search(text):
        return "betting_content_excluded"
    return None
