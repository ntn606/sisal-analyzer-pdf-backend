"""All fixtures and settlement rules are explicitly synthetic/experimental."""

import tempfile
import unittest

from fixtures import AFTER, NOW, dossier, market, result, source
from football_validation import Registry, evaluate
from football_validation.common import schema_errors


class EvaluatorTests(unittest.TestCase):
    def assess(self, selection, score=None, transform=None):
        with tempfile.TemporaryDirectory() as directory:
            prediction = Registry(
                directory, mode="synthetic_test", _clock=lambda: NOW
            ).record_prediction(dossier(selection))
        outcome = result(score)
        if transform:
            transform(outcome)
        report = evaluate(
            prediction, outcome, mode="synthetic_test", _clock=lambda: AFTER
        )
        self.assertEqual(schema_errors(report, "evaluation"), [])
        return report

    def test_1x2_winning_losing_draw(self):
        self.assertEqual(self.assess(market())["status"], "winning")
        self.assertEqual(self.assess(market(selection="away"))["status"], "losing")
        self.assertEqual(
            self.assess(market(selection="draw"), {"home": 1, "away": 1})["status"],
            "winning",
        )

    def test_double_chance(self):
        for selection, state in (
            ("home_draw", "winning"),
            ("home_away", "winning"),
            ("draw_away", "losing"),
        ):
            self.assertEqual(
                self.assess(market("double_chance", selection))["status"], state
            )

    def test_over_under_half_lines_and_integer_push(self):
        for line, state in ((2.5, "winning"), (3.5, "losing"), (3, "void")):
            self.assertEqual(
                self.assess(
                    market(
                        "over_under",
                        {"scope": "match", "line": line, "direction": "over"},
                    )
                )["status"],
                state,
            )
        self.assertEqual(
            self.assess(
                market(
                    "over_under", {"scope": "home", "line": 2.5, "direction": "under"}
                )
            )["status"],
            "winning",
        )

    def test_asian_quarter_lines_not_assumed(self):
        self.assertEqual(
            self.assess(
                market(
                    "over_under", {"scope": "match", "line": 2.25, "direction": "over"}
                )
            )["status"],
            "not_evaluable",
        )

    def test_btts(self):
        self.assertEqual(self.assess(market("btts", "yes"))["status"], "winning")
        self.assertEqual(
            self.assess(market("btts", "no"), {"home": 2, "away": 0})["status"],
            "winning",
        )

    def test_multigoal_range_not_over_under(self):
        multi = market("multigoal", {"min": 2, "max": 3, "scope": "match"})
        over = market(
            "over_under", {"line": 1.5, "direction": "over", "scope": "match"}
        )
        score = {"home": 3, "away": 1}
        self.assertEqual(self.assess(multi, score)["status"], "losing")
        self.assertEqual(self.assess(over, score)["status"], "winning")

    def test_multigoal_team_and_bounds(self):
        self.assertEqual(
            self.assess(market("multigoal", {"min": 2, "max": 2, "scope": "home"}))[
                "status"
            ],
            "winning",
        )
        self.assertEqual(
            self.assess(market("multigoal", {"min": 0, "max": 0, "scope": "away"}))[
                "status"
            ],
            "losing",
        )

    def test_combination_and_my_combo_goal_only(self):
        for family in ("combination", "my_combo"):
            selection = market(
                family,
                {"legs": [market(), market("btts", "yes")], "void_policy": "unknown"},
            )
            self.assertEqual(self.assess(selection)["status"], "winning")

    def test_combo_needs_corners_not_available_in_final_score(self):
        selection = market(
            "my_combo",
            {
                "legs": [
                    market(),
                    market(
                        "unsupported",
                        {"label": "Corners over 8.5", "required_data": ["corners"]},
                    ),
                ],
                "void_policy": "unknown",
            },
        )
        self.assertEqual(self.assess(selection)["status"], "not_evaluable")

    def test_combo_void_rule_unknown(self):
        selection = market(
            "combination",
            {
                "legs": [
                    market(),
                    market(
                        "over_under", {"scope": "match", "line": 3, "direction": "over"}
                    ),
                ],
                "void_policy": "unknown",
            },
        )
        self.assertEqual(self.assess(selection)["status"], "not_evaluable")
        selection["selection"]["void_policy"] = "void_all"
        self.assertEqual(self.assess(selection)["status"], "void")

    def test_penalties_do_not_change_90_minute_draw(self):
        def penalties(outcome):
            outcome["extra_time"] = {"home": 2, "away": 2}
            outcome["penalties"] = {"home": 5, "away": 4}

        self.assertEqual(
            self.assess(market(selection="draw"), {"home": 1, "away": 1}, penalties)[
                "status"
            ],
            "winning",
        )
        self.assertEqual(
            self.assess(market(), {"home": 1, "away": 1}, penalties)["status"], "losing"
        )

    def test_missing_90_minute_score_not_replaced_by_extra_time(self):
        def missing(outcome):
            outcome["regular_time"] = None
            outcome["extra_time"] = {"home": 2, "away": 1}

        self.assertEqual(
            self.assess(market(), transform=missing)["status"], "not_evaluable"
        )

    def test_first_half_not_evaluable_from_final_score(self):
        self.assertEqual(
            self.assess(market(period="first_half"))["status"], "not_evaluable"
        )

    def test_postponed_and_cancelled_not_automatically_void(self):
        for status in ("POSTPONED", "CANCELLED", "IN_PLAY"):
            self.assertEqual(
                self.assess(market(), transform=lambda x: x.update(status=status))[
                    "status"
                ],
                "not_evaluable",
            )

    def test_void_requires_independent_instruction_proof(self):
        def void(outcome):
            outcome["status"] = "CANCELLED"
            outcome["settlement"] = "verified_void"
            outcome["settlement_proof"] = source(
                "void", "2026-10-16T20:10:00Z", "2026-10-16T20:05:00Z"
            )

        self.assertEqual(self.assess(market(), transform=void)["status"], "void")
        self.assertEqual(
            self.assess(
                market(), transform=lambda x: x.update(settlement="verified_void")
            )["status"],
            "not_evaluable",
        )

    def test_wrong_team_competition_season_kickoff_block(self):
        for key, value in (
            ("home_team_id", "synthetic:other"),
            ("competition_id", "synthetic:other-league"),
            ("season", "2025-2026"),
            ("kickoff_utc", "2026-10-16T19:00:00Z"),
        ):
            with self.subTest(key=key):
                self.assertEqual(
                    self.assess(market(), transform=lambda x: x.update({key: value}))[
                        "status"
                    ],
                    "not_evaluable",
                )

    def test_unverified_and_future_result(self):
        def unverified(outcome):
            outcome["source"]["verification"] = "reported_unconfirmed"

        def future(outcome):
            outcome["source"]["observed_at"] = "2026-10-17T00:00:00Z"

        for transform in (unverified, future):
            self.assertEqual(
                self.assess(market(), transform=transform)["status"], "not_evaluable"
            )

    def test_unknown_completion_time(self):
        self.assertEqual(
            self.assess(market(), transform=lambda x: x.update(finished_at=None))[
                "status"
            ],
            "not_evaluable",
        )

    def test_direct_evaluator_rejects_modified_prediction_envelope(self):
        with tempfile.TemporaryDirectory() as directory:
            prediction = Registry(
                directory, mode="synthetic_test", _clock=lambda: NOW
            ).record_prediction(dossier())
        prediction["data"]["snapshot"]["decision"]["status"] = "watch"
        report = evaluate(
            prediction, result(), mode="synthetic_test", _clock=lambda: AFTER
        )
        self.assertEqual(report["reasons"], ["prediction_integrity_failed"])

    def test_no_bet_not_a_losing_prediction(self):
        data = dossier()
        data["decision"] = {
            "status": "no_bet",
            "candidate_id": None,
            "reasons": ["Synthetic abstention"],
        }
        with tempfile.TemporaryDirectory() as directory:
            prediction = Registry(
                directory, mode="synthetic_test", _clock=lambda: NOW
            ).record_prediction(data)
        report = evaluate(
            prediction, result(), mode="synthetic_test", _clock=lambda: AFTER
        )
        self.assertEqual(report["status"], "not_evaluable")
        self.assertEqual(report["reasons"], ["no_selection_recorded"])
