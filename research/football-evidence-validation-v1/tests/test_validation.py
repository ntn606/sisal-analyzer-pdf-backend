"""Synthetic offline dossier regressions. No live or archived-real claims."""

import copy
import unittest
from datetime import timedelta

from fixtures import NOW, dossier, market
from football_validation.common import schema_errors
from football_validation.validation import validate_dossier


class ValidationTests(unittest.TestCase):
    def validate(self, data, now=NOW):
        return validate_dossier(data, mode="synthetic_test", _clock=lambda: now)

    def blocked(self, data, reason, now=NOW):
        report = self.validate(data, now)
        self.assertEqual(report["status"], "blocked", report)
        self.assertIn(reason, report["reasons"])

    def test_complete_synthetic_dossier_and_flags(self):
        report = self.validate(dossier())
        self.assertEqual(report["status"], "validated")
        self.assertEqual(report["usable_evidence_ids"], ["quote-1", "stats-1"])
        self.assertFalse(report["ready_for_quant"])
        self.assertEqual(schema_errors(report, "validation"), [])

    def test_real_only_rejects_synthetic(self):
        report = validate_dossier(dossier(), _clock=lambda: NOW)
        self.assertIn("synthetic_not_allowed", report["reasons"])

    def test_missing_quote_blocks_candidate(self):
        data = dossier()
        data["candidates"][0]["quote_id"] = None
        self.blocked(data, "current_verified_quote_required")

    def test_missing_quote_can_be_watch_not_candidate(self):
        data = dossier()
        data["decision"]["status"] = "watch"
        data["candidates"][0]["quote_id"] = None
        self.assertEqual(self.validate(data)["status"], "validated")

    def test_explicit_no_bet_can_record_missing_optional_evidence(self):
        data = dossier()
        data["decision"] = {
            "status": "no_bet",
            "candidate_id": None,
            "reasons": ["Insufficient information"],
        }
        data["candidates"] = []
        data["evidence"] = [data["evidence"][3]]
        self.assertEqual(self.validate(data)["status"], "validated")

    def test_stale_quote_and_expiry_cannot_extend_policy(self):
        data = dossier()
        data["evidence"][0]["payload"]["valid_until"] = "2027-01-01T00:00:00Z"
        self.blocked(data, "quote-1:odds_stale", NOW + timedelta(hours=2))

    def test_expired_quote(self):
        data = dossier()
        data["evidence"][0]["payload"]["valid_until"] = data["analysis_at"]
        self.blocked(data, "quote-1:odds_expired")

    def test_new_observation_cannot_rejuvenate_old_publication(self):
        data = dossier()
        data["evidence"][0]["source"]["published_at"] = "2026-10-13T22:00:00Z"
        self.blocked(data, "quote-1:odds_stale")

    def test_unknown_publication_with_verified_observation_is_not_invented(self):
        data = dossier()
        data["evidence"][0]["source"]["published_at"] = None
        self.assertEqual(self.validate(data)["status"], "validated")
        self.assertIsNone(data["evidence"][0]["source"]["published_at"])

    def test_unknown_availability_blocks(self):
        data = dossier()
        data["evidence"][0]["source"]["availability_verified"] = False
        self.blocked(data, "quote-1:availability_unverified")

    def test_missing_observation_schema_blocks(self):
        data = dossier()
        data["evidence"][0]["source"]["observed_at"] = None
        self.assertEqual(self.validate(data)["status"], "blocked")

    def test_exact_kickoff_and_after_block(self):
        for hours in (56, 57):
            with self.subTest(hours=hours):
                self.blocked(dossier(), "kickoff_reached", NOW + timedelta(hours=hours))

    def test_analysis_in_future(self):
        self.blocked(dossier(), "analysis_in_future", NOW - timedelta(seconds=1))

    def test_publication_after_analysis(self):
        data = dossier()
        data["evidence"][0]["source"]["published_at"] = "2026-10-14T10:01:00Z"
        self.blocked(data, "quote-1:publication_after_cutoff")

    def test_information_published_after_kickoff_not_pre_match(self):
        data = dossier()
        data["evidence"][2]["assessment"] = "confirmed"
        data["evidence"][2]["use_as_evidence"] = True
        data["evidence"][2]["payload"]["basis"] = "official"
        data["evidence"][2]["payload"]["category"] = "absence"
        data["evidence"][2]["source"]["published_at"] = "2026-10-16T18:01:00Z"
        data["evidence"][2]["source"]["observed_at"] = "2026-10-16T18:02:00Z"
        self.blocked(data, "news-1:publication_after_cutoff")

    def test_late_observation_blocks_backtest_even_if_publication_old(self):
        data = dossier()
        data["evidence"][0]["source"]["observed_at"] = "2026-10-14T10:01:00Z"
        self.blocked(data, "quote-1:observed_after_analysis")

    def test_future_context_is_not_smuggled_into_snapshot(self):
        data = dossier()
        data["evidence"][2]["source"]["observed_at"] = "2026-10-14T11:00:00Z"
        self.assertFalse(data["evidence"][2]["use_as_evidence"])
        self.blocked(data, "news-1:observed_after_analysis")

    def test_probable_lineup_is_not_official(self):
        for field, value in (
            ("assessment", "confirmed"),
            ("category", "official_lineup"),
        ):
            data = dossier()
            if field == "assessment":
                data["evidence"][2][field] = value
            else:
                data["evidence"][2]["payload"][field] = value
            self.blocked(data, "news-1:probable_is_not_official")

    def test_hypothesis_cannot_be_confirmed_evidence(self):
        data = dossier()
        data["evidence"][2]["use_as_evidence"] = True
        self.blocked(data, "news-1:not_confirmed")

    def test_unverified_identity(self):
        data = dossier()
        data["identity"]["proof"] = None
        self.blocked(data, "identity_unverified")

    def test_same_names_do_not_override_ids(self):
        data = dossier()
        data["identity"]["away"]["name"] = data["identity"]["home"]["name"]
        self.assertEqual(self.validate(data)["status"], "validated")
        data["evidence"][1]["payload"]["team_id"] = "synthetic:other"
        self.blocked(data, "stats-1:team_identity_mismatch")

    def test_provider_home_away_mapping_incoherent(self):
        data = dossier()
        data["identity"]["providers"][0]["canonical_home_id"] = "synthetic:away"
        self.blocked(data, "provider_identity_incoherent")

    def test_provider_competition_and_season_incoherent(self):
        for field, value in (
            ("canonical_competition_id", "synthetic:wrong-league"),
            ("season", "2025-2026"),
        ):
            data = dossier()
            data["identity"]["providers"][0][field] = value
            self.blocked(data, "provider_identity_incoherent")

    def test_youth_senior_mismatch(self):
        data = dossier()
        data["identity"]["away"]["category"] = "u19"
        self.blocked(data, "team_category_mismatch")

    def test_timezone_offset_wrong_and_unknown(self):
        data = dossier()
        data["identity"]["kickoff_local"] = "2026-10-16T19:00:00+01:00"
        self.blocked(data, "kickoff_timezone_incoherent")
        data["identity"]["timezone"] = "Not/A_Zone"
        self.blocked(data, "timezone_unknown")

    def test_timezone_missing_offset_schema(self):
        data = dossier()
        data["identity"]["kickoff_local"] = "2026-10-16T20:00:00"
        self.assertEqual(self.validate(data)["status"], "blocked")

    def test_dst_nonexistent_local_time(self):
        data = dossier()
        data["identity"]["kickoff_utc"] = "2027-03-28T01:30:00Z"
        data["identity"]["kickoff_local"] = "2027-03-28T02:30:00+01:00"
        data["identity"]["match_date"] = "2027-03-28"
        self.blocked(data, "kickoff_timezone_incoherent")

    def test_duplicate_and_conflicting_history(self):
        for conflict in (False, True):
            data = dossier()
            payload = data["evidence"][1]["payload"]
            duplicate = copy.deepcopy(payload["results"][0])
            if conflict:
                duplicate["goals_for_90"] = 3
            payload["results"].append(duplicate)
            payload["sample_size"] = 2
            self.blocked(
                data,
                "stats-1:" + ("conflicting_match" if conflict else "duplicate_match"),
            )

    def test_incomplete_or_postponed_statistics(self):
        for field, value in (("status", "POSTPONED"), ("goals_for_90", None)):
            data = dossier()
            data["evidence"][1]["payload"]["results"][0][field] = value
            self.blocked(data, "stats-1:incomplete_history")

    def test_match_future_relative_analysis(self):
        data = dossier()
        data["evidence"][1]["payload"]["results"][0]["kickoff"] = data["analysis_at"]
        self.blocked(data, "stats-1:history_after_cutoff")

    def test_quote_market_must_match_exact_family(self):
        data = dossier(
            market("over_under", {"scope": "match", "direction": "over", "line": 2.5})
        )
        data["candidates"][0]["market"] = market(
            "multigoal", {"scope": "match", "min": 2, "max": 3}
        )
        self.blocked(data, "candidate-1:quote_market_mismatch")

    def test_missing_reference_and_duplicate_evidence(self):
        data = dossier()
        data["candidates"][0]["evidence_refs"].append("missing-ref")
        self.blocked(data, "candidate-1:unusable_evidence_reference")
        data["evidence"].append(copy.deepcopy(data["evidence"][0]))
        self.blocked(data, "duplicate_evidence_id")

    def test_mixed_synthetic_real_origin_rejected(self):
        data = dossier()
        data["evidence"][2]["source"]["data_origin"] = "archived_real"
        self.blocked(data, "mixed_data_origins")

    def test_schema_rejects_extra_probability_and_modified_flags(self):
        data = dossier()
        data["probability"] = 0.9
        self.assertEqual(self.validate(data)["status"], "blocked")
        data = dossier()
        data["ready_for_quant"] = True
        self.assertEqual(self.validate(data)["status"], "blocked")
