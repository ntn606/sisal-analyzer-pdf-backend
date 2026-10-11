"""Offline diagnostic projection. No collector import or web requests."""

import json
import re
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator, FormatChecker

from .cache import EvidenceCache, encoded
from .security import SafeError, digest, instant, unsafe_content, validated_url

VERSION = "football-web-research-v1.1"
CATEGORIES = (
    "recent_results",
    "standings",
    "injury",
    "suspension",
    "availability",
    "probable_lineup",
    "official_lineup",
    "schedule",
    "news",
)
ROOT = Path(__file__).resolve().parents[1]


def validate_claim(claim):
    schema = json.loads((ROOT / "contracts/claim.schema.json").read_text())
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(claim)
        if any(
            unsafe_content(v)
            for k, v in claim.items()
            if k not in ("value", "description", "evidence_sha256")
        ):
            raise SafeError("claim_metadata_unsafe")
    except Exception:
        raise SafeError("claim_contract_invalid") from None


def projection(claim):
    return {
        k: claim[k]
        for k in (
            "id",
            "team_id",
            "event_key",
            "category",
            "claim_key",
            "effective_at",
            "value",
            "description",
            "assertion",
            "fresh_until",
            "source_id",
            "url",
            "published_at",
            "publication_date",
            "collected_at",
            "origin",
        )
    }


