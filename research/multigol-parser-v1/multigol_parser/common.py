"""Local-only utilities. Neither this package nor its CLI makes HTTP requests."""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

FLAGS = {
    "diagnostic_only": True,
    "ready_for_analysis": False,
    "ready_for_quant": False,
    "statistics_usable_in_production": False,
}
MAX_PDF_BYTES = 8_000_000


def utc_now():
    return datetime.now(timezone.utc)


class Blocked(ValueError):
    """A stable error code, never a raw PDF/parser/provider exception."""


def stamp(value):
    try:
        if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d"
            r"(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)",
            value,
        ):
            raise ValueError()
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except (ValueError, OverflowError) as error:
        raise Blocked("invalid_acquisition_timestamp") from error


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(data):
    return hash_bytes(
        json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    )


def local_bytes(path, limit=MAX_PDF_BYTES):
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(limit + 1)
    except OSError as error:
        raise Blocked("local_file_unavailable") from error
    if len(data) > limit:
        raise Blocked("document_too_large")
    return data


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise Blocked("duplicate_json_key")
        result[key] = value
    return result


def load_json(path):
    def invalid(_):
        raise Blocked("invalid_json")

    try:
        return json.loads(
            local_bytes(path, 1_000_000),
            object_pairs_hook=_pairs,
            parse_constant=invalid,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise Blocked("invalid_json") from error


def validate_manifest(manifest, data, mode, now):
    if mode not in ("real_only", "synthetic_test"):
        raise Blocked("invalid_mode")
    if not isinstance(manifest, dict):
        raise Blocked("invalid_provenance")
    if manifest.get("sha256") != hash_bytes(data):
        raise Blocked("snapshot_hash_mismatch")
    if stamp(manifest.get("retrieved_at")) > now:
        raise Blocked("acquisition_in_future")
    origin = manifest.get("data_origin")
    if origin not in ("archived_real", "synthetic"):
        raise Blocked("data_origin_required")
    if origin == "synthetic":
        if mode != "synthetic_test" or not str(
            manifest.get("source_url", "")
        ).startswith("urn:synthetic:"):
            raise Blocked("synthetic_not_allowed")
    else:
        try:
            url = urlsplit(manifest["source_url"])
            if (
                url.scheme != "https"
                or url.hostname != "landing.sisal.it"
                or url.username is not None
                or url.password is not None
                or url.port not in (None, 443)
                or url.query
                or url.fragment
                or unquote(url.path)
                != "/volantini/Scommesse_Sport/Quote/calcio multigoal per data.pdf"
            ):
                raise ValueError()
        except (ValueError, KeyError, TypeError) as error:
            raise Blocked("official_document_source_unverified") from error


def result_blocked(code, source=None):
    return {
        "schema_version": "1.0.0",
        **FLAGS,
        "status": "blocked",
        "reasons": [code],
        "source": source,
        "event": None,
        "selections": [],
        "layouts": [],
    }
