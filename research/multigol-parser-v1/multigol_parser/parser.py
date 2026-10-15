"""Offline parser of one immutable byte snapshot and its physical PDF cells."""

import io
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import pdfplumber

from .common import (
    FLAGS,
    Blocked,
    hash_bytes,
    local_bytes,
    load_json,
    result_blocked,
    validate_manifest,
    utc_now,
)
from .layout import EPS, box, collapse, contained, join, recognize

MONTHS = {
    name: i
    for i, name in enumerate(
        (
            "gennaio",
            "febbraio",
            "marzo",
            "aprile",
            "maggio",
            "giugno",
            "luglio",
            "agosto",
            "settembre",
            "ottobre",
            "novembre",
            "dicembre",
        ),
        1,
    )
}
WEEKDAYS = (
    "lunedì",
    "martedì",
    "mercoledì",
    "giovedì",
    "venerdì",
    "sabato",
    "domenica",
)
DATE_LINE = re.compile(
    r"^(lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica),?\s+(\d{1,2})\s+([a-z]+)(?:\s+(\d{4}))?$",
    re.I,
)
PUBLISHER = re.compile(
    r"Dati aggiornati al\s+(\d{2}/\d{2}/\d{4})\s*-\s*ore\s*(\d{2}:\d{2}:\d{2})", re.I
)


def extract_pages(data):
    if not data.startswith(b"%PDF"):
        raise Blocked("pdf_unrecognized")
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if not 1 <= len(pdf.pages) <= 40:
                raise Blocked("page_limit_exceeded")
            pages = []
            for page in pdf.pages:
                words = page.extract_words(
                    x_tolerance=1,
                    y_tolerance=2,
                    keep_blank_chars=False,
                    use_text_flow=False,
                )
                if len(words) > 15000:
                    raise Blocked("page_word_limit_exceeded")
                pages.append(
                    {
                        "page": page.page_number,
                        "source_sha256": hash_bytes(data),
                        "width": page.width,
                        "height": page.height,
                        "words": words,
                        "lines": page.lines,
                    }
                )
            return pages
    except Blocked:
        raise
    except Exception as error:
        # pdfminer exceptions can include fragments of the input document.
        raise Blocked("pdf_corrupt_or_encrypted") from error


def publication(pages):
    stamps = []
    for page in pages:
        # The stamp can be in a different column from the footer page number.
        words = page["words"]
        footer = sorted(
            (w for w in words if w["top"] > page["height"] * 0.9),
            key=lambda w: (round(w["top"] / 3), w["x0"]),
        )
        matches = PUBLISHER.findall(" ".join(w["text"] for w in footer))
        if len(matches) != 1:
            raise Blocked("publisher_timestamp_missing_or_ambiguous")
        stamp = " ".join(matches[0])
        try:
            datetime.strptime(stamp, "%d/%m/%Y %H:%M:%S")
        except ValueError as error:
            raise Blocked("publisher_timestamp_invalid") from error
        stamps.append(stamp)
    if len(set(stamps)) != 1:
        raise Blocked("publisher_timestamps_conflict")
    return stamps[0]


def heading_date(text, publisher_date):
    match = DATE_LINE.fullmatch(text.strip())
    if not match or match[3].lower() not in MONTHS:
        return None
    years = (
        [int(match[4])]
        if match[4]
        else range(publisher_date.year - 1, publisher_date.year + 2)
    )
    choices = []
    for year in years:
        try:
            resolved = date(year, MONTHS[match[3].lower()], int(match[2]))
        except ValueError:
            continue
        if WEEKDAYS[resolved.weekday()] == match[1].lower() and timedelta(
            days=-2
        ) <= resolved - publisher_date <= timedelta(days=120):
            choices.append(resolved)
    if len(choices) != 1:
        raise Blocked("event_date_ambiguous")
    return {
        "value": choices[0].isoformat(),
        "printed": text,
        "year_explicit": bool(match[4]),
        "basis": "printed_date"
        if match[4]
        else "weekday_day_month_and_publisher_year_context",
    }


def normalized_name(value):
    # Whitespace only: no fuzzy aliases, suffix removal or case-insensitive IDs.
    return " ".join(value.split())


