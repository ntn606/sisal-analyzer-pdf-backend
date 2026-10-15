"""Build the standalone output contract; all references remain local."""

import json
from pathlib import Path


def obj(properties, optional=()):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": [k for k in properties if k not in optional],
    }


def arr(items):
    return {"type": "array", "items": items}


def ref(name):
    return {"$ref": "#/$defs/" + name}


def nullable(value):
    return {"anyOf": [value, {"type": "null"}]}


S = {"type": "string"}
N = {"type": "number"}
I = {"type": "integer"}
HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
BOX = {"type": "array", "items": N, "minItems": 4, "maxItems": 4}
defs = {}
defs["source"] = obj(
    {
        "source_url": S,
        "sha256": HASH,
        "retrieved_at": S,
        "data_origin": {"enum": ["archived_real", "synthetic"]},
        "publisher_timestamp_text": S,
        "publisher_timezone": {"type": "null"},
        "published_at_utc": {"type": "null"},
    },
    optional=("publisher_timestamp_text", "publisher_timezone", "published_at_utc"),
)
defs["word"] = obj({"text": S, "bbox": BOX})
defs["date_resolution"] = obj(
    {
        "value": S,
        "printed": S,
        "year_explicit": {"type": "boolean"},
        "basis": {
            "enum": ["printed_date", "weekday_day_month_and_publisher_year_context"]
        },
    }
)
defs["event"] = obj(
    {
        "palinsesto": S,
        "avvenimento": S,
        "event_key": S,
        "competition_code": S,
        "home": S,
        "away": S,
        "match_date": S,
        "local_time": S,
        "date_resolution": ref("date_resolution"),
        "category": {"type": "null"},
        "category_status": {"const": "not_explicitly_printed"},
        "timezone": {"type": "null"},
        "kickoff_utc": {"type": "null"},
        "identity_scope": {
            "const": "printed_sisal_event_only_no_cross_provider_mapping"
        },
        "identity_status": {"const": "printed_identity_matched"},
        "identity_bbox": BOX,
        "identity_words": arr(ref("word")),
        "page": I,
    }
)
defs["selection"] = obj(
    {
        "event_key": S,
        "market_type": {"const": "multigol_match"},
        "scope": {"const": "match"},
        "period": {"type": "null"},
        "range_min": I,
        "range_max": I,
        "selection": {"enum": ["range", "altro"]},
        "decimal_original": nullable(S),
        "decimal": nullable({"type": "string", "pattern": r"^[0-9]+(\.[0-9]+)?$"}),
        "raw_cell_text": S,
        "status": {"enum": ["verified_from_pdf_cell", "missing", "blocked"]},
        "reasons": arr(S),
        "page": I,
        "cell_bbox": BOX,
        "word_boxes": arr(BOX),
        "header_bbox": BOX,
        "band_bbox": BOX,
        "layout_sha256": HASH,
        "source_sha256": HASH,
        "source_url": S,
        "retrieved_at": S,
        "publisher_timestamp_text": S,
        "published_at_utc": {"type": "null"},
    }
)
defs["column"] = obj(
    {
        "range_min": I,
        "range_max": I,
        "selection": {"enum": ["range", "altro"]},
        "column_index": I,
        "header_text": S,
        "header_bbox": BOX,
        "band_bbox": BOX,
    }
)
defs["layout"] = obj(
    {
        "profile": {"const": "sisal_multigol_per_data_paired_v1"},
        "page": I,
        "source_sha256": HASH,
        "header_top": N,
        "header_bottom": N,
        "x_boundaries": arr(N),
        "row_boundaries": arr(N),
        "markets": arr(ref("column")),
        "layout_sha256": HASH,
    }
)
schema = obj(
    {
        "schema_version": {"const": "1.0.0"},
        "diagnostic_only": {"const": True},
        "ready_for_analysis": {"const": False},
        "ready_for_quant": {"const": False},
        "statistics_usable_in_production": {"const": False},
        "status": {"enum": ["parsed", "partial", "blocked"]},
        "reasons": arr(S),
        "source": nullable(ref("source")),
        "event": nullable(ref("event")),
        "selections": arr(ref("selection")),
        "layouts": arr(ref("layout")),
    }
)
schema.update(
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:sisal:multigol-parser:v1:output",
        "$defs": defs,
        "allOf": [
            {
                "if": {"properties": {"status": {"const": "blocked"}}},
                "then": {
                    "properties": {
                        "event": {"type": "null"},
                        "selections": {"maxItems": 0},
                    }
                },
                "else": {
                    "properties": {
                        "source": ref("source"),
                        "event": ref("event"),
                        "selections": {"minItems": 1},
                    }
                },
            }
        ],
    }
)
output = Path(__file__).resolve().parent.parent / "schemas" / "output.schema.json"
output.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n")
