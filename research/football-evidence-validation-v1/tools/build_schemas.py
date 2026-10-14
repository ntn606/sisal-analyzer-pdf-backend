"""Reproducible local JSON Schema generation; no remote references."""

import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent / "schemas"


def obj(p, optional=()):
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": p,
        "required": [k for k in p if k not in optional],
    }


def ref(n):
    return {"$ref": "#/$defs/" + n}


def arr(x, **kw):
    return {"type": "array", "items": x, "maxItems": 200, **kw}


def enum(*x):
    return {"enum": list(x)}


S = {"type": "string", "minLength": 1, "maxLength": 1000}
ID = {"type": "string", "pattern": r"^[A-Za-z0-9_.:-]{1,100}$"}
T = {"type": "string", "format": "date-time"}
N = lambda x: {"anyOf": [x, {"type": "null"}]}
flags = {
    k: {"const": v}
    for k, v in {
        "diagnostic_only": True,
        "ready_for_analysis": False,
        "ready_for_quant": False,
        "statistics_usable_in_production": False,
    }.items()
}
defs = {}
defs["source"] = obj(
    {
        "source_id": ID,
        "uri": {"type": "string", "format": "uri", "maxLength": 2000},
        "content_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "published_at": N(T),
        "observed_at": T,
        "availability_verified": {"type": "boolean"},
        "verification": enum("verified", "reported_unconfirmed"),
        "data_origin": enum("synthetic", "archived_real"),
    }
)
defs["team"] = obj(
    {
        "id": ID,
        "name": S,
        "category": enum(
            "men_senior", "women_senior", "u19", "u20", "reserve", "other"
        ),
    }
)
defs["provider_id"] = obj(
    {
        "provider": ID,
        "match_id": ID,
        "home_team_id": ID,
        "away_team_id": ID,
        "competition_id": ID,
        "canonical_competition_id": ID,
        "canonical_home_id": ID,
        "canonical_away_id": ID,
        "kickoff_utc": T,
        "season": S,
        "verified": {"const": True},
        "proof": ref("source"),
    }
)
defs["identity"] = obj(
    {
        "match_id": ID,
        "home": ref("team"),
        "away": ref("team"),
        "competition": obj({"id": ID, "name": S, "season": S}),
        "match_date": {"type": "string", "format": "date"},
        "kickoff_utc": T,
        "kickoff_local": T,
        "timezone": S,
        "verification": enum("verified", "identity_unverified"),
        "proof": N(ref("source")),
        "sisal": N(
            obj(
                {
                    "palinsesto": ID,
                    "avvenimento": ID,
                    "verified": {"const": True},
                    "proof": ref("source"),
                }
            )
        ),
        "providers": arr(ref("provider_id")),
    }
)


# Each family has a distinct typed selection. No fuzzy string parsing.
def market(f, selection):
    return obj(
        {
            "family": {"const": f},
            "period": enum("regular_time", "first_half", "extra_time", "penalties"),
            "selection": selection,
        }
    )


simple = [
    market("1x2", enum("home", "draw", "away")),
    market("double_chance", enum("home_draw", "home_away", "draw_away")),
    market(
        "over_under",
        obj(
            {
                "direction": enum("over", "under"),
                "line": {"type": "number", "minimum": 0, "maximum": 50},
                "scope": enum("match", "home", "away"),
            }
        ),
    ),
    market("btts", enum("yes", "no")),
    market(
        "multigoal",
        obj(
            {
                "min": {"type": "integer", "minimum": 0, "maximum": 50},
                "max": {"type": "integer", "minimum": 0, "maximum": 50},
                "scope": enum("match", "home", "away"),
            }
        ),
    ),
    market("unsupported", obj({"label": S, "required_data": arr(S, minItems=1)})),
]
defs["simple_market"] = {"oneOf": simple}
defs["market"] = {
    "oneOf": simple
    + [
        obj(
            {
                "family": enum("combination", "my_combo"),
                "period": {"const": "regular_time"},
                "selection": obj(
                    {
                        "legs": arr(ref("simple_market"), minItems=2, maxItems=10),
                        "void_policy": enum("unknown", "void_all"),
                    }
                ),
            }
        )
    ]
}
defs["historical_match"] = obj(
    {
        "match_id": ID,
        "team_id": ID,
        "opponent_id": ID,
        "competition_id": ID,
        "season": S,
        "kickoff": T,
        "status": enum("FINISHED", "POSTPONED", "CANCELLED", "IN_PLAY"),
        "venue": enum("home", "away"),
        "goals_for_90": N({"type": "integer", "minimum": 0}),
        "goals_against_90": N({"type": "integer", "minimum": 0}),
        "source": ref("source"),
    }
)
payloads = {
    "odds": obj(
        {
            "market": ref("market"),
            "decimal": {"type": "string", "pattern": r"^[0-9]{1,4}(\.[0-9]{1,6})?$"},
            "valid_until": N(T),
        }
    ),
    "statistics": obj(
        {
            "team_id": ID,
            "sample_size": {"type": "integer", "minimum": 0, "maximum": 200},
            "results": arr(ref("historical_match")),
            "sample_start": N(T),
            "sample_end": N(T),
            "limits": arr(S),
        }
    ),
    "news": obj(
        {
            "team_id": ID,
            "category": enum(
                "absence",
                "suspension",
                "probable_lineup",
                "official_lineup",
                "statement",
            ),
            "basis": enum("official", "reported", "probable"),
            "description": S,
            "player_ids": arr(ID),
        }
    ),
}
defs["evidence"] = {
    "oneOf": [
        obj(
            {
                "id": ID,
                "kind": {"const": kind},
                "assessment": enum("confirmed", "hypothesis", "contradictory"),
                "use_as_evidence": {"type": "boolean"},
                "source": ref("source"),
                "payload": p,
                "limitations": arr(S),
            }
        )
        for kind, p in payloads.items()
    ]
    + [
        obj(
            {
                "id": ID,
                "kind": enum("odds", "statistics", "news"),
                "assessment": {"const": "missing"},
                "use_as_evidence": {"const": False},
                "source": {"type": "null"},
                "payload": {"type": "null"},
                "limitations": arr(S, minItems=1),
            }
        )
    ]
}
defs["candidate"] = obj(
    {
        "id": ID,
        "market": ref("market"),
        "quote_id": N(ID),
        "favorable_reasons": arr(S),
        "risks": arr(S),
        "evidence_refs": arr(ID),
    }
)
dossier = obj(
    {
        "schema_version": {"const": "1.0.0"},
        "data_origin": enum("synthetic", "archived_real"),
        **flags,
        "analysis_at": T,
        "identity": ref("identity"),
        "evidence": arr(ref("evidence")),
        "candidates": arr(ref("candidate")),
        "decision": obj(
            {
                "status": enum("candidate", "watch", "no_bet"),
                "candidate_id": N(ID),
                "reasons": arr(S, minItems=1),
            }
        ),
    }
)
score = obj(
    {
        "home": {"type": "integer", "minimum": 0, "maximum": 100},
        "away": {"type": "integer", "minimum": 0, "maximum": 100},
    }
)
result = obj(
    {
        "schema_version": {"const": "1.0.0"},
        "match_id": ID,
        "home_team_id": ID,
        "away_team_id": ID,
        "competition_id": ID,
        "season": S,
        "kickoff_utc": T,
        "status": enum("FINISHED", "CANCELLED", "POSTPONED", "IN_PLAY"),
        "regular_time": N(score),
        "extra_time": N(score),
        "penalties": N(score),
        "finished_at": N(T),
        "source": ref("source"),
        "settlement": enum("normal", "verified_void", "unknown"),
        "settlement_proof": N(ref("source")),
    }
)


