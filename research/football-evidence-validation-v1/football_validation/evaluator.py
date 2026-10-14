"""Deterministic experimental settlement, not official bookmaker settlement."""

from decimal import Decimal

from .common import FLAGS, digest, instant, schema_errors, utc_now
from .validation import source_issues


def _settle(market, score):
    if market["period"] != "regular_time":
        return "not_evaluable", "period_data_missing"
    family, selection = market["family"], market["selection"]
    home, away = score["home"], score["away"]
    if family in ("combination", "my_combo"):
        outcomes = [_settle(leg, score) for leg in selection["legs"]]
        if any(state == "not_evaluable" for state, _ in outcomes):
            return "not_evaluable", "combination_data_or_rules_missing"
        if any(state == "void" for state, _ in outcomes):
            if selection["void_policy"] != "void_all":
                return "not_evaluable", "combination_void_policy_unknown"
            return "void", "explicit_experimental_void_all"
        return (
            "winning" if all(state == "winning" for state, _ in outcomes) else "losing"
        ), "experimental_conjunction"
    outcome = "home" if home > away else "away" if home < away else "draw"
    if family == "1x2":
        won = outcome == selection
    elif family == "double_chance":
        won = (
            outcome
            in {
                "home_draw": {"home", "draw"},
                "home_away": {"home", "away"},
                "draw_away": {"draw", "away"},
            }[selection]
        )
    elif family == "btts":
        won = (home > 0 and away > 0) == (selection == "yes")
    elif family in ("over_under", "multigoal"):
        goals = {"match": home + away, "home": home, "away": away}[selection["scope"]]
        if family == "multigoal":
            if selection["min"] > selection["max"]:
                return "not_evaluable", "invalid_goal_range"
            won = selection["min"] <= goals <= selection["max"]
        else:
            line = Decimal(str(selection["line"]))
            if line * 2 != (line * 2).to_integral_value():
                return "not_evaluable", "asian_quarter_line_rules_missing"
            if goals == line:
                return "void", "experimental_integer_line_push"
            won = goals > line if selection["direction"] == "over" else goals < line
    else:
        return "not_evaluable", "required_market_data_missing"
    return ("winning" if won else "losing"), "experimental_regular_time_rules"


def evaluate(prediction, result, *, mode="real_only", _clock=utc_now):
    """Evaluate a registered snapshot and a separately supplied verified result.

    Callers must first obtain prediction via Registry.get/verify, not trust an
    arbitrary envelope downloaded from elsewhere. No scores are inferred.
    """

    def answer(state, reasons):
        return {
            **FLAGS,
            "status": state,
            "reasons": sorted(set(reasons)),
            "rules_version": "experimental-90min-v1",
            "settlement_authority": "diagnostic_not_bookmaker",
            "data_origin": prediction.get("data", {})
            .get("snapshot", {})
            .get("data_origin", "unvalidated"),
        }

    if mode not in ("real_only", "synthetic_test"):
        raise ValueError("invalid_mode")
    if prediction.get("record_type") != "prediction":
        return answer("not_evaluable", ["prediction_required"])
    if schema_errors(prediction, "record"):
        return answer("not_evaluable", ["prediction_envelope_invalid"])
    body = {key: value for key, value in prediction.items() if key != "content_hash"}
    if prediction["content_hash"] != digest(body):
        return answer("not_evaluable", ["prediction_integrity_failed"])
    dossier = prediction["data"]["snapshot"]
    issues = schema_errors(dossier, "dossier") + schema_errors(result, "result")
    if issues:
        return answer("not_evaluable", issues)
    now = _clock()
    issues += source_issues(result["source"], now, mode, "result")
    if result["source"]["data_origin"] != dossier["data_origin"]:
        issues.append("mixed_data_origins")
    if mode == "real_only" and dossier["data_origin"] != "archived_real":
        issues.append("synthetic_not_allowed")
    identity = dossier["identity"]
    checks = {
        "match_id": identity["match_id"],
        "home_team_id": identity["home"]["id"],
        "away_team_id": identity["away"]["id"],
        "competition_id": identity["competition"]["id"],
        "season": identity["competition"]["season"],
    }
    if any(result[key] != value for key, value in checks.items()):
        issues.append("result_identity_mismatch")
    kickoff = instant(identity["kickoff_utc"])
    if instant(result["kickoff_utc"]) != kickoff:
        issues.append("result_kickoff_mismatch")
    if instant(prediction["recorded_at"]) >= kickoff:
        issues.append("prediction_not_pre_kickoff")
    if issues:
        return answer("not_evaluable", issues)
    if (
        dossier["decision"]["status"] == "no_bet"
        or dossier["decision"]["candidate_id"] is None
    ):
        return answer("not_evaluable", ["no_selection_recorded"])
    candidate = next(
        (
            c
            for c in dossier["candidates"]
            if c["id"] == dossier["decision"]["candidate_id"]
        ),
        None,
    )
    if candidate is None:
        return answer("not_evaluable", ["selected_candidate_missing"])
    if result["settlement"] == "verified_void":
        if result["settlement_proof"] is None:
            return answer("not_evaluable", ["void_authority_missing"])
        issues = source_issues(result["settlement_proof"], now, mode, "settlement")
        return (
            answer("not_evaluable", issues)
            if issues
            else answer("void", ["verified_void_instruction"])
        )
    if result["status"] != "FINISHED" or result["settlement"] != "normal":
        return answer("not_evaluable", ["final_result_or_settlement_missing"])
    if result["finished_at"] is None:
        return answer("not_evaluable", ["result_completion_time_unverified"])
    finished = instant(result["finished_at"])
    if (
        finished < kickoff
        or finished > now
        or instant(result["source"]["observed_at"]) < finished
    ):
        return answer("not_evaluable", ["result_temporal_incoherence"])
    if result["regular_time"] is None:
        return answer("not_evaluable", ["regular_time_score_missing"])
    state, reason = _settle(candidate["market"], result["regular_time"])
    return answer(state, [reason])
