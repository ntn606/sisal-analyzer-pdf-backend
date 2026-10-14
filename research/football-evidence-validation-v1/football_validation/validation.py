"""Conservative validation of supplied evidence, never evidence acquisition."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .common import FLAGS, instant, schema_errors, utc_now

MAX_ODDS_AGE_SECONDS = 3600
MAX_HISTORY_AGE_SECONDS = 180 * 86400


def source_issues(source, analysis, mode, prefix):
    issues = []
    if mode == "real_only" and source["data_origin"] != "archived_real":
        issues.append(prefix + ":synthetic_not_allowed")
    if not source["availability_verified"] or source["verification"] != "verified":
        issues.append(prefix + ":availability_unverified")
    observed = instant(source["observed_at"])
    if observed > analysis:
        issues.append(prefix + ":observed_after_analysis")
    if source["published_at"] is not None:
        published = instant(source["published_at"])
        if published > analysis or published > observed:
            issues.append(prefix + ":publication_after_cutoff")
    return issues


def market_issues(market, prefix):
    if market["family"] == "multigoal":
        if market["selection"]["min"] > market["selection"]["max"]:
            return [prefix + ":invalid_goal_range"]
    if market["family"] in ("combination", "my_combo"):
        return [
            issue
            for leg in market["selection"]["legs"]
            for issue in market_issues(leg, prefix)
        ]
    return []


def validate_dossier(dossier, *, mode="real_only", _clock=utc_now):
    """_clock is a trusted test seam, never accepted by CLI or dossier JSON.

    'validated' means structurally and temporally usable in this diagnostic
    contract; independent review of source authenticity remains necessary.
    """
    if mode not in ("real_only", "synthetic_test"):
        raise ValueError("invalid_mode")
    issues = schema_errors(dossier, "dossier")
    if issues:
        return {
            **FLAGS,
            "status": "blocked",
            "reasons": issues,
            "usable_evidence_ids": [],
            "data_origin": "unvalidated",
        }
    now = _clock()
    analysis = instant(dossier["analysis_at"])
    identity = dossier["identity"]
    kickoff = instant(identity["kickoff_utc"])
    if mode == "real_only" and dossier["data_origin"] != "archived_real":
        issues.append("synthetic_not_allowed")

    def check_origins(value):
        if isinstance(value, dict):
            if (
                "data_origin" in value
                and value["data_origin"] != dossier["data_origin"]
            ):
                issues.append("mixed_data_origins")
            for nested in value.values():
                check_origins(nested)
        elif isinstance(value, list):
            for nested in value:
                check_origins(nested)

    check_origins(dossier)
    if analysis > now:
        issues.append("analysis_in_future")
    if analysis >= kickoff or now >= kickoff:
        issues.append("kickoff_reached")
    if identity["verification"] != "verified" or identity["proof"] is None:
        issues.append("identity_unverified")
    else:
        issues += source_issues(identity["proof"], analysis, mode, "identity")
    local = datetime.fromisoformat(identity["kickoff_local"].replace("Z", "+00:00"))
    try:
        zone = ZoneInfo(identity["timezone"])
        expected = kickoff.astimezone(zone)
        if (
            local.replace(tzinfo=None) != expected.replace(tzinfo=None)
            or local.utcoffset() != expected.utcoffset()
            or instant(identity["kickoff_local"]) != kickoff
            or identity["match_date"] != expected.date().isoformat()
        ):
            issues.append("kickoff_timezone_incoherent")
    except (ZoneInfoNotFoundError, ValueError):
        issues.append("timezone_unknown")
    if identity["home"]["id"] == identity["away"]["id"]:
        issues.append("team_identity_collision")
    if identity["home"]["category"] != identity["away"]["category"]:
        issues.append("team_category_mismatch")
    providers = set()
    for mapping in identity["providers"]:
        if mapping["provider"] in providers:
            issues.append("provider_mapping_ambiguous")
        providers.add(mapping["provider"])
        if mapping["home_team_id"] == mapping["away_team_id"]:
            issues.append("provider_team_collision")
        if (
            mapping["canonical_home_id"] != identity["home"]["id"]
            or mapping["canonical_away_id"] != identity["away"]["id"]
            or mapping["canonical_competition_id"] != identity["competition"]["id"]
            or instant(mapping["kickoff_utc"]) != kickoff
            or mapping["season"] != identity["competition"]["season"]
        ):
            issues.append("provider_identity_incoherent")
        issues += source_issues(mapping["proof"], analysis, mode, "provider_identity")
    if identity["sisal"] is not None:
        issues += source_issues(
            identity["sisal"]["proof"], analysis, mode, "sisal_identity"
        )

    evidence = {}
    usable = []
    withheld = []
    for item in dossier["evidence"]:
        key = item["id"]
        if key in evidence:
            issues.append("duplicate_evidence_id")
        evidence[key] = item
        if not item["use_as_evidence"]:
            withheld.append({"id": key, "assessment": item["assessment"]})
        if item["assessment"] == "missing":
            continue
        payload = item["payload"]
        item_issues = source_issues(item["source"], analysis, mode, key)
        # Even excluded context cannot contain facts first seen after the
        # analysis: storing them in a pre-match snapshot risks future leakage.
        issues += [
            code
            for code in item_issues
            if code.endswith((":observed_after_analysis", ":publication_after_cutoff"))
        ]
        if item["use_as_evidence"] and item["assessment"] != "confirmed":
            item_issues.append(key + ":not_confirmed")
        if item["kind"] == "odds":
            item_issues += market_issues(payload["market"], key)
            if Decimal(payload["decimal"]) <= 1:
                item_issues.append(key + ":invalid_decimal_odds")
            reference_times = [instant(item["source"]["observed_at"])]
            if item["source"]["published_at"] is not None:
                reference_times.append(instant(item["source"]["published_at"]))
            # A new observation must not rejuvenate a known old quote.
            age = (max(now, analysis) - min(reference_times)).total_seconds()
            if age > MAX_ODDS_AGE_SECONDS:
                item_issues.append(key + ":odds_stale")
            if payload["valid_until"] is not None:
                expiry = instant(payload["valid_until"])
                if expiry < instant(item["source"]["observed_at"]) or expiry <= max(
                    now, analysis
                ):
                    item_issues.append(key + ":odds_expired")
        else:
            if payload["team_id"] not in (
                identity["home"]["id"],
                identity["away"]["id"],
            ):
                item_issues.append(key + ":team_identity_mismatch")
        if item["kind"] == "news":
            probable = (
                payload["category"] == "probable_lineup"
                or payload["basis"] == "probable"
            )
            if probable and (
                payload["category"] == "official_lineup"
                or item["assessment"] == "confirmed"
            ):
                # Always reject this semantic inconsistency, even as context.
                issues.append(key + ":probable_is_not_official")
            if (
                payload["category"] == "official_lineup"
                and payload["basis"] != "official"
            ):
                issues.append(key + ":official_lineup_unverified")
        if item["kind"] == "statistics":
            results = payload["results"]
            if payload["sample_size"] != len(results):
                item_issues.append(key + ":sample_size_mismatch")
            seen = {}
            dates = []
            for match in results:
                # Provider-namespaced IDs are required by the documented contract.
                if match["match_id"] in seen:
                    code = (
                        "duplicate_match"
                        if seen[match["match_id"]] == match
                        else "conflicting_match"
                    )
                    item_issues.append(key + ":" + code)
                seen[match["match_id"]] = match
                date = instant(match["kickoff"])
                dates.append(date)
                if date >= analysis or date >= kickoff:
                    item_issues.append(key + ":history_after_cutoff")
                if (analysis - date).total_seconds() > MAX_HISTORY_AGE_SECONDS:
                    item_issues.append(key + ":history_stale")
                if (
                    match["team_id"] != payload["team_id"]
                    or match["opponent_id"] == match["team_id"]
                ):
                    item_issues.append(key + ":history_identity_mismatch")
                if (
                    match["status"] != "FINISHED"
                    or match["goals_for_90"] is None
                    or match["goals_against_90"] is None
                ):
                    item_issues.append(key + ":incomplete_history")
                history_issues = source_issues(
                    match["source"], analysis, mode, key + ":history"
                )
                item_issues += history_issues
                issues += [
                    code
                    for code in history_issues
                    if code.endswith(
                        (":observed_after_analysis", ":publication_after_cutoff")
                    )
                ]
                if instant(match["source"]["observed_at"]) < date:
                    item_issues.append(key + ":result_observed_before_match")
            if results:
                if (
                    payload["sample_start"] is None
                    or payload["sample_end"] is None
                    or instant(payload["sample_start"]) != min(dates)
                    or instant(payload["sample_end"]) != max(dates)
                ):
                    item_issues.append(key + ":sample_dates_mismatch")
            elif (
                payload["sample_start"] is not None or payload["sample_end"] is not None
            ):
                item_issues.append(key + ":sample_dates_mismatch")
            if not results and item["use_as_evidence"]:
                item_issues.append(key + ":empty_sample")
        if item["use_as_evidence"]:
            issues += item_issues
            if not item_issues:
                usable.append(key)
        elif item_issues:
            withheld[-1]["reasons"] = sorted(set(item_issues))

    candidates = {}
    for candidate in dossier["candidates"]:
        key = candidate["id"]
        if key in candidates:
            issues.append("duplicate_candidate_id")
        candidates[key] = candidate
        issues += market_issues(candidate["market"], key)
        for evidence_id in candidate["evidence_refs"]:
            if evidence_id not in usable:
                issues.append(key + ":unusable_evidence_reference")
        quote_id = candidate["quote_id"]
        if quote_id is not None:
            quote = evidence.get(quote_id)
            if quote is None or quote["kind"] != "odds" or quote_id not in usable:
                issues.append(key + ":quote_unavailable")
            elif quote["payload"]["market"] != candidate["market"]:
                issues.append(key + ":quote_market_mismatch")
    decision = dossier["decision"]
    selected = candidates.get(decision["candidate_id"])
    if decision["candidate_id"] is not None and selected is None:
        issues.append("selected_candidate_missing")
    if decision["status"] == "candidate" and (
        selected is None or selected["quote_id"] is None
    ):
        issues.append("current_verified_quote_required")
    if decision["status"] == "no_bet" and decision["candidate_id"] is not None:
        issues.append("no_bet_has_selection")
    return {
        **FLAGS,
        "status": "blocked" if issues else "validated",
        "reasons": sorted(set(issues)),
        "usable_evidence_ids": usable,
        "withheld_evidence": withheld,
        "data_origin": dossier["data_origin"],
        "freshness_policy": {
            "odds_max_age_seconds": MAX_ODDS_AGE_SECONDS,
            "history_max_age_days": 180,
        },
        "verification_scope": "operator_attested_offline_not_independently_certified",
    }