def write(name, schema):
    def references(value):
        if isinstance(value, dict):
            return (
                {value["$ref"].split("/")[-1]} if "$ref" in value else set()
            ) | set().union(*(references(v) for v in value.values()))
        if isinstance(value, list):
            return set().union(*(references(v) for v in value))
        return set()

    used = references(schema)
    pending = set(used)
    while pending:
        dependency = pending.pop()
        additions = references(defs[dependency]) - used
        used |= additions
        pending |= additions
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:sisal:football-validation:v1:" + name,
        **schema,
        "$defs": {k: defs[k] for k in sorted(used)},
    }
    root.joinpath(name + ".schema.json").write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
    )


write("dossier", dossier)
write("result", result)
defs["validation"] = obj(
    {
        **flags,
        "status": enum("validated", "blocked"),
        "reasons": arr(S),
        "usable_evidence_ids": arr(ID),
        "withheld_evidence": arr(
            obj(
                {
                    "id": ID,
                    "assessment": enum(
                        "confirmed", "hypothesis", "contradictory", "missing"
                    ),
                    "reasons": arr(S),
                },
                optional=("reasons",),
            )
        ),
        "data_origin": enum("synthetic", "archived_real"),
        "freshness_policy": obj(
            {
                "odds_max_age_seconds": {"const": 3600},
                "history_max_age_days": {"const": 180},
            }
        ),
        "verification_scope": {
            "const": "operator_attested_offline_not_independently_certified"
        },
    }
)
defs["evaluation"] = obj(
    {
        **flags,
        "status": enum("winning", "losing", "void", "not_evaluable"),
        "reasons": arr(S),
        "rules_version": {"const": "experimental-90min-v1"},
        "settlement_authority": {"const": "diagnostic_not_bookmaker"},
        "data_origin": enum("synthetic", "archived_real", "unvalidated"),
    }
)
H = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
base = {
    "schema_version": {"const": "1.0.0"},
    **flags,
    "sequence": {"type": "integer", "minimum": 1},
    "record_id": {"type": "string", "format": "uuid"},
    "recorded_at": T,
    "previous_hash": H,
    "content_hash": H,
    "mode": enum("real_only", "synthetic_test"),
}
prediction = obj(
    {
        **base,
        "record_type": {"const": "prediction"},
        "data": obj(
            {
                "snapshot": dossier,
                "validation": ref("validation"),
                "evaluated_market": N(ref("market")),
                "evaluated_quote": N(
                    {"type": "string", "pattern": r"^[0-9]{1,4}(\.[0-9]{1,6})?$"}
                ),
                "decision": dossier["properties"]["decision"],
            }
        ),
    }
)
outcome = obj(
    {
        **base,
        "record_type": {"const": "outcome"},
        "data": obj(
            {
                "prediction_id": {"type": "string", "format": "uuid"},
                "prediction_hash": H,
                "result": result,
                "evaluation": ref("evaluation"),
            }
        ),
    }
)
write("record", {"oneOf": [prediction, outcome]})
write("dossier", dossier)
write("result", result)
write("validation", ref("validation"))
write("evaluation", ref("evaluation"))