def expected_valid(expected):
    keys = {
        "palinsesto",
        "avvenimento",
        "competition_code",
        "home",
        "away",
        "match_date",
        "local_time",
    }
    if not isinstance(expected, dict) or set(expected) not in (
        keys,
        keys | {"category"},
    ):
        raise Blocked("expected_identity_incomplete")
    if any(not isinstance(expected[k], str) or not expected[k] for k in keys):
        raise Blocked("expected_identity_incomplete")
    if not re.fullmatch(r"\d{3,6}", expected["palinsesto"]) or not re.fullmatch(
        r"\d{1,6}", expected["avvenimento"]
    ):
        raise Blocked("event_key_invalid")
    try:
        date.fromisoformat(expected["match_date"])
    except ValueError as error:
        raise Blocked("expected_date_invalid") from error
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", expected["local_time"]):
        raise Blocked("expected_time_invalid")


def _row_event(page, layout, top, bottom, current_date):
    row_words = [
        w
        for w in page["words"]
        if top - EPS <= (w["top"] + w["bottom"]) / 2 <= bottom + EPS
    ]
    if not row_words:
        return None, current_date
    x = layout["x_boundaries"]
    text = join(row_words)
    new_date = heading_date(text, page["publisher_date"])
    if new_date:
        return None, new_date
    midpoint = (top + bottom) / 2
    body_x = collapse(
        line["x0"]
        for line in page["lines"]
        if abs(line["x0"] - line["x1"]) < 0.1
        and line["top"] <= midpoint <= line["bottom"]
    )
    if len(body_x) != len(x) or any(abs(a - b) > EPS for a, b in zip(body_x, x)):
        raise Blocked("body_columns_disagree_with_header")
    bboxes = [[a, top, b, bottom] for a, b in zip(x, x[1:])]
    cells = [[w for w in row_words if contained(w, bbox)] for bbox in bboxes]
    if any(
        sum(contained(w, bbox) for bbox in bboxes) != 1
        for w in row_words
        if w["x0"] < x[6]
    ):
        raise Blocked("identity_cell_boundary_overlap")
    identity = [join(cell) for cell in cells[:6]]
    if (
        not re.fullmatch(r"(?:[01]?\d|2[0-3])[.:][0-5]\d", identity[0])
        or not re.fullmatch(r"[A-Za-z0-9_]{2,12}", identity[1])
        or not re.fullmatch(r"\d{3,6}", identity[2])
        or not re.fullmatch(r"\d{1,6}", identity[3])
        or not identity[4]
        or not identity[5]
    ):
        raise Blocked("document_row_identity_unreadable")
    if current_date is None:
        raise Blocked("event_date_missing")
    if normalized_name(identity[4]) == normalized_name(identity[5]):
        raise Blocked("printed_team_identity_ambiguous")
    if bottom - top > 18:
        raise Blocked("event_row_geometry_ambiguous")
    event = {
        "palinsesto": identity[2],
        "avvenimento": identity[3],
        "event_key": identity[2] + "/" + identity[3],
        "competition_code": identity[1],
        "home": identity[4],
        "away": identity[5],
        "match_date": current_date["value"],
        "local_time": identity[0].replace(".", ":").zfill(5),
        "date_resolution": current_date,
        "category": None,
        "category_status": "not_explicitly_printed",
        "timezone": None,
        "kickoff_utc": None,
        "identity_scope": "printed_sisal_event_only_no_cross_provider_mapping",
        "identity_bbox": [x[0], top, x[6], bottom],
        "identity_words": [
            {"text": w["text"], "bbox": box(w)} for cell in cells[:6] for w in cell
        ],
        "page": page["page"],
    }
    selections = []
    outside = [
        w
        for w in row_words
        if w["x0"] >= x[6] and not any(contained(w, b) for b in bboxes)
    ]
    for market in layout["markets"]:
        index = market["column_index"]
        bbox = bboxes[index]
        words = cells[index]
        raw = join(words)
        reasons, value = [], None
        overlaps = [w for w in outside if w["x0"] < bbox[2] and w["x1"] > bbox[0]]
        if overlaps:
            reasons = ["cell_boundary_overlap"]
        elif not words:
            reasons = ["empty_cell"]
        elif len(words) != 1:
            reasons = ["multiple_tokens_in_cell"]
        elif not re.fullmatch(r"\d{1,4}(?:[,.]\d{1,3})?", raw):
            reasons = ["unreadable_odds"]
        else:
            try:
                price = Decimal(raw.replace(",", "."))
                if price <= 1:
                    reasons = ["invalid_decimal_odds"]
                else:
                    value = raw.replace(",", ".")
            except InvalidOperation:
                reasons = ["unreadable_odds"]
        selections.append(
            {
                "event_key": event["event_key"],
                "market_type": "multigol_match",
                "scope": "match",
                "period": None,
                "range_min": market["range_min"],
                "range_max": market["range_max"],
                "selection": market["selection"],
                "decimal_original": raw if value is not None else None,
                "decimal": value,
                "raw_cell_text": raw,
                "status": "verified_from_pdf_cell"
                if value is not None
                else "missing"
                if reasons == ["empty_cell"]
                else "blocked",
                "reasons": reasons,
                "page": page["page"],
                "cell_bbox": bbox,
                "word_boxes": [box(w) for w in words],
                "header_bbox": market["header_bbox"],
                "band_bbox": market["band_bbox"],
                "layout_sha256": layout["layout_sha256"],
                "source_sha256": page["source_sha256"],
            }
        )
    # Do not silently drop a quote drawn outside the recognized table bounds.
    if any(w["x0"] >= x[-1] or w["x1"] <= x[6] for w in outside):
        raise Blocked("row_tokens_outside_market_grid")
    return {"event": event, "selections": selections}, current_date


