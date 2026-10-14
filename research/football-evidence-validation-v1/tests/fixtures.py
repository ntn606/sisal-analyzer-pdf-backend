"""ALL DATA HERE IS SYNTHETIC. IDs and sources are intentionally fictitious.

Fixed clocks exercise contracts, not a backdated registration of real events.
No saved provider data or real predictions are used by this suite.
"""

import copy
from datetime import datetime, timezone

from football_validation.common import FLAGS, digest

NOW = datetime(2026, 10, 14, 10, tzinfo=timezone.utc)
AFTER = datetime(2026, 10, 16, 21, tzinfo=timezone.utc)


def source(
    label="fixture", observed="2026-10-14T09:55:00Z", published="2026-10-14T09:50:00Z"
):
    return {
        "source_id": "synthetic:" + label,
        "uri": "urn:synthetic:" + label,
        "content_sha256": digest({"synthetic_fixture": label}),
        "published_at": published,
        "observed_at": observed,
        "availability_verified": True,
        "verification": "verified",
        "data_origin": "synthetic",
    }


def market(family="1x2", selection="home", period="regular_time"):
    return {"family": family, "selection": selection, "period": period}


def dossier(selected_market=None):
    selected_market = copy.deepcopy(selected_market or market())
    identity = {
        "match_id": "synthetic:fixture-1",
        "home": {
            "id": "synthetic:home",
            "name": "Test Club A",
            "category": "men_senior",
        },
        "away": {
            "id": "synthetic:away",
            "name": "Test Club B",
            "category": "men_senior",
        },
        "competition": {
            "id": "synthetic:league",
            "name": "Synthetic League",
            "season": "2026-2027",
        },
        "match_date": "2026-10-16",
        "kickoff_utc": "2026-10-16T18:00:00Z",
        "kickoff_local": "2026-10-16T20:00:00+02:00",
        "timezone": "Europe/Rome",
        "verification": "verified",
        "proof": source("identity"),
        "sisal": {
            "palinsesto": "synthetic-1",
            "avvenimento": "synthetic-2",
            "verified": True,
            "proof": source("sisal"),
        },
        "providers": [
            {
                "provider": "synthetic-provider",
                "match_id": "synthetic-provider:fixture",
                "home_team_id": "synthetic-provider:home",
                "away_team_id": "synthetic-provider:away",
                "canonical_home_id": "synthetic:home",
                "canonical_away_id": "synthetic:away",
                "competition_id": "synthetic-provider:league",
                "verified": True,
                "canonical_competition_id": "synthetic:league",
                "season": "2026-2027",
                "kickoff_utc": "2026-10-16T18:00:00Z",
                "proof": source("provider"),
            }
        ],
    }
    results = [
        {
            "match_id": "synthetic-provider:history-1",
            "team_id": "synthetic:home",
            "opponent_id": "synthetic:other",
            "competition_id": "synthetic:league",
            "season": "2026-2027",
            "kickoff": "2026-10-12T18:00:00Z",
            "status": "FINISHED",
            "venue": "home",
            "goals_for_90": 1,
            "goals_against_90": 1,
            "source": source(
                "history-1", "2026-10-12T20:30:00Z", "2026-10-12T20:20:00Z"
            ),
        }
    ]
    evidence = [
        {
            "id": "quote-1",
            "kind": "odds",
            "assessment": "confirmed",
            "use_as_evidence": True,
            "source": source("odds"),
            "payload": {
                "market": selected_market,
                "decimal": "2.10",
                "valid_until": "2026-10-14T10:55:00Z",
            },
            "limitations": [],
        },
        {
            "id": "stats-1",
            "kind": "statistics",
            "assessment": "confirmed",
            "use_as_evidence": True,
            "source": source("stats"),
            "payload": {
                "team_id": "synthetic:home",
                "sample_size": 1,
                "results": results,
                "sample_start": results[0]["kickoff"],
                "sample_end": results[0]["kickoff"],
                "limits": ["Synthetic sample of one match; no inference"],
            },
            "limitations": ["Synthetic only"],
        },
        {
            "id": "news-1",
            "kind": "news",
            "assessment": "hypothesis",
            "use_as_evidence": False,
            "source": source("news"),
            "payload": {
                "team_id": "synthetic:away",
                "category": "probable_lineup",
                "basis": "probable",
                "description": "Synthetic probable lineup, not official",
                "player_ids": [],
            },
            "limitations": ["Unconfirmed"],
        },
        {
            "id": "news-missing",
            "kind": "news",
            "assessment": "missing",
            "use_as_evidence": False,
            "source": None,
            "payload": None,
            "limitations": ["No synthetic official injury bulletin"],
        },
        {
            "id": "news-conflict",
            "kind": "news",
            "assessment": "contradictory",
            "use_as_evidence": False,
            "source": source("conflict"),
            "payload": {
                "team_id": "synthetic:home",
                "category": "statement",
                "basis": "reported",
                "description": "Synthetic conflicting availability report",
                "player_ids": [],
            },
            "limitations": ["Conflict unresolved; excluded"],
        },
    ]
    return {
        "schema_version": "1.0.0",
        "data_origin": "synthetic",
        **FLAGS,
        "analysis_at": "2026-10-14T10:00:00Z",
        "identity": identity,
        "evidence": evidence,
        "candidates": [
            {
                "id": "candidate-1",
                "market": selected_market,
                "quote_id": "quote-1",
                "favorable_reasons": ["Synthetic operator-supplied review reason"],
                "risks": ["Unconfirmed lineup; small sample"],
                "evidence_refs": ["quote-1", "stats-1"],
            }
        ],
        "decision": {
            "status": "candidate",
            "candidate_id": "candidate-1",
            "reasons": ["Synthetic contract exercise, not a recommendation"],
        },
    }


def result(score=None):
    return {
        "schema_version": "1.0.0",
        "match_id": "synthetic:fixture-1",
        "home_team_id": "synthetic:home",
        "away_team_id": "synthetic:away",
        "competition_id": "synthetic:league",
        "season": "2026-2027",
        "kickoff_utc": "2026-10-16T18:00:00Z",
        "status": "FINISHED",
        "regular_time": score if score is not None else {"home": 2, "away": 1},
        "extra_time": None,
        "penalties": None,
        "finished_at": "2026-10-16T20:00:00Z",
        "source": source("result", "2026-10-16T20:10:00Z", "2026-10-16T20:05:00Z"),
        "settlement": "normal",
        "settlement_proof": None,
    }