class DiagnosticProbe:
    def __init__(self, cache, *, clock=None, allow_synthetic=False):
        self.cache = EvidenceCache(cache)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.allow_synthetic = allow_synthetic

    def football_web_research_v1_probe(self, palinsesto, avvenimento, match_date):
        result = self._run(palinsesto, avvenimento, match_date)
        schema = json.loads((ROOT / "contracts/response.schema.json").read_text())
        try:
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(
                result
            )
        except Exception:
            result.update(
                status="data_unverified",
                identity=None,
                teams={},
                blockers=["response_contract_invalid"],
            )
            result["provenance"]["real_web_claims_verified"] = 0
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(
                result
            )
        return result

    def _run(self, palinsesto, avvenimento, match_date):
        now = self.clock()
        result = {
            "schema_version": VERSION,
            "diagnostic_only": True,
            "ready_for_analysis": False,
            "ready_for_quant": False,
            "statistics_usable_in_production": False,
            "execution_mode": "synthetic_offline_fixture"
            if self.allow_synthetic
            else "real_only_cache",
            "status": "identity_unverified",
            "requested_event": None,
            "verified_at": now.isoformat(),
            "identity": None,
            "teams": {},
            "blockers": [],
            "provenance": {
                "new_web_requests": 0,
                "cache_revision": None,
                "real_web_claims_verified": 0,
                "untrusted_content_is_data": True,
                "current_event_revalidated": False,
                "upstream_statistics_imported": False,
            },
        }
        try:
            if (
                not all(
                    type(v) is str and re.fullmatch(r"[0-9]{1,20}", v)
                    for v in (palinsesto, avvenimento)
                )
                or type(match_date) is not str
                or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", match_date)
            ):
                raise SafeError("invalid_event_reference")
            __import__("datetime").date.fromisoformat(match_date)
            key = [palinsesto, avvenimento, match_date]
            result["requested_event"] = key
            revision, files = self.cache.read()
            result["provenance"]["cache_revision"] = revision
            for name in ("identity-references", "sources"):
                schema = json.loads(
                    (ROOT / "contracts" / (name + ".schema.json")).read_text()
                )
                Draft202012Validator(schema, format_checker=FormatChecker()).validate(
                    files[name + ".json"]
                )
            for source in files["sources.json"]["sources"].values():
                for url in source["resources"].values():
                    validated_url(url, source)
            registry = files["identity-references.json"]
            entries = [
                event for event in registry["events"] if event["event_key"] == key
            ]
            if len(entries) != 1:
                raise SafeError("event_identity_missing_or_ambiguous")
            event = entries[0]
            references = [
                r
                for r in registry["references"]
                if r["id"] == event["identity_reference"]
            ]
            if (
                len(references) != 1
                or references[0]["prior_status"] != "diagnostic_available"
                or references[0]["origin"] != "prior_saved_identity_review_reference"
            ):
                raise SafeError("identity_reference_unverified")
            if references[0].get("new_verification") is not False or not references[
                0
            ].get("reference_files"):
                raise SafeError("identity_reference_unverified")
            if not re.fullmatch(
                "[0-9a-f]{40}", references[0].get("reference_commit", "")
            ) or references[0].get("identity_projection_sha256") != digest(
                encoded(event)
            ):
                raise SafeError("identity_reference_projection_mismatch")
            if instant(event["mapping_valid_until"]) <= now:
                raise SafeError("identity_mapping_expired")
            sides = event["teams"]
            if (
                set(sides) != set(("home", "away"))
                or sides["home"]["canonical_id"] == sides["away"]["canonical_id"]
            ):
                raise SafeError("team_identity_invalid")
            for side, team in sides.items():
                if (
                    not re.fullmatch(r"local:team:[a-z0-9-]+", team["canonical_id"])
                    or set(team["provider_ids"])
                    != set(("api_football", "football_data"))
                    or any(
                        type(x) is not int or x <= 0
                        for x in team["provider_ids"].values()
                    )
                ):
                    raise SafeError("team_identity_invalid")
                if unsafe_content(team["display_name"]):
                    raise SafeError("unsafe_identity_label")
            if any(
                sides["home"]["provider_ids"][provider]
                == sides["away"]["provider_ids"][provider]
                for provider in ("api_football", "football_data")
            ):
                raise SafeError("team_identity_invalid")
            if instant(references[0]["prior_verified_at"]) > now:
                result.update(
                    status="temporal_unverified",
                    blockers=["identity_reference_not_available_at_verification"],
                )
                return result
            kickoff = instant(event["kickoff_utc"])
            if (
                kickoff.astimezone(ZoneInfo(event["local_timezone"])).date().isoformat()
                != match_date
            ):
                raise SafeError("event_local_date_mismatch")
            cutoff = min(now, kickoff)
            result["identity"] = {
                "canonical_mapping_reference_verified": True,
                "current_event_verified": False,
                "basis": "prior_saved_identity_review_not_new_live_validation",
                "reference": event["identity_reference"],
                "reference_commit": references[0]["reference_commit"],
                "competition": event["competition"],
                "kickoff_utc": kickoff.isoformat(),
                "teams": deepcopy(sides),
                "api_football_fixture_id": event["api_football_fixture_id"],
                "football_data_match_id": event["football_data_match_id"],
            }
            sources = files["sources.json"]["sources"]
            records = files["claims.json"]
            if not isinstance(records, list) or len(records) > 256:
                raise SafeError("claim_count_limit")
            if now >= kickoff:
                result.update(
                    status="temporal_unverified", blockers=["event_already_started"]
                )
                return result
            identities = {team["canonical_id"] for team in sides.values()}
            relevant = []
            seen = {}
            for claim in records:
                validate_claim(claim)
                if claim["event_key"] != key:
                    continue
                if claim["id"] in seen:
                    if seen[claim["id"]] != claim:
                        raise SafeError("conflicting_duplicate_claim_id")
                    continue
                seen[claim["id"]] = claim
                if claim["team_id"] not in identities:
                    result["blockers"].append("claim_team_identity_mismatch")
                    continue
                item = self.verify(claim, sources, files, cutoff, now)
                relevant.append(item)
            groups = defaultdict(list)
            for claim in relevant:
                if claim["eligible_pre_match"] and claim["value"] is not None:
                    groups[
                        (
                            claim["team_id"],
                            claim["category"],
                            claim["claim_key"],
                            claim["effective_at"],
                        )
                    ].append(claim)
            for group in groups.values():
                values = {json.dumps(c["value"], sort_keys=True) for c in group}
                if len(values) > 1:
                    for claim in group:
                        claim.update(
                            status="conflicting",
                            eligible_pre_match=False,
                            reasons=list(claim["reasons"])
                            + ["sources_disagree_same_claim_scope"],
                        )
            observations = files.get("access-observations.json", [])
            for side, team in sides.items():
                team_sources = {
                    sid
                    for sid, s in sources.items()
                    if team["canonical_id"] in s["team_ids"]
                    or event["competition"] in s["competitions"]
                }
                attempts = [
                    self.safe_observation(o)
                    for o in observations
                    if self.observation_available(o, cutoff)
                    and any(
                        o.get("url") in sources[s]["resources"].values()
                        for s in team_sources
                    )
                ]
                categories = {}
                for category in CATEGORIES:
                    found = [
                        c
                        for c in relevant
                        if c["team_id"] == team["canonical_id"]
                        and c["category"] == category
                    ]
                    categories[category] = {
                        "status": self.aggregate(found, attempts),
                        "claims": found,
                        "search_scope": "saved_cache_only",
                        "absence_is_not_proof_of_no_injury_or_suspension": True,
                    }
                result["teams"][side] = {
                    "canonical_id": team["canonical_id"],
                    "provider_ids": team["provider_ids"],
                    "categories": categories,
                    "source_access_observations": attempts,
                }
            eligible = [
                c
                for c in relevant
                if c["status"] == "verified" and c["eligible_pre_match"]
            ]
            result["provenance"]["real_web_claims_verified"] = sum(
                c["origin"] == "real_saved" for c in eligible
            )
            if result["blockers"]:
                result.update(status="identity_unverified", teams={})
                result["provenance"]["real_web_claims_verified"] = 0
            elif any(c["status"] == "conflicting" for c in relevant):
                result["status"] = "conflicting"
            elif eligible:
                result["status"] = "diagnostic_available"
            elif any(c["status"] == "source_stale" for c in relevant):
                result["status"] = "source_stale"
            elif relevant:
                result["status"] = "reported_unconfirmed"
            elif any(
                t["categories"]["news"]["status"] == "source_blocked"
                for t in result["teams"].values()
            ):
                result["status"] = "source_blocked"
            else:
                result["status"] = "not_found"
            return result
        except SafeError as error:
            result.update(
                status="data_unverified"
                if error.code.startswith(("cache_", "claim_", "conflicting_"))
                else "identity_unverified",
                blockers=[error.code],
                teams={},
            )
            return result
        except Exception:
            result.update(
                status="data_unverified", blockers=["local_contract_invalid"], teams={}
            )
            return result

    def observation_available(self, observation, cutoff):
        try:
            return instant(observation.get("collected_at")) < cutoff
        except SafeError:
            return False

    def safe_observation(self, observation):
        try:
            collected = instant(observation.get("collected_at")).isoformat()
        except SafeError:
            collected = None
        reason = observation.get("reason")
        if reason not in (
            "proxy_tunnel_denied_403",
            "https_or_network_unavailable",
            "http_access_denied_or_unavailable",
            "robots_not_a_license",
        ):
            reason = "unclassified_source_problem"
        return {
            "url": observation["url"],
            "collected_at": collected,
            "origin": observation.get("origin")
            if observation.get("origin") in ("real_access_attempt", "real_saved")
            else "unverified",
            "status": "source_blocked"
            if observation.get("status") == "source_blocked"
            else "reported_unconfirmed",
            "reason": reason,
            "http_status": observation.get("http_status")
            if type(observation.get("http_status")) is int
            else None,
            "proxy_tunnel_status": 403
            if observation.get("proxy_tunnel_status") == 403
            else None,
            "content_retrieved": bool(observation.get("content_retrieved", False)),
        }

    def aggregate(self, claims, attempts):
        if claims:
            for state in (
                "conflicting",
                "verified",
                "source_stale",
                "reported_unconfirmed",
                "source_blocked",
                "identity_unverified",
                "data_unverified",
            ):
                if any(c["status"] == state for c in claims):
                    return state
        return (
            "source_blocked"
            if any(o.get("status") == "source_blocked" for o in attempts)
            else "not_found"
        )

    def verify(self, claim, sources, files, cutoff, now):
        item = deepcopy(claim)
        item.update(
            status="reported_unconfirmed",
            eligible_pre_match=False,
            reasons=[],
            untrusted_source_content=True,
            source_type=None,
        )

        def withhold(reason, state="reported_unconfirmed"):
            item.update(status=state, value=None, description=None)
            item["reasons"].append(reason)
            return item

        try:
            if unsafe_content(claim["value"]) or unsafe_content(
                claim["description"] or ""
            ):
                return withhold("untrusted_content_quarantined")
            source = sources[claim["source_id"]]
            validated_url(claim["url"], source)
            if source["source_type"] not in (
                "official_club",
                "official_competition",
                "official_federation",
                "public_press",
                "documented_statistics",
            ):
                raise SafeError("source_type_invalid")
            item["source_type"] = source["source_type"]
            if claim["origin"] != "real_saved" and not (
                self.allow_synthetic and claim["origin"] == "synthetic"
            ):
                return withhold("synthetic_claim_not_accepted")
            if (
                source["review_state"] != "approved"
                or not source["metadata_retention_allowed"]
            ):
                return withhold(
                    "source_terms_or_retention_unverified", "source_blocked"
                )
            if (
                source["source_type"] == "official_club"
                and claim["team_id"] not in source["team_ids"]
            ):
                return withhold("source_team_identity_mismatch", "identity_unverified")
            proof = files[claim["evidence_file"]]
            proof_schema = json.loads(
                (ROOT / "contracts/reviewed-proof.schema.json").read_text()
            )
            Draft202012Validator(proof_schema, format_checker=FormatChecker()).validate(
                proof
            )
            if digest(encoded(proof)) != claim["evidence_sha256"]:
                return withhold("claim_evidence_integrity_failed", "data_unverified")
            if (
                proof["source_id"] != claim["source_id"]
                or proof["url"] != claim["url"]
                or proof["origin"] != claim["origin"]
            ):
                return withhold("claim_provenance_mismatch", "data_unverified")
            if (
                proof.get("claim_projection_sha256")
                != digest(encoded(projection(claim)))
                or proof.get("team_id") != claim["team_id"]
                or proof.get("event_key") != claim["event_key"]
            ):
                return withhold(
                    "claim_identity_or_projection_unverified", "identity_unverified"
                )
            if (
                not proof.get("reviewer_ref")
                or not proof.get("reviewed_at")
                or instant(proof["reviewed_at"]) > now
            ):
                return withhold("manual_review_missing_or_future")
            observed = instant(claim["collected_at"])
            if instant(proof["reviewed_at"]) < observed:
                return withhold("manual_review_before_observation")
            published = (
                instant(claim["published_at"]) if claim["published_at"] else None
            )
            if observed >= cutoff or published and published >= cutoff:
                return withhold("not_available_before_cutoff")
            if published and published > observed:
                return withhold("publication_after_observation")
            expires = instant(claim["fresh_until"])
            if expires > observed + __import__("datetime").timedelta(hours=24):
                return withhold("freshness_window_exceeds_24_hours")
            if (
                published
                and published + __import__("datetime").timedelta(hours=24) <= now
            ):
                return withhold("publication_older_than_24_hours", "source_stale")
            if expires <= now:
                return withhold("evidence_expired", "source_stale")
            if not published:
                item["reasons"].append("publication_timestamp_unknown_or_date_only")
                return item
            if claim["category"] == "probable_lineup":
                item["reasons"].append("probable_lineup_is_not_official")
                item["eligible_pre_match"] = True
                return item
            if (
                claim["assertion"] != "confirmed"
                or source["source_type"] == "public_press"
            ):
                item["reasons"].append("report_is_not_official_confirmation")
                item["eligible_pre_match"] = True
                return item
            if claim["category"] == "official_lineup" and not proof.get(
                "official_lineup_explicit"
            ):
                return withhold("official_lineup_not_explicitly_proven")
            item.update(status="verified", eligible_pre_match=True)
            return item
        except SafeError as error:
            item["url"] = "urn:sisal:source:withheld"
            return withhold(error.code, "data_unverified")
        except Exception:
            return withhold("evidence_missing_or_invalid", "data_unverified")