def parse_pages(pages, source, expected):
    """Internal seam for clearly marked synthetic layout fixtures, not a CLI API."""
    if any(p["source_sha256"] != source["sha256"] for p in pages):
        raise Blocked("mixed_snapshot_coordinates")
    expected_valid(expected)
    if "category" in expected:
        raise Blocked("category_not_verifiable_from_this_layout")
    printed_stamp = publication(pages)
    publisher_date = datetime.strptime(printed_stamp, "%d/%m/%Y %H:%M:%S").date()
    layouts, candidates, current_date = [], [], None
    for page in pages:
        page["publisher_date"] = publisher_date
        layout = recognize(page)
        layouts.append(layout)
        for top, bottom in zip(layout["row_boundaries"], layout["row_boundaries"][1:]):
            parsed, current_date = _row_event(page, layout, top, bottom, current_date)
            if parsed and (
                parsed["event"]["palinsesto"],
                parsed["event"]["avvenimento"],
            ) == (expected["palinsesto"], expected["avvenimento"]):
                candidates.append(parsed)
    if not candidates:
        raise Blocked("event_not_found")
    if len(candidates) != 1:
        # Classify repeated content without treating duplicates as independent proof.
        comparison = [
            {
                "identity": {
                    k: v
                    for k, v in c["event"].items()
                    if k not in ("page", "identity_bbox", "identity_words")
                },
                "prices": [
                    (s["range_min"], s["range_max"], s["selection"], s["decimal"])
                    for s in c["selections"]
                ],
            }
            for c in candidates
        ]
        raise Blocked(
            "duplicate_event_key"
            if all(c == comparison[0] for c in comparison)
            else "conflicting_event_records"
        )
    chosen = candidates[0]
    event = chosen["event"]
    if any(
        (normalized_name(event[key]) if key in ("home", "away") else event[key])
        != (
            normalized_name(expected[key]) if key in ("home", "away") else expected[key]
        )
        for key in expected
    ):
        raise Blocked("printed_identity_mismatch")
    event["identity_status"] = "printed_identity_matched"
    source.update(
        {
            "publisher_timestamp_text": printed_stamp,
            "publisher_timezone": None,
            "published_at_utc": None,
        }
    )
    for selection in chosen["selections"]:
        selection.update(
            {
                "source_url": source["source_url"],
                "retrieved_at": source["retrieved_at"],
                "publisher_timestamp_text": printed_stamp,
                "published_at_utc": None,
            }
        )
    partial = any(s["status"] != "verified_from_pdf_cell" for s in chosen["selections"])
    return {
        "schema_version": "1.0.0",
        **FLAGS,
        "status": "partial" if partial else "parsed",
        "reasons": ["some_quotes_missing_or_unreadable"] if partial else [],
        "source": source,
        "event": event,
        "selections": chosen["selections"],
        "layouts": layouts,
    }


def parse_snapshot(pdf_path, manifest_path, expected, *, mode="real_only", _clock=None):
    source = None
    try:
        data = local_bytes(pdf_path)
        manifest = load_json(manifest_path)
        validate_manifest(manifest, data, mode, (_clock or utc_now)())
        source = {
            key: manifest[key]
            for key in ("source_url", "sha256", "retrieved_at", "data_origin")
        }
        pages = extract_pages(data)
        return parse_pages(pages, source, expected)
    except Blocked as error:
        return result_blocked(str(error), source)
    except (ValueError, KeyError, TypeError, OverflowError):
        return result_blocked("document_structure_invalid", source)
