"""Explicit synthetic claims over a saved identity reference; never live news."""

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from web_research_scout.cache import encoded
from web_research_scout.probe import projection
from web_research_scout.security import digest

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 11, 22, tzinfo=timezone.utc)


def documents():
    return {
        name: json.loads((ROOT / "cache" / name).read_text())
        for name in (
            "sources.json",
            "claims.json",
            "identity-references.json",
            "access-observations.json",
            "source-matrix.json",
        )
    }


def claim_bundle(
    documents=None,
    *,
    claim_id="test-injury",
    team="local:team:newcastle",
    assertion="confirmed",
    category="injury",
    value="unavailable",
    source_id="newcastle",
):
    docs = deepcopy(documents) if documents else globals()["documents"]()
    source = docs["sources.json"]["sources"][source_id]
    source.update(review_state="approved", metadata_retention_allowed=True)
    source["resources"]["test-news"] = (
        "https://" + source["hosts"][0] + "/synthetic-test-news"
    )
    claim = {
        "id": claim_id,
        "team_id": team,
        "event_key": ["36411", "1885", "2026-10-12"],
        "category": category,
        "claim_key": "player:synthetic:101",
        "effective_at": "2026-10-12",
        "value": value,
        "description": "Synthetic test availability statement, not an actual player injury",
        "source_id": source_id,
        "url": source["resources"]["test-news"],
        "published_at": "2026-10-11T20:00:00Z",
        "publication_date": None,
        "collected_at": "2026-10-11T21:00:00Z",
        "fresh_until": "2026-10-12T00:00:00Z",
        "origin": "synthetic",
        "assertion": assertion,
        "evidence_file": "evidence/" + claim_id + ".json",
        "evidence_sha256": "0" * 64,
    }
    proof = {
        "schema_version": "web-scout-reviewed-claim.1",
        "source_id": source_id,
        "url": claim["url"],
        "team_id": team,
        "event_key": claim["event_key"],
        "origin": "synthetic",
        "claim_projection_sha256": digest(encoded(projection(claim))),
        "reviewer_ref": "synthetic-offline-review",
        "reviewed_at": "2026-10-11T21:01:00Z",
        "official_lineup_explicit": False,
    }
    claim["evidence_sha256"] = digest(encoded(proof))
    docs[claim["evidence_file"]] = proof
    docs["claims.json"].append(claim)
    return docs, claim


def refresh(docs, claim):
    proof = docs[claim["evidence_file"]]
    proof["claim_projection_sha256"] = digest(encoded(projection(claim)))
    claim["evidence_sha256"] = digest(encoded(proof))
