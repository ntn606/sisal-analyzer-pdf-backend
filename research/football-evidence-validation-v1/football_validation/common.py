"""Offline primitives. No network clients or environment credentials are used."""

import hashlib
import json
import re
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"
FLAGS = {
    "diagnostic_only": True,
    "ready_for_analysis": False,
    "ready_for_quant": False,
    "statistics_usable_in_production": False,
}


class ValidationError(ValueError):
    """Contains only stable diagnostic codes, never input payloads."""


FORMATS = FormatChecker()


@FORMATS.checks("date-time")
def _rfc3339(value):
    if not isinstance(value, str):
        return True  # JSON Schema's type check rejects non-strings.
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d"
        r"(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)",
        value,
    ):
        return False
    try:
        instant(value)
        return True
    except ValidationError:
        return False


@FORMATS.checks("uri")
def _absolute_uri(value):
    if not isinstance(value, str):
        return True
    if not re.fullmatch(
        r"[A-Za-z][A-Za-z0-9+.-]*:[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+", value
    ):
        return False
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        return False
    try:
        parsed = urlsplit(value)
        if parsed.username is not None or parsed.password is not None:
            return False
        if parsed.scheme in ("http", "https"):
            return bool(parsed.hostname) and parsed.port != 0
        return True
    except ValueError:
        return False


def utc_now():
    return datetime.now(timezone.utc)


def instant(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValidationError("timezone_required")
        return parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise ValidationError("invalid_datetime") from exc


def timestamp(value):
    if value.tzinfo is None:
        raise ValidationError("timezone_required")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("duplicate_json_key")
        result[key] = value
    return result


def loads(value):
    def invalid_constant(_):
        raise ValidationError("non_finite_number")

    try:
        return json.loads(
            value, object_pairs_hook=_object, parse_constant=invalid_constant
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("invalid_json") from exc


def load(path):
    # The CLI accepts local files only; no URL retrieval.
    if Path(path).stat().st_size > 2_000_000:
        raise ValidationError("document_too_large")
    return loads(Path(path).read_bytes())


@lru_cache(maxsize=5)
def _validator(name):
    schema = load(SCHEMAS / (name + ".schema.json"))
    return Draft202012Validator(schema, format_checker=FORMATS)


def schema_errors(value, name):
    validator = _validator(name)
    # Do not include rejected values or jsonschema exception text in output.
    return sorted(
        {
            "schema:" + "/".join(str(x) for x in e.absolute_path)
            for e in validator.iter_errors(value)
        }
    )
